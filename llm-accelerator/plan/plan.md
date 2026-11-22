# Complete LLM accelerator core: forward-pass module and dimension plan

**Current normative refinement:** [implementation contract](implementation-contract.md) and [ABI 1](abi-v1.md). The [review record](refinement-review.md) tracks independent findings; [checks](refinement-checks.json) are planning evidence, not RTL or hardware qualification.

Updated October 23, 2026, including memory, FPGA-resource and plan-gap refinements. Status: architecture and verification plan; no complete RTL forward pass has been implemented. This replaces the FFN-only objective in the previous plan. The previous plan is preserved as `ffn-demo-plan.md`: its FFN engine is an early milestone, not the final system.

The detailed [memory plan](memory-plan.md) now specifies residency, physical layouts, buffer budgets, transport queues and quantitative limits. Its reproducible model is `memory_model.py`; calculations are in `memory-model-results.json`. Section 9 summarizes the decisions. These are planning estimates and synthetic scheduling evidence, not measured hardware throughput.

The [plan gap audit](plan-gap-audit.md) defines the latest numerical, command, memory, recovery and acceptance contracts. Its decisions take precedence over earlier tentative interface choices. It closes 15 specification gaps, pins source revisions, and adds checked allocation/packing calculations; it does not mark pending RTL or hardware gates as complete.

## 1. Required end state and system boundary

The core must execute the **whole learned inference graph**, from token IDs to logits and updated model state. For image/video requests, it must also execute the learned vision encoder and place its output into the decoder's embedding stream. No normalization, attention, DeltaNet recurrence, activation, projection, or other learned model operation may silently fall back to host Python/C++.

"On the core" means computations execute in synthesizable RTL datapaths under the accelerator's controller. Weights, scratch tensors and persistent states may reside in external memory behind the core's memory interface. It does not mean that 27B parameters fit in FPGA block RAM. In simulation, a behavioral memory model is allowed to store these bytes and inject delays, but may not compute network outputs for the RTL.

The host may tokenize/detokenize, resize/normalize input pixels, provide frame timestamps and modality descriptors, load checkpoint tensors/constants and inputs, issue a command, and read results. Pixel patch gathering, learned position interpolation, vision blocks, merger, text embedding selection, positional transforms and the decoder run on the core. Tokenization and media decoding are preprocessing, not a hidden substitute for model execution. The definitive forward-pass output is the vocabulary logits plus caches; ABI 1 returns logits and the host selects the next token. On-core generation is a future separately versioned extension. Sampling is a generation policy layered on that output.

Two supported input routes are required in the final architecture:

1. **Text:** IDs -> embedding -> 64 decoder blocks -> final normalization -> vocabulary projection -> logits.
2. **Vision-language:** normalized pixels/video frames -> patch projection -> 27 vision blocks -> merger -> placeholder replacement -> the same complete text route.

Auxiliary MTP is not invoked by the ordinary inference forward path inspected in the source; no MTP acceleration or speculative speedup is assumed. If exposed later, it requires a separate graph and acceptance tests. Training/backpropagation are outside this inference objective.

## 2. Sources, profiles and what has been verified

Ground truth for the planning ledger is the saved official checkpoint config and inspected Hugging Face Qwen3.5-family implementation used by Qwen3.8-27B. `dimension-ledger.md` lists every learned tensor family in the active graph, including bias and normalization vectors. `full-dimension-audit.json` records counts and SHA-256 hashes of those source snapshots.

The subsequent provenance audit pins model revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` and Transformers revision `1a55addd658aaa95b52871f5b72e91a6b91449b6`. Fresh config, tensor index and model-source bytes match the existing audited snapshots. The saved `reference-sources/` includes numerical/vision helpers and tokenizer, generation and processor metadata. Runtime dependencies and tensor payload hashes still require qualification; source identity does not establish inference accuracy.

An independent exact-key audit also fetched only the JSON headers from all 18 checkpoint safetensors shards using bounded HTTP range requests. It checked all **1,199 tensor names, shapes, BF16 dtypes and byte spans** against the expected inventory: **1,184 active forward-path tensors and 15 auxiliary MTP tensors**, with no missing, unexpected or mismatched shapes. Total tensor payload is 55,562,855,904 bytes, agreeing with the official index metadata. No weight tensor payload was downloaded. `checkpoint-shape-audit.json` and the saved headers document this evidence. Packed-layout export, content hashes and actual numerical loading remain loader implementation gates.

The previous small MAC probes and synthetic quantized FFN tests remain useful but do not prove any full model path. New planning evidence in `full_forward_sanity.py` exercised a tiny synthetic four-layer hybrid text graph over eight tokens. Layer-major execution, token-major execution, resumed cached decode, reset and future-token causality agreed to less than 1e-5 (observed maximum difference zero). Both schedules share the same block function; this is a scheduling/state-lifetime sanity check, not independent proof of equations, RTL correctness or Qwen accuracy. Vision is not executed by that probe.

Use three explicit profiles; do not relabel a reduced model as Qwen:

| Dimension | Tiny complete-graph profile | Qwen3.8-27B text | Native vision encoder |
|---|---:|---:|---:|
| Hidden width | 32 | 5,120 | 1,152 |
| FFN width | 64 | 17,408 | 4,304 |
| Layers | 4: three DeltaNet + one full attention | 64: 48 DeltaNet + 16 full attention | 27 vision blocks |
| Vocabulary | 64 | 248,320 | Not applicable |
| Attention query / KV heads | 6 / 1 | 24 / 4 | 16 / 16 |
| Attention head dimension | 8 | 256 | 72 |
| Delta QK / V heads | 1 / 3 | 16 / 48 | Not applicable |
| Delta key / value head widths | 4 / 4 | 128 / 128 | Not applicable |
| Partial text rotary width | 2 | 64 | Vision rotates its full 72-wide head |
| Initial context cap | 32 tokens | Configured native maximum 262,144 | Per input grid/segment |

Tiny text uses mRoPE sections `[1,0,0]` for its two rotary coordinates. Its query width is 6*8=48, intentionally larger than H=32, and its GQA sharing factor is six, exercising the same non-equal-width and head-sharing issues as the native model. Tiny vision integration profile: width 32, four heads of width eight, two vision blocks, FFN width 64, patch 4x4, temporal patch two, spatial merge two, 16 learned positions (4x4 grid), output width 32. The first tiny image fixture is two repeated 8x8 RGB frames: four raw patches -> one merged visual token. A tiny complete graph is for control/operator validation; it has random weights and no expected language capability.

The first real-sized gate uses actual Qwen dimensions with a short context, e.g. 8-32 tokens. Native context capacity is a separate scale-up gate. Dimension configurability establishes a theoretical schedule, not evidence that huge RTL simulations finish quickly or an FPGA meets timing.

## 3. Complete model flow and scheduling

```text
host command + IDs + optional normalized pixels + weight/state memory
      |
      +-- vision input -> patch/position -> 27 vision blocks -> merger --+
      |                                                               |
      +-- token embedding -----------------> placeholder replacement <-+
                                               |
                              position IDs / masks / sequence controller
                                               |
                           repeat decoder blocks in exact layer order:
                          residual copy -> input RMSNorm
                                       -> DeltaNet OR full attention
                                       -> residual add
                                       -> post-mixer RMSNorm
                                       -> SwiGLU FFN
                                       -> residual add
                                               |
                              final RMSNorm -> LM head -> logits
                                               |
                                 optional argmax / next-token loop
```

Execute one logical operator at a time using shared units initially. There are 64 logical text blocks with different weights/state, not necessarily 64 physical copies. The controller reads a validated descriptor table for each layer. Layer 0-2 are DeltaNet, layer 3 full attention; this repeats 16 times. Use the actual `layer_types` list rather than inferring unsupported future layouts.

Start with token-major causal execution: for each token, run every decoder layer, update its own state and produce logits. Prompt prefill uses the same recurrent token-by-token path at first; full-attention layers read the causal prefix. This is semantically a complete causal prompt evaluation, albeit inefficient in weight reuse. The memory refinement adds layer-major/chunked prefill with explicit input-tile capacity and traffic accounting. It must match that reference. Start at U=1, qualify U=8 only after schedule/position/credit equivalence and measured spills, and treat U=16 as a later optional scale experiment. Weight reuse across known prompt rows cannot be assumed across unknown future generated tokens.

Vision is different: within each vision attention segment, all patch tokens must be available and attention is bidirectional. Run its blocks layer-major across the segment, then merge tokens. Reusing the text causal scheduler unchanged would be incorrect.

## 4. Shared module inventory and interface contracts

All names below are planned RTL modules. Every result stays on the core or in its external-memory workspace. Host golden calculations exist only in the testbench/reference environment.

| Module | Responsibility and shape contract | Execution and precision |
|---|---|---|
| `llm_core_top` | Command/descriptor validation, completion/error/status, output stream | Owns whole invocation; no opaque host callbacks |
| `model_sequencer` | Token/layer/operator loops, dependencies, barriers and memory lifetimes | Dimension counters independent of physical lane count |
| `tensor_dma` | Read/write weights, tensors and states through 64-bit byte addresses | Legal bursts, outstanding tags, finite destination credits, bounds/tail checks, write visibility and epoch-safe completion |
| `prefetch_scheduler` | Issue independent upcoming weight/input requests while current tiles execute | Respect producer readiness, available response capacity and consumer release |
| `memory_telemetry` | Count useful/wire bytes by tensor class, queues, stalls, occupancy and completion latency | Distinguish each memory tier/channel; reconcile model estimates with actual traces |
| `tile_packer_decoder` | Decode known weight layout, BF16 first; optional W8/W4 formats | Checkpoint export conversion is offline; tensor math is on core |
| `scratchpad_banks` | Synchronous local tiles and vector chunks | No full-H/full-I/full-S register arrays required |
| `fp32_alu` | Add/subtract, multiply/FMA, compare, divide, sqrt, integer conversion | Free HardFloat candidate; explicit wrappers and qualified formats |
| `bf16_convert` | BF16 storage to/from FP32 datapath | RNE conversion, explicit subnormal/NaN behavior |
| `gemv_engine` | `[N,K] * [K] -> [N]`; later share each weight tile across U prompt or B batch rows | BF16 operands expanded for FP32 accumulation initially; retain input vectors where capacity permits |
| `vector_engine` | Add, multiply, scale, broadcast, reductions and comparisons | Handles tails and strides; FP32 where required |
| `norm_engine` | RMS, L2 and LayerNorm, each with correct axis/gamma/beta | Shared reduction plus reciprocal sqrt, not one generic wrong formula |
| `nonlinear_engine` | exp, sigmoid, SiLU, stable softplus, GELU variants | Range reduction/polynomial or LUT, qualified errors |
| `position_engine` | Text/vision position generation, RoPE angles and layout | Integer position IDs; sin/cos on core from loaded constants |
| `attention_engine` | QK dots, masks, stable softmax, AV, gated output | Full text causal or vision segmented bidirectional mode |
| `kv_cache_manager` | Per-layer/head/position K/V append and reads | Store native KV head count, never permanent GQA duplication |
| `conv1d_engine` | Length-four depthwise causal convolution over projected QKV | One filter per channel, no channel mixing |
| `delta_state_engine` | Decay, prediction, correction, outer product, readout | Persistent FP32 state, per layer and sequence |
| `ffn_controller` | Gate/up projections, SiLU, product, down projection | Earlier FFN engine becomes this subgraph |
| `embedding_reader` | ID -> one embedding row | Independent untied output head |
| `vision_controller` | Patch gathering, position embedding, vision blocks/merger | Operates complete visual tensor before decoder insertion |
| `logits_writer` | Stream V logits or selected positions' logits | Full logits available even if greedy mode streams argmax |
| `generation_controller` | Deferred ABI extension; initial generation loop is on host | ABI 1 rejects opcode 6; complete logits still run on-core |

One shared FP32 arithmetic lane is sufficient for a functionally complete slow design. More lanes are optional parameters. The previous eight-lane integer engine may remain as an optimized kernel, but it cannot stand in for the floating-point/state/nonlinear machinery required by the full graph.

Operation interface: opcode, input/output addresses, shapes/strides, dtype, layer/sequence IDs, mask mode and tag; valid/ready on descriptors and results. Writes become visible before dependents run. An operation's done event means its writes and state commits completed, not merely that inputs were accepted. Keep exceptional FP values, invalid shapes, unsupported formats and memory errors observable.

The gap audit section 5 fixes the external interface as versioned 256-byte commands and 64-byte completions, using registered region handles with checked 64-bit offsets/extents. Host virtual pointers, checkpoint offsets, host DMA mappings and board addresses are distinct. The initial core memory beat is 128 bits; 64-byte alignment is not a bus width. The host may serve weight byte ranges through bounded DMA staging buffers; all network operations and graph sequencing remain on-core. Failed partial tokens/chunks invalidate the context; no automatic state rollback is promised.

Use at least 64-bit byte addresses and 64-bit byte/element products; native 16-bit weights exceed a 32-bit address space. Context length needs a counter that can represent 262,144 itself (19 bits), not merely positions 0..262,143 (18 bits). Vocabulary IDs require 18 bits; 32-bit descriptor fields are simpler. Dimension counters must not truncate FFN length 17,408, vocabulary width 248,320, or padded row counts.

## 5. Text tensor ledger: axes and matrix shapes

Notation: B=batch (first implementation B=1), T=new token count, S=valid cached prefix including the current token; H=5,120; I=17,408; Q=24; K=4; D=256; K_h=16; V_h=48; D_k=D_v=128. Weight shapes below are checkpoint/output-first `[out,in]`; activations list logical axes. A flattened bus must preserve these meanings.

### 5.1 Embedding, norms, residuals, FFN and logits

| Stage | Input -> output | Learned tensors / axis |
|---|---|---|
| Text embedding | IDs `[B,T]` -> `[B,T,5120]` | Embedding `[248320,5120]`; one row lookup per token |
| Input norm | `[B,T,5120]` -> same | Weight `[5120]`; reduce hidden axis |
| Mixer residual | Two `[B,T,5120]` -> same | Elementwise add; preserve pre-norm original input |
| Post-mixer norm | `[B,T,5120]` -> same | Distinct weight `[5120]` in every layer |
| FFN gate/up | `[B,T,5120]` -> two `[B,T,17408]` | Each weight `[17408,5120]`; no bias |
| SiLU and product | Two `[B,T,17408]` -> `[B,T,17408]` | Gate is SiLU(gate), then multiply up |
| FFN down | `[B,T,17408]` -> `[B,T,5120]` | Weight `[5120,17408]`; no bias |
| FFN residual | Two `[B,T,5120]` -> same | Original post-mixer residual, not normalized input |
| Final norm | `[B,T,5120]` -> same | Separate weight `[5120]` |
| LM head | `[B,T,5120]` -> `[B,T,248320]` | Weight `[248320,5120]`, untied, no bias |

Qwen's text RMSNorm is **zero-centered weight**: `x * rsqrt(mean(x^2)+1e-6) * (1+w)`. Do not replace `(1+w)` with `w`. It applies to text layer/final norms and full-attention Q/K norms in the inspected source. Normalization accumulation is FP32. FFN activation is SiLU, not GELU.

The LM head may compute only the last prompt position when the command asks for last-position logits; all-position mode must retain the `[T,V]` meaning and spill/stream results. Greedy argmax can consume each vocabulary row as generated without storing V logits, but the full-logit verification mode remains available.

### 5.2 Gated full attention: 16 logical blocks

| Operation | Tensor shape / dimension check |
|---|---|
| Q-plus-gate projection | Weight `[12288,5120]`, output `[B,T,12288]` |
| Per-head unpack | Reshape `[B,T,24,512]`, split each 512 into Q `[256]` and gate `[256]` |
| K / V projections | Each weight `[1024,5120]`; each output `[B,T,4,256]` |
| Q/K RMSNorm | Learned Q gamma `[256]` and K gamma `[256]`, shared across their respective heads; reduce width 256 |
| Partial RoPE | Transform first 64 coordinates of Q/K; remaining 192 pass through |
| KV append | Native K and V cache each `[B,4,S,256]` per layer |
| Group mapping | Query head h reads KV head `floor(h/6)`; Q/K/V head counts are not equal |
| Scores | Each query head computes `[T,S]`, scaled by `1/sqrt(256)=1/16` |
| Mask + softmax | Causal and valid-token masks; normalize over S only |
| Weighted values | Output `[B,T,24,256]`, flatten to 6,144 values |
| Output gate | `sigmoid(gate)` on the matching 24x256 values, not SiLU |
| Output projection | Weight `[5120,6144]`, produces `[B,T,5120]` |

**Important ordering:** Q-plus-gate projection is split within each head. Splitting the flat 12,288 vector into two global 6,144 halves without honoring the head packing is wrong. The packer must export the source's per-head layout explicitly.

Text RoPE uses a 64-wide rotated subvector, paired through `rotate_half` (first 32 with last 32 of that subvector), not adjacent-pair rotation across all 256 coordinates. The saved config's three-axis mRoPE sections are `[11,11,10]`, summing to 32 unique frequencies; sin/cos are duplicated to width 64. For frequency index j=0..31, omega_j=10,000,000^(-2*j/64). In this configured interleaving, j modulo three selects temporal/height/width respectively (11 temporal, 11 height, 10 width slots); duplicate the resulting 32-vector for the two rotated halves. For pure text, the three positional streams use the same sequence position. For multimodal input they differ. Test exact frequency-index/axis mapping against the pinned helper rather than generalizing this particular layout to other configs.

Position metadata has four logical streams in the inspected text model: causal text index plus temporal/height/width rotary indices. It may be carried as `[4,B,T]`. Text masks use the causal index; rotary phases use the other three. A modality/position controller produces them from descriptors; raw byte token offsets are not valid rotary positions.

### 5.3 Gated DeltaNet: 48 logical blocks

| Operation | Tensor shape / learned weight |
|---|---|
| QKV projection | Weight `[10240,5120]`, output `[B,T,10240]` |
| z gate projection | Weight `[6144,5120]`, output `[B,T,48,128]` |
| a / b projections | Each weight `[48,5120]`, output `[B,T,48]` |
| Depthwise convolution | Kernel `[10240,1,4]`; no bias; causal zero history at reset; followed by SiLU |
| Split Q/K/V | 2,048 Q + 2,048 K + 6,144 V = 10,240 |
| Native heads | Q/K `[B,T,16,128]`; V `[B,T,48,128]` |
| Q/K norm and mapping | L2 over 128; value head h uses native Q/K head `floor(h/3)` |
| beta | `sigmoid(b)` -> `[B,T,48]` |
| g / decay | `g=-exp(A_log)*softplus(a+dt_bias)`; both learned vectors `[48]`; decay `exp(g)` per value head |
| Query scaling | L2-normalized q is also multiplied by `1/sqrt(128)` |
| Persistent matrix | `[B,48,128,128]` FP32 per DeltaNet layer, axes key then value |
| Readout | `[B,T,48,128]` |
| Gated norm | RMS over final value axis 128; learned weight `[128]` shared over heads; multiply by **SiLU(z)** |
| Output projection | Flatten readout to 6,144; weight `[5120,6144]` -> `[B,T,5120]` |

For each value head and token, with S_old `[128,128]`, normalized k/q `[128]`, v `[128]`, beta/decay scalars:

```text
S_decay[k,v] = decay * S_old[k,v]
prediction[v] = sum_k k[k] * S_decay[k,v]
delta[v] = beta * (v_input[v] - prediction[v])
S_new[k,v] = S_decay[k,v] + k[k] * delta[v]
output[v] = sum_k q_scaled[k] * S_new[k,v]
```

The readout uses **updated** state. Do not omit Q's inverse-sqrt scaling, apply the wrong gate, normalize Q/K with RMS instead of L2, or make state `[128]` instead of `[128,128]`. Delta gated RMSNorm uses its direct learned weight (not `1+w`) and SiLU(z); it is a distinct mode from text zero-centered RMSNorm.

Convolution must retain per-layer/channel history of the **raw projected QKV**, not history of post-SiLU outputs. A kernel length four needs the current value plus three prior samples. A four-slot buffer is a conservative storage format compatible with the earlier estimate; exact update/slot ordering must match the pinned reference and be tested across prompt/decode boundaries.

## 6. Vision-language path: all learned encoder dimensions

Native variables: P_t=2 frames/temporal patch, P=16 pixels/spatial patch, C=3 channels, E=1,152, J=4,304, heads=16, head width=72, merge factor m=2. Let normalized/padded frame dimensions be F,H_px,W_px, all divisible by the required patch sizes; grid `(t_g,h_g,w_g)=(F/2,H_px/16,W_px/16)`. Each spatial grid dimension must be divisible by two for the merger.

Raw patch count `N=t_g*h_g*w_g`; merged visual token count `M=N/4`. For a static image, preprocessing repeats or supplies the temporal pair required by the official processor contract. One 224x224 image with repeated temporal pair yields t_g=1,h_g=w_g=14, N=196, M=49. Special text/modality tokens are additional decoder positions.

| Stage | Dimensions and on-core work |
|---|---|
| Patch gather/projection | Gather `[3,2,16,16]` = 1,536 values/patch. Conv3D weight `[1152,3,2,16,16]`, bias `[1152]`; equivalent matrix `[1152,1536]`; output `[N,1152]` |
| Learned position embedding | Table `[2304,1152]`, conceptual 48x48 grid. Bilinear interpolation gathers four table rows and weights per patch, adds to `[N,1152]` |
| Vision RoPE | Grid-indexed axial rotation of all 72 head coordinates: 18 unique frequencies for each spatial axis, concatenate h/w phases to 36, duplicate to 72 and rotate halves of width 36; distinct from partial text mRoPE |
| Vision norm1/norm2 | LayerNorm on 1,152 coordinates: subtract mean, divide by sqrt(variance+epsilon), multiply gamma, add beta; each gamma/beta `[1152]` |
| Vision QKV | Weight `[3456,1152]`, bias `[3456]`; reshape `[N,3,16,72]` |
| Vision attention | Noncausal attention inside each valid segment, scores per head `[N_segment,N_segment]`; no cross-segment attention |
| Vision attention output | `[N,1152]`; projection weight `[1152,1152]`, bias `[1152]` |
| Vision MLP | First `[4304,1152]` + bias `[4304]`, tanh-approximate GELU, second `[1152,4304]` + bias `[1152]` |
| Vision block residuals | Add after attention and after MLP; repeat all 27 distinct blocks |
| Merger normalization | LayerNorm over 1,152 before spatial grouping, gamma/beta `[1152]` |
| Spatial grouping | Concatenate each 2x2 group -> `[M,4608]`; use processor/encoder reorder, not four arbitrary raster neighbors |
| Merger MLP | `[4608,4608]` + bias `[4608]`, GELU with the reference default erf formulation, then `[5120,4608]` + bias `[5120]` -> `[M,5120]` |
| Placeholder replacement | Replace exactly M decoder visual placeholder rows, each width 5,120; reject count/type mismatch |

Vision input frame and attention segment boundaries are not automatically one huge video attention matrix. Derive `cu_seqlens` and ordering from the pinned vision helper: packed images/temporal groups must not attend across unrelated segments. Position interpolation uses align-corners semantics, and a grid dimension of one needs its own defined branch to avoid division by zero. Video timestamps and per-frame markers affect decoder positions; preserve them in the modality descriptor.

Both GELU variants need module support: tanh approximation for vision-block MLPs, erf/default GELU for the merger. A reusable nonlinear unit may implement erf via a qualified approximation, but replacing both with SiLU changes the model.

## 7. Numerical architecture for a complete pass

The earlier power-of-two W8 FFN is an optimization experiment, not a sufficient numerical foundation for 64 layers and FP32 recurrent state. Establish whole-graph correctness with a floating-point path first.

1. **REF32 diagnostic profile:** FP32 operands/states throughout, deterministic reduction and activation definitions. Use it for tiny whole-graph RTL validation; it is not an exact reproduction of BF16 serving kernels.
2. **BF16-storage profile:** native BF16 tensor storage, conversion to FP32 arithmetic, FP32 reductions and DeltaNet state, and explicit casts at source-defined boundaries. Match these boundaries in the software golden model. Reproduce the pinned reference's softmax output cast and gated-norm behavior; do not indiscriminately cast every intermediate.
3. **Quantized profile later:** independently qualify W8/W4 projections, scales and activation conversion across complete layers and logits. No assumption that a single FFN's 4.2% error remains acceptable through 64 layers.

Free arithmetic route: qualify the native Verilog Berkeley HardFloat release with Icarus, wrapped behind `fp32_alu`; use SoftFloat/TestFloat for primitive checks where appropriate. HardFloat supplies basic FP arithmetic, not exp/log/tanh/sin/cos/erf. Those require separately designed modules. The free source uses a permissive license; preserve its notices. Direct BF16 HardFloat instantiations need format/subnormal qualification; a simpler initial route is BF16 bit conversion into the tested FP32 datapath.

Specify round-to-nearest-even for the floating-point profiles, FMA versus separate multiply/add per opcode, reduction order, exception behavior, subnormals and cast locations. Use the selected policy in a bit-level primitive reference. Model-level comparison against PyTorch is tolerance-based because kernel reduction/fusion order may differ. The integer FFN's ties-away rule remains confined to that explicitly versioned quantized mode.

The gap audit section 3 now defines **BF16-P0** and its boundary table, including QK/scale casts before FP32 softmax, BF16 beta, the intermediate Delta gated-norm cast, distinct text/vision rotary arithmetic, and the BF16 LM-head output before optional widening for transport. Keep a bit-exact RTL-policy reference separate from a pinned framework reference. Source dtype traces, the fully ordered arithmetic table, immutable nonlinear manifests and fixed model-level fidelity ceilings must pass before this profile is called qualified. Delta L2 is `x*rsqrt(sum(x*x)+1e-6)`; all vision LayerNorm modes use epsilon `1e-6`.

An FMA pipeline does not sustain a dependent accumulator every cycle automatically. The candidate eight-lane schedule interleaves 16 independent output rows per lane, retains 128 FP32 accumulators (512 bytes), and requires measured feedback latency <=16 cycles for full issue. Reduction order remains increasing k for each row. Its 128x32 BF16 packed tiles are 8 KiB each; two fit the 16-KiB DMA allocation. HardFloat's combinational FMA still needs an actual timing/pipelining qualification; adding a wrapper alone does not establish 100/200 MHz.

Nonlinear design must cover **unbounded practical ranges**, not blindly clamp all values to an FFN LUT interval:

- exp: base-two range reduction plus mantissa approximation and exponent reconstruction; define overflow/underflow.
- softmax: subtract the row maximum before exp; ignore masked elements; all-masked rows produce specified zero output/error behavior instead of NaNs.
- sigmoid: sign-stable formulation; SiLU=x*sigmoid(x).
- softplus: `max(x,0)+log1p(exp(-abs(x)))` or a qualified equivalent; stable large-positive/negative branches.
- reciprocal sqrt: sqrt plus division initially; epsilon differs by norm mode and axis.
- sin/cos: range reduction and LUT/polynomial/CORDIC; mRoPE position multiplication uses adequate precision at large positions.
- GELU: separate tanh and erf variants with their documented formulas.

Each primitive needs directed exceptional-value tests and an error envelope over real checkpoint activations. The implementation contract fixes independent fidelity ceilings and exact calibration/holdout recipes now; calibration may tighten bounds, never enlarge them to accommodate observed error. Tiny synthetic agreement cannot certify pretrained quality.

LayerNorm uses population variance, reducing the final feature axis: first compute mean, then mean of squared centered differences. Do not silently substitute unbiased variance or an unstable subtraction of large moments. Text RMS and Delta L2 reductions use their distinct mean-versus-sum definitions. In synthesizable modules, neither SystemVerilog `real`/`shortreal`, `$exp`/`$sqrt`, nor DPI/Python numerical callbacks are acceptable implementations; those belong only to testbench/reference code. Numerical ROM constants are allowed, but all input-dependent operations execute in RTL.

## 8. Buffer, state and address-space accounting

### 8.1 Learned parameters: derived exact constructor inventory

The dimension audit counts all active text/vision parameters from the inspected constructors, including embeddings, norm vectors and vision biases:

| Active graph | Derived elements | BF16 bytes |
|---|---:|---:|
| Text embedding + all decoder layers + final norm + untied head | 26,895,998,464 | 53,791,996,928 |
| Vision encoder and merger | 460,730,096 | 921,460,192 |
| Combined | 27,356,728,560 | 54,713,457,120 |

These refine the earlier nominal "27B" capacity estimate and agree with the checked active checkpoint tensor headers. The separate 15-tensor MTP inventory contains 424,699,392 parameters, adding 849,398,784 BF16 bytes. The entire checkpoint therefore contains 27,781,427,952 parameters / 55,562,855,904 tensor bytes, while ordinary text/vision forward uses the active subset in the table. Archive/headers/padding may add file bytes. FP32 storage doubles the tensor byte counts. Four-bit packing of every tensor is not a realistic automatic allocation: small parameters, state and normalization may retain higher precision and scales add overhead.

MTP dimension inventory: `fc.weight` is `[5120,10240]`; pre-FC embedding/hidden norms and final norm are each `[5120]`; its one auxiliary block has the same `[12288,5120]` Q/gate, `[1024,5120]` K/V, `[5120,6144]` output, `[256]` Q/K norms, `[17408,5120]` gate/up and `[5120,17408]` down shapes as a text full-attention block, plus two `[5120]` layer norms. These fit existing module primitives plus concatenation. Auxiliary execution order, token alignment and speculation acceptance must follow a separately specified MTP forward contract; ordinary inference code inspected here does not invoke it, so no speculative behavior is invented.

For BF16 text inference, visual weights need not be fetched when no media is supplied. Embedding is a row lookup, not a whole-table stream. All-position logits require T*V values; at FP32, one vocabulary vector is 993,280 bytes. Streaming avoids holding it all in on-core SRAM.

### 8.2 Persistent sequence state

| Tensor family | Logical shape | Storage per B=1 sequence |
|---|---|---:|
| All DeltaNet states | `[48,48,128,128]` | 150,994,944 bytes FP32 = 144 MiB |
| Conservative convolution ring | `[48,10240,4]` | 3,932,160 bytes BF16 = 3.75 MiB |
| Full-attention K+V | `[16,2,4,S,256]` | 65,536*S bytes BF16 |

KV examples: S=32 -> 2 MiB; 4,096 -> 256 MiB; 32,768 -> 2 GiB; 262,144 -> 16 GiB. FP32 cache doubles these values. Batch/concurrent sequence count multiplies all sequence-specific state, not shared weights. Keep sequence ID and layer ID in the state address calculation.

Use 64-bit checked arithmetic for `base + stride*index`. Logical state axes are `[layer][sequence][value_head][key_dim][value_dim]`. The refined physical layout packs value-column panels as `[layer][sequence][head][value_panel][key][value_lane]`, making a 128x16 FP32 panel contiguous. Check logical-to-physical conversion explicitly. KV and conv each have their own descriptor strides. Reset should invalidate state descriptors/epochs rather than synchronously zero hundreds of megabytes through a register reset. New sequences require defined zero state: use explicit initialization writes or an epoch/valid scheme that returns zeros until the first committed write.

### 8.3 Scratch and bounded local working sets

Full vectors: H BF16=10 KiB; I BF16=34 KiB; Q/gate each 6,144 BF16=12 KiB; projected Delta QKV BF16=20 KiB. Vision hidden storage is N*1,152*2 bytes per buffer (451,584 bytes at N=196); QKV is three times this. A 2x2 merged feature row is 4,608 BF16=9 KiB. Scratch memory is external and its liveness is explicitly scheduled.

Do not carry over the old FFN demo's small maximum-H/I buffers as a full-Qwen limit. Full-core vectors are chunked. Physical buffers have bounded tile sizes, e.g. 8 output lanes, reduction tile 32, vector chunk 256, state tile 16x16. A state tile is 1 KiB FP32; two are 2 KiB. Per-head delta, prediction and readout are each 128 FP32=512 bytes. A full-attention value accumulator is 256 FP32=1 KiB. These fit bounded working sets even though the entire tensors do not.

The refined local-SRAM budget remains a 64-KiB logical payload target with mutually exclusive GEMV, grouped-attention and Delta modes; see the allocation table in `memory-plan.md`. GEMV retains up to 34 KiB of BF16 input plus 16 KiB DMA tiles. Delta mode uses two 8-KiB column panels; attention retains six query/output heads and K/V ping-pong buffers. This supersedes any assumption that 16x16 state tiles alone are the most efficient schedule. Optional 128/512-KiB profiles add queue or prompt capacity; none is verified FPGA fit. FP32 FFN input alone is 68 KiB, so that diagnostic storage mode needs extra capacity or counted spills. Exp/sin/GELU ROMs, arithmetic buffers, RAM rounding, banking/replication, ECC and CDC queues count in the physical resource report. No implicit full-context allocation in RTL is permitted.

## 9. Caching, bandwidth, latency and operator schedules

The [memory plan](memory-plan.md) defines the complete memory refinement, including exact assumptions, capacity tables, per-tier traffic, modes and M0-M6 measurement gates. The major architectural changes are below.

**Stream weights; retain useful inputs.** Ideal BF16 decode reads 51,249,210,368 weight bytes/token: all required text weights, including the untied head, but only one embedding row. A small LRU cache cannot retain a cyclic scan of the model. Use packed sequential tiles, explicit prefetch and selective pinning. Retain the current GEMV input across output rows; without retention, eight-output tiling can add roughly 6.41 GB of activation reads/token. SRAM banks must support arithmetic reads and DMA writes at their required rates.

**Delta state: one external read and write.** Instead of reading the full state twice, retain a 128-key x 16-value FP32 panel (8 KiB). Compute decay and the complete prediction for those value columns, update the retained panel, compute the corresponding output columns, then write it once. Complete all value panels before the full-head gated norm. Two panel buffers require 16 KiB. Matrix traffic falls from the old 432 MiB/token to **288 MiB/token** across 48 layers. Contiguous panel packing avoids scattered row-major slices. Prompt chunks may process U chronological recurrence steps per retained panel, amortizing that traffic over U, with explicit input/output scratch accounting.

**Grouped reference attention.** Process all six query heads belonging to one KV head together and reuse each key/value tile. Keep independent per-query maxima, denominator sums and output accumulators. Retain the chosen three-pass schedule initially: maximum, exponential denominator, then normalized/BF16-cast probabilities and AV, including BF16-P0's score/scale boundaries. This is not automatically bit-equivalent to a framework kernel. KV read traffic is `2*Ckv`, where `Ckv=65,536*S` bytes for the native cache across all 16 layers. Ungrouped execution costs `12*Ckv`. At S=4,096 this changes 3 GiB into 512 MiB of KV reads/token; compute still includes three different QK passes for every query. No permanent GQA expansion is stored.

**Online attention is a separate numerical profile.** One-pass online softmax/AV can approach `Ckv` reads, but changes reduction order and does not reproduce a BF16 cast of each globally normalized probability before AV. A two-pass online-denominator plus cast-probability/AV variant uses `1.5*Ckv`. Qualify each against the selected arithmetic reference before substituting it. Saved-score variants trade extra scratch traffic against repeated QK scans and must remain bounded.

**Bounded scratch modes and finite DMA credits.** Use operator-specific lifetimes and legal bursts, independent tagged requests, response buffers, backpressure and acknowledged writes. A 64-KiB logical budget does not permit arbitrary outstanding requests. At an illustrative 8-GB/s service and 2-us first-byte latency, five 4-KiB requests are needed to saturate an ideal response bus; eight reserve 32 KiB of destinations. A 16-KiB tile allocation cannot accept that much. Prefetch depth must match latency, tile consumption and genuinely free buffers. Account for shared DDR read/write bandwidth and bank conflicts.

**Decode performance is bounded by both compute and traffic.** With grouped reference attention at S=4,096, modeled BF16 weights/state/KV/logits total 52.097 GB/token, before activation spills and protocol overhead. At 8 effective GB/s this is at least 6.512 s/token for memory alone. Eight MAC lanes at an assumed 200 MHz need at least 16.014 s/token for dense projections alone; attention and other operators add work. Quantized storage estimates are sensitivity studies, not quality-qualified implementations or promised speedups.

**Host-backed tiers.** If every missing weight is written into board DDR and read back by compute, count both transfers. Let W be consumed weight bytes, C pinned bytes and M other local traffic: host reads at least `W-C`, board DDR handles at least `2*W-C+M`. Direct host-to-SRAM streaming has a different budget and requires a supported implementation. Separate checkpoint load time, prefill time, decode latency and simulator wall time. Never assume a host link can provide DDR-class effective throughput.

**Concrete allocation and topology.** The gap audit reserves 836 MiB for the initial 4K-context state/workspace/staging map, leaving 188 MiB under a tested 1-GiB aperture or 1,212 MiB at 2 GiB. This remains a proposed map requiring board/liveness validation. The candidate 128-output packed layout adds 75 MiB of text weight padding/token. With hypothetical host service 3 GB/s and shared DDR service 4 GB/s, staged DDR alone needs 25.876 s/token, rather than the separate resident-weight memory scenario's 6.512 s. Every bridge's width/clock and source/destination credits must be included.

**Prefill and vision.** Layer-major prompt chunks reuse weights across known rows, but U=16 BF16 FFN down inputs require 544 KiB, so they do not fit the small scratchpad. Count reloaded inputs and intermediate spills or reduce U per operator. Vision stays layer-major and segmented bidirectional; it has no sixfold GQA reuse. Cache compatible merged visual features instead of re-running the encoder during every later text token. All patch/segment/position semantics remain unchanged.

**Residuals and commits.** Preserve external residuals until their consumers finish. Current-token K/V must be visible before attention reads it; Delta writes precede the next dependent recurrence. Publish context length and rope delta only after the entire command’s layers, logits and state writes complete; U1/U8 barriers are internal. Full multimodal positions are planned on-core before chunking, retained for the command, and fresh media in a nonempty cache is rejected. Normal cancel drains within a bounded deadline; fatal transport uses OFFLINE/quarantined mappings until positive quiescence. Partial failures invalidate the context. Snapshot/prefix sharing remain future features.

**Evidence.** `memory_model.py` calculates traffic/capacity and an ideal finite-queue burst stream; it is not a DDR/FPGA benchmark. The new synthetic NumPy schedule probe compared column panels against whole 128x128 state updates over nine tokens (15 width/chunk combinations, max output difference 8.94e-8), and six-head shared KV against separate-head three-pass attention (identical outputs, sixfold lower KV read bytes). Native checkpoint numerics, RTL timing, SRAM mapping and hardware rates remain open gates.

## 10. Exact dimension and layout invariants

The loader/controller and tests must enforce all of these before execution:

1. Layer count equals `len(layer_types)` and each layer type has a matching weight/state descriptor.
2. Text H does **not** imply attention width: actual Q width is 24*256=6,144, larger than H=5,120.
3. Q-plus-gate width is twice Q width; per-head packing is preserved.
4. Q_heads % KV_heads == 0 (24/4=6); V_heads % QK_heads == 0 for DeltaNet (48/16=3).
5. Delta QKV width = 2*K_h*D_k + V_h*D_v = 10,240. Distinguish 16 native QK heads from 48 state heads.
6. Text partial rotary width is even, <=D, and equals 64; mRoPE section sum equals width/2=32. Axis ordering matches source helper.
7. Delta state key/value axes are both 128 now but remain separate descriptor fields; do not exploit equality to hide a transpose bug.
8. Text norm parameter shape is H, full-attention Q/K norm shape is D, gated Delta norm shape is D_v. Norm axes are not interchangeable.
9. FFN gate/up output I matches down input I; residual/output H match. Gate/up and LM output weights are separate tensor descriptors.
10. Vision width 1,152 divides into 16 heads of width 72; never borrow text head width 256.
11. Patch flatten size =3*2*16*16=1,536. Temporal/spatial/channel order matches exported weight layout.
12. Learned vision position count 2,304 is a 48x48 grid. Grid interpolation and 2x2 spatial merge use consistent patch reorder.
13. Vision merger width =1,152*2*2=4,608; its output width equals decoder H=5,120.
14. N raw patches /4 equals the number of visual placeholder rows; check separately per image/video item and modality.
15. Pixel dimensions/grid/segment lengths are valid and bounded; no padded token contributes to attention reductions or state updates.
16. S includes the current appended position where appropriate, and 0<=position<capacity. Counter widths can represent capacity itself.
17. All byte ranges fit allocated memory, alignment is obeyed, and region aliasing respects lifetimes. BF16/FP32/packed integer byte strides differ.
18. Tile remainder masks protect non-multiple widths, including vision's head dimension 72 and FFN width 4,304. Test tails, not just powers of two.

`audit_full_dimensions.py` checks the algebraic invariants derivable from config and produces the complete learned tensor ledger. It cannot verify attention masks, mRoPE index permutation, checkpoint key names or RTL buffer addressing by itself; those have explicit implementation tests below.

## 11. Verification plan: whole-graph completion gates

There are three distinct evidence levels: static dimension coverage, numerical software graph validation, and actual synthesizable RTL execution. The memory plan adds M0-M6 for analytical traffic, finite-queue memory modeling, schedule equivalence, SRAM/DMA traces, timed whole-graph simulation, native runtime samples and actual transport/board measurements. Report them separately. Neither a successful graph walk nor a passing FFN is a complete core forward pass.

| Gate | Required result |
|---|---|
| D0: checkpoint and descriptor audit | Tensor name/shape/dtype/byte-span audit is complete at plan time. Still implement packed export/layout descriptors, tensor data validation and loader errors; reject missing/unexpected active tensors |
| D1: arithmetic primitives | Free FP32 datapath compiles in Icarus; primitive bit tests/rounding/NaN/subnormal flags; qualified exp/log1p/sin/cos/GELU approximation envelopes |
| D2: module tests | Every planned numerical module receives shape, tail, exceptional-value, stall and reset tests; no host numerical fallback |
| D3: text block tests | Delta block compares conv history, Q/K norm, beta/decay, state before/after, gate and output; full-attention block compares head unpack, RoPE, masks, probabilities, gate and output |
| D4: tiny complete text RTL | IDs -> all four hybrid blocks -> final norm -> all logits; exact selected arithmetic reference; 8-token prefill, resumed decode and reset |
| D5: vision modules and tiny VL RTL | Pixels -> patch/position -> two vision blocks -> merger -> placeholder replace -> complete tiny text graph -> logits; no precomputed host encoder outputs |
| D6: native-shape layer tests | H/I/head/patch/vision dimensions from actual config, short S; independent source-based reference and resource/traffic counters |
| D7: complete actual model text pass | All 64 blocks and vocabulary head execute on the core with actual checkpoint weights, short context, validated logits/cache comparison; trace proves every layer executed |
| D8: complete actual multimodal pass | Actual vision weights, all 27 vision blocks/merger plus all 64 text blocks; processed-pixel fixture; correct modality positions/segments and logits |
| D9: scale and hardware feasibility | Larger S/batches, runtime memory allocation, sustained memory traffic, synthesis and target-specific routing; publish limitations |

D7 is the required proof of the complete text model. D8 is required before claiming the **entire multimodal model** is on-core. D4/D5 are development stepping stones and cannot replace D7/D8. Actual checkpoint storage/download and potentially long simulation jobs will be needed to execute those gates, even though the present plan and tiny tests are free and small.

Comparison policy: prescribed primitive operations, reductions and cast traces match the BF16-P0 policy oracle bit-for-bit. Independent framework comparisons must meet the implementation contract’s fixed intermediate/state/logit/distribution ceilings and all-position top-1/top-5 rates, including low-margin cases. Software calibration may tighten per-operator limits before RTL results are viewed. Failed fidelity requires revising arithmetic, not widening the passing threshold.

Critical tests: distinguish Q-head gate halves; head mappings at boundaries 5/6 and 2/3; RoPE pass-through coordinates; zero-norm inputs; empty/all-masked prefixes; strict causality under future-token perturbation; distinct per-layer sentinels to detect weight/state aliasing; zero-length/overflow descriptors; partial tiles; backpressure; reset halfway through state write; splitting a prompt at multiple boundaries; convolution history across decode; vision grid dimension one; non-square images; multiple images/frame segments; placeholder-count mismatch; both GELU modes.

The gap audit adds mandatory command/ownership/fault tests, pinned processor fixtures, acceptance datasets, FPGA CDC/reset/timing gates and measured simulator runtime. Initial admitted hardware workloads are B=1, native context capacity <=4,096, with shorter first checkpoint runs and bounded vision grids; unsupported masks/batches/sizes are rejected before mutation. A 256x256 processed image is the first native VL fixture. The host-side greedy development loop checks EOS IDs **248046 and 248044**, lowest-ID ties and maximum-token termination; it is distinct from the checkpoint's default sampling policy. The 262,144-token configuration remains a later scale gate, not a claimed first-board capacity.

Use a trace scoreboard with per-layer IDs and checksums for residuals, norms, projections, Q/K/V, state and logits. Independent numerical references must not import RTL implementation approximations as their only definition. For a failed stage retain both the local exact-policy result and the pinned model comparison to separate implementation errors from approximation drift.

## 12. Free toolchain, project structure and sequence

Continue with SystemVerilog and the existing ARM Ubuntu-24.04 WSL Icarus/Python path; NumPy, GTKWave, Yosys, Verilator and the framework runtime must be version-checked or installed/qualified as needed. This Snapdragon ARM host is not a supported Vivado x86-64 host. Hardware build/programming and native Linux PCIe runtime require confirmed compatible host access. Current 45.22-GiB free disk cannot hold the 55.56-GB checkpoint; start with bounded tiny/tensor jobs. The implementation contract specifies storage/RAM/runtime admission. Add a pinned free HardFloat release and preserve its license; qualify it before dependent modules. SoftFloat/TestFloat and an independent framework runtime remain verification prerequisites as appropriate to each gate.

```text
llm-accelerator/
  spec/architecture.md, tensor_layout.md, numerics.md, descriptors.md
  profiles/tiny_text.json, tiny_vl.json, qwen3.8-27b.json
  rtl/control/       core, sequencer, position/modality, descriptor checks
  rtl/memory/        DMA, scratch banks, KV/conv/state managers
  rtl/arithmetic/    FP32 wrapper, BF16 conversion, GEMV, vector, reductions
  rtl/nonlinear/     exp, log1p, sigmoid, SiLU, GELU, sin/cos
  rtl/text/          embedding, norms, DeltaNet, attention, FFN, logits
  rtl/vision/        patch gather, position interpolation, blocks, merger
  reference/        independent modules and complete text/VL graphs
  tools/            tensor-index audit/export, packer, simulator runner
  tests/            primitives, module shapes, full graph, protocols
  reports/          provenance, comparison, coverage, dimensions, traffic
  planning-evidence/ saved probes and dimension ledger from planning
```

Implementation order: freeze ledger/descriptors, physical packing and scratch liveness -> finite-bandwidth/latency memory harness with credited DMA/counters alongside FP32/nonlinear primitives -> shared vector/GEMV/norms -> standalone FFN -> complete DeltaNet block -> full-attention block/cache/RoPE -> tiny complete text -> vision operators/tiny complete VL -> native-shape layers -> complete actual checkpoint runs -> optimization and physical deployment. Quantized kernels can be developed in parallel conceptually, but must not block a credible floating-point graph path or be used to conceal missing operators.

This is substantially larger than the old 8-15-session FFN estimate. A complete verified core including floating-point/nonlinear units, both mixer types and vision is a multi-month engineering project for an individual, with large uncertainty. Do not turn the schedule estimate into a claim that native-model simulation or board fit is already demonstrated.

## 13. Feasibility conclusion and open engineering gates

**Theoretically complete:** every ordinary text/VL forward operation now has an assigned module, tensor shape, state definition and execution route. Parameter widths, GQA/Delta head mappings, patch/merger dimensions and state counts were statically audited, and every checkpoint tensor shape was independently verified from actual shard headers. A serial/tiled implementation can reuse bounded local resources and external storage; full unrolling is unnecessary.

**Numerically feasible but not yet qualified:** free FP primitives exist; nonlinear approximations, BF16 cast boundaries and recurrence stability must be verified. The earlier simple W4 quantization failed its synthetic quality target and is not the correctness baseline.

**Simulation feasible in stages:** tiny complete-graph tests and isolated native-shape blocks are reasonable starting goals. A native 27B forward includes tens of billions of MACs/token, large weight files and potentially prohibitive event-driven simulation runtime. An operator-count estimate alone cannot establish completion time. Measure representative FP GEMV/state/attention/nonlinear throughput before D7/D8. The 256-patch D8 image requires 64 visual placeholders plus two markers: 66 decoder positions. Its calculated eight-lane floor is about 25 days at a hypothetical 100k simulator cycles/s. Admit at most 48 hours per fixture after a 2x margin, or improve the host/simulator or execute the unchanged full proof on qualified hardware. All fixture/state comparisons remain required.

**Low-cost FPGA residency unresolved:** the constructor-derived model weights alone are about 54.71 GB BF16, plus cache/state/scratch. Existing under-$500 boards with small DDR cannot hold that locally. A host-backed memory system could theoretically supply it, but then transfer bandwidth and latency dominate and require measurement. Nothing in this plan claims complete Qwen fits an Arty/ULX3S/KU5P board's installed RAM or runs interactively.

**Development resource target, October 23:** the [FPGA resource and board analysis](fpga-resource-and-board-analysis.md) budgets roughly **40–90k physical LUT6, 25–80 DSPs and 70–170 RAMB36 equivalents** for eight shared FP32 lanes, complete operator controllers, one DDR channel, PCIe DMA and modest debug. These are explicit engineering allowances, not synthesis results. Conditional on compatible host access and board gates, the preferred development target is **XCKU5P on a documented RK-XCKU5P-F V1.2**, with 216,960 LUT6 and 2 GiB DDR4; the matching documented interface is PCIe Gen3 x4, despite an inconsistent marketplace x8 title. A used XC7K325T is the cheapest large-fabric candidate, conditional on usable board documentation and memory. Start at 100 MHz and qualify higher clocks through routing. The KU5P supports native-layer experiments and host-backed graph development; it does not solve complete-model residency. Synthesize the actual arithmetic, SRAM wrappers and board interfaces before replacing this budget with measured counts.

The next concrete work follows the gap audit section 12: finish D0 with runtime dtype traces, a locked reference and tested packer/ABI; qualify actual FP32/BF16 arithmetic and SRAM mapping for D1; then implement the credited memory harness and whole-graph sequencer. The checkpoint shape inventory and planning calculations are already checked. Native-model simulator wall time, activation/liveness traces, numerical quality and measured transport still need evidence before a deployment claim.

## 14. Sources and saved artifacts

Latest gap refinement: [plan-gap-audit.md](plan-gap-audit.md), `plan_audit_checks.py`, `plan-audit-checks.json` and `reference-sources/`. The audit gives the 15-gap register, exact source revisions, numerical/ABI/layout/recovery contracts, bounded workloads and ordered work packets. Source hashes and allocation/packing arithmetic passed; implementation gates remain open.

New hardware feasibility refinement: [fpga-resource-and-board-analysis.md](fpga-resource-and-board-analysis.md), reproducible `fpga_resource_estimate.py`, and `fpga-resource-estimate.json`. The analysis includes primary-source implementation anchors, device capacities, dated board listings, free-tool licensing checks and synthesis/bring-up gates. Its allowances remain separate from measured implementation evidence.

New memory refinement: `memory-plan.md`, reproducible `memory_model.py`, `memory-model-results.json`, and the synthetic `memory_schedule_probe.py` / `memory-schedule-probe.json`. Copies of the probes/results are in the project planning-evidence directory. The companion memory plan cites primary sources for IO-aware attention and AXI transfer/measurement behavior; its hardware scenarios are explicit assumptions.

- [Official Qwen3.8-27B configuration](https://huggingface.co/Qwen/Qwen3.8-27B/raw/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/config.json)
- [Official model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [Inspected implementation family](https://github.com/huggingface/transformers/blob/1a55addd658aaa95b52871f5b72e91a6b91449b6/src/transformers/models/qwen3_5/modeling_qwen3_5.py)
- [Official checkpoint weight index](https://huggingface.co/Qwen/Qwen3.8-27B/raw/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/model.safetensors.index.json), reconciled with bounded-range JSON headers for all 18 indexed shards
- [Berkeley HardFloat native Verilog release and operation list](https://www.jhauser.us/arithmetic/HardFloat.html)
- [HardFloat formats, BF16 caveats and licensing](https://www.jhauser.us/arithmetic/HardFloat-1/doc/HardFloat-Verilog.html)
- [Berkeley SoftFloat](https://github.com/ucb-bar/berkeley-softfloat-3)

Existing local context: `research.md`, the Qwen compute analysis and `ffn-demo-plan.md`. Current planning evidence: `audit_full_dimensions.py`, `dimension-ledger.md`, `full-dimension-audit.json`, `verify_checkpoint_shapes.py`, `checkpoint-shape-audit.json`, `qwen-weight-index.json`, `qwen-headers/`, `fetch_tensor_headers.py`, `full_forward_sanity.py`, and `full-forward-sanity.json` under `llm-accelerator/planning-evidence/`. Snapshot hashes in the audit distinguish inspected sources from moving URLs. No new complete accelerator was implemented while preparing this plan.
