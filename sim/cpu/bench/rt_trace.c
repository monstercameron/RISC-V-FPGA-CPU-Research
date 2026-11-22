/* SPDX-License-Identifier: MIT
 * RT-T traversal kernels: a C translation of TinyBVH 1.9.2's binary-BVH
 * kernels, BVH::IntersectOctant and BVH::IsOccludedOctant with
 * Moeller-Trumbore TriHit (tiny_bvh_base.h; TinyBVH, Copyright (c) 2024
 * Jacco Bikker, MIT licence, see licenses/TINYBVH-LICENSE.txt), for plain
 * (non-indexed) triangles and one BLAS. Same node order, near-child-first
 * stack, slab test, comparisons and min/max argument order. Differences:
 *   - the octant templates become two index offsets chosen per ray;
 *   - tinybvh_fma(a, b, c) is evaluated as a * b + c without fusion (this file
 *     is built with -ffp-contract=off), as TinyBVH computes it on targets
 *     without FMA contraction; the laptop build fused it, so a few t values
 *     differ in the last bits from rt_export's TinyBVH cross-check;
 *   - the ray is built from O and D here (TinyBVH's Ray constructor, with
 *     tinybvh_safercp for 1/D).
 */
#include "rt_bench.h"

#define RT_FAR 1e30f            /* BVH_FAR */
#define RT_RCP_FAR 0x1p100f     /* BVH_RCP_FAR */
#define RT_STACK 128            /* TINYBVH_STACK_SIZE */

static inline float f32(rt_u32 b) {
    union { rt_u32 u; float f; } v;
    v.u = b;
    return v.f;
}

static inline rt_u32 u32_of(float f) {
    union { rt_u32 u; float f; } v;
    v.f = f;
    return v.u;
}

/* tinybvh_safercp: 1 / x, or +-2^100 (sign of x) when that is not finite or too large. */
static inline float safercp(float x) {
    const float r = 1 / x;
    if (!(f32(u32_of(r) & 0x7fffffffu) <= RT_RCP_FAR)) return f32(u32_of(RT_RCP_FAR) | (u32_of(x) & 0x80000000u));
    return r;
}

static inline float tmin(float a, float b) { return a < b ? a : b; }
static inline float tmax(float a, float b) { return a > b ? a : b; }

typedef struct {
    float ox, oy, oz, dx, dy, dz, rdx, rdy, rdz, nrox, nroy, nroz;
    unsigned nx, ny, nz; /* word offset of the near bound per axis: 0 (aabbMin) or 4 (aabbMax) */
} ray_t;

static inline void make_ray(const rt_u32 *w, ray_t *r) {
    r->ox = f32(w[0]), r->oy = f32(w[1]), r->oz = f32(w[2]);
    r->dx = f32(w[3]), r->dy = f32(w[4]), r->dz = f32(w[5]);
    r->rdx = safercp(r->dx), r->rdy = safercp(r->dy), r->rdz = safercp(r->dz);
    r->nrox = -(r->ox * r->rdx), r->nroy = -(r->oy * r->rdy), r->nroz = -(r->oz * r->rdz);
    r->nx = r->rdx >= 0 ? 0 : 4, r->ny = r->rdy >= 0 ? 0 : 4, r->nz = r->rdz >= 0 ? 0 : 4;
}

/* Moeller-Trumbore (MOLLER_TRUMBORE_TEST); returns 1 and t when hit before tlimit. */
static inline int tri_hit(const ray_t *r, rt_u32 prim, float tlimit, float *thit) {
    const rt_u32 *v = rt_tris + 12 * prim;
    const float v0x = f32(v[0]), v0y = f32(v[1]), v0z = f32(v[2]);
    const float e1x = f32(v[4]) - v0x, e1y = f32(v[5]) - v0y, e1z = f32(v[6]) - v0z;
    const float e2x = f32(v[8]) - v0x, e2y = f32(v[9]) - v0y, e2z = f32(v[10]) - v0z;
    const float hx = r->dy * e2z - r->dz * e2y, hy = r->dz * e2x - r->dx * e2z, hz = r->dx * e2y - r->dy * e2x;
    const float a = e1x * hx + e1y * hy + e1z * hz;
    if (a == 0) return 0;
    const float f = 1 / a;
    const float sx = r->ox - v0x, sy = r->oy - v0y, sz = r->oz - v0z;
    const float u = f * (sx * hx + sy * hy + sz * hz);
    const float qx = sy * e1z - sz * e1y, qy = sz * e1x - sx * e1z, qz = sx * e1y - sy * e1x;
    const float vv = f * (r->dx * qx + r->dy * qy + r->dz * qz);
    if (!(u >= 0 && vv >= 0 && u + vv <= 1)) return 0;
    const float t = f * (e2x * qx + e2y * qy + e2z * qz);
    if (!(t >= 0 && t < tlimit)) return 0;
    *thit = t;
    return 1;
}

/* SLAB_TEST_TWO_NODES for one child: entry distance, or RT_FAR on a miss. */
static inline float slab(const ray_t *r, const rt_u32 *c, float t) {
    const float tx1 = f32(c[0 + r->nx]) * r->rdx + r->nrox;
    const float ty1 = f32(c[1 + r->ny]) * r->rdy + r->nroy;
    const float tz1 = f32(c[2 + r->nz]) * r->rdz + r->nroz;
    const float tx2 = f32(c[4 - r->nx]) * r->rdx + r->nrox;
    const float ty2 = f32(c[5 - r->ny]) * r->rdy + r->nroy;
    const float tz2 = f32(c[6 - r->nz]) * r->rdz + r->nroz;
    const float tn = tmax(tmax(tx1, ty1), tmax(tz1, 0.0f));
    const float tf = tmin(tmin(tx2, ty2), tmin(tz2, t));
    return tf >= tn ? tn : RT_FAR;
}

rt_u32 rt_intersect(const rt_u32 *ray, float *t_out) {
    ray_t r;
    make_ray(ray, &r);
    float t = RT_FAR;
    rt_u32 prim = 0;
    const rt_u32 *node = rt_nodes, *stack[RT_STACK];
    unsigned sp = 0;
    for (;;) {
        const rt_u32 count = node[7];
        if (count > 0) {
            const rt_u32 first = node[3];
            for (rt_u32 i = 0; i < count; i++) {
                const rt_u32 pi = rt_prim[first + i];
                float th;
                if (tri_hit(&r, pi, t, &th)) t = th, prim = pi;
            }
            if (sp == 0) break;
            node = stack[--sp];
            continue;
        }
        const rt_u32 *c1 = rt_nodes + 8 * node[3], *c2 = c1 + 8;
        float d1 = slab(&r, c1, t), d2 = slab(&r, c2, t);
        if (d1 > d2) {
            const float td = d1;
            const rt_u32 *tc = c1;
            d1 = d2, d2 = td, c1 = c2, c2 = tc;
        }
        if (d1 == RT_FAR) {
            if (sp == 0) break;
            node = stack[--sp];
        } else {
            node = c1;
            if (d2 != RT_FAR) stack[sp++] = c2;
        }
    }
    *t_out = t;
    return t < RT_FAR ? prim : 0xffffffffu;
}

int rt_occluded(const rt_u32 *ray) {
    ray_t r;
    make_ray(ray, &r);
    const float t = RT_FAR;
    const rt_u32 *node = rt_nodes, *stack[RT_STACK];
    unsigned sp = 0;
    for (;;) {
        const rt_u32 count = node[7];
        if (count > 0) {
            const rt_u32 first = node[3];
            for (rt_u32 i = 0; i < count; i++) {
                float th;
                if (tri_hit(&r, rt_prim[first + i], t, &th)) return 1;
            }
            if (sp == 0) break;
            node = stack[--sp];
            continue;
        }
        const rt_u32 *c1 = rt_nodes + 8 * node[3], *c2 = c1 + 8;
        float d1 = slab(&r, c1, t), d2 = slab(&r, c2, t);
        if (d1 > d2) {
            const float td = d1;
            const rt_u32 *tc = c1;
            d1 = d2, d2 = td, c1 = c2, c2 = tc;
        }
        if (d1 == RT_FAR) {
            if (sp == 0) break;
            node = stack[--sp];
        } else {
            node = c1;
            if (d2 != RT_FAR) stack[sp++] = c2;
        }
    }
    return 0;
}
