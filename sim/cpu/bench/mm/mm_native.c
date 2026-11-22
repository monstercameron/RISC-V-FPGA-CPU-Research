/* SPDX-License-Identifier: MIT
 * Native reference of the mm benchmark: runs mm_bench_run() once and prints the
 * mailbox words the bare-metal build writes (mm_runtime.c) as JSON, after the
 * self-checks that need a host: mm_i2f against the hardware conversion, FP16
 * against the compiler's _Float16, BF16 rounding cases, and an independent
 * 64-bit recomputation (reverse order) of the integer kernels.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mm_bench.h"

void mm_mark(unsigned value) { (void)value; }

static mm_u32 bits(float f) { mm_u32 u; memcpy(&u, &f, 4); return u; }
static float from_bits(mm_u32 u) { float f; memcpy(&f, &u, 4); return f; }

static int self_check(void) {
    int bad = 0;
    for (long v = -(1L << 20); v <= (1L << 20); v++) bad += bits(mm_i2f((mm_i32)v)) != bits((float)(mm_i32)v);
    for (int s = 0; s < 31; s++)
        for (long d = -3; d <= 3; d++) {
            long v = (1L << s) + d;
            if (v > 2147483647L || v < -2147483647L) continue;
            bad += bits(mm_i2f((mm_i32)v)) != bits((float)(mm_i32)v);
            bad += bits(mm_i2f((mm_i32)-v)) != bits((float)(mm_i32)-v);
        }
    bad += bits(mm_i2f(2147483647)) != bits(2147483648.0f);
    bad += bits(mm_i2f((mm_i32)0x80000001)) != bits((float)(mm_i32)0x80000001);
#if defined(__FLT16_MANT_DIG__)
    for (unsigned h = 0; h < 65536; h++) {
        if (((h >> 10) & 31u) == 31u) continue;
        union { mm_u16 u; _Float16 f; } v;
        v.u = (mm_u16)h;
        bad += bits(mm_f16_to_f32((mm_u16)h)) != bits((float)v.f);
    }
#else
    bad += 1000; /* the check needs _Float16 */
#endif
    bad += mm_f32_to_bf16(1.0f) != 0x3f80 || mm_f32_to_bf16(-2.5f) != 0xc020;
    bad += mm_f32_to_bf16(from_bits(0x3f808000u)) != 0x3f80; /* tie, even */
    bad += mm_f32_to_bf16(from_bits(0x3f818000u)) != 0x3f82; /* tie, odd */
    bad += mm_f32_to_bf16(from_bits(0x3f808001u)) != 0x3f81; /* above a tie */
    bad += mm_f32_to_bf16(from_bits(0x3fffffffu)) != 0x4000; /* carry into the exponent */
    return bad;
}

static int int_check(void) {
    int bad = 0;
    static mm_i32 c[MM_G * MM_G], y[MM_V1_ROWS];
    mm_gemm_i8(c, mm_g1_a, mm_g1_bt);
    for (int i = 0; i < MM_G; i++)
        for (int j = 0; j < MM_G; j++) {
            long long s = 0;
            for (int k = MM_G - 1; k >= 0; k--) s += (long long)mm_g1_a[i * MM_G + k] * mm_g1_bt[j * MM_G + k];
            bad += s != c[i * MM_G + j];
        }
    mm_gemv_i8(y, mm_v1_w, mm_x8, MM_V1_ROWS, MM_COLS8);
    for (int r = 0; r < MM_V1_ROWS; r++) {
        long long s = 0;
        for (int k = MM_COLS8 - 1; k >= 0; k--) s += (long long)mm_v1_w[(long long)r * MM_COLS8 + k] * mm_x8[k];
        bad += s != y[r];
    }
    return bad;
}

int main(void) {
    int bad = self_check() + int_check();
    if (bad) { fprintf(stderr, "mm_native: %d self-check failures\n", bad); return 1; }
    mm_results r;
    mm_u64 w[16];
    mm_bench_run(&r);
    unsigned n = mm_words(&r, w);
    printf("{\"mailbox\": {");
    for (unsigned i = 0; i < n; i++) printf("%s\"%u\": %llu", i ? ", " : "", i + 2, (unsigned long long)w[i]);
    printf("}, \"kernels\": [");
    for (unsigned k = 0; k < r.n; k++) printf("%s\"%s\"", k ? ", " : "", mm_names[k]);
    printf("], \"self_checks\": \"mm_i2f, FP16, BF16 rounding, integer kernels recomputed in 64 bits: pass\"}\n");
    return 0;
}
