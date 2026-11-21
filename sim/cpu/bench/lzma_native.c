/* SPDX-License-Identifier: MIT
 * Native (hosted) harness for the scaled-down 7-Zip LZMA kernel.
 *
 * Builds the same lzma_bench.c, lzma_bench_data.c and vendor/lzma sources
 * with -DLZMA_BENCH_NATIVE and the same LZMA_BENCH_* sizes as the bare-metal
 * image, runs the pass many times and reports each phase's time per pass
 * (minimum and median) as JSON on stdout. The marker hook records a
 * timestamp per phase marker; the phases are the same intervals the
 * testbench measures in clocks.
 *
 * Without a cycle counter available to user code, the clock frequency is
 * estimated by timing a chain of dependent integer adds (one per clock on
 * current cores), sampled before and after the passes.
 *
 * Usage: lzma_native [passes]
 */
#define _POSIX_C_SOURCE 199309L
#include "lzma_bench.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* LzFind.c's LzFindPrepare() refers to this on Arm; the benchmark never calls
 * LzFindPrepare(), as 7-Zip calls it only at program start. */
BoolInt CPU_IsSupported_NEON(void);
BoolInt CPU_IsSupported_NEON(void) { return 0; }

static double now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec * 1e9 + (double)t.tv_nsec;
}

enum { MARK_START = 1, MARK_STOP = 2, NUM_MARKS = 6 };
static double marks[NUM_MARKS];

static int mark_slot(unsigned value) {
    switch (value) {
    case LZMA_MARK_ENC_CALL: return 0;
    case MARK_START: return 1;
    case LZMA_MARK_ENC_DONE: return 2;
    case LZMA_MARK_DEC_CALL: return 3;
    case LZMA_MARK_DEC_KERNEL: return 4;
    case MARK_STOP: return 5;
    default: return -1;
    }
}

void lzma_bench_mark(unsigned value) {
    const int slot = mark_slot(value);
    if (slot >= 0) marks[slot] = now_ns();
}

/* 64 dependent adds per loop step. */
static double add_chain_ghz(void) {
    const long steps = 2000000;
    double best = 0;
    for (int trial = 0; trial < 5; trial++) {
        unsigned long long x = 0;
        long n = steps;
        const double t0 = now_ns();
#if defined(__aarch64__)
        __asm__ volatile(
            "1:\n"
            ".rept 64\n add %0, %0, #1\n .endr\n"
            "subs %1, %1, #1\n b.ne 1b\n"
            : "+r"(x), "+r"(n) : : "cc");
#elif defined(__x86_64__)
        __asm__ volatile(
            "1:\n"
            ".rept 64\n addq $1, %0\n .endr\n"
            "subq $1, %1\n jnz 1b\n"
            : "+r"(x), "+r"(n) : : "cc");
#else
#error "add-chain frequency estimate needs aarch64 or x86-64"
#endif
        const double t1 = now_ns();
        const double ghz = (double)steps * 64.0 / (t1 - t0);
        if (ghz > best) best = ghz;
    }
    return best;
}

static int compare_double(const void *a, const void *b) {
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

#define NUM_PHASES 4
static const char *const phase_names[NUM_PHASES] = {
    "compress_kernel", "compress_call", "decompress_kernel", "decompress_call"};

int main(int argc, char **argv) {
    const long passes = argc > 1 ? atol(argv[1]) : 2000;
    const size_t arena_size = (size_t)64 << 20;
    void *arena = malloc(arena_size);
    double *samples[NUM_PHASES];
    for (int p = 0; p < NUM_PHASES; p++) samples[p] = malloc(sizeof(double) * (size_t)passes);
    if (!arena || passes < 1) return 2;

    lzma_bench_prepare();
    LzmaBenchResult first, r;
    /* Untimed warm-up passes (a fifth of the count) let the clock settle first. */
    for (long i = 0; i < passes / 5; i++) {
        lzma_arena_init(arena, arena_size);
        lzma_bench_pass(&r);
    }
    const double ghz_before = add_chain_ghz();
    const double wall0 = now_ns();
    for (long i = 0; i < passes; i++) {
        lzma_arena_init(arena, arena_size);
        lzma_bench_pass(&r);
        if (i == 0) first = r;
        if (!r.compare_ok || memcmp(&r, &first, sizeof(r)) != 0) {
            fprintf(stderr, "pass %ld failed or differs\n", i);
            return 1;
        }
        samples[0][i] = marks[2] - marks[1]; /* first read .. encoder returned */
        samples[1][i] = marks[2] - marks[0]; /* LzmaEnc_Encode() call */
        samples[2][i] = marks[5] - marks[4]; /* LzmaDec_DecodeToDic() and CRC */
        samples[3][i] = marks[5] - marks[3]; /* LzmaDec_Init() .. CRC */
    }
    const double wall1 = now_ns();
    const double ghz_after = add_chain_ghz();

    printf("{\n  \"passes\": %ld,\n  \"wall_seconds\": %.3f,\n", passes, (wall1 - wall0) / 1e9);
    printf("  \"add_chain_ghz_before\": %.4f,\n  \"add_chain_ghz_after\": %.4f,\n", ghz_before, ghz_after);
    printf("  \"data_size\": %u,\n  \"dict_size\": %u,\n  \"packed_size\": %u,\n", r.data_size, r.dict_size,
           r.packed_size);
    printf("  \"crc_data\": %u,\n  \"crc_packed\": %u,\n  \"crc_unpacked\": %u,\n  \"props_byte\": %u,\n", r.crc_data,
           r.crc_packed, r.crc_unpacked, r.props_byte);
    printf("  \"arena_used\": %llu,\n  \"phases_ns\": {\n", (unsigned long long)r.arena_used);
    for (int p = 0; p < NUM_PHASES; p++) {
        qsort(samples[p], (size_t)passes, sizeof(double), compare_double);
        printf("    \"%s\": {\"min\": %.1f, \"median\": %.1f}%s\n", phase_names[p], samples[p][0],
               samples[p][passes / 2], p + 1 < NUM_PHASES ? "," : "");
    }
    printf("  }\n}\n");
    return 0;
}
