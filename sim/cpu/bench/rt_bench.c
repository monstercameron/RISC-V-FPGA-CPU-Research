/* SPDX-License-Identifier: MIT
 * One pass of the ray-tracing benchmark (include-rt/rt_bench.h): RT-T closest
 * hit on the primary and secondary rays, any hit on the secondary rays, then
 * RT-P (smallpt). The checksums are the ones the laptop reference build
 * (build/rt-bench, 2026-11-21) prints: hits, sum of hit primitive ids, FNV-1a
 * style hash of every ray's primitive id (0xffffffff for a miss), and the sum
 * of hit distances in double precision.
 */
#include "rt_bench.h"

#define FNV_OFFSET 1469598103934665603ull
#define FNV_PRIME 1099511628211ull

static rt_u64 fnv_words(const rt_u32 *w, rt_u64 n, rt_u64 h) {
    for (rt_u64 i = 0; i < n; i++)
        for (unsigned b = 0; b < 32; b += 8) h = (h ^ ((w[i] >> b) & 0xff)) * FNV_PRIME;
    return h;
}

static void trace_closest(const rt_u32 *rays, rt_check *c) {
    c->hits = 0, c->primsum = 0, c->hash = FNV_OFFSET, c->tsum = 0;
    for (rt_u32 i = 0; i < rt_n_rays; i++) {
        float t;
        const rt_u32 prim = rt_intersect(rays + 6 * i, &t);
        if (prim != 0xffffffffu) {
            c->hits++;
            c->primsum += prim;
            c->tsum += t;
        }
        c->hash = (c->hash ^ prim) * FNV_PRIME;
    }
}

static void trace_any(const rt_u32 *rays, rt_check *c) {
    c->hits = 0, c->primsum = 0, c->hash = FNV_OFFSET, c->tsum = 0;
    for (rt_u32 i = 0; i < rt_n_rays; i++) {
        const rt_u32 o = rt_occluded(rays + 6 * i) ? 1u : 0u;
        c->hits += o;
        c->hash = (c->hash ^ o) * FNV_PRIME;
    }
}

void rt_bench_run(rt_results *r) {
    /* Input check before the timed region: the image holds the exported data. */
    rt_u64 h = fnv_words(rt_tris, 12ull * rt_n_tris, FNV_OFFSET);
    h = fnv_words(rt_nodes, 8ull * rt_n_nodes, h);
    h = fnv_words(rt_prim, rt_n_tris, h);
    h = fnv_words(rt_rays_p, 6ull * rt_n_rays, h);
    r->data_hash = fnv_words(rt_rays_s, 6ull * rt_n_rays, h);
    rt_mark(RT_MARK_START);
    trace_closest(rt_rays_p, &r->p);
    rt_mark(RT_MARK_S_CLOSEST);
    trace_closest(rt_rays_s, &r->s);
    rt_mark(RT_MARK_S_ANY);
    trace_any(rt_rays_s, &r->a);
    rt_mark(RT_MARK_PATH);
    rt_smallpt(RT_PT_W, RT_PT_H, RT_PT_SPP / 4, r);
    rt_mark(RT_MARK_STOP);
    r->image_hash = rt_smallpt_hash(RT_PT_W, RT_PT_H);
}
