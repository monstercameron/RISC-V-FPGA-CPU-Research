# 7-Zip benchmark: reference scores and targets

Set on 2026-11-21 as the project's new benchmark program, next to Dhrystone. This page collects what
other CPUs score so our core's results can be placed. All figures here are measured or published
single-thread ratings; none of them is a result of our core.

## What the 7-Zip benchmark measures

`7z b` LZMA-compresses and decompresses generated benchmark data and reports a **rating in "MIPS"**
per thread. The rating is an estimate scaled from measured speed with fixed per-byte "command" counts
(calibrated against an Intel Core 2 core), **not** a count of instructions executed, so it is not an
instruction rate of the CPU under test and is comparable across ISAs only as a speed measure.
Compression depends heavily on memory latency and cache size (it searches a large dictionary);
decompression depends more on branch prediction and short dependency chains. Use `-mmt1` (one thread)
and the **Rating** column (not Usage or R/U), state the dictionary (`-md22` = 2^22 bytes = 4 MiB, `-md25` = 32 MiB),
the 7-Zip version, and divide by the measured clock in MHz for a per-MHz figure (corrected 2026-11-21 17:57: earlier text said per GHz, a factor-of-1,000 unit error found by the Codex review).

**Units on this page.** "MIPS" is always 7-Zip's nominal rating, not instructions per second: real CPUs are
rated from measured time, and our simulated cores from clock counts with the same per-byte command counts, so
"MIPS/MHz" is rating per MHz of clock. For the laptop the clock is the one 7-Zip measured or an assumed
average (stated in each table); for our cores it is the simulated clock, with no frequency claim. Our IPC
columns are retired RISC-V instructions per clock, a different quantity. Sizes use binary prefixes (KiB, MiB)
for powers of two and SI prefixes (kB, MB) for decimal counts (IEC 80000-13).

Source code used here: 7-Zip 26.06, `https://github.com/ip7z/7zip`, commit
`d3296e39e1f1f92c7b41c0c3848e65640428d42d` (copy in the ignored `build/third-party/7zip/`).

## Measured on the user's laptop (2026-11-21)

NVIDIA RTX Spark N1X, Arm Cortex-X925 performance core (pinned), `7zz` 26.06 built with clang 18.1.3
for aarch64 Linux (WSL), `7zz b -mmt1`; 7-Zip measured the single-thread clock at 3.7-4.3 GHz.

| Dictionary | Compressing rating | Decompressing rating | Per MHz (at ~4.2 GHz) |
|---|---:|---:|---|
| 22 (4 MiB) | 8,003 MIPS | 8,087 MIPS | about 1.9 / 1.9 |
| 22-25 average | 7,085 MIPS | 8,042 MIPS | about 1.7 / 1.9 |

## Published single-thread ratings (per MHz, derived from the listed clock)

Collected by a research agent from 7-cpu.com and sbc-bench; 7-Zip versions and dictionaries vary
between sources, which can change results by up to 1.7x. "Combined" is a single overall score.

| Core | Compress / MHz | Decompress / MHz | Source |
|---|---:|---:|---|
| SpacemiT K1 (X60, RISC-V) | about 0.61 combined | | sbc-bench |
| SiFive U74 (RISC-V) | 0.79 | 0.90 | 7-cpu.com (7-Zip 21.07) |
| StarFive JH7110 / T-Head C910 / Sophgo SG2042 (RISC-V) | about 0.75-0.81 combined | | sbc-bench |
| Cortex-A55 | 0.72 | 0.98 | 7-cpu.com (16.04) |
| Cortex-A76 | 1.18 | 1.19 | 7-cpu.com (16.04) |
| Intel Skylake | about 1.16 | about 1.16 | 7-cpu.com |
| Qualcomm Oryon | about 1.3 combined | | sbc-bench (boost clock; likely understated) |
| AMD Zen 3 | 1.52 | 2.11 | 7-cpu.com |
| Arm Cortex-X925 (laptop above) | about 1.9 | about 1.9 | measured here |
| Apple M1 | 2.22 | 2.52 | 7-cpu.com |

Not found: single-thread figures for Zen 4/5, Golden/Lion Cove, Apple M2-M4, Arm X1-X4.

## Where our core needs to be

Per MHz (rating MIPS divided by clock MHz), single thread: best published RISC-V about 0.8; A76 / Skylake class
about 1.2; Zen 3 about 1.5 / 2.1; X925 about 1.9; M1 about 2.2 / 2.5.

Our simulated core runs a **scaled-down** version of 7-Zip's LZMA kernel (small data and dictionary,
so a simulation finishes in minutes; see the benchmark's own notes), so its rating is comparable only
after calibrating the same scaled kernel on a real CPU, and compression results in particular depend
on memory latency, which our model idealizes (1-clock SRAM, 4 KiB caches). Quote our numbers as
simulation of a scaled kernel, with those caveats.

## Goal (Apple M6 reference, set 2026-11-22 03:37)

The user decided "M6 everywhere": every goal is referenced to Apple's M6 core per clock, single thread. Apple
publishes no M6 microarchitecture, SPEC or 7-Zip figures, so each M6 goal here is a **bridge, an estimate and not
a measurement**: the laptop's measured per-clock figure on our identical workload times a published M6 / X925
per-clock ratio on the closest public benchmark. Source: [research/performance-targets.md](research/performance-targets.md) (Notebookcheck M6, RTX Spark and Dimensity analyses, fetched 2026-11-22).

**Bridge (a), the goal:** Geekbench 6.7 single-core per GHz, M6 4,698 / 4.78 GHz = 983 against the laptop's
Cortex-X925 3,096 / 4.1 GHz = 755 (both Notebookcheck), ratio **1.30** (1.26 if M6 ran 4.93 GHz). Uncertainty about
+-6% from the two clocks, plus the workload mismatch (Geekbench uses SME in some subtests, which the X925 lacks,
so 1.30 may overstate a scalar workload such as LZMA).

| Metric | Laptop per clock (measured) | Bridge ratio | **M6-referenced goal** | Previous goal (10,000 MIPS at 4 GHz) |
|---|---:|---:|---:|---:|
| `7z b -md22` compress, MIPS/MHz | 1.91 | 1.30 (GB6/GHz) | **2.48** (9,920 MIPS at 4 GHz) | 2.50 |
| `7z b -md22` decompress, MIPS/MHz | 1.93 | 1.30 | **2.51** (10,040 MIPS at 4 GHz) | 2.50 |
| d22 kernel compress, MIPS/MHz | 1.55 | 1.30 | **2.02** | 2.03 |
| d22 kernel decompress, MIPS/MHz | 1.68 | 1.30 | **2.18** (kernel before the 2026-11-22 CRC change; **2.47** after it, provisional, see below) | 2.18 |

**The headline does not change materially.** The M6 bridge gives 9,920 / 10,040 MIPS at 4 GHz, within 1% of the
10,000 MIPS goal; the d22 kernel goals move by under 1% (2.03 to 2.02 compress, 2.18 to 2.18 decompress). The
0.16.0 deciding-configuration run (2.187 / 2.322) is 108% / 107% of the new goal.

### Decompression goals after the CRC change (2026-11-22, provisional)

On 2026-11-22 the user approved matching 7-Zip's decompression CRC ("Yes, match 7-Zip"). Since then the kernel
decodes in 1 MiB output steps and CRCs each step inside the timed region with slicing-by-12, as `7z b` does
([lzma-benchmark.md](lzma-benchmark.md), "Known departures"). Before the change it ran one byte-table CRC pass over
the whole output after decoding. That pass was 13% (d22) and 17% (d12) of the X925's decompress time, and 24% of
our core's d22 decompress clocks at a 4 MiB L2. Compression code is unchanged, so the compress goals stay.

**No quiet window.** The laptop was re-measured on vCPU 19 on 2026-11-22 in two windows, 05:29-05:34 and
05:52-05:57 (the second on the final code). Other agents' simulations kept the 1-minute load average at
11.3-14.0 on 20 vCPUs throughout. The add-chain clock read 3.44-3.80 GHz and `7zz b -mmt1 -md22` measured
3.15-3.77 GHz (quiet: 4.2-4.3). In those windows `7zz b` rated 1.42-1.52 / 1.84-1.90 per MHz against 1.91 / 1.93
quiet, so the loaded absolutes are not used.

Method: the old and new kernels ran interleaved, 5 runs each, each run ramped by its own untimed fifth of the
passes. Each quiet 2026-11-21 reference is scaled by the paired new/old ratio, taken in the statistic that
reference used (d22: minimum of 15 passes; d12: median of 30,000 passes).

| | Paired new/old decompress ratio, median of 5 runs [range] | Laptop kernel per clock, old -> new | Goal, old -> new |
|---|---:|---:|---:|
| d22 kernel (M6 bridge 1.30) | 1.129 [1.083-1.190] | 1.68 -> 1.68 x 1.129 = **1.90** | 1.68 x 1.30 = 2.18 -> 1.90 x 1.30 = **2.47** [2.37-2.60] |
| d12 kernel (`7z b` ratio, 10,000 MIPS at 4 GHz) | 1.183 [1.162-1.216] | 2.586 -> 2.586 x 1.183 = **3.06** | 2.5 x 2.586 / 1.93 = 3.35 -> 2.5 x 3.06 / 1.93 = **3.96** [3.89-4.07] |

- The first window, on an earlier build of the change, gave 1.171 [1.139-1.192] (d22) and 1.176 [1.101-1.208]
  (d12). That build had the same decode code but built its tables before compression.
- Compression, whose code is unchanged, moved 1.01-1.05x in medians over the same runs, and 0.88-1.10x in single
  d22 runs. That is the noise floor of these windows.
- The corrected d22 kernel now rates 1.90 / 1.93 = 0.98x the laptop's real `7z b -md22` decompression per clock,
  against 0.87x before. The kernel now calibrates almost one to one, as expected once the same work is timed.
- **These goals are provisional** until a quiet-machine re-measure.

Measured detail and commands: DEVLOG.md 2026-11-22 (backend bench package).

**Deciding run on the new bench (simulation, 2026-11-22, cpu-v0.18.0 and cpu-v0.16.0).** d22, the deciding
configuration at a 4 MiB L2, 60 sampled pieces per phase per core (backend `pkg/d22agg.py`; DEVLOG 08:07 and
08:55 to 10:47 rows). Ratings are 7-Zip commands per clock.

| Core | Compress MIPS/MHz (95% CI, low end) | Share of 2.02 | Decompress MIPS/MHz (95% CI, low end) | Share of 2.47 |
|---|---:|---:|---:|---:|
| cpu-v0.18.0 | 2.211 (±6.7%, 2.072) | 109% | 2.975 (±3.0%, 2.887) | 120% |
| cpu-v0.16.0 | 2.184 (±6.8%, 2.044) | 108% | 2.950 (±3.1%, 2.862) | 119% |

On cpu-v0.18.0 both phase goals are met in the point estimate and at the low end; the two-phase average is 2.593
MIPS/MHz, 10,372 MIPS at 4 GHz (low ends 2.48, 9,918). The decompress goal is provisional (above). Later
versions were not measured at d22; 0.19.x is bit-exact to 0.18.0 at default through 0.19.3.

**Sensitivity row, not the goal (low confidence): bridge (b).** Apple M1's 7-cpu.com 7-Zip 16.04 ratings
(2.22 / 2.52 per MHz) scaled by the Geekbench 6 per-clock gain M1 to M6 (about 731 to 983 per GHz, M1 figure
recalled) give 1.56 / 1.76 over the laptop: **2.99 / 3.39** MIPS/MHz on `7z b`, **2.43 / 2.96** on the d22 kernel.
It mixes 7-Zip versions (16.04 against the laptop's 26.06) and two chips' clocks, so it is not used; at that
level 0.16.0 would be 90% / 78%.

## Optimization target: 10,000 MIPS (set 2026-11-21)

The user set the core's optimization target to a **10,000 MIPS** single-thread 7-Zip rating (`7z b -mmt1`,
`-md22`, compression and decompression each). A rating is a speed, so a per-clock target depends on the
clock; the goal is stated at **4 GHz**, near the clock at which the X925 above rates 8,000:

| Clock | Per-MHz rating needed (`7z b`) | Compared with the X925 (1.9 per MHz) |
|---|---:|---|
| 3 GHz | 3.33 | 1.75x |
| **4 GHz (goal)** | **2.50** | **1.3x** |
| 5 GHz | 2.00 | 1.05x |
| 100 MHz (FPGA class) | 100 | not reachable by any core; an FPGA build is measured per MHz only |

At 4 GHz the target is about 1.3x the X925 and 1.1x / 1.0x Apple M1 per clock (2.22 / 2.52). On the
scaled kernel our simulation runs, the X925's ratio between kernel and `7z b` (4.37x compression,
1.34x decompression) puts the goal at about **10.9 compression / 3.35 decompression kernel MIPS/MHz**.
That conversion is an estimate from one real CPU: the kernel's 4 KiB dictionary removes most of the
cache-miss cost that dominates `7z b` compression, so a core that does well on the kernel can still miss
the target on the real benchmark. A full-dictionary result needs a realistic memory hierarchy in the
model, which it does not have yet (1-clock memory).

### Goal on the full-size kernel (added 2026-11-21 20:34)

Since 2026-11-21 the kernel also runs at the real benchmark's size: `--lzma-dict-log 22` (4 MiB dictionary,
4 MiB + 64 KiB = 4,259,840 bytes of data, about 4.0 billion instructions), in checkpointed pieces on the out-of-order core. On
the X925 the d22 kernel rates 1.55 / 1.68 MIPS/MHz against 1.91 / 1.93 from the real `7z b -md22`
(ratios 0.81 / 0.87, close to 1, so this calibration is far less uncertain than the d12 one). The
10,000 MIPS goal (2.5 MIPS/MHz at 4 GHz) is therefore about **2.03 compress / 2.18 decompress MIPS/MHz
on the d22 kernel**, and that is the figure to quote once our model's memory is realistic. Native X925
kernel figures by size (compress / decompress MIPS/MHz, machine loaded, noisy): d16 4.71 / 1.80, d18
3.89 / 1.81, d20 2.45 / 1.67, d22 1.55 / 1.68. With flat memory our out-of-order core's d22 estimate
(0.14.7) is 6.72 / 3.30, which only shows that the dictionary costs nothing until memory latency is
modelled; with the 0.15.0 memory model (L2 and `MEM_LAT`) the d22 runs are in progress.

### The configuration that decides the goal (proposed 2026-11-21 21:16)

A rating counts toward the 10,000 MIPS goal only on the full-size kernel (d22) in a configuration whose
latencies a shipping core of the X925's class could plausibly have. Until each piece exists in the
released model, the rating is quoted with the piece it lacks:

| Parameter | Value | Why |
|---|---|---|
| L1 instruction / data | 64 KiB / 64 KiB | the X925's L1 sizes |
| Load-to-use (`RV64_OOO_LD_LAT`) | 4 clocks | current large cores (since 0.14.10 a knob; default 1) |
| L0 recent-beat buffer | 16 beats at 2 clocks | Lion Cove-class precedent (backend hand-off 7, queued) |
| Multiply | 2 clocks | as released (0.14.7), a behavioural assumption |
| L2 (stand-in for L2 + L3) | 4 MiB, 8-way, 64 B lines, 20 clocks | the X925 has 2-3 MiB of L2 and a shared L3 behind it |
| Memory (`MEM_LAT`) | 350 clocks | about 88 ns at 4 GHz |
| Misses in flight | several, oldest guaranteed | memory hand-off 2 (held after its Codex review) |

The first full-size runs (0.15.1, L2 1 / 4 MiB at 12 clocks, MEM_LAT 100, one miss at a time, 1-clock
loads) rate 2.62 / 2.77 and 3.27 / 2.85 MIPS/MHz: above the 2.03 / 2.18 goal, but with 1-clock loads
and 25 ns memory, so they do not yet decide it.

| Deciding-configuration run | Compress MIPS/MHz | Decompress MIPS/MHz | Note |
|---|---:|---:|---|
| Goal (10,000 MIPS at 4 GHz) | 2.03 | 2.18 | |
| 0.15.4, one miss at a time (2026-11-21 21:53) | **1.53** (75%, +-10.9%) | **1.98** (91%, +-22.9%) | not met |
| **0.16.0, 4 misses in flight, MEM_GAP 8 (2026-11-22 00:21)** | **2.187** (108%, +-6.8%; low end 2.04) | **2.322** (107%, +-10.2%; low end 2.09) | **met in point estimate**; compress above the goal at the low end of its interval |

The 0.15.4 run had everything in the table above except several misses in flight; 0.16.0 adds them
(`--n-miss 4 --mem-gap 8`), with 3M detailed warm-up and 60 sampled pieces per phase (41 invocations,
each under 300 s, `--warm-l2`): compress kernel 1,850,671,244 clocks (IPC 1.911), decompress
152,967,666 (IPC 2.138). A 4-piece probe of 3M against 5M warm-up says 3M reads compress about 2.3%
slow (conservative) and decompress about 1.0% fast. The decompress interval still reaches below the
goal; more pieces would narrow it (about 80 minutes per 120 pieces).

## The scaled kernel on our cores (simulation)

`sim/cpu/bench/lzma_bench.c` runs 7-Zip's LZMA benchmark kernel (the LZMA SDK C sources of 7-Zip 26.06,
the same benchmark data generator and level-5 BT4 encoder settings as `7z b`) at a size a simulation can
finish: 4 KiB dictionary (the LZMA minimum), 4,160 bytes of data, 2,220 bytes packed. Ratings use
7-Zip's own formulas (compression: 870 commands per data byte; decompression: 190 per packed byte plus 4
per data byte) divided by clocks, so they are per MHz and independent of clock rate. Because the small
dictionary fits in cache, the kernel rates a real CPU far higher than `7z b` does: on the X925 the same
kernel gives 8.34 / 2.59 MIPS/MHz against 1.91 / 1.93 from `7z b -md22` (compression 4.4x, decompression
1.34x; the decompression figures here predate the 2026-11-22 CRC change, after which the d12 decompress goal is
3.96, provisional, see "Decompression goals after the CRC change"). The second `-md22` row of the native run (8,267 / 8,290) would move the kernel goal to about
10.59 / 3.28, so the goal carries a few percent of calibration uncertainty. Compare our cores with the native figure for the same kernel, not with the `7z b` tables above.

| Core (architecture 0.14.6 RTL, rv64imb, clang -O2) | Compress MIPS/MHz | Decompress MIPS/MHz | Compress / decompress IPC |
|---|---:|---:|---|
| **Goal at 4 GHz (estimated kernel equivalent of 10,000 MIPS)** | **10.9** | **3.35** | |
| Arm Cortex-X925, native (user's laptop, ~4.27 GHz) | 8.34 | 2.59 | n/a |
| Multicycle core (`rv64_core.sv`) | 1.61 (19% of X925) | 1.69 (65%) | 1.36 / 1.66 |
| Pipelined core (`rv64_pipe.sv`) | 0.96 (12%) | 0.89 (34%) | 0.82 / 0.87 |
| Out-of-order core (`rv64_ooo.sv`), 4 KiB caches, Verilator | 3.39 (41%) | 2.56 (99%) | 2.87 / 2.50 |
| Out-of-order 0.14.6, 64 KiB I / 64 KiB D caches (measured configuration from 2026-11-21 18:07) | 7.46 (89%) | 2.89 (112%) | 6.32 / 2.83 |
| **Out-of-order 0.14.7, 64 KiB I / 64 KiB D** | **7.65 (92%)** | **3.23 (125%)** | 6.48 / 3.16 |

All simulated figures are idealized-model simulation (1-clock memory, 4 KiB caches). The multicycle and
pipelined results are whole-program runs checked against the reference model and an independent liblzma
decode. The out-of-order figures come from one
whole-program run under Verilator 5.020, whose clock counts matched Icarus exactly on every case that
Icarus can finish (Dhrystone on all three cores, the multicycle and pipelined LZMA runs, two
out-of-order LZMA windows); its result mailbox passed and equals the multicycle core's. Compress kernel
1,067,884 clocks for 3,065,963 instructions; decompress kernel 171,494 clocks for 429,119. An earlier
sampled Icarus estimate (13 of 21 compress pieces) gave 3.32 / 2.555. Against the goal (10.9 / 3.35),
out-of-order compression is at 31% and decompression at 76%. Benchmark design and commands:
[lzma-benchmark.md](lzma-benchmark.md).

### Measured configuration

From 2026-11-21 18:07 the 7-Zip kernel is measured with 64 KiB instruction and 64 KiB data caches
(`run_bench.py --benchmark lzma`, default `--icache-beats 8192 --dcache-beats 8192`), the L1 sizes of
the Cortex-X925 it is compared with; the SoC's 4 KiB caches (`--icache-beats 512 --dcache-beats 512`)
stay as the FPGA-class figure. The bus behind the caches is unchanged (2 clocks per 8-byte read, one
miss at a time), so a miss costs far less than DRAM would. Baseline at architecture 0.14.6: 485,401
compress-kernel clocks (7.46 MIPS/MHz, 68% of the goal) and 151,758 decompress (2.89, 86% of the goal).
Dhrystone keeps the 4 KiB configuration, so its history stays comparable.

