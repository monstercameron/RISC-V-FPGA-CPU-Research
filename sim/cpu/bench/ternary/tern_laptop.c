/* SPDX-License-Identifier: MIT
 * Laptop reference of the ternary benchmark (aarch64 Linux; run by tern_laptop.py under taskset).
 * The same scalar kernels as the RISC-V program (tern_kernels.h, compiled with the auto-vectoriser
 * off) over the same synthetic weights, plus a NEON SDOT kernel (ndot, I2_S-like layout) for context
 * only. Each (layer, kernel) is checked against the int8 reference, then measured with the CPU's
 * own user-space PMUv3 counters (CPU_CYCLES 0x11, INST_RETIRED 0x08, through perf_event_open):
 *   resident  the kernel repeated for at least 20 ms on weights that stay cached after the first call;
 *   cold      (T-2B4T only) a 256 MiB sweep evicts the caches, then one call is timed.
 * Output lines: R shape layer kernel mode M K weights bytes cycles insns seconds   (per call)
 * Usage: tern_laptop [cold_repeats]
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sched.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#if defined(__ARM_FEATURE_DOTPROD)
#include <arm_neon.h>
#endif
#include "tern_data.h"

static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (double)t.tv_sec + 1e-9 * (double)t.tv_nsec; }

/* ---- PMU counters: the armv8_pmuv3_N whose cpu list holds the CPU we run on ---- */
static int pmu_type(int cpu) {
    for (int n = 0; n < 8; n++) {
        char path[128], buf[256];
        snprintf(path, sizeof path, "/sys/bus/event_source/devices/armv8_pmuv3_%d/cpus", n);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        int in = 0;
        if (fgets(buf, sizeof buf, f)) {
            char *p = buf;
            while (*p) {
                long lo = strtol(p, &p, 10), hi = lo;
                if (*p == '-') hi = strtol(p + 1, &p, 10);
                if (cpu >= lo && cpu <= hi) in = 1;
                if (*p == ',') p++; else break;
            }
        }
        fclose(f);
        if (!in) continue;
        snprintf(path, sizeof path, "/sys/bus/event_source/devices/armv8_pmuv3_%d/type", n);
        f = fopen(path, "r");
        int t = -1;
        if (f) { if (fscanf(f, "%d", &t) != 1) t = -1; fclose(f); }
        return t;
    }
    return -1;
}
static int pmu_open(uint64_t event) {
    struct perf_event_attr a;
    memset(&a, 0, sizeof a);
    a.size = sizeof a;
    a.type = (uint32_t)pmu_type(sched_getcpu());
    a.config = event;
    a.disabled = 1; a.exclude_kernel = 1; a.exclude_hv = 1;
    return (int)syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}
static int fd_cyc = -1, fd_ins = -1;
static void pmu_begin(void) {
    ioctl(fd_cyc, PERF_EVENT_IOC_RESET, 0); ioctl(fd_ins, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd_cyc, PERF_EVENT_IOC_ENABLE, 0); ioctl(fd_ins, PERF_EVENT_IOC_ENABLE, 0);
}
static void pmu_end(long long *cyc, long long *ins) {
    ioctl(fd_cyc, PERF_EVENT_IOC_DISABLE, 0); ioctl(fd_ins, PERF_EVENT_IOC_DISABLE, 0);
    if (read(fd_cyc, cyc, 8) != 8) *cyc = -1;
    if (read(fd_ins, ins, 8) != 8) *ins = -1;
}

/* Clock ramp: dependent adds for about 2 s so the core is at its working frequency. */
static double ramp(void) {
    double t0 = now(), ghz = 0;
    uint64_t x = 1;
    while (now() - t0 < 2.0) {
        double s = now();
        uint64_t n = 100000000;
        for (uint64_t i = 0; i < n; i++) __asm__ volatile("add %0, %0, %1" : "+r"(x) : "r"(i));
        ghz = (double)n / (now() - s) / 1e9;
    }
    if (x == 42) puts("");
    return ghz;
}

/* ---- NEON SDOT kernel (context only): I2_S-like 2-bit two's complement fields, 16-byte blocks ---- */
#if defined(__ARM_FEATURE_DOTPROD)
static size_t bytes_mad(int M, int K) { return (size_t)M * (K / 4); }
static void pack_mad(int li, int M, int K, uint8_t *W) {
    for (int m = 0; m < M; m++)
        for (int j = 0; j < K / 64; j++)
            for (int r = 0; r < 16; r++) {
                unsigned b = 0;
                for (int i = 0; i < 4; i++) b |= (unsigned)(tern_trit(li, m, j * 64 + i * 16 + r, K) & 3) << (2 * i);
                W[((size_t)m * (K / 64) + j) * 16 + r] = (uint8_t)b;
            }
}
__attribute__((noinline)) static void k_ndot(const uint8_t *W, const int8_t *A, int32_t *Y, int M, int K) {
    int nb = K / 64;
    for (int m = 0; m < M; m++) {
        const int8_t *p = (const int8_t *)W + (size_t)m * nb * 16;
        int32x4_t s0 = vdupq_n_s32(0), s1 = vdupq_n_s32(0);
        for (int j = 0; j < nb; j++, p += 16) {
            int8x16_t w = vld1q_s8(p);
            const int8_t *a = A + j * 64;
            s0 = vdotq_s32(s0, vshrq_n_s8(vshlq_n_s8(w, 6), 6), vld1q_s8(a));
            s1 = vdotq_s32(s1, vshrq_n_s8(vshlq_n_s8(w, 4), 6), vld1q_s8(a + 16));
            s0 = vdotq_s32(s0, vshrq_n_s8(vshlq_n_s8(w, 2), 6), vld1q_s8(a + 32));
            s1 = vdotq_s32(s1, vshrq_n_s8(w, 6), vld1q_s8(a + 48));
        }
        Y[m] = vaddvq_s32(vaddq_s32(s0, s1));
    }
}
#endif

typedef void (*kfn)(const uint8_t *, const int8_t *, int32_t *, int, int);
static volatile uint64_t sink;
static uint8_t *evict_buf;
#define EVICT_BYTES (256u << 20)
static void evict(void) {
    uint64_t s = 0;
    for (size_t i = 0; i < EVICT_BYTES; i += 64) { evict_buf[i] += 1; s += evict_buf[i]; }
    sink = s;
}

static void report(const char *shape, int li, const char *kern, const char *mode, int M, int K, double weights,
                   size_t bytes, long long cyc, long long ins, double secs) {
    printf("R %s %d %s %s %d %d %.0f %zu %lld %lld %.9f\n", shape, li, kern, mode, M, K, weights, bytes, cyc, ins, secs);
}

int main(int argc, char **argv) {
    int cold_reps = argc > 1 ? atoi(argv[1]) : 3;
    fd_cyc = pmu_open(0x11); fd_ins = pmu_open(0x08);
    if (fd_cyc < 0 || fd_ins < 0) { fprintf(stderr, "PMU counters unavailable\n"); return 1; }
#if TERN_SHAPE == 1
    const char *shape = "small";
#else
    const char *shape = "2b4t";
#endif
    tern_init_qidx();
    double ghz = ramp();
    printf("C %s clock_ramp_ghz %.3f qidx_bad %d cpu %d\n", shape, ghz, tern_qidx_selfcheck(), sched_getcpu());
    size_t wmax = 0;
    for (int li = 0; li < TERN_NL; li++) {
        size_t b[3] = {tern_bytes_i2(TERN_LAYERS[li].m, TERN_LAYERS[li].k), tern_bytes_lut5w(TERN_LAYERS[li].m, TERN_LAYERS[li].k),
                       tern_bytes_bs8(TERN_LAYERS[li].m, TERN_LAYERS[li].k)};
        for (int s = 0; s < 3; s++) if (b[s] > wmax) wmax = b[s];
    }
    uint8_t *W = aligned_alloc(64, wmax + 64);
    int8_t *A = aligned_alloc(64, (size_t)TERN_MAXK + 512);
    int32_t *YR = malloc(4 * (size_t)(TERN_MAXM + 16)), *Y = malloc(4 * (size_t)(TERN_MAXM + 16));
    int cold = TERN_SHAPE == 0;
    if (cold) { evict_buf = malloc(EVICT_BYTES); memset(evict_buf, 1, EVICT_BYTES); }
    int bad = 0;
    for (int li = 0; li < TERN_NL; li++) {
        int M = TERN_LAYERS[li].m, K = TERN_LAYERS[li].k;
        memset(A, 0, (size_t)TERN_MAXK + 512);
        for (int k = 0; k < K; k++) A[k] = (int8_t)tern_act(li, k);
        tern_ref(li, M, K, A, YR);
        struct { const char *name; kfn f; size_t bytes; } ks[4];
        int nk = 0;
        ks[nk].name = "i2"; ks[nk].f = k_i2; ks[nk++].bytes = tern_bytes_i2(M, K);
        ks[nk].name = "lut5w"; ks[nk].f = k_lut5w; ks[nk++].bytes = tern_bytes_lut5w(M, K);
        ks[nk].name = "bs8"; ks[nk].f = k_bs8; ks[nk++].bytes = tern_bytes_bs8(M, K);
#if defined(__ARM_FEATURE_DOTPROD)
        ks[nk].name = "ndot"; ks[nk].f = k_ndot; ks[nk++].bytes = bytes_mad(M, K);
#endif
        for (int kk = 0; kk < nk; kk++) {
            if (!strcmp(ks[kk].name, "i2")) tern_pack_i2(li, M, K, W);
            else if (!strcmp(ks[kk].name, "lut5w")) tern_pack_lut5w(li, M, K, W);
            else if (!strcmp(ks[kk].name, "bs8")) tern_pack_bs8(li, M, K, W);
#if defined(__ARM_FEATURE_DOTPROD)
            else pack_mad(li, M, K, W);
#endif
            ks[kk].f(W, A, Y, M, K);
            for (int m = 0; m < M; m++) bad += Y[m] != YR[m];
            ks[kk].f(W, A, Y, M, K);
            double t0 = now();
            ks[kk].f(W, A, Y, M, K);
            double one = now() - t0;
            int reps = (int)(0.02 / (one > 1e-6 ? one : 1e-6)) + 1;
            long long cyc, ins;
            t0 = now();
            pmu_begin();
            for (int r = 0; r < reps; r++) ks[kk].f(W, A, Y, M, K);
            pmu_end(&cyc, &ins);
            double secs = (now() - t0) / reps;
            report(shape, li, ks[kk].name, "resident", M, K, (double)M * K, ks[kk].bytes, cyc / reps, ins / reps, secs);
            if (cold)
                for (int c = 0; c < cold_reps; c++) {
                    evict();
                    t0 = now();
                    pmu_begin();
                    ks[kk].f(W, A, Y, M, K);
                    pmu_end(&cyc, &ins);
                    report(shape, li, ks[kk].name, "cold", M, K, (double)M * K, ks[kk].bytes, cyc, ins, now() - t0);
                }
        }
        /* read-bandwidth probe over the i2 blob (the same bytes as the i2 kernel) */
        tern_pack_i2(li, M, K, W);
        size_t sb = tern_bytes_i2(M, K);
        uint64_t s0 = k_stream((const uint64_t *)W, sb / 8);
        double t0 = now();
        s0 += k_stream((const uint64_t *)W, sb / 8);
        double one = now() - t0;
        int reps = (int)(0.02 / (one > 1e-6 ? one : 1e-6)) + 1;
        long long cyc, ins;
        t0 = now();
        pmu_begin();
        for (int r = 0; r < reps; r++) { s0 += k_stream((const uint64_t *)W, sb / 8); __asm__ volatile("" ::: "memory"); }
        pmu_end(&cyc, &ins);
        report(shape, li, "stream", "resident", M, K, 0, sb, cyc / reps, ins / reps, (now() - t0) / reps);
        if (cold)
            for (int c = 0; c < cold_reps; c++) {
                evict();
                t0 = now();
                pmu_begin();
                s0 += k_stream((const uint64_t *)W, sb / 8);
                pmu_end(&cyc, &ins);
                report(shape, li, "stream", "cold", M, K, 0, sb, cyc, ins, now() - t0);
            }
        sink = s0;
    }
    printf("C %s mismatches %d\n", shape, bad);
    return bad != 0;
}
