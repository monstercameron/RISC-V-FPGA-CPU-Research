/* SPDX-License-Identifier: MIT
 * Scalar ternary GEMV kernels (original code; the formats follow the published ideas of bitnet.cpp
 * I2_S, llama.cpp TQ1_0 base-3 bytes and bit-serial popcount; nothing is copied from those projects).
 * y[m] = sum_k w[m][k] * a[k], w in {-1, 0, +1}, a int8 in [-127, 127], exact int32 result.
 * Included by one translation unit (static scratch buffers): the RISC-V program, the native
 * generator and the laptop reference. Integer only; bs8 uses cpop where Zbb exists.
 * The packers are in tern_data.h (native only): the core never packs.
 */
#ifndef TERN_KERNELS_H
#define TERN_KERNELS_H
#include <stdint.h>
#include <stddef.h>
#include "tern_shapes.h"

#define TERN_KPAD5(K) (((K) + 319) / 320 * 320)

static int16_t tern_lut5[64 * 256] __attribute__((aligned(64)));       /* one 32 KiB table tile */
static uint64_t tern_ap[TERN_MAXK / 64 * 8 + 8];                       /* bs8: activation bit planes */
static uint8_t tern_qidx[243];

static void tern_init_qidx(void) {      /* TQ1_0-style byte for base-3 value b: ceil(b * 256 / 243) */
    for (int b = 0; b < 243; b++) tern_qidx[b] = (uint8_t)((b * 256 + 242) / 243);
}

/* ---- i2: row-major, 4 codes (w + 1) per byte, bits 2i = weight 4j + i; y = sum(code * a) - sum(a) ---- */
__attribute__((noinline)) static void k_i2(const uint8_t *W, const int8_t *A, int32_t *Y, int M, int K) {
    int32_t sa = 0;
    for (int k = 0; k < K; k++) sa += A[k];
    for (int m = 0; m < M; m++) {
        const uint8_t *p = W + (size_t)m * (K / 4);
        const int8_t *a = A;
        int32_t s = 0;
        for (int j = 0; j < K / 4; j++, a += 4) {
            unsigned b = p[j];
            s += (int32_t)(b & 3) * a[0] + (int32_t)((b >> 2) & 3) * a[1] + (int32_t)((b >> 4) & 3) * a[2] +
                 (int32_t)(b >> 6) * a[3];
        }
        Y[m] = s - sa;
    }
}

/* ---- lut5w: 5 trits per byte (TQ1_0 order, first weight most significant), K padded to a multiple of
 * 320 (64 groups = one 32 KiB table tile), layout [tile][m][64 bytes]. Per tile one 256-entry int16
 * table per group of 5 activations is built, then each row sums 64 table entries; 8 index bytes
 * are fetched per 64-bit load. ---- */
static void tern_build_lut5(const int8_t *A, int t, int K) {
    for (int g = 0; g < 64; g++) {
        int a[5];
        for (int i = 0; i < 5; i++) { int k = t * 320 + g * 5 + i; a[i] = k < K ? A[k] : 0; }
        int16_t *T = tern_lut5 + g * 256;
        const uint8_t *q = tern_qidx;
        for (int d0 = -1; d0 <= 1; d0++) { int s0 = d0 * a[0];
        for (int d1 = -1; d1 <= 1; d1++) { int s1 = s0 + d1 * a[1];
        for (int d2 = -1; d2 <= 1; d2++) { int s2 = s1 + d2 * a[2];
        for (int d3 = -1; d3 <= 1; d3++) { int s3 = s2 + d3 * a[3];
            T[q[0]] = (int16_t)(s3 - a[4]); T[q[1]] = (int16_t)s3; T[q[2]] = (int16_t)(s3 + a[4]); q += 3; } } } }
    }
}
__attribute__((noinline)) static void k_lut5w(const uint8_t *W, const int8_t *A, int32_t *Y, int M, int K) {
    int tiles = TERN_KPAD5(K) / 320;
    for (int m = 0; m < M; m++) Y[m] = 0;
    for (int t = 0; t < tiles; t++) {
        tern_build_lut5(A, t, K);
        for (int m = 0; m < M; m++) {
            const uint64_t *p = (const uint64_t *)(W + ((size_t)t * M + m) * 64);
            const int16_t *T = tern_lut5;
            int32_t s0 = 0, s1 = 0;
            for (int g = 0; g < 8; g++, T += 2048) {
                uint64_t x = p[g];
                s0 += T[x & 255];                  s1 += T[256 + ((x >> 8) & 255)];
                s0 += T[512 + ((x >> 16) & 255)];  s1 += T[768 + ((x >> 24) & 255)];
                s0 += T[1024 + ((x >> 32) & 255)]; s1 += T[1280 + ((x >> 40) & 255)];
                s0 += T[1536 + ((x >> 48) & 255)]; s1 += T[1792 + (x >> 56)];
            }
            Y[m] += s0 + s1;
        }
    }
}

/* ---- bs8: bit-serial popcount. Weights as two 64-bit planes (+1 mask, -1 mask) per 64 weights;
 * activations are transposed per call into 8 two's-complement bit planes per 64; the dot product is
 * the sum over planes of c_i * (cpop(B_i & P) - cpop(B_i & N)), c_i = 2^i, c_7 = -128 (Horner). ---- */
static inline int tern_popc(uint64_t x) { return __builtin_popcountll(x); }
__attribute__((noinline)) static void k_bs8(const uint8_t *W, const int8_t *A, int32_t *Y, int M, int K) {
    int nb = K / 64;
    for (int j = 0; j < nb; j++)
        for (int b = 0; b < 8; b++) {
            uint64_t x = 0;
            for (int i = 0; i < 64; i++) x |= (uint64_t)(((uint8_t)A[64 * j + i] >> b) & 1) << i;
            tern_ap[8 * j + b] = x;
        }
    for (int m = 0; m < M; m++) {
        const uint64_t *w = (const uint64_t *)W + (size_t)m * nb * 2;
        int64_t s = 0;
        for (int j = 0; j < nb; j++) {
            uint64_t P = w[2 * j], N = w[2 * j + 1];
            const uint64_t *B = tern_ap + 8 * j;
            int64_t h = -(int64_t)(tern_popc(B[7] & P) - tern_popc(B[7] & N));
            for (int b = 6; b >= 0; b--) h = 2 * h + (tern_popc(B[b] & P) - tern_popc(B[b] & N));
            s += h;
        }
        Y[m] = (int32_t)s;
    }
}

/* ---- stream: sum of 64-bit words, four independent accumulators; a read-bandwidth probe with
 * almost no compute (the loads are independent, so the core overlaps as many misses as it can). ---- */
__attribute__((noinline)) static uint64_t k_stream(const uint64_t *p, size_t words) {
    uint64_t s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    for (size_t i = 0; i + 4 <= words; i += 4) { s0 += p[i]; s1 += p[i + 1]; s2 += p[i + 2]; s3 += p[i + 3]; }
    return s0 + s1 + s2 + s3;
}

static uint32_t tern_fnv(const int32_t *y, int n) {
    uint32_t h = 2166136261u;
    for (int i = 0; i < n; i++) { h ^= (uint32_t)y[i]; h *= 16777619u; }
    return h;
}
#endif
