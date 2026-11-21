# Scaled-down 7-Zip LZMA benchmark kernel

The bare-metal program `sim/cpu/bench/lzma_bench.c` reproduces what `7z b` times for LZMA, at a
size the RTL simulator can run. Results are labelled **"scaled-down 7-Zip LZMA kernel,
simulation"**. They are not 7-Zip benchmark scores. Reference scores for real CPUs are in
[7zip-benchmark-targets.md](7zip-benchmark-targets.md).

## What `7z b` does (7-Zip 26.06, `CPP/7zip/UI/Common/Bench.cpp`)

- **Data.** `CBenchRandomGenerator::GenerateLz(kOldLzmaDictBits = 32, salt)` produces
  pseudo-random data with LZ structure. The generator is two 16-bit multiply-with-carry streams
  (`36969`/`18000`, seeds `362436069`/`521288629`), and salt 0 is used for the first thread. The
  first 1,024 bytes are random literals. After that, each step is a literal (probability 1/2) or a
  copy. A copy has a short random length, and 7 in 8 copies also get a new distance, drawn
  log-uniformly up to the current position. The data size is the dictionary plus
  `kAdditionalSize` = 64 KiB (for `-md22`: 4 MiB + 64 KiB).
- **Encoder.** The LZMA coder runs at its default level 5 with only the dictionary set (`-mdN`),
  `reduceSize` = the data size and, with `-mmt1`, one thread. The level gives these settings:
  - lc 3, lp 0, pb 2
  - 32 fast bytes
  - optimal parsing (algo 1)
  - BT4 binary-tree match finder (4 hash bytes), cut value 32
  - no end marker
- **Timing.** Timing starts after the data, its CRC and the encoder properties are prepared.
  - Each compression pass is one `ICompressCoder::Code()`, which includes encoder and
    match-finder initialisation. The output stream copies the packed bytes and updates their CRC.
  - Each decompression pass decodes to the end and CRCs the output; the CRC must match.
  - Passes repeat until about 4 s of nominal work (`kComplexInCommands`) is done.
- **Rating.** Bench.cpp converts speed to "MIPS" with fixed per-byte command counts:
  - Compression: `870 + (t*t*5 >> 16)` commands per input byte, with
    `t = GetLogSize_Sub(dict) - (18 << 8)`. A dictionary below 2^18 counts as 2^18, which gives
    870; `-md22` gives 950.
  - Decompression: `190` per packed byte plus `4` per unpacked byte.
  - The rating is commands × timer frequency / elapsed ticks. With elapsed time = clocks / f,
    **rating / f = commands / clocks**, so the MIPS-per-MHz figure needs no clock frequency.

## What the kernel keeps, and what is scaled or different

| | 7z b -mmt1 -md22 | This kernel |
|---|---|---|
| Data | GenerateLz(32, salt 0), 4 MiB + 64 KiB | Same generator (checked byte-identical to the upstream C++ text in 60 cases, including 4 MiB + 64 KiB), **4,160 B** (4 KiB + 1/64, the same shape) |
| Encoder | LZMA SDK, level 5, BT4, lc3 lp0 pb2, fb32, mc32 | The same unmodified LZMA SDK files (`vendor/lzma/`), same settings, **4 KiB dictionary** (the LZMA minimum) |
| Streams | Input copied from memory; output copied with a CRC; decoder output CRC-checked | Same, as callbacks; the CRC is a byte-table CRC-32, not 7-Zip's sliced or hardware CRC |
| Passes | Repeated for about 4 s, alloc once, init per pass | One pass. The *kernel* phases exclude the fixed per-pass init; *call* phases include it |
| Memory | malloc, about 25 MiB for d22 | Static arena in 1 MiB of RAM (878,400 B used; the BT4 hash alone is 528 KiB) |
| Rating | 950 commands/B (d22) | 870 commands/B (dictionaries up to 2^18 count as 2^18); decompress formula unchanged |

Because the match finder searches only a 4 KiB window, the kernel runs far fewer clocks per byte than
`-md22`, although the BT4 hash table is 528 KiB and not all of it fits a small cache (measured on the
out-of-order core with 4 KiB caches: 17 data-cache misses per thousand instructions in compression,
against 104 instruction-cache misses). Its per-MHz rating is therefore much higher than a
real 7-Zip rating, and is comparable to one only through a calibration on real hardware (below).

### Phases (markers in `include-lzma/lzma_bench.h`; laps are mailbox values 16 and above)

| Phase | From | To | Instructions (rv64imb, clang 23.1.5 -O2) |
|---|---|---|---:|
| compress kernel | first input-stream read, which LzFind makes right after clearing its hash | `LzmaEnc_Encode()` returns | 3,065,962 |
| compress call | `LzmaEnc_Encode()` called | returns | 3,509,472 |
| decompress kernel | after `LzmaDec_Init()` | output CRC done | 429,119 |
| decompress call | `LzmaDec_Init()` | output CRC done | 429,130 |

The whole program is 4.18 M instructions. Data generation and setup take 211 k, and encoder init
takes 443 k, almost all of it clearing the fixed 132 k-entry BT4 hash, which LzFind keeps at a
minimum of 64 Ki + 66 Ki entries whatever the dictionary.

## Running it

```
python -B sim/cpu/bench/build_bench.py --benchmark lzma [--out-dir build/cpu/bench/lzma-d12-rv64imb-<core>]
python3 -B sim/cpu/bench/run_bench.py --benchmark lzma --out-dir <same> --core multicycle|pipe|ooo \
    [--lzma-mode full|sampled] [--jobs 3] [--sim icarus|verilator]
```

`--sim verilator` runs on Verilator instead of Icarus (see [simulator.py](../sim/cpu/simulator.py)
and the Verilator note in [dhrystone.md](dhrystone.md)). The mode then defaults to `full` for every
core, since the whole out-of-order program takes about 15 s. Verilator starts registers at 0 where
Icarus starts them at X, so a reset-dependence bug can hide; Icarus stays the cross-check.

The lzma build defaults to rv64imb (`rv64im_zba_zbb_zbs_zifencei`), 1 MiB RAM and a 2^12
dictionary (`--lzma-dict-log`). The runner checks the following:
- **Reference model.** It runs the image on `sim/cpu/reference.py` and checks every mailbox
  result.
- **liblzma.** It decodes the packed stream independently with Python's liblzma and compares the
  zlib CRC-32.
- **Timing.**
  - `full`: the whole program from reset, split by laps. This fits the multicycle and pipelined
    cores in a 5-minute step.
  - `sampled`: each kernel phase is cut into pieces. Each piece starts from a checkpoint image
    (`bench_checkpoint.py`: state rebuilt from the reference trace plus a 34-instruction
    register-restore stub), runs a warm-up, and is then timed over its retirement window. Phase
    clocks are the sum of the pieces. This is needed for the out-of-order model, which simulates
    at only about 200 clocks per second.
- **Trace check.** Every piece's trace, warm-up included, is compared with the reference model on
  `tb_core.sv`, with the wait-cycle settings 0 and 7 alternating between pieces. One checkpoint per
  phase is also replayed on the reference model to the end of the program.

The native harness `lzma_native.c` builds the same sources for the host, runs many passes and
estimates the clock from a dependent-add chain, so the kernel can be calibrated on a real CPU.

## Results, 2026-11-21 (architecture 0.14.6, rv64imb, clang 23.1.5 -O2; simulation)

Ratings are 7-Zip "MIPS" per MHz, which equals 7-Zip commands per clock; kernel phases only.

| Core | Mode | Compress clocks | IPC | MIPS/MHz | Decompress clocks | IPC | MIPS/MHz |
|---|---|---:|---:|---:|---:|---:|---:|
| multicycle (`rv64_core.sv`) | full | 2,255,190 | 1.360 | 1.605 | 259,246 | 1.655 | 1.691 |
| pipelined (`rv64_pipe.sv`) | full | 3,763,359 | 0.815 | 0.962 | 491,743 | 0.873 | 0.892 |
| out-of-order (`rv64_ooo.sv`) | full, Verilator 5.020 | 1,067,884 | 2.871 | 3.389 | 171,494 | 2.502 | 2.557 |
| out-of-order, earlier estimate | sampled, partial (Icarus) | about 1,089,000 (13 of 21 pieces) | 2.82 | about 3.32 | 171,624 (3 of 3) | 2.50 | 2.555 |
| Cortex-X925 native, same kernel | 4.27 GHz (add chain) | 434,230 | | 8.335 | 169,539 | | 2.586 |
| Cortex-X925, real `7zz b -mmt1 -md22` | about 4.2 GHz | | | about 1.91 | | | about 1.93 |

The full out-of-order run under Verilator passes all checks, including 24 trace checks against the reference
model (`run_bench.py --benchmark lzma --core ooo --sim verilator`, 147 s). The earlier sampled Icarus estimate
was 2.0% high on compression. Out-of-order compress was cut short to save time in that estimate. 13 of the 21 pieces of 150 k instructions were
timed (1.87 M of 3.07 M instructions, 662,620 clocks), and the total is scaled by instruction
count. Interpolating the missing pieces from their neighbours gives 1.07-1.10 M clocks instead, or
3.30-3.39 MIPS/MHz. Piece IPC ranges from 2.1 to 5.7; the literal-only start of the data runs at
about 5.5. The out-of-order pieces were not trace-checked on tb_core in this session. The first checkpoint
of each phase was replayed on the reference model to the end of the program.

Sampling accuracy: the sum of checkpointed pieces matches the contiguous run within 0.1%.
- multicycle, 1.2 M-instruction pieces with 50 k warm-up: compress 2,255,998 against 2,255,190;
  decompress identical.
- pipelined, 150 k-instruction pieces with 20 k warm-up (the out-of-order setting): compress
  3,766,251 against 3,763,359; decompress 491,986 against 491,743.

The kernel and real 7-Zip differ by different amounts in the two phases. On the X925 the scaled
kernel rates 4.4x the real `-md22` rating for compression and 1.34x for decompression, because
the small dictionary removes the cache misses and long match searches of a 4 MiB window.
Multiplying a core's kernel rating by 1.905 / 8.335 (compress) or 1.925 / 2.586 (decompress) gives
a rough 7-Zip-equivalent figure. That estimate assumes the core loses as much as the X925 does on
the large dictionary. Our cores, with idealized 1-clock memory, would probably lose less, so treat
the result as an estimate, not a measurement.
