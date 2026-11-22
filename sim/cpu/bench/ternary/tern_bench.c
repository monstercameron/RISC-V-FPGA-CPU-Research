/* SPDX-License-Identifier: MIT
 * Bare-metal program of the ternary benchmark (run_bench.py --benchmark ternary). For each selected
 * kernel and each layer: touch the layer's packed weights once (one load per 64-byte line; this puts
 * them in the L2 when it can hold them), mark, run the kernel, mark, compare every output with the
 * native reference and fold it into a checksum. Weights, activations and reference outputs come
 * from the generated data object (ternary_data.S); the core never generates or packs.
 *
 * Markers: 1 region start, 2 region stop; a timed call c = slot * (NL + 1) + layer is bracketed by
 * 0x10 + 2c (begin) and 0x11 + 2c (end). Slots: 0 i2, 1 lut5w, 2 bs8, 3 stream (each layer's i2
 * region), 4 streamall (one call: the whole i2 blob, no touch pass, run first so it reads cold memory).
 * Mailbox results (bench_result index, word = 2 + index):
 *   0 magic "TERNBNCH"   1 mismatches (0 expected)   2 weights per pass   3 kernel mask | NL << 8
 *   4 + c   the call's FNV-1a of its int32 outputs, or the 64-bit word sum for the stream slot
 *
 * TERN_KERNELS (bit mask of slots) and TERN_SHAPE come from build_bench.py.
 */
#include "bench.h"
#include "tern_kernels.h"

#ifndef TERN_KERNELS
#define TERN_KERNELS 15
#endif
#define TERN_MAGIC 0x48434e424e524554ull   /* "TERNBNCH", little endian */

extern const uint8_t tern_w_i2[], tern_w_lut5w[], tern_w_bs8[], tern_act[], tern_yref[];
extern const uint64_t tern_desc[][8];

static int32_t Y[TERN_MAXM + 16];
static volatile uint64_t sink;

void *memcpy(void *d, const void *s, size_t n) {
    unsigned char *o = d;
    const unsigned char *i = s;
    while (n--) *o++ = *i++;
    return d;
}
void *memset(void *d, int c, size_t n) {
    unsigned char *o = d;
    while (n--) *o++ = (unsigned char)c;
    return d;
}

static void touch(const void *p, size_t bytes) {
    const volatile uint64_t *q = (const volatile uint64_t *)p;
    uint64_t s = 0;
    for (size_t i = 0; i < bytes / 8; i += 8) s += q[i];
    sink = s;
}

int main(void) {
    tern_init_qidx();
    uint64_t bad = 0, weights = 0;
    for (int li = 0; li < TERN_NL; li++) weights += (uint64_t)TERN_LAYERS[li].m * (uint64_t)TERN_LAYERS[li].k;
    bench_result(0, TERN_MAGIC);
    bench_result(2, weights);
    bench_result(3, (uint64_t)TERN_KERNELS | (uint64_t)TERN_NL << 8);
    bench_marker(BENCH_MARKER_START);
    for (int pass = 0; pass < TS_N; pass++) {
        int slot = pass == 0 ? TS_STREAMALL : pass - 1;
        if (!(TERN_KERNELS >> slot & 1)) continue;
        int layers = slot == TS_STREAMALL ? 1 : TERN_NL;
        for (int li = 0; li < layers; li++) {
            int c = slot * (TERN_NL + 1) + li;
            const uint64_t *d = tern_desc[slot == TS_STREAMALL ? TERN_NL : li];
            int M = slot == TS_STREAMALL ? 0 : TERN_LAYERS[li].m, K = slot == TS_STREAMALL ? 0 : TERN_LAYERS[li].k;
            const int8_t *A = (const int8_t *)(tern_act + d[3]);
            const int32_t *YR = (const int32_t *)(tern_yref + d[4]);
            if (slot == TS_STREAM || slot == TS_STREAMALL) {
                const uint8_t *p = tern_w_i2 + d[0];
                if (slot == TS_STREAM) touch(p, d[6]);
                bench_marker(0x10 + 2 * c);
                uint64_t sum = k_stream((const uint64_t *)p, d[6] / 8);
                bench_marker(0x11 + 2 * c);
                bad += sum != d[5];
                bench_result(4 + c, sum);
                continue;
            }
            const uint8_t *W = slot == TS_I2 ? tern_w_i2 + d[0] : slot == TS_LUT5W ? tern_w_lut5w + d[1] : tern_w_bs8 + d[2];
            size_t bytes = slot == TS_LUT5W ? (size_t)(TERN_KPAD5(K) / 320) * M * 64 : (size_t)M * (K / 4);
            touch(W, bytes);
            bench_marker(0x10 + 2 * c);
            if (slot == TS_I2) k_i2(W, A, Y, M, K);
            else if (slot == TS_LUT5W) k_lut5w(W, A, Y, M, K);
            else k_bs8(W, A, Y, M, K);
            bench_marker(0x11 + 2 * c);
            for (int m = 0; m < M; m++) bad += Y[m] != YR[m];
            bench_result(4 + c, tern_fnv(Y, M));
        }
    }
    /* Space the stop marker from the last call's end marker: the core may write two adjacent stores in one
     * clock, and the timing bench would then miss the end marker (seen with N_MISS 8, MEM_GAP 4 and 8). */
    for (int i = 0; i < 4; i++) sink = sink + 1;
    bench_marker(BENCH_MARKER_STOP);
    bench_result(1, bad);
    return bad != 0;
}
