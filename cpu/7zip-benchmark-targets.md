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
the 7-Zip version, and divide by the measured clock for a per-GHz figure.

Source code used here: 7-Zip 26.06, `https://github.com/ip7z/7zip`, commit
`d3296e39e1f1f92c7b41c0c3848e65640428d42d` (copy in the ignored `build/third-party/7zip/`).

## Measured on the user's laptop (2026-11-21)

NVIDIA RTX Spark N1X, Arm Cortex-X925 performance core (pinned), `7zz` 26.06 built with clang 18.1.3
for aarch64 Linux (WSL), `7zz b -mmt1`; 7-Zip measured the single-thread clock at 3.7-4.3 GHz.

| Dictionary | Compressing rating | Decompressing rating | Per GHz (at ~4.2 GHz) |
|---|---:|---:|---|
| 22 (4 MB) | 8,003 MIPS | 8,087 MIPS | about 1.9 / 1.9 |
| 22-25 average | 7,085 MIPS | 8,042 MIPS | about 1.7 / 1.9 |

## Published single-thread ratings (per GHz derived from the listed clock)

Collected by a research agent from 7-cpu.com and sbc-bench; 7-Zip versions and dictionaries vary
between sources, which can change results by up to 1.7x. "Combined" is a single overall score.

| Core | Compress / GHz | Decompress / GHz | Source |
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

Per GHz (= per MHz x 1000), single thread: best published RISC-V about 0.8; A76 / Skylake class
about 1.2; Zen 3 about 1.5 / 2.1; X925 about 1.9; M1 about 2.2 / 2.5.

Our simulated core runs a **scaled-down** version of 7-Zip's LZMA kernel (small data and dictionary,
so a simulation finishes in minutes; see the benchmark's own notes), so its rating is comparable only
after calibrating the same scaled kernel on a real CPU, and compression results in particular depend
on memory latency, which our model idealizes (1-clock SRAM, 4 KiB caches). Quote our numbers as
simulation of a scaled kernel, with those caveats.
