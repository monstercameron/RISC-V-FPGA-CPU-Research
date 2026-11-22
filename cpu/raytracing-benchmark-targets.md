# Ray-tracing and path-tracing benchmarks: reference and goal

Set on 2026-11-21 as the project's next benchmark series, after Dhrystone and 7-Zip. It stresses
floating-point and FMA throughput, vector execution with masks, irregular memory access (BVH traversal)
and divergent control flow. The goal the user set is **the user's laptop + 50% performance**, expressed
per clock, as the other benchmarks are: each metric's goal was 1.5 x the laptop's single-thread figure
per clock. **Since 2026-11-22 03:37 the goal is the Apple M6 reference, 1.44 x the laptop per clock (an
estimate; see "Goal (Apple M6 reference)" below).** All figures on this page are native measurements of the laptop; none is a result of our core.

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

### Faster laptop kernels raise the SIMD goal (2026-11-22 00:14; S corrected 00:20)

The SIMD engineer wrote packet and ray-stream kernels for the same BVH4 tree and rays and ran them on
the laptop (vCPU 19, clang 18.1.3 -O2, auto-vectorizer off, 5 runs x 5 passes, every ray checked
against TinyBVH's `BVH4_CPU::Intersect`, 0 mismatches). They are faster than TinyBVH's own kernel, so
the SIMD goal is now 1.5x the laptop's **best** kernel on each ray set, which keeps the comparison
same-algorithm: a gain from a better algorithm counts only if the laptop can't run it as well.

| Ray set | Laptop's best kernel | Laptop per clock | **SIMD goal (1.5x)** | Was (TinyBVH kernel) |
|---|---|---:|---:|---:|
| P, primary | 16-ray packets, NEON (32-ray: 13.1) | 12.1 rays/kclk | **18.2 rays/kclk** | 10.73 |
| S, secondary | ray streams with gather and compaction, SVE2, 16,384-ray streams (SWITCH 4) | 6.00 rays/kclk [5.85-6.08] | **9.0 rays/kclk** | 3.98 |

The scalar goals (6.17 / 2.24 / 2.70 rays/kclk) and the path-tracing goal (563 paths/Mclk) are
unchanged. TinyBVH NEON measured 7.27 / 2.65 in the same session, reproducing the table above. The
S row was first set at 5.18 / 7.8 from 4,096-ray streams; larger streams on the laptop give 6.00
(6.24 in a 3x3 run), so the S goal is 9.0.

## Goal (Apple M6 reference, set 2026-11-22 03:37)

The user decided "M6 everywhere": goals are referenced to Apple's M6 core per clock, single thread. Apple
publishes no M6 microarchitecture or ray-tracing figures, so each goal is a **bridge, an estimate and not a
measurement**: the laptop's per-clock figure on our identical workload (the tables above, unchanged) times the
**Cinebench 2024 single-core per-clock ratio M6 / X925 = 1.44** (M6 221 / 4.78 GHz = 46.2 against the laptop's
131 / 4.1 GHz = 32.0, both Notebookcheck; 1.40 if M6 ran 4.93 GHz). Source:
`build/research/performance-targets.md` (ignored, not committed; Notebookcheck M6, RTX Spark and Dimensity analyses, fetched 2026-11-22). Cinebench 2024 is a SIMD path tracer, so it matches this workload better than Geekbench; the uncertainty
is about +-6% (clocks) plus the workload mismatch. The new goals are about 4% **looser** than the previous 1.5x.

| Metric | Laptop per clock (measured) | Bridge ratio | **M6-referenced goal** | Previous goal (laptop + 50%) |
|---|---:|---:|---:|---:|
| scalar P closest-hit, rays/kclk | 4.110 | 1.44 (Cinebench 2024) | **5.92** | 6.17 |
| scalar S closest-hit | 1.493 | 1.44 | **2.15** | 2.24 |
| scalar S any-hit | 1.802 | 1.44 | **2.59** | 2.70 |
| SIMD P closest-hit (laptop best: 16-ray NEON packets) | 12.1 | 1.44 | **17.4** | 18.2 |
| SIMD S closest-hit (laptop best: SVE2 ray streams) | 6.00 | 1.44 | **8.64** | 9.0 |
| SIMD S any-hit (TinyBVH NEON) | 3.085 | 1.44 | **4.44** | 4.63 |
| RT-P smallpt, paths/Mclk (scalar = SIMD) | 375.5 | 1.44 | **541** | 563 |

The 1.5x goal figures elsewhere on this page are history. `rt_run.py` now scores against this table.

## Baseline on our cores (2026-11-22, soft float)

The scaled workloads (1,024 triangles, 1,024 + 1,024 rays, smallpt 16x12 at 4 spp) run on the
released cores with compiler-rt soft-float builtins (`run_bench.py --benchmark rt`), checked word for
word against the native build. Out-of-order 0.16.2, Verilator, 64 KiB caches: P closest-hit 0.327
rays/kclk, S closest-hit 0.200, S any-hit 0.210, RT-P 15.36 paths/Mclk, that is 3-9% and 2.7% of the
goal. About 70% of RT-T instructions are the soft-float add and multiply routines, so this is a
library-bound baseline; the real comparison starts with F / D (0.17.0) and then RVV.

Comparisons with Apple M5, Intel Panther Lake and AMD Zen 5 on the identical workloads need those
machines; they are not available here, and published numbers for these exact workloads do not exist.

## Where our core stands

Status as of architecture 0.17.4 (updated 2026-11-22 from the [architecture history](architecture.md#history); earlier
text here predated F and D):
1. **Done: RISC-V F and D** in the out-of-order core behind the build define `RV64_OOO_FPU`, default off (0.17.0;
   contract in [architecture.md](architecture.md) section 1), with FP add 2, multiply 3 and FMA 4 clocks (0.17.1)
   and divide 7 / 10, square root 10 / 15 clocks single / double (0.17.2).
2. **Done: the scaled RT-T and RT-P port** (same generators and seeds, fewer triangles, rays and pixels), checked
   against the native checksums; the soft-float baseline is the section above. Hard float, full mode, at 0.17.2
   (unchanged at 0.17.3; RT-P within 0.05% at 0.17.4): flat memory P closest-hit 4.136 rays/kclk, S closest-hit
   2.208, S any-hit 2.225, RT-P 394.6 paths/Mclk; deciding configuration 3.531, 1.907, 1.900 and 375.0. Against
   the scalar M6-referenced goals (5.92, 2.15, 2.59, 541) the deciding configuration is at about 60%, 89%, 73% and
   69%. The flat-memory S closest-hit figure (2.208) is above its goal, but flat memory is not the deciding
   configuration, so it does not count.
3. RVV 1.0 (VLEN 128 / 256 / 512, FP32 FMA pipelines, masks, gather / scatter, compress), with lane
   utilisation, divergence and memory stalls measured.
