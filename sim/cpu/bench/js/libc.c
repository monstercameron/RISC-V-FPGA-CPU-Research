/* SPDX-License-Identifier: MIT
 * Minimal freestanding libc for the bare-metal QuickJS-ng benchmark on the RV64 cores
 * (run_bench.py --benchmark js; original code, from the 2026-11-22 research prototype).
 *
 * Provides exactly what quickjs.c, libregexp.c, libunicode.c and dtoa.c link against
 * (51 symbols, measured with llvm-nm on QuickJS-ng v0.18.0): memory and string routines,
 * a size-class allocator over one arena, a small vsnprintf, strtod (through QuickJS's own
 * correctly rounded js_atod), exact floor/ceil/trunc/fmod/frexp/scalbn/lrint, sqrt through
 * the FPU, a fixed clock (time 0, so runs are deterministic) and UTC localtime.
 * Transcendental functions (sin, exp, log, pow, ...) are not implemented: they stop the
 * run with a recorded reason, so a kernel that needs them is detected instead of giving a
 * libm-dependent checksum.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
#include <time.h>
#include <sys/time.h>

typedef struct FILE FILE;
struct FILE { int fd; };
static FILE f_out = {1}, f_err = {2}, f_in = {0};
FILE *stdout = &f_out, *stderr = &f_err, *stdin = &f_in;
int errno;

/* ---- output sink: the harness hashes everything written ---- */
void shim_write(int fd, const char *p, size_t n);   /* provided by the harness */
_Noreturn void shim_stop(const char *why);          /* provided by the harness */

/* ---- memory and strings ---- */
typedef uint64_t __attribute__((may_alias)) w64;
void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *o = d; const unsigned char *i = s;
    if ((((uintptr_t)o ^ (uintptr_t)i) & 7) == 0) {
        while (n && ((uintptr_t)o & 7)) { *o++ = *i++; n--; }
        w64 *wo = (w64 *)o; const w64 *wi = (const w64 *)i;
        while (n >= 32) { wo[0] = wi[0]; wo[1] = wi[1]; wo[2] = wi[2]; wo[3] = wi[3]; wo += 4; wi += 4; n -= 32; }
        while (n >= 8) { *wo++ = *wi++; n -= 8; }
        o = (unsigned char *)wo; i = (const unsigned char *)wi;
    }
    while (n--) *o++ = *i++;
    return d;
}
void *memmove(void *d, const void *s, size_t n) {
    unsigned char *o = d; const unsigned char *i = s;
    if (o <= i || o >= i + n) return memcpy(d, s, n);
    o += n; i += n;
    while (n--) *--o = *--i;
    return d;
}
void *memset(void *d, int v, size_t n) {
    unsigned char *o = d, b = (unsigned char)v;
    while (n && ((uintptr_t)o & 7)) { *o++ = b; n--; }
    uint64_t w = 0x0101010101010101ull * b; w64 *wo = (w64 *)o;
    while (n >= 8) { *wo++ = w; n -= 8; }
    o = (unsigned char *)wo;
    while (n--) *o++ = b;
    return d;
}
int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *x = a, *y = b;
    for (; n; n--, x++, y++) if (*x != *y) return *x - *y;
    return 0;
}
void *memchr(const void *s, int c, size_t n) {
    const unsigned char *p = s;
    for (; n; n--, p++) if (*p == (unsigned char)c) return (void *)p;
    return 0;
}
size_t strlen(const char *s) { const char *p = s; while (*p) p++; return (size_t)(p - s); }
int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}
char *strchr(const char *s, int c) {
    for (;; s++) { if (*s == (char)c) return (char *)s; if (!*s) return 0; }
}
char *strrchr(const char *s, int c) {
    const char *r = 0;
    for (;; s++) { if (*s == (char)c) r = s; if (!*s) return (char *)r; }
}
char *strstr(const char *h, const char *n) {
    size_t k = strlen(n);
    if (!k) return (char *)h;
    for (; *h; h++) if (*h == *n && memcmp(h, n, k) == 0) return (char *)h;
    return 0;
}

/* ---- allocator: 16-byte header, power-of-two-ish size classes with free lists ---- */
static unsigned char *heap_next, *heap_end;
static void *free_list[240];
uint64_t shim_heap_peak;
void shim_heap_init(void *base, size_t size) {
    heap_next = (unsigned char *)(((uintptr_t)base + 15) & ~(uintptr_t)15);
    heap_end = (unsigned char *)base + size;
}
static unsigned size_class(size_t n, size_t *cap) {
    /* classes: 16..256 step 16 (0-15), then 4 per power of two up to 2^47 */
    if (n <= 256) { unsigned c = (unsigned)((n + 15) >> 4); if (c == 0) c = 1; *cap = (size_t)c << 4; return c - 1; }
    unsigned lg = 63 - (unsigned)__builtin_clzll(n - 1);       /* n-1 >= 256, lg >= 8 */
    size_t q = (size_t)1 << (lg - 2);
    size_t c = ((n - 1) >> (lg - 2)) + 1;                      /* 5..8 quarters of 2^(lg) / 2 */
    *cap = c * q;
    return 16 + (lg - 8) * 4 + (unsigned)(c - 5);
}
void *malloc(size_t n) {
    size_t cap; unsigned c = size_class(n ? n : 1, &cap);
    if (c >= 240) return 0;
    uint64_t *h;
    if (free_list[c]) { h = free_list[c]; free_list[c] = *(void **)(h + 2); }
    else {
        if ((size_t)(heap_end - heap_next) < cap + 16) return 0;
        h = (uint64_t *)heap_next; heap_next += cap + 16;
        if ((uint64_t)(uintptr_t)heap_next > shim_heap_peak) shim_heap_peak = (uintptr_t)heap_next;
        h[0] = cap; h[1] = c;
    }
    return h + 2;
}
void free(void *p) {
    if (!p) return;
    uint64_t *h = (uint64_t *)p - 2;
    *(void **)p = free_list[h[1]]; free_list[h[1]] = h;
}
size_t malloc_usable_size(void *p) { return p ? ((uint64_t *)p - 2)[0] : 0; }
void *calloc(size_t a, size_t b) {
    size_t n = a * b; void *p = malloc(n);
    if (p) memset(p, 0, n);
    return p;
}
void *realloc(void *p, size_t n) {
    if (!p) return malloc(n);
    if (!n) { free(p); return 0; }
    size_t have = malloc_usable_size(p);
    if (n <= have) return p;
    void *q = malloc(n);
    if (q) { memcpy(q, p, have); free(p); }
    return q;
}

_Noreturn void abort(void) { shim_stop("abort"); }
_Noreturn void __shim_assert(const char *e, const char *f, int l) { (void)e; (void)f; (void)l; shim_stop("assert"); }

/* ---- formatted output ---- */
typedef struct { char *buf; size_t cap, len; } Out;
static void out_c(Out *o, char c) { if (o->len + 1 < o->cap) o->buf[o->len] = c; o->len++; }
static void out_s(Out *o, const char *s, size_t n) { while (n--) out_c(o, *s++); }
static void out_u(Out *o, unsigned long long v, unsigned base, int upper, int width, char pad, int neg) {
    char t[24]; int n = 0; const char *dig = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    do { t[n++] = dig[v % base]; v /= base; } while (v);
    if (neg) t[n++] = '-';
    while (width > n) { out_c(o, pad); width--; }
    while (n) out_c(o, t[--n]);
}
int vsnprintf(char *buf, size_t cap, const char *f, va_list ap) {
    Out o = {buf, cap, 0};
    for (; *f; f++) {
        if (*f != '%') { out_c(&o, *f); continue; }
        f++;
        char pad = ' '; int width = 0, prec = -1, lng = 0;
        while (*f == '-' || *f == '+' || *f == ' ' || *f == '#' || *f == '0') { if (*f == '0') pad = '0'; f++; }
        if (*f == '*') { width = va_arg(ap, int); f++; } else while (*f >= '0' && *f <= '9') width = width * 10 + (*f++ - '0');
        if (*f == '.') { f++; prec = 0; if (*f == '*') { prec = va_arg(ap, int); f++; } else while (*f >= '0' && *f <= '9') prec = prec * 10 + (*f++ - '0'); }
        while (*f == 'l' || *f == 'z' || *f == 'h' || *f == 'j' || *f == 't') { if (*f != 'h') lng++; f++; }
        switch (*f) {
        case 'd': case 'i': {
            long long v = lng ? va_arg(ap, long long) : va_arg(ap, int);
            out_u(&o, v < 0 ? 0ull - (unsigned long long)v : (unsigned long long)v, 10, 0, width, pad, v < 0); break; }
        case 'u': case 'x': case 'X': case 'o': {
            unsigned long long v = lng ? va_arg(ap, unsigned long long) : va_arg(ap, unsigned);
            out_u(&o, v, *f == 'u' ? 10 : *f == 'o' ? 8 : 16, *f == 'X', width, pad, 0); break; }
        case 'p': out_s(&o, "0x", 2); out_u(&o, (uintptr_t)va_arg(ap, void *), 16, 0, 0, ' ', 0); break;
        case 'c': out_c(&o, (char)va_arg(ap, int)); break;
        case 's': {
            const char *s = va_arg(ap, const char *); if (!s) s = "(null)";
            size_t n = strlen(s); if (prec >= 0 && (size_t)prec < n) n = (size_t)prec;
            while (width > (int)n) { out_c(&o, ' '); width--; }
            out_s(&o, s, n); break; }
        case 'g': case 'f': case 'e': (void)va_arg(ap, double); out_s(&o, "<fp>", 4); break;
        case '%': out_c(&o, '%'); break;
        default: out_c(&o, '?'); break;
        }
    }
    if (cap) buf[o.len < cap ? o.len : cap - 1] = 0;
    return (int)o.len;
}
int snprintf(char *b, size_t n, const char *f, ...) { va_list ap; va_start(ap, f); int r = vsnprintf(b, n, f, ap); va_end(ap); return r; }
static int vfput(FILE *fp, const char *f, va_list ap) {
    char t[512]; int n = vsnprintf(t, sizeof t, f, ap);
    shim_write(fp->fd, t, (size_t)(n < (int)sizeof t ? n : (int)sizeof t - 1));
    return n;
}
int fprintf(FILE *fp, const char *f, ...) { va_list ap; va_start(ap, f); int r = vfput(fp, f, ap); va_end(ap); return r; }
int printf(const char *f, ...) { va_list ap; va_start(ap, f); int r = vfput(stdout, f, ap); va_end(ap); return r; }
int fputc(int c, FILE *fp) { char ch = (char)c; shim_write(fp->fd, &ch, 1); return c; }
size_t fwrite(const void *p, size_t a, size_t b, FILE *fp) { shim_write(fp->fd, p, a * b); return b; }

/* ---- numbers ---- */
typedef struct { uint64_t mem[27]; } JSATODTempMem;
double js_atod(const char *str, const char **pnext, int radix, int flags, JSATODTempMem *tmp);
double strtod(const char *s, char **end) {
    JSATODTempMem t; const char *e;
    double d = js_atod(s, &e, 10, 0, &t);
    if (end) *end = (char *)e;
    return d;
}
static inline uint64_t bits(double d) { union { double d; uint64_t u; } v = {d}; return v.u; }
static inline double dbl(uint64_t u) { union { uint64_t u; double d; } v = {u}; return v.d; }
double fabs(double x) { return dbl(bits(x) & ~(1ull << 63)); }
#ifdef __riscv_d
double sqrt(double x) { double r; __asm__("fsqrt.d %0, %1" : "=f"(r) : "f"(x)); return r; }
#else
/* soft-float build: correctly rounded (RNE) square root by integer digit recurrence */
double sqrt(double x) {
    uint64_t u = bits(x);
    if (x != x || x == 0 || (u >> 63)) return (u >> 63) && x != 0 ? (x - x) / (x - x) : x;
    int e = (int)((u >> 52) & 0x7ff); uint64_t m = u & ((1ull << 52) - 1);
    if (e == 0x7ff) return x;
    if (e == 0) { while (!(m >> 52)) { m <<= 1; e--; } e++; } else m |= 1ull << 52;
    e -= 1023;
    if (e & 1) { m <<= 1; e--; }                      /* now x = m * 2^(e-52), e even */
    /* root of m * 2^62 (m < 2^54) gives 57+ bits: r = floor(sqrt(m << 62)) */
    unsigned __int128 v = (unsigned __int128)m << 62, rem = 0, root = 0;
    for (int i = 0; i < 58; i++) {
        rem = (rem << 2) | (uint64_t)(v >> 114); v <<= 2;
        unsigned __int128 t = (root << 2) | 1; root <<= 1;
        if (rem >= t) { rem -= t; root |= 1; }
    }
    /* root has 58 bits with 5 extra below the 53-bit significand */
    uint64_t r = (uint64_t)root, keep = r >> 5, low = r & 31; int sticky = rem != 0;
    if (low > 16 || (low == 16 && (sticky || (keep & 1)))) keep++;
    if (keep >> 53) { keep >>= 1; e += 2; }
    return dbl(((uint64_t)(e / 2 + 1023) << 52) | (keep & ((1ull << 52) - 1)));
}
#endif
double trunc(double x) {
    uint64_t u = bits(x); int e = (int)((u >> 52) & 0x7ff) - 1023;
    if (e >= 52) return x;                       /* integral, inf or NaN */
    if (e < 0) return dbl(u & (1ull << 63));     /* |x| < 1: signed zero */
    return dbl(u & ~((1ull << (52 - e)) - 1));
}
double floor(double x) { double t = trunc(x); return (t != x && x < 0) ? t - 1.0 : t; }
double ceil(double x) { double t = trunc(x); return (t != x && x > 0) ? t + 1.0 : t; }
#ifdef __riscv_d
long lrint(double x) { long r; __asm__("fcvt.l.d %0, %1, rne" : "=r"(r) : "f"(x)); return r; }
#else
long lrint(double x) {   /* round half to even, as the default rounding mode */
    double t = trunc(x), f = x - t;
    if (f > 0.5 || (f == 0.5 && ((long)t & 1))) t += 1.0;
    else if (f < -0.5 || (f == -0.5 && ((long)t & 1))) t -= 1.0;
    return (long)t;
}
#endif
double scalbn(double x, int n) {
    /* exact for results in the normal range; the subnormal and overflow edges go through
       multiplication by powers of two, which rounds once as libm does */
    while (n > 1023) { x *= 0x1p1023; n -= 1023; if (n <= 1023) break; }
    while (n < -1022) { x *= 0x1p-1022; n += 1022; if (n >= -1022) break; }
    return x * dbl((uint64_t)(n + 1023) << 52);
}
double frexp(double x, int *e) {
    uint64_t u = bits(x); int ex = (int)((u >> 52) & 0x7ff);
    if (ex == 0) { if (x == 0) { *e = 0; return x; } x *= 0x1p64; u = bits(x); ex = (int)((u >> 52) & 0x7ff) - 64; }
    else if (ex == 0x7ff) { *e = 0; return x; }
    *e = ex - 1022;
    return dbl((u & ~(0x7ffull << 52)) | (1022ull << 52));
}
double fmod(double x, double y) {
    /* exact remainder by binary long division on the significands */
    uint64_t ux = bits(x), uy = bits(y), sx = ux & (1ull << 63);
    int ex = (int)((ux >> 52) & 0x7ff), ey = (int)((uy >> 52) & 0x7ff);
    if ((uy << 1) == 0 || ex == 0x7ff || (ey == 0x7ff && (uy << 12))) return (x * y) / (x * y);
    if ((ux << 1) <= (uy << 1)) return (ux << 1) == (uy << 1) ? x * 0.0 : x;
    uint64_t mx, my;
    if (!ex) { for (uint64_t i = ux << 12; i >> 63 == 0; ex--, i <<= 1) {} mx = ux << (-ex + 1); }
    else mx = (ux & ((1ull << 52) - 1)) | (1ull << 52);
    if (!ey) { for (uint64_t i = uy << 12; i >> 63 == 0; ey--, i <<= 1) {} my = uy << (-ey + 1); }
    else my = (uy & ((1ull << 52) - 1)) | (1ull << 52);
    for (; ex > ey; ex--) { if (mx >= my) mx -= my; mx <<= 1; }
    if (mx >= my) mx -= my;
    if (mx == 0) return x * 0.0;
    for (; mx >> 52 == 0; mx <<= 1, ex--) {}
    if (ex > 0) mx = (mx - (1ull << 52)) | ((uint64_t)ex << 52);
    else mx >>= -ex + 1;
    return dbl(mx | sx);
}

#define UNIMPL1(name) double name(double x) { (void)x; shim_stop(#name); }
#define UNIMPL2(name) double name(double x, double y) { (void)x; (void)y; shim_stop(#name); }
UNIMPL1(sin) UNIMPL1(cos) UNIMPL1(tan) UNIMPL1(asin) UNIMPL1(acos) UNIMPL1(atan) UNIMPL1(sinh) UNIMPL1(cosh)
UNIMPL1(tanh) UNIMPL1(asinh) UNIMPL1(acosh) UNIMPL1(atanh) UNIMPL1(exp) UNIMPL1(expm1) UNIMPL1(log) UNIMPL1(log2)
UNIMPL1(log10) UNIMPL1(log1p) UNIMPL1(cbrt) UNIMPL2(atan2) UNIMPL2(hypot) UNIMPL2(pow)

/* ---- time: a fixed clock so every run is identical ---- */
int gettimeofday(struct timeval *tv, void *tz) { (void)tz; tv->tv_sec = 0; tv->tv_usec = 0; return 0; }
struct tm *localtime_r(const time_t *t, struct tm *r) {
    long s = (long)*t, days = s / 86400, rem = s % 86400;
    if (rem < 0) { rem += 86400; days--; }
    r->tm_hour = (int)(rem / 3600); r->tm_min = (int)(rem / 60 % 60); r->tm_sec = (int)(rem % 60);
    r->tm_wday = (int)(((days + 4) % 7 + 7) % 7);
    /* civil-from-days (proleptic Gregorian) */
    long z = days + 719468, era = (z >= 0 ? z : z - 146096) / 146097;
    unsigned doe = (unsigned)(z - era * 146097), yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    long y = (long)yoe + era * 400; unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100), mp = (5 * doy + 2) / 153;
    unsigned d = doy - (153 * mp + 2) / 5 + 1, m = mp < 10 ? mp + 3 : mp - 9;
    y += m <= 2;
    r->tm_year = (int)(y - 1900); r->tm_mon = (int)m - 1; r->tm_mday = (int)d; r->tm_yday = 0; r->tm_isdst = 0;
    r->tm_gmtoff = 0; r->tm_zone = "UTC";
    return r;
}

double round(double x) {   /* half away from zero */
    double t = trunc(x), f = x - t;
    if (f >= 0.5) t += 1.0; else if (f <= -0.5) t -= 1.0;
    return t;
}

#ifndef __riscv_d
/* Soft-float conversions missing from the vendored compiler-rt subset (original code). In-range
   inputs give C's results; out-of-range inputs, undefined in C, are not relied on by QuickJS. */
long long __fixdfdi(double);
int __fixdfsi(double x) { return (int)__fixdfdi(x); }
/* standalone: compiler-rt's __fixdfdi itself calls __fixunsdfdi on this target */
unsigned long long __fixunsdfdi(double x) {
    uint64_t u = bits(x); int e = (int)((u >> 52) & 0x7ff) - 1023;
    if ((u >> 63) || e < 0) return 0;                 /* negative, NaN with sign, or below 1 */
    if (e >= 64) return ~0ull;                         /* too large, inf, NaN */
    uint64_t m = (u & ((1ull << 52) - 1)) | (1ull << 52);
    return e >= 52 ? m << (e - 52) : m >> (52 - e);
}
unsigned __fixunsdfsi(double x) { return (unsigned)__fixunsdfdi(x); }
float __truncdfsf2(double x) {   /* binary64 to binary32, round to nearest even */
    uint64_t u = bits(x); uint32_t s = (uint32_t)(u >> 63) << 31, r;
    int e = (int)((u >> 52) & 0x7ff); uint64_t m = u & ((1ull << 52) - 1);
    if (e == 0x7ff) r = s | 0x7f800000u | (m ? 0x400000u | (uint32_t)(m >> 29) : 0);
    else {
        int fe = e - 1023 + 127;                      /* biased single exponent */
        if (e == 0 && m == 0) r = s;
        else {
            uint64_t sig = (e ? m | (1ull << 52) : m << 1);  /* 53 bits, value sig * 2^(e-1075) */
            int shift = 29;                           /* 53 -> 24 bits */
            if (fe <= 0) { shift += 1 - fe; fe = 0; }  /* subnormal single */
            uint64_t keep, rem, half;
            if (shift >= 64) { keep = 0; rem = sig; half = ~0ull; }
            else { keep = sig >> shift; rem = sig & ((1ull << shift) - 1); half = 1ull << (shift - 1); }
            if (rem > half || (rem == half && (keep & 1))) keep++;
            /* keep: 24-bit significand with implicit bit (normal) or the subnormal field */
            if (fe == 0) r = s | (uint32_t)keep;     /* carry into bit 23 makes it the smallest normal */
            else {
                if (keep >> 24) { keep >>= 1; fe++; }
                r = fe >= 255 ? s | 0x7f800000u : s | ((uint32_t)fe << 23) | ((uint32_t)keep & 0x7fffff);
            }
        }
    }
    union { uint32_t u; float f; } v = {r};
    return v.f;
}
#endif
