/* SPDX-License-Identifier: MIT
 * Fast sequential RV64 functional simulator for the benchmark runners.
 *
 * Executes the same subset as sim/cpu/reference.py (RV64I, M, Zba, Zbb, Zbs,
 * fence, fence.i; ecall/ebreak and every fault stop the run) with the same
 * byte-addressed memory, starting at PC 0 with all registers 0, or from a
 * saved state. It is a laboratory interpreter like reference.py, not an ISA
 * oracle; lzma_run.py compares its trace with reference.py's before relying
 * on it. It exists because reference.py runs about 50 k instructions per
 * second, and the large-dictionary LZMA kernels run billions.
 *
 * --fp 1 adds RV64F and RV64D per cpu/architecture.md (RV64F and RV64D),
 * with the trace extension (f destinations 20-3f, F and C records); --fp-soft 1 uses the exact software
 * arithmetic for every FP operation instead of the AArch64 FPU. Without --fp the behaviour, traces and
 * state files are those of rv_iss.c. With --fp 1 state files are "RVISSST2": as below, plus u64 f0..f31
 * and u64 fcsr after x31.
 *
 * Usage: rv_iss --ram BYTES (--image FILE | --state FILE) [options]
 *   --image FILE         raw memory image (bench.bin), zero-padded to --ram
 *   --state FILE         saved state (format below) instead of an image
 *   --mailbox HEX        report marker stores and mailbox words (as lzma_run.scan)
 *   --max N              stop with an error after N instructions (default 2^62)
 *   --dump-at LIST       comma-separated instruction indices: before each one
 *                        executes, write <dump-prefix><index>.state
 *   --dump-prefix PATH   prefix for --dump-at files
 *   --trace FILE         write reference.py-format trace lines for the
 *   --trace-from A       instructions with program-order index in [A, B),
 *   --trace-to B         their memory writes included (default: all)
 *   --final-memory FILE  write the memory at the end
 *   --final-state FILE   write the state at the end (the stopping instruction
 *                        not executed)
 *   --warm-caches I,D,K,W,L  model L1s of I and D beats and a K KiB, W-way, L-byte-line
 *                        tags-only L2; --dump-at also writes <prefix><index>.l2
 * Prints one JSON object on stdout: instructions retired, the stop (trap
 * cause, tval and PC, as reference.py's T line), the marker stores with the
 * program-order index of the storing instruction, the mailbox words written
 * with full 8-byte stores, and the wall time.
 *
 * State file: "RVISSST1", u64 instruction index, u64 pc, u64 x0..x31,
 * u64 memory bytes, then the memory; all little-endian.
 *
 * --sys 1 selects system mode (cpu/PRIV-CONTRACT.md, a draft): RV64GC with M/S/U, Sv39, the lab-virt devices
 * and DRAM of --ram bytes at 0x8000_0000. Its options: --elf FILE (loaded by physical address; tohost and
 * fromhost symbols enable HTIF exit), --bin FILE@ADDR (raw, repeatable), --dtb FILE (into the boot ROM after
 * the reset code), --time lab|spike, --commit-log FILE (Spike --log-commits format; --commit-from/--commit-to
 * select an instruction range), --uart-in FILE (scripted RX bytes), --uart-out FILE (TX; default stdout),
 * --isa rv64...(default rv64imafdc_zicsr_zifencei_zicntr; also b/zba_zbb_zbs) and --priv m|mu|msu (default msu),
 * --marchid N, --adopt FILE (mcycle reads take the values of the N records in FILE, an RTL trace, in order:
 * the RTL is the source of mcycle, which counts its clocks; each adopted read is written to --trace as N),
 * --dump-on-output STR (write <dump-prefix>marker.state once the console output ends with STR);
 * --state, --dump-at/--dump-prefix and --final-state read and write "RVISSST3" full-system states
 * (layout in PRIV-CONTRACT.md); --trace adds E (exception) and I (interrupt) records. Without --sys nothing
 * below changes.
 */
#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef uint64_t u64;
typedef int64_t i64;
typedef uint32_t u32;

static uint8_t *mem;
static u64 ram;
static u64 regs[64];   /* x0-x31, then f0-f31 (destination codes 32-63 of the trace) */
static u64 pc, count;
static u64 mailbox = ~(u64)0;
static FILE *trace_fd;
static u64 trace_from = 0, trace_to = ~(u64)0;
static u64 *dumps;
static size_t ndumps, next_dump;
static const char *dump_prefix = "state-";

/* ---- F and D (cpu/architecture.md (RV64F and RV64D)), enabled by --fp 1 ------------------------------------
 * Two implementations of the arithmetic:
 *  - hardware: on AArch64 the host FPU through inline assembly (FPCR rounding mode, FPSR flags), with
 *    the RISC-V rules applied on top: canonical NaN results, and tininess after rounding (AArch64
 *    detects it before rounding; when the FPU reports underflow for a result of magnitude 2^emin the
 *    operation is redone in software). RMM arithmetic, which AArch64 lacks, also uses software.
 *  - software: exact integer arithmetic (unsigned __int128 with a jammed sticky bit), used on other
 *    hosts, for the cases above, and for every operation with --fp-soft 1 (a self-check).
 * Sign injection, min/max, compares, classify and moves are bit logic shared by both. */
typedef unsigned __int128 u128;

static int fp_on, fp_soft, host_fz;
#define fregs (regs + 32)
static u32 fcsr;

enum { FL_NX = 1, FL_UF = 2, FL_OF = 4, FL_DZ = 8, FL_NV = 16 };
enum { RM_RNE, RM_RTZ, RM_RDN, RM_RUP, RM_RMM };

typedef struct { int p, fbits, ebits, bias, emin, emax, width; u64 qnan, infb, maxfin, sbit, minnorm; } fmt_t;
static const fmt_t FMT_S = {24, 23, 8, 127, -126, 127, 32, 0x7fc00000ull, 0x7f800000ull, 0x7f7fffffull,
                            0x80000000ull, 0x00800000ull};
static const fmt_t FMT_D = {53, 52, 11, 1023, -1022, 1023, 64, 0x7ff8000000000000ull, 0x7ff0000000000000ull,
                            0x7fefffffffffffffull, 0x8000000000000000ull, 0x0010000000000000ull};

enum { C_NAN, C_INF, C_ZERO, C_FIN };
enum { OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_SQRT, OP_FMA };
typedef struct { int cls, sign, snan, e; u64 m; } unp_t;

static unp_t fp_unpack(u64 bits, const fmt_t *f) {
    unp_t u = {0, (int)((bits >> (f->width - 1)) & 1), 0, 0, 0};
    u64 ex = (bits >> f->fbits) & ((1ull << f->ebits) - 1), fr = bits & ((1ull << f->fbits) - 1);
    if (ex == (1ull << f->ebits) - 1) {
        u.cls = fr ? C_NAN : C_INF;
        u.snan = fr && !((fr >> (f->fbits - 1)) & 1);
    } else if (ex == 0) {
        u.cls = fr ? C_FIN : C_ZERO;
        u.m = fr; u.e = f->emin - f->fbits;
    } else {
        u.cls = C_FIN; u.m = fr | (1ull << f->fbits); u.e = (int)ex - f->bias - f->fbits;
    }
    return u;
}

static inline u64 fp_zero(int sign, const fmt_t *f) { return sign ? f->sbit : 0; }
static inline u64 fp_inf(int sign, const fmt_t *f) { return fp_zero(sign, f) | f->infb; }
static inline int is_nan_bits(u64 v, const fmt_t *f) { return (v & ~f->sbit) > f->infb; }
static inline int is_snan_bits(u64 v, const fmt_t *f) {
    return is_nan_bits(v, f) && !((v >> (f->fbits - 1)) & 1);
}

static int bitlen128(u128 x) {
    u64 hi = (u64)(x >> 64), lo = (u64)x;
    return hi ? 128 - __builtin_clzll(hi) : lo ? 64 - __builtin_clzll(lo) : 0;
}

/* Drop s low bits of m (s >= 1 whenever sticky: a fraction below them is non-zero) in mode rm. */
static u128 round_shift(u128 m, int s, int sticky, int sign, int rm, int *inexact) {
    if (s <= 0) { *inexact = 0; return m << -s; }
    u128 q, rem, half;
    int far = s > 128;
    if (s >= 128) { q = 0; rem = m; half = (u128)1 << 127; }
    else { q = m >> s; rem = m & (((u128)1 << s) - 1); half = (u128)1 << (s - 1); }
    *inexact = rem != 0 || sticky;
    if (!*inexact) return q;
    int above = !far && (rem > half || (rem == half && sticky));
    int tie = !far && rem == half && !sticky;
    int up;
    switch (rm) {
    case RM_RNE: up = above || (tie && (q & 1)); break;
    case RM_RTZ: up = 0; break;
    case RM_RDN: up = sign; break;
    case RM_RUP: up = !sign; break;
    default: up = above || tie; break;
    }
    return q + (u128)up;
}

/* Round (-1)^sign * (m + sticky) * 2^e, m > 0, to format f (FP-CONTRACT.md section 5). */
static u64 soft_round(int sign, u128 m, int e, int sticky, const fmt_t *f, int rm, unsigned *fl) {
    int nb = bitlen128(m), inexact;
    int s = nb - f->p;
    if (f->emin - f->fbits - e > s) s = f->emin - f->fbits - e;
    u128 q = round_shift(m, s, sticky, sign, rm, &inexact);
    if (bitlen128(q) > f->p) { q >>= 1; s++; }
    unsigned flags = inexact ? FL_NX : 0;
    if (q == 0) { *fl |= flags | FL_UF | FL_NX; return fp_zero(sign, f); }
    int E = bitlen128(q) - 1 + e + s;
    if (E > f->emax) {
        *fl |= flags | FL_OF | FL_NX;
        if (rm == RM_RNE || rm == RM_RMM || (rm == RM_RUP && !sign) || (rm == RM_RDN && sign)) return fp_inf(sign, f);
        return fp_zero(sign, f) | f->maxfin;
    }
    if (inexact) {
        int t, s1 = nb > f->p ? nb - f->p : 0;
        u128 q1 = s1 ? round_shift(m, s1, sticky, sign, rm, &t) : m;
        if (bitlen128(q1) - 1 + e + s1 < f->emin) flags |= FL_UF;
    }
    *fl |= flags;
    if (bitlen128(q) == f->p)
        return fp_zero(sign, f) | (u64)(E + f->bias) << f->fbits | ((u64)q & ((1ull << f->fbits) - 1));
    return fp_zero(sign, f) | (u64)q;
}

/* Exact sum of two non-zero values m * 2^e (m up to 106 bits), rounded once. Both are normalized to a
 * 125-bit significand; the smaller is shifted right with its lost bits jammed into bit 0, which is
 * at least 70 bits below every rounding position used for the result. */
static u64 add_exact(int sa, u128 ma, int ea, int sb, u128 mb, int eb, const fmt_t *f, int rm, unsigned *fl) {
    int la = bitlen128(ma), lb = bitlen128(mb);
    ma <<= 125 - la; ea -= 125 - la;
    mb <<= 125 - lb; eb -= 125 - lb;
    if (ea < eb) {
        int ts = sa; sa = sb; sb = ts;
        u128 tm = ma; ma = mb; mb = tm;
        int te = ea; ea = eb; eb = te;
    }
    int d = ea - eb;
    if (d >= 128) mb = 1;
    else if (d) mb = (mb >> d) | (u128)((mb & (((u128)1 << d) - 1)) != 0);
    u128 r;
    int sign;
    if (sa == sb) { r = ma + mb; sign = sa; }
    else if (ma >= mb) { r = ma - mb; sign = sa; }
    else { r = mb - ma; sign = sb; }
    if (r == 0) return fp_zero(rm == RM_RDN, f);
    return soft_round(sign, r, ea, 0, f, rm, fl);
}

static u64 soft_add(u64 a, u64 b, const fmt_t *f, int rm, int sub, unsigned *fl) {
    unp_t x = fp_unpack(a, f), y = fp_unpack(b, f);
    if (x.cls == C_NAN || y.cls == C_NAN) { if (x.snan || y.snan) *fl |= FL_NV; return f->qnan; }
    y.sign ^= sub;
    if (x.cls == C_INF || y.cls == C_INF) {
        if (x.cls == C_INF && y.cls == C_INF && x.sign != y.sign) { *fl |= FL_NV; return f->qnan; }
        return fp_inf(x.cls == C_INF ? x.sign : y.sign, f);
    }
    if (x.cls == C_ZERO && y.cls == C_ZERO) return fp_zero(x.sign == y.sign ? x.sign : rm == RM_RDN, f);
    if (y.cls == C_ZERO) return a;
    if (x.cls == C_ZERO) return sub ? b ^ f->sbit : b;
    return add_exact(x.sign, x.m, x.e, y.sign, y.m, y.e, f, rm, fl);
}

static u64 soft_mul(u64 a, u64 b, const fmt_t *f, int rm, unsigned *fl) {
    unp_t x = fp_unpack(a, f), y = fp_unpack(b, f);
    if (x.cls == C_NAN || y.cls == C_NAN) { if (x.snan || y.snan) *fl |= FL_NV; return f->qnan; }
    int sign = x.sign ^ y.sign;
    if ((x.cls == C_INF && y.cls == C_ZERO) || (x.cls == C_ZERO && y.cls == C_INF)) { *fl |= FL_NV; return f->qnan; }
    if (x.cls == C_INF || y.cls == C_INF) return fp_inf(sign, f);
    if (x.cls == C_ZERO || y.cls == C_ZERO) return fp_zero(sign, f);
    return soft_round(sign, (u128)x.m * y.m, x.e + y.e, 0, f, rm, fl);
}

static u64 soft_div(u64 a, u64 b, const fmt_t *f, int rm, unsigned *fl) {
    unp_t x = fp_unpack(a, f), y = fp_unpack(b, f);
    if (x.cls == C_NAN || y.cls == C_NAN) { if (x.snan || y.snan) *fl |= FL_NV; return f->qnan; }
    int sign = x.sign ^ y.sign;
    if (x.cls == C_INF) { if (y.cls == C_INF) { *fl |= FL_NV; return f->qnan; } return fp_inf(sign, f); }
    if (y.cls == C_INF) return fp_zero(sign, f);
    if (y.cls == C_ZERO) {
        if (x.cls == C_ZERO) { *fl |= FL_NV; return f->qnan; }
        *fl |= FL_DZ;
        return fp_inf(sign, f);
    }
    if (x.cls == C_ZERO) return fp_zero(sign, f);
    int sx = 53 - (64 - __builtin_clzll(x.m)), sy = 53 - (64 - __builtin_clzll(y.m));
    u64 mx = x.m << sx, my = y.m << sy;          /* both in [2^52, 2^53) */
    u128 num = (u128)mx << 64;
    u128 q = num / my;                            /* more than 63 bits */
    int sticky = num % my != 0;
    return soft_round(sign, q, (x.e - sx) - (y.e - sy) - 64, sticky, f, rm, fl);
}

static u64 isqrt128(u128 n) {
    u128 r = 0, bit = (u128)1 << 126;
    while (bit > n) bit >>= 2;
    while (bit) {
        if (n >= r + bit) { n -= r + bit; r = (r >> 1) + bit; }
        else r >>= 1;
        bit >>= 2;
    }
    return (u64)r;
}

static u64 soft_sqrt(u64 a, const fmt_t *f, int rm, unsigned *fl) {
    unp_t x = fp_unpack(a, f);
    if (x.cls == C_NAN) { if (x.snan) *fl |= FL_NV; return f->qnan; }
    if (x.cls == C_ZERO) return a;
    if (x.sign) { *fl |= FL_NV; return f->qnan; }
    if (x.cls == C_INF) return a;
    int sh = 53 - (64 - __builtin_clzll(x.m));
    u64 m = x.m << sh;
    int e = x.e - sh;
    if (e & 1) { m <<= 1; e--; }
    u128 rad = (u128)m << 64;                     /* 117 or 118 bits */
    u64 root = isqrt128(rad);                     /* 59 bits */
    return soft_round(0, root, (e - 64) / 2, (u128)root * root != rad, f, rm, fl);
}

/* (-1)^np * a * b + (-1)^nc * c with one rounding: FMADD (0,0), FMSUB (0,1), FNMSUB (1,0), FNMADD (1,1). */
static u64 soft_fma(u64 a, u64 b, u64 c, const fmt_t *f, int rm, int np, int nc, unsigned *fl) {
    unp_t x = fp_unpack(a, f), y = fp_unpack(b, f), z = fp_unpack(c, f);
    int inf_zero = (x.cls == C_INF && y.cls == C_ZERO) || (x.cls == C_ZERO && y.cls == C_INF);
    if (x.cls == C_NAN || y.cls == C_NAN || z.cls == C_NAN || inf_zero) {
        if (x.snan || y.snan || z.snan || inf_zero) *fl |= FL_NV;
        return f->qnan;
    }
    int sp = x.sign ^ y.sign ^ np, sc = z.sign ^ nc;
    if (x.cls == C_INF || y.cls == C_INF) {
        if (z.cls == C_INF && sc != sp) { *fl |= FL_NV; return f->qnan; }
        return fp_inf(sp, f);
    }
    if (z.cls == C_INF) return fp_inf(sc, f);
    int pz = x.cls == C_ZERO || y.cls == C_ZERO;
    if (pz && z.cls == C_ZERO) return fp_zero(sp == sc ? sp : rm == RM_RDN, f);
    if (pz) return (c & ~f->sbit) | fp_zero(sc, f);
    u128 mp = (u128)x.m * y.m;
    if (z.cls == C_ZERO) return soft_round(sp, mp, x.e + y.e, 0, f, rm, fl);
    return add_exact(sp, mp, x.e + y.e, sc, z.m, z.e, f, rm, fl);
}

static u64 soft_cvt_ff(u64 a, const fmt_t *src, const fmt_t *dst, int rm, unsigned *fl) {
    unp_t x = fp_unpack(a, src);
    if (x.cls == C_NAN) { if (x.snan) *fl |= FL_NV; return dst->qnan; }
    if (x.cls == C_INF) return fp_inf(x.sign, dst);
    if (x.cls == C_ZERO) return fp_zero(x.sign, dst);
    return soft_round(x.sign, x.m, x.e, 0, dst, rm, fl);
}

static u64 soft_int2f(int sign, u64 mag, const fmt_t *f, int rm, unsigned *fl) {
    if (!mag) return 0;
    return soft_round(sign, mag, 0, 0, f, rm, fl);
}

/* FCVT.W/WU/L/LU: the 64-bit x-register value (32-bit results sign-extended). */
static u64 int_result(i64 v, int bits) { return bits == 32 ? (u64)(i64)(int32_t)(u32)v : (u64)v; }
static u64 sat_result(int sign_neg, int bits, int uns) {
    if (uns) return int_result(sign_neg ? 0 : (i64)(bits == 32 ? 0xffffffffull : ~0ull), bits);
    if (bits == 32) return int_result(sign_neg ? INT32_MIN : INT32_MAX, 32);
    return sign_neg ? (u64)INT64_MIN : (u64)INT64_MAX;
}

static u64 soft_f2int(u64 a, const fmt_t *f, int rm, int bits, int uns, unsigned *fl) {
    unp_t x = fp_unpack(a, f);
    if (x.cls == C_NAN) { *fl |= FL_NV; return sat_result(0, bits, uns); }
    if (x.cls == C_INF) { *fl |= FL_NV; return sat_result(x.sign, bits, uns); }
    if (x.cls == C_ZERO) return 0;
    int inexact = 0;
    u128 mag;
    int nb = 64 - __builtin_clzll(x.m);
    if (x.e >= 0) {
        if (nb + x.e > 65) { *fl |= FL_NV; return sat_result(x.sign, bits, uns); }
        mag = (u128)x.m << x.e;
    } else mag = round_shift(x.m, -x.e, 0, x.sign, rm, &inexact);
    u128 limit = uns ? (x.sign ? 0 : ((u128)1 << bits) - 1)
                     : (x.sign ? (u128)1 << (bits - 1) : ((u128)1 << (bits - 1)) - 1);
    if (mag > limit) { *fl |= FL_NV; return sat_result(x.sign, bits, uns); }
    if (inexact) *fl |= FL_NX;
    u64 v = x.sign ? (u64)0 - (u64)mag : (u64)mag;
    return int_result((i64)v, bits);
}

/* ---- AArch64 hardware path ---- */
#if defined(__aarch64__)
#define FP_HW 1
static int hw_rm = -1;
static inline void hw_mode(int rm) {
    if (rm == hw_rm) return;
    static const u64 rmode[4] = {0, 3, 2, 1};      /* RNE, RTZ, RDN (RM), RUP (RP) */
    u64 c;
    __asm__ volatile("mrs %0, fpcr" : "=r"(c));
    /* RMode[23:22]; FZ (24), DN (25), AH (1), FIZ (0) cleared: IEEE subnormals, no default NaN. */
    c = (c & ~(u64)((3u << 22) | (1u << 24) | (1u << 25) | 3u)) | rmode[rm] << 22;
    __asm__ volatile("msr fpcr, %0" :: "r"(c));
    hw_rm = rm;
}
static inline void hw_clear(void) { __asm__ volatile("msr fpsr, xzr" ::: "memory"); }
static inline unsigned hw_flags(void) {
    u64 s;
    __asm__ volatile("mrs %0, fpsr" : "=r"(s) :: "memory");
    /* FPSR IOC 0, DZC 1, OFC 2, UFC 3, IXC 4 -> NV DZ OF UF NX */
    return (unsigned)(((s & 1) << 4) | ((s & 2) << 2) | (s & 4) | ((s & 8) >> 2) | ((s & 16) >> 4));
}
static inline double d_of(u64 v) { double d; memcpy(&d, &v, 8); return d; }
static inline u64 bits_d(double d) { u64 v; memcpy(&v, &d, 8); return v; }
static inline float s_of(u64 v) { u32 w = (u32)v; float f; memcpy(&f, &w, 4); return f; }
static inline u64 bits_s(float f) { u32 w; memcpy(&w, &f, 4); return w; }

#define HW2(insn, R) __asm__ volatile(insn " %" R "0, %" R "1, %" R "2" : "=w"(r) : "w"(x), "w"(y))
static u64 hw_arith(int op, int dbl, u64 a, u64 b, u64 c, int rm, unsigned *fl, int *redo) {
    hw_mode(rm);
    u64 out;
    hw_clear();
    if (dbl) {
        double x = d_of(a), y = d_of(b), z = d_of(c), r;
        switch (op) {
        case OP_ADD: HW2("fadd", "d"); break;
        case OP_SUB: HW2("fsub", "d"); break;
        case OP_MUL: HW2("fmul", "d"); break;
        case OP_DIV: HW2("fdiv", "d"); break;
        case OP_SQRT: __asm__ volatile("fsqrt %d0, %d1" : "=w"(r) : "w"(x)); break;
        default: __asm__ volatile("fmadd %d0, %d1, %d2, %d3" : "=w"(r) : "w"(x), "w"(y), "w"(z)); break;
        }
        out = bits_d(r);
    } else {
        float x = s_of(a), y = s_of(b), z = s_of(c), r;
        switch (op) {
        case OP_ADD: HW2("fadd", "s"); break;
        case OP_SUB: HW2("fsub", "s"); break;
        case OP_MUL: HW2("fmul", "s"); break;
        case OP_DIV: HW2("fdiv", "s"); break;
        case OP_SQRT: __asm__ volatile("fsqrt %s0, %s1" : "=w"(r) : "w"(x)); break;
        default: __asm__ volatile("fmadd %s0, %s1, %s2, %s3" : "=w"(r) : "w"(x), "w"(y), "w"(z)); break;
        }
        out = bits_s(r);
    }
    unsigned st = hw_flags();
    const fmt_t *f = dbl ? &FMT_D : &FMT_S;
    if (is_nan_bits(out, f)) out = f->qnan;
    if ((st & FL_UF) && (out & ~f->sbit) == f->minnorm) { *redo = 1; return 0; }   /* tininess rule */
    *fl |= st;
    return out;
}
#endif

static u64 fp_arith(int op, const fmt_t *f, u64 a, u64 b, u64 c, int rm, int np, int nc, unsigned *fl) {
#ifdef FP_HW
    if (!fp_soft && rm != RM_RMM) {
        int redo = 0;
        u64 x = a, z = c;
        if (op == OP_FMA) { x ^= np ? f->sbit : 0; z ^= nc ? f->sbit : 0; }
        u64 r = hw_arith(op, f == &FMT_D, x, b, z, rm, fl, &redo);
        if (!redo) return r;
    }
#endif
    switch (op) {
    case OP_ADD: return soft_add(a, b, f, rm, 0, fl);
    case OP_SUB: return soft_add(a, b, f, rm, 1, fl);
    case OP_MUL: return soft_mul(a, b, f, rm, fl);
    case OP_DIV: return soft_div(a, b, f, rm, fl);
    case OP_SQRT: return soft_sqrt(a, f, rm, fl);
    default: return soft_fma(a, b, c, f, rm, np, nc, fl);
    }
}

static u64 fp_cvt_ff(u64 a, const fmt_t *src, const fmt_t *dst, int rm, unsigned *fl) {
#ifdef FP_HW
    if (!fp_soft && rm != RM_RMM) {
        hw_mode(rm);
        u64 out;
        hw_clear();
        if (dst == &FMT_S) {
            float r; double x = d_of(a);
            __asm__ volatile("fcvt %s0, %d1" : "=w"(r) : "w"(x));
            out = bits_s(r);
        } else {
            double r; float x = s_of(a);
            __asm__ volatile("fcvt %d0, %s1" : "=w"(r) : "w"(x));
            out = bits_d(r);
        }
        unsigned st = hw_flags();
        if (is_nan_bits(out, dst)) out = dst->qnan;
        if (!((st & FL_UF) && (out & ~dst->sbit) == dst->minnorm)) { *fl |= st; return out; }
    }
#endif
    return soft_cvt_ff(a, src, dst, rm, fl);
}

/* rs2 selects W (0), WU (1), L (2), LU (3); the source is the 64-bit x register. */
static u64 fp_int2f(u64 xa, int kind, const fmt_t *f, int rm, unsigned *fl) {
#ifdef FP_HW
    if (!fp_soft && rm != RM_RMM) {
        hw_mode(rm);
        u64 out;
        u32 w = (u32)xa;
        hw_clear();
        if (f == &FMT_D) {
            double r;
            switch (kind) {
            case 0: __asm__ volatile("scvtf %d0, %w1" : "=w"(r) : "r"(w)); break;
            case 1: __asm__ volatile("ucvtf %d0, %w1" : "=w"(r) : "r"(w)); break;
            case 2: __asm__ volatile("scvtf %d0, %x1" : "=w"(r) : "r"(xa)); break;
            default: __asm__ volatile("ucvtf %d0, %x1" : "=w"(r) : "r"(xa)); break;
            }
            out = bits_d(r);
        } else {
            float r;
            switch (kind) {
            case 0: __asm__ volatile("scvtf %s0, %w1" : "=w"(r) : "r"(w)); break;
            case 1: __asm__ volatile("ucvtf %s0, %w1" : "=w"(r) : "r"(w)); break;
            case 2: __asm__ volatile("scvtf %s0, %x1" : "=w"(r) : "r"(xa)); break;
            default: __asm__ volatile("ucvtf %s0, %x1" : "=w"(r) : "r"(xa)); break;
            }
            out = bits_s(r);
        }
        *fl |= hw_flags();
        return out;
    }
#endif
    int neg = 0;
    u64 mag;
    switch (kind) {
    case 0: { i64 v = (int32_t)(u32)xa; neg = v < 0; mag = neg ? (u64)0 - (u64)v : (u64)v; break; }
    case 1: mag = (u32)xa; break;
    case 2: neg = (i64)xa < 0; mag = neg ? (u64)0 - xa : xa; break;
    default: mag = xa; break;
    }
    return soft_int2f(neg, mag, f, rm, fl);
}

#ifdef FP_HW
/* AArch64 FCVT{N,Z,M,P,A}{S,U}: rounding in the opcode, saturation and IOC/IXC as RISC-V, except NaN. */
#define CVTI(mn, rd, fr) __asm__ volatile(mn " %" rd "0, %" fr "1" : "=r"(out) : "w"(x))
#define CVTI_ALL(fr) do { \
    switch (rm * 4 + kind) { \
    case 0: CVTI("fcvtns", "w", fr); break;  case 1: CVTI("fcvtnu", "w", fr); break; \
    case 2: CVTI("fcvtns", "x", fr); break;  case 3: CVTI("fcvtnu", "x", fr); break; \
    case 4: CVTI("fcvtzs", "w", fr); break;  case 5: CVTI("fcvtzu", "w", fr); break; \
    case 6: CVTI("fcvtzs", "x", fr); break;  case 7: CVTI("fcvtzu", "x", fr); break; \
    case 8: CVTI("fcvtms", "w", fr); break;  case 9: CVTI("fcvtmu", "w", fr); break; \
    case 10: CVTI("fcvtms", "x", fr); break; case 11: CVTI("fcvtmu", "x", fr); break; \
    case 12: CVTI("fcvtps", "w", fr); break; case 13: CVTI("fcvtpu", "w", fr); break; \
    case 14: CVTI("fcvtps", "x", fr); break; case 15: CVTI("fcvtpu", "x", fr); break; \
    case 16: CVTI("fcvtas", "w", fr); break; case 17: CVTI("fcvtau", "w", fr); break; \
    case 18: CVTI("fcvtas", "x", fr); break; default: CVTI("fcvtau", "x", fr); break; \
    } } while (0)
#endif

static u64 fp_f2int(u64 a, const fmt_t *f, int kind, int rm, unsigned *fl) {
    int bits = kind < 2 ? 32 : 64, uns = kind & 1;
#ifdef FP_HW
    if (!fp_soft) {
        if (is_nan_bits(a, f)) { *fl |= FL_NV; return sat_result(0, bits, uns); }
        u64 out = 0;
        /* The rounding is in the opcode, but FPCR must still be ours (FZ, AH, FIZ and DN cleared): set it up
         * if no other hardware path has yet (Codex review of 0.17.0: a host left with FZ = 1 flushed a
         * subnormal input to 0 here). */
        if (hw_rm < 0) hw_mode(RM_RNE);
        hw_clear();
        if (f == &FMT_D) { double x = d_of(a); CVTI_ALL("d"); }
        else { float x = s_of(a); CVTI_ALL("s"); }
        unsigned st = hw_flags() & (FL_NV | FL_NX);
        *fl |= (st & FL_NV) ? FL_NV : st;          /* RISC-V: an invalid conversion is not also inexact */
        return int_result((i64)out, bits);
    }
#endif
    return soft_f2int(a, f, rm, bits, uns, fl);
}

/* FMIN/FMAX (minimumNumber/maximumNumber), compares and classify: bit logic. */
static int fp_lt(u64 a, u64 b, const fmt_t *f) {   /* a < b for non-NaN values; -0 == +0 */
    int sa = (a & f->sbit) != 0, sb = (b & f->sbit) != 0;
    u64 ma = a & ~f->sbit, mb = b & ~f->sbit;
    if (!ma && !mb) return 0;
    if (sa != sb) return sa;
    return sa ? ma > mb : ma < mb;
}

static u64 fp_minmax(u64 a, u64 b, const fmt_t *f, int is_max, unsigned *fl) {
    int na = is_nan_bits(a, f), nb = is_nan_bits(b, f);
    if (is_snan_bits(a, f) || is_snan_bits(b, f)) *fl |= FL_NV;
    if (na && nb) return f->qnan;
    if (na) return b;
    if (nb) return a;
    int lt = fp_lt(a, b, f) || ((a & f->sbit) && !(b & f->sbit) && !(a & ~f->sbit) && !(b & ~f->sbit));
    return is_max ? (lt ? b : a) : (lt ? a : b);
}

static u64 fp_cmp(u64 a, u64 b, const fmt_t *f, int f3, unsigned *fl) {   /* 0 FLE, 1 FLT, 2 FEQ */
    if (is_nan_bits(a, f) || is_nan_bits(b, f)) {
        if (f3 != 2 || is_snan_bits(a, f) || is_snan_bits(b, f)) *fl |= FL_NV;
        return 0;
    }
    int eq = a == b || (!(a & ~f->sbit) && !(b & ~f->sbit));
    if (f3 == 2) return (u64)eq;
    if (f3 == 1) return (u64)fp_lt(a, b, f);
    return (u64)(eq || fp_lt(a, b, f));
}

static u64 fp_class(u64 a, const fmt_t *f) {
    int sign = (a & f->sbit) != 0;
    u64 mag = a & ~f->sbit;
    if (mag > f->infb) return is_snan_bits(a, f) ? 1u << 8 : 1u << 9;
    if (mag == f->infb) return sign ? 1u : 1u << 7;
    if (mag == 0) return sign ? 1u << 3 : 1u << 4;
    int normal = mag >= f->minnorm;
    if (sign) return normal ? 1u << 1 : 1u << 2;
    return normal ? 1u << 6 : 1u << 5;
}

#define BOX 0xffffffff00000000ull
static inline u64 read_s(u64 r) { return (r >> 32) == 0xffffffffu ? (r & 0xffffffffu) : FMT_S.qnan; }

/* One OP-FP or FMA instruction. Returns -1 if illegal, 0 for an x destination, 1 for an f destination;
 * *val gets the 64-bit result, *fl the raised flags. */
static __attribute__((noinline)) int fp_exec(u32 ins, u64 xa, u64 fa, u64 fb, u64 fc, unsigned frm, u64 *val, unsigned *fl) {
    u32 op = ins & 127, f3 = (ins >> 12) & 7, rs2 = (ins >> 20) & 31, fmt = (ins >> 25) & 3, f5 = ins >> 27;
    if (fmt > 1) return -1;
    const fmt_t *f = fmt ? &FMT_D : &FMT_S;
    int dbl = fmt == 1;
    int rm = f3 == 7 ? (int)frm : (int)f3, rm_ok = rm <= 4;
    u64 a = dbl ? fa : read_s(fa), b = dbl ? fb : read_s(fb), c = dbl ? fc : read_s(fc);
    u64 box = dbl ? 0 : BOX;
    *fl = 0;
    if (op == 0x43 || op == 0x47 || op == 0x4b || op == 0x4f) {
        if (!rm_ok) return -1;
        *val = fp_arith(OP_FMA, f, a, b, c, rm, op >= 0x4b, op == 0x47 || op == 0x4f, fl) | box;
        return 1;
    }
    if (op != 0x53) return -1;
    switch (f5) {
    case 0x00: case 0x01: case 0x02: case 0x03:
        if (!rm_ok) return -1;
        *val = fp_arith((int)f5, f, a, b, 0, rm, 0, 0, fl) | box;
        return 1;
    case 0x0b:
        if (rs2 || !rm_ok) return -1;
        *val = fp_arith(OP_SQRT, f, a, 0, 0, rm, 0, 0, fl) | box;
        return 1;
    case 0x04: {
        if (f3 > 2) return -1;
        u64 sb = b & f->sbit, sa = a & f->sbit;
        u64 s = f3 == 0 ? sb : f3 == 1 ? sb ^ f->sbit : sa ^ sb;
        *val = ((a & ~f->sbit) | s) | box;
        return 1;
    }
    case 0x05:
        if (f3 > 1) return -1;
        *val = fp_minmax(a, b, f, f3 == 1, fl) | box;
        return 1;
    case 0x08:
        if (!rm_ok) return -1;
        if (!dbl && rs2 == 1) { *val = fp_cvt_ff(fa, &FMT_D, &FMT_S, rm, fl) | BOX; return 1; }
        if (dbl && rs2 == 0) { *val = fp_cvt_ff(read_s(fa), &FMT_S, &FMT_D, rm, fl); return 1; }
        return -1;
    case 0x14:
        if (f3 > 2) return -1;
        *val = fp_cmp(a, b, f, (int)f3, fl);
        return 0;
    case 0x1c:
        if (rs2) return -1;
        if (f3 == 1) { *val = fp_class(a, f); return 0; }
        if (f3 == 0) { *val = dbl ? fa : (u64)(i64)(int32_t)(u32)fa; return 0; }
        return -1;
    case 0x1e:
        if (rs2 || f3) return -1;
        *val = dbl ? xa : ((xa & 0xffffffffu) | BOX);
        return 1;
    case 0x18:
        if (rs2 > 3 || !rm_ok) return -1;
        *val = fp_f2int(a, f, (int)rs2, rm, fl);
        return 0;
    case 0x1a:
        if (rs2 > 3 || !rm_ok) return -1;
        *val = fp_int2f(xa, (int)rs2, f, rm, fl) | box;
        return 1;
    default:
        return -1;
    }
}


#define MAX_MARKS 64
static u64 mark_value[MAX_MARKS], mark_index[MAX_MARKS];
static int nmarks;
static u64 mbox_words[32];
static u32 mbox_seen;

static void die(const char *msg) {
    fprintf(stderr, "rv_iss: %s\n", msg);
    exit(2);
}

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + 1e-9 * (double)t.tv_nsec;
}

static void write_state(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot write state");
    u64 head[3] = {0, count, pc};
    memcpy(&head[0], fp_on ? "RVISSST2" : "RVISSST1", 8);
    fwrite(head, 8, 3, f);
    fwrite(regs, 8, 32, f);
    if (fp_on) {
        u64 c = fcsr;
        fwrite(fregs, 8, 32, f);
        fwrite(&c, 8, 1, f);
    }
    fwrite(&ram, 8, 1, f);
    if (fwrite(mem, 1, ram, f) != ram || fclose(f)) die("state write failed");
}

static void read_state(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot read state");
    u64 head[3], bytes = 0;
    if (fread(head, 8, 3, f) != 3) die("not a state file");
    int st2 = !memcmp(&head[0], "RVISSST2", 8);
    if (!st2 && memcmp(&head[0], "RVISSST1", 8)) die("not a state file");
    if (st2 && !fp_on) die("RVISSST2 state needs --fp 1");
    count = head[1];
    pc = head[2];
    if (fread(regs, 8, 32, f) != 32) die("short state file");
    if (st2) {
        u64 c = 0;
        if (fread(fregs, 8, 32, f) != 32 || fread(&c, 8, 1, f) != 1) die("short state file");
        fcsr = (u32)c & 0xff;
    }
    if (fread(&bytes, 8, 1, f) != 1) die("short state file");
    if (bytes != ram) die("state memory size differs from --ram");
    if (fread(mem, 1, ram, f) != ram) die("short state file");
    fclose(f);
    regs[0] = 0;
}

static inline int tracing(void) { return trace_fd && count >= trace_from && count < trace_to; }

static inline i64 sx(u64 v, int bits) { return (i64)(v << (64 - bits)) >> (64 - bits); }

static int stop_cause = -1;
static u64 stop_tval;

#define TRAP(c, t) do { stop_cause = (c); stop_tval = (t); return 0; } while (0)

static inline u64 rot64(u64 x, unsigned n) { n &= 63; return n ? (x << n) | (x >> (64 - n)) : x; }
static inline u32 rot32(u32 x, unsigned n) { n &= 31; return n ? (x << n) | (x >> (32 - n)) : x; }

static u64 mulhu64(u64 a, u64 b) { return (u64)(((unsigned __int128)a * b) >> 64); }
static u64 mulh64(u64 a, u64 b) { return (u64)(((__int128)(i64)a * (__int128)(i64)b) >> 64); }
static u64 mulhsu64(u64 a, u64 b) { return (u64)(((__int128)(i64)a * (__int128)(unsigned __int128)b) >> 64); }

/* M-extension division, per the unprivileged specification. */
static u64 divide(int f3, int word, u64 a, u64 b) {
    int sign = f3 == 4 || f3 == 6, rem = f3 >= 6;
    if (word) {
        if (sign) {
            int32_t x = (int32_t)a, y = (int32_t)b, q, r;
            if (y == 0) { q = -1; r = x; }
            else if (x == INT32_MIN && y == -1) { q = x; r = 0; }
            else { q = x / y; r = x % y; }
            return (u64)(i64)(rem ? r : q);
        }
        u32 x = (u32)a, y = (u32)b, q, r;
        if (y == 0) { q = 0xffffffffu; r = x; } else { q = x / y; r = x % y; }
        return (u64)(i64)(int32_t)(rem ? r : q);
    }
    if (sign) {
        i64 x = (i64)a, y = (i64)b, q, r;
        if (y == 0) { q = -1; r = x; }
        else if (x == INT64_MIN && y == -1) { q = x; r = 0; }
        else { q = x / y; r = x % y; }
        return (u64)(rem ? r : q);
    }
    u64 q, r;
    if (b == 0) { q = ~(u64)0; r = a; } else { q = a / b; r = a % b; }
    return rem ? r : q;
}

/* Zba/Zbb/Zbs: returns 1 and sets *v when ins is one of them (as reference.bitmanip_op). */
static int bitmanip(u32 ins, u64 a, u64 b, u64 *v) {
    u32 op = ins & 127, f3 = (ins >> 12) & 7, f7 = ins >> 25, f6 = ins >> 26, f12 = ins >> 20;
    u32 rs2 = (ins >> 20) & 31, sh6 = (ins >> 20) & 63, sh5 = (ins >> 20) & 31;
    u64 a32 = a & 0xffffffffu;
    if (op == 0x33) {
        if (f7 == 0x10 && (f3 == 2 || f3 == 4 || f3 == 6)) { *v = (a << (f3 / 2)) + b; return 1; }
        if (f7 == 0x20 && f3 == 7) { *v = a & ~b; return 1; }
        if (f7 == 0x20 && f3 == 6) { *v = a | ~b; return 1; }
        if (f7 == 0x20 && f3 == 4) { *v = ~(a ^ b); return 1; }
        if (f7 == 0x05) {
            switch (f3) {
            case 4: *v = (i64)a < (i64)b ? a : b; return 1;
            case 5: *v = a < b ? a : b; return 1;
            case 6: *v = (i64)a > (i64)b ? a : b; return 1;
            case 7: *v = a > b ? a : b; return 1;
            default: return 0;
            }
        }
        if (f7 == 0x30 && f3 == 1) { *v = rot64(a, b & 63); return 1; }
        if (f7 == 0x30 && f3 == 5) { *v = rot64(a, (64 - (b & 63)) & 63); return 1; }
        if (f7 == 0x24 && f3 == 1) { *v = a & ~((u64)1 << (b & 63)); return 1; }
        if (f7 == 0x24 && f3 == 5) { *v = (a >> (b & 63)) & 1; return 1; }
        if (f7 == 0x34 && f3 == 1) { *v = a ^ ((u64)1 << (b & 63)); return 1; }
        if (f7 == 0x14 && f3 == 1) { *v = a | ((u64)1 << (b & 63)); return 1; }
        return 0;
    }
    if (op == 0x3b) {
        if (f7 == 0x04 && f3 == 0) { *v = a32 + b; return 1; }
        if (f7 == 0x04 && f3 == 4 && rs2 == 0) { *v = a & 0xffff; return 1; }
        if (f7 == 0x10 && (f3 == 2 || f3 == 4 || f3 == 6)) { *v = (a32 << (f3 / 2)) + b; return 1; }
        if (f7 == 0x30 && f3 == 1) { *v = (u64)sx(rot32((u32)a32, b & 31), 32); return 1; }
        if (f7 == 0x30 && f3 == 5) { *v = (u64)sx(rot32((u32)a32, (32 - (b & 31)) & 31), 32); return 1; }
        return 0;
    }
    if (op == 0x13) {
        if (f3 == 1 && f12 == 0x600) { *v = a ? (u64)__builtin_clzll(a) : 64; return 1; }
        if (f3 == 1 && f12 == 0x601) { *v = a ? (u64)__builtin_ctzll(a) : 64; return 1; }
        if (f3 == 1 && f12 == 0x602) { *v = (u64)__builtin_popcountll(a); return 1; }
        if (f3 == 1 && f12 == 0x604) { *v = (u64)sx(a, 8); return 1; }
        if (f3 == 1 && f12 == 0x605) { *v = (u64)sx(a, 16); return 1; }
        if (f3 == 5 && f6 == 0x18) { *v = rot64(a, (64 - sh6) & 63); return 1; }
        if (f3 == 5 && f12 == 0x287) {
            u64 r = 0;
            for (int i = 0; i < 8; i++) if ((a >> (8 * i)) & 0xff) r |= (u64)0xff << (8 * i);
            *v = r;
            return 1;
        }
        if (f3 == 5 && f12 == 0x6b8) { *v = __builtin_bswap64(a); return 1; }
        if (f3 == 1 && f6 == 0x12) { *v = a & ~((u64)1 << sh6); return 1; }
        if (f3 == 5 && f6 == 0x12) { *v = (a >> sh6) & 1; return 1; }
        if (f3 == 1 && f6 == 0x1a) { *v = a ^ ((u64)1 << sh6); return 1; }
        if (f3 == 1 && f6 == 0x0a) { *v = a | ((u64)1 << sh6); return 1; }
        return 0;
    }
    if (op == 0x1b) {
        if (f3 == 1 && f6 == 0x02) { *v = a32 << sh6; return 1; }
        if (f3 == 1 && f12 == 0x600) { *v = a32 ? (u64)__builtin_clz((u32)a32) : 32; return 1; }
        if (f3 == 1 && f12 == 0x601) { *v = a32 ? (u64)__builtin_ctz((u32)a32) : 32; return 1; }
        if (f3 == 1 && f12 == 0x602) { *v = (u64)__builtin_popcount((u32)a32); return 1; }
        if (f3 == 5 && f7 == 0x30) { *v = (u64)sx(rot32((u32)a32, (32 - sh5) & 31), 32); return 1; }
        return 0;
    }
    return 0;
}

static inline void note_store(u64 address, u64 b, int size) {
    u64 aligned = address & ~(u64)7;
    int lane = (int)(address & 7);
    u64 data = b << (8 * lane); /* unmasked, like reference.py's W line */
    unsigned mask = ((1u << size) - 1) << lane;
    if (tracing()) fprintf(trace_fd, "W %016" PRIx64 " %016" PRIx64 " %02x\n", aligned, data, mask);
    if (aligned == mailbox) {
        if (nmarks < MAX_MARKS) { mark_value[nmarks] = data; mark_index[nmarks] = count; }
        nmarks++;
    } else if (aligned > mailbox && aligned < mailbox + 256 && mask == 0xff) {
        mbox_words[(aligned - mailbox) / 8] = data;
        mbox_seen |= 1u << ((aligned - mailbox) / 8);
    }
}

/* ---- Functional cache warming (--warm-caches): an approximate model of the out-of-order
 * core's L1s (I: direct-mapped 8-byte beats; D: 2-way 8-byte lines, fill into the way the
 * core picks, write-through without allocation) feeding the SoC's tags-only L2 (LRU by a
 * use counter; reads that miss the L1s and every store touch it, as in the SoC). Correct-path
 * accesses only: the core's wrong-path fetches and loads are not modelled. At each --dump-at
 * index the L2 tags are written to <prefix><index>.l2 for tb_bench's +l2_preload. */
static int warm;
static u64 ic_n, dc_sets, l2_lines, l2_sets, l2_ways, l2_off, l2_clock;
static u64 *ic_tag, *dc_tag, *l2_tag, *l2_use;
static uint8_t *ic_valid, *dc_valid, *dc_last, *l2_valid;

static void warm_init(const char *spec) {
    u64 ib, db, kib, line;
    if (sscanf(spec, "%" SCNu64 ",%" SCNu64 ",%" SCNu64 ",%" SCNu64 ",%" SCNu64, &ib, &db, &kib, &l2_ways, &line) != 5)
        die("--warm-caches IBEATS,DBEATS,L2_KIB,L2_WAYS,L2_LINE");
    ic_n = ib; dc_sets = db / 2; l2_lines = kib * 1024 / line; l2_sets = l2_lines / l2_ways;
    for (l2_off = 0; ((u64)1 << l2_off) < line; l2_off++) {}
    ic_tag = calloc(ic_n, 8); ic_valid = calloc(ic_n, 1);
    dc_tag = calloc(2 * dc_sets, 8); dc_valid = calloc(2 * dc_sets, 1); dc_last = calloc(dc_sets, 1);
    l2_tag = calloc(l2_lines, 8); l2_use = calloc(l2_lines, 8); l2_valid = calloc(l2_lines, 1);
    if (!ic_tag || !dc_tag || !l2_tag || !l2_use || !l2_valid || !dc_last || !l2_sets) die("cache model");
    warm = 1;
}

static void l2_touch(u64 a) {
    u64 line = a >> l2_off, base = (line % l2_sets) * l2_ways, v = ~(u64)0;
    l2_clock++;
    for (u64 w = 0; w < l2_ways; w++)
        if (l2_valid[base + w] && l2_tag[base + w] == line) { l2_use[base + w] = l2_clock; return; }
    for (u64 w = 0; w < l2_ways; w++) if (v == ~(u64)0 && !l2_valid[base + w]) v = w;
    if (v == ~(u64)0) {
        v = 0;
        for (u64 w = 1; w < l2_ways; w++) if (l2_use[base + w] < l2_use[base + v]) v = w;
    }
    l2_valid[base + v] = 1; l2_tag[base + v] = line; l2_use[base + v] = l2_clock;
}

static inline void warm_fetch(u64 a) {
    u64 beat = a >> 3, i = beat % ic_n;
    if (ic_valid[i] && ic_tag[i] == beat) return;
    ic_valid[i] = 1; ic_tag[i] = beat;
    l2_touch(a);
}

static inline void warm_load(u64 a) {
    u64 beat = a >> 3, set = beat % dc_sets;
    if ((dc_valid[set] && dc_tag[set] == beat) || (dc_valid[dc_sets + set] && dc_tag[dc_sets + set] == beat)) return;
    u64 l = set;
    if (dc_valid[l] && (!dc_valid[dc_sets + set] || !dc_last[set])) l = dc_sets + set;
    dc_valid[l] = 1; dc_tag[l] = beat; dc_last[set] = l >= dc_sets;
    l2_touch(a);
}

static void write_l2(const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) die("cannot write L2 state");
    /* One line per L2 entry (way-major within a set, as the SoC's arrays): valid tag use (hex). */
    for (u64 i = 0; i < l2_lines; i++)
        fprintf(f, "%x %016" PRIx64 " %016" PRIx64 "\n", l2_valid[i], l2_tag[i], l2_use[i]);
    fprintf(f, "%x %016" PRIx64 " %016" PRIx64 "\n", 2u, l2_clock, (u64)0); /* trailer: the use clock */
    if (fclose(f)) die("L2 state write failed");
}

/* F/D instructions and the FP CSRs (kept out of step() so the integer path is unchanged):
 * returns 1 when executed (fp_value, fp_dest set), 0 when illegal, -1 when it trapped (stop_cause set). */
static u64 fp_value;     /* fp_step's results (globals, so step()'s locals stay in registers) */
static u32 fp_dest;
static __attribute__((noinline)) int fp_step(u32 ins, u64 a) {
    u32 op = ins & 127, rd = (ins >> 7) & 31, f3 = (ins >> 12) & 7, rs1 = (ins >> 15) & 31, rs2 = (ins >> 20) & 31;
    i64 imm = (i64)(int32_t)ins >> 20;
    u64 value = 0;
    u32 dest = 0;
    int ok = 0;
#undef TRAP
#define TRAP(c, t) do { stop_cause = (c); stop_tval = (t); return -1; } while (0)
    if (op == 0x73) {
        if ((f3 & 3) && (ins >> 20) >= 1 && (ins >> 20) <= 3) {
            /* Zicsr on fflags (0x001), frm (0x002) and fcsr (0x003) only. */
            u32 csr = ins >> 20, kind = f3 & 3;
            u64 old = csr == 1 ? (fcsr & 0x1f) : csr == 2 ? (fcsr >> 5) : fcsr;
            u64 src = f3 >= 5 ? rs1 : a, nv = kind == 1 ? src : kind == 2 ? (old | src) : (old & ~src);
            if (kind == 1 || rs1 != 0) {
                if (csr == 1) fcsr = (fcsr & 0xe0) | (u32)(nv & 0x1f);
                else if (csr == 2) fcsr = (fcsr & 0x1f) | (u32)(nv & 7) << 5;
                else fcsr = (u32)nv & 0xff;
                if (tracing()) fprintf(trace_fd, "C 003 %016" PRIx64 "\n", (u64)fcsr);
            }
            value = old; dest = rd; ok = 1;
        }
    } else if (op == 0x07 || op == 0x27) {
        if (f3 == 2 || f3 == 3) {
            int load = op == 0x07, size = f3 == 2 ? 4 : 8;
            i64 off = load ? imm : sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12);
            u64 address = a + (u64)off;
            if (address & (u64)(size - 1)) TRAP(load ? 4 : 6, address);
            if ((address & ~(u64)7) >= ram) TRAP(load ? 5 : 7, address);
            if (load) {
                u64 v = 0;
                memcpy(&v, mem + address, (size_t)size);
                if (warm) warm_load(address);
                value = size == 4 ? v | BOX : v; dest = 32 + rd;
            } else {
                u64 data = size == 4 ? fregs[rs2] & 0xffffffffu : fregs[rs2];
                memcpy(mem + address, &data, (size_t)size);
                note_store(address, data, size);
                if (warm) l2_touch(address);
            }
            ok = 1;
        }
    } else {
        unsigned fl;
        int k = fp_exec(ins, a, fregs[rs1], fregs[rs2], fregs[ins >> 27], fcsr >> 5, &value, &fl);
        if (k >= 0) {
            dest = k ? 32 + rd : rd; ok = 1;
            if (fl) {
                fcsr |= fl;
                if (tracing()) fprintf(trace_fd, "F %02x\n", fl);
            }
        }
    }
#undef TRAP
#define TRAP(c, t) do { stop_cause = (c); stop_tval = (t); return 0; } while (0)
    fp_value = value;
    fp_dest = dest;
    return ok;
}

/* One instruction; returns 0 when the run stops (stop_cause set). */
static inline int step(void) {
    if (pc & 3) TRAP(0, pc);
    if ((pc & ~(u64)7) >= ram) TRAP(1, pc);
    u32 ins;
    memcpy(&ins, mem + pc, 4);
    if (warm) warm_fetch(pc);
    u32 op = ins & 127, rd = (ins >> 7) & 31, f3 = (ins >> 12) & 7, rs1 = (ins >> 15) & 31, rs2 = (ins >> 20) & 31;
    u32 f7 = ins >> 25;
    u64 a = regs[rs1], b = regs[rs2];
    i64 imm = (i64)(int32_t)ins >> 20;
    u64 nxt = pc + 4, value = 0;
    u32 dest = 0;
    int ok = 0;
    switch (op) {
    case 0x37: value = (u64)(i64)(int32_t)(ins & 0xfffff000u); dest = rd; ok = 1; break;
    case 0x17: value = (u64)(i64)(int32_t)(ins & 0xfffff000u) + pc; dest = rd; ok = 1; break;
    case 0x6f: {
        u64 d = ((u64)(ins >> 31) << 20) | (((ins >> 12) & 255) << 12) | (((ins >> 20) & 1) << 11) | (((ins >> 21) & 1023) << 1);
        nxt = pc + (u64)sx(d, 21);
        value = pc + 4; dest = rd; ok = 1;
        break;
    }
    case 0x67:
        if (f3 == 0) { nxt = (a + (u64)imm) & ~(u64)1; value = pc + 4; dest = rd; ok = 1; }
        break;
    case 0x63: {
        int t;
        switch (f3) {
        case 0: t = a == b; break;
        case 1: t = a != b; break;
        case 4: t = (i64)a < (i64)b; break;
        case 5: t = (i64)a >= (i64)b; break;
        case 6: t = a < b; break;
        case 7: t = a >= b; break;
        default: t = -1;
        }
        if (t >= 0) {
            ok = 1;
            if (t) {
                u64 d = ((u64)(ins >> 31) << 12) | (((ins >> 7) & 1) << 11) | (((ins >> 25) & 63) << 5) | (((ins >> 8) & 15) << 1);
                nxt = pc + (u64)sx(d, 13);
            }
        }
        break;
    }
    case 0x03: case 0x23: {
        int load = op == 0x03;
        if ((load && f3 != 7) || (!load && f3 < 4)) {
            int size = 1 << (f3 & 3);
            i64 off = load ? imm : sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12);
            u64 address = a + (u64)off;
            if (address & (u64)(size - 1)) TRAP(load ? 4 : 6, address);
            if ((address & ~(u64)7) >= ram) TRAP(load ? 5 : 7, address);
            if (load) {
                u64 v = 0;
                memcpy(&v, mem + address, (size_t)size);
                if (warm) warm_load(address);
                if (f3 < 4 && size < 8) v = (u64)sx(v, 8 * size);
                value = v; dest = rd;
            } else {
                memcpy(mem + address, &b, (size_t)size);
                note_store(address, b, size);
                if (warm) l2_touch(address);
            }
            ok = 1;
        }
        break;
    }
    case 0x0f: if (f3 == 0 || f3 == 1) ok = 1; break;
    case 0x73:
        if (ins == 0x73) TRAP(11, 0);
        if (ins == 0x100073) TRAP(3, 0);
        if (fp_on) { int r = fp_step(ins, a); if (r < 0) return 0; ok = r; value = fp_value; dest = fp_dest; }
        break;
    case 0x13: case 0x1b: case 0x33: case 0x3b: {
        int word = op == 0x1b || op == 0x3b;
        if ((op == 0x33 || op == 0x3b) && f7 == 1) {
            if (!word || f3 == 0 || f3 >= 4) {
                if (f3 < 4) {
                    if (word) value = (u64)(i64)(int32_t)(u32)(a * b);
                    else if (f3 == 0) value = a * b;
                    else if (f3 == 1) value = mulh64(a, b);
                    else if (f3 == 2) value = mulhsu64(a, b);
                    else value = mulhu64(a, b);
                } else value = divide((int)f3, word, a, b);
                dest = rd; ok = 1;
            }
            break;
        }
        if (bitmanip(ins, a, b, &value)) { dest = rd; ok = 1; break; }
        int immediate = op == 0x13 || op == 0x1b;
        int width = word ? 32 : 64;
        u64 rhs = immediate ? (u64)imm : b;
        unsigned shift = (unsigned)(rhs & (u64)(width - 1));
        int subtract = !immediate && f7 == 32;
        int arith = (ins >> 30) & 1;
        int valid = 1;
        if (immediate) {
            if (f3 == 1 || f3 == 5) {
                u32 top = ins >> (word ? 25 : 26);
                valid = top == 0 || (f3 == 5 && top == (word ? 32u : 16u));
            }
        } else valid = f7 == 0 || (f7 == 32 && (f3 == 0 || f3 == 5));
        if (word && f3 != 0 && f3 != 1 && f3 != 5) valid = 0;
        if (!valid) break;
        switch (f3) {
        case 0: value = subtract ? a - rhs : a + rhs; break;
        case 1: value = a << shift; break;
        case 2: value = (i64)a < (i64)rhs; break;
        case 3: value = a < rhs; break;
        case 4: value = a ^ rhs; break;
        case 5:
            if (arith) value = word ? (u64)((i64)(int32_t)(u32)a >> shift) : (u64)((i64)a >> shift);
            else value = word ? (u64)((u32)a >> shift) : a >> shift;
            break;
        case 6: value = a | rhs; break;
        default: value = a & rhs;
        }
        if (word) value = (u64)(i64)(int32_t)(u32)value;
        dest = rd; ok = 1;
        break;
    }
    default:   /* LOAD-FP, STORE-FP, FMA and OP-FP: dispatched here, which keeps the integer path's speed */
        if (fp_on) { int r = fp_step(ins, a); if (r < 0) return 0; ok = r; value = fp_value; dest = fp_dest; }
        break;
    }
    if (!ok) TRAP(2, ins);
    if (nxt & 3) TRAP(0, nxt);
    if (dest) regs[dest] = value; else value = 0;
    if (tracing())
        fprintf(trace_fd, "R %016" PRIx64 " %08x %02x %016" PRIx64 " %016" PRIx64 "\n", pc, ins, dest, value, nxt);
    pc = nxt;
    count++;
    return 1;
}

static void parse_dumps(const char *list) {
    char *copy = strdup(list), *save = NULL;
    for (char *t = strtok_r(copy, ",", &save); t; t = strtok_r(NULL, ",", &save)) {
        dumps = realloc(dumps, (ndumps + 1) * sizeof *dumps);
        dumps[ndumps++] = strtoull(t, NULL, 0);
        if (ndumps > 1 && dumps[ndumps - 1] <= dumps[ndumps - 2]) die("--dump-at must be increasing");
    }
    free(copy);
}

#ifndef RV_ISS_NO_MAIN
/* ==== System mode (--sys 1): the lab-virt platform of cpu/PRIV-CONTRACT.md (draft) ======================
 * RV64GC (rv64imafdc_zicsr_zifencei_zicntr) with M, S and U modes, Sv39 with Svade (A/D faults), traps and
 * delegation, CLINT, ns16550a, PLIC, SiFive test finisher, a Spike-layout boot ROM, and HTIF tohost for the
 * riscv-tests. Kept apart from step() so that the user-mode path, its traces and its state files are
 * unchanged. Physical memory: DRAM of --ram bytes at 0x8000_0000 (mem[]), the boot ROM at 0x1000.
 * Two time models: "lab" (the contract: mtime = retired instructions / 100, interrupts checked before every
 * instruction, WFI fast-forwards to mtimecmp) and "spike" (Spike's scheduling, for commit-log comparison:
 * chunks of 5000 steps, a chunk ends at a trap or WFI, mtime += 50 and the LR reservation is dropped at each
 * chunk end, interrupts checked at chunk starts and after CSR instructions, MRET and SRET). */
#define DRAM_BASE 0x80000000ull
#define ROM_BASE 0x1000ull
#define CLINT_BASE 0x2000000ull
#define CLINT_SIZE 0xc000ull
#define PLIC_BASE 0xc000000ull
#define PLIC_SIZE 0x1000000ull
#define UART_BASE 0x10000000ull
#define UART_SIZE 0x1000ull
#define TEST_BASE 0x100000ull
#define TEST_SIZE 0x1000ull

#define MS_SIE (1ull << 1)
#define MS_MIE (1ull << 3)
#define MS_SPIE (1ull << 5)
#define MS_MPIE (1ull << 7)
#define MS_SPP (1ull << 8)
#define MS_MPP (3ull << 11)
#define MS_FS (3ull << 13)
#define MS_MPRV (1ull << 17)
#define MS_SUM (1ull << 18)
#define MS_MXR (1ull << 19)
#define MS_TVM (1ull << 20)
#define MS_TW (1ull << 21)
#define MS_TSR (1ull << 22)
#define MS_UXL (3ull << 32)
#define MS_SXL (3ull << 34)
#define MS_SD (1ull << 63)
#define SSTATUS_RMASK (MS_SIE | MS_SPIE | MS_SPP | MS_FS | MS_SUM | MS_MXR | MS_UXL | MS_SD | (1ull << 6))
#define SSTATUS_WMASK (MS_SIE | MS_SPIE | MS_SPP | MS_FS | MS_SUM | MS_MXR)
#define MSTATUS_WMASK (SSTATUS_WMASK | MS_MIE | MS_MPIE | MS_MPP | MS_MPRV | MS_TVM | MS_TW | MS_TSR)

#define IP_SSIP (1ull << 1)
#define IP_MSIP (1ull << 3)
#define IP_STIP (1ull << 5)
#define IP_MTIP (1ull << 7)
#define IP_SEIP (1ull << 9)
#define IP_MEIP (1ull << 11)
#define IP_S_MASK (IP_SSIP | IP_STIP | IP_SEIP)
#define IP_ALL (IP_S_MASK | IP_MSIP | IP_MTIP | IP_MEIP)
/* medeleg: every synchronous cause below 16 except misaligned fetch (not delegable with C, as Spike),
 * ecall from M (11) and the reserved 10 and 14. */
#define MEDELEG_MASK 0xb3feull

#define PTE_V 1u
#define PTE_R 2u
#define PTE_W 4u
#define PTE_X 8u
#define PTE_U 16u
#define PTE_G 32u
#define PTE_A 64u
#define PTE_D 128u

static int sys_on, time_spike;
static u64 marchid_val;
/* --adopt: the DUT-sourced mcycle values (N records of an RTL trace), consumed by mcycle reads in order */
static u64 *adopt_v;
static size_t adopt_n, adopt_i;
static const char *adopt_path;

static void adopt_load(const char *path) {
    FILE *f = fopen(path, "r");
    char line[256];
    size_t cap = 0;
    if (!f) die("cannot open --adopt file");
    while (fgets(line, sizeof line, f)) {
        unsigned csr;
        unsigned long long v;
        if (line[0] != 'N') continue;
        if (sscanf(line, "N %x %llx", &csr, &v) != 2 || csr != 0xb00) die("--adopt: bad N record");
        if (adopt_n == cap) {
            cap = cap ? 2 * cap : 64;
            adopt_v = realloc(adopt_v, cap * sizeof *adopt_v);
            if (!adopt_v) die("out of memory");
        }
        adopt_v[adopt_n++] = (u64)v;
    }
    fclose(f);
}
static int prv = 3;
static u64 mstatus, medeleg, mideleg, mie, mip_sw, mip_dev, mtvec, mepc, mcause, mtval, mscratch;
static u64 mcontext;
static u64 mcounteren, mcountinhibit, menvcfg, stvec, sepc, scause, stval, sscratch, satp, scounteren, senvcfg;
static u64 mcycle, minstret;
/* Counter writes win over the writing instruction's own increment (a flag skips that one increment).
 * Spike time model: the counters advance only when Spike's inner loop ends an iteration (after a CSR
 * instruction, MRET, SRET, WFI or a trap, and at a chunk end), by the instructions retired in it, unless
 * mcountinhibit as read at the iteration's start inhibits them; reads in between see the older value. */
static u64 mcycle_written, minstret_written, iter_n, iter_inh, csr_serialized;
static void counters_iter_end(void) {
    if (minstret_written) minstret_written = 0; else if (!(iter_inh & 4)) minstret += iter_n;
    if (mcycle_written) mcycle_written = 0; else if (!(iter_inh & 1)) mcycle += iter_n;
    iter_n = 0;
    iter_inh = mcountinhibit;
}
/* --isa and --priv (P0): the implemented subset. Default RV64GC (rv64imafdc_zicsr_zifencei_zicntr), M+S+U.
 * Without S there are no S CSRs, no delegation, no satp/SFENCE.VMA/SRET; without U, MPP is read-only M;
 * without C, IALIGN is 32 (a jump to a 2-byte boundary is cause 0 on the jump, mepc bits 1:0 read 0);
 * without A, F/D or the B extensions their encodings are cause 2. misa follows (B when Zba+Zbb+Zbs, as Spike). */
static int has_m = 1, has_a = 1, has_fd = 1, has_c = 1, has_b = 0, has_zicntr = 1, has_s = 1, has_u = 1;
static u64 misa_val = (2ull << 62) | (1u << 0) | (1u << 2) | (1u << 3) | (1u << 5) | (1u << 8) | (1u << 12) |
                      (1u << 18) | (1u << 20);  /* A C D F I M S U */
static void set_isa(const char *isa, const char *privs) {
    if (isa) {
        if (strncmp(isa, "rv64", 4)) die("--isa must start with rv64");
        const char *q = isa + 4;
        int zba = 0, zbb = 0, zbs = 0, f = 0, d = 0;
        has_m = has_a = has_fd = has_c = has_zicntr = 0;
        for (; *q && *q != '_'; q++) {
            switch (*q) {
            case 'i': break;
            case 'm': has_m = 1; break;
            case 'g': has_m = has_a = 1; f = d = 1; break;
            case 'a': has_a = 1; break;
            case 'f': f = 1; break;
            case 'd': d = 1; break;
            case 'c': has_c = 1; break;
            case 'b': zba = zbb = zbs = 1; break;
            default: die("--isa: unsupported single-letter extension");
            }
        }
        while (*q == '_') {
            const char *e = ++q;
            while (*q && *q != '_') q++;
            size_t n = (size_t)(q - e);
            if (n == 3 && !strncmp(e, "zba", 3)) zba = 1;
            else if (n == 3 && !strncmp(e, "zbb", 3)) zbb = 1;
            else if (n == 3 && !strncmp(e, "zbs", 3)) zbs = 1;
            else if (n == 6 && !strncmp(e, "zicntr", 6)) has_zicntr = 1;
            else if ((n == 5 && !strncmp(e, "zicsr", 5)) || (n == 8 && !strncmp(e, "zifencei", 8))) {}
            else die("--isa: unsupported extension");
        }
        if (f != d) die("--isa: F and D only together (the model's FP has FLEN 64)");
        has_fd = f;
        if (zba + zbb + zbs != 0 && zba + zbb + zbs != 3) die("--isa: Zba, Zbb and Zbs only together");
        has_b = zba;
    }
    if (privs) {
        if (!strcmp(privs, "m")) has_s = has_u = 0;
        else if (!strcmp(privs, "mu")) { has_s = 0; has_u = 1; }
        else if (!strcmp(privs, "msu")) has_s = has_u = 1;
        else die("--priv m|mu|msu");
    }
    misa_val = (2ull << 62) | (1u << 8) | (has_m ? 1u << 12 : 0) | (has_a ? 1u : 0) | (has_c ? 1u << 2 : 0) |
               (has_fd ? (1u << 3) | (1u << 5) : 0) | (has_b ? 1u << 1 : 0) | (has_s ? 1u << 18 : 0) |
               (has_u ? 1u << 20 : 0);
}
static inline u64 epc_mask(void) { return has_c ? ~(u64)1 : ~(u64)3; }
static int in_wfi;
static u64 resv_addr = ~(u64)0;          /* the LR reservation's physical address, or all ones */

/* devices */
static uint8_t rom_data[0x10000];
static u64 rom_len;
static u64 mtime, mtimecmp = ~(u64)0, tick_accum, idle_ticks;
static u64 chunk_steps;                  /* spike time model: steps taken in the current 5000-step chunk */
static int irq_check = 1;
static u64 tohost_addr = ~(u64)0, fromhost_addr = ~(u64)0;
static int sys_stop = -1;                /* -1 running; else exit kind (below) */
static u64 sys_exit_code;
enum { SX_TOHOST = 1, SX_FINISHER = 2, SX_TRAPLOOP = 3, SX_WFI_DEADLOCK = 4 };

/* ns16550a, register behaviour as Spike's model (reg-shift 0, 1-byte I/O), TX to stdout or --uart-out. */
static uint8_t u_ier, u_iir = 1, u_fcr, u_lcr, u_mcr = 0x08, u_lsr = 0x60, u_msr = 0xb0, u_scr, u_dll = 0x0c, u_dlm;
static uint8_t u_rxq[64];
static int u_rxn, u_rxh;
static uint8_t *u_in;
static size_t u_in_len, u_in_pos;
static FILE *uart_out;
static u64 uart_bytes;
static const char *out_marker;           /* --dump-on-output: write a state once the console output ends so */
static char out_tail[256];
static size_t out_tail_n;
static int out_marker_hit;
static void uart_note_tx(uint8_t b) {
    if (!out_marker || out_marker_hit) return;
    size_t m = strlen(out_marker);
    if (out_tail_n == sizeof out_tail) { memmove(out_tail, out_tail + 128, 128); out_tail_n = 128; }
    out_tail[out_tail_n++] = (char)b;
    if (out_tail_n >= m && !memcmp(out_tail + out_tail_n - m, out_marker, m)) out_marker_hit = 1;
}

/* PLIC: sources 1..PLIC_NDEV, contexts 0 (M) and 1 (S), behaviour as Spike's model. */
#define PLIC_NDEV 31
static uint8_t plic_prio[PLIC_NDEV + 1];
static u32 plic_level, plic_enable[2], plic_pending[2], plic_claimed[2], plic_thresh[2];
static uint8_t plic_pprio[2][PLIC_NDEV + 1];
#define UART_IRQ 1

/* the Spike-format commit log (--commit-log) */
static FILE *clog;
static u64 clog_from = 0, clog_to = ~(u64)0;
static int lg_nld, lg_nst, lg_xrd, lg_frd;
static u64 lg_ld[4], lg_st[4], lg_stv[4], lg_xv, lg_fv;
static int lg_sts[4];

static inline void mip_update_dev(u64 mask, int on) {
    u64 old = mip_dev;
    mip_dev = on ? (mip_dev | mask) : (mip_dev & ~mask);
    if (old != mip_dev && !time_spike) irq_check = 1;
}
static inline u64 mip_read(void) { return mip_sw | mip_dev; }

static void clint_tick(void) { mip_update_dev(IP_MTIP, mtime >= mtimecmp); }

/* ---- PLIC ---- */
static inline int plic_ctx(void) { return has_s ? 2 : 1; }   /* contexts: M, and S only with S (Spike) */
static u32 plic_best(int c) {
    u32 best = 0;
    uint8_t bp = 0;
    for (u32 id = 1; id <= PLIC_NDEV; id++) {
        if (!(plic_pending[c] >> id & 1) || (plic_claimed[c] >> id & 1)) continue;
        if (!best || bp < plic_pprio[c][id]) { best = id; bp = plic_pprio[c][id]; }
    }
    return bp <= plic_thresh[c] ? 0 : best;
}
static void plic_update(int c) { mip_update_dev(c ? IP_SEIP : IP_MEIP, plic_best(c) != 0); }
static void plic_set_level(u32 id, int lvl) {
    u32 m = 1u << id;
    if (lvl) plic_level |= m; else plic_level &= ~m;
    for (int c = 0; c < plic_ctx(); c++) {   /* as Spike: only the first context that enables the source */
        if (!(plic_enable[c] & m)) continue;
        if (lvl) { plic_pending[c] |= m; plic_pprio[c][id] = plic_prio[id]; }
        else { plic_pending[c] &= ~m; plic_pprio[c][id] = 0; plic_claimed[c] &= ~m; }
        plic_update(c);
        break;
    }
}
static int plic_load32(u64 off, u32 *v) {
    *v = 0;
    if (off < 0x1000) { u32 id = (u32)(off >> 2); if (id >= 1 && id <= PLIC_NDEV) *v = plic_prio[id]; return 1; }
    if (off < 0x2000) { if (off == 0x1000) *v = plic_pending[0] | plic_pending[1]; return 1; }
    if (off < 0x200000) {
        u64 c = (off - 0x2000) / 0x80, o = (off - 0x2000) % 0x80;
        if (c >= (u64)plic_ctx()) return 0;
        if (o == 0) *v = plic_enable[c];
        return 1;
    }
    u64 c = (off - 0x200000) / 0x1000, o = (off - 0x200000) % 0x1000;
    if (c >= (u64)plic_ctx()) return 0;
    if (o == 0) *v = plic_thresh[c];
    else if (o == 4) {
        u32 best = plic_best((int)c);
        if (best) plic_claimed[c] |= 1u << best;
        plic_update((int)c);
        *v = best;
    }
    return 1;
}
static int plic_store32(u64 off, u32 v) {
    if (off < 0x2000) {
        u32 id = (u32)(off >> 2);
        if (id >= 1 && id <= PLIC_NDEV) plic_prio[id] = v & 15;
        return 1;
    }
    if (off < 0x200000) {
        u64 c = (off - 0x2000) / 0x80, o = (off - 0x2000) % 0x80;
        if (c >= (u64)plic_ctx()) return 0;
        if (o != 0) return 1;
        u32 nv = v & ~1u & (u32)((2ull << PLIC_NDEV) - 1), x = plic_enable[c] ^ nv;
        plic_enable[c] = nv;
        for (u32 id = 1; id <= PLIC_NDEV; id++) {
            u32 m = 1u << id;
            if (!(x & m)) continue;
            if ((nv & m) && (plic_level & m)) { plic_pending[c] |= m; plic_pprio[c][id] = plic_prio[id]; }
            else if (!(nv & m)) { plic_pending[c] &= ~m; plic_pprio[c][id] = 0; plic_claimed[c] &= ~m; }
        }
        plic_update((int)c);
        return 1;
    }
    u64 c = (off - 0x200000) / 0x1000, o = (off - 0x200000) % 0x1000;
    if (c >= (u64)plic_ctx()) return 0;
    if (o == 0) { plic_thresh[c] = v & 15; plic_update((int)c); return 1; }
    if (o == 4) {
        if (v <= PLIC_NDEV && (plic_enable[c] >> v & 1)) { plic_claimed[c] &= ~(1u << v); plic_update((int)c); }
        return 1;
    }
    return 0;
}

/* ---- ns16550a ---- */
static void uart_update(void) {
    uint8_t irq = 0;
    if (u_fcr & 2) { u_fcr &= ~2; u_rxn = 0; u_lsr &= ~1; }
    if (u_fcr & 4) { u_fcr &= ~4; u_lsr |= 0x60; }
    if ((u_ier & 1) && (u_lsr & 1)) irq |= 4;
    if ((u_ier & 2) && (u_lsr & 0x40)) irq |= 2;
    u_iir = irq ? irq : 1;
    plic_set_level(UART_IRQ, irq != 0);
    if (!(u_ier & 2)) u_lsr |= 0x60;
}
/* Lab model: a scripted byte is offered only when the guest reads the UART by interrupt (IER.RDI set,
 * so a driver has the port open) and the RX FIFO is empty, which keeps input from being flushed at
 * driver start-up and feeds it at the pace the guest consumes it. */
static inline int uart_wants_input(void) { return u_in_pos < u_in_len && (u_ier & 1) && u_rxn == 0; }
static void uart_push_input(void) {      /* one scripted RX byte, when the FIFO can take it (as Spike's tick) */
    if (!(u_fcr & 1) || (u_mcr & 0x10) || u_rxn >= 64 || u_in_pos >= u_in_len) return;
    u_rxq[(u_rxh + u_rxn++) % 64] = u_in[u_in_pos++];
    u_lsr |= 1;
    uart_update();
}
static int uart_load(u64 off, int size, u64 *v) {
    if (size != 1 || off + 1 > UART_SIZE) return 0;
    uint8_t r = 0;
    switch (off & 7) {
    case 0:
        if (u_lcr & 0x80) r = u_dll;
        else if (!u_rxn) u_lsr &= ~1;
        else if (u_lsr & 0x10) u_lsr &= ~0x10;
        else { r = u_rxq[u_rxh]; u_rxh = (u_rxh + 1) % 64; if (!--u_rxn) u_lsr &= ~1; }
        *v = r;
        uart_update();
        return 1;
    case 1: r = (u_lcr & 0x80) ? u_dlm : u_ier; break;
    case 2: r = u_iir | 0xc0; break;
    case 3: r = u_lcr; break;
    case 4: r = u_mcr; break;
    case 5: r = u_lsr; break;
    case 6: r = u_msr; break;
    default: r = u_scr; break;
    }
    *v = r;
    return 1;
}
static int uart_store(u64 off, int size, u64 val) {
    if (size != 1 || off + 1 > UART_SIZE) return 0;
    uint8_t b = (uint8_t)val;
    switch (off & 7) {
    case 0:
        if (u_lcr & 0x80) u_dll = b;
        else if (u_mcr & 0x10) { if (u_rxn < 64) { u_rxq[(u_rxh + u_rxn++) % 64] = b; u_lsr |= 1; } }
        else { u_lsr |= 0x60; fputc(b, uart_out); uart_bytes++; uart_note_tx(b); if (b == '\n') fflush(uart_out); }
        break;
    case 1: if (u_lcr & 0x80) u_dlm = b; else u_ier = b & 15; break;
    case 2: u_fcr = b; break;
    case 3: u_lcr = b; break;
    case 4: u_mcr = b; break;
    case 7: u_scr = b; return 1;
    default: return 1;
    }
    uart_update();
    return 1;
}

/* ---- CLINT (SiFive layout, as Spike) ---- */
static void reg_read_le(u64 reg, u64 off, int size, u64 *v) {
    u64 r = reg >> (8 * off);
    *v = size == 8 ? r : r & ((1ull << (8 * size)) - 1);
}
static void reg_write_le(u64 *reg, u64 off, int size, u64 val) {
    u64 m = (size == 8 ? ~0ull : (1ull << (8 * size)) - 1) << (8 * off);
    *reg = (*reg & ~m) | ((val << (8 * off)) & m);
}
static int clint_load(u64 off, int size, u64 *v) {
    if (off < 0x4000) {
        if (size == 8) { u64 lo, hi; clint_load(off, 4, &lo); clint_load(off + 4, 4, &hi); *v = lo | hi << 32; return 1; }
        reg_read_le(off < 4 && (mip_dev & IP_MSIP) ? 1 : 0, off & 3, size, v);
        if (off >= 4) *v = 0;
        return 1;
    }
    if (off < 0xbff8) { if (off < 0x4008) reg_read_le(mtimecmp, off & 7, size, v); else *v = 0; return 1; }
    if (off + size <= 0xc000) { reg_read_le(mtime, off & 7, size, v); return 1; }
    return 0;
}
static int clint_store(u64 off, int size, u64 val) {
    if (off < 0x4000) {
        if (size == 8) return clint_store(off, 4, val) && clint_store(off + 4, 4, val >> 32);
        if (off == 0) mip_update_dev(IP_MSIP, val & 1);
    } else if (off < 0xbff8) {
        if (off < 0x4008) reg_write_le(&mtimecmp, off & 7, size, val);
    } else if (off + size <= 0xc000) {
        reg_write_le(&mtime, off & 7, size, val);
        tick_accum = ~(u64)0;      /* lab model: the store's own retirement makes it 0, then 100 more */
    } else return 0;
    clint_tick();
    return 1;
}

/* ---- physical access ---- */
static inline uint8_t *dram_ptr(u64 pa, int size) {
    u64 o = pa - DRAM_BASE;
    return o <= ram - (u64)size ? mem + o : NULL;
}
/* HTIF, as Spike's host: the run ends when the 64-bit tohost word holds a non-zero value. */
static void htif_check(void) {
    uint8_t *t = dram_ptr(tohost_addr, 8);
    u64 v = 0;
    if (t) memcpy(&v, t, 8);
    if (v) { sys_stop = SX_TOHOST; sys_exit_code = v; }
}
static int phys_load(u64 pa, int size, u64 *v) {
    uint8_t *p = dram_ptr(pa, size);
    if (p) { *v = 0; memcpy(v, p, (size_t)size); return 1; }
    if (pa >= ROM_BASE && pa - ROM_BASE + (u64)size <= rom_len) { *v = 0; memcpy(v, rom_data + (pa - ROM_BASE), (size_t)size); return 1; }
    if (pa >= CLINT_BASE && pa - CLINT_BASE < CLINT_SIZE) return clint_load(pa - CLINT_BASE, size, v);
    if (pa >= PLIC_BASE && pa - PLIC_BASE < PLIC_SIZE) {
        u32 lo, hi = 0;
        if (size != 4 && size != 8) return 0;
        if (!plic_load32(pa - PLIC_BASE, &lo)) return 0;
        if (size == 8 && !plic_load32(pa - PLIC_BASE + 4, &hi)) return 0;
        *v = lo | (u64)hi << 32;
        return 1;
    }
    if (pa >= UART_BASE && pa - UART_BASE < UART_SIZE) return uart_load(pa - UART_BASE, size, v);
    if (pa >= TEST_BASE && pa - TEST_BASE < TEST_SIZE) { *v = 0; return 1; }
    return 0;
}
static int phys_store(u64 pa, int size, u64 val) {
    uint8_t *p = dram_ptr(pa, size);
    if (p) {
        memcpy(p, &val, (size_t)size);
        if ((pa & ~(u64)7) == tohost_addr) htif_check();
        return 1;
    }
    if (pa >= CLINT_BASE && pa - CLINT_BASE < CLINT_SIZE) return clint_store(pa - CLINT_BASE, size, val);
    if (pa >= PLIC_BASE && pa - PLIC_BASE < PLIC_SIZE) {
        if (size != 4 && size != 8) return 0;
        if (!plic_store32(pa - PLIC_BASE, (u32)val)) return 0;
        return size == 4 || plic_store32(pa - PLIC_BASE + 4, (u32)(val >> 32));
    }
    if (pa >= UART_BASE && pa - UART_BASE < UART_SIZE) return uart_store(pa - UART_BASE, size, val);
    if (pa >= TEST_BASE && pa - TEST_BASE < TEST_SIZE) {
        if (pa == TEST_BASE && size >= 4) {
            u32 w = (u32)val, kind = w & 0xffff;
            if (kind == 0x5555 || kind == 0x3333 || kind == 0x7777) {
                sys_stop = SX_FINISHER;
                sys_exit_code = kind == 0x5555 ? 0 : kind == 0x7777 ? 0x7777 : ((w >> 16) ? (w >> 16) : 1);
            }
        }
        return 1;
    }
    return 0;
}

/* ---- Sv39 with Svade, and a 256-entry direct-mapped translation cache per access type, flushed (as
 * Spike's TLB) on every privilege change, satp change, SFENCE.VMA and mstatus MPP/MPRV/SUM/MXR change. ---- */
enum { AC_FETCH = 0, AC_LOAD = 1, AC_STORE = 2 };
static u64 tlb_vpn[3][256], tlb_ppage[3][256];
static void tlb_flush(void) { memset(tlb_vpn, 0xff, sizeof tlb_vpn); }
static const int pf_cause[3] = {12, 13, 15}, af_cause[3] = {1, 5, 7};

static int walk(u64 va, int acc, int eprv, u64 *pa) {
    int pf = pf_cause[acc];
    if ((u64)((i64)(va << 25) >> 25) != va) return pf;
    u64 base = (satp & ((1ull << 44) - 1)) << 12;
    for (int i = 2; i >= 0; i--) {
        u64 pte;
        uint8_t *p = dram_ptr(base + ((va >> (12 + 9 * i)) & 511) * 8, 8);
        if (!p) return af_cause[acc];
        memcpy(&pte, p, 8);
        u64 ppn = (pte >> 10) & ((1ull << 44) - 1);
        if (pte >> 54) return pf;                               /* reserved, PBMT and N: not implemented */
        if ((pte & (PTE_V | PTE_R | PTE_W | PTE_X)) == PTE_V) {  /* pointer to the next level */
            if (pte & (PTE_D | PTE_A | PTE_U)) return pf;
            base = ppn << 12;
            continue;
        }
        if (!(pte & PTE_V) || (!(pte & PTE_R) && (pte & PTE_W))) return pf;
        if (eprv == 0 ? !(pte & PTE_U) : ((pte & PTE_U) && (acc == AC_FETCH || !(mstatus & MS_SUM)))) return pf;
        if (acc == AC_FETCH ? !(pte & PTE_X)
            : acc == AC_LOAD ? !((pte & PTE_R) || ((mstatus & MS_MXR) && (pte & PTE_X)))
            : !((pte & PTE_R) && (pte & PTE_W))) return pf;
        if (i && (ppn & ((1ull << (9 * i)) - 1))) return pf;  /* misaligned superpage */
        if (!(pte & PTE_A) || (acc == AC_STORE && !(pte & PTE_D))) return pf;  /* Svade */
        u64 mask = (1ull << (12 + 9 * i)) - 1;
        *pa = ((ppn << 12) & ~mask) | (va & mask);
        return 0;
    }
    return pf;
}

/* 0 on success (pa set), else the exception cause. */
static inline int xlate(u64 va, int acc, u64 *pa) {
    int eprv = prv;
    if (acc != AC_FETCH && (mstatus & MS_MPRV) && prv == 3) eprv = (int)((mstatus >> 11) & 3);
    if (eprv == 3 || !(satp >> 60)) { *pa = va; return 0; }
    u64 vpn = va >> 12, i = vpn & 255;
    if (tlb_vpn[acc][i] == vpn) { *pa = tlb_ppage[acc][i] | (va & 4095); return 0; }
    int c = walk(va, acc, eprv, pa);
    if (c) return c;
    tlb_vpn[acc][i] = vpn;
    tlb_ppage[acc][i] = *pa & ~(u64)4095;
    return 0;
}

static void set_prv(int p) {
    if (p != prv) { prv = p; tlb_flush(); }
    else tlb_flush();          /* Spike's set_privilege always flushes */
    if (!time_spike) irq_check = 1;
}

static u64 mstatus_wmask(void) {
    u64 m = MS_MIE | MS_MPIE | MS_MPP;
    if (has_s) m |= MS_SIE | MS_SPIE | MS_SPP | MS_SUM | MS_MXR | MS_TVM | MS_TSR;
    if (has_s || has_fd) m |= MS_FS;
    if (has_u) m |= MS_MPRV | MS_TW;
    return m;
}
static void write_mstatus(u64 v) {
    u64 mpp = (v >> 11) & 3;
    if (!has_u) mpp = 3;
    else if (mpp == 2 || (mpp == 1 && !has_s)) mpp = 0;
    v = (v & ~MS_MPP) | mpp << 11;
    u64 n = (mstatus & ~mstatus_wmask()) | (v & mstatus_wmask());
    if ((n ^ mstatus) & (MS_MPP | MS_MPRV | MS_SUM | MS_MXR)) tlb_flush();
    n = ((n & MS_FS) == MS_FS) ? (n | MS_SD) : (n & ~MS_SD);
    mstatus = n;
    if (!time_spike) irq_check = 1;
}
static inline void fs_dirty(void) { mstatus |= MS_FS | MS_SD; }

/* ---- traps ---- */
static void take_trap(u64 cause, u64 tval, int interrupt) {
    u64 c = cause & 63;
    int deleg = has_s && prv <= 1 && ((interrupt ? mideleg : medeleg) >> c & 1);
    u64 epc = pc;
    if (trace_fd && tracing())
        fprintf(trace_fd, "%c %016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n", interrupt ? 'I' : 'E', pc, cause, tval);
    if (deleg) {
        scause = interrupt ? (1ull << 63) | c : c;
        sepc = epc & ~(u64)1;
        stval = tval;
        u64 s = mstatus;
        s = (s & ~MS_SPIE) | ((s & MS_SIE) ? MS_SPIE : 0);
        s = (s & ~MS_SPP) | (prv ? MS_SPP : 0);
        s &= ~MS_SIE;
        mstatus = s;
        pc = (stvec & ~(u64)3) + ((interrupt && (stvec & 1)) ? 4 * c : 0);
        set_prv(1);
    } else {
        mcause = interrupt ? (1ull << 63) | c : c;
        mepc = epc & ~(u64)1;
        mtval = tval;
        u64 s = mstatus;
        s = (s & ~MS_MPIE) | ((s & MS_MIE) ? MS_MPIE : 0);
        s = (s & ~MS_MPP) | ((u64)prv << 11);
        s &= ~MS_MIE;
        mstatus = s;
        pc = (mtvec & ~(u64)3) + ((interrupt && (mtvec & 1)) ? 4 * c : 0);
        set_prv(3);
    }
    if (time_spike) { counters_iter_end(); chunk_steps = 5000; }   /* a trap ends Spike's step chunk */
    else resv_addr = ~(u64)0;
}

/* Returns 1 when an interrupt was taken. Also leaves WFI when any interrupt is pending and enabled in mie. */
static int check_interrupts(void) {
    u64 pend = mip_read() & mie;
    if (!pend) return 0;
    in_wfi = 0;
    int m_en = prv < 3 || (mstatus & MS_MIE);
    u64 en = m_en ? pend & ~mideleg : 0;
    if (!en) {
        int s_en = prv < 1 || (prv == 1 && (mstatus & MS_SIE));
        en = s_en ? pend & mideleg : 0;
    }
    if (!en) return 0;
    static const int order[6] = {11, 3, 7, 9, 1, 5};
    for (int k = 0; k < 6; k++)
        if (en >> order[k] & 1) { take_trap((u64)order[k], 0, 1); return 1; }
    return 0;
}

/* ---- CSRs ---- */
static u64 sys_fcsr_read(u32 csr) { return csr == 1 ? (fcsr & 0x1f) : csr == 2 ? (fcsr >> 5) : fcsr; }

/* Read (and on write, the new value) of CSR csr. Returns 0 if the access is illegal. */
static int csr_access(u32 csr, int write, u64 wval_in, u64 *old, int kind, u64 src, int is_write_op) {
    (void)wval_in;
    u32 need = (csr >> 8) & 3;
    if ((int)need > prv) return 0;
    if (write && (csr >> 10) == 3) return 0;
    if (!has_s && (((csr >> 8) & 3) == 1 || csr == 0x302 || csr == 0x303)) return 0;   /* S CSRs, delegation */
    if (!has_u && (csr == 0x306 || csr == 0x30a)) return 0;                        /* mcounteren, menvcfg */
    if (!has_zicntr && csr >= 0xc00 && csr <= 0xc02) return 0;
    if (!has_fd && csr >= 0x001 && csr <= 0x003) return 0;
    u64 v = 0;
    int ok = 1;
    /* counters from S/U */
    if ((csr >= 0xc00 && csr <= 0xc02)) {
        u32 bit = csr - 0xc00;
        if (prv < 3 && !(mcounteren >> bit & 1)) return 0;
        if (prv == 0 && has_s && !(scounteren >> bit & 1)) return 0;
    }
    switch (csr) {
    case 0x001: case 0x002: case 0x003:
        if (!(mstatus & MS_FS)) return 0;
        v = sys_fcsr_read(csr); break;
    case 0xc00: v = mcycle; break;
    case 0xc01: v = mtime; break;
    case 0xc02: v = minstret; break;
    case 0x100: v = mstatus & SSTATUS_RMASK; break;
    case 0x104: v = mie & mideleg; break;
    case 0x105: v = stvec; break;
    case 0x106: v = scounteren; break;
    case 0x10a: v = senvcfg; break;
    case 0x140: v = sscratch; break;
    case 0x141: v = sepc & epc_mask(); break;
    case 0x142: v = scause; break;
    case 0x143: v = stval; break;
    case 0x144: v = mip_read() & mideleg; break;
    case 0x180:
        if (prv == 1 && (mstatus & MS_TVM)) return 0;
        v = satp; break;
    case 0x5a8: v = 0; break;                        /* scontext (Sdtrig, as Spike): reads 0 here */
    case 0x300: v = mstatus; break;
    case 0x301: v = misa_val; break;
    case 0x302: v = medeleg; break;
    case 0x303: v = mideleg; break;
    case 0x304: v = mie; break;
    case 0x305: v = mtvec; break;
    case 0x306: v = mcounteren; break;
    case 0x30a: v = menvcfg; break;
    case 0x320: v = mcountinhibit; break;
    case 0x340: v = mscratch; break;
    case 0x341: v = mepc & epc_mask(); break;
    case 0x342: v = mcause; break;
    case 0x343: v = mtval; break;
    case 0x344: v = mip_read(); break;
    case 0x7a0: case 0x7a1: case 0x7a2: case 0x7a3: case 0x7a4: v = 0; break;  /* Sdtrig, 0 triggers */
    case 0x7a8: v = mcontext; break;  /* Spike: a writable 13-bit context even with --triggers=0 (not in RVISSST3) */
    case 0xb00: v = mcycle; break;
    case 0xb02: v = minstret; break;
    case 0xf11: v = 0; break;
    case 0xf12: v = marchid_val; break;
    case 0xf13: v = 0; break;
    case 0xf14: v = 0; break;
    case 0xf15: v = 0; break;
    default:
        if ((csr >= 0x323 && csr <= 0x33f) || (csr >= 0xb03 && csr <= 0xb1f)) { v = 0; break; }  /* mhpmevent/counter */
        /* pmpcfg 0x3A0-0x3AF and pmpaddr 0x3B0-0x3EF: with 0 PMP entries they do not exist (cause 2), as Spike.
           mseccfg 0x747 exists only with Smepmp, Smmpm, Zicfilp or Zkr (none here): cause 2, as Spike */
        ok = 0;
    }
    if (!ok) return 0;
    *old = v;
    if (!write) return 1;
    u64 base = csr == 0x344 ? ((v & ~IP_SEIP) | (mip_sw & IP_SEIP)) : v;   /* mip: software SEIP only */
    u64 nv = kind == 1 ? src : kind == 2 ? (base | src) : (base & ~src);
    (void)is_write_op;
    switch (csr) {
    case 0x001: fcsr = (fcsr & 0xe0) | (u32)(nv & 0x1f); fs_dirty(); break;
    case 0x002: fcsr = (fcsr & 0x1f) | (u32)(nv & 7) << 5; fs_dirty(); break;
    case 0x003: fcsr = (u32)nv & 0xff; fs_dirty(); break;
    case 0x100: write_mstatus((mstatus & ~SSTATUS_WMASK) | (nv & SSTATUS_WMASK)); break;
    case 0x104: mie = (mie & ~mideleg) | (nv & mideleg); break;
    case 0x105: stvec = nv & ~(u64)2; break;
    case 0x106: scounteren = nv & (has_zicntr ? 7 : 0); break;
    case 0x10a: senvcfg = nv & 1; break;
    case 0x140: sscratch = nv; break;
    case 0x141: sepc = nv & ~(u64)1; break;
    case 0x142: scause = nv; break;
    case 0x143: stval = nv; break;
    case 0x144: { u64 m = mideleg & IP_SSIP; mip_sw = (mip_sw & ~m) | (nv & m); break; }
    case 0x180: {
        u64 mode = nv >> 60, n;
        /* An unsupported MODE leaves satp unchanged (the specification, and Spike's satp write). */
        n = (mode == 0 || mode == 8) ? (nv & ((0xfull << 60) | (0xffffull << 44) | ((1ull << 44) - 1))) : satp;
        if (n != satp) tlb_flush();
        satp = n;
        break;
    }
    case 0x300: write_mstatus(nv); break;
    case 0x302: medeleg = nv & (MEDELEG_MASK | (has_c ? 0 : 1) | (has_zicntr ? 1u << 19 : 0)); break;   /* 19: as Spike */
    case 0x303: mideleg = nv & IP_S_MASK; break;
    case 0x304: mie = nv & (has_s ? IP_ALL : IP_MSIP | IP_MTIP | IP_MEIP); break;
    case 0x305: mtvec = nv & ~(u64)2; break;
    case 0x306: mcounteren = nv & (has_zicntr ? 7 : 0); break;
    case 0x30a: menvcfg = nv & (has_s ? 1 : 0); break;
    case 0x320: mcountinhibit = nv & (has_zicntr ? 5 : 0); break;
    case 0x340: mscratch = nv; break;
    case 0x7a8: mcontext = nv & 0x1fff; break;
    case 0x341: mepc = nv & ~(u64)1; break;
    case 0x342: mcause = nv; break;
    case 0x343: mtval = nv; break;
    case 0x344: { u64 m = has_s ? IP_S_MASK : 0; mip_sw = (mip_sw & ~m) | (nv & m); break; }
    case 0xb00: mcycle = nv; mcycle_written = 1; break;
    case 0xb02: minstret = nv; minstret_written = 1; break;
    default: break;                        /* read-only zero fields and WARL constants ignore writes */
    }
    if (!time_spike) irq_check = 1;
    return 1;
}

/* ---- C expansion: the 32-bit equivalent of a 16-bit parcel, or 0 if illegal (RV64C, Zca + Zcd) ---- */
static inline u32 enc_i(u32 op, u32 rd, u32 f3, u32 rs1, i64 imm) { return ((u32)imm & 0xfff) << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op; }
static inline u32 enc_s(u32 op, u32 f3, u32 rs1, u32 rs2, i64 imm) {
    u32 i = (u32)imm & 0xfff;
    return (i >> 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | (i & 31) << 7 | op;
}
static inline u32 enc_r(u32 op, u32 rd, u32 f3, u32 rs1, u32 rs2, u32 f7) { return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op; }
static inline u32 enc_b(u32 f3, u32 rs1, u32 rs2, i64 imm) {
    u32 i = (u32)imm;
    return ((i >> 12) & 1) << 31 | ((i >> 5) & 63) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | ((i >> 1) & 15) << 8 | ((i >> 11) & 1) << 7 | 0x63;
}
static inline u32 enc_j(u32 rd, i64 imm) {
    u32 i = (u32)imm;
    return ((i >> 20) & 1) << 31 | ((i >> 1) & 1023) << 21 | ((i >> 11) & 1) << 20 | ((i >> 12) & 255) << 12 | rd << 7 | 0x6f;
}
#define CB(hi, lo) ((c >> (lo)) & ((1u << ((hi) - (lo) + 1)) - 1))

static u32 rvc_expand(u32 c) {
    u32 q = c & 3, f3 = c >> 13, rd = CB(11, 7), rs2 = CB(6, 2), rdp = 8 + CB(4, 2), rs1p = 8 + CB(9, 7);
    i64 imm6 = sx((CB(12, 12) << 5) | CB(6, 2), 6);
    switch (q) {
    case 0:
        switch (f3) {
        case 0: {
            u32 n = (CB(12, 11) << 4) | (CB(10, 7) << 6) | (CB(6, 6) << 2) | (CB(5, 5) << 3);
            return n ? enc_i(0x13, rdp, 0, 2, n) : 0;
        }
        case 1: return enc_i(0x07, rdp, 3, rs1p, (CB(12, 10) << 3) | (CB(6, 5) << 6));
        case 2: return enc_i(0x03, rdp, 2, rs1p, (CB(12, 10) << 3) | (CB(6, 6) << 2) | (CB(5, 5) << 6));
        case 3: return enc_i(0x03, rdp, 3, rs1p, (CB(12, 10) << 3) | (CB(6, 5) << 6));
        case 5: return enc_s(0x27, 3, rs1p, rdp, (CB(12, 10) << 3) | (CB(6, 5) << 6));
        case 6: return enc_s(0x23, 2, rs1p, rdp, (CB(12, 10) << 3) | (CB(6, 6) << 2) | (CB(5, 5) << 6));
        case 7: return enc_s(0x23, 3, rs1p, rdp, (CB(12, 10) << 3) | (CB(6, 5) << 6));
        default: return 0;
        }
    case 1:
        switch (f3) {
        case 0: return enc_i(0x13, rd, 0, rd, imm6);
        case 1: return rd ? enc_i(0x1b, rd, 0, rd, imm6) : 0;
        case 2: return enc_i(0x13, rd, 0, 0, imm6);
        case 3:
            if (rd == 2) {
                i64 n = sx((CB(12, 12) << 9) | (CB(6, 6) << 4) | (CB(5, 5) << 6) | (CB(4, 3) << 7) | (CB(2, 2) << 5), 10);
                return n ? enc_i(0x13, 2, 0, 2, n) : 0;
            } else {
                i64 n = sx((CB(12, 12) << 17) | (CB(6, 2) << 12), 18);
                return n ? ((u32)n & 0xfffff000u) | rd << 7 | 0x37 : 0;
            }
        case 4: {
            u32 f2 = CB(11, 10), sh = (CB(12, 12) << 5) | CB(6, 2);
            if (f2 == 0) return enc_i(0x13, rs1p, 5, rs1p, sh);
            if (f2 == 1) return enc_i(0x13, rs1p, 5, rs1p, sh | 0x400);
            if (f2 == 2) return enc_i(0x13, rs1p, 7, rs1p, imm6);
            u32 f = CB(6, 5), r2 = rdp;
            if (!CB(12, 12)) {
                static const u32 f3s[4] = {0, 4, 6, 7};
                return enc_r(0x33, rs1p, f3s[f], rs1p, r2, f == 0 ? 0x20 : 0);
            }
            if (f == 0) return enc_r(0x3b, rs1p, 0, rs1p, r2, 0x20);
            if (f == 1) return enc_r(0x3b, rs1p, 0, rs1p, r2, 0);
            return 0;
        }
        case 5: {
            i64 o = sx((CB(12, 12) << 11) | (CB(11, 11) << 4) | (CB(10, 9) << 8) | (CB(8, 8) << 10) | (CB(7, 7) << 6) |
                       (CB(6, 6) << 7) | (CB(5, 3) << 1) | (CB(2, 2) << 5), 12);
            return enc_j(0, o);
        }
        default: {
            i64 o = sx((CB(12, 12) << 8) | (CB(11, 10) << 3) | (CB(6, 5) << 6) | (CB(4, 3) << 1) | (CB(2, 2) << 5), 9);
            return enc_b(f3 == 6 ? 0 : 1, rs1p, 0, o);
        }
        }
    case 2:
        switch (f3) {
        case 0: return enc_i(0x13, rd, 1, rd, (CB(12, 12) << 5) | CB(6, 2));
        case 1: return enc_i(0x07, rd, 3, 2, (CB(12, 12) << 5) | (CB(6, 5) << 3) | (CB(4, 2) << 6));
        case 2: return rd ? enc_i(0x03, rd, 2, 2, (CB(12, 12) << 5) | (CB(6, 4) << 2) | (CB(3, 2) << 6)) : 0;
        case 3: return rd ? enc_i(0x03, rd, 3, 2, (CB(12, 12) << 5) | (CB(6, 5) << 3) | (CB(4, 2) << 6)) : 0;
        case 4:
            if (!CB(12, 12)) {
                if (!rs2) return rd ? enc_i(0x67, 0, 0, rd, 0) : 0;
                return enc_r(0x33, rd, 0, 0, rs2, 0);
            }
            if (!rs2) return rd ? enc_i(0x67, 1, 0, rd, 0) : 0x00100073u;
            return enc_r(0x33, rd, 0, rd, rs2, 0);
        case 5: return enc_s(0x27, 3, 2, rs2, (CB(12, 10) << 3) | (CB(9, 7) << 6));
        case 6: return enc_s(0x23, 2, 2, rs2, (CB(12, 9) << 2) | (CB(8, 7) << 6));
        default: return enc_s(0x23, 3, 2, rs2, (CB(12, 10) << 3) | (CB(9, 7) << 6));
        }
    default: return 0;
    }
}
#undef CB

/* ---- the commit log in Spike's --log-commits format ---- */
static inline int clogging(void) { return clog && count >= clog_from && count < clog_to; }
static void clog_line(u64 at, u32 raw, int ilen, int priv_at) {
    fprintf(clog, "core   0: %d 0x%016" PRIx64 " (0x%0*x)", priv_at, at, ilen == 2 ? 4 : 8, raw);
    if (lg_xrd) fprintf(clog, " x%-2d 0x%016" PRIx64, lg_xrd, lg_xv);
    if (lg_frd >= 0) fprintf(clog, " f%-2d 0x%016" PRIx64, lg_frd, lg_fv);
    for (int i = 0; i < lg_nld; i++) fprintf(clog, " mem 0x%016" PRIx64, lg_ld[i]);
    for (int i = 0; i < lg_nst; i++) {
        int w = lg_sts[i] * 2;
        u64 v = lg_sts[i] == 8 ? lg_stv[i] : lg_stv[i] & ((1ull << (8 * lg_sts[i])) - 1);
        fprintf(clog, " mem 0x%016" PRIx64 " 0x%0*" PRIx64, lg_st[i], w, v);
    }
    fputc('\n', clog);
}

/* ---- virtual memory access for the instruction being executed: 0 ok, else it raised (take_trap done) ---- */
static int raised;
#define RAISE(c, t) do { take_trap((c), (t), 0); raised = 1; return 0; } while (0)

static int vload(u64 va, int size, u64 *v) {
    u64 pa;
    if (va & (u64)(size - 1)) RAISE(4, va);
    int c = xlate(va, AC_LOAD, &pa);
    if (c) RAISE((u64)c, va);
    if (!phys_load(pa, size, v)) RAISE(5, va);
    if (warm) warm_load(pa);
    if (clog && lg_nld < 4) lg_ld[lg_nld++] = va;
    return 1;
}
static int vstore(u64 va, int size, u64 v) {
    u64 pa;
    if (va & (u64)(size - 1)) RAISE(6, va);
    int c = xlate(va, AC_STORE, &pa);
    if (c) RAISE((u64)c, va);
    if (!phys_store(pa, size, v)) RAISE(7, va);
    if (warm) l2_touch(pa);
    if (tracing()) note_store(va, v, size);
    if (clog && lg_nst < 4) { lg_st[lg_nst] = va; lg_stv[lg_nst] = v; lg_sts[lg_nst++] = size; }
    return 1;
}
/* Translate an AMO/SC address as a store (faults are store faults); returns the physical address. */
static int vamo_addr(u64 va, int size, u64 *pa) {
    if (va & (u64)(size - 1)) RAISE(6, va);
    int c = xlate(va, AC_STORE, pa);
    if (c) RAISE((u64)c, va);
    if (!dram_ptr(*pa, size)) RAISE(7, va);
    return 1;
}

static int fetch16(u64 va, u32 *h) {
    u64 pa;
    int c = xlate(va, AC_FETCH, &pa);
    if (c) RAISE((u64)c, va);
    uint8_t *p = dram_ptr(pa, 2);
    if (p) { uint16_t x; memcpy(&x, p, 2); *h = x; }
    else if (pa >= ROM_BASE && pa - ROM_BASE + 2 <= rom_len) { uint16_t x; memcpy(&x, rom_data + (pa - ROM_BASE), 2); *h = x; }
    else RAISE(1, va);
    if (warm) warm_fetch(pa);
    return 1;
}

/* ---- one instruction in system mode ---- */
static void sys_step(void) {
    u32 ins, lo, hi;
    int ilen;
    raised = 0;
    if (!fetch16(pc, &lo)) return;
    if ((lo & 3) == 3) {
        if (!fetch16(pc + 2, &hi)) return;
        ins = lo | hi << 16;
        ilen = 4;
    } else ilen = 2;
    u32 raw = ilen == 4 ? ins : lo;
    if (ilen == 2) { ins = has_c ? rvc_expand(lo) : 0; if (!ins) { take_trap(2, lo, 0); return; } }
    int priv_at = prv;
    u64 inh = mcountinhibit;
    lg_nld = lg_nst = 0; lg_xrd = 0; lg_frd = -1;
    u32 op = ins & 127, rd = (ins >> 7) & 31, f3 = (ins >> 12) & 7, rs1 = (ins >> 15) & 31, rs2 = (ins >> 20) & 31;
    u32 f7 = ins >> 25;
    u64 a = regs[rs1], b = regs[rs2];
    i64 imm = (i64)(int32_t)ins >> 20;
    u64 nxt = pc + (u64)ilen, value = 0;
    u32 dest = 0;        /* 1-31 x, 32-63 f */
    int ok = 0, serial = 0;
#define ILLEGAL() do { take_trap(2, raw, 0); return; } while (0)
#define CHK(x) do { if (!(x)) return; } while (0)
    switch (op) {
    case 0x37: value = (u64)(i64)(int32_t)(ins & 0xfffff000u); dest = rd; ok = 1; break;
    case 0x17: value = (u64)(i64)(int32_t)(ins & 0xfffff000u) + pc; dest = rd; ok = 1; break;
    case 0x6f: {
        u64 d = ((u64)(ins >> 31) << 20) | (((ins >> 12) & 255) << 12) | (((ins >> 20) & 1) << 11) | (((ins >> 21) & 1023) << 1);
        nxt = pc + (u64)sx(d, 21);
        value = pc + (u64)ilen; dest = rd; ok = 1;
        break;
    }
    case 0x67:
        if (f3 == 0) { nxt = (a + (u64)imm) & ~(u64)1; value = pc + (u64)ilen; dest = rd; ok = 1; }
        break;
    case 0x63: {
        int t;
        switch (f3) {
        case 0: t = a == b; break;
        case 1: t = a != b; break;
        case 4: t = (i64)a < (i64)b; break;
        case 5: t = (i64)a >= (i64)b; break;
        case 6: t = a < b; break;
        case 7: t = a >= b; break;
        default: t = -1;
        }
        if (t >= 0) {
            ok = 1;
            if (t) {
                u64 d = ((u64)(ins >> 31) << 12) | (((ins >> 7) & 1) << 11) | (((ins >> 25) & 63) << 5) | (((ins >> 8) & 15) << 1);
                nxt = pc + (u64)sx(d, 13);
            }
        }
        break;
    }
    case 0x03: case 0x23: {
        int load = op == 0x03;
        if ((load && f3 != 7) || (!load && f3 < 4)) {
            int size = 1 << (f3 & 3);
            i64 off = load ? imm : sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12);
            u64 address = a + (u64)off;
            if (load) {
                u64 v;
                CHK(vload(address, size, &v));
                if (f3 < 4 && size < 8) v = (u64)sx(v, 8 * size);
                value = v; dest = rd;
            } else CHK(vstore(address, size, b));
            ok = 1;
        }
        break;
    }
    case 0x07: case 0x27:      /* FLW/FLD/FSW/FSD */
        if (has_fd && (f3 == 2 || f3 == 3)) {
            if (!(mstatus & MS_FS)) ILLEGAL();
            int load = op == 0x07, size = f3 == 2 ? 4 : 8;
            i64 off = load ? imm : sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12);
            u64 address = a + (u64)off;
            if (load) {
                u64 v;
                CHK(vload(address, size, &v));
                value = size == 4 ? v | BOX : v; dest = 32 + rd;
            } else CHK(vstore(address, size, size == 4 ? fregs[rs2] & 0xffffffffu : fregs[rs2]));
            ok = 1;
        }
        break;
    case 0x43: case 0x47: case 0x4b: case 0x4f: case 0x53: {
        if (!has_fd || !(mstatus & MS_FS)) ILLEGAL();
        unsigned fl;
        int k = fp_exec(ins, a, fregs[rs1], fregs[rs2], fregs[ins >> 27], fcsr >> 5, &value, &fl);
        if (k < 0) ILLEGAL();
        dest = k ? 32 + rd : rd; ok = 1;
        if (fl) {
            fcsr |= fl; fs_dirty();
            if (tracing()) fprintf(trace_fd, "F %02x\n", fl);
        }
        break;
    }
    case 0x2f: {               /* A: LR/SC and AMOs, .W and .D */
        if (!has_a || (f3 != 2 && f3 != 3)) break;
        int size = f3 == 2 ? 4 : 8;
        u32 f5 = ins >> 27;
        u64 pa, old;
        if (f5 == 2) {          /* LR */
            if (rs2) break;
            if (a & (u64)(size - 1)) { take_trap(4, a, 0); return; }
            int c = xlate(a, AC_LOAD, &pa);
            if (c) { take_trap((u64)c, a, 0); return; }
            if (!dram_ptr(pa, size)) { take_trap(5, a, 0); return; }
            old = 0; memcpy(&old, dram_ptr(pa, size), (size_t)size);
            if (clog && lg_nld < 4) lg_ld[lg_nld++] = a;
            if (warm) warm_load(pa);
            resv_addr = pa;
            value = size == 4 ? (u64)sx(old, 32) : old; dest = rd; ok = 1;
            break;
        }
        if (f5 == 3) {          /* SC */
            CHK(vamo_addr(a, size, &pa));
            int success = resv_addr == pa;
            if (success) {
                memcpy(dram_ptr(pa, size), &b, (size_t)size);
                if ((pa & ~(u64)7) == tohost_addr) htif_check();
                if (tracing()) note_store(a, b, size);
                if (clog && lg_nst < 4) { lg_st[lg_nst] = a; lg_stv[lg_nst] = b; lg_sts[lg_nst++] = size; }
                if (warm) l2_touch(pa);
            }
            resv_addr = ~(u64)0;
            value = !success; dest = rd; ok = 1;
            break;
        }
        if (f5 != 0x01 && f5 != 0x00 && f5 != 0x04 && f5 != 0x0c && f5 != 0x08 && f5 != 0x10 && f5 != 0x14 &&
            f5 != 0x18 && f5 != 0x1c) ILLEGAL();
        CHK(vamo_addr(a, size, &pa));
        old = 0; memcpy(&old, dram_ptr(pa, size), (size_t)size);
        u64 x = size == 4 ? (u64)sx(old, 32) : old, y = size == 4 ? (u64)sx(b, 32) : b, r;
        switch (f5) {
        case 0x01: r = y; break;
        case 0x00: r = x + y; break;
        case 0x04: r = x ^ y; break;
        case 0x0c: r = x & y; break;
        case 0x08: r = x | y; break;
        case 0x10: r = (i64)x < (i64)y ? x : y; break;
        case 0x14: r = (i64)x > (i64)y ? x : y; break;
        case 0x18: r = (size == 4 ? (u32)x < (u32)y : x < y) ? x : y; break;
        case 0x1c: r = (size == 4 ? (u32)x > (u32)y : x > y) ? x : y; break;
        default: ILLEGAL();
        }
        memcpy(dram_ptr(pa, size), &r, (size_t)size);
        if ((pa & ~(u64)7) == tohost_addr) htif_check();
        if (clog && lg_nld < 4) lg_ld[lg_nld++] = a;
        if (clog && lg_nst < 4) { lg_st[lg_nst] = a; lg_stv[lg_nst] = r; lg_sts[lg_nst++] = size; }
        if (tracing()) note_store(a, r, size);
        if (warm) l2_touch(pa);
        value = x; dest = rd; ok = 1;
        break;
    }
    case 0x0f: if (f3 == 0 || f3 == 1) ok = 1; break;
    case 0x73: {
        if (f3 == 0) {
            if (ins == 0x00000073) { take_trap(prv == 3 ? 11 : prv == 1 ? 9 : 8, 0, 0); return; }
            if (!has_s && (ins == 0x10200073 || ((ins >> 25) == 0x09 && rd == 0))) ILLEGAL();   /* SRET, SFENCE.VMA */
            if (ins == 0x00100073) { take_trap(3, pc, 0); return; }
            if (ins == 0x30200073) {                       /* MRET */
                if (prv < 3) ILLEGAL();
                u64 s = mstatus;
                int np = (int)((s >> 11) & 3);
                if (np != 3) s &= ~MS_MPRV;
                s = (s & ~MS_MIE) | ((s & MS_MPIE) ? MS_MIE : 0);
                s |= MS_MPIE;
                s &= ~MS_MPP;                             /* MPP := U (M without U) */
                write_mstatus(s);
                nxt = mepc & epc_mask();
                set_prv(np);
                ok = 1; serial = 1;
                break;
            }
            if (ins == 0x10200073) {                       /* SRET */
                if (prv < 1 || (prv == 1 && (mstatus & MS_TSR))) ILLEGAL();
                u64 s = mstatus;
                int np = (s & MS_SPP) ? 1 : 0;
                s = (s & ~MS_SIE) | ((s & MS_SPIE) ? MS_SIE : 0);
                s |= MS_SPIE;
                s &= ~MS_SPP;
                s &= ~MS_MPRV;
                write_mstatus(s);
                nxt = sepc & epc_mask();
                set_prv(np);
                ok = 1; serial = 1;
                break;
            }
            if (ins == 0x10500073) {                       /* WFI */
                if ((mstatus & MS_TW) ? prv < 3 : (has_s && prv < 1)) ILLEGAL();
                in_wfi = 1;
                ok = 1; serial = 2;
                break;
            }
            if ((ins >> 25) == 0x09 && rd == 0) {          /* SFENCE.VMA */
                if (prv < 1 || (prv == 1 && (mstatus & MS_TVM))) ILLEGAL();
                tlb_flush();
                ok = 1;
                break;
            }
            break;
        }
        if (f3 == 4) break;
        if (time_spike && !csr_serialized) {
            /* Spike's validate_csr ends its inner loop before a CSR instruction executes (counters bumped,
             * pending interrupts taken), then runs the instruction in the next iteration. */
            csr_serialized = 1;
            counters_iter_end();
            if (check_interrupts()) { csr_serialized = 0; return; }
        }
        csr_serialized = 0;
        u32 csr = ins >> 20;
        int kind = f3 & 3;
        u64 src = f3 >= 5 ? rs1 : a, old;
        int write = kind == 1 || rs1 != 0;
        if (!csr_access(csr, write, 0, &old, kind, src, 1)) ILLEGAL();
        if (adopt_path && csr == 0xb00 && rd != 0) {
            /* the RTL's own mcycle value for this read (its N record); the write, if any, was applied above */
            if (adopt_i == adopt_n) die("--adopt: an mcycle read with no N record left");
            old = adopt_v[adopt_i++];
            if (tracing()) fprintf(trace_fd, "N b00 %016" PRIx64 "\n", old);
        }
        value = old; dest = rd; ok = 1; serial = 1;
        break;
    }
    case 0x13: case 0x1b: case 0x33: case 0x3b: {
        int word = op == 0x1b || op == 0x3b;
        if ((op == 0x33 || op == 0x3b) && f7 == 1 && !has_m) break;
        if ((op == 0x33 || op == 0x3b) && f7 == 1) {
            if (!word || f3 == 0 || f3 >= 4) {
                if (f3 < 4) {
                    if (word) value = (u64)(i64)(int32_t)(u32)(a * b);
                    else if (f3 == 0) value = a * b;
                    else if (f3 == 1) value = mulh64(a, b);
                    else if (f3 == 2) value = mulhsu64(a, b);
                    else value = mulhu64(a, b);
                } else value = divide((int)f3, word, a, b);
                dest = rd; ok = 1;
            }
            break;
        }
        if (has_b && bitmanip(ins, a, b, &value)) { dest = rd; ok = 1; break; }
        int immediate = op == 0x13 || op == 0x1b;
        int width = word ? 32 : 64;
        u64 rhs = immediate ? (u64)imm : b;
        unsigned shift = (unsigned)(rhs & (u64)(width - 1));
        int subtract = !immediate && f7 == 32;
        int arith = (ins >> 30) & 1;
        int valid = 1;
        if (immediate) {
            if (f3 == 1 || f3 == 5) {
                u32 top = ins >> (word ? 25 : 26);
                valid = top == 0 || (f3 == 5 && top == (word ? 32u : 16u));
            }
        } else valid = f7 == 0 || (f7 == 32 && (f3 == 0 || f3 == 5));
        if (word && f3 != 0 && f3 != 1 && f3 != 5) valid = 0;
        if (!valid) break;
        switch (f3) {
        case 0: value = subtract ? a - rhs : a + rhs; break;
        case 1: value = a << shift; break;
        case 2: value = (i64)a < (i64)rhs; break;
        case 3: value = a < rhs; break;
        case 4: value = a ^ rhs; break;
        case 5:
            if (arith) value = word ? (u64)((i64)(int32_t)(u32)a >> shift) : (u64)((i64)a >> shift);
            else value = word ? (u64)((u32)a >> shift) : a >> shift;
            break;
        case 6: value = a | rhs; break;
        default: value = a & rhs;
        }
        if (word) value = (u64)(i64)(int32_t)(u32)value;
        dest = rd; ok = 1;
        break;
    }
    default: break;
    }
#undef CHK
    if (!ok) ILLEGAL();
#undef ILLEGAL
    if (!has_c && (nxt & 2)) { take_trap(0, nxt, 0); return; }
    if (dest >= 32) { fregs[dest - 32] = value; fs_dirty(); lg_frd = (int)dest - 32; lg_fv = value; }
    else if (dest) { regs[dest] = value; lg_xrd = (int)dest; lg_xv = value; }
    else value = 0;
    if (tracing())
        fprintf(trace_fd, "R %016" PRIx64 " %08x %02x %016" PRIx64 " %016" PRIx64 "\n", pc, raw, dest, value, nxt);
    if (clogging()) clog_line(pc, raw, ilen, priv_at);
    pc = nxt;
    count++;
    if (time_spike) iter_n++;
    else {
        if (mcycle_written) mcycle_written = 0; else if (!(inh & 1)) mcycle++;
        if (minstret_written) minstret_written = 0; else if (!(inh & 4)) minstret++;
    }
    if (time_spike) {
        chunk_steps++;
        if (serial) { irq_check = 1; counters_iter_end(); }
        if (serial == 2) chunk_steps = 5000;   /* WFI yields: the chunk ends */
    } else if (++tick_accum == 100) { tick_accum = 0; mtime++; clint_tick(); }
}

/* Spike's chunk boundary: the reservation is dropped, devices tick by 50 RTC ticks, the UART polls input. */
static void spike_chunk_end(void) {
    counters_iter_end();
    chunk_steps = 0;
    resv_addr = ~(u64)0;
    mtime += 50;
    clint_tick();
    uart_push_input();
    irq_check = 1;
}

/* ---- loading ---- */
typedef struct { unsigned char e_ident[16]; uint16_t e_type, e_machine; u32 e_version; u64 e_entry, e_phoff, e_shoff;
    u32 e_flags; uint16_t e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx; } elf64_ehdr;
typedef struct { u32 p_type, p_flags; u64 p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align; } elf64_phdr;
typedef struct { u32 sh_name, sh_type; u64 sh_flags, sh_addr, sh_offset, sh_size; u32 sh_link, sh_info; u64 sh_addralign, sh_entsize; } elf64_shdr;
typedef struct { u32 st_name; unsigned char st_info, st_other; uint16_t st_shndx; u64 st_value, st_size; } elf64_sym;

static uint8_t *read_file(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = malloc((size_t)n + 1);
    if (!b || fread(b, 1, (size_t)n, f) != (size_t)n) die("read failed");
    fclose(f);
    *len = (size_t)n;
    return b;
}

static u64 load_elf(const char *path) {
    size_t n;
    uint8_t *b = read_file(path, &n);
    if (!b || n < sizeof(elf64_ehdr) || memcmp(b, "\177ELF\2\1", 6)) die("not a little-endian ELF64 file");
    elf64_ehdr h;
    memcpy(&h, b, sizeof h);
    if (h.e_phentsize < sizeof(elf64_phdr) || h.e_phoff > n || (u64)h.e_phnum * h.e_phentsize > n - h.e_phoff ||
        (h.e_shnum && (h.e_shentsize < sizeof(elf64_shdr) || h.e_shoff > n ||
                       (u64)h.e_shnum * h.e_shentsize > n - h.e_shoff)))
        die("ELF header tables outside the file");
    u64 off = h.e_type == 3 ? DRAM_BASE : 0;   /* ET_DYN is loaded at DRAM base + its addresses, as Spike */
    for (int i = 0; i < h.e_phnum; i++) {
        elf64_phdr p;
        memcpy(&p, b + h.e_phoff + (u64)i * h.e_phentsize, sizeof p);
        if (p.p_type != 1 || !p.p_memsz) continue;
        p.p_paddr += off;
        uint8_t *d = dram_ptr(p.p_paddr, 1);
        if (p.p_filesz > p.p_memsz || p.p_offset > n || p.p_filesz > n - p.p_offset) die("bad ELF segment");
        if (!d || p.p_memsz > ram || p.p_paddr - DRAM_BASE > ram - p.p_memsz) die("ELF segment outside DRAM");
        memset(d, 0, p.p_memsz);
        memcpy(d, b + p.p_offset, p.p_filesz);
    }
    for (int i = 0; i < h.e_shnum; i++) {      /* tohost/fromhost symbols (HTIF), as Spike */
        elf64_shdr s;
        memcpy(&s, b + h.e_shoff + (u64)i * h.e_shentsize, sizeof s);
        if (s.sh_type != 2) continue;
        elf64_shdr st;
        if (s.sh_link >= h.e_shnum || s.sh_offset > n || s.sh_size > n - s.sh_offset) die("bad ELF symbol table");
        memcpy(&st, b + h.e_shoff + (u64)s.sh_link * h.e_shentsize, sizeof st);
        if (st.sh_offset > n || st.sh_size > n - st.sh_offset || !st.sh_size || b[st.sh_offset + st.sh_size - 1])
            die("bad ELF string table");
        for (u64 k = 0; k < s.sh_size / sizeof(elf64_sym); k++) {
            elf64_sym y;
            memcpy(&y, b + s.sh_offset + k * sizeof y, sizeof y);
            if (y.st_name >= st.sh_size) die("bad ELF symbol name");
            const char *name = (const char *)b + st.sh_offset + y.st_name;
            if (!strcmp(name, "tohost")) tohost_addr = y.st_value + off;
            else if (!strcmp(name, "fromhost")) fromhost_addr = y.st_value + off;
        }
    }
    free(b);
    return h.e_entry + off;
}

/* Spike's boot ROM: auipc t0; addi a1, t0, 32 (the DTB); csrr a0, mhartid; ld t0, 24(t0); jr t0; then the
 * entry PC, then the DTB; the ROM is padded to a 4 KiB multiple. */
static void build_rom(u64 entry, const char *dtb) {
    u32 v[8] = {0x297, 0x28593 + (8 * 4 << 20), 0xf1402573, 0x0182b283u, 0x28067, 0, (u32)entry, (u32)(entry >> 32)};
    memcpy(rom_data, v, sizeof v);
    rom_len = sizeof v;
    if (dtb) {
        size_t n;
        uint8_t *d = read_file(dtb, &n);
        if (!d || n + rom_len > sizeof rom_data) die("cannot read --dtb");
        memcpy(rom_data + rom_len, d, n);
        rom_len += n;
        free(d);
    }
    rom_len = (rom_len + 4095) & ~(u64)4095;
}

/* ---- RVISSST3 full-system state ---- */
#define KV(name) {#name, &name}
typedef struct { const char *name; u64 *p; } kv_t;
static u64 kv_prv, kv_fcsr, kv_wfi, kv_uart[11], kv_plic_level, kv_plic_ctx[8], kv_plic_prio[PLIC_NDEV + 1],
           kv_plic_pprio[2 * (PLIC_NDEV + 1)], kv_rx[3];
static void kv_pack(int out) {
    if (out) {
        kv_prv = (u64)prv; kv_fcsr = fcsr; kv_wfi = (u64)in_wfi;
        uint8_t ur[11] = {u_ier, u_iir, u_fcr, u_lcr, u_mcr, u_lsr, u_msr, u_scr, u_dll, u_dlm, 0};
        for (int i = 0; i < 11; i++) kv_uart[i] = ur[i];
        kv_plic_level = plic_level;
        for (int c = 0; c < 2; c++) {
            kv_plic_ctx[4 * c] = plic_enable[c]; kv_plic_ctx[4 * c + 1] = plic_pending[c];
            kv_plic_ctx[4 * c + 2] = plic_claimed[c]; kv_plic_ctx[4 * c + 3] = plic_thresh[c];
        }
        for (int i = 0; i <= PLIC_NDEV; i++) { kv_plic_prio[i] = plic_prio[i]; kv_plic_pprio[i] = plic_pprio[0][i];
                                              kv_plic_pprio[PLIC_NDEV + 1 + i] = plic_pprio[1][i]; }
        kv_rx[0] = (u64)u_rxn; kv_rx[1] = (u64)u_rxh; kv_rx[2] = u_in_pos;
    } else {
        prv = (int)kv_prv; fcsr = (u32)kv_fcsr; in_wfi = (int)kv_wfi;
        u_ier = (uint8_t)kv_uart[0]; u_iir = (uint8_t)kv_uart[1]; u_fcr = (uint8_t)kv_uart[2]; u_lcr = (uint8_t)kv_uart[3];
        u_mcr = (uint8_t)kv_uart[4]; u_lsr = (uint8_t)kv_uart[5]; u_msr = (uint8_t)kv_uart[6]; u_scr = (uint8_t)kv_uart[7];
        u_dll = (uint8_t)kv_uart[8]; u_dlm = (uint8_t)kv_uart[9];
        plic_level = (u32)kv_plic_level;
        for (int c = 0; c < 2; c++) {
            plic_enable[c] = (u32)kv_plic_ctx[4 * c]; plic_pending[c] = (u32)kv_plic_ctx[4 * c + 1];
            plic_claimed[c] = (u32)kv_plic_ctx[4 * c + 2]; plic_thresh[c] = (u32)kv_plic_ctx[4 * c + 3];
        }
        for (int i = 0; i <= PLIC_NDEV; i++) { plic_prio[i] = (uint8_t)kv_plic_prio[i]; plic_pprio[0][i] = (uint8_t)kv_plic_pprio[i];
                                              plic_pprio[1][i] = (uint8_t)kv_plic_pprio[PLIC_NDEV + 1 + i]; }
        u_rxn = (int)kv_rx[0]; u_rxh = (int)kv_rx[1]; u_in_pos = kv_rx[2];
    }
}
static u64 kv_time_spike, kv_irq_check, kv_isa;
static u64 isa_config(void) {
    return (u64)has_m | (u64)has_a << 1 | (u64)has_fd << 2 | (u64)has_c << 3 | (u64)has_b << 4 |
           (u64)has_zicntr << 5 | (u64)has_s << 6 | (u64)has_u << 7;
}
/* The named words of an RVISSST3 file, in file order (documented in cpu/PRIV-CONTRACT.md). */
static kv_t sys_kv[] = {
    {"prv", &kv_prv}, {"fcsr", &kv_fcsr}, KV(mstatus), KV(medeleg), KV(mideleg), KV(mie), {"mip_sw", &mip_sw},
    {"mip_dev", &mip_dev}, KV(mtvec), KV(mepc), KV(mcause), KV(mtval), KV(mscratch), KV(mcounteren),
    KV(mcountinhibit), KV(menvcfg), KV(stvec), KV(sepc), KV(scause), KV(stval), KV(sscratch), KV(satp),
    KV(scounteren), KV(senvcfg), KV(mcycle), KV(minstret), {"wfi", &kv_wfi}, KV(mtime), KV(mtimecmp),
    KV(tick_accum), KV(chunk_steps), {"time_spike", &kv_time_spike}, KV(idle_ticks), KV(tohost_addr),
    KV(fromhost_addr), KV(marchid_val), {"plic_level", &kv_plic_level}, KV(resv_addr), {"irq_check", &kv_irq_check},
    KV(mcycle_written), KV(minstret_written), KV(iter_n), KV(iter_inh), KV(csr_serialized), {"isa_config", &kv_isa},
};
static void write_sys_state(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot write state");
    kv_pack(1);
    kv_time_spike = (u64)time_spike;
    kv_irq_check = (u64)irq_check;
    kv_isa = isa_config();
    u64 head[4] = {0, 1, count, pc};
    memcpy(&head[0], "RVISSST3", 8);
    fwrite(head, 8, 4, f);
    fwrite(regs, 8, 64, f);
    u64 nkv = sizeof sys_kv / sizeof sys_kv[0] + 11 + 8 + 2 * (PLIC_NDEV + 1) * 1 + (PLIC_NDEV + 1) + 3;
    fwrite(&nkv, 8, 1, f);
    char name[24];
#define PUT(nm, val) do { memset(name, 0, 24); snprintf(name, 24, "%s", nm); fwrite(name, 1, 24, f); u64 vv = (val); fwrite(&vv, 8, 1, f); } while (0)
    for (size_t i = 0; i < sizeof sys_kv / sizeof sys_kv[0]; i++) PUT(sys_kv[i].name, *sys_kv[i].p);
    static const char *un[11] = {"uart_ier", "uart_iir", "uart_fcr", "uart_lcr", "uart_mcr", "uart_lsr", "uart_msr",
                                 "uart_scr", "uart_dll", "uart_dlm", "uart_pad"};
    for (int i = 0; i < 11; i++) PUT(un[i], kv_uart[i]);
    static const char *pc_names[4] = {"enable", "pending", "claimed", "threshold"};
    char nb[24];
    for (int i = 0; i < 8; i++) { snprintf(nb, 24, "plic_c%d_%s", i / 4, pc_names[i % 4]); PUT(nb, kv_plic_ctx[i]); }
    for (int i = 0; i <= PLIC_NDEV; i++) { snprintf(nb, 24, "plic_prio%d", i); PUT(nb, kv_plic_prio[i]); }
    for (int i = 0; i < 2 * (PLIC_NDEV + 1); i++) { snprintf(nb, 24, "plic_c%d_pprio%d", i / (PLIC_NDEV + 1), i % (PLIC_NDEV + 1)); PUT(nb, kv_plic_pprio[i]); }
    PUT("uart_rx_count", kv_rx[0]); PUT("uart_rx_head", kv_rx[1]); PUT("uart_in_pos", kv_rx[2]);
#undef PUT
    u64 rx[64];
    for (int i = 0; i < 64; i++) rx[i] = u_rxq[i];
    fwrite(rx, 8, 64, f);
    u64 region[2] = {DRAM_BASE, ram};
    fwrite(region, 8, 2, f);
    if (fwrite(mem, 1, ram, f) != ram) die("state write failed");
    u64 rregion[2] = {ROM_BASE, rom_len};
    fwrite(rregion, 8, 2, f);
    if (fwrite(rom_data, 1, rom_len, f) != rom_len || fclose(f)) die("state write failed");
}
static void read_sys_state(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot read state");
    u64 head[4], nkv = 0;
    kv_isa = isa_config();   /* states written before the configuration was recorded are the default machine */
    if (fread(head, 8, 4, f) != 4 || memcmp(&head[0], "RVISSST3", 8) || head[1] != 1) die("not an RVISSST3 state file");
    count = head[2]; pc = head[3];
    if (fread(regs, 8, 64, f) != 64 || fread(&nkv, 8, 1, f) != 1) die("short state file");
    for (u64 i = 0; i < nkv; i++) {
        char name[24];
        u64 v;
        if (fread(name, 1, 24, f) != 24 || fread(&v, 8, 1, f) != 1) die("short state file");
        name[23] = 0;
        int found = 0;
        for (size_t k = 0; k < sizeof sys_kv / sizeof sys_kv[0]; k++)
            if (!strcmp(name, sys_kv[k].name)) { *sys_kv[k].p = v; found = 1; }
        static const char *un[11] = {"uart_ier", "uart_iir", "uart_fcr", "uart_lcr", "uart_mcr", "uart_lsr", "uart_msr",
                                     "uart_scr", "uart_dll", "uart_dlm", "uart_pad"};
        for (int k = 0; k < 11; k++) if (!strcmp(name, un[k])) { kv_uart[k] = v; found = 1; }
        int c, j;
        char tail[24];
        if (sscanf(name, "plic_c%d_pprio%d", &c, &j) == 2 && c >= 0 && c < 2 && j >= 0 && j <= PLIC_NDEV) { kv_plic_pprio[c * (PLIC_NDEV + 1) + j] = v; found = 1; }
        else if (sscanf(name, "plic_c%d_%23s", &c, tail) == 2 && c >= 0 && c < 2) {
            static const char *pc_names[4] = {"enable", "pending", "claimed", "threshold"};
            for (int k = 0; k < 4; k++) if (!strcmp(tail, pc_names[k])) { kv_plic_ctx[4 * c + k] = v; found = 1; }
        } else if (sscanf(name, "plic_prio%d", &j) == 1 && j >= 0 && j <= PLIC_NDEV) { kv_plic_prio[j] = v; found = 1; }
        if (!strcmp(name, "uart_rx_count")) { kv_rx[0] = v; found = 1; }
        if (!strcmp(name, "uart_rx_head")) { kv_rx[1] = v; found = 1; }
        if (!strcmp(name, "uart_in_pos")) { kv_rx[2] = v; found = 1; }
        if (!found) { fprintf(stderr, "rv_iss: unknown state word %s\n", name); exit(2); }
    }
    u64 rx[64], region[2];
    if (fread(rx, 8, 64, f) != 64) die("short state file");
    for (int i = 0; i < 64; i++) u_rxq[i] = (uint8_t)rx[i];
    if (fread(region, 8, 2, f) != 2 || region[0] != DRAM_BASE || region[1] != ram) die("state DRAM size differs from --ram");
    if (fread(mem, 1, ram, f) != ram) die("short state file");
    if (fread(region, 8, 2, f) != 2 || region[0] != ROM_BASE || region[1] > sizeof rom_data) die("bad ROM region");
    rom_len = region[1];
    if (fread(rom_data, 1, rom_len, f) != rom_len) die("short state file");
    fclose(f);
    if (kv_rx[0] > 64 || kv_rx[1] >= 64 || kv_rx[2] > u_in_len) die("bad UART state in the state file");
    kv_pack(0);
    if ((int)kv_time_spike != time_spike) die("state was written with the other --time model");
    if (kv_isa != isa_config()) die("state was written with another --isa/--priv configuration");
    regs[0] = 0;
    tlb_flush();
    irq_check = (int)kv_irq_check;
}

/* ---- the system-mode run ---- */
static const char *sys_isa, *sys_priv;
static const char *sys_elf, *sys_dtb, *sys_bins[8], *uart_in_path, *uart_out_path;
static int sys_nbins;

static int sys_main(const char *state, const char *trace, const char *final_state, u64 max, const char *clog_path) {
    if (ram > ((u64)1 << 34)) die("--sys: --ram above 16 GiB");
    mem = calloc(1, ram + 8);
    if (!mem) die("out of memory");
    uart_out = stdout;
    if (uart_out_path && !(uart_out = fopen(uart_out_path, "w"))) die("cannot write --uart-out");
    if (uart_in_path) { u_in = read_file(uart_in_path, &u_in_len); if (!u_in) die("cannot read --uart-in"); }
    tlb_flush();
    mstatus = has_u ? (2ull << 32) : 0;                 /* UXL with U, SXL with S, MPP = least mode */
    mstatus |= has_s ? (2ull << 34) : 0;
    mstatus |= has_u ? 0 : MS_MPP;
    if (state) read_sys_state(state);
    else {
        u64 entry = DRAM_BASE;
        if (sys_elf) entry = load_elf(sys_elf);
        for (int i = 0; i < sys_nbins; i++) {          /* FILE@ADDR raw binaries */
            char *at = strrchr(sys_bins[i], '@');
            if (!at) die("--bin FILE@ADDR");
            *at = 0;
            u64 addr = strtoull(at + 1, NULL, 0);
            size_t n;
            uint8_t *b = read_file(sys_bins[i], &n);
            if (!b || !dram_ptr(addr, 1) || addr - DRAM_BASE + n > ram) die("--bin outside DRAM");
            memcpy(dram_ptr(addr, 1), b, n);
            free(b);
        }
        build_rom(entry, sys_dtb);
        pc = ROM_BASE;
        prv = 3;
    }
    if (adopt_path) adopt_load(adopt_path);
    if (trace && !(trace_fd = fopen(trace, "w"))) die("cannot write trace");
    if (trace_fd) setvbuf(trace_fd, NULL, _IOFBF, 1 << 20);
    if (clog_path && !(clog = fopen(clog_path, "w"))) die("cannot write commit log");
    if (clog) setvbuf(clog, NULL, _IOFBF, 1 << 20);
    double t0 = now();
    u64 start = count, wfi_entries = 0, marker_index = 0, trap_streak = 0;
    char path[4096];
    const char *why = "budget";
    for (;;) {
        while (next_dump < ndumps && dumps[next_dump] < count) next_dump++;
        if (next_dump < ndumps && dumps[next_dump] == count) {
            snprintf(path, sizeof path, "%s%" PRIu64 ".state", dump_prefix, count);
            write_sys_state(path);
            next_dump++;
            continue;
        }
        if (count >= max) break;
        if (sys_stop >= 0) break;
        if (time_spike) {
            if (chunk_steps >= 5000) spike_chunk_end();
            if (irq_check) {
                irq_check = 0;
                if (check_interrupts()) continue;
            }
            if (in_wfi) {
                /* A chunk passes with no instruction. When only the timer can wake the hart, the chunks that
                 * end below mtimecmp (each adds 50 ticks and changes nothing else) are skipped at once. */
                if (u_in_pos >= u_in_len && !(mip_read() & mie)) {
                    if (!(mie & IP_MTIP) || mtimecmp == ~(u64)0) { sys_stop = SX_WFI_DEADLOCK; break; }
                    if (mtimecmp > mtime + 50) {
                        u64 k = (mtimecmp - mtime - 1) / 50;
                        mtime += 50 * k;
                        idle_ticks += 50 * k;
                    }
                }
                chunk_steps = 5000; idle_ticks += 50; continue;
            }
        } else {
            if (count % 5000 == 0 && uart_wants_input()) uart_push_input();
            if (irq_check) {
                irq_check = 0;
                if (check_interrupts()) continue;
            }
            if (in_wfi) {
                /* Nothing pending and enabled: deliver scripted UART input if it can wake the hart, else jump
                 * mtime to mtimecmp when the timer can wake it. */
                wfi_entries++;
                if (mip_read() & mie) { in_wfi = 0; irq_check = 1; continue; }
                int n0 = u_rxn;
                if (uart_wants_input()) uart_push_input();
                if (u_rxn != n0) { irq_check = 1; if (mip_read() & mie) continue; }
                if ((mie & IP_MTIP) && mtimecmp > mtime && mtimecmp != ~(u64)0) {
                    idle_ticks += mtimecmp - mtime; mtime = mtimecmp; tick_accum = 0; clint_tick(); irq_check = 1; continue;
                }
                sys_stop = SX_WFI_DEADLOCK;
                break;
            }
        }
        u64 c0 = count;
        sys_step();
        if (count != c0) trap_streak = 0;
        else if (!in_wfi && ++trap_streak > 1000000) { sys_stop = SX_TRAPLOOP; break; }
        if (out_marker_hit == 1) {
            snprintf(path, sizeof path, "%smarker.state", dump_prefix);
            write_sys_state(path);
            marker_index = count;
            out_marker_hit = 2;
        }
    }
    double t1 = now();
    if (trace_fd && fclose(trace_fd)) die("trace write failed");
    if (adopt_path && adopt_i != adopt_n) die("--adopt: N records left unused (the runs took different paths)");
    if (clog && fclose(clog)) die("commit log write failed");
    if (final_state) write_sys_state(final_state);
    fflush(uart_out);
    if (sys_stop == SX_TOHOST) why = "tohost";
    else if (sys_stop == SX_FINISHER) why = "finisher";
    else if (sys_stop == SX_WFI_DEADLOCK) why = "wfi_deadlock";
    else if (sys_stop == SX_TRAPLOOP) why = "trap_loop";
    double secs = t1 - t0;
    printf("%s{\"mode\": \"sys\", \"instructions\": %" PRIu64 ", \"start_index\": %" PRIu64 ", \"stop\": \"%s\", "
           "\"exit_code\": %" PRIu64 ", \"pc\": %" PRIu64 ", \"prv\": %d, \"mtime\": %" PRIu64 ", \"idle_ticks\": %" PRIu64
           ", \"uart_bytes\": %" PRIu64 ", \"marker_state_index\": %" PRIu64 ", \"seconds\": %.3f, \"mips\": %.3f}\n",
           uart_bytes && uart_out == stdout ? "\n" : "", count, start, why, sys_exit_code, pc, prv, mtime, idle_ticks,
           uart_bytes, marker_index, secs, secs > 0 ? (double)(count - start) / secs / 1e6 : 0.0);
    (void)wfi_entries;
    return 0;
}
#endif

#ifndef RV_ISS_NO_MAIN
int main(int argc, char **argv) {
    const char *image = NULL, *state = NULL, *trace = NULL, *final_memory = NULL, *final_state = NULL, *clog_path = NULL;
    u64 max = (u64)1 << 62;
    for (int i = 1; i < argc; i++) {
        const char *k = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) die("option without a value");
        i++;
        if (!strcmp(k, "--ram")) ram = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--image")) image = v;
        else if (!strcmp(k, "--state")) state = v;
        else if (!strcmp(k, "--mailbox")) mailbox = strtoull(v, NULL, 16);
        else if (!strcmp(k, "--max")) max = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--dump-at")) parse_dumps(v);
        else if (!strcmp(k, "--dump-prefix")) dump_prefix = v;
        else if (!strcmp(k, "--trace")) trace = v;
        else if (!strcmp(k, "--trace-from")) trace_from = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--trace-to")) trace_to = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--final-memory")) final_memory = v;
        else if (!strcmp(k, "--final-state")) final_state = v;
        else if (!strcmp(k, "--warm-caches")) warm_init(v);
        else if (!strcmp(k, "--fp")) fp_on = (int)strtol(v, NULL, 0);
        else if (!strcmp(k, "--fp-soft")) fp_soft = (int)strtol(v, NULL, 0);
        else if (!strcmp(k, "--host-fz")) host_fz = (int)strtol(v, NULL, 0);
        else if (!strcmp(k, "--sys")) sys_on = (int)strtol(v, NULL, 0);
        else if (!strcmp(k, "--elf")) sys_elf = v;
        else if (!strcmp(k, "--dtb")) sys_dtb = v;
        else if (!strcmp(k, "--bin")) { if (sys_nbins == 8) die("too many --bin"); sys_bins[sys_nbins++] = v; }
        else if (!strcmp(k, "--time")) { if (!strcmp(v, "spike")) time_spike = 1; else if (strcmp(v, "lab")) die("--time lab|spike"); }
        else if (!strcmp(k, "--commit-log")) clog_path = v;
        else if (!strcmp(k, "--commit-from")) clog_from = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--commit-to")) clog_to = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--uart-in")) uart_in_path = v;
        else if (!strcmp(k, "--uart-out")) uart_out_path = v;
        else if (!strcmp(k, "--marchid")) marchid_val = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--adopt")) adopt_path = v;
        else if (!strcmp(k, "--isa")) sys_isa = v;
        else if (!strcmp(k, "--priv")) sys_priv = v;
        else if (!strcmp(k, "--dump-on-output")) out_marker = v;
        else die("unknown option");
    }
    if (!sys_on && (sys_elf || sys_dtb || sys_nbins || time_spike || clog_path || uart_in_path || uart_out_path ||
                    marchid_val || adopt_path || out_marker || sys_isa || sys_priv || clog_from || clog_to != ~(u64)0))
        die("system-mode options need --sys 1");
    if (sys_on) {
        if (!ram || (ram & 7) || image) die("--sys needs --ram and takes --elf/--bin/--state, not --image");
        set_isa(sys_isa, sys_priv);
        if (!fp_on) fp_on = 1;
        return sys_main(state, trace, final_state, max, clog_path);
    }
    if (!ram || (ram & 7) || (!image == !state)) die("need --ram and one of --image / --state");
    mem = calloc(1, ram + 8); /* +8: an aligned 4-byte fetch or load never reads past the end */
#ifdef FP_HW
    if (host_fz) {
        /* Test hook: start from a host FPCR with flush-to-zero on (FZ = 1, AH = 0), as another program or
         * runtime might leave it; every hardware path must still give exact RISC-V results. */
        u64 c;
        __asm__ volatile("mrs %0, fpcr" : "=r"(c));
        c = (c | (u64)1 << 24) & ~(u64)2;
        __asm__ volatile("msr fpcr, %0" :: "r"(c));
    }
#endif
    if (!mem) die("out of memory");
    if (image) {
        FILE *f = fopen(image, "rb");
        if (!f) die("cannot read image");
        size_t n = fread(mem, 1, ram, f);
        if (!feof(f) && fgetc(f) != EOF) die("image larger than --ram");
        fclose(f);
        (void)n;
    } else read_state(state);
    if (trace && !(trace_fd = fopen(trace, "w"))) die("cannot write trace");
    if (trace_fd) setvbuf(trace_fd, NULL, _IOFBF, 1 << 20);
    double t0 = now();
    u64 start = count;
    char path[4096];
    for (;;) {
        while (next_dump < ndumps && dumps[next_dump] < count) next_dump++;
        u64 limit = next_dump < ndumps ? dumps[next_dump] : max;
        if (limit > max) limit = max;
        if (count == limit) {
            if (next_dump < ndumps && dumps[next_dump] == count) {
                snprintf(path, sizeof path, "%s%" PRIu64 ".state", dump_prefix, count);
                write_state(path);
                if (warm) {
                    snprintf(path, sizeof path, "%s%" PRIu64 ".l2", dump_prefix, count);
                    write_l2(path);
                }
                next_dump++;
                continue;
            }
            stop_cause = -2; /* instruction budget */
            break;
        }
        if (trace_fd) {
            while (count < limit && step()) {}
        } else {
            while (count < limit && step()) {}
        }
        if (stop_cause != -1) break;
    }
    double t1 = now();
    if (stop_cause >= 0 && tracing())
        fprintf(trace_fd, "T %016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n", pc, (u64)stop_cause, stop_tval);
    if (trace_fd && fclose(trace_fd)) die("trace write failed");
    if (final_memory) {
        FILE *f = fopen(final_memory, "wb");
        if (!f || fwrite(mem, 1, ram, f) != ram || fclose(f)) die("final memory write failed");
    }
    if (final_state) write_state(final_state);
    printf("{\"instructions\": %" PRIu64 ", \"start_index\": %" PRIu64 ", ", count, start);
    if (stop_cause == -2) printf("\"stop\": \"budget\", ");
    else printf("\"stop\": {\"pc\": %" PRIu64 ", \"cause\": %d, \"tval\": %" PRIu64 "}, ", pc, stop_cause, stop_tval);
    printf("\"marks\": [");
    for (int i = 0; i < nmarks && i < MAX_MARKS; i++)
        printf("%s[%" PRIu64 ", %" PRIu64 "]", i ? ", " : "", mark_value[i], mark_index[i]);
    printf("], \"marks_total\": %d, \"mailbox\": {", nmarks);
    int first = 1;
    for (int i = 1; i < 32; i++)
        if (mbox_seen >> i & 1) { printf("%s\"%d\": %" PRIu64, first ? "" : ", ", i, mbox_words[i]); first = 0; }
    double secs = t1 - t0;
    printf("}, \"seconds\": %.3f, \"mips\": %.3f}\n", secs, secs > 0 ? (double)(count - start) / secs / 1e6 : 0.0);
    return 0;
}
#endif
