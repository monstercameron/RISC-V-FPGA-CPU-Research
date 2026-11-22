# JavaScript benchmark: laptop reference, goal and baseline

Set on 2026-11-22 as the project's next benchmark series, after Dhrystone, 7-Zip and ray tracing:
JavaScript and web-page code are now a first-class target. The goal the user first set was **the user's laptop
+ 50% per clock** (since 2026-11-22 03:37 it is the Apple M6 reference, 1.30x the laptop; see "Goal (Apple M6 reference)"), the rule used for the 7-Zip and ray-tracing goals: for every kernel, and for the suite
as a geometric mean, our core must do the same work in at most 1/1.5 of the laptop's clocks. The
research behind this page (engines, weaknesses, plan) is [research/js-engines.md](research/js-engines.md).

Everything here is simulation (rubric evidence class E1) or a native laptop measurement. Nothing is a
hardware result of our core, and no clock frequency is claimed.

## Sources and licences

| Part | Version | Licence | Where |
|---|---|---|---|
| QuickJS-ng (engine, regexp, unicode, dtoa) | v0.18.0, commit `d7215b0ad3fc2c562e8317fd9bca058fd4863804`, github.com/quickjs-ng/quickjs tag archive (SHA-256 `28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd`, 910,210 bytes) | MIT, (c) 2017-2026 Fabrice Bellard, Charlie Gordon, Ben Noordhuis, Saúl Ibarra Corretgé ([copy](../licenses/QUICKJS-NG-LICENSE.txt)) | fetched by `sim/cpu/bench/js/fetch_quickjs.sh` into the ignored `build/third-party/quickjs-ng/`; not vendored. The 17 files the build compiles or includes and `LICENSE` are SHA-256 locked in `build_bench.py` (`QUICKJS_SHA256`); a mismatch stops the build |
| Shim libc (51 symbols), harness, kernels, script generator, native and laptop scripts | original | MIT (SPDX headers) | `sim/cpu/bench/js/` |
| Soft-float builtins (rv64imb build only) | compiler-rt from LLVM 23.1.5, as for rt | Apache-2.0 WITH LLVM-exception | `sim/cpu/bench/vendor/compiler-rt/` |

The engine is compiled unmodified with `-D__DJGPP -DNDEBUG -D_GNU_SOURCE` (no threads or atomics, no
debug dumps) on both machines.

## Workload and checks

QuickJS-ng is a bytecode interpreter (computed-goto dispatch); it stands in for interpreter tiers
(Ignition, LLInt, jitless modes), not for JIT code. One process runs `kernels.js` (scale 1) in one
runtime and context:

| # | Kernel | What it stresses |
|---|---|---|
| 0 | props | monomorphic and 4-way polymorphic property access, constructors, method calls |
| 1 | sched | Richards-like scheduler, prototype dispatch, linked packet queues |
| 2 | navier | Float64Array diffusion and advection stencil |
| 3 | sha256 | 32-bit integer and bit operations on typed arrays, BigInt set-up |
| 4 | json | JSON.stringify and JSON.parse of 400 records, then a walk |
| 5 | regex | RegExp exec, replace with a callback, global match over 400 log lines |
| 6 | strings | template literals, join/split, charCodeAt, `+=`, indexOf |
| 7 | dom | DOM-like tree: build, Map/Set attributes, query by class, remove, serialise |
| 8 | funcs | closures, map/filter/reduce, sort with a comparator |

- **Warm, then timed.** Every kernel runs twice with its PRNG reseeded. Markers 0x10+k, 0x20+k and
  0x30+k bracket the warm call and the timed call; **the figure is the timed (second) call**, so code,
  data and predictors are warm on both machines. Both calls must return the same checksum.
- **Checks.** `js_native.sh` builds the same sources natively and records the output (`expected.json`).
  Every RV64 run must reproduce, word for word: the output hash (`06484b07bf7fe92f`, 251 bytes), the
  line count and **each kernel's own line hash** (FNV-1a), no exception and no shim stop. The script
  embedded in the RV64 image must be byte-identical (SHA-256) to the one the native build ran.
- **RTL checks.** Timed pieces start from rv_iss checkpoints. Separate differential runs trace-check
  one piece per kernel (200K warm-up plus 100K, wait cycles alternating 0 and 7) against rv_iss on
  `tb_core`: 9 of 9 pass on each build below.

Commands (Linux or WSL):

```sh
bash sim/cpu/bench/js/fetch_quickjs.sh
bash sim/cpu/bench/js/js_native.sh 1                  # build/cpu/bench/js-ref/s1: expected.json, qjs_bench
python3 -B sim/cpu/bench/js/js_laptop.py --runs 7     # laptop reference (aarch64), laptop.json
python3 -B sim/cpu/bench/build_bench.py --benchmark js --isa rv64imfd_zba_zbb_zbs_zifencei   # or rv64im_zba_zbb_zbs_zifencei
python3 -B sim/cpu/bench/run_bench.py --benchmark js --core ooo --sim verilator --fpu \
    --sample-pieces 16 --no-differential --jobs 6 --pieces 0:18       # ... 18:36 to 126:144, then --pieces merge
```

## Laptop measurement (2026-11-22 01:58-01:59)

NVIDIA RTX Spark N1X, one Cortex-X925 (vCPU 19, MIDR part 0xd85, `taskset`), aarch64 WSL Ubuntu 24.04
(kernel 6.18.33.2), Ubuntu clang 18.1.3 `-O2`, glibc malloc and libm. The binary is
`js_native.sh`'s, the same engine, harness and script. Each run first ramps the clock (1.5-2 s of
dependent adds in the process); the harness reads the CPU's own user-space PMUv3 counters
(0x08 INST_RETIRED, 0x11 CPU_CYCLES) at every marker. 16 runs in two sessions (7 at 01:58, 9 at 01:59);
the table gives the median over all 16 with the min-max, and each session's median.

- **Per clock is by the cycle counter.** At 02:01, 640M dependent adds counted 640.2-640.3M cycles
  (`build/rt-bench/hwtest.c`, 3 runs), so a counted cycle is a core clock. The clock was 3.60-3.94 GHz
  by the 64-add chain and 3.49-3.73 GHz by cycles over wall time during the ramp. Timed calls ran at
  3.2-3.9 GHz effective (cycles / wall time).
- Machine load average was 6-7 of 20 vCPUs from other work; it shows as the high run maxima (sched,
  sha256, dom), not in the medians, which agree between sessions within 1-3% except dom (9%).

| Kernel | CPU cycles, median of 16 [min-max] | Session medians (7 / 9 runs) | AArch64 instructions | IPC | **Goal: our clocks at most (laptop / 1.5)** |
|---|---:|---:|---:|---:|---:|
| props | 4,224,946 [4,187,834-4,907,940] | 4,215,597 / 4,232,288 | 22,331,315 | 5.29 | **2,816,631** |
| sched | 4,902,544 [4,779,729-5,747,409] | 4,884,865 / 4,947,191 | 20,932,234 | 4.27 | **3,268,363** |
| navier | 3,869,884 [3,808,603-3,919,201] | 3,870,606 / 3,864,933 | 22,075,942 | 5.70 | **2,579,923** |
| sha256 | 4,574,128 [4,494,985-6,311,879] | 4,603,938 / 4,569,786 | 23,602,824 | 5.16 | **3,049,418** |
| json | 4,594,272 [4,473,529-5,013,562] | 4,526,095 / 4,614,028 | 26,289,559 | 5.72 | **3,062,848** |
| regex | 3,879,336 [3,763,739-4,319,135] | 3,808,970 / 3,971,305 | 22,643,462 | 5.84 | **2,586,224** |
| strings | 6,366,042 [6,281,708-7,266,796] | 6,341,400 / 6,419,490 | 36,028,535 | 5.66 | **4,244,028** |
| dom | 6,141,912 [6,062,466-7,329,284] | 6,090,835 / 6,643,578 | 26,336,185 | 4.29 | **4,094,608** |
| funcs | 3,544,158 [3,513,476-3,980,823] | 3,546,382 / 3,537,132 | 17,552,382 | 4.95 | **2,362,772** |
| sum | 42,097,221 | | 217,792,438 | 5.17 | 28,064,814 |

Instructions are the 01:58 session's medians (the 01:59 session's are within 0.1%, except json -0.06%).
The laptop runs its interpreter at an IPC of 4.3-5.8.

Node and Bun are not installed in WSL (`which node bun nodejs` found nothing on 2026-11-22), so there
is no JIT context row; installing them needs the user's approval. They would not be the same algorithm.

## Goal (Apple M6 reference, set 2026-11-22 03:37)

The user decided "M6 everywhere": goals are referenced to Apple's M6 core per clock, single thread. Apple
publishes no M6 microarchitecture or JavaScript figures (no Speedometer or JetStream per-clock figure exists for
the X925), so the goal is a **bridge, an estimate and not a measurement**: the laptop's measured cycles above
divided by the **Geekbench 6 single-core per-clock ratio M6 / X925 = 1.30** (M6 4,698 / 4.78 GHz = 983 against
the laptop's 3,096 / 4.1 GHz = 755, both Notebookcheck; 1.26 at 4.93 GHz). Source:
[research/performance-targets.md](research/performance-targets.md) (Notebookcheck M6, RTX Spark and Dimensity analyses, fetched 2026-11-22). Geekbench 6 contains browser-style tests but also SME-assisted ones the X925 cannot run, so this ratio
may overstate an interpreter workload; uncertainty about +-6% plus workload mismatch. The goal is **15% looser**
than the previous 1.5x (suite 32.38M clocks against 28.06M). The same factor applies to every kernel and to the
geometric mean (goal geomean 1.30x the laptop per clock, previously 1.5x). "IPC at goal" uses the hard-float
RV / AArch64 instruction ratios in the table below; it is 7.0-9.3 against 8.0-10.8 before.

| Kernel | Laptop cycles (median) | Bridge ratio | **Goal: our clocks at most** | IPC needed, hard float | Previous goal (laptop / 1.5) |
|---|---:|---:|---:|---:|---:|
| props | 4,224,946 | 1.30 | **3,249,958** | 8.59 | 2,816,631 |
| sched | 4,902,544 | 1.30 | **3,771,188** | 7.16 | 3,268,363 |
| navier | 3,869,884 | 1.30 | **2,976,834** | 8.97 | 2,579,923 |
| sha256 | 4,574,128 | 1.30 | **3,518,560** | 8.45 | 3,049,419 |
| json | 4,594,272 | 1.30 | **3,534,055** | 9.15 | 3,062,848 |
| regex | 3,879,336 | 1.30 | **2,984,105** | 9.03 | 2,586,224 |
| strings | 6,366,042 | 1.30 | **4,896,955** | 9.34 | 4,244,028 |
| dom | 6,141,912 | 1.30 | **4,724,548** | 6.97 | 4,094,608 |
| funcs | 3,544,158 | 1.30 | **2,726,275** | 8.05 | 2,362,772 |
| sum | 42,097,222 | 1.30 | **32,382,478** | | 28,064,815 |

The 1.5x text and the "IPC needed" rows below are history; `js_run.py` scores against 1.30.

## The goal

**1.5x the laptop's per-clock rate on each kernel, and 1.5x as the geometric mean over the nine
kernels** of (laptop cycles / our clocks). In clocks per timed call, the goal is the last column above.

What it implies for our core depends on how many RISC-V instructions the same work takes: the
hard-float build runs 1.19-1.29x the AArch64 instruction count (no load/store pair, two loads and two
stores per 16-byte JSValue move). At the goal clocks that is an **IPC of 8.0-10.8** (hard float) or
8.0-14.8 (soft float, navier 14.8), against the X925's 4.3-5.8:

| Kernel | props | sched | navier | sha256 | json | regex | strings | dom | funcs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RV / AArch64 instructions, hard float | 1.25 | 1.29 | 1.21 | 1.26 | 1.23 | 1.19 | 1.27 | 1.25 | 1.25 |
| IPC needed at the goal, hard float | 9.90 | 8.27 | 10.40 | 9.77 | 10.57 | 10.45 | 10.76 | 8.04 | 9.27 |
| IPC needed at the goal, soft float | 9.80 | 8.27 | 14.81 | 10.29 | 10.74 | 10.52 | 11.18 | 8.03 | 9.40 |

## Baseline on our cores (2026-11-22, architecture 0.17.0)

Out-of-order core 0.17.0 (`rv64_ooo.sv` SHA-256 `8d0357b2022e...`), Verilator 5.020, the runner's
standard configuration for 7-Zip and rt: 64 KiB I and D caches (direct-mapped instruction cache with
8-byte lines), flat memory (1 clock), one miss in flight, `FE_DEPTH` 0 (the idealised refill). Images
built with the same clang 18.1.3 `-O2` as the laptop binary.

Sampling: per kernel, K evenly spaced 250K-instruction pieces of the timed call (K = 16 hard float,
8 soft float), each from an rv_iss checkpoint after a **2M-instruction detailed warm-up**; kernel
clocks are the timed clocks per instruction times the call's instructions, with a 95% interval from
the spread of piece CPI. Why 2M and not `--warm-l2`: there is no L2 in this configuration, and with
1-clock memory the cold start is predictor and cache state, which a detailed warm-up restores. A
paired study (one piece per kernel, same pieces) gives suite clocks of 54.31M with no warm-up, 49.15M
at 100K, 48.72M at 500K, **48.66M at 2M** and 48.57M at 4M: 2M is within 0.2% of 4M in total and
within 0.9% per kernel. With no warm-up the suite reads 11.6% slow, the kind of cold-start artifact the rt runs showed at 01:11.

### Hard float, `--core ooo --fpu` (RV64_OOO_FPU), `rv64imfd_zba_zbb_zbs_zifencei`

| Kernel | Our clocks (95% CI) | RV instructions | IPC | RV / AArch64 | IPC needed | Laptop / our clocks | **Fraction of goal** |
|---|---:|---:|---:|---:|---:|---:|---:|
| props | 5,298,431 (+-0.1%) | 27,871,407 | 5.26 | 1.25 | 9.90 | 0.797 | **53.2%** |
| sched | 5,129,262 (+-0.2%) | 27,019,473 | 5.27 | 1.29 | 8.27 | 0.956 | **63.7%** |
| navier | 4,383,154 (+-5.7%) | 26,822,186 | 6.12 | 1.21 | 10.40 | 0.883 | **58.9%** |
| sha256 | 5,141,702 (+-7.5%) | 29,796,819 | 5.80 | 1.26 | 9.77 | 0.890 | **59.3%** |
| json | 6,879,020 (+-5.1%) | 32,382,603 | 4.71 | 1.23 | 10.57 | 0.668 | **44.5%** |
| regex | 5,718,406 (+-9.3%) | 27,035,493 | 4.73 | 1.19 | 10.45 | 0.678 | **45.2%** |
| strings | 6,242,628 (+-9.6%) | 45,664,459 | 7.31 | 1.27 | 10.76 | 1.020 | **68.0%** |
| dom | 7,417,639 (+-20.0%) | 32,932,414 | 4.44 | 1.25 | 8.04 | 0.828 | **55.2%** |
| funcs | 3,741,851 (+-10.7%) | 21,898,242 | 5.85 | 1.25 | 9.27 | 0.947 | **63.1%** |
| **total / geomean** | 49,952,093 | 271,423,096 | 5.43 | | | **0.844** | **56.3%** |

16 pieces per kernel (144). An 8-piece run of the same build gave 49,817,976 clocks and 56.7% of the
goal (geomean 0.851), inside these intervals. No kernel reaches the goal; strings and funcs are at
about the laptop's own rate per clock.

### Soft float, FPU off, `rv64im_zba_zbb_zbs_zifencei` with compiler-rt (runs on the released integer configuration)

| Kernel | Our clocks (95% CI) | RV instructions | IPC | RV / AArch64 | IPC needed | Laptop / our clocks | **Fraction of goal** |
|---|---:|---:|---:|---:|---:|---:|---:|
| props | 4,416,694 (+-0.1%) | 27,610,033 | 6.25 | 1.24 | 9.80 | 0.957 | **63.8%** |
| sched | 4,408,839 (+-0.2%) | 27,033,417 | 6.13 | 1.29 | 8.27 | 1.112 | **74.1%** |
| navier | 5,715,800 (+-7.4%) | 38,219,229 | 6.69 | 1.73 | 14.81 | 0.677 | **45.1%** |
| sha256 | 4,908,888 (+-14.9%) | 31,393,575 | 6.40 | 1.33 | 10.29 | 0.932 | **62.1%** |
| json | 5,913,485 (+-6.6%) | 32,888,780 | 5.56 | 1.25 | 10.74 | 0.777 | **51.8%** |
| regex | 5,149,315 (+-24.0%) | 27,216,540 | 5.29 | 1.20 | 10.52 | 0.753 | **50.2%** |
| strings | 6,198,711 (+-1.1%) | 47,445,346 | 7.65 | 1.32 | 11.18 | 1.027 | **68.5%** |
| dom | 6,902,371 (+-40.4%) | 32,894,046 | 4.77 | 1.25 | 8.03 | 0.890 | **59.3%** |
| funcs | 2,795,089 (+-13.8%) | 22,211,189 | 7.95 | 1.27 | 9.40 | 1.268 | **84.5%** |
| total / geomean | 46,409,192 | 286,912,155 | 6.18 | | | 0.916 | **61.1%** |

8 pieces per kernel (72). The same image on the FPU-enabled core gives identical clocks (a 9-piece
probe, 46,040,658 clocks both ways), so the FPU option does not slow integer code.

### What the first numbers say

- **The instruction cache is the largest measured lever.** With a 1 MiB instruction cache (the same
  direct-mapped 8-byte-line design, holding the whole 1.03 MB text; a probe, one piece per kernel,
  500K warm-up) the hard-float suite falls from 48.72M to 37.08M clocks (-24%; json -54%, regex -32%,
  strings -27%, dom -30%, props -34%), to a geometric mean of 1.15x the laptop (76% of the goal). The
  research report's trace model predicted this (7-59 MPKI at 64 KiB direct-mapped).
- **Soft float beats hard float at 64 KiB, for layout reasons.** props has 0.1 FP instructions per
  1,000 and the same instruction count in both builds, yet runs at IPC 5.3 hard and 6.3 soft. With the
  1 MiB instruction cache the two builds come within 1.5% of each other (37.08M / 36.55M clocks), so
  the gap at 64 KiB is instruction-cache conflicts from a different code layout, not the FPU. Any JS
  result on this cache is layout-sensitive by several percent.
- Even with that cache the core needs about 1.3x more speed per clock to reach the goal; the
  next levers ranked by the research report are indirect-target prediction and the BTB.

### Hard float in 7-Zip's deciding configuration

The memory and load latencies of `cpu/7zip-benchmark-targets.md`'s deciding configuration
(`--ld-lat 4 --l0 16 --l2-kib 4096 --l2-lat 20 --mem-lat 350 --n-miss 4 --mem-gap 8`), hard float,
4 pieces per kernel (36), 2M warm-up **plus `--warm-l2`** (each piece's L2 tags preloaded from rv_iss's
cache model: with 350-clock memory a detailed warm-up alone cannot refill a cold 4 MiB L2):

| Kernel | Our clocks (95% CI) | RV instructions | IPC | RV / AArch64 | IPC needed | Laptop / our clocks | **Fraction of goal** |
|---|---:|---:|---:|---:|---:|---:|---:|
| props | 24,019,579 (+-0.3%) | 27,871,407 | 1.16 | 1.25 | 9.90 | 0.176 | **11.7%** |
| sched | 8,529,345 (+-0.9%) | 27,019,473 | 3.17 | 1.29 | 8.27 | 0.575 | **38.3%** |
| navier | 6,809,456 (+-9.4%) | 26,822,186 | 3.94 | 1.21 | 10.40 | 0.568 | **37.9%** |
| sha256 | 9,358,883 (+-54.7%) | 29,796,819 | 3.18 | 1.26 | 9.77 | 0.489 | **32.6%** |
| json | 40,596,645 (+-19.4%) | 32,382,603 | 0.80 | 1.23 | 10.57 | 0.113 | **7.5%** |
| regex | 17,571,070 (+-34.5%) | 27,035,493 | 1.54 | 1.19 | 10.45 | 0.221 | **14.7%** |
| strings | 21,942,595 (+-45.6%) | 45,664,459 | 2.08 | 1.27 | 10.76 | 0.290 | **19.3%** |
| dom | 39,284,780 (+-22.3%) | 32,932,414 | 0.84 | 1.25 | 8.04 | 0.156 | **10.4%** |
| funcs | 9,363,053 (+-79.0%) | 21,898,242 | 2.34 | 1.25 | 9.27 | 0.379 | **25.2%** |
| total / geomean | 177,475,406 | 271,423,096 | 1.53 | | | 0.284 | **18.9%** |

Every instruction-cache miss here costs an L2 hit (20 clocks) through a blocking fetch with the lowest
bus priority, so the kernels the trace model gave the most instruction misses (json, dom, props, regex,
strings) fall to an IPC of 0.8-2.1. Four pieces leave wide intervals; the order of magnitude, not the
digits, is the result. This row is closer to the laptop's real memory system than the flat one.

## What is and isn't comparable

- **Same algorithm:** the same QuickJS-ng sources, configuration, harness and script on both machines,
  checked by output hashes; per-clock figures on both sides.
- **Not the same:** the laptop uses glibc's malloc, memcpy and string routines, the bare-metal build
  the shim's (a size-class allocator; word-wise memcpy and memset). The laptop runs under Linux in WSL
  (page faults, interrupts; user-mode counters exclude kernel time), our core bare metal. The compiler
  is the same clang 18.1.3 but for different ISAs: the instruction ratio (1.19-1.29 hard float) is part
  of the comparison, as for 7-Zip and rt.
- **Memory:** the baseline uses flat 1-clock memory and an idealised front-end refill (`FE_DEPTH` 0);
  the laptop has real L2, L3 and DRAM latencies. The flat figures flatter our core; the
  deciding-configuration row is the fairer one.
- **Interpreter only:** no JIT. V8, JavaScriptCore, Node and Bun need A, C, an OS and an MMU that the
  core does not have ([research/js-engines.md](research/js-engines.md)); their JIT tiers would change the instruction mix
  completely.
- **Sampling:** kernel clocks are estimates from sampled pieces; dom, regex, sha256 and funcs have wide
  intervals because their phases differ (build, query, serialise). A whole-program run is about 550M
  instructions, too long for one 5-minute simulator step.
- The scorecard and numbers here are self-assessed; none has had an independent review.
