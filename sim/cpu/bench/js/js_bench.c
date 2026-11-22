/* SPDX-License-Identifier: MIT
 * QuickJS-ng benchmark harness (run_bench.py --benchmark js; original code). One source for
 * the bare-metal RV64 build and the native laptop reference.
 *
 * Runs the embedded script js_src (js_src.h, made by gen_src.py from kernels.js) in one
 * runtime and context. JavaScript sees two functions:
 *   print(...)  one output line; its bytes are folded into a 64-bit FNV-1a hash of the whole
 *               output, and the line's own FNV-1a hash (newline included) is kept per line;
 *   mark(n)     a phase marker: mailbox word 0 on the cores, a counter reading natively.
 * kernels.js runs every kernel twice and marks 0x10+k (warm call), 0x20+k (timed call) and
 * 0x30+k (end); the timed region of kernel k is 0x20+k to 0x30+k.
 *
 * Mailbox words (bare metal): 1 main's return (start.S), 2 magic "QJSBENCH", 3 output hash,
 * 4 output bytes, 5 exception flag, 6 heap bytes used at the peak, 7 stop reason (8 ASCII
 * bytes) when the shim stopped the run, 8 number of output lines, 9-24 per-line hashes.
 *
 * Native: counters are the CPU's own user-space PMUv3 events 0x08 (INST_RETIRED) and 0x11
 * (CPU_CYCLES), read at every mark. JS_BENCH_RAMP_MS=n first runs dependent adds for n ms
 * (raises the clock) and reports the clock from the cycle counter and from a 64-add chain.
 */
#include <stdint.h>
#include <string.h>
#include "quickjs.h"
#include "js_src.h"

#define FNV_BASIS 0xcbf29ce484222325ull
#define FNV_PRIME 0x100000001b3ull
#define MAX_LINES 16
static uint64_t out_hash = FNV_BASIS, out_bytes, line_hash, line_hashes[MAX_LINES];
static unsigned lines;
static void hash_bytes(const char *p, size_t n) {
    for (size_t i = 0; i < n; i++) {
        out_hash ^= (unsigned char)p[i]; out_hash *= FNV_PRIME;
        line_hash ^= (unsigned char)p[i]; line_hash *= FNV_PRIME;
    }
    out_bytes += n;
}

#ifdef JS_BENCH_NATIVE
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
static double t0;
static int fd_ins = -1, fd_cyc = -1;
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }
/* The PMU that owns this CPU (hybrid hosts have one per core type), raw PMUv3 events. */
static int pmu_open(int ev) {
    int cpu = sched_getcpu(), type = -1;
    for (int n = 0; n < 8 && type < 0; n++) {
        char path[128], buf[256], *p; long lo, hi; int in = 0;
        snprintf(path, sizeof path, "/sys/bus/event_source/devices/armv8_pmuv3_%d/cpus", n);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        if (fgets(buf, sizeof buf, f))
            for (p = buf;;) {
                lo = strtol(p, &p, 10); hi = lo;
                if (*p == '-') hi = strtol(p + 1, &p, 10);
                if (cpu >= lo && cpu <= hi) in = 1;
                if (*p == ',') p++; else break;
            }
        fclose(f);
        if (!in) continue;
        snprintf(path, sizeof path, "/sys/bus/event_source/devices/armv8_pmuv3_%d/type", n);
        f = fopen(path, "r");
        if (f) { if (fscanf(f, "%d", &type) != 1) type = -1; fclose(f); }
    }
    struct perf_event_attr a;
    memset(&a, 0, sizeof a);
    a.size = sizeof a; a.type = type >= 0 ? (unsigned)type : PERF_TYPE_HARDWARE;
    a.config = type >= 0 ? (unsigned)ev : (ev == 8 ? PERF_COUNT_HW_INSTRUCTIONS : PERF_COUNT_HW_CPU_CYCLES);
    a.exclude_kernel = 1; a.exclude_hv = 1;
    return (int)syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}
static long long rd(int fd) { long long v = -1; if (fd >= 0 && read(fd, &v, 8) != 8) v = -1; return v; }
static void emit(const char *p, size_t n) { hash_bytes(p, n); fwrite(p, 1, n, stdout); }
static void marker(int64_t v) {
    long long i = rd(fd_ins), c = rd(fd_cyc);
    fprintf(stderr, "mark 0x%llx t %.9f s ins %lld cyc %lld\n", (long long)v, now() - t0, i, c);
}
#if defined(__aarch64__)
/* 64 dependent adds per step, best of 5 (the 7-Zip and ray-tracing references' clock check). */
static double add_chain_ghz(void) {
    double best = 0;
    for (int trial = 0; trial < 5; trial++) {
        unsigned long long x = 0; long n = 2000000;
        double a = now();
        __asm__ volatile("1:\n.rept 64\nadd %0, %0, #1\n.endr\nsubs %1, %1, #1\nb.ne 1b\n" : "+r"(x), "+r"(n) : : "cc");
        double g = 2000000.0 * 64 / ((now() - a) * 1e9);
        if (g > best) best = g;
    }
    return best;
}
#endif
static void ramp(void) {
    const char *e = getenv("JS_BENCH_RAMP_MS");
    if (!e) return;
    double ms = atof(e), a = now(); long long c0 = rd(fd_cyc);
    volatile unsigned long long x = 0;
    while ((now() - a) * 1e3 < ms) for (int i = 0; i < 100000; i++) x += (unsigned long long)i;
    double dt = now() - a; long long c1 = rd(fd_cyc);
#if defined(__aarch64__)
    double chain = add_chain_ghz();
#else
    double chain = -1;
#endif
    fprintf(stderr, "clock ramp_ms %.1f pmu_ghz %.4f add_chain_ghz %.4f cpu %d\n", dt * 1e3,
            (double)(c1 - c0) / dt / 1e9, chain, sched_getcpu());
}
#else
typedef unsigned long long u64;
extern volatile u64 __bench_mailbox[32];
extern char __bss_end[], __heap_end[];
void shim_heap_init(void *base, size_t size);
extern uint64_t shim_heap_peak;
static void emit(const char *p, size_t n) { hash_bytes(p, n); }
static void marker(int64_t v) { __bench_mailbox[0] = (u64)v; }
void shim_write(int fd, const char *p, size_t n) { (void)fd; hash_bytes(p, n); }
_Noreturn void shim_stop(const char *why) {
    u64 w = 0;
    for (int i = 0; i < 8 && why[i]; i++) w |= (u64)(unsigned char)why[i] << (8 * i);
    __bench_mailbox[3] = out_hash; __bench_mailbox[7] = w;
    for (;;) __asm__ volatile("ebreak");
}
void *malloc(size_t); void free(void *); void *realloc(void *, size_t); void *calloc(size_t, size_t);
size_t malloc_usable_size(void *);
static void *bm_calloc(void *o, size_t a, size_t b) { (void)o; return calloc(a, b); }
static void *bm_malloc(void *o, size_t n) { (void)o; return malloc(n); }
static void bm_free(void *o, void *p) { (void)o; free(p); }
static void *bm_realloc(void *o, void *p, size_t n) { (void)o; return realloc(p, n); }
static size_t bm_usable(const void *p) { return malloc_usable_size((void *)p); }
#endif

static JSValue js_print(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv) {
    (void)this_val;
    line_hash = FNV_BASIS;
    for (int i = 0; i < argc; i++) {
        size_t len; const char *s = JS_ToCStringLen(ctx, &len, argv[i]);
        if (!s) return JS_EXCEPTION;
        if (i) emit(" ", 1);
        emit(s, len);
        JS_FreeCString(ctx, s);
    }
    emit("\n", 1);
    if (lines < MAX_LINES) line_hashes[lines] = line_hash;
    lines++;
    return JS_UNDEFINED;
}
static JSValue js_mark(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv) {
    (void)this_val; int32_t v = 0;
    if (argc > 0 && JS_ToInt32(ctx, &v, argv[0])) return JS_EXCEPTION;
    marker(v);
    return JS_UNDEFINED;
}

int main(void) {
#ifdef JS_BENCH_NATIVE
    fd_ins = pmu_open(8); fd_cyc = pmu_open(0x11);
    t0 = now();
    ramp();
    marker(0);
    JSRuntime *rt = JS_NewRuntime();
#else
    shim_heap_init(__bss_end, (size_t)(__heap_end - __bss_end));
    /* QuickJS's default table reports usable size 0 on unknown platforms, which disables its
       in-place string append and changes GC accounting; report the shim's real sizes, as
       glibc's malloc_usable_size does natively. */
    static const JSMallocFunctions mf = { bm_calloc, bm_malloc, bm_free, bm_realloc, bm_usable };
    JSRuntime *rt = JS_NewRuntime2(&mf, NULL);
#endif
    JS_SetMaxStackSize(rt, 768 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    JSValue g = JS_GetGlobalObject(ctx);
    JS_SetPropertyStr(ctx, g, "print", JS_NewCFunction(ctx, js_print, "print", 1));
    JS_SetPropertyStr(ctx, g, "mark", JS_NewCFunction(ctx, js_mark, "mark", 1));
    JS_FreeValue(ctx, g);
    marker(1);   /* after engine start-up: script parse, compile and every kernel follow */
    JSValue r = JS_Eval(ctx, js_src, sizeof js_src - 1, "bench.js", JS_EVAL_TYPE_GLOBAL);
    marker(2);
    int exc = JS_IsException(r);
    if (exc) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        emit("EXCEPTION: ", 11);
        if (s) { emit(s, strlen(s)); JS_FreeCString(ctx, s); }
        emit("\n", 1);
        JS_FreeValue(ctx, e);
    }
    JS_FreeValue(ctx, r);
#ifdef JS_BENCH_NATIVE
    for (unsigned i = 0; i < lines && i < MAX_LINES; i++)
        fprintf(stderr, "line %u %016llx\n", i, (unsigned long long)line_hashes[i]);
    fprintf(stderr, "hash %016llx bytes %llu lines %u exception %d\n", (unsigned long long)out_hash,
            (unsigned long long)out_bytes, lines, exc);
#else
    __bench_mailbox[2] = 0x48434e45424a5351ull;   /* "QJSBENCH" */
    __bench_mailbox[3] = out_hash;
    __bench_mailbox[4] = out_bytes;
    __bench_mailbox[5] = (u64)exc;
    __bench_mailbox[6] = shim_heap_peak - (uint64_t)(uintptr_t)__bss_end;
    __bench_mailbox[8] = lines;
    for (unsigned i = 0; i < lines && i < MAX_LINES; i++) __bench_mailbox[9 + i] = line_hashes[i];
#endif
    return exc;
}
