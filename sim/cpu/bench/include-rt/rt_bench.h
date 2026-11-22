/* SPDX-License-Identifier: MIT
 * Ray-tracing benchmark (RT-T traversal, RT-P path tracing) shared by the
 * bare-metal RV64 build (rt_runtime.c) and the native reference (rt_native.c).
 *
 * The scene, the BVH and both ray sets are made on the host by rt_export.cpp
 * with TinyBVH and written to rt_data.c; the programs only traverse and shade.
 * Phase markers (written to mailbox word 0; tb_bench.sv reports 16-255 as laps):
 *   1     start: RT-T primary rays, closest hit      0x22  RT-P path tracing
 *   0x20  RT-T secondary rays, closest hit           2     stop
 *   0x21  RT-T secondary rays, any hit
 */
#ifndef RT_BENCH_H
#define RT_BENCH_H

typedef unsigned int rt_u32;
typedef unsigned long long rt_u64;

#ifdef __cplusplus
extern "C" {
#endif

enum { RT_MARK_START = 1, RT_MARK_STOP = 2, RT_MARK_S_CLOSEST = 0x20, RT_MARK_S_ANY = 0x21, RT_MARK_PATH = 0x22 };
#define RT_MAGIC 0x31484342544e4552ull /* "RENTBCH1" little-endian */

/* rt_data.c (generated). A node is TinyBVH's 32-byte BVH::BVHNode: aabbMin.xyz,
 * leftFirst, aabbMax.xyz, triCount, as bit patterns. A triangle is three
 * bvhvec4 (x, y, z, unused). A ray is O.xyz, D.xyz. */
extern const rt_u32 rt_n_tris, rt_n_nodes, rt_n_rays;
extern const rt_u32 rt_tris[];  /* 12 words per triangle */
extern const rt_u32 rt_nodes[]; /* 8 words per node */
extern const rt_u32 rt_prim[];  /* rt_n_tris entries */
extern const rt_u32 rt_rays_p[], rt_rays_s[]; /* 6 words per ray */

typedef struct {
    rt_u32 hits;
    rt_u64 primsum, hash;
    double tsum;
} rt_check;

typedef struct {
    rt_check p, s, a;
    rt_u64 paths, segments, image_hash, data_hash;
} rt_results;

/* Provided by the harness: record a phase marker. */
void rt_mark(unsigned value);

/* rt_trace.c */
rt_u32 rt_intersect(const rt_u32 *ray, float *t);   /* closest hit: prim or 0xffffffff */
int rt_occluded(const rt_u32 *ray);                 /* any hit, t = far */

/* smallpt_rt.cpp: render w x h at 4*samps samples per pixel into the static
 * image (sets paths and segments); hash of that image's doubles. */
void rt_smallpt(int w, int h, int samps, rt_results *r);
rt_u64 rt_smallpt_hash(int w, int h);

/* rt_bench.c: one benchmark pass with markers. */
void rt_bench_run(rt_results *r);

#ifdef __cplusplus
}
#endif

#ifndef RT_PT_W
#define RT_PT_W 16
#endif
#ifndef RT_PT_H
#define RT_PT_H 12
#endif
#ifndef RT_PT_SPP
#define RT_PT_SPP 4
#endif

#endif
