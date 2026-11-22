// SPDX-License-Identifier: MIT
// Host tool of the ray-tracing benchmark: builds the RT-T scene, its BVH and
// both ray sets with TinyBVH, and writes them as rt_data.c for the bare-metal
// and native builds (rt_export.sh). Same generator and seeds as the laptop
// reference (build/rt-bench/rt_bench.cpp, 2026-11-21); with --grid 32
// --spheres 8 --image 256 it reproduces that workload exactly (4,096
// triangles, 65,536 + 65,536 rays; its scene and ray-set hashes are printed).
//   scene   heightfield GRID x GRID cells over [-8,8]^2 (2 triangles per cell)
//           + SPHERES UV spheres of 256 triangles; xorshift32 seed 0x2545F491
//   BVH     TinyBVH binary BVH, scalar reference binned-SAH builder, one thread
//   P rays  IMAGE x IMAGE pinhole camera, eye (0,9,-12), target (0,0.5,0.5), 60 deg
//   S rays  from each P hit (TinyBVH closest hit, as on the laptop) + 1e-3 x facing
//           normal into a uniform hemisphere; for a miss from a random point in the
//           scene box into a uniform sphere; xorshift32 seed 0x9E3779B9
// It also prints, as JSON, TinyBVH's own closest-hit and any-hit checksums
// (binary BVH, the laptop build's fused arithmetic) and the work per ray, for
// the cross-check with the portable kernel in rt_trace.c.
// TinyBVH 1.9.2 (commit 58439efd892f6738f7ffc4e7fcf3cd50ecb9a3b2, MIT, Copyright
// (c) 2024 Jacco Bikker) is included from build/third-party/tinybvh, not vendored.
// Usage: rt_export --grid G --spheres N --image S --out DIR
#define NO_THREADED_BUILDS
#define TINYBVH_IMPLEMENTATION
#include "tiny_bvh.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>

using namespace tinybvh;

static uint32_t rng_state;
static inline uint32_t xs32() { uint32_t x = rng_state; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return rng_state = x; }
static inline float rnd() { return (xs32() >> 8) * (1.0f / 16777216.0f); }

static int GRID = 16, NSPH = 2, IMG = 32;
static const int LON = 16, LAT = 9;
static std::vector<bvhvec4> tri;
static void emit(bvhvec3 a, bvhvec3 b, bvhvec3 c) {
    tri.push_back(bvhvec4(a.x, a.y, a.z, 0)); tri.push_back(bvhvec4(b.x, b.y, b.z, 0)); tri.push_back(bvhvec4(c.x, c.y, c.z, 0));
}

static void build_scene() {
    rng_state = 0x2545F491u;
    std::vector<float> h((GRID + 1) * (GRID + 1));
    for (int j = 0; j <= GRID; j++) for (int i = 0; i <= GRID; i++) {
        const float x = -8 + 16.0f * i / GRID, z = -8 + 16.0f * j / GRID;
        h[j * (GRID + 1) + i] = 0.4f * sinf(0.7f * x) * cosf(0.5f * z) + 0.1f * rnd();
    }
    auto H = [&](int j, int i) { return h[j * (GRID + 1) + i]; };
    for (int j = 0; j < GRID; j++) for (int i = 0; i < GRID; i++) {
        const float x0 = -8 + 16.0f * i / GRID, x1 = -8 + 16.0f * (i + 1) / GRID;
        const float z0 = -8 + 16.0f * j / GRID, z1 = -8 + 16.0f * (j + 1) / GRID;
        const bvhvec3 a(x0, H(j, i), z0), b(x1, H(j, i + 1), z0), c(x1, H(j + 1, i + 1), z1), d(x0, H(j + 1, i), z1);
        emit(a, b, c); emit(a, c, d);
    }
    for (int s = 0; s < NSPH; s++) {
        const float r = 0.8f + 1.0f * rnd();
        const bvhvec3 ctr(-6 + 12 * rnd(), 0.4f + r + 1.5f * rnd(), -6 + 12 * rnd());
        auto P = [&](int la, int lo) {
            const float th = 3.14159265f * la / LAT, ph = 6.28318531f * lo / LON;
            return bvhvec3(ctr.x + r * sinf(th) * cosf(ph), ctr.y + r * cosf(th), ctr.z + r * sinf(th) * sinf(ph));
        };
        for (int lo = 0; lo < LON; lo++) {
            emit(P(0, 0), P(1, lo), P(1, lo + 1));
            for (int la = 1; la < LAT - 1; la++) { emit(P(la, lo), P(la + 1, lo), P(la + 1, lo + 1)); emit(P(la, lo), P(la + 1, lo + 1), P(la, lo + 1)); }
            emit(P(LAT - 1, lo), P(LAT, 0), P(LAT - 1, lo + 1));
        }
    }
}

struct RaySet { std::vector<bvhvec3> O, D; };
static uint64_t fnv(const void* p, size_t n, uint64_t h = 1469598103934665603ull) {
    const unsigned char* b = (const unsigned char*)p;
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ull; }
    return h;
}
static uint64_t rayset_hash(const RaySet& r) {
    uint64_t h = fnv(r.O.data(), r.O.size() * sizeof(bvhvec3));
    return fnv(r.D.data(), r.D.size() * sizeof(bvhvec3), h);
}

static void primary_rays(RaySet& rs) {
    const bvhvec3 eye(0, 9, -12), at(0, 0.5f, 0.5f);
    const bvhvec3 fwd = tinybvh_normalize(at - eye);
    const bvhvec3 right = tinybvh_normalize(tinybvh_cross(bvhvec3(0, 1, 0), fwd));
    const bvhvec3 up = tinybvh_cross(fwd, right);
    const float tn = 0.57735027f;
    for (int y = 0; y < IMG; y++) for (int x = 0; x < IMG; x++) {
        const float u = (2.0f * (x + 0.5f) / IMG - 1) * tn, v = (1 - 2.0f * (y + 0.5f) / IMG) * tn;
        rs.O.push_back(eye);
        rs.D.push_back(tinybvh_normalize(fwd + right * u + up * v));
    }
}

static bvhvec3 rand_dir() {
    const float z = 2 * rnd() - 1, ph = 6.28318531f * rnd(), s = sqrtf(fmaxf(0.0f, 1 - z * z));
    return bvhvec3(s * cosf(ph), s * sinf(ph), z);
}

static void secondary_rays(const BVH& bvh, const RaySet& p, RaySet& rs) {
    rng_state = 0x9E3779B9u;
    const int n = IMG * IMG;
    for (int i = 0; i < n; i++) {
        Ray r(p.O[i], p.D[i]);
        bvh.Intersect(r);
        if (r.hit.t < BVH_FAR) {
            const uint32_t k = r.hit.prim;
            const bvhvec3 v0 = tri[k * 3], v1 = tri[k * 3 + 1], v2 = tri[k * 3 + 2];
            bvhvec3 nrm = tinybvh_normalize(tinybvh_cross(v1 - v0, v2 - v0));
            if (tinybvh_dot(nrm, p.D[i]) > 0) nrm = nrm * -1.0f;
            bvhvec3 d = rand_dir();
            if (tinybvh_dot(d, nrm) < 0) d = d * -1.0f;
            rs.O.push_back(p.O[i] + p.D[i] * r.hit.t + nrm * 1e-3f);
            rs.D.push_back(d);
        } else {
            rs.O.push_back(bvhvec3(-8 + 16 * rnd(), 0.6f + 3.4f * rnd(), -8 + 16 * rnd()));
            rs.D.push_back(rand_dir());
        }
    }
}

static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }

static void words(FILE* f, const char* decl, const std::vector<uint32_t>& w) {
    fprintf(f, "%s = {", decl);
    for (size_t i = 0; i < w.size(); i++) fprintf(f, "%s0x%08x,", i % 8 ? "" : "\n", w[i]);
    fprintf(f, "\n};\n");
}

static void ray_words(const RaySet& rs, std::vector<uint32_t>& w) {
    for (size_t i = 0; i < rs.O.size(); i++) {
        const float v[6] = {rs.O[i].x, rs.O[i].y, rs.O[i].z, rs.D[i].x, rs.D[i].y, rs.D[i].z};
        for (float x : v) w.push_back(bits(x));
    }
}

int main(int argc, char** argv) {
    const char* out = ".";
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--grid")) GRID = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--spheres")) NSPH = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--image")) IMG = atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--out")) out = argv[i + 1];
        else { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
    }
    if (GRID < 1 || NSPH < 0 || IMG < 1) { fprintf(stderr, "bad sizes\n"); return 2; }
    build_scene();
    const uint32_t ntri = (uint32_t)(tri.size() / 3), nrays = (uint32_t)(IMG * IMG);
    BVH bvh;
    bvh.settings.useSIMDifavailable = false;
    bvh.settings.enableThreading = false;
    bvh.Build(tri.data(), ntri);
    RaySet P, S;
    primary_rays(P);
    secondary_rays(bvh, P, S);

    std::vector<uint32_t> wt, wn, wp, wrp, wrs;
    for (const bvhvec4& v : tri) { wt.push_back(bits(v.x)); wt.push_back(bits(v.y)); wt.push_back(bits(v.z)); wt.push_back(bits(v.w)); }
    for (uint32_t i = 0; i < bvh.usedNodes; i++) {
        const BVH::BVHNode& n = bvh.bvhNode[i];
        const uint32_t w8[8] = {bits(n.aabbMin.x), bits(n.aabbMin.y), bits(n.aabbMin.z), n.leftFirst,
                                bits(n.aabbMax.x), bits(n.aabbMax.y), bits(n.aabbMax.z), n.triCount};
        wn.insert(wn.end(), w8, w8 + 8);
    }
    for (uint32_t i = 0; i < ntri; i++) wp.push_back(bvh.primIdx[i]);
    ray_words(P, wrp);
    ray_words(S, wrs);

    const std::string path = std::string(out) + "/rt_data.c";
    FILE* f = fopen(path.c_str(), "w");
    if (!f) { perror(path.c_str()); return 1; }
    fprintf(f, "/* Generated by rt_export (grid %d, spheres %d, image %d): RT-T scene, TinyBVH BVH and rays.\n"
               " * Bit patterns of the floats; see include-rt/rt_bench.h. */\n#include \"rt_bench.h\"\n", GRID, NSPH, IMG);
    fprintf(f, "const rt_u32 rt_n_tris = %u, rt_n_nodes = %u, rt_n_rays = %u;\n", ntri, bvh.usedNodes, nrays);
    words(f, "const rt_u32 rt_tris[]", wt);
    words(f, "const rt_u32 rt_nodes[]", wn);
    words(f, "const rt_u32 rt_prim[]", wp);
    words(f, "const rt_u32 rt_rays_p[]", wrp);
    words(f, "const rt_u32 rt_rays_s[]", wrs);
    fclose(f);

    // TinyBVH's own results on the same data (cross-check), and the work per ray.
    printf("{\"grid\": %d, \"spheres\": %d, \"image\": %d, \"tris\": %u, \"nodes\": %u, \"rays\": %u,\n", GRID, NSPH, IMG, ntri, bvh.usedNodes, nrays);
    printf(" \"scene_hash\": \"%016llx\", \"primary_hash\": \"%016llx\", \"secondary_hash\": \"%016llx\",\n",
           (unsigned long long)fnv(tri.data(), tri.size() * sizeof(bvhvec4)), (unsigned long long)rayset_hash(P), (unsigned long long)rayset_hash(S));
    const char* names[2] = {"P", "S"};
    for (int set = 0; set < 2; set++) {
        const RaySet& rs = set ? S : P;
        uint32_t hits = 0; uint64_t primsum = 0, hash = 1469598103934665603ull; double tsum = 0;
        std::vector<uint32_t> prims(nrays);
        for (uint32_t i = 0; i < nrays; i++) {
            Ray r(rs.O[i], rs.D[i]);
            bvh.Intersect(r);
            const uint32_t pr = r.hit.t < BVH_FAR ? r.hit.prim : 0xFFFFFFFFu;
            if (pr != 0xFFFFFFFFu) { hits++; primsum += pr; tsum += r.hit.t; }
            hash = (hash ^ pr) * 1099511628211ull;
        }
        double nodes = 0, tris = 0;
        const float ct = bvh.c_trav, ci = bvh.c_int;
        bvh.c_trav = 1; bvh.c_int = 0;
        for (uint32_t i = 0; i < nrays; i++) { Ray r(rs.O[i], rs.D[i]); nodes += bvh.Intersect(r); }
        bvh.c_trav = 0; bvh.c_int = 1;
        for (uint32_t i = 0; i < nrays; i++) { Ray r(rs.O[i], rs.D[i]); tris += bvh.Intersect(r); }
        bvh.c_trav = ct; bvh.c_int = ci;
        printf(" \"tinybvh_%s_closest\": {\"hits\": %u, \"primsum\": %llu, \"hash\": %llu, \"tsum\": %.17g, "
               "\"node_visits_per_ray\": %.4f, \"tri_tests_per_ray\": %.4f},\n",
               names[set], hits, (unsigned long long)primsum, (unsigned long long)hash, tsum, nodes / nrays, tris / nrays);
    }
    {
        uint32_t occ = 0; uint64_t hash = 1469598103934665603ull;
        for (uint32_t i = 0; i < nrays; i++) {
            Ray r(S.O[i], S.D[i]);
            const uint32_t o = bvh.IsOccluded(r) ? 1u : 0u;
            occ += o; hash = (hash ^ o) * 1099511628211ull;
        }
        printf(" \"tinybvh_S_anyhit\": {\"hits\": %u, \"hash\": %llu}}\n", occ, (unsigned long long)hash);
    }
    return 0;
}
