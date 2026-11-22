# Ternary-weight GEMV benchmark: workloads, laptop reference and baseline

`run_bench.py --benchmark ternary` runs BitNet b1.58-style ternary-weight matrix-vector kernels on the
RTL (bench-only change, no CPU version). **Goal: the Apple M6 reference, set 2026-11-22 03:37 (estimates; see "Goal (Apple M6 reference)").** Every baseline number below is a
measurement; the measured baseline is on 0.17.2 (out-of-order core) at the commit named in DEVLOG.

## Sources and licences

All code is original MIT work with SPDX headers (`sim/cpu/bench/ternary/`, `ternary_run.py`). The
formats follow published ideas; nothing is copied.

| Idea | Source (read, not copied) | Licence of the source |
|---|---|---|
| I2_S: 2-bit codes, multiply, subtract the activation sum | microsoft/BitNet `src/ggml-bitnet-mad.cpp` | MIT |
| TQ1_0: 5 trits per byte, byte = ceil(base-3 value x 256 / 243) | llama.cpp PR 8151, `ggml-common.h` | MIT |
| Table-lookup maps (256-entry sums per 5 activations) | T-MAC (arXiv 2407.00088), bitnet.cpp TL kernels (arXiv 2502.11880) | MIT |
| Model shape | BitNet b1.58 2B4T (arXiv 2504.12285; hidden 2560, FFN 6912) | MIT (weights not used) |

Weights are **synthetic** (a hash gives each trit, uniform in -1, 0, +1) and activations are hashed int8
in [-127, 127]. No model weights or binaries are downloaded. Details: `build/research/bitnet-ternary.md`.

## Workloads

| Name | Layers (M x K) | Weights | Packed size per kernel |
|---|---|---|---|
| T-small | 256x1280, 512x1024, 128x2560 | 1,179,648 | 0.26-0.29 MB |
| T-2B4T | 3840x2560 (QKV), 2560x2560 (O), 13824x2560 (gate+up), 2560x6912 (down) | 69,468,160 | 14-17 MB |

Kernels (scalar, integer, int8 activations, exact int32 outputs):

| Kernel | Map | Bits per weight |
|---|---|---|
| `i2` | 2-bit codes (w+1), four multiplies per byte, minus the activation sum | 2 |
| `lut5w` | 5 trits per byte (TQ1_0 order); per 320 weights a 32 KiB table of int16 sums; 8 index bytes per 64-bit load | 1.6 (+K padded to 320) |
| `bs8` | two 64-bit planes (+1, -1) per 64 weights against 8 activation bit planes, `cpop` (Zbb) | 2 |
| `stream` | probe: sum of 64-bit words over each layer's `i2` bytes (after the touch pass) | - |
| `streamall` | probe: the whole T-small `i2` blob (295 KB), no touch pass, run first so it reads cold memory | - |

Table building (`lut5w`) and the activation bit-plane transpose (`bs8`) are inside the timed call.
RVV variants are not written; the kernel set is a bit mask in `tern_bench.c`
(`TERN_KERNELS`), and `tern_kernels.h` is the place for `__riscv_vector` kernels later.

**Packing and checks.** `sim/cpu/bench/ternary/tern_export.py SHAPE KERNELS` builds `tern_gen.c`
natively, packs every layout, computes reference outputs by plain int8 multiply-accumulate straight
from the trits, checks that the three native kernels equal it, and writes `ternary_data.S`
(`.incbin` blobs, descriptor table) plus `expected.json` and `export.json` (tools, SHA-256). The core
never packs. The RISC-V program compares every output with the reference outputs, writes FNV-1a
checksums to the mailbox, and `ternary_run.py` requires rv_iss and the RTL timing run to equal the
native words (T-small layer checksums match the research prototype's). Each call is preceded by an
untimed touch (one load per 64-byte line of its weights): with an L2 that holds the layer the weights
are L2-resident; with a smaller L2 they stream.

Builds are `rv64im` or `rv64imb` (integer, runs on the released integer cores; `rv64im` uses a
software popcount). No F, D or V is needed; `--fpu` is not required.

```sh
python3 -B sim/cpu/bench/ternary/tern_export.py small i2,lut5w,bs8      # or 2b4t i2,lut5w,bs8
python3 -B sim/cpu/bench/build_bench.py --benchmark ternary [--tern-kernels i2,lut5w]
python3 -B sim/cpu/bench/run_bench.py --benchmark ternary --core ooo --sim verilator   # full mode up to 12 M instructions
python3 -B sim/cpu/bench/run_bench.py --benchmark ternary --core ooo --sim verilator --tern-mode sampled --sample-pieces 1
python3 -B sim/cpu/bench/ternary/tern_laptop.py --runs 9                 # laptop reference (aarch64)
```

T-small in full mode is 11.2 M instructions; at the deciding configuration one build per kernel
(`--tern-kernels i2`, and so on) runs in 20-60 s, the all-kernel flat run in 107 s. T-2B4T is
552 M instructions on rv_iss (checked) and runs sampled (`--tern-mode sampled`), one piece of
150,000 instructions per call here, so its RTL numbers are single-piece estimates.

## Laptop reference

Cortex-X925 (vCPU 19 under `taskset`), aarch64 WSL Ubuntu 24.04, kernel 6.18.33.2, Ubuntu clang 18.1.3
`-O2 -fno-vectorize -fno-slp-vectorize -march=armv8.2-a+dotprod`, measured 2026-11-22 03:24-03:25 with
the user-space PMUv3 counters (CPU_CYCLES 0x11, INST_RETIRED 0x08). Each process ramps the clock for
2 s, then repeats each kernel for at least 20 ms (resident) or evicts with a 256 MiB sweep and times
one call (cold, T-2B4T). T-small: 9 runs, T-2B4T: 7 runs; median [min-max]. The host load average was
17-18 on 20 CPUs, so the ranges are wide (min values are interference; the clock read 3.0-3.4 GHz by
wall time against 3.7 GHz when quiet). `ndot` is the NEON SDOT kernel, for context only. Output of all
kernels equals the reference (0 mismatches). Raw: `ternary-laptop/laptop.json`.

| Shape / mode | Kernel | Weights per clock | Bytes per clock | AArch64 instr per weight |
|---|---|---|---|---|
| T-small resident | i2 | 0.988 [0.910-1.000] | 0.247 | 4.03 |
| | lut5w | 3.10 [2.21-3.22] | 0.690 | 2.04 |
| | bs8 | 3.11 [2.33-3.18] | 0.778 | 1.88 |
| | ndot (SDOT) | 20.9 [18.5-22.0] | 5.24 | 0.26 |
| | stream probe | - | 18.5 [17.4-19.0] | - |
| T-2B4T resident | i2 | 0.954 [0.882-0.976] | 0.238 | 4.01 |
| | lut5w | 5.33 [5.01-5.66] | 1.07 | 1.14 |
| | bs8 | 3.38 [3.15-3.66] | 0.845 | 1.66 |
| | ndot (SDOT) | 17.7 [15.3-18.3] | 4.42 | 0.26 |
| T-2B4T cold (DRAM) | i2 | 0.959 [0.899-0.988] | 0.240 | 4.01 |
| | lut5w | 4.52 [4.08-4.82] | 0.909 | 1.14 |
| | bs8 | 3.46 [2.31-3.83] | 0.865 | 1.66 |
| | ndot (SDOT) | 15.8 [10.5-18.2] | 3.96 | 0.26 |
| | stream probe | - | 7.10 [6.25-9.08] | - |

## Goal (Apple M6 reference, set 2026-11-22 03:37)

The user decided "M6 everywhere": goals are referenced to Apple's M6 core per clock, single thread. Apple
publishes no M6 microarchitecture, so every goal here is a **bridge or a different-chip figure, an estimate and
not a measurement**. Source: `build/research/performance-targets.md` (ignored, not committed; Notebookcheck M6 and RTX Spark analyses, fetched 2026-11-22).

**Scalar kernels: 1.30 x the laptop's weights per clock** (laptop table above, unchanged), the Geekbench 6
single-core per-clock ratio M6 / X925 (983 / 755; Notebookcheck). The report has no integer-kernel-specific
bridge; uncertainty about +-6% plus workload mismatch. `ternary_run.py` records these as `goal_reference`.
T-small is compared with the resident row, T-2B4T with the cold (DRAM) row, the regime our sampled run sees.

| Shape / mode | Kernel | Laptop weights/clk (measured) | Bridge ratio | **M6-referenced goal, weights/clk** | Previous goal |
|---|---|---:|---:|---:|---|
| T-small resident | i2 | 0.988 | 1.30 | **1.28** | none |
| T-small resident | lut5w | 3.1 | 1.30 | **4.03** | none |
| T-small resident | bs8 | 3.11 | 1.30 | **4.04** | none |
| T-2B4T cold (DRAM) | i2 | 0.959 | 1.30 | **1.25** | none |
| T-2B4T cold (DRAM) | lut5w | 4.52 | 1.30 | **5.88** | none |
| T-2B4T cold (DRAM) | bs8 | 3.46 | 1.30 | **4.5** | none |

**Decode / streaming bandwidth goal: 20-32 bytes per clock from DRAM, single core.** Source: the report's row 12,
Apple M1 Max about 102 GB/s from one thread (AnandTech 2021, via search; about 32 B/clk) and M4 Max about
92 GB/s (a forum figure, unverified; about 20 B/clk). Both are older chips and the clock divisor is an
assumption, so the confidence is medium-low and **M6 is unpublished**. The laptop's cold stream probe measured
7.10 B/clk (resident 18.5). Our deciding configuration (`N_MISS` 4) measures **0.17 B/clk**, about 0.5-0.9% of
the goal and 2.4% of the laptop; `N_MISS` 8 measures 0.54. At 350 clocks of latency the goal needs about 11 KiB
(about 175 lines) in flight (Little's law, the report's arithmetic), so it is a memory-level-parallelism target.

## Baseline on 0.17.2 (out-of-order core, rv64imb, 64 KiB L1s, N_MISS as stated, one build)

T-small, full mode (exact clocks, whole program from reset), results PASS against the native reference
(rv_iss and RTL mailbox). Deciding configuration = `--ld-lat 4 --l0 16 --l2-lat 20 --mem-lat 350
--n-miss 4 --mem-gap 8` with the L2 size stated.

| Memory regime | Kernel | Clocks | Instructions | IPC | Weights per clock | Bytes per clock |
|---|---|---|---|---|---|---|
| flat (default SoC) | i2 | 571,223 | 6,517,499 | 11.41 | 2.065 | 0.516 |
| | lut5w | 403,595 | 2,820,082 | 6.99 | 2.923 | 0.650 |
| | bs8 | 164,282 | 1,538,936 | 9.37 | 7.181 | 1.795 |
| | stream | 134,412 | 92,226 | 0.69 | - | 2.194 |
| deciding, L2 4 MiB (L2-resident) | i2 | 813,792 | 6,517,487 | 8.01 | 1.450 | 0.362 |
| | lut5w | 541,410 | 2,820,067 | 5.21 | 2.179 | 0.484 |
| | bs8 | 324,145 | 1,538,924 | 4.75 | 3.639 | 0.910 |
| | stream | 223,906 | 92,222 | 0.41 | - | 1.317 |
| deciding, L2 32 KiB (forced streaming) | i2 | 2,348,832 | 6,517,487 | 2.77 | 0.502 | 0.126 |
| | lut5w | 1,942,524 | 2,820,067 | 1.45 | 0.607 | 0.135 |
| | bs8 | 1,828,611 | 1,538,924 | 0.84 | 0.645 | 0.161 |
| | stream | 1,553,904 | 92,222 | 0.06 | - | 0.190 |

T-2B4T, sampled (one 150,000-instruction piece per call, 20,000-instruction warm-up, cold caches, so single-piece
estimates; flat and deciding config with L2 4 MiB, which cannot hold a 1.6-8.8 MB layer, so the pieces stream):

| Regime | Kernel | Clocks (whole layer) | IPC | Weights per clock | Bytes per clock |
|---|---|---|---|---|---|
| flat | i2 | 34.8 M | 10.98 | 1.995 | 0.499 |
| | lut5w | 15.5 M | 5.11 | 4.473 | 0.899 |
| | bs8 | 8.77 M | 8.54 | 7.922 | 1.981 |
| deciding | i2 | 144 M | 2.65 | 0.481 | 0.120 |
| | lut5w | 66.4 M | 1.20 | 1.046 | 0.210 |
| | bs8 | 106 M | 0.71 | 0.657 | 0.164 |

Sampling is not free: T-small `lut5w` sampled gave 553,130 clocks against 403,595 in full mode in the
first flat comparison (cold pieces), so use full mode where it fits.

## Measured streaming bandwidth (settles 0.52 against 0.17 B/clk)

`streamall` reads the 294,912-byte `i2` blob once with independent 64-bit loads from cold memory
(L2 256 KiB, L2 20 clocks, `MEM_LAT` 350, `MEM_GAP` 8, 8-byte beats, 64-byte L2 lines), full mode:

| `N_MISS` | Clocks | B/clk |
|---|---|---|
| 1 | 2,399,793 | 0.123 |
| 2 | 2,333,499 | 0.126 |
| **4 (deciding configuration)** | 1,728,764 | **0.1706** |
| 8 | 548,164 | **0.538** |
| 8, `MEM_GAP` 0 | 521,602 | 0.565 |
| flat memory (1 clock), `N_MISS` 8 | 36,916 | 7.99 (the bus) |

At the deciding configuration (`N_MISS` 4) the core streams **0.17 B/clk** (0.68 GB/s at 4 GHz), as the
matrix report predicted (one 64-byte line per about 375 clocks, the 4 misses sharing a line). The
ternary report's 0.52 B/clk was for four lines in flight; the RTL reaches it only at `N_MISS` 8
(0.54), and 1 to 2 misses give 0.12-0.13. The L2-resident ceiling, 4 x 8 / 20 = 1.6 B/clk, measured
1.32 (`stream`, L2 4 MiB). Forced-streaming kernels sit at 0.13-0.16 B/clk (`i2`, `lut5w`, `bs8`), a
read-bandwidth limit rather than a compute one: with the data in the L2 they run 2.9x (`i2`), 3.6x
(`lut5w`) and 5.6x (`bs8`) faster. A 1.178 GB token at 0.17 B/clk is 6.9 G clocks, 1.7 s at 4 GHz
(0.58 tokens/s); at 0.54 B/clk it is 0.55 s (1.8 tokens/s).

The `L2 256 KiB` configuration of the research plan holds each T-small layer (82-131 KB), so the
per-layer touch leaves layers resident there; `streamall` (295 KB) is the call that streams at 256 KiB.

## Limitations

- Synthetic weights, no model run. Per-layer calls with untimed touch; a real decode streams a whole
  layer once per token.
- T-2B4T numbers are single-piece samples; T-small is exact.
- Laptop figures were taken at host load 17-18; rerun on a quiet machine before quoting a tight range.
- Simulation only (Verilator 5.020), rubric class E1; no board measurement.
