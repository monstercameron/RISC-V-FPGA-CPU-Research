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

static int fp_on, fp_soft;
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
int main(int argc, char **argv) {
    const char *image = NULL, *state = NULL, *trace = NULL, *final_memory = NULL, *final_state = NULL;
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
        else die("unknown option");
    }
    if (!ram || (ram & 7) || (!image == !state)) die("need --ram and one of --image / --state");
    mem = calloc(1, ram + 8); /* +8: an aligned 4-byte fetch or load never reads past the end */
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
