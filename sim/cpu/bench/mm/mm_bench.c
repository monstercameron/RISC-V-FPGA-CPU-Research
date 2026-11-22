/* SPDX-License-Identifier: MIT
 * mm benchmark driver: one pass of every kernel with phase markers, then the
 * FNV-1a checksums of the outputs (after the stop marker, so hashing is not timed).
 */
#include "mm_bench.h"

static mm_i32 c_g1[MM_G * MM_G];
static float c_g2[MM_G * MM_G], c_g3[MM_G * MM_G];
static mm_i32 y_v1[MM_V1_ROWS];
static float y_v3[MM_V3_ROWS], y_v4[MM_V4_ROWS];
#if MM_V1B_ROWS
static mm_i32 y_v1b[MM_V1B_ROWS];
#endif

const char *const mm_names[8] = {"G1_int8_gemm", "G2_bf16_gemm", "G3_fp32_gemm", "V1_int8_gemv", "V3_q4_gemv",
                                 "V4_fp32_gemv", "V1b_int8_gemv_8MiB", 0};

static mm_u64 fnv1a(const void *data, mm_u64 bytes) {
    const mm_u8 *p = data;
    mm_u64 h = 1469598103934665603ull;
    for (mm_u64 i = 0; i < bytes; i++) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

void mm_bench_run(mm_results *r) {
    unsigned n = 0;
    mm_mark(1);
    mm_gemm_i8(c_g1, mm_g1_a, mm_g1_bt);
    mm_mark(0x20 + n++);
    mm_gemm_bf16(c_g2, mm_g2_a, mm_g2_bt);
    mm_mark(0x20 + n++);
    mm_gemm_f32(c_g3, mm_g3_a, mm_g3_bt);
    mm_mark(0x20 + n++);
    mm_gemv_i8(y_v1, mm_v1_w, mm_x8, MM_V1_ROWS, MM_COLS8);
    mm_mark(0x20 + n++);
    mm_gemv_q4(y_v3, mm_v3_w, mm_x8, mm_xs, MM_V3_ROWS, MM_COLS4);
    mm_mark(0x20 + n++);
#if MM_V1B_ROWS
    mm_gemv_f32(y_v4, mm_v4_w, mm_v4_x, MM_V4_ROWS, MM_COLSF);
    mm_mark(0x20 + n++);
    mm_gemv_i8(y_v1b, mm_v1b_w, mm_x8, MM_V1B_ROWS, MM_COLS8);
#else
    mm_gemv_f32(y_v4, mm_v4_w, mm_v4_x, MM_V4_ROWS, MM_COLSF);
#endif
    n++;
    mm_mark(2);
    r->n = n;
    n = 0;
    r->hash[n++] = fnv1a(c_g1, sizeof c_g1);
    r->hash[n++] = fnv1a(c_g2, sizeof c_g2);
    r->hash[n++] = fnv1a(c_g3, sizeof c_g3);
    r->hash[n++] = fnv1a(y_v1, sizeof y_v1);
    r->hash[n++] = fnv1a(y_v3, sizeof y_v3);
    r->hash[n++] = fnv1a(y_v4, sizeof y_v4);
#if MM_V1B_ROWS
    r->hash[n++] = fnv1a(y_v1b, sizeof y_v1b);
#endif
}

unsigned mm_words(const mm_results *r, mm_u64 *w) {
    unsigned n = 0;
    w[n++] = MM_MAGIC;
    w[n++] = (mm_u64)MM_V1_ROWS | (mm_u64)MM_V3_ROWS << 16 | (mm_u64)MM_V4_ROWS << 32 | (mm_u64)MM_V1B_ROWS << 48;
    for (unsigned k = 0; k < r->n; k++) w[n++] = r->hash[k];
    return n;
}
