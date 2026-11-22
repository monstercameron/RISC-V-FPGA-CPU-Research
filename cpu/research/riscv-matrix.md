# RISC-V matrix engines: landscape, comparison, fit to our core, and a benchmark

Research engineer, 2026-11-22 01:36 to 01:55 (clock: `date` in Git Bash). Repository HEAD `c607485`, nothing in
the repository edited. Native prototypes live in `build/research/matrix/` (ignored). No model weights or binaries
were downloaded; specifications and code were read on the web and are summarised, not copied.

**How to read this.** **Fact** marks something taken from a named source (URL, with the date shown or read).
**Measured** marks a number from my own run (section 6). **Judgement** marks my estimate or recommendation.
ISA/profile status, simulation results and physical-hardware claims are kept apart, as AGENTS.md requires.
BitNet / ternary inference is covered by the parallel agent (`build/research/bitnet-ternary.md`, not yet written
when I finished; its working folder `build/research/bitnet/` exists). Here ternary appears only as one data type.

---

## 0. Summary

* **Nothing in RISC-V matrix land is ratified yet.** The ratified pieces that matter for matmul are RVV 1.0 itself
  (widening integer and FP MACs), **Zvfbfmin / Zvfbfwma** (BF16 convert and widening BF16 FMA, ratified 2024) and
  **Zvfh / Zvfhmin**. The 8-bit dot product (**Zvdot4a8i**, formerly Zvqdotq) is a fast-track draft (v0.7, internal
  review, Oct 2026) and is expected to be ratified before any matrix extension. Three matrix approaches are drafts:
  **IME** (matrices in vector registers, `vtype.lambda`), **VME / Zvt** (outer products from vector registers into
  new tile accumulators) and **AME / Ztt v0.6** (fully separate tile state). Vendors ship their own: SpacemiT IME
  (in llama.cpp), XuanTie MME / AME (C907, C950), SiFive XM (VCIX-attached), Andes AMM, Semidynamics Tensor Unit.
* **Decode is memory-bound; prefill is compute-bound.** At int8 a GEMV does 1 MAC per weight byte. Our SoC model's
  ceiling is 8 B/clk (64-bit beat bus, MEM_GAP 8), which needs only 8 int8 MACs per clock: RVV already has 4-8x that.
  At the deciding configuration (MEM_LAT 350, N_MISS 4, 8 B L1 lines, no prefetcher) a streaming GEMV is
  latency-bound at about **0.17 B/clk: about 0.55 tokens/s for a 1B int8 model at 4 GHz**, against about
  **26 tokens/s** at the 8 B/clk ceiling. No matrix engine changes that; memory-level parallelism does.
* **Recommendation (Judgement): Option A first, then a small Option B.** RVV widening, then BF16 (Zvfbfwma), then
  Zvdot4a8i behind a draft-tracking option, all on the existing pipes and register file, no new state. Add an
  IME-style instruction (a SpacemiT-vmadot / IME lambda=2 shape: 128 int8 MACs per instruction at VLEN 256 with a
  2-register accumulator) only after the `mm` benchmark shows prefill is the limit and the IME draft has settled.
  Defer AME / VME tile state until the core has `mstatus` (stage C1) and those specs freeze.
* **Benchmark:** a deterministic `mm` suite for `run_bench.py` (int8 / int4 / BF16 / FP32 GEMM and GEMV, plus one
  tiny transformer block), with host-generated data, FNV-1a checksums and scalar / RVV / matrix variants. The
  laptop prototype already gives reference numbers (section 6). The laptop has **no SME**; SVE is only 128 bits.

---

## 1. The RISC-V landscape (official and vendor sources)

### 1.1 RISC-V International specifications

| Extension | Status (date read) | State added | Data types | What it computes |
|---|---|---|---|---|
| **V 1.0** widening ops (`vwmacc[u,su,us]`, `vwmul`, `vfwmacc`, `vfwcvt`) | Ratified 2021, mandatory in RVA23U64 | none | int8->16, 16->32, 32->64; FP16->FP32 (with Zvfh), FP32->FP64 | elementwise widening MAC; 2x wide destination |
| **Zvfh / Zvfhmin** | Ratified; Zvfhmin mandatory in RVA23U64, Zvfh optional | none | FP16 arithmetic (Zvfh), FP16<->FP32 converts (Zvfhmin) | FP16 vector arithmetic incl. `vfwmacc` FP16->FP32 |
| **Zfbfmin / Zvfbfmin / Zvfbfwma** | **Ratified**, BF16 spec v1.0 "05 July 2024: Ratified"; optional in RVA23 | none | BF16 converts; BF16 x BF16 + FP32 | `vfwmaccbf16.vv/.vf`: widening BF16 FMA into FP32 (single rounding) |
| **Zvdot4a8i** (was **Zvqdotq**) | Fast-track draft **v0.7**, ISA-manual PR #2576 still Draft, internal-review PDF posted 2026-10-16; LLVM renamed it (PR #179393, Feb 2026), experimental | none | 4 x int8 (s/u/su/us) -> int32 accumulator, SEW = 32 only | `vdot4a[u,su].vv/.vx`, `vdot4aus.vx`: each 32-bit element += dot of 4 packed bytes |
| **Zvdota / Zvbdota** (batched dot products) | Draft, ISA-manual PR #2618 open (opened 2026-01-29; reviews to 2026-11-01) | none | int8, FP8 (OFP8), FP16, BF16 -> wider | batched dot products using RVBNA rounding (round-to-odd in dot mode) |
| **Zvfbfa** (`vtype.altfmt`), **Zvfofp8min**, Zvfofp4min | Zvfbfa draft; Zvfofp8min tag 0.9 (QEMU v5, Apr 2026); Zvfofp4min dropped from ratification track | `vtype.altfmt` bit | BF16 arithmetic via altfmt; OFP8 E4M3/E5M2 converts | format selection for later matrix/dot work |
| **IME** (Integrated Matrix Extension; Zvvmm, Zvvfmm, Zvvmtls, Zvvmttls) | Draft in `github.com/riscv/integrated-matrix-extension`, no version line in the source read 2026-11-22; TG charter in riscv-admin | `vtype.lambda[2:0]`, `vtype.bs`, `vtype.altfmt_A/B` (written only by `vsetvl`) | int4/8/16/32/64; OFP4, OFP8, FP16, BF16, FP32, FP64; OCP MX block scales (E8M0, blocks 32/16) | `C += A x B^T`, A/B/C in vector register groups; tile `M = (VLEN/SEW)/lambda`, `K = lambda*W*LMUL`, `N = vl/(lambda*LMUL) <= M`, accumulator `EMUL_C = (VLEN/SEW)/lambda^2` |
| **VME / Zvt** (vector-matrix, outer product) | Draft **v0.3** (Coral NPU page, 2026; PDF dated 2026-08-31); spec PR #2997; TG charter presented at TSC 2026-02-04 | 4 accumulator tiles (TEW 32: mt0, mt4, mt8, mt12), TE x TE with 4 <= TE <= VLEN/4; `mtype` CSR; `mstatus.MS[30:29]` (like FS) | int8 (x4 widening), int16, 32-bit; BF16 / FP16 / OFP8 via altfmt using RVBNA | `C[M,N] += A[K,M]^T x B[K,N]` outer products from vector registers into tiles; `vtle/vtse`, `vtmv`, `vtzero`, `vtdiscard` |
| **AME / Ztt** (Attached Matrix Extension) | Draft **v0.6** (release tag v0.6 in `github.com/riscv/riscv-attached-matrix-extension`); TG recalled its data-type vote in Dec 2025 to pivot | independent of RVV: 16 or 32 matrix (M) registers, 1-16 accumulator (A) registers, per-register datatype registers, `mstatus.MS` with Off/Initial/Clean/Dirty | per-register datatype incl. rounding; FP described by exponent width etc. | >100 ops: matrix-matrix (fat inner product), element-wise (incl. tanh, log2), reductions |

Sources: [BF16 spec, ratified](https://docs.riscv.org/reference/isa/unpriv/bfloat16.html);
[Zvdot4a8i PR #2576](https://github.com/riscv/riscv-isa-manual/pull/2576) (read 2026-11-22);
[riscv-dot-product repo](https://github.com/riscv/riscv-dot-product) (Zvqdotq source);
[LLVM rename to zvdot4a8i](https://lists.llvm.org/pipermail/cfe-commits/Week-of-Mon-20260202/803240.html);
[Zvdota / Zvbdota PR #2618](https://github.com/riscv/riscv-isa-manual/pull/2618);
[QEMU Zvfofp8min v5, 2026-04-27](https://patchew.org/QEMU/20260427060928.2322570-1-max.chou@sifive.com/);
[IME source](https://github.com/riscv/integrated-matrix-extension/blob/main/src/unpriv/integrated-matrix.adoc)
(first 100k of 331k characters read) and [IME charter](https://github.com/riscv-admin/integrated-matrix-extension/blob/main/charter.adoc);
[Zvt / VME v0.3 on the Coral NPU site](https://developers.google.com/coral/guides/hardware/vme-isa-extensions);
[TSC 2026-02-04 minutes](https://riscv.atlassian.net/wiki/spaces/TSCX/pages/1100742657/2026-02-04+TSC+Meeting) (via search snippet);
[AME repo](https://github.com/riscv/riscv-attached-matrix-extension) and [charter](https://github.com/riscv-admin/attached-matrix-facility/blob/main/charter.adoc);
secondary summaries: [FPRox, "RISC-V Matrix Extensions", 2026-11-14](https://fprox.substack.com/p/risc-v-matrix-extensions)
and [FPRox, "RISC-V Vector Is Expanding", 2026-01-25, updated 2026-07-10](https://fprox.substack.com/p/risc-v-vector-is-expanding);
[ServeTheHome, Hot Chips 2026 standards update, 2026-09-02](https://www.servethehome.com/update-on-risc-v-standards-and-adoption-at-hot-chips-2026/)
(confirms AME / IME / VME plus a "fast-track vector-based option", no dates).

**Facts worth keeping in mind.**
* IME's charter targets more than 2x over vector code, VLEN-portable binaries, 32-bit encodings and little new CSR
  state; first data types int8, BF16, FP32, FP64, later FP8 and 4-bit block FP.
* IME exactness: products exact; `psm=0` exact partial sums, `psm=1` an implementation-defined reduction that must
  be published (with a SAIL fragment); `rnd` = frm / round-to-odd / exact. Our traces must therefore fix one mode.
* IME examples (from the spec text, VLEN 512, SEW 32): lambda 1 gives 16 x 16 = 256 MACs per rank-1 update with an
  accumulator of 16 registers; lambda 4 gives 4 x 4 x 4 = 64 MACs with a 1-register accumulator. The accumulator /
  input ratio is the main design knob.
* VME adds tile state and an `mstatus.MS` field; AME adds a whole register file and `mstatus.MS`. IME and
  Zvdot4a8i add **no** state beyond `vtype` bits.
* FPRox (2026-11-14): no dot-product or matrix extension is ratified; only Zvdot4a8i is on the fast track.

### 1.2 Vendor extensions

| Vendor | Name / product | Status | Model | Data types | Throughput (vendor claims unless measured) |
|---|---|---|---|---|---|
| **SpacemiT** | IME (`vmadot*`, `vfmadot*`, sliding-window `vmadot1/2/3/n`); K1 / X60 (IME1), K3 A100 cores (IME2) | Shipping silicon; spec public (spacemit-com/riscv-ime-extension-spec); LLVM `xsmtvdot` | reuses vector registers; at VLEN 256, SEW 8: A 4x8 (1 reg) x B 8x4 (1 reg) -> C 4x4 int32 (2 regs, even vd); VLEN 512 uses 2 "copies" | int4/8/16, fp4/fp8/fp16/bf16 | **128 int8 MACs per instruction** at VLEN 256; claims ">10x" for AI |
| **T-Head / XuanTie** | MME ("RISC-V Matrix Extension" proposal v0.6.0, Apache-2.0); C907 first implementation; C950 with "AME v0.5" TPE | proposal; C907 / C950 IP | separate source and accumulator tile registers, RLEN 128-1024+ | int4, int8, fp16, bf16, fp32 (C950 TPE adds FP8, MXFP8/MXFP4) | 0.5-32 TOPS by RLEN; C950 TPE 8 TOPS each; a 64-core C950 *target configuration* claims Qwen3.8-27B decode >30 tok/s (vendor) |
| **SiFive** | Intelligence X280 / X390 Gen 2 (VLEN 1024 / DLEN 512 dual VPU on X390), XM Gen 2 cluster | IP; first silicon expected Q2 2026 | XM matrix engine fed from vector registers, 1-4 X300 cores as control units; **VCIX** (Xsfvcp, `sf.vc.*`, software spec 1.0.0) attaches custom units to the vector register file | int8, BF16 | XM cluster **16 TOPS int8 / 8 TFLOPS BF16 per GHz** (about 2,048 int8 MAC/clk per 4-core cluster, my division) |
| **Andes** | AX46MPV with "Andes Matrix Multiply" extension, ACE / COPILOT custom instructions, ACE_RVV | IP, production release Oct 2025 | RVV 1.0 VLEN up to 1024; matrix datapath details not public | not public | DGEMM tuning claims only |
| **Semidynamics** | Tensor Unit, Cervell NPU | IP | built on its RVV 1.0 unit, **uses the vector registers, no new architectural state** (runs on stock vector Linux) | INT8, INT4, FP16, BF16... | Cervell up to 8 TOPS int8 at 1 GHz (edge) to 256 TOPS int4 |
| **Tenstorrent** | Ascalon (RVA23 OoO CPU); Tensix | IP / silicon | matrix math in Tensix engines driven by small RV32IM cores; no RISC-V matrix ISA found | — | — |
| **Google** | Coral NPU | open | carries the Zvt (VME) draft | int8, BF16, OFP8 | — |

Sources: [SpacemiT IME spec](https://github.com/spacemit-com/riscv-ime-extension-spec) and
[instruction-func.adoc](https://github.com/spacemit-com/riscv-ime-extension-spec/blob/master/src/instruction-func.adoc);
[XuanTie MME](https://github.com/XUANTIE-RV/riscv-matrix-extension-spec) and
[RISC-V blog on MME](https://riscv.org/blog/xuantie-matrix-multiply-extension-instructions/);
[C950 / Qwen3.8-27B write-up](https://rits.shanghai.nyu.edu/ai/xuantie-c950-qwen38-riscv/) (vendor target configuration, not a measurement);
[SiFive XM series](https://sifive.com/cores/intelligence-xm-series), [X390](https://www.sifive.com/cores/intelligence-x390),
[LLVM VCIX docs](https://llvm.org/docs/RISCV/RISCVVCIX.html), [binutils VCIX 1.0 patch](https://sourceware.org/pipermail/binutils/2023-December/130905.html);
[Andes AX46MPV](https://design-reuse.com/news/56944/andes-vector-processor-ax46mpv-with-matrix-extension.html);
[Semidynamics Tensor Unit](https://www.design-reuse.com/news/55074/semidynamics-fully-coherent-risc-v-tensor-unit-ai.html);
[Tenstorrent RISC-V guide](https://docs.tenstorrent.com/tt-vscode-toolkit/riscv-guide/).

### 1.3 Software support

* **llama.cpp / ggml (Fact).** RVV dot-product kernels since 2023 (PR #2929: q4_0, q4_1, q5_x, q8_0), later
  LMUL tuning and K-quants, VLEN-agnostic selection (PR #17496), more RVV quant kernels in release b8329
  (iq4_nl, mxfp4, ...); build option `GGML_RVV` default on. **SpacemiT IME backend** merged 2025-09-29
  ([PR #15288](https://github.com/ggml-org/llama.cpp/pull/15288)), `ggml/src/ggml-cpu/spacemit/`, IME for Q4_0 / Q4_1 /
  Q4_K; on X60 with 4 threads, Qwen2.5 0.5B Q4_0: pp512 64.1 t/s, tg128 10.0 t/s; 3B: 12.1 / 2.2. A later Q8_0 IME1
  kernel took pp128 from 10.7 to 93.9 t/s (Qwen2.5-0.5B Q8_0, Milk-V Jupiter). On K3 A100 cores with IME2
  ([dev.to, 2026-03-12, corrected 2026-05-15](https://dev.to/gounthar/benchmarking-llamacpp-on-spacemit-k3-risc-v-ai-cores-vs-standard-rvv-part-4-10mc)),
  TinyLlama Q4_0 tg is 9.2 t/s at 1 thread and **plateaus at ~27.8 t/s from 4 to 8 threads** (memory-bound), while
  pp keeps scaling (59 -> 111 t/s). That article's "standard RVV" baseline (0.3 t/s) looks like a broken build, so
  I do not use it as an RVV-vs-IME ratio (Judgement).
* **ONNX Runtime (Fact, via commit pages, merge state not confirmed):** RVV SGEMM + softmax (PR #28261, 3.2-3.6x),
  RVV QNBitGemm / MatMulNBits (PR #29537, tested at VLEN 256), RVV INT8 GEMM/GEMV with M = 1 routing (PR #28308,
  verified on SpacemiT K3).
* **XNNPACK (Fact):** RVV F32 GEMM/IGEMM (7 x m4 kernel landed via PR #7035), SiFive-contributed FP kernels
  ([SiFive blog, Dec 2024](https://www.sifive.com/blog/sifive-accelerates-risc-v-vector-integration-in-xnnpack-for-optimized-ai-inference)),
  qs8 GEMM/IGEMM RVV PR #7639 (state not confirmed).
* **Compilers (Fact):** LLVM has intrinsics / MC for Zvfbfmin, Zvfbfwma, Zvfh, experimental Zvdot4a8i (renamed from
  Zvqdotq), experimental Zvfofp8min, SpacemiT `xsmtvdot`, SiFive Xsfvcp (VCIX) with an MLIR VCIX dialect.
  Our clang 23.1.5 should be checked for each name before use (not done here).

---

## 2. Comparison with Intel AMX, Apple AMX / M4 SME and Arm SME / SME2

| | Intel AMX (SPR/EMR/GNR) | Apple AMX (M1-M3, undocumented) | Apple M4 SME | Arm SME / SME2 (e.g. C1-Ultra cluster) | RISC-V IME | RISC-V VME / AME |
|---|---|---|---|---|---|---|
| State | 8 tiles x 16 rows x 64 B = **8 KiB** + 64 B TILECFG | X, Y operand regs + Z accumulator grid in a per-cluster coprocessor | **ZA = (SVL/8)^2 B = 4 KiB at SVL 512** (+ ZT0 512 b on SME2) | ZA, ZT0 | vector registers (no new state) | VME: 4 accumulator tiles; AME: M and A register files |
| Product | dot product (TDPBSSD, TDPBF16PS, TDPFP16PS) | outer product (32 x 32 16-bit grid) | outer product (FMOPA / SMOPA / BFMOPA) | outer product, plus multi-vector dot ops (SME2) | dot/outer hybrid via lambda | VME outer product; AME fat inner product |
| Mode | always available after OS permission | coprocessor set/clr | **streaming SVE mode** (SMSTART/SMSTOP); regular SVE / NEON throughput drops inside | streaming mode; unit shared per cluster | normal vector mode | normal vector mode (VME) / separate (AME) |
| Peak per core per clock | **1,024 int8 MAC, 512 BF16 MAC** (2,048 / 1,024 ops) | not documented | Measured (single P-core, shared unit, ~3.9 GHz): **FP32 512 FLOP/clk (256 MAC), BF16/FP16->FP32 512 FLOP/clk, int8->int32 1,024 op/clk (512 MAC)** | C1 cluster: one SME2 unit shared by the cluster (size of a C1-Pro core); no per-clock figure found | implementation choice | implementation choice |
| Context switch | XSAVE component 18; Linux traps first use, needs `arch_prctl(ARCH_REQ_XCOMP_PERM)`, then saves 8 KiB per switch; signal frames grow | — | ZA saved per thread when PSTATE.ZA = 1; signal frames grow; kernel docs urge enabling ZA only while used | as M4 | nothing new (vector state already saved) | new state and `mstatus.MS` dirty tracking |

Sources: [Intel peak footnote via Wikipedia and Intel material](https://en.wikipedia.org/wiki/Advanced_Matrix_Extensions)
("2048 int8 operations per cycle ... 1024 bfloat16 operations per cycle" per core);
[Linux xstate doc](https://docs.kernel.org/arch/x86/xstate.html); [corsix/amx](https://github.com/corsix/amx);
[M4 SME outer-product measurements](https://github.com/tzakharko/m4-sme-exploration) (reports 01 and 02: FP32
~2,000 GFLOPS on one P-core with 4 accumulators, int8 ~4,000 GOPS, FP64 ~500; SVL 512, ZA 4 KiB, one SME block per
cluster shared by 4 P-cores, SVE FMLA in streaming mode only ~31 GFLOPS);
[Hello SME!, arXiv 2409.18779](https://arxiv.org/pdf/2409.18779) (~2,009 FP32 GFLOPS, 4-cycle FMOPA latency);
[Linux arm64 SME doc](https://docs.kernel.org/arch/arm64/sme.html);
[Arm C1 shared SME2 unit (Monoist)](https://monoist.itmedia.co.jp/mn/articles/2510/06/news030_3.html).

**Design choices (Judgement, grounded in the above).**
* **Separate tile state vs. vector registers.** Separate tiles (AMX, SME ZA, VME, AME) let a big array keep its
  accumulators local, so operand bandwidth is only A and B. The price is new state (4-8 KiB per thread), OS
  enablement and save/restore, and on Arm a separate streaming mode where ordinary vector code runs slowly (M4:
  31 GFLOPS SVE vs 2 TFLOPS ZA). Vector-register designs (IME, SpacemiT, Semidynamics, XM sourcing) need no OS work
  but put the accumulator in the vector register file, so the register file ports set the size of the array.
* **Outer vs. dot product.** For a register-to-register instruction with operands of V bits each, a full outer
  product yields (V/w)^2 MACs, a K-deep fat inner product (V/w)^2 / K, and a plain dot product V/w. Outer
  products need the biggest accumulator (that is why they live in tiles); IME's lambda trades accumulator size for
  operand reuse.
* **Peak is not the LLM limit.** In decode every weight byte is used once per token, so throughput is bandwidth /
  bytes-per-token. llama.cpp on K3 plateaus at 4 threads in tg while pp scales (Fact above); Intel and Apple matrix
  units mostly speed up prefill and batched serving. The laptop measurement below shows one X925 core pulling
  8-9 B/clk from DRAM, which a 96 MAC/clk SDOT unit already saturates 10x over.

---

## 3. Fit to our core

### 3.1 What the core has (Facts from the repository)

* Vector plan (BOARD 23:42, DEVLOG 00:20 and 01:36): VLEN and DLEN parameters, first build **VLEN = DLEN = 256**;
  **VP0 / VP1 = FMA + full integer class** (incl. vector-scalar moves), **VP2 = ALU, permute, reductions**, a second
  permute on VP1; VRF 8 banks x 2R + 4W, 96 physical 256-bit registers (24 Kbit). Peak FP32 FMA = 2 x DLEN / 32 = 16 per
  clock. Step 1 (hand-off v1, 01:30) runs vector instructions in order at the ROB head and is "slow by design".
* RVV contract (`build/cpu/fp/RVV-CONTRACT.md`): Zve64f-level subset; **widening / narrowing, fixed point and FP64
  vectors are out of scope**; integer, mask, permute and indexed are illegal in step 1. `mstatus` does not exist;
  vector state behaves as VS = Dirty.
* SoC memory (architecture.md section 3, 7-Zip targets page): 64-bit beats (`mem_rdata[63:0]`), L1 D lines are
  **8 B beats**, at most one split-read answer per clock, `N_MISS` 1-8 (deciding config 4), L2 tags-only 4 MiB /
  8-way / 64 B / 20 clocks, `MEM_LAT` 350, `MEM_GAP` 8 (one DRAM line start per 8 clocks), and a data prefetcher only
  as a parked default-off candidate (DEVLOG 21:25).

### 3.2 Compute per clock (Judgement; per core, peak, all operands in registers)

Assumptions: "beats" as in the BOARD model (`ceil(vl x SEW_dest / DLEN)`); integer MAC on VP0 and VP1, VP2 also
able to issue dot products only where stated; BF16 FMA reuses the FP32 FMA lanes (one BF16 product per FP32 lane).

| Option | Instruction | int8 MAC/clk, DLEN 256 (2 pipes / 3 pipes) | at DLEN 512 (2 / 3) | BF16 MAC/clk, DLEN 256 / 512 | FP32 MAC/clk 256 / 512 |
|---|---|---|---|---|---|
| A0 RVV base | `vwmacc.vv` e8->e16 (16 lanes per beat), periodic `vwadd` to e32 | ~32 / 48 | ~64 / 96 | n/a | 16 / 32 |
| A1 + Zvfbfwma | `vfwmaccbf16` (8 FP32 lanes per beat) | — | — | **16** / 32 | 16 / 32 |
| A2 + Zvdot4a8i | `vdot4a.vv` (8 x 4 MACs per beat) | **64 / 96** | 128 / 192 | — | — |
| B IME-style, lambda = 2 shape (= SpacemiT vmadot) | 4x8 x 8x4 -> 4x4 int32 (C in 2 regs): 128 MAC per instruction at VLEN 256 | one array on VP0: **128**; on VP0+VP1: 256 | VLEN 512: 512 MAC per instruction (C 4 regs) | BF16 W = 2: 64 per instruction -> 64 / 128 | (FP32 lambda shapes: 16-32) |
| B IME lambda = 1 | 8x8x4 = 256 MAC per instruction, C = 8 regs | 256 per array, but needs an accumulator-stationary datapath | 1,024 per instruction | 128 | — |
| C AME / VME tile engine | own tiles, e.g. 8x8x4 or 16x16x4 array | 256 to 1,024 | same (independent of VLEN) | 128 to 512 | 64 to 256 |
| D custom (VCIX-like) | whatever unit is attached; reads 2-3 vector registers per op | as B or C | | | |
| *Laptop, one X925 core (measured)* | SDOT / SMMLA / BFMMLA / FMLA | *96 / 192 peak; 103 sustained on 64^3 (SMMLA)* | | *64-96 peak BFMMLA; 53 sustained* | *24 peak; 19.6 sustained* |
| *Intel AMX / M4 SME (Fact)* | | *1,024 / 512 MAC* | | *512 / 256 MAC* | *— / 256 MAC* |

### 3.3 Register-file ports and bandwidth (Judgement)

| Instruction | Reads x 256 b | Writes x 256 b | MACs | MACs per register bit read |
|---|---|---|---|---|
| `vfmacc` / `vdot4a` (one beat) | 3 (vs1, vs2, vd) | 1 | 8 FP32 / 32 int8 | 0.04 int8 |
| `vwmacc` e8->e16 (2 beats) | 1 + 1 + 2 | 2 | 32 | 0.03 |
| IME lambda 2 / vmadot (one instruction) | 2 + **2** (C) | **2** | 128 | **0.125** |
| IME lambda 1 | 2 + **8** | **8** | 256 | 0.10, or 0.5 if C stays in the array |
| AME / VME tile op | 2 (or none: tiles loaded from L1) | 0 to the VRF | 256-1,024 | n/a: separate tile storage |

* The planned VRF (8 banks x 2R + 4W) feeds today's 3 pipes with 3 reads each. A vmadot-shaped IME pipe at one
  instruction per clock needs 4R + 2W, i.e. it replaces one FMA pipe's port budget plus one extra write; two of them
  would need 8R + 4W, the whole VRF. Lambda 1 is only practical if the accumulator is kept in the array across a
  chain of instructions with the same `vd` and written back on a chain break (a hidden-tile microarchitecture with
  precise-trap obligations).
* Memory feed for prefill: 128 int8 MAC/clk on a 4x8 x 8x4 tile needs 64 B of A and B per instruction if nothing is
  reused across instructions; with register blocking (e.g. 4 A tiles x 4 B tiles = 16 instructions per 8 loads)
  about 32 B/clk from L1, which is 4 beats per clock: more than the current 8 B beat L1 port model
  (BOARD: unit-stride is "up to DLEN / 64 beats per clock through one load port" = 4 at DLEN 256). Feasible but at
  the limit.

### 3.4 FPGA cost, orders of magnitude (Judgement)

Assumptions: AMD UltraScale+ (the repo's candidate XCKU5P: about 217K LUT6, 1,824 DSP48E2); an int8 MAC packs two per
DSP48E2 when one operand is shared, or costs ~50-80 LUT6 in fabric with its adder-tree share; a BF16 multiply with
FP32 accumulate ~250-400 LUT + 1 DSP; FP32 FMA 706 LUT + 2 DSP (AMD's Kintex-7 table quoted in
`fpga-resource-and-board-analysis.md`). Not synthesised; useful only to rank options.

| Option | Datapath added | LUT6 (fabric) | DSP48E2 | RAM |
|---|---|---|---|---|
| A0 widening | reuse integer multipliers, widening muxes | 1-3K | 0 | 0 |
| A1 Zvfbfwma | BF16 operand unpack into the existing 16 FP32 FMA lanes | 1-2K | 0 | 0 |
| A2 Zvdot4a8i on 2 pipes | 64 int8 multipliers + 4:1 adder trees | 4-6K (or 32 DSP) | 0-32 | 0 |
| B one vmadot-shaped array (128 int8 MAC; BF16 at 64) | multipliers, 8-input adder trees, C forwarding | 10-20K (int8 only) to 30-45K with BF16 | 64-128 | 0 |
| C tile engine, 256-1,024 MAC + 4-8 KiB tiles + own L1 port | array, tile RF with wide ports, loader | 30-100K | 128-512 | 2-8 BRAM36 or LUTRAM |
| D custom via VCIX-like port | the unit itself + 1-2K interface | unit + 1-2K | unit | unit |

### 3.5 Contract, versioning and privilege (Judgement against AGENTS.md and architecture.md section 9)

| Option | Contract change | MINOR steps | New privilege state |
|---|---|---|---|
| A0 widening | RVV-CONTRACT section 5/8: widening and narrowing integer and FP ops | 1 (needed for V and Zvfhmin anyway) | none |
| A1 BF16 | Zfbfmin (scalar converts) + Zvfbfmin + Zvfbfwma, ratified | 1 | none |
| A2 Zvdot4a8i | OP-V encodings of a **draft** (v0.7); option define, draft version recorded in the ISA string text; any later spec change of encodings is a new MINOR (or MAJOR if the option's meaning changes) | 1 | none |
| B IME | new `vtype` fields (lambda, altfmt_A/B, bs) only via `vsetvl`; trace format for vtype grows; accumulation mode fixed (psm = 0, or our algorithm published in the golden model) | 2+ (vtype + first int8 op; BF16 op; tile loads) | none beyond vtype (already saved with V state) |
| C AME / VME | new register file, CSRs (`mtype` or Ad/Md), `mstatus.MS` Off/Initial/Clean/Dirty, trap on use when Off | 3+, **after C1** (M-mode CSRs and `mstatus`, which the core does not have) | yes: MS field, context save of 4-8 KiB+, lazy enable |
| D VCIX-like | vendor custom opcode space; contract must say non-standard, unaffecting RVA23 | 1 | none (if no unit state) / like C (if stateful) |

### 3.6 Time to useful results (Judgement)

* All options wait for the vector performance PATCHes 2-4 (renamed VRF, IQ issue, chaining, vector LSU): step 1
  serialises vector instructions at the ROB head, so no matmul number measured on it means anything.
* A0 + A1 + A2: about one MINOR each on top of that; the golden models (`reference_fp.py`, `rv_iss_fp.c`) need the
  ops; the 24 + 27,000-program golden-model method already exists. Useful prefill numbers in a few steps.
* B: needs A's widening and the `mm` benchmark first, then golden-model support for a draft with moving bit
  positions; one array plus forwarding in RTL. Several more steps.
* C: privilege stage C1 first, then a new LSU path and tile file: the longest path.
* D: the fastest RTL demo (an RTL block behind custom opcodes), but no standard toolchain or RVA23 value, and the
  council's golden models would carry a non-standard op forever.

### 3.7 The decode memory wall (Judgement, computed from the SoC model)

Bytes read per decoded token are about the weight bytes: Llama-3.2-1B-class (1.24 B parameters with the tied
128K-entry embedding read as the LM head): ~1.24 GB at int8, ~0.70 GB at 4.5-bit Q4_0; Llama-3.1-8B-class:
~8.0 GB at int8, ~4.5 GB at Q4_0. KV-cache reads are small at short context and ignored. Clock 4 GHz.

| Memory regime | B/clk | GB/s at 4 GHz | 1B int8 tok/s | 1B Q4_0 | 8B int8 | 8B Q4_0 | int8 MAC/clk needed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Deciding config today (N_MISS 4, 8 B L1 lines, no prefetch): ~4 beats in flight inside one 64 B line, ~350 + 20 clocks per line | ~0.17 | ~0.7 | **~0.55** | ~1.0 | ~0.09 | ~0.15 | 0.2 |
| Same, N_MISS 8 (all 8 beats of a line in flight, still one line) | ~0.18 | ~0.7 | ~0.6 | ~1.0 | ~0.09 | ~0.16 | 0.2 |
| Line-granular stream prefetch with 44+ lines in flight (bandwidth-delay 8 B/clk x 350 clk = 2.8 KB) | 8 | 32 | **~26** | ~46 | ~4.0 | ~7.1 | 8 (int8) / 16 (+unpack) |
| SoC ceiling (64-bit beat, one answer per clock, MEM_GAP 8) | 8 | 32 | ~26 | ~46 | ~4.0 | ~7.1 | 8 / 16 |
| Laptop, one X925 core, DRAM GEMV (Measured, section 6) | 8.0-9.0 | 31-35 | ~25-28 | ~45-50 | ~4 | ~7 | |
| Laptop + 50% (illustration only, not a goal) | 12-13.5 | 48-54 | | | | | needs a 128-bit beat or MEM_GAP <= 5 |

* **Where a matrix engine helps:** prefill (T prompt tokens share each weight read, so arithmetic intensity is about
  T MACs per weight byte and the 64-256 MAC/clk compute is the limit) and batched decode (B sequences). At 4 GHz a
  1B model needs ~1 GMAC per prompt token: Option A2 (64 MAC/clk) ~260 tok/s peak prefill, Option B with one array
  (128) ~520, two arrays (256) ~1,000, before efficiency losses (the laptop reaches 54% of its SMMLA peak on a
  64^3 tile).
* **Where it does not:** batch-1 decode. Even at the ceiling, decode needs 8-16 int8 MACs per clock; A0 already has
  32. The decode levers are memory-level parallelism (line-sized misses, an L2 stream prefetcher, more `N_MISS`),
  bus width (128-bit beats) and weight compression (int4 halves bytes; ternary at ~1.6-2 bits would cut them
  further, see the BitNet report). With int4 and ternary the unpack ALU work, not the MAC count, sets the vector
  pipe load; that argues for integer ALU on every pipe (already decided at 01:36).

---

## 4. A benchmark to optimise against: the `mm` suite (proposal)

Shape it like the `rt` and `lzma` ports: `build_bench.py --benchmark mm` with sources `sim/cpu/bench/mm_bench.c`
(driver, markers, checksums), `mm_kernels_scalar.c`, `mm_kernels_rvv.c` (intrinsics, compiled only with `--vector`),
`mm_kernels_ime.c` (later, behind its option), `mm_runtime.c`; a host generator writes `mm_data.c` / a RAM blob
(as `rt_data.c` is built on the host), so the simulator spends no instructions making 8 MiB of weights; `mm_run.py`
drives phases like `rt_run.py`; `mm_native.c` is the laptop reference (section 6 prototype). Each phase between
start / stop markers; `run_bench.py --benchmark mm --mm-variant scalar|rvv|rvv-dot|ime --vector --vlen N` plus the
usual memory knobs; results and the rubric go to `devlog/devlog-<commit>.md` with `--devlog`.

**Data and checks.** xorshift32 from fixed seeds (as the prototype): int8 uniform; BF16 with random sign, exponent
2^-8..2^7 and 7-bit fraction (so accumulation order shows in the bits; the first prototype run used k/128 values,
where every order was exact, and could not tell orders apart); FP32 16-bit fractions. Checksums FNV-1a 64 over the
output buffer. Integer results must be **bit-exact** in every variant. FP "ordered" variants keep, per output,
ascending k with one FMA per product from +0 (the BF16-P0 `dot_fma` order of `implementation-contract.md`), which
a vector kernel keeps by vectorising across outputs; they must be **bit-exact** with the scalar reference. Matrix /
tree variants (IME with psm = 1, BFMMLA-like, `vfredusum`) are checked by max relative error against the ordered
reference, with a tolerance fixed in advance (proposal: <= 2^-10 relative for BF16-input, <= 2^-20 for FP32 at
K <= 2048; never loosened after a failure). The laptop measured 8.4e-5 max relative error for BFMMLA on G2.

**Cases (instruction estimates are mine, for VLEN 256, to size simulation; Verilator full mode ran rt's 10.2M
instructions in 172 s on this laptop, so the RVV and IME variants stay well under a minute each).**

| ID | Kernel | Shape | MACs | Weight bytes | Scalar instr | RVV instr | IME instr |
|---|---|---|---:|---:|---:|---:|---:|
| G1 | int8 x int8 -> int32 GEMM | 64x64x64 | 262,144 | 4 KiB | ~1.0M | ~25K (`vdot4a`), ~50K (`vwmacc`) | ~6K (2,048 x 128-MAC + loads) |
| G2 | BF16 -> FP32 GEMM | 64x64x64 | 262,144 | 8 KiB | ~1.3M | ~35K (`vfwmaccbf16`) | ~10K |
| G3 | FP32 GEMM, ordered | 64x64x64 | 262,144 | 16 KiB | ~1.0M | ~35K (`vfmacc.vf`, bit-exact) | — |
| V1 | int8 GEMV (1B decode Q/O projection) | 2048 x 2048 | 4.19M | 4 MiB | ~13M (run 256 rows: ~1.6M) | ~0.4M | ~0.4M (GEMV does not use a tile) |
| V1b | int8 GEMV, larger than the 4 MiB L2 (memory wall) | 4096 x 2048 | 8.39M | 8 MiB | — | ~0.8M | — |
| V2 | BF16 GEMV | 2048 x 2048 | 4.19M | 8 MiB | ~16M (256 rows) | ~0.6M | — |
| V3 | int4 (Q4_0-like, blocks of 32, FP16 scale) GEMV | 2048 x 2048 | 4.19M | 2.25 MiB | ~20M (256 rows) | ~0.8M (unpack + `vdot4a`) | — |
| V4 | FP32 GEMV | 1024 x 1024 | 1.05M | 4 MiB | ~3.5M | ~0.15M | — |
| T1 | One transformer block: d 256, 4 heads x 64 (2 KV heads), SwiGLU FFN 768, RMSNorm, RoPE, softmax (fixed polynomial exp), int8 weights with per-row FP32 scale, prefill 16 tokens then 1 decode token | | prefill 12.6M, decode 0.79M | 0.79 MB | decode only (~3M); prefill native only | ~1.5M | ~0.6M |

Reported metrics: clocks per case, MAC/clk, weight B/clk for GEMV, and derived "1B int8 decode tok/s at 4 GHz" =
4e9 x B/clk / 1.24e9 (labelled as derived). Run at flat memory and at the deciding configuration (`--warm-l2` off
for V1b, since streaming is the point).

**Laptop reference (aarch64 WSL).** `mm_native.c` built with Ubuntu clang 18.1.3 `-O2
-march=armv9.2-a+sve2+i8mm+bf16 -fno-vectorize -fno-slp-vectorize`, pinned (`taskset -c 19`), PMU cycles via
`perf_event_open` (as `build/rt-bench/bench_common.h`), median of 7 trials, at least 5 runs. Variants: generic C,
NEON SDOT, I8MM SMMLA, BF16 BFMMLA / BFDOT, NEON FMA (ordered). **Facts measured here:** the laptop is an NVIDIA
RTX Spark N1X (`lscpu`: Cortex-X925 MIDR 0x410fd851 and Cortex-A725), HWCAP2 reports **no SME / SME2**, and SVE's
vector length is **128 bits**, so SVE adds no width over NEON and there is no SME reference to take. Runs must be
dropped when the peak probe shows ~2 instructions per clock instead of ~6: 2 of 9 runs did, which looks like the
vCPU landing on a smaller physical core or being migrated (Judgement; not proven). The laptop + 50% per-clock
figures would follow the usual rule, but **no goal is set here**; note that a DRAM-bound V1b goal at +50% exceeds
the SoC's 8 B/clk bus ceiling.

---

## 5. Recommendation and plan (Judgement)

**Option A now, a small Option B later, C and D not now.** A uses ratified or fast-track extensions, adds no
state, fits the 3-pipe plan and VRF, and is on the RVA23 path (widening is mandatory V; Zvfhmin needs it). B is the
only route to laptop-class prefill per clock (~2x A2) without new privilege state, and its vmadot shape fits the
VRF ports. C needs `mstatus` and a tile file the core does not have, for a gain that decode cannot use. D buys a
quick demo at the cost of a permanent non-standard op.

Ordered steps, each its own version with regression at both cache sizes, logged benchmark numbers, history row,
tag and DEVLOG entries (AGENTS.md):

1. **Bench only (no version bump):** add the `mm` suite with scalar and FP32-RVV variants and the native
   reference; log laptop numbers at 5+ runs. Gives baselines before any ISA change.
2. **Prerequisite (SIMD plan):** vector performance PATCHes 2-4 and the integer / mask / permute MINORs, so vector
   numbers mean something.
3. **MINOR: RVV widening and narrowing** (integer `vwmul*`, `vwmacc*`, `vwadd*`, `vnsrl/vnsra`, `vnclip*` with
   fixed point if it lands together; FP `vfwmacc*`, `vfwcvt`, `vfncvt`). Golden models first.
4. **MINOR: BF16** — Zfbfmin + Zvfbfmin + Zvfbfwma (ratified). G2 / V2 measured.
5. **MINOR (option): Zvdot4a8i v0.7, draft-tracking**, behind its own define, the draft version stated in the
   contract; re-check the spec at each release. G1 / V1 / V3 / T1 measured.
6. **Microarchitecture PATCHes:** dot/MAC on VP2 too if the model says so; L1 line fill / L2 stream prefetch for
   V1b (memory engineer); these move decode far more than any matrix unit.
7. **MINOR (option), only if prefill is the stated goal:** an IME subset (`vtype.lambda`, int8 -> int32 at the
   lambda-2 shape, psm = 0), then BF16, then tile loads, tracking the IME draft; or SpacemiT IME encodings if the
   council prefers shipping-silicon compatibility with llama.cpp's backend (vendor, non-standard).
8. **Later:** VME / AME after stage C1 and after either spec freezes.

**Extensions to add first:** widening (V), Zvfbfmin / Zvfbfwma, Zvdot4a8i; Zvfh when FP16 models matter. No tile
state before C1.

**Risks.** (1) Draft churn: Zvqdotq was renamed in 2026, IME bit positions and AME data types are still moving
(the AME data-type vote was recalled in Dec 2025). (2) Decode is set by memory, not compute: without line-granular
misses and prefetch, 1B int8 decode stays near 0.5 tok/s whatever is added. (3) FP determinism: implementation-
defined reductions (IME psm = 1, VME/Zvdota RVBNA) need the golden model to carry our exact algorithm, or traces
diverge. (4) VRF ports and FPGA area: an IME array consumes a pipe's port budget; BF16 arrays are LUT-heavy.
(5) Not RVA23: none of the matrix extensions is in RVA23; time spent there does not close the profile gap.
(6) Simulation cost: a scalar 2048 x 2048 GEMV is ~13M instructions, so scalar variants run reduced rows.

---

## 6. Experiments run (for DEVLOG)

All in WSL Ubuntu 24.04.5, kernel 6.18.33.2-microsoft-standard-WSL2, aarch64, Ubuntu clang 18.1.3; repo HEAD
`c607485`, uncommitted; files in `build/research/matrix/` (`probe.c` sha256 cc44bde9f81bdce2..., `mm_bench.c`
ac033759d96042bb..., logs in `logs/`). Clock reads: add-chain estimate 3.83-3.96 GHz; PMU cycles used.

| Time | Goal | Command | Result | Conclusion |
|---|---|---|---|---|
| 01:37 | Identify the laptop's cores and features | `wsl -e bash -c 'lscpu; grep Features /proc/cpuinfo; ...'` | NVIDIA RTX Spark N1X, Cortex-X925 (0xd85) and Cortex-A725 (0xd87), 20 vCPUs; flags include asimddp, i8mm, bf16, sve2, svei8mm, svebf16; **no sme** | No SME on this laptop |
| 01:45:55 | Build prototypes | `clang -O2 -march=armv9.2-a+sve2+i8mm+bf16 -fno-vectorize -fno-slp-vectorize mm_bench.c` | **failed**: `sched_getcpu` undeclared (needs `_GNU_SOURCE`) | fixed with `-D_GNU_SOURCE` |
| 01:46:04 | Feature probe | `taskset -c {0,6,19} bin/probe` | HWCAP2 0x1873f7: SME no, SME2 no; SVE VL 128 bits on all three | SVE gives no width over NEON |
| 01:46:10-13 | First matrix reference, 3 runs, CPU 19 | `timeout 100 taskset -c 19 bin/mm_bench` (x3), `logs/run-20261122-014610.jsonl` | Peaks varied: run 1 at ~2 instr/clk for every op, runs 2-3 at ~6; BF16 data k/128 made BFMMLA bit-exact (data not order-sensitive) | Discard run 1; change BF16 data |
| 01:46:36-40 | Matrix reference, 6 runs (4 on CPU 19, 2 on CPU 0), order-sensitive BF16 data | same, `logs/run-20261122-014636.jsonl` | Peaks (X925, 5 of 6 runs): SDOT 5.9-6.0 instr/clk (**95 int8 MAC/clk**), SMMLA 6.0 (**192**), FMLA.4S 6.0 (**24 FP32 MAC/clk**), BFMMLA 4.0 (64; 6.0 = 96 in 1 run), BFDOT 6.0 (48); run 4 again ~2/clk. Kernels (median run): G1 int8 64^3 scalar 0.84-0.94, SDOT 72.9, **SMMLA 102.8 MAC/clk**, all exact; G3 FP32 ordered scalar 0.90, NEON 19.6 MAC/clk, bit-exact; G2 BF16 scalar 0.50, NEON widen+FMA ordered 11.8 (bit-exact), BFMMLA **52.8 MAC/clk, not bit-exact, max rel. err 8.4e-5**; V1 int8 GEMV 2048^2 scalar 0.89, SDOT 23.1 MAC/clk = 23 B/clk; BF16 GEMV 2048^2 BFDOT 9.5 MAC/clk (19 B/clk); FP32 GEMV 2048^2 3.5 MAC/clk (14 B/clk); **int8 GEMV 8192^2 (64 MiB, DRAM) 8.1-9.0 B/clk = 31-35 GB/s**; BF16 GEMV 8192^2 7.0-8.0 B/clk. Checksums (FNV-1a 64): G1 3b5e33fd811ed06e, G3 67523f59da3b02f7, G2 28bec3dac8df6b5e, V1 e3133618cd6f169f, 8192^2 int8 13b9cef325cac69f | One X925 core streams 8-9 B/clk from DRAM, about our SoC's 8 B/clk ceiling; SMMLA sustains 54% of its peak on a 64^3 tile; ~2 of 9 runs ran at a third of the peak (likely vCPU placement), so the reference needs a peak-probe filter |
