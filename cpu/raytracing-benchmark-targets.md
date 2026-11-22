# Ray-tracing and path-tracing benchmarks: reference and goal

Set on 2026-11-21 as the project's next benchmark series, after Dhrystone and 7-Zip. It stresses
floating-point and FMA throughput, vector execution with masks, irregular memory access (BVH traversal)
and divergent control flow. The goal the user set is **the user's laptop + 50% performance**, expressed
per clock, as the other benchmarks are: each metric's goal is 1.5 x the laptop's single-thread figure
per clock. All figures on this page are native measurements of the laptop; none is a result of our core.

## Sources

Fetched from the official sources into the ignored `build/third-party/`; not vendored into the
repository yet.

| Source | Version | Licence | Identity |
|---|---|---|---|
| TinyBVH (Jacco Bikker), github.com/jbikker/tinybvh | 1.9.2, commit `58439efd892f6738f7ffc4e7fcf3cd50ecb9a3b2` (root files only) | MIT, (c) 2024 Jacco Bikker | SHA-256 in `build/rt-bench/results.txt` |
| smallpt (Kevin Beason), kevinbeason.com/smallpt/smallpt.tar.gz | 2008 archive | MIT, (c) 2006-2008 Kevin Beason (LICENSE.txt in the archive) | SHA-256 in `build/rt-bench/results.txt` |

## Workloads

- **RT-T, BVH traversal.** A deterministic scene of 4,096 triangles (a 32 x 32 heightfield plus 8 UV
  spheres, fixed seed) in a binary BVH built with TinyBVH's scalar binned-SAH builder on one thread
  (4,046 nodes, so every build gives the same tree).
  - P: 65,536 coherent primary rays from a 256 x 256 pinhole camera (43,276 hit).
  - S: 65,536 incoherent secondary rays from the P hit points in random hemisphere directions, fixed
    seed (20,067 hit).
  - Kernels: closest-hit and any-hit, on the binary BVH and on TinyBVH's BVH4_CPU.
  - Work per ray on the binary BVH: P 11.6 nodes and 2.0 triangles; S 16.2 nodes and 3.2 triangles.
  - Correctness: hit counts, primitive-ID and distance checksums, identical across every run and build;
    0 hit mismatches between the two BVH kinds.
- **RT-P, Monte Carlo path tracing.** smallpt's Cornell box (diffuse, specular and refractive spheres) at
  128 x 96 and 16 samples per pixel: 196,608 paths, 9.46 segments per path, double precision, one thread,
  `erand48` replaced by the same 48-bit generator in code. Correctness: image hash `1286f2cdca854c44`.

## Laptop measurement (2026-11-21 23:14-23:28)

NVIDIA RTX Spark N1X, one Cortex-X925 (vCPU 19, `taskset`), aarch64 WSL Ubuntu 24.04, clang 18.1.3
`-O2 -std=c++17`, 5 runs per variant, median with the min-max of run medians. "Per clock" uses the CPU's
own cycle counter (640M dependent adds counted 640M cycles); the effective clock was 3.89-3.95 GHz.
(The dependent-add chain used for 7-Zip gives 4.14 GHz; on that basis per-clock figures are 3-5% lower.)

| Build | Metric | Rate | Per clock | AArch64 instructions | **Goal (1.5x per clock)** |
|---|---|---:|---:|---:|---:|
| scalar | RT-T P closest-hit, binary BVH | 16.25 Mrays/s | 4.110 rays/kclk | 990 / ray | **6.17 rays/kclk** (162 clk/ray) |
| scalar | RT-T S closest-hit, BVH4 | 5.83 Mrays/s | 1.493 rays/kclk | 1,393 / ray | **2.24** (447 clk/ray) |
| scalar | RT-T S any-hit, BVH4 | 7.14 Mrays/s | 1.802 rays/kclk | 1,122 / ray | **2.70** |
| SIMD (NEON BVH4) | RT-T P closest-hit, BVH4 | 28.59 Mrays/s | 7.154 rays/kclk | 498 / ray | **10.73** (93 clk/ray) |
| SIMD (NEON BVH4) | RT-T S closest-hit, BVH4 | 10.50 Mrays/s | 2.655 rays/kclk | 594 / ray | **3.98** |
| SIMD (NEON BVH4) | RT-T S any-hit, BVH4 | 12.01 Mrays/s | 3.085 rays/kclk | 416 / ray | **4.63** |
| scalar = SIMD | RT-P smallpt | 1,461 kpaths/s | 375.5 paths/Mclk | 6,339 / path | **563 paths/Mclk** (1,775 clk/path) |

Builds: scalar `-fno-vectorize -fno-slp-vectorize -DTINYBVH_NO_SIMD`; SIMD = TinyBVH's fastest aarch64
kernel (BVH4_CPU with NEON, `tiny_bvh_arm_float.h`) with the auto-vectorizer off, the best of the SIMD
builds tried (with it on, P drops to 6.22 rays/kclk). TinyBVH has no SVE path and its BVH8_CPU needs
AVX2; smallpt has no SIMD path, so its SIMD binary is byte-identical to the scalar one. Under WSL
`taskset` pins a virtual CPU: vCPU 6 reports a Cortex-A725 but measured the same per clock within 1%.

Comparisons with Apple M5, Intel Panther Lake and AMD Zen 5 on the identical workloads need those
machines; they are not available here, and published numbers for these exact workloads do not exist.

## Where our core stands

Our cores implement rv64imb with no F, D or V extension, so these kernels cannot run on them as they are.
The plan, each step its own version:
1. RISC-V F and D (contract proposal `build/cpu/fp/FP-CONTRACT.md`; golden models in progress), with
   realistic latencies (FMA about 4 clocks, add about 3, iterative divide and square root) behind the
   build define `RV64_OOO_FPU`, default off.
2. A scaled RT-T and RT-P port for the simulator (same generators and seeds, fewer triangles, rays and
   pixels), checked against the native checksums; a soft-float build on the released cores gives a
   baseline only.
3. RVV 1.0 (VLEN 128 / 256 / 512, FP32 FMA pipelines, masks, gather / scatter, compress), with lane
   utilisation, divergence and memory stalls measured.
