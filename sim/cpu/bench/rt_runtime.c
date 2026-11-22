/* SPDX-License-Identifier: MIT
 * Bare-metal harness of the ray-tracing benchmark (include-rt/rt_bench.h):
 * main(), phase markers and the result mailbox. Results (mailbox words):
 *   2  magic                    13 any hit: occluded rays     19 RT-P w | h << 16 | spp << 32
 *   3  triangles | nodes << 32  14 any hit: hash
 *   4  rays per set             15 RT-P paths
 *   5-8   primary: hits, prim sum, hash, distance sum (double bits)
 *   9-12  secondary: the same   16 RT-P segments (rays cast)
 *                               17 RT-P image hash, 18 input data hash
 * memcpy and memset are here for the compiler's block copies and clears.
 */
#include "bench.h"
#include "rt_bench.h"

typedef __SIZE_TYPE__ size_t;

void *memcpy(void *destination, const void *source, size_t count) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    while (count--) *out++ = *in++;
    return destination;
}

void *memset(void *destination, int value, size_t count) {
    unsigned char *out = destination;
    while (count--) *out++ = (unsigned char)value;
    return destination;
}

void rt_mark(unsigned value) { bench_marker(value); }

static rt_u64 bits(double d) {
    union { double d; rt_u64 u; } v;
    v.d = d;
    return v.u;
}

int main(void) {
    rt_results r;
    rt_bench_run(&r);
    bench_result(0, RT_MAGIC);
    bench_result(1, rt_n_tris | (rt_u64)rt_n_nodes << 32);
    bench_result(2, rt_n_rays);
    const rt_check *c[2] = {&r.p, &r.s};
    for (unsigned k = 0; k < 2; k++) {
        bench_result(3 + 4 * k, c[k]->hits);
        bench_result(4 + 4 * k, c[k]->primsum);
        bench_result(5 + 4 * k, c[k]->hash);
        bench_result(6 + 4 * k, bits(c[k]->tsum));
    }
    bench_result(11, r.a.hits);
    bench_result(12, r.a.hash);
    bench_result(13, r.paths);
    bench_result(14, r.segments);
    bench_result(15, r.image_hash);
    bench_result(16, r.data_hash);
    bench_result(17, RT_PT_W | (rt_u64)RT_PT_H << 16 | (rt_u64)RT_PT_SPP << 32);
    return 0;
}
