# Standards, formats and metrics review (2026-11-22, `date` 03:06 EST at start)

Scope: governing documents per number format and metric, and gaps in our contract, models, tests and target docs.
Method: repo reading plus web search of official pages. The paywalled IEEE 754 text was NOT read; I relied on the
RISC-V spec's own wording, IEEE abstracts and secondary sources. Items marked (unverified) need a primary-source check.

## 1. IEEE 754 and the RISC-V mapping

Sources: IEEE 754-2019 (standards.ieee.org/ieee/754/6210, abstract only); RISC-V unprivileged ISA at
https://docs.riscv.org/reference/isa/unpriv/f-st-ext.html and https://docs.riscv.org/reference/isa/unpriv/zfa.html (v20260120).

* 754-2019 vs 2008: adds minimum/maximum/minimumNumber/maximumNumber (and magnitude forms), augmented
  addition/subtraction/multiplication, clearer conversion rules, more recommended functions; minNum/maxNum are deprecated
  (not associative with sNaN). Formats binary16/32/64/128; five exceptions (invalid, divide-by-zero, overflow, underflow, inexact) with
  default non-trapping results; five rounding attributes (RNE, roundTiesToAway, RTZ, RTP, RTN). Tininess: implementer picks before or after
  rounding but must be consistent. NaN payload propagation is a "should", not a "shall".
* RISC-V choices: canonical NaN (0x7fc00000 / 0x7ff8000000000000), no payload propagation, tininess after rounding, no traps (flags only),
  NaN-boxing, FMIN/FMAX = minimumNumber/maximumNumber since F v2.2 (sNaN sets NV, other operand returned, two NaNs give canonical NaN),
  RMM = roundTiesToAway. Zfa adds FMINM/FMAXM (754-2019 minimum/maximum: any NaN gives canonical NaN; sNaN sets NV), FROUND/FROUNDNX, FLI, FLEQ/FLTQ (quiet
  compares), FCVTMOD.W.D. Zfh is IEEE binary16; Zfhmin only converts.
* Vector vfmin/vfmax: an LLVM list post claims the text says 2019 while behaviour is 2008-like (unverified; check the V spec).

## 2. Other formats

| Format | Governing document | Status |
|---|---|---|
| binary16/32/64 | IEEE 754-2019; RISC-V Zfh/F/D | normative |
| BF16 | Not IEEE. RISC-V Zfbfmin, Zvfbfmin, Zvfbfwma define conversion and widening multiply-accumulate behaviour | ratified RISC-V |
| OCP FP8 E4M3/E5M2 | OCP "8-bit Floating Point Specification (OFP8)" rev 1.0. E4M3 has no infinities and one NaN pattern; E5M2 is IEEE-like | OCP industry spec |
| MX (MXFP8/6/4, MXINT8) | OCP Microscaling Formats (MX) Spec v1.0 (2023); block of 32, E8M0 power-of-two scale; MXFP4 = E2M1, MXFP6 = E3M2/E2M3. Secondary sources mention a v1.1 (unverified). arXiv 2310.10537 | OCP |
| P3109 ML formats | IEEE P3109 WG Interim Report v4.0 (2026-06-26): "unapproved IEEE Standards Draft"; parameterised binary formats, one NaN, rounding plus saturation modes (sagroups.ieee.org/p3109wgpublic) | NOT a standard |
| two's-complement ints | RISC-V base ISA | normative |
| RVV fixed point | RISC-V V spec: vxrm rnu 00, rne 01, rdn 10 (truncate), rod 11 (jam); vxsat sticky | ratified |
| ternary, int4, GGUF, bitnet.cpp packing | de facto conventions, no standard; we must define them in our own ABI doc | none |
| fixed point/saturating (RPCS3 SIMD) | Cell/PowerPC semantics, not IEEE | none |

## 3. Testing and conformance
* Berkeley SoftFloat/TestFloat Release 3e (2018-01-20, J. Hauser, jhauser.us/arithmetic/TestFloat.html): Berkeley BSD-style licence; TestFloat needs SoftFloat; it
  covers f16/f32/f64/f128/extF80, all rounding modes, flags, a tininess switch; the RISC-V specialisation of SoftFloat exists (Spike uses it). Best independent oracle for us. Build from source; no binaries.
* IBM FPgen: coverage-model test suites for 754; distribution and licence (unverified).
* riscv-arch-test (github.com/riscv-non-isa/riscv-arch-test): F, D, Zfh, V tests, signature-based, run with a reference model (unverified detail; my search found no coverage page).
* Sail RISC-V (github.com/riscv/sail-riscv): the formal golden model; its FP uses the SoftFloat C library.
* Claims: "IEEE 754 conformant" needs all required operations for a format with documented attribute choices. RISC-V hardware lacks several (remainder,
  nextUp, scaleB, logB, ...), so say "RISC-V F/D semantics, following 754 with the deviations listed". We may claim bit-exact agreement with our own models on N vectors. We may NOT claim IEEE conformance, riscv-arch-test passing or Sail equivalence until they are run.

## 4. Metrics
* Binary prefixes: IEC 80000-13 and IEEE 1541-2002 (KiB, MiB = powers of 1024). KB/MB are SI powers of 1000.
* Dhrystone: Weicker, CACM 27(10), 1984, and the Version 2 rationale (1988). DMIPS = Dhrystones/s / 1757 (VAX 11/780). DMIPS/MHz divides by clock in MHz. Run rules: strcpy/strcmp stay real
  calls, no cross-module inlining, validate outputs, report compiler/flags, run long enough for timer granularity.
* 7-Zip: its documentation defines no rating formula (www.7-zip.org/7z.html gives only speed ranges). The rating lives in the source (CPP/7zip/UI/Common/Bench.cpp): fixed per-byte "command" counts scaled to measured speed, so "MIPS" is nominal, not retired instructions. Cite version, -mmt, -md.
* SPEC CPU 2017 run rules (spec.org/cpu2017/Docs/runrules.html): base vs peak, at least 3 iterations with the median, ratios to a reference machine, geometric mean over benchmarks.
* Statistics: SMARTS (Wunderlich et al., ISCA 2003): systematic sampling, CI from sample CPI variance, functional plus detailed warm-up. SimPoint (Sherwood et al., ASPLOS 2002): weighted phase representatives, error not a CI. Fleming & Wallace (CACM 1986): normalised ratios need a geometric mean. Smith (CACM 1988): rates need the harmonic mean, times the arithmetic. A ratio of totals differs from the geometric mean of per-kernel ratios; a CI on a ratio needs the delta method or a bootstrap.
* IEEE 1800 SystemVerilog (2017, revised 2023): the RTL language; record simulator version and the subset it needs.

## 5. Gap analysis (file:line)
Severity H/M/L. Cost: T test-only, W wording, C contract change.

1. H: No independent FP oracle. build/cpu/fp/NOTES.md:38,53 (fracoracle.py is our own Fraction rounding); build/cpu/fp/FP-CONTRACT.md:75 cites "the Sail model and Spike" but none was run; cpu/architecture.md:199 says Sail/Spike comparison is pending. Fix: compile SoftFloat/TestFloat 3e from source and cross-check f32/f64 x 5 modes x all ops (T, medium).
2. H: No op x rounding-mode x boundary coverage matrix in sim/cpu/fp_cases.py (only spot cases); the TestFloat run in 1 would also close it. Fix: generated coverage report (T).
3. M: build/cpu/fp/FP-CONTRACT.md:7 and cpu/architecture.md:37 cite "IEEE 754-2008" while FP-CONTRACT.md:61 and architecture.md:49 use 754-2019 min/max. Fix wording: basis 754-2008/2019 as RISC-V F/D v2.2 states, min/max per 2019 (W).
4. M: Zfa, Zfhmin, Zvfhmin, Zvfbfmin absent (FP-CONTRACT.md:138), yet RVA23U64 lists them. No contract text for FMINM/FMAXM, FROUND, bf16 conversions (C, large).
5. M: RVV fixed point not implemented (build/cpu/fp/RVV-CONTRACT.md:28-30 storage only, :231 lists vsadd/vxrm). Needs contract text for the four vxrm modes and vxsat, plus tests, before ffmpeg/RPCS3-class workloads (C).
6. M: Tininess-after-rounding is verified only against our own models (NOTES.md:40 notes AArch64 differs). TestFloat has a tininess switch; add a cross-check (T).
7. M: cpu/js-benchmark-targets.md:101,133-144 and :124-128: geometric mean over kernels is shown next to per-kernel CIs but has no CI of its own; define "ratio of totals vs geomean", add a bootstrap CI over piece CPIs, and state that piece-CPI spread does not bound warm-up bias (W/T).
8. M: cpu/7zip-benchmark-targets.md:9-15,26-28,53,64: rating is nominal (not instructions/s), "4 MB" for -md22 is 4 MiB, per-MHz mixes published ratings at assumed 4.2 GHz with our simulated clocks (W).
9. L: KB/KiB mix: cpu/dhrystone.md:95 ("15.7 KB" next to "16 KiB"); cpu/7zip-benchmark-targets.md:15,28,85-86 "4 MB"/"4.19 MB" vs :108 "4 MiB" for the same quantity (W).
10. L: cpu/dhrystone.md:3,31 reports a labelled "fast runtime" (word-at-a-time strcpy/strcmp) that departs from Weicker's rule; keep it labelled non-comparable and keep MIPS/MHz (7-Zip) and DMIPS/MHz (Dhrystone) in separate columns (architecture.md:288-298 history mixes them) (W).
11. L: build/research/riscv-matrix.md and bitnet-ternary.md should call P3109 a draft, OFP8 E4M3 inf-free, and int4/ternary packing de facto (W).
12. L: No stated SystemVerilog version/simulator subset in sim/cpu/run.sh or architecture.md; record tool versions and language mode (W).

Suggested order: 1, 2, 6 (tests); then 3, 7-12 (one wording commit, no CPU version bump); then 4 and 5 as separate MINOR contract steps.
