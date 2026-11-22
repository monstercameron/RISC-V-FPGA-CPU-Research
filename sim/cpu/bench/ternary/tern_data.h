/* SPDX-License-Identifier: MIT
 * Synthetic weights, activations and packers of the ternary benchmark. Native only (generator and
 * laptop reference); the RISC-V program never generates or packs. Deterministic: a hash of the
 * layer, row and column gives each trit (uniform in {-1, 0, +1}) and each int8 activation
 * (uniform in [-127, 127]). Synthetic weights are used on purpose: kernel speed does not depend on
 * the values, and no model weights are downloaded.
 */
#ifndef TERN_DATA_H
#define TERN_DATA_H
#include "tern_kernels.h"

static const uint64_t TERN_SEED = 0x1b17e7u;
static inline uint32_t tern_h32(uint64_t x) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdull; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ull; x ^= x >> 33;
    return (uint32_t)x;
}
static inline int tern_trit(int li, int m, int k, int K) {
    return (int)(((uint64_t)tern_h32(TERN_SEED ^ ((uint64_t)li << 56) ^ ((uint64_t)m * (uint64_t)K + (uint64_t)k)) * 3u) >> 32) - 1;
}
static inline int tern_act(int li, int k) {
    return (int)(((uint64_t)tern_h32((TERN_SEED * 7u) ^ ((uint64_t)li << 48) ^ (uint64_t)k) * 255u) >> 32) - 127;
}

/* Reference: plain int8 multiply-accumulate straight from the trits (independent of every packer). */
static void tern_ref(int li, int M, int K, const int8_t *A, int32_t *Y) {
    for (int m = 0; m < M; m++) {
        int32_t s = 0;
        for (int k = 0; k < K; k++) s += tern_trit(li, m, k, K) * A[k];
        Y[m] = s;
    }
}

static size_t tern_bytes_i2(int M, int K) { return (size_t)M * (K / 4); }
static size_t tern_bytes_lut5w(int M, int K) { return (size_t)(TERN_KPAD5(K) / 320) * M * 64; }
static size_t tern_bytes_bs8(int M, int K) { return (size_t)M * (K / 64) * 16; }

static void tern_pack_i2(int li, int M, int K, uint8_t *W) {
    for (int m = 0; m < M; m++)
        for (int j = 0; j < K / 4; j++) {
            unsigned b = 0;
            for (int i = 0; i < 4; i++) b |= (unsigned)(tern_trit(li, m, 4 * j + i, K) + 1) << (2 * i);
            W[(size_t)m * (K / 4) + j] = (uint8_t)b;
        }
}
static void tern_pack_lut5w(int li, int M, int K, uint8_t *W) {
    int tiles = TERN_KPAD5(K) / 320;
    for (int t = 0; t < tiles; t++)
        for (int m = 0; m < M; m++)
            for (int g = 0; g < 64; g++) {
                int b = 0;
                for (int i = 0; i < 5; i++) {
                    int k = t * 320 + g * 5 + i;
                    b = b * 3 + (k < K ? tern_trit(li, m, k, K) + 1 : 1);
                }
                W[((size_t)t * M + m) * 64 + g] = tern_qidx[b];
            }
}
static void tern_pack_bs8(int li, int M, int K, uint8_t *W8) {
    uint64_t *w = (uint64_t *)W8;
    for (int m = 0; m < M; m++)
        for (int j = 0; j < K / 64; j++) {
            uint64_t P = 0, N = 0;
            for (int i = 0; i < 64; i++) {
                int t = tern_trit(li, m, 64 * j + i, K);
                P |= (uint64_t)(t > 0) << i; N |= (uint64_t)(t < 0) << i;
            }
            w[((size_t)m * (K / 64) + j) * 2] = P; w[((size_t)m * (K / 64) + j) * 2 + 1] = N;
        }
}
/* decode check of the TQ1_0-style bytes: x *= 3, digit = x >> 8, as llama.cpp's scheme decodes */
static int tern_qidx_selfcheck(void) {
    int bad = 0;
    for (int b = 0; b < 243; b++) {
        unsigned x = tern_qidx[b], v = 0;
        for (int i = 0; i < 5; i++) { x *= 3; v = v * 3 + (x >> 8); x &= 255; }
        bad += v != (unsigned)b;
    }
    return bad;
}
#endif
