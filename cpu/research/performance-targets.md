# Performance dimensions and per-clock "benchmark to beat" (research, 2026-11-22)

Started 03:20 EST, written 03:28-03:45 EST (`date`). Read-only research for the coordinator; it edits no target
document and sets no goal. Facts carry a source and date. **[F]** = fetched this session, **[S]** = from a search
summary of the named page (not fetched in full), **[R]** = recall or repository-internal, not re-fetched: check
before relying on it. **[J]** = my judgement or arithmetic. Per-GHz figures are score / reported peak clock, single
thread. Reported clocks for Apple chips come from Geekbench/Notebookcheck (Apple publishes none), so every Apple
per-clock figure carries about +-3% clock uncertainty.

## 1. Apple M6 status (facts)

* **M6 has shipped.** Announced 2026-08-25 (Apple press release, via [Wikipedia Apple M6](https://en.wikipedia.org/wiki/Apple_M6) [F],
  [MacRumors 2026-08-25](https://www.macrumors.com/2026/08/25/apple-reveals-m6/) [S]); Mac mini first (Wikipedia gives
  release 2026-09-22), then 14-inch MacBook Pro and iMac announced 2026-10-27
  ([MacRumors](https://www.macrumors.com/2026/10/27/14-inch-macbook-pro-with-m6-chip/) [S]). TSMC N2. CPU: 2 "super"
  + 4 performance + 6 efficiency cores. No M6 Pro/Max announced (Bloomberg, 2026-06, via Wikipedia).
* **Clocks** (Notebookcheck, not Apple): super and performance cores 4.78 GHz max, efficiency 2.94 GHz
  ([Notebookcheck M6 SoC analysis](https://www.notebookcheck.net/Apple-M6-SoC-Analysis-Apple-s-2-nm-chip-crushes-AMD-Intel-Qualcomm.1404057.0.html), 2026-09/10) [F].
  Some Geekbench listings report 4.93 GHz [S]; I use 4.78 and show 4.93 as the alternative.
* **Single thread, measured** (same Notebookcheck page) [F]: Geekbench 6.7 ST **4,698**, Cinebench 2024 ST **221**
  (M5 MBP 14: 4,326 / 200). Cinebench 2024 ST system power 14.5 W (M5 15.3 W).
* **Microarchitecture: not published.** No Chips and Cheese / Geekerwan M6 core analysis found. Geekerwan's A20 Pro
  review (same generation, 2026-09-18, [summary at kocpc](https://en.kocpc.com.tw/archives/25562) [F]) reports the
  super core at 4.93 GHz, decode narrowed 10 -> 9 wide, smaller schedulers / register files, integer IPC +3% vs A19 Pro,
  DRAM latency 70 ns from the S-core. That is the A20 Pro, not the M6; I assume the same core family **[J]**, unconfirmed.
* **Not found for M6:** SPEC CPU 2017, 7-Zip single thread, Speedometer/JetStream, cache sizes, FP latencies,
  SME throughput, single-core DRAM bandwidth. Where the table needs an Apple figure for these, it uses M4/M5/M1 and
  says so. No M6 number below is extrapolated unless marked **PROJECTION**.
* Geekbench 7 now exists (scores lower than GB6). All Geekbench figures here are GB6 for consistency.

## 2. Single-thread per-clock anchors (used by the bridges)

| Chip (core) | GB6 ST | Clock | **GB6 / GHz** | CB2024 ST | **CB24 / GHz** | Source |
|---|---:|---:|---:|---:|---:|---|
| Apple M6 (super core) | 4,698 | 4.78 (4.93) | **983** (953) | 221 | **46.2** (44.8) | Notebookcheck M6 analysis [F] |
| Apple A20 Pro | 4,719-4,735 | 4.93 | 957-960 | n/a | | leaks/reviews via Tom's Hardware, Notebookcheck, Tom's Guide [S], 2026-09 |
| MediaTek D9500 (Arm C1-Ultra) | 4,007 (vendor) | 4.21 | 952 | n/a | | MediaTek claim, GB6.4, via search [S] (vendor; GB6.4+ uses SME2 on some tests) |
| Apple M5 (MBP 14) | 4,326 | 4.61 | 938 | 200 | 43.4 | Notebookcheck [F]; clock from Geekbench via [Tom's Guide](https://www.tomsguide.com/computing/macbooks/whoops-apple-m5-benchmark-leaked-and-its-the-fastest-single-core-ive-ever-seen) [S] |
| Snapdragon 8 Elite Extreme Gen 6 (Oryon) | ~4,300 | 5.0 (not sustained) | ~860 | n/a | | [Notebookcheck](https://www.notebookcheck.net/Snapdragon-8-Elite-Extreme-Gen-6-hits-5-GHz-in-early-Geekbench-run-but-can-t-sustain-it.1377776.0.html), MobileSyrup [S] |
| Snapdragon X2 Elite Extreme (Oryon v3) | 3,826 | 5.0 | 765 | 151 | 30.2 | Notebookcheck [F] |
| **NVIDIA N1X (Cortex-X925), the laptop** | 3,096 | 4.1 | **755** | 131 | **32.0** | [Notebookcheck RTX Spark analysis](https://www.notebookcheck.net/Nvidia-RTX-Spark-Analysis-Finally-an-answer-to-Apple-s-M5-Pro-M5-Max.1422820.0.html) [F] |
| Intel Core Ultra X9 388H (Panther Lake, Cougar Cove) | 3,020 | 5.1 [R] | 592 | 129.8 | 25.5 | Notebookcheck [F]; clock [R] |
| AMD Ryzen AI Max+ 395 (Zen 5) | 2,978 | 5.1 [R] | 584 | 116.8 | 22.9 | Notebookcheck [F]; clock [R] |

Zen 6 has not shipped (only Geekbench leaks, e.g. EPYC "9996" GB7 2,847 at 4.1 GHz, 2026-10 [S]); Arm C2-Ultra
(Dimensity 9600 Pro, GB6 4,216 measured by Notebookcheck 2026-09-16 [F]) has no confirmed clock, so no per-GHz figure.

**Ratios to the laptop's X925 [J]:** GB6 per clock M6 **1.30x** (1.26x at 4.93 GHz), A20 Pro 1.27x, C1-Ultra 1.26x
(vendor score), M5 1.24x. Cinebench 2024 per clock M6 **1.44x** (1.40x at 4.93 GHz; 1.41x if the X925 ran 4.0 GHz).
The X925 clock under Cinebench/Geekbench is the 4.1 GHz spec max; our own cycle counts put it at 3.9-4.27 GHz, so
the X925 side also carries about +-4%.

## 3. Dimension table

"Leader" = fastest shipping core per clock that I could source. "Implied goal" = the dimension leader's per-clock
figure on our metric (1.0x leader), next to today's goal. Confidence: H = measured and same-workload, M = measured
but bridged or few samples, L = recall, vendor claim, or a weak bridge.

| # | Dimension | Our metric | Leader per clock (chip, figure, source) | Apple reference (chip, figure, source) | X925 laptop figure | Implied goal | Conf. |
|---|---|---|---|---|---|---|---|
| 1 | Integer, general (GB6) | none directly; proxy for bridges | **Apple M6 983 GB6/GHz** (Notebookcheck [F]); runner-up A20 Pro ~958, C1-Ultra 952 (vendor) | same (M6) | 755 GB6/GHz (Notebookcheck) | 1.30x X925 per clock | M |
| 2 | Integer, SPECint2017 rate-1 | none (SPEC not licensed/run here) | **Apple M4 Pro 13.7 at ~4.5 GHz = ~3.04/GHz** (David Huang via [jia.je](https://jia.je/benchmark/spec-cpu-2017-rate/), page 2026-10-08 [F]; clock [R]); M2 10.6/3.5 = 3.03 (jia own run [F]); tie with X925 | M4 Pro ~3.04/GHz; **M5/M6 SPEC not found** | ~11.8-12 at 3.9-4.0 GHz = **2.95-3.08/GHz** ([Chips and Cheese 2026-03-03](https://chipsandcheese.com/p/arms-cortex-x925-reaching-desktop) and a commenter citing Huang [F]) | ~1.0x X925 by SPECint (vs 1.30x by GB6): the bridges disagree | M |
| 2b | | | others: Zen 5 9950X 12.9/5.7 = 2.26; Oryon v1 9.25/4.0 = 2.31; Lion Cove 258V 9.37/~4.8 = 1.95; Golden Cove 10.6/5.5 = 1.93 (jia [F]) | | | | |
| 3 | FP scalar, SPECfp2017 rate-1 | rt scalar (indirect) | **Apple M1/M2 ~3.8/GHz** (M1 12.2/3.2, M2 13.3/3.5, jia [F]); runner-up Oryon v1 14.4/4.0 = 3.6 | M2 3.8/GHz; newer Apple not found | no number ("keeps pace with Lion Cove", C&C [F]) | unknown; no bridge | L |
| 4 | Vector FP32 peak | none yet (RVV planned, 16 FP32 FMA/clk at DLEN 256) | **Zen 5 desktop: 2 x 512-bit FMA = 32 FMA = 64 FLOP/clk** (C&C, AMD Hot Chips 2024 [S]) | Firestorm 4 x 128-bit = 16 FMA = 32 FLOP/clk (Dougall Johnson, units u11-u14 [F], M1); M5/M6 not published | **6 x 128-bit FMA = 24 FMA/clk** (C&C [F]; laptop FMLA.4S 6.0/clk measured, riscv-matrix.md [R]) | 32 FP32 FMA/clk (leader); Apple 16 | M |
| 5 | Vector int8 MAC peak (no matrix unit) | mm SIMD (not run on our core yet) | **X925 SMMLA 192 int8 MAC/clk** (laptop, riscv-matrix.md [R], measured 2026-11-22); Zen 5 VPDPBUSD zmm ~128 [R] | not published for M5/M6 | 192 peak, 102.8 sustained on 64^3 (laptop [R]) | 192 (= X925) | M |
| 6 | Matrix unit (AMX/SME) | mm G1-G3 SIMD | **Intel AMX (Xeon, server): 1,024 int8 / 512 BF16 MAC/clk per core** (Intel peak via Wikipedia [R]) | **M4 SME, one P-core: 256 FP32 / 512 int8 MAC/clk**, ~2,000 FP32 GFLOPS ([tzakharko m4-sme-exploration](https://github.com/tzakharko/m4-sme-exploration), arXiv 2409.18779, [Jena](https://scalable.uni-jena.de/opt/sme/micro.html) [S]); unit shared per cluster | none (X925 has no SME) | Apple: 256 FP32 / 512 int8 MAC/clk | M |
| 7 | Branch prediction (MPKI) | JS trace-model MPKI (js-engines.md), none measured on hardware | **no public same-workload MPKI for any shipping core** | none | not measured (PMU 0x22 BR_MIS_PRED_RETIRED available) | measure laptop MPKI on our 9 JS kernels and 7-Zip; goal <= laptop | none |
| 8 | Front end (I-cache, BTB) | JS kernels | I-cache: **Apple 192 KB** ([R], catalog); L1 BTB: **Zen 5 16K** [R]; X925 2,048-entry L1 BTB at 2 taken/clk (C&C [F]) | 192 KB L1I (M1-M4, [R]) | 64 KB L1I, 2K BTB L1, 16K total, 10 instr/clk sustained (C&C [F]) | structural, not a score | L |
| 9 | Web/JS (Speedometer 3.1, JetStream) | JS QuickJS-ng 9 kernels (interpreter) | **Apple M5 Chrome Speedometer 3.1 = 61 -> 13.2/GHz** ([9to5Mac 2026-06-05](https://9to5mac.com/2026/06/05/chrome-for-mac-breaks-benchmark-records-on-the-latest-macbook-pro/) [S]); no M6, no per-clock rivals found | M5 61 (Chrome) | not found (HotHardware: "bottom third" [S]) | no usable bridge; use GB6 1.30x | L |
| 10 | Memory: L1D / L2 load-to-use | `--ld-lat`, `--l2-lat` | L1D **Apple 3 clk** (M4 Pro, forum [S]; M1 [R]); L2 **X925 12 clk** (C&C [F]) | 3 / shared L2 ~16-27+ clk (forum, unverified) | 4 / 12 clk (C&C [F]) | deciding config uses 4 / 20: L2 is 8 clk worse than X925 (it stands in for L2+L3) | M |
| 11 | Memory: DRAM latency | `MEM_LAT` 350 clk | lowest ns: **A20 Pro 70 ns = ~345 clk at 4.93 GHz** (Geekerwan [F]) | same | not measured | 350 clk at 4 GHz = 88 ns is already in the leader's range | M |
| 12 | Memory: single-core DRAM bandwidth | mm V1b, bitnet decode (B/clk) | **Apple M1 Max 102 GB/s from one thread = ~32 B/clk** ([AnandTech 2021](https://at-web1.www.anandtech.com/show/17024/apple-m1-max-performance-review/2) [S]); M4 Max ~92 GB/s = ~20 B/clk (forum, unverified) | as leader | **8-9 B/clk (31-35 GB/s)**, int8 GEMV 8192^2 (riscv-matrix.md [R]; not STREAM) | 20-32 B/clk = 2.3-3.6x X925 | M/L |
| 13 | Memory-level parallelism | `N_MISS` (deciding config 4) | Lion Cove L2 80 miss-queue entries (catalog [R]); Apple/X925 not published | none | not published | Little's law [J]: 32 B/clk x 350 clk = 11 KiB in flight = ~175 64-B lines | L |
| 14 | Compression (7-Zip) | `7z b -md22` per MHz and the d22 kernel | **Apple (bridged)**: no single-thread 7-Zip for M2-M6 found; M1 2.22 / 2.52 per MHz (7-cpu.com, 7-Zip 16.04 [R]) | M6 bridged 2.48-2.99 / 2.51-3.39 (section 4) | **1.91 / 1.93 measured** (7-Zip 26.06, laptop) | see section 4 | L/M |
| 15 | Ray tracing (scalar + SIMD) | rt RT-T / RT-P | **Apple M6 Cinebench 2024 ST 46.2/GHz** (Notebookcheck [F]); runner-up M5 43.4; then X925 32.0, X2 Elite 30.2 | M6 46.2/GHz | 32.0/GHz | 1.44x X925 per clock | M |
| 16 | Media (FFmpeg/x264/dav1d) | none yet (ffmpeg.md research only) | **no per-clock single-thread data found** | none | not measured | none; measure laptop first | none |
| 17 | LLM inference per core | mm GEMV, bitnet kernels | no per-clock leader figure; decode is B/clk-bound (row 12). T-MAC BitNet 3B 30 tok/s on one M2 Ultra core (bitnet-ternary.md [R]) | M2 Ultra 30 tok/s/core (BitNet 3B, T-MAC) | 8-9 B/clk DRAM; SDOT 19-22 ternary weights/clk (bitnet-ternary.md [R]) | decode: Apple-referenced bandwidth 2.3-3.6x X925 | L |
| 18 | FP latency | FP chains (0.17.0: FADD 3, FMUL 4, FMA 4, FDIV.D 13, FSQRT.D 18) | **FADD 2 clk: Zen 5** (AMD Hot Chips 2024 [S]); Golden/Lion Cove and X925 FADD 2 [R]; FMA 4 everywhere [R] | Firestorm FADD 3 (Dougall [F]), FMA 4 [R]; M5/M6 not published | FADD 2, FMUL 3, FMA 4 [R: Arm SOG 109842 not fetched] | FADD 2 / FMA 4; FDIV.D ~4-5 issue interval [R] | L/M |
| 19 | Dhrystone | DMIPS/MHz | no reputable per-clock figure for current cores | none | native-dhrystone exists in build/ [R] | keep current goal | n/a |
| 20 | Power / area | none (goals are per clock) | Cinebench 2024 ST points/W, system: **M6 15.2** vs N1X 3.9-4.3 (Notebookcheck [F]); not per clock | M6 | ~9 W core, 30 W system | noted only | n/a |

## 4. Bridges per benchmark and implied per-clock goals

A bridge scales the laptop measurement (identical workload, cycle counter) by the leader/X925 per-clock ratio on the
closest public workload. Each bridge adds the uncertainty of that ratio (both clocks +-3-4%, so about +-6% before
any workload mismatch).

| Our benchmark | Today's goal | Bridge workload | Ratio (M6 / X925 per clock) | **M6-referenced goal** (leader = M6 on every bridge used) | Stricter? |
|---|---|---|---|---|---|
| 7-Zip `7z b -md22` (per MHz) | 2.50 / 2.50 (10,000 MIPS at 4 GHz; 1.3x X925) | (a) GB6 ST per clock | 1.30 (1.26-1.30) | **2.48 / 2.51** -> d22 kernel 2.01 / 2.19 | equal to today's (today: 2.03 / 2.18 kernel) |
| | | (b) M1 7-cpu 7-Zip x GB6 M6/M1 per clock (M1 GB6 ~731/GHz [R]) | 1.56 / 1.76 | **2.99 / 3.39** -> d22 kernel 2.43 / 2.96 | yes, by 1.20x / 1.36x; 0.16.0 (2.187 / 2.322) would be 90% / 78% |
| rt (rays/kclk, paths/Mclk) | 1.5x X925 | Cinebench 2024 ST per clock (Redshift path tracer, SIMD) | 1.44 (1.40-1.44) | scalar P 5.92, S-ch 2.15, S-ah 2.59; SIMD P 17.4, S 8.64; RT-P 541 | no: today's 1.5x is ~4% stricter |
| JS (clocks per kernel) | laptop / 1.5 (suite 28.06M clocks) | GB6 ST per clock (contains HTML5-browser and navigation tests); Speedometer has no X925 figure | 1.30 | laptop / 1.30 (suite 32.38M clocks) | no: today's is 15% stricter |
| mm scalar (MAC/clk) | not set | GB6 ST per clock | 1.30 | 1.30x laptop (G1 0.83, G3 1.17, V1 1.13, V4 0.67 MAC/clk) | n/a |
| mm SIMD / matrix (MAC/clk) | not set | peak MAC/clk (row 6) | int8 512 / 192 = 2.7x; FP32 256 / 24 = 10.7x | 512 int8 / 256 FP32 MAC/clk peak (Apple M4 SME); leader Intel AMX 1,024 int8 | n/a |
| LLM / ternary decode (B/clk, tok/s) | not set (bitnet-ternary.md has estimates) | single-core DRAM bandwidth per clock | 2.3-3.6x (M1 Max / M4 Max, not M6) | 20-32 B/clk sustained from DRAM | n/a; needs ~175 lines in flight |
| Dhrystone | 20, then 30 DMIPS/MHz (superseded by 7-Zip) | none | | keep | |

**Leader vs Apple:** on every bridge I could source (GB6, Cinebench 2024, single-core bandwidth) the per-clock
leader **is** Apple (M6, or older Apple where M6 data does not exist), so "leader" and "Apple reference" give the same
goal. Exceptions where Apple is not the leader: vector FP32 peak (Zen 5 512-bit), int8 SIMD without matrix
(X925 SMMLA), matrix peak (Intel AMX, server only), FADD latency (2 clocks on Zen 5 / Intel / Arm vs Apple's 3), and
SPECint per clock (M4 Pro and X925 tie at ~3.0/GHz; M6 SPEC unpublished).

**Recommendations [J]:**
* 7-Zip: becomes "leader per clock" naturally; today's 2.5 MIPS/MHz equals M6 on the GB6 bridge. If the user wants
  margin for the weaker but workload-specific M1-anchored bridge, the goal would rise to ~3.0 / 3.4.
* rt and JS: keep "laptop + 50%"; it is stricter than M6 on the available bridges (1.44x and 1.30x).
* mm: scalar goal 1.5x laptop for consistency; separate peak goals for vector (32 FP32 FMA/clk to tie Zen 5) and
  matrix (Apple M4 SME 256 FP32 / 512 int8 MAC/clk) if a matrix unit is in scope.
* LLM decode: the only dimension where an Apple reference is far stricter (2.3-3.6x X925 bytes/clk); it sets the
  MLP requirement, not a compute one.
* Branch MPKI, media and FP latency have no usable public per-clock leader on our workloads; the cheapest valid
  reference is the laptop's own PMU (branch misses, I-cache misses) on our identical workloads.

**PROJECTION (labelled, not a fact):** M6 SPECint2017 rate-1 per GHz = M4 Pro 3.04 x GB6 per-clock gain M4 -> M6
(~875 -> 983/GHz, M4 figure [R]) = ~3.4/GHz. Not used in any goal above.

## 5. Caveats and repository notes

* Geekbench 6.4+ uses SME/SME2 in some subtests on Apple M4+ and Arm C1; the X925 has no SME, which inflates
  the Apple and C1 GB6 ratio relative to scalar workloads like 7-Zip and QuickJS **[J]**. Cinebench 2024 does not use
  SME as far as I know **[R]**.
* SPECint per clock (X925 ~= M4 Pro) and GB6 per clock (M4 1.16x X925, M6 1.30x) disagree; different compilers,
  OS and memory. The bridges inherit this.
* M6 clock: Notebookcheck 4.78 GHz vs some listings 4.93 GHz; both shown.
* 7-cpu.com M1 numbers are 7-Zip 16.04; our laptop ran 26.06. The 7-Zip targets page already warns of up to 1.7x
  version effects, which is why bridge (b) is L confidence.
* `build/research/bitnet-ternary.md:282` labels the laptop "Snapdragon X2 Elite at about 3.8 GHz"; every other
  document says Cortex-X925 (N1X). Probably a wording error in that report; worth a check.
* Fetch failures: browser.geekbench.com returned 403 (no per-result subtests); Arm X925 Software Optimization Guide
  not fetched, so X925 FP latencies are recall.

## Sources (fetched or searched 2026-11-22)

Notebookcheck M6 analysis; Notebookcheck RTX Spark analysis; Notebookcheck Dimensity 9600 Pro (2026-09-16);
Wikipedia Apple M6; tech-insider.org M6 vs M5; kocpc Geekerwan A20 Pro summary (2026-09-18); Chips and Cheese
Cortex X925 (2026-03-03); jia.je SPEC CPU 2017 rate table (updated 2026-10-08); Dougall Johnson Firestorm SIMD
tables; AnandTech M1 Max review (2021) via search; 9to5Mac Chrome Speedometer 3.1 (2026-06-05) via search;
tzakharko m4-sme-exploration, Jena SME pages via search; AMD Hot Chips 2024 Zen 5 via search; Tom's Hardware/Notebookcheck
A20 Pro and Snapdragon 8 Elite Extreme Gen 6 leaks via search.
