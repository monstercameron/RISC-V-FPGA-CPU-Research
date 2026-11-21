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
and the **Rating** column (not Usage or R/U), state the dictionary (`-md22` = 4 MB, `-md25` = 32 MB),
the 7-Zip version, and divide by the measured clock in MHz for a per-MHz figure (corrected 18:05: earlier text said per GHz, a factor-of-1,000 unit error found by the Codex review).

Source code used here: 7-Zip 26.06, `https://github.com/ip7z/7zip`, commit
`d3296e39e1f1f92c7b41c0c3848e65640428d42d` (copy in the ignored `build/third-party/7zip/`).

## Measured on the user's laptop (2026-11-21)

NVIDIA RTX Spark N1X, Arm Cortex-X925 performance core (pinned), `7zz` 26.06 built with clang 18.1.3
for aarch64 Linux (WSL), `7zz b -mmt1`; 7-Zip measured the single-thread clock at 3.7-4.3 GHz.

| Dictionary | Compressing rating | Decompressing rating | Per MHz (at ~4.2 GHz) |
|---|---:|---:|---|
| 22 (4 MB) | 8,003 MIPS | 8,087 MIPS | about 1.9 / 1.9 |
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

## The scaled kernel on our cores (simulation)

`sim/cpu/bench/lzma_bench.c` runs 7-Zip's LZMA benchmark kernel (the LZMA SDK C sources of 7-Zip 26.06,
the same benchmark data generator and level-5 BT4 encoder settings as `7z b`) at a size a simulation can
finish: 4 KiB dictionary (the LZMA minimum), 4,160 bytes of data, 2,220 bytes packed. Ratings use
7-Zip's own formulas (compression: 870 commands per data byte; decompression: 190 per packed byte plus 4
per data byte) divided by clocks, so they are per MHz and independent of clock rate. Because the small
dictionary fits in cache, the kernel rates a real CPU far higher than `7z b` does: on the X925 the same
kernel gives 8.34 / 2.59 MIPS/MHz against 1.91 / 1.93 from `7z b -md22` (compression 4.4x, decompression
1.34x). The second `-md22` row of the native run (8,267 / 8,290) would move the kernel goal to about
10.59 / 3.28, so the goal carries a few percent of calibration uncertainty. Compare our cores with the native figure for the same kernel, not with the `7z b` tables above.

| Core (architecture 0.14.6 RTL, rv64imb, clang -O2) | Compress MIPS/MHz | Decompress MIPS/MHz | Compress / decompress IPC |
|---|---:|---:|---|
| **Goal at 4 GHz (estimated kernel equivalent of 10,000 MIPS)** | **10.9** | **3.35** | |
| Arm Cortex-X925, native (user's laptop, ~4.27 GHz) | 8.34 | 2.59 | n/a |
| Multicycle core (`rv64_core.sv`) | 1.61 (19% of X925) | 1.69 (65%) | 1.36 / 1.66 |
| Pipelined core (`rv64_pipe.sv`) | 0.96 (12%) | 0.89 (34%) | 0.82 / 0.87 |
| Out-of-order core (`rv64_ooo.sv`), whole program under Verilator | 3.39 (41%) | 2.56 (99%) | 2.87 / 2.50 |

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

