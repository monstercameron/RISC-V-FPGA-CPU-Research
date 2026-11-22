/* SPDX-License-Identifier: MIT
 * mm benchmark kernels, scalar C (see mm_bench.h for the definitions). Build
 * with -ffp-contract=off: every FP result must be the unfused one.
 */
#include "mm_bench.h"

/* Hardware float converts with one instruction; the soft-float build converts by integer code (the compiler would
 * call __floatsisf, which the vendored compiler-rt subset lacks). */
#ifdef __riscv_float_abi_soft
#define MM_CONVERT(v) mm_i2f(v)
#else
#define MM_CONVERT(v) ((float)(v))
#endif

typedef union { float f; mm_u32 u; } mm_fbits;

static float bits_to_float(mm_u32 u) { mm_fbits v; v.u = u; return v.f; }
static mm_u32 float_to_bits(float f) { mm_fbits v; v.f = f; return v.u; }

void mm_gemm_i8(mm_i32 *c, const mm_i8 *a, const mm_i8 *bt) {
    for (unsigned i = 0; i < MM_G; i++)
        for (unsigned j = 0; j < MM_G; j++) {
            mm_i32 s = 0;
            const mm_i8 *p = a + i * MM_G, *q = bt + j * MM_G;
            for (unsigned k = 0; k < MM_G; k++) s += (mm_i32)p[k] * q[k];
            c[i * MM_G + j] = s;
        }
}

/* BF16 is the upper half of an FP32; the product of two is exact in FP32. */
static float bf16_to_f32(mm_u16 h) { return bits_to_float((mm_u32)h << 16); }

void mm_gemm_bf16(float *c, const mm_u16 *a, const mm_u16 *bt) {
    for (unsigned i = 0; i < MM_G; i++)
        for (unsigned j = 0; j < MM_G; j++) {
            float s = 0.0f;
            const mm_u16 *p = a + i * MM_G, *q = bt + j * MM_G;
            for (unsigned k = 0; k < MM_G; k++) s += bf16_to_f32(p[k]) * bf16_to_f32(q[k]);
            c[i * MM_G + j] = s;
        }
}

void mm_gemm_f32(float *c, const float *a, const float *bt) {
    for (unsigned i = 0; i < MM_G; i++)
        for (unsigned j = 0; j < MM_G; j++) {
            float s = 0.0f;
            const float *p = a + i * MM_G, *q = bt + j * MM_G;
            for (unsigned k = 0; k < MM_G; k++) s += p[k] * q[k];
            c[i * MM_G + j] = s;
        }
}

void mm_gemv_i8(mm_i32 *y, const mm_i8 *w, const mm_i8 *x, unsigned rows, unsigned cols) {
    for (unsigned r = 0; r < rows; r++) {
        mm_i32 s = 0;
        const mm_i8 *p = w + (mm_u64)r * cols;
        for (unsigned k = 0; k < cols; k++) s += (mm_i32)p[k] * x[k];
        y[r] = s;
    }
}

float mm_f16_to_f32(mm_u16 h) {
    mm_u32 sign = (mm_u32)(h & 0x8000u) << 16, e = (h >> 10) & 31u, m = h & 1023u;
    if (e == 0) { /* zero or subnormal: m * 2^-24 */
        if (m == 0) return bits_to_float(sign);
        int shift = 0;
        while (!(m & 1024u)) m <<= 1, shift++;
        return bits_to_float(sign | ((mm_u32)(113 - shift) << 23) | ((m & 1023u) << 13));
    }
    return bits_to_float(sign | ((e + 112u) << 23) | (m << 13));
}

/* Round to nearest even; a carry out of the fraction raises the exponent (correct). */
mm_u16 mm_f32_to_bf16(float f) {
    mm_u32 u = float_to_bits(f);
    u += 0x7fffu + ((u >> 16) & 1u);
    return (mm_u16)(u >> 16);
}

/* (float)v by integer arithmetic only: the soft-float build's __floatsisf, and a check on the host. */
float mm_i2f(mm_i32 v) {
    if (v == 0) return 0.0f;
    mm_u32 sign = v < 0 ? 0x80000000u : 0u, m = v < 0 ? 0u - (mm_u32)v : (mm_u32)v;
    int e = 31;
    while (!(m >> e)) e--;
    if (e <= 23) m <<= 23 - e;
    else {
        int shift = e - 23;
        mm_u32 lost = m & ((1u << shift) - 1u), half = 1u << (shift - 1);
        m >>= shift;
        if (lost > half || (lost == half && (m & 1u))) m++;
        if (m == (1u << 24)) m >>= 1, e++;
    }
    return bits_to_float(sign | ((mm_u32)(e + 127) << 23) | (m & 0x7fffffu));
}

void mm_gemv_q4(float *y, const mm_u8 *w, const mm_i8 *x, const float *xs, unsigned rows, unsigned cols) {
    const unsigned blocks = cols / MM_QBLOCK;
    for (unsigned r = 0; r < rows; r++) {
        float acc = 0.0f;
        const mm_u8 *blk = w + (mm_u64)r * blocks * MM_QBYTES;
        for (unsigned b = 0; b < blocks; b++, blk += MM_QBYTES) {
            const mm_i8 *xv = x + b * MM_QBLOCK;
            const mm_u8 *qs = blk + 2;
            mm_i32 isum = 0;
            for (unsigned j = 0; j < 16; j++)
                isum += ((mm_i32)(qs[j] & 15u) - 8) * xv[j] + ((mm_i32)(qs[j] >> 4) - 8) * xv[j + 16];
            float d = mm_f16_to_f32((mm_u16)(blk[0] | (blk[1] << 8)));
            float scale = d * xs[b];
            acc = acc + MM_CONVERT(isum) * scale;
        }
        y[r] = acc;
    }
}

void mm_gemv_f32(float *y, const float *w, const float *x, unsigned rows, unsigned cols) {
    for (unsigned r = 0; r < rows; r++) {
        float s = 0.0f;
        const float *p = w + (mm_u64)r * cols;
        for (unsigned k = 0; k < cols; k++) s += p[k] * x[k];
        y[r] = s;
    }
}
