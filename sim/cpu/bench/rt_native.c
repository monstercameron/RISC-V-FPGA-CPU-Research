/* SPDX-License-Identifier: MIT
 * Native harness of the ray-tracing benchmark: runs rt_bench_run() once and
 * prints the mailbox words the bare-metal build writes (rt_runtime.c), as JSON,
 * so rt_run.py can compare the RV64 results with this reference bit for bit.
 * Build it from the same sources with -ffp-contract=off (rt_export.sh).
 */
#include <stdio.h>
#include "rt_bench.h"

void rt_mark(unsigned value) { (void)value; }

static rt_u64 bits(double d) {
    union { double d; rt_u64 u; } v;
    v.d = d;
    return v.u;
}

int main(void) {
    rt_results r;
    rt_bench_run(&r);
    rt_u64 w[18];
    w[0] = RT_MAGIC;
    w[1] = rt_n_tris | (rt_u64)rt_n_nodes << 32;
    w[2] = rt_n_rays;
    const rt_check *c[2] = {&r.p, &r.s};
    for (unsigned k = 0; k < 2; k++) {
        w[3 + 4 * k] = c[k]->hits, w[4 + 4 * k] = c[k]->primsum, w[5 + 4 * k] = c[k]->hash, w[6 + 4 * k] = bits(c[k]->tsum);
    }
    w[11] = r.a.hits, w[12] = r.a.hash, w[13] = r.paths, w[14] = r.segments, w[15] = r.image_hash, w[16] = r.data_hash;
    w[17] = RT_PT_W | (rt_u64)RT_PT_H << 16 | (rt_u64)RT_PT_SPP << 32;
    printf("{\"mailbox\": {");
    for (int i = 0; i < 18; i++) printf("%s\"%d\": %llu", i ? ", " : "", i + 2, (unsigned long long)w[i]);
    printf("}, \"p_tsum\": %.17g, \"s_tsum\": %.17g}\n", r.p.tsum, r.s.tsum);
    return 0;
}
