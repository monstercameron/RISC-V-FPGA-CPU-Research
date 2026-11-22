# Qwen3.8-27B operations mapped to RVA23 instructions and assembly

Research date: October 23, 2026. This is a companion mapping for the project's pinned model and BF16-P0 policy, not a replacement architecture or a declaration of ISA/numerical compliance. Model shapes come from the [dimension ledger](dimension-ledger.md); arithmetic order and casts come from the [implementation contract](implementation-contract.md). That contract, the [ABI](abi-v1.md) and the [adapter](adapter-v1.md) remain normative.

**The main mapping is BF16 storage -> FP32 arithmetic -> explicit BF16 boundaries, with vector lanes assigned to independent outputs.** RVA23 has no single attention, GEMM, softmax, SiLU or DeltaNet instruction. Those operations become instruction sequences. Native BF16 widening multiply-accumulate can shorten the dominant sequence, when its optional extension is present.

Five assembly files and a reproducible encoding checker are in [isa/](../../isa/README.md). All five assembled with LLVM 23.1.3, and 23 instruction encodings were checked. They have not executed on a RISC-V simulator or FPGA. Nonlinear kernels, the full runtime and numerical qualification remain work to implement.

## 1. What RVA23 provides

RVA23 is an application-processor **profile** specifying required extensions and behavior. It is not an opcode namespace. Use RVA23U64 for this user-level mapping; a Linux-capable platform also has supervisor/platform requirements. Implementing the few instructions below does not make a small FPGA core RVA23 compliant. [RVA23 profile specification](https://github.com/riscv/riscv-profiles/blob/main/src/rva23-profile.adoc).

| Relevant capability | Profile status | Use in this model |
|---|---|---|
| RV64I, M, F, D; integer/FP register and memory operations | Required | Addresses, indexing, checked dimensions, FP32 arithmetic; FP64 available but not substituted into BF16-P0 |
| V | Required | Vector FP32 arithmetic, loads/stores, permutations and reductions |
| Zfhmin, Zvfhmin | Required | Minimal IEEE FP16 support; **FP16 is not BF16** |
| Zfa, bit manipulation and related profile facilities | Required | Additional supporting operations; no transformer or transcendental instruction implied |
| Zic64b, Zicbom, Zicbop, Zicboz | Required | 64-byte cache-block property, cache management, prefetch and zeroing under platform rules |
| Zfbfmin | Optional expansion | `fcvt.s.bf16`, `fcvt.bf16.s` and BF16 interchange support |
| Zvfbfmin | Optional expansion | `vfwcvtbf16.f.f.v`, `vfncvtbf16.f.f.w` |
| Zvfbfwma | Optional expansion | `vfwmaccbf16.vv` / `.vf`: BF16 operands, FP32 accumulator; depends on both BF16 conversion extensions |
| Matrix/tensor, exp/log/sin/cos/tanh/erf, quantized dot-product extras | No such instruction guaranteed by RVA23 | Software kernels, existing accelerator datapaths, or separately specified extensions |

This is the subset relevant to the mapping, not the complete compliance checklist. Probe optional capabilities before selecting an optimized binary. The compiler's `-march` does not discover runtime hardware. [Scalar BF16](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/zfbfmin.adoc), [vector conversions](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/zvfbfmin.adoc), [widening accumulation](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/zvfbfwma.adoc).

The full V extension provides VLEN >=128 bits and the FP32/FP64 operations needed here. VLEN is register capacity, not a promise of that many physical arithmetic lanes or one-cycle execution. Use `vsetvli` and its returned VL; never assume a particular vector length. [V requirements](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/v-st-ext.adoc).

## 2. Primitive lowering dictionary

Here **R16** means the contract's BF16 RNE boundary, **F32** means exact widening, and **P0** means the ordered BF16-P0 policy. Scalar instructions have `.s` because accumulation is binary32. Vector element types are selected through `vtype`; their mnemonics do not carry `.s`.

| Primitive | Required-instruction implementation | Optional BF16 route / constraint |
|---|---|---|
| Read BF16 and widen | `lhu; slli ...,16; fmv.w.x` | `flh; fcvt.s.bf16`; bit moves alone do not implement conversion exception policy |
| Vector BF16 widening | At e32/m2: `vle16.v; vzext.vf2; vsll.vi ...,16` | At e16/m1: `vfwcvtbf16.f.f.v` produces FP32/m2 |
| FP32 -> BF16 | Software bit classification, RNE rounding, packing, flag handling | `fcvt.bf16.s ...,rne`; vector `vfncvtbf16.f.f.w` at SEW16 with FP32 source |
| FP32 element add/subtract/multiply | `fadd.s`, `fsub.s`, `fmul.s`; `vfadd`, `vfsub`, `vfmul` in `.vv`/`.vf` forms | Widen BF16 inputs first; narrow at each required graph boundary |
| Ordered FMA dot | Loop over `fmadd.s acc,x,w,acc,rne` | `vfmacc.vf` across output rows; or `vfwmaccbf16.vf` with BF16 inputs |
| Ordered separate dot | Loop `fmul.s` then `fadd.s` | `vfmul` then ordered sum; **do not contract into FMA** |
| Reciprocal / reciprocal sqrt | `fdiv.s one,x`; `fsqrt.s` then `fdiv.s one,sqrt` | `vfdiv` / `vfsqrt.v`; `vfrec7.v` / `vfrsqrt7.v` are approximations, not drop-in P0 replacements |
| Sum / mean | Ascending `fadd.s`; divide sum by count | `vfredosum.vs` can preserve ordered additions with correct seed/chunks; avoid unordered `vfredusum.vs` for P0 |
| Max with first-index tie | Ordered compare `flt.s`, update only on strict greater; keep index | `vfmax` / `vfredmax` find values, but do not by themselves preserve required index/tie/nonfinite policy |
| exp/log1p/sin/cos/tanh/erf | Function calls to frozen FP32 kernels using arithmetic, comparisons, integer range reduction and constant loads | No RVA23 instruction performs these functions |
| Abs/negate/compare | `fsgnjx.s`/`fsgnjn.s` (aliases `fabs.s`/`fneg.s`), `flt.s`, `feq.s`, `fclass.s` | Vector sign operations, `vmflt`, `vmfeq`, `vfclass.v`, masks/merge |
| Tensor address/shape | `add`, `mul`, `slli`, shifts, branches; explicit overflow/range checks | `vle*`, `vse*`, `vlse*`, indexed loads or `vrgather` for suitable layouts |
| Positions -> FP32 phases | Checked signed 64-bit arithmetic then `fcvt.s.l ...,rne`, `fmul.s` | Integer positions stay exact until the contract's FP32 phase boundary |
| Cache/state copy or clear | Integer/vector loads and stores | `cbo.zero` only for permitted whole owned blocks; preserve partial edges |

These are mappings, not permission to alter dtype boundaries or tensor layouts. A scalar sign/bit instruction or vector narrowing step may need a surrounding wrapper to match canonical-NaN and sticky-flag rules. [Scalar encodings](https://github.com/riscv/riscv-opcodes/blob/master/extensions/rv_f), [vector encodings](https://github.com/riscv/riscv-opcodes/blob/master/extensions/rv_v), [vector semantics](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/vector-common.adoc).

## 3. Complete learned-graph mapping

The same small instruction set is reused throughout the graph. Dimensions and ordering below are specific to the pinned checkpoint, not inferred from the model name.

### Text path and shared projections

| LLM operation | Shape / role | Assembly lowering and required boundary |
|---|---|---|
| Token embedding | Select one of 248320 rows of width 5120 | Check token ID; address multiply/add; BF16 vector copy. Embedding and LM head are untied; no matrix multiply for lookup |
| Dense projections | `y[M]=W[M,K]*x[K]`; FFN gate/up M17408,K5120, down M5120,K17408 | Ordered FMA over K, parallel output rows; optional bias `fadd.s`; R16. `gemv_bf16_rvv` / `gemv_bf16_native` show the inner recurrence |
| Text input/post-mixer/final RMSNorm | Width5120, epsilon1e-6 | Square `fmul`, ordered `fadd`, divide by N, add epsilon, sqrt/divide, multiply x, multiply `(1+w)`, R16. Do not use direct w gamma |
| FFN SiLU | 17408 gate values | Stable sigmoid kernel, multiply x, R16; no `silu` instruction |
| SwiGLU product | R16(SiLU(gate)) times BF16 up projection | Widen -> `vfmul.vv` -> R16 -> down projection |
| Residual add | Width5120 at each declared boundary | Widen both -> `vfadd.vv` -> R16; do not retain FP32 across the residual boundary |
| Final LM head | 248320 x5120 | Same ordered GEMV; R16 result; optional exact widening for FP32 logits transport |
| Token selection | Host reads logits; ABI 1 forward output | Host policy outside the learned graph. No generation instruction or on-device generation operation is added |

### Full attention: 16 decoder layers

| Operation | Shape / semantic rule | Assembly lowering |
|---|---|---|
| Q plus gate projection | 12288x5120; 24 heads, each split 512 into Q256/gate256 | GEMV; unpack each head with address/stride operations, not a global half split |
| K/V projection | Each1024x5120: 4 heads x256 | GEMV then BF16 storage |
| Q/K RMSNorm | Width256 | Same ordered RMS recipe with zero-centered `(1+w)` gamma |
| Text partial mRoPE | First 64 of 256; pair first 32/last 32; `[11,11,10]` axis allocation | Checked position/index arithmetic; phase `fmul.s`; sin/cos kernel then R16; two BF16-rounded products and BF16 add. Remaining 192 copied |
| GQA mapping | Query head h uses KV head floor(h/6) | Integer index calculation; no physical repeat of six copies required |
| KV append / cached reads | Separate K/V, layer/head/position offsets | BF16 loads/stores, checked valid lengths and ordered publication. Vector instructions do not implement cache ownership |
| QK score | Ordered dot over D256 | Scalar FMA or vectors across independent key positions; R16 score, multiply frozen scale1/16, R16 again |
| Causal masking | Skip invalid/future positions entirely | Integer bound/mask construction; guarded loads and vector masks. Do not read invalid cache slots then multiply by zero |
| Three-pass softmax | Valid positions in ascending order | Passes for max, exp-sum and probability/AV; fixed EXP32 call; ordered denominator; division then R16 probabilities. Recompute scores with identical casts each pass |
| AV accumulation | 256 coordinates/query head | Vector lanes across output coordinates; iterate valid positions in order with `vfmacc.vf`; R16 |
| Attention gate | 24x256 matching gate values | SIGMOID32 and required product/R16 boundaries; gate is sigmoid, not SiLU |
| Output projection | 5120x6144 | Ordered GEMV. Query width 6144 must not be truncated to hidden width 5120 |

### Gated DeltaNet: 48 decoder layers

| Operation | Shape / semantic rule | Assembly lowering |
|---|---|---|
| QKV, z, a, b projections | Output widths10240,6144,48,48 from5120 | Reuse ordered GEMV and projection casts |
| Depthwise conv | Four taps on10240 channels | Parallel channels, oldest-to-current four `vfmacc` steps; R16, SiLU32, R16. Ring history stores raw projected BF16 values |
| Q/K L2 normalization | 16 heads x128 | Square -> ordered sum -> epsilon -> sqrt/divide -> multiply. **No division by 128**; Q has subsequent stored inverse-root scaling |
| Head expansion | 48 value heads share16 Q/K heads | Value head h maps to floor(h/3); address aliases/views, not unnecessary copies |
| beta | 48 values | `R16(SIGMOID32(b))`, then widen for the recurrence |
| decay | `g=-exp(A_log)*softplus(a+dt_bias)`; decay=exp(g) | Separate FP32 add/mul/negate and frozen EXP32/LOG1P32 kernels; stable softplus formulation |
| Decayed state | Per-head S[128,128] FP32 | `vfmul.vf Sd,Sold,decay` across value coordinates |
| Prediction | pred[v]=sum_k(k[k]*Sd[k,v]) | For each k, `vfmul.vf` temporary then `vfadd.vv` into pred; ascending k. No FMA |
| Delta correction | delta[v]=beta*(v_input[v]-pred[v]) | `vfsub.vv` then `vfmul.vf`; keep FP32 |
| Outer-product state update | Snew[k,v]=Sd[k,v]+k[k]*delta[v] | Separate multiply then add. [Delta row example](../../isa/rvv_ops.S) requires prediction to have finished first |
| Readout | out[v]=sum_k(q_scaled[k]*Snew[k,v]) | Separate multiply/add over ascending k, reading **updated** state; R16 output |
| Gated RMSNorm | Width128 per value head | FP32 RMS -> R16 normalized -> BF16 multiply direct gamma -> FP32 multiply SiLU32(z) -> R16 |
| Output projection | 5120x6144 | Ordered GEMV then graph residual boundary |

The complete recurrent state is 144 MiB FP32; conv history is 3.75 MiB BF16. It is external/on-chip-buffered memory state, not something a vector register file can retain across the whole model. Schedule its reads/writes under the existing [memory plan](memory-plan.md).

### Vision encoder and merger

| Operation | Shape / semantic rule | Assembly lowering |
|---|---|---|
| Patch gathering / Conv3D | 3x2x16x16=1536 inputs ->1152 | Integer gather/reorder; ordered dot per output with bias then R16. Avoid an unbounded full-image im2col buffer |
| Learned positional interpolation | 48x48 table, width 1152 | FP32 coordinate arithmetic, four row gathers; four separately rounded products accumulated in fixed tap order; R16 then BF16 patch add. Branch for grid dimension 1 |
| Vision LayerNorm | Width1152, gamma and beta | Ordered mean; subtract mean; ordered squares/variance; epsilon, sqrt/divide; normalize, gamma multiply, beta add, R16 |
| Vision QKV/out | QKV3456x1152; out1152x1152; 16 heads x72 | Ordered projections with bias; address unpack |
| Vision rotary | Full72, paired halves36;18 frequencies per spatial axis | FP32 phase/sin/cos; separate two multiplies and add, then R16. This differs from text rotary casts |
| Vision attention | Segment-local QK/softmax/AV | Same score recipe and ordered softmax/AV primitives; width 72 and frozen scale; enforce image/temporal segment boundaries |
| Vision block MLP | 27 blocks; FC1 4304x1152, FC2 1152x4304 | Biased projections; **tanh-GELU** kernel with separate FP32 operations then R16 |
| Spatial merger grouping | LayerNorm1152 before 2x2 concatenation ->4608 | Norm kernel then checked gather/copy preserving spatial order |
| Merger MLP | FC1 4608x4608; FC2 5120x4608 | Biased GEMV; **erf-GELU**, not tanh approximation; R16 boundaries |
| Feature insertion / positions | Visual tokens replace validated placeholder runs | Integer indexed copy into decoder input; generate full `[T,4]` signed64 position plan before chunks; preserve committed rope delta |

Host tokenization and pixel preprocessing retain the already approved boundary. The mapping covers on-core learned vision computation, position generation and decoder execution; a software reference on an external CPU does not satisfy that hardware objective.

## 4. Assembly patterns and numerical traps

### Ordered dot product

The callable [scalar example](../../isa/scalar_ops.S) widens BF16 bit patterns with integer shifts and loops over K. Its key step is:

```asm
lhu      t0, 0(a0)                  # BF16 bits
slli     t0, t0, 16
fmv.w.x  ft0, t0                    # exact FP32 representation for finite BF16
fmadd.s  fa0, ft0, ft1, fa0, rne    # one rounded acc + x*w; ft1 already widened
```

For Delta prediction/readout, replace the FMA with **two** instructions:

```asm
fmul.s   ft2, ft0, ft1, rne
fadd.s   fa0, fa0, ft2, rne
```

`(1+2^-23)*(1-2^-23)-1` distinguishes these paths: FMA produces -2^-46; separately rounded multiply/add produces zero. Neither is interchangeable merely because storage is BF16 elsewhere.

### Vectorize outputs, keep K ordered

The baseline [RVV GEMV](../../isa/rvv_ops.S) uses `v12:v13` as FP32 accumulators for independent output rows, initialized once per row block:

```asm
vsetvli   t0, a3, e32, m2, ta, ma
vmv.v.i   v12, 0
# Repeat these operations for increasing k; pointers handled by full example.
vle16.v   v8, (t1)                  # BF16 bits, EMUL1
vzext.vf2 v10, v8                   # unsigned 16 ->32, EMUL2
vsll.vi   v10, v10, 16              # reinterpret as FP32
vfmacc.vf v12, ft0, v10             # ft0 is widened x[k]
```

One lane follows the same serial FMA recurrence as one scalar output. This exposes output parallelism without a partial-sum tree. For U8 prefill, use separate accumulators per token/output while retaining K order and the dependency constraints of the mixer; changing a vector length does not authorize token reordering in DeltaNet.

The [optional kernel](../../isa/bf16_optional.S) uses e16/m1 source groups and a double-width FP32 accumulator:

```asm
vle16.v        v8, (t1)
flh            ft0, 0(t2)           # raw BF16 bits, NaN-boxed in scalar FP reg
vfwmaccbf16.vf v12, ft0, v8         # SEW16; accumulator EEW32 / EMUL2
```

This removes explicit widening from the hot loop. It does **not** reduce the BF16 weight bytes or convert the FPGA into a matrix engine. [BF16 accumulation semantics](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/zvfbfwma.adoc).

### Reductions, nonlinear functions and conversions

`vfredosum.vs` is useful for an ordered sum of already rounded FP32 values. Seed element 0 with the previous scalar accumulator and carry it between ascending chunks; skip masked elements. A vector multiply followed by this reduction implements a separate-product dot, not a serial FMA dot. Do not substitute unordered reduction, a tree, or independently accumulated K tiles for the prescribed recurrence.

RNE narrowing from finite FP32 bits u can be expressed as `((u + 0x7fff + ((u >> 16) & 1)) mod 2^32) >> 16`. That formula alone does not handle NaN classification/canonicalization and IEEE flags. A software BF16 converter must add those cases, overflow/underflow/inexact handling and tests. `fcvt.bf16.s` supplies the optional native operation. The included native helper returns the 16 result bits; it still does not perform command-level exception handling.

Nonlinear calls are unresolved implementation work, not imaginary instructions. Preserve the contract's sign-stable sigmoid, stable softplus and distinct GELU formulas. Freeze their FP32 constants, range reductions, polynomial/table algorithms, operation order and hashes before numerical qualification. Ordinary host `expf` or `tanhf` is not automatically the deterministic kernel identity. Approximate reciprocal/sqrt instructions similarly require a separately reviewed policy if their results differ.

Use explicit RNE scalar operations or save/set/restore `frm` for vectors. Retain accrued `fflags`; handle nonfinite values at the wrapper boundary. ISA flags do not automatically produce the ABI's NONFINITE completion. Preserve subnormals; do not enable fast-math, reassociation, flush-to-zero or unwanted FMA contraction. Tail/mask-agnostic lanes must never later be consumed as valid values.

## 5. Actual opcode families and encoded instructions

A 32-bit RISC-V instruction's low 7 bits are its major opcode. Register numbers, immediate, funct fields and rounding mode make up the rest. One major opcode therefore covers many distinct instructions. Compressed instructions have different lengths; the examples use `.option norvc` for readable fixed 32-bit encodings.

| Major opcode | Family | Relevant uses |
|---|---|---|
| 0x03 / 0x23 | LOAD / STORE | BF16 bit loads, integer metadata, MMIO stores |
| 0x07 / 0x27 | LOAD-FP / STORE-FP, also vector memory | `flw`, `flh`, `vle16.v`, `vse32.v` |
| 0x13 / 0x33 | OP-IMM / OP | Shifts, address operations; `mul` uses OP plus M funct fields |
| 0x53 | OP-FP | FP32 add/mul/div/sqrt, conversions, comparisons, classification |
| 0x43 / 0x47 / 0x4b / 0x4f | FMADD / FMSUB / FNMSUB / FNMADD | Fused scalar operations |
| 0x57 | OP-V | Vector setup/arithmetic/reductions and optional BF16 vector operations |
| 0x63 / 0x6f / 0x67 | BRANCH / JAL / JALR | Loops, calls, returns |
| 0x0f / 0x73 | MISC-MEM / SYSTEM | Fences/cache operations; floating/vector CSR access |
| 0x2f | AMO | Shared control synchronization when used by the runtime; no matrix operation |

`prefetch.r` is an OP-IMM hint encoding, despite relating to caches. Instructions such as `ret`, `li`, `mv`, `csrw` and `fabs.s` may be assembler aliases/pseudoinstructions; their source spelling is not a new major opcode. [Official encoding map](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/rv-32-64g.adoc).

Selected complete words from [opcode_examples.S](../../isa/opcode_examples.S), independently field-checked by [verify_assembly.py](../../isa/verify_assembly.py):

| Assembly | 32-bit word | Major opcode | Requirement |
|---|---|---|---|
| `lhu t0,0(a0)` | 0x00055283 | 0x03 | Base |
| `fadd.s fa0,fa1,fa2,rne` | 0x00c58553 | 0x53 | F |
| `fmul.s fa0,fa1,fa2,rne` | 0x10c58553 | 0x53 | F |
| `fmadd.s fa0,fa1,fa2,fa0,rne` | 0x50c58543 | 0x43 | F |
| `fsqrt.s fa0,fa1,rne` | 0x58058553 | 0x53 | F |
| `vsetvli t0,a0,e32,m2,ta,ma` | 0x0d1572d7 | 0x57 | V |
| `vle16.v v8,(a0)` | 0x02055407 | 0x07 | V |
| `vfmacc.vf v12,ft0,v10` | 0xb2a05657 | 0x57 | V |
| `vfredosum.vs v8,v10,v12` | 0x0ea61457 | 0x57 | V |
| `fcvt.bf16.s fa0,fa1,rne` | 0x44858553 | 0x53 | Zfbfmin |
| `fcvt.s.bf16 fa0,fa1` | 0x40658553 | 0x53 | Zfbfmin |
| `vfwcvtbf16.f.f.v v10,v8` | 0x4a869557 | 0x57 | Zvfbfmin |
| `vfncvtbf16.f.f.w v8,v10` | 0x4aae9457 | 0x57 | Zvfbfmin |
| `vfwmaccbf16.vf v12,ft0,v8` | 0xee805657 | 0x57 | Zvfbfwma |
| `fence iorw,iorw` | 0x0ff0000f | 0x0f | Base |
| `sw t0,0x600(a0)` | 0x60552023 | 0x23 | Base; MMIO behavior is platform-specific |

These words apply to the exact registers/operands shown, not every use of a mnemonic. For example, the FMA word stores bytes `43 85 c5 50` on a little-endian target. Vector encoding validity also depends on runtime `vtype`, group alignment and enabled extensions. [Scalar BF16 encodings](https://github.com/riscv/riscv-opcodes/blob/master/extensions/rv_zfbfmin), [vector BF16 encodings](https://github.com/riscv/riscv-opcodes/blob/master/extensions/rv_zvfbfmin).

## 6. Memory, latency and accelerator integration

The instruction mapping does not remove the workload's memory limit. Dense text projections alone account for 25,621,954,560 MACs per decoded token including the untied head. Reading one BF16 weight per MAC corresponds to 51,243,909,120 bytes (51.24 GB decimal), before state/KV/activation traffic and any reuse. This is a projection-stream baseline, not a claim that every active parameter is read once on every step. A matrix instruction cannot eliminate this transfer requirement.

| Design decision | Effect on assembly and schedule |
|---|---|
| Keep weights BF16 in memory | Widen only loaded blocks; optional BF16 FMA removes instructions but reads the same 2 bytes/weight |
| Pack bounded output tiles | Contiguous weight bursts feed lanes; naive K-major views can stride across distant rows. Measure cache/TLB behavior and comply with the existing layout hash |
| Cache activations and accumulate across K tiles | Reuse x, retain FP32 accumulators or spill exactly; never BF16-round an unfinished dot |
| U8 prefill reuse | Reuse one weight tile across multiple token accumulators; more live state/register pressure and mixer scheduling requirements |
| KV and Delta tiling | Retain useful state blocks; separate prediction/update dependencies; count all reads/writes and keep valid lengths/epochs |
| Latency hiding | Double buffers, enough outstanding reads, bounded credits; CPU `prefetch.r` is a hint, not a DMA transaction or completion guarantee |
| Cache maintenance | CBO instructions obey access/privilege/coherence rules; use the OS DMA API and board contract. Cache-block operations alone are not a device ownership protocol |

For a simplified streamed projection, `time >= max(MACs / sustained_MACs_per_s, transferred_bytes / sustained_bytes_per_s)` only when compute/transfer can overlap; startup, dependencies and stalls add time. Measure effective bandwidth and latency, not just DDR advertised width/rate. VLEN, issued vector instructions and physical MAC lanes are three different quantities. [Cache management specification](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/cmo.adoc).

The existing accelerator is controlled by **ABI command opcodes** 0..5. Its `EVALUATE=4` lives in the command structure at byte 6 as a u16. It is not an ISA instruction with opcode 0x04. [transport.S](../../isa/transport.S) copies an already validated 256-byte command into the mailbox and rings the command doorbell with value 1 using `sw`.

The submission example assumes session/region/upload/seal setup and OS DMA visibility are complete. Driver release ordering precedes ringing; acquire ordering precedes consuming a valid completion. A RISC-V `fence` orders accesses but does not wait for accelerator completion, drain PCIe writes, cancel DMA, make an invalid handle valid or prove safe buffer reuse. The existing tagged weight service, terminal-result ownership and fatal quarantine path remain required.

Custom instruction slots exist at major opcodes 0x0b, 0x2b, 0x5b, 0x7b. **No custom LLM instruction is defined or allocated by this document.** Keeping the current MMIO ABI avoids creating an instruction encoding, compiler intrinsic, privilege/trap model and restart/exception contract merely to start a long command. A future tightly coupled custom operation needs a separately versioned ISA proposal; it must not be represented as part of RVA23.

## 7. Development interpretation and next gates

There are three distinct uses of this mapping:

1. **CPU software reference:** run these scalar/RVV sequences on a suitable RISC-V simulator to inspect arithmetic order, layouts and opcodes. This is still software execution, not our accelerator RTL.
2. **Accelerator datapath specification:** implement the same primitive semantics in the planned GEMV, norm, nonlinear, Delta and attention RTL engines. Their internal micro-operations need not be RISC-V instructions. This preserves the current full-graph objective.
3. **A future programmable RVA23 core:** execute real scalar/vector instructions and meet the complete chosen profile. Its decoder, vector registers, precise execution, FP64 and other required facilities need a new resource/verification analysis; previous accelerator LUT estimates do not cover that CPU automatically.

For the current project, use route 2 and route 1 as supporting verification. First execute tiny ordered dot and norm tests, then compare baseline and native-BF16 vector kernels at multiple VLENs, then implement and freeze nonlinear manifests and full graph-boundary casting. Only afterward benchmark blocked kernels, memory overlap and full shapes. Existing D0-D9 and memory/hardware admission gates continue to apply.

FP16 or integer quantization is not a free opcode substitution for BF16-P0. V integer widening multiplies/MACs can support a future quantized path, but scales, zero points, packing, overflow, calibration and fidelity need their own policy. Likewise, newer draft/vendor matrix or dot-product instructions require separate feature checks and are not assumed merely because the core advertises RVA23.

The completed work here is the mapping, assemblable examples and encoding validation. RISC-V execution, independent numerical testing, driver integration, full-model inference, synthesis, timing and hardware throughput are explicitly unverified.
