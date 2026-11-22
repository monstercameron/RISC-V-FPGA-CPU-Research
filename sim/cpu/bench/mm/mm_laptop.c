/* SPDX-License-Identifier: MIT
 * Laptop timing of the mm benchmark's scalar kernels (the same mm_kernels.c, mm_data.S and shapes as the
 * RV64 build), per clock from the CPU cycle counter. aarch64 Linux, run pinned: taskset -c 19.
 * Build (mm_laptop.sh): clang -O2 -fno-vectorize -fno-slp-vectorize -ffp-contract=off -D_GNU_SOURCE.
 * Per run: a peak probe (independent adds, instructions per clock; a run well below the others is discarded by the
 * caller, below 0.9 x the median probe: the vCPU shared a core), then per kernel the median of 7 trials of `reps` back-to-back
 * calls, cycles and instructions per call, and the FNV-1a checksum words of one pass (compare with
 * expected.json). One JSON line per item.
 */
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <linux/perf_event.h>
#include "mm_bench.h"

void mm_mark(unsigned value) { (void)value; }

/* The PMU of the core type this thread runs on: raw PMUv3 events 0x08 INST_RETIRED and 0x11 CPU_CYCLES. */
static int pmu_type_for_cpu(int cpu) {
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

static int perf_open(uint64_t config) {
    struct perf_event_attr a;
    const int type = pmu_type_for_cpu(sched_getcpu());
    memset(&a, 0, sizeof a);
    a.size = sizeof a;
    a.type = type >= 0 ? (uint32_t)type : PERF_TYPE_HARDWARE;
    a.config = type >= 0 ? (config == PERF_COUNT_HW_INSTRUCTIONS ? 0x08 : 0x11) : config;
    a.disabled = 1;
    a.exclude_kernel = 1;
    a.exclude_hv = 1;
    return (int)syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}

static int fd_ins = -1, fd_cyc = -1;

static void counters_start(void) {
    ioctl(fd_ins, PERF_EVENT_IOC_RESET, 0), ioctl(fd_ins, PERF_EVENT_IOC_ENABLE, 0);
    ioctl(fd_cyc, PERF_EVENT_IOC_RESET, 0), ioctl(fd_cyc, PERF_EVENT_IOC_ENABLE, 0);
}

static void counters_stop(long long *ins, long long *cyc) {
    ioctl(fd_ins, PERF_EVENT_IOC_DISABLE, 0), ioctl(fd_cyc, PERF_EVENT_IOC_DISABLE, 0);
    if (read(fd_ins, ins, 8) != 8) *ins = -1;
    if (read(fd_cyc, cyc, 8) != 8) *cyc = -1;
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static mm_i32 c_g1[MM_G * MM_G], y_v1[MM_V1_ROWS];
static float c_g2[MM_G * MM_G], c_g3[MM_G * MM_G], y_v3[MM_V3_ROWS], y_v4[MM_V4_ROWS];
#if MM_V1B_ROWS
static mm_i32 y_v1b[MM_V1B_ROWS];
#endif

static void k_g1(void) { mm_gemm_i8(c_g1, mm_g1_a, mm_g1_bt); }
static void k_g2(void) { mm_gemm_bf16(c_g2, mm_g2_a, mm_g2_bt); }
static void k_g3(void) { mm_gemm_f32(c_g3, mm_g3_a, mm_g3_bt); }
static void k_v1(void) { mm_gemv_i8(y_v1, mm_v1_w, mm_x8, MM_V1_ROWS, MM_COLS8); }
static void k_v3(void) { mm_gemv_q4(y_v3, mm_v3_w, mm_x8, mm_xs, MM_V3_ROWS, MM_COLS4); }
static void k_v4(void) { mm_gemv_f32(y_v4, mm_v4_w, mm_v4_x, MM_V4_ROWS, MM_COLSF); }
#if MM_V1B_ROWS
static void k_v1b(void) { mm_gemv_i8(y_v1b, mm_v1b_w, mm_x8, MM_V1B_ROWS, MM_COLS8); }
#endif

/* Peak probe: 8 independent add chains, instructions per clock (about 6 on the Cortex-X925). */
static double probe(void) {
    long long ins, cyc;
    uint64_t a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0, h = 0, n = 200000;
    counters_start();
    __asm__ volatile("1:\n .rept 16\n add %0,%0,#1\n add %1,%1,#1\n add %2,%2,#1\n add %3,%3,#1\n"
                     " add %4,%4,#1\n add %5,%5,#1\n add %6,%6,#1\n add %7,%7,#1\n .endr\n"
                     " subs %8,%8,#1\n b.ne 1b\n"
                     : "+r"(a), "+r"(b), "+r"(c), "+r"(d), "+r"(e), "+r"(f), "+r"(g), "+r"(h), "+r"(n) : : "cc");
    counters_stop(&ins, &cyc);
    return cyc > 0 ? (double)ins / (double)cyc : 0;
}

static void measure(const char *name, void (*fn)(void), double macs, double weight_bytes, double min_cycles) {
    double per[7], per_ins[7];
    long long ins, cyc;
    fn();
    counters_start();
    fn();
    counters_stop(&ins, &cyc);
    long reps = (long)(min_cycles / (double)(cyc > 0 ? cyc : 1)) + 1;
    for (int t = 0; t < 7; t++) {
        counters_start();
        for (long r = 0; r < reps; r++) fn();
        counters_stop(&ins, &cyc);
        per[t] = (double)cyc / (double)reps;
        per_ins[t] = (double)ins / (double)reps;
    }
    qsort(per, 7, sizeof per[0], cmp_double);
    qsort(per_ins, 7, sizeof per_ins[0], cmp_double);
    printf("{\"kernel\":\"%s\",\"cycles\":%.0f,\"instructions\":%.0f,\"reps\":%ld,\"macs_per_clk\":%.4f", name, per[3],
           per_ins[3], reps, macs / per[3]);
    if (weight_bytes > 0) printf(",\"bytes_per_clk\":%.4f", weight_bytes / per[3]);
    printf(",\"ipc\":%.3f}\n", per_ins[3] / per[3]);
}

int main(void) {
    fd_ins = perf_open(PERF_COUNT_HW_INSTRUCTIONS);
    fd_cyc = perf_open(PERF_COUNT_HW_CPU_CYCLES);
    if (fd_ins < 0 || fd_cyc < 0) { fprintf(stderr, "no PMU\n"); return 1; }
    /* Ramp the clock: spin for 0.4 s before measuring. */
    {
        static volatile uint64_t sink;
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        do {
            for (uint64_t i = 0; i < 1000000; i++) sink += i;
            clock_gettime(CLOCK_MONOTONIC, &t1);
        } while ((t1.tv_sec - t0.tv_sec) * 1000000000L + (t1.tv_nsec - t0.tv_nsec) < 400000000L);
    }
    mm_results r;
    mm_u64 w[16];
    mm_bench_run(&r);
    unsigned n = mm_words(&r, w);
    printf("{\"cpu\":%d,\"peak_probe_ipc\":%.3f,\"words\":[", sched_getcpu(), probe());
    for (unsigned i = 0; i < n; i++) printf("%s%llu", i ? "," : "", (unsigned long long)w[i]);
    printf("]}\n");
    const double q4_row = MM_COLS4 / MM_QBLOCK * MM_QBYTES, g = (double)MM_G * MM_G * MM_G, cycles = 3e6;
    measure("G1", k_g1, g, 0, cycles);
    measure("G2", k_g2, g, 0, cycles);
    measure("G3", k_g3, g, 0, cycles);
    measure("V1", k_v1, (double)MM_V1_ROWS * MM_COLS8, (double)MM_V1_ROWS * MM_COLS8, cycles);
    measure("V3", k_v3, (double)MM_V3_ROWS * MM_COLS4, MM_V3_ROWS * q4_row, cycles);
    measure("V4", k_v4, (double)MM_V4_ROWS * MM_COLSF, (double)MM_V4_ROWS * MM_COLSF * 4, cycles);
#if MM_V1B_ROWS
    measure("V1b", k_v1b, (double)MM_V1B_ROWS * MM_COLS8, (double)MM_V1B_ROWS * MM_COLS8, cycles);
#endif
    return 0;
}
