/* SPDX-License-Identifier: MIT
 * Portable math for the ray-tracing benchmark; see include-rt/rt_math.h.
 * Original code. The reduction constant is pi/2 split into a 33-bit head and
 * a tail (the usual Cody-Waite pair); the polynomials are Taylor series.
 */
#include "rt_math.h"

typedef unsigned long long u64;

static inline u64 bits_of(double x) {
    union { double d; u64 u; } v;
    v.d = x;
    return v.u;
}

static inline double double_of(u64 u) {
    union { double d; u64 u; } v;
    v.u = u;
    return v.d;
}

double rt_fabs(double x) { return double_of(bits_of(x) & ~(1ull << 63)); }

#if (defined(__riscv_d) || defined(__aarch64__) || defined(__x86_64__)) && !defined(RT_SOFT_SQRT)
/* IEEE square root is correctly rounded, so hardware and the software path agree. */
double rt_sqrt(double x) { return __builtin_sqrt(x); }
#else
/* Correctly rounded (round to nearest even) square root with integer operations only. */
double rt_sqrt(double x) {
    const u64 ix = bits_of(x);
    if (ix >> 63) return (ix << 1) == 0 ? x : double_of(0x7ff8000000000000ull); /* -0 stays -0 */
    const unsigned e = (unsigned)(ix >> 52);
    if (e == 0x7ff) return x; /* +inf, NaN */
    if (ix == 0) return x;
    u64 m;
    int exp;
    if (e == 0) { /* subnormal: normalize */
        m = ix;
        exp = -1022;
        while (!(m & (1ull << 52))) {
            m <<= 1;
            exp--;
        }
    } else {
        m = (ix & ((1ull << 52) - 1)) | (1ull << 52);
        exp = (int)e - 1023;
    }
    /* x = m * 2^(exp-52); make exp even, then m in [2^52, 2^54) */
    if (exp & 1) {
        m <<= 1;
        exp--;
    }
    /* q = floor(sqrt(m * 2^54)), in [2^53, 2^54): 53 result bits and a round bit.
     * Digit by digit, two bits of m * 2^54 per step: 27 pairs from m (a 54-bit
     * field), then 27 zero pairs. rem < 2 * root + 1 < 2^55, so 64 bits suffice. */
    u64 rem = 0, root = 0;
    for (int i = 0; i < 54; i++) {
        const u64 pair = i < 27 ? (m >> (52 - 2 * i)) & 3 : 0;
        rem = (rem << 2) | pair;
        root <<= 1;
        const u64 test = (root << 1) | 1;
        if (rem >= test) {
            rem -= test;
            root |= 1;
        }
    }
    u64 q = root;
    const int round = (int)(q & 1), sticky = rem != 0;
    u64 mant = q >> 1;
    if (round && (sticky || (mant & 1))) mant++;
    int biased = exp / 2 + 1023;
    if (mant >> 53) {
        mant >>= 1;
        biased++;
    }
    return double_of(((u64)biased << 52) | (mant & ((1ull << 52) - 1)));
}
#endif

/* pi/2 = PIO2_HI + PIO2_LO; PIO2_HI has 33 significant bits, so k * PIO2_HI is exact for |k| < 2^20. */
static const double PIO2_HI = 1.57079632673412561417e+00;
static const double PIO2_LO = 6.07710050650619224932e-11;
static const double INV_PIO2 = 6.36619772367581382433e-01;

/* sin(r) and cos(r) for |r| <= pi/4 (plus the reduction error): Taylor series to r^17 / r^18. */
static double sin_poly(double r) {
    const double z = r * r;
    double p = 2.8114572543455206e-15;
    p = p * z - 7.647163731819816e-13;
    p = p * z + 1.6059043836821613e-10;
    p = p * z - 2.505210838544172e-08;
    p = p * z + 2.755731922398589e-06;
    p = p * z - 1.984126984126984e-04;
    p = p * z + 8.333333333333333e-03;
    p = p * z - 1.6666666666666666e-01;
    return r + r * z * p;
}

static double cos_poly(double r) {
    const double z = r * r;
    double p = -1.5619206968586225e-16;
    p = p * z + 4.779477332387385e-14;
    p = p * z - 1.1470745597729725e-11;
    p = p * z + 2.08767569878681e-09;
    p = p * z - 2.755731922398589e-07;
    p = p * z + 2.48015873015873e-05;
    p = p * z - 1.388888888888889e-03;
    p = p * z + 4.1666666666666664e-02;
    return 1.0 - 0.5 * z + z * z * p;
}

/* Quadrant k (mod 4) and remainder r of x / (pi/2); valid for |x| below about 1e6. */
static double reduce(double x, int *quadrant) {
    const double fk = x * INV_PIO2;
    const long long k = (long long)(fk >= 0 ? fk + 0.5 : fk - 0.5);
    const double dk = (double)k;
    *quadrant = (int)(k & 3);
    return (x - dk * PIO2_HI) - dk * PIO2_LO;
}

double rt_sin(double x) {
    int q;
    const double r = reduce(x, &q);
    switch (q) {
    case 0: return sin_poly(r);
    case 1: return cos_poly(r);
    case 2: return -sin_poly(r);
    default: return -cos_poly(r);
    }
}

double rt_cos(double x) {
    int q;
    const double r = reduce(x, &q);
    switch (q) {
    case 0: return cos_poly(r);
    case 1: return -sin_poly(r);
    case 2: return -cos_poly(r);
    default: return sin_poly(r);
    }
}
