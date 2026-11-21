# Plan gap audit and implementation contracts

**Current normative refinement:** [implementation contract](implementation-contract.md) and [ABI 1](abi-v1.md). The [review record](refinement-review.md) tracks independent findings; [checks](refinement-checks.json) are planning evidence, not RTL or hardware qualification.

Updated October 23, 2026. Applies to `plan.md`, `memory-plan.md` and `fpga-resource-and-board-analysis.md`. This is a planning refinement, not an accelerator implementation. Decisions below supersede conflicting earlier working assumptions. Hardware fit, arithmetic quality and full-model execution remain explicit evidence gates.

The audit found gaps in source provenance, dtype boundaries, accumulator scheduling, physical packing, transport address spaces, command completion, recovery, input limits and proof of performance. The critical path is now: **freeze the arithmetic/format contract -> qualify one real arithmetic lane and its memory adapter -> complete tiny text/vision RTL -> scale to native dimensions -> execute actual checkpoint workloads -> optimize.** Board purchase is not needed for the first synthesis experiments.

## 1. Gap register and closure evidence

| ID | Gap or misleading assumption | Decision added | Required implementation evidence |
|---|---|---|---|
| G01 | Moving source URLs and unrecorded helper/default behavior | Immutable model/Transformers revisions; byte comparison; saved helper, generation and processor files | Reproducible runtime dependency lock and resolved configuration |
| G02 | “BF16 storage” did not identify every rounded intermediate | Boundary table and separate exact-policy/framework references | Dtype trace and numerical qualification before block RTL |
| G03 | Pipelined FMA treated as a one-cycle dependent accumulator | Interleave independent output rows; preserve reduction order; measure full feedback latency | Lane throughput, inferred DSPs, numerical tests and routed timing |
| G04 | Packing and SRAM credits were abstract | 8-lane/16-context/32-reduction candidate layout, two 8-KiB tiles, explicit credit invariant | Packer round-trip, bank/port traces and masked-tail tests |
| G05 | Host addresses, model offsets and board addresses could be confused | Region handles plus checked 64-bit offsets; separate host DMA translation | Above-4-GiB, noncontiguous mapping and bounds tests |
| G06 | No concrete host command/completion ABI | Versioned 256-byte command and 64-byte completion contract | Parser, ordering, stale-ID and malformed-command tests |
| G07 | A failed token could leave partially updated state | Context-invalidating failure policy; no implied rollback | Fault injection before/during/after state writes |
| G08 | No complete small-DDR allocation | Illustrative 836-MiB reservation, runtime admission checks | Physical memory map, full-range memtest and high-water traces |
| G09 | Pipeline/PCIe/DDR rates were considered separately | Per-port and staged-DDR rooflines; measure actual overlap | Timed trace and hardware service-rate measurements |
| G10 | Vision ordering, processor overrides and timestamp handling were not pinned | Raster input contract, exact gather/reorder, pinned processor fixtures | Independent patch/position/segment comparisons |
| G11 | Optional generation could use the wrong EOS and sampling behavior | Two EOS IDs; explicit greedy bring-up; deterministic argmax | Both EOS cases, tie handling and max-token termination |
| G12 | “Complete graph” did not define an admitted workload | B=1 bounded profiles and capability reporting | Reject unsupported sizes before mutation; preserve final full-graph objective |
| G13 | Tests lacked a workload/error/fault matrix | Independent numerical layers, holdout fixtures, commit and liveness checks | D0-D9 plus M0-M6 evidence, not synthetic agreement alone |
| G14 | FPGA readiness omitted clock/reset/CDC, driver and thermal gates | Shell-first bring-up and complete build manifest | Post-route timing/CDC, memory/DMA tests and sustained thermal run |
| G15 | Native RTL runtime and host capacity were unbudgeted | Measured simulator extrapolation, staged downloads and working-set ledger | Short native benchmark before a full expensive run |

“Decision added” means the plan gap is specified. It does not mean the implementation or its acceptance test has passed. Newly completed evidence is limited to source identity and the arithmetic checks in `plan-audit-checks.json`.

## 2. Freeze the reference and input identity

Pinned model revision: **`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`** in `Qwen/Qwen3.8-27B`. Pinned Transformers revision: **`1a55addd658aaa95b52871f5b72e91a6b91449b6`**. The freshly fetched config, tensor index and `modeling_qwen3_5.py` are byte-identical to the earlier audited files. Existing dimension/header evidence is therefore still applicable to those exact snapshots; this does not validate the undisclosed tensor payload contents.

Saved under `reference-sources/`: config, weight index, generation/tokenizer metadata, chat template, image/video processor metadata, model/config source, vision helpers, rotary/configuration helpers and referenced processor sources. `reference-source-lock.json` pins the expected bytes, origins and SHA256 of all 16 identity files; its own digest is anchored in the checker. The README is explicitly mutable documentation. Mutation/missing/extra-file/lock-negative tests reject changes. No model-weight payload was downloaded. [Pinned model](https://huggingface.co/Qwen/Qwen3.8-27B/tree/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0), [pinned Transformers](https://github.com/huggingface/transformers/tree/1a55addd658aaa95b52871f5b72e91a6b91449b6).

Before D1/D3, record the actual Python, PyTorch, Transformers, NumPy, simulator and arithmetic-library versions/commits; OS, CPU instruction support, flags and thread counts; resolved config defaults; attention implementation; enabled kernel substitutions; and arithmetic constants. Pin package hashes or a lockfile. The config's `5.8.0.dev0` string alone is not a dependency lock. Run evaluation mode with dropout disabled. Disable optional fused attention/FLA/hub substitutions in the reference harness unless explicitly captured as a separately named comparison backend. Confirm the chosen functions actually executed using traces.

Each fixture binds: model revision, numerical profile, layout version, tokenizer files/chat-template hash, exact token IDs, masks, normalized pixel bytes, grids, modality types, frame timestamps and expected positional metadata. Processor defaults must come from this checkpoint's metadata; do not silently inherit another Qwen or CLIP model's normalization. Tokenizer vocabulary/merges or tokenizer artifact content, PyTorch dependencies and runtime behavior still need their own lock when the harness is implemented.

Header validation is not weight integrity. Before executing real weights, download only required shards/tensors for the stage, verify range lengths and tensor spans, record content digests, and reject truncated/stale data. Keep original and packed tensor digests plus packer version. Do not mix a newly fetched model revision with old tensor headers or cached prefixes.

## 3. Numerical policy and reference hierarchy

Keep **REF32** for tiny diagnostic tests. Name the initial native storage profile **BF16-P0**: checkpoint storage BF16, persistent Delta matrix FP32, integer indexing exact, RNE casts, gradual underflow in the initial basic FP path, no silent flush-to-zero. An eventual FTZ or quantized implementation gets a different numerical profile ID and quality gate.

There are two independent comparisons:

1. **RTL-policy reference:** mirrors our explicitly ordered FMA/add/multiply and approximation/cast policy. Basic primitives and deterministic instruction traces must be bit-exact to this reference, including defined NaN normalization. It does not claim every libm transcendental is correctly rounded.
2. **Pinned framework reference:** source-defined dtype boundaries and model behavior, with its actual backend recorded. Compare tensors, state and logits with predeclared tolerances; framework reduction/fusion order need not match our hardware. The framework oracle must not reuse our approximation code as its only implementation.

The following boundaries close omissions in the earlier “cast where the source casts” instruction. BF16 below means round the result to BF16 and then widen losslessly if a subsequent FP32 unit consumes it. Do not keep extra FP32 precision across a required BF16 boundary. A dtype probe of the pinned runtime is a release gate for this table.

| Operation family | BF16-P0 boundary rule |
|---|---|
| Embedding, linear/conv outputs, ordinary residuals | BF16 tensors; accumulate linear/conv arithmetic in the specified FP32 order, include bias before the final result cast; residual add produces BF16 |
| Text RMSNorm and Q/K norm | FP32 norm and multiplication by `1 + FP32(weight)`; cast the final output once to BF16; epsilon `1e-6` |
| Text RoPE | Form phases in FP32, compute sin/cos, cast trig values to BF16; each BF16 product and their BF16 sum is an observable boundary in the selected eager-style profile |
| Attention scores and scale | Cast QK dot output to BF16, then cast the scaled score to BF16 before FP32 softmax; masking uses explicit validity bits rather than requiring a fabricated large negative arithmetic value |
| Attention probability / AV / gate | FP32 softmax reduction, probabilities cast to BF16; AV result BF16; sigmoid(gate) BF16, product BF16, output projection BF16 |
| Delta beta and decay | `sigmoid(b)` stored BF16 before widening; `a`, bias and A_log are widened for the source FP32 softplus/exp path; decay and recurrent matrix stay FP32 |
| Delta Q/K normalization | `x * rsqrt(sum(x*x) + 1e-6)` in FP32; this is not `x/max(norm(x),eps)` and not RMSNorm; Q also receives `1/sqrt(128)` |
| Delta recurrent output and gated norm | Readout casts to BF16 before gated norm; normalize in FP32, cast normalized vector to BF16, multiply by BF16 learned weight and round, multiply by FP32 SiLU(z), then cast to BF16 |
| FFN | Gate/up projections BF16, SiLU output BF16, gate-times-up BF16, down projection BF16 |
| Vision norm/position/rotary | LayerNorm population variance with epsilon `1e-6`; output BF16. Position-table interpolation uses FP32 weights/reduction then BF16 before addition. Vision rotary promotes Q/K and trig operands to FP32 for rotation, then casts back to BF16; it differs from text rotary |
| LM head / result transport | Preserve the projection's BF16 output boundary for BF16-P0. The diagnostic FP32 logits buffer is a widening of those values, not permission to remove the BF16 cast |

These rules refine rather than certify framework equivalence: PyTorch linear/conv kernels, reduction trees and fused activation internals must be measured. The same distinction applies to three-pass attention: it is our reference schedule and preserves chosen boundaries; calling it automatically bit-equivalent to a serving kernel would be incorrect. Delta chunk and recurrent paths also need tolerance-based comparison, not an assertion that algebraic equivalence implies equal floating-point bits.

For standalone vector/Delta expressions, keep separate FP32 multiply and add where specified; do not silently contract them into FMA. GEMV uses a declared FP32 FMA chain in increasing reduction index. Norm/reduction modules use the implementation contract’s ascending serial order, with fixed bias/nonlinear/cast sequencing. Initialize accumulators with +0; preserve valid finite signed-zero behavior. Canonicalize NaNs to FP32 `0x7fc00000` / BF16 `0x7fc0` at the primitive wrapper, maintain the appropriate sticky invalid/divide-by-zero/overflow/underflow/inexact flags, and abort a native command on unexpected nonfinite model intermediates. Underflow/inexact alone are observable but not automatic failures. Invalid/all-masked rows return zero plus an explicit row status; an unexpectedly all-masked valid text row is an error. Padding rows do not advance state.

Nonlinear modules require a deterministic coefficient/ROM-generation recipe, its hashes, range-reduction widths and a high-precision independent oracle. Initial engineering acceptance targets: sin/cos and bounded sigmoid/tanh/erf absolute error <=2e-6; exp relative error <=4e-6 for normal finite outputs, with subnormal/overflow classifications tested separately; log1p/softplus/SiLU/GELU error <=4e-6*max(1,abs(reference)). These are design targets, not achieved results or a model-quality guarantee. Measure BF16 boundary crossings as well. If the targets cannot be met within the resource budget, revise both the approximation profile and resource report before integrating it.

RoPE tests cover positions 0, 1, 4,095, 32,767 and 262,143, both axes/halves and large-angle range reduction. Compare against the pinned FP32 phase construction, not an accidental higher-precision phase model. Text theta is 10,000,000; the inspected resolved vision default is axial theta 10,000, with 18 unique frequencies per spatial axis. Store rounded constants and test their bits; do not infer frequencies from hidden width.

## 4. Close the FMA throughput and packing gap

The HardFloat FMA module has a combinational arithmetic interface; adding registers only around that module does not automatically create a high-frequency internally pipelined FMA. Its division/sqrt module has a different sequential protocol. The first synthesis experiment must establish the actual configuration's timing, latency, initiation interval, subnormal handling and DSP inference. A pipelined open implementation, an explicitly pipelined adaptation or a lower clock are choices after that evidence. Vendor FMA resource tables remain comparison anchors. [HardFloat interfaces](https://www.jhauser.us/arithmetic/HardFloat-1/doc/HardFloat-Verilog.html).

Define `L_feedback` as the cycles from issuing an FMA until its result can safely be read as that accumulator's next input, including bank read/write and forwarding. If a lane owns only one dot product, its dependent issue rate may be one per `L_feedback` cycles even when independent operations can enter every cycle.

Candidate initial schedule: **8 lanes, 16 independent output-row contexts per lane**, each with an FP32 accumulator. Within a 128-row output group, iterate reduction index k, then context c; all eight lanes process eight different rows at that c using the same x[k]. Every row receives its k terms in ascending order, so increasing contexts does not introduce a partial-sum reduction tree. Keep accumulators across reduction tiles and add bias only at the defined final boundary. The 128 accumulators need **512 bytes**. For saturation require measured `L_feedback <= 16` and initiation interval one; otherwise increase contexts with a revised layout/buffer budget or accept measured stalls. Do not claim a clock just because sufficient contexts exist.

Small projections with only 48 output rows have six useful contexts/lane and will not fill a 16-context schedule without masked work. Track useful versus issued MACs. Other operations, especially one small reduction, have their own independent-work limits. Accumulator banking and read-after-write bypass must be validated under stalls, not only in a no-stall waveform.

Candidate packed GEMV order:

```text
[output_supergroup][reduction_tile][k_in_tile][row_context][lane]
output_supergroup = floor(output_row / 128)
row_context      = floor((output_row % 128) / 8)
lane             = output_row % 8
reduction_tile   = floor(k / 32)
k_in_tile        = k % 32
```

Each 128x32 BF16 tile is **8 KiB**. Two tiles occupy the existing 16-KiB DMA allocation. Each cycle supplies 128 bits of weights; the input scalar is retained/broadcast for context visits. Use separate fill/consume banks or a validated dual-port mapping. Keep embeddings row-major for 10-KiB row reads; do not force embedding lookup through the GEMV packing. Small vectors, convolution kernels, KV and Delta state keep separate layout IDs.

Round matrix N to 128 and K to 32 only in this layout, mask all padded values, and export original dimensions. This candidate adds **75 MiB of text decode weight traffic** from padded 48-row a/b projections: 51.249 GB becomes **51.328 GB/token**, before alignment, metadata or activation spills. This overhead is small here but is not zero. Vision/tiny tensors must be counted separately. A compact-tail layout may reduce it later under a new layout ID. Existing memory-model values remain useful-byte subtotals.

Core memory ABI starts with **128-bit data beats**, 64-byte preferred alignment and bursts up to 4 KiB, split at each 4-KiB boundary. A full 4-KiB request is 256 such beats. Width converters handle board interfaces; neither a descriptor's alignment nor a 64-byte cache line implies a 512-bit physical bus. This supersedes the earlier tentative 64-byte-beat wording.

Credit invariant for each scratch pool:

```text
reserved_inflight_response_bytes + filled_unconsumed_bytes
  + other_live_allocations <= pool_capacity_bytes
```

Four 4-KiB tags are legal only when all 16 KiB is free. With one 8-KiB tile being consumed, at most two more 4-KiB responses can reserve the other half. Separate write credits retain source bytes until the adapter confirms release. No progress proof may assume all read tags remain available while the consumer owns their destinations.

## 5. Addresses, DMA and command ABI

Use **region handle + checked 64-bit offset/extent**, not a host pointer. ABI 1 fixes generation/slot encoding, trusted registration, BOARD_DDR/HOST_DMA/MODEL_BYTES/SIM_MEMORY kinds, permissions, ownership, table schemas, tensor spans and physical alias rejection. Registered addresses are distinct from checkpoint-file offsets and user virtual pointers.

A host virtual pointer, a checkpoint-file offset, a CPU physical address and a PCIe DMA address are distinct objects. The host driver maps buffers, respects its DMA address mask, handles scatter/gather and synchronization, and releases mappings only after positive DMA completion or platform-confirmed fatal isolation; bounded normal drain may fail. The core is not given permission to issue DMA to arbitrary unregistered memory. Use explicit ownership transfer and ordering barriers even with coherent allocations. [Linux DMA mapping guide](https://docs.kernel.org/core-api/dma-api-howto.html).

Initial host-backed route: pinned host transfer chunks -> PCIe DMA -> board DDR staging -> compute. Model bytes can stay in ordinary host RAM/file backing until copied into a bounded registered transfer chunk; do not assume a contiguous pinned 55-GB allocation. Host transport service may supply requested immutable byte ranges and handle completions, but may not compute a network operation. Direct host-to-core streaming is a later separately measured adapter, not an assumed capability of the board target.

The authoritative [ABI 1](abi-v1.md) fixes a little-endian 256-byte command, 64-byte completion, independent control path, region/table/capability layouts and operation field rules. Opcodes0..5 query/register/reset/evaluate/cancel; opcode6 generation is reserved and rejected. Profile0 REF32,1 BF16-P0. Flagbit0 LAB_UNQUALIFIED permits explicitly labelled numerical tests, never memory/capacity bypass. Logits0=last,1=all,2=selected. Generate the shared implementation header from this schema before writing parser/driver; unknown fields reject.

| Byte offset | Field |
|---:|---|
| 0 | Magic u32; ABI major u16; opcode u16 |
| 8 | Flags u32; numerical-profile ID u32 |
| 16 | Command ID u64 |
| 24 | Context ID u64 |
| 32 | Context epoch u64 |
| 40 | Expected committed token count u64; CANCEL uses target numerical command ID |
| 48, 56 | Model-manifest handle u64; layout-manifest handle u64 |
| 64, 72, 80, 88 | Input-table, state, output and workspace region-table handles, each u64 |
| 96 | First causal position u64 |
| 104, 108 | New-token count u32; requested context capacity u32 |
| 112, 116 | Media count u32; logits selection mode u32 |
| 120 | Progress-watchdog budget in core cycles u64; zero means the configured default |
| 128..255 | Reserved; must be zero in ABI 1 |

ABI 1 specifies exact input roles and tensor/media/table records, checked byte spans, immutable descriptor lifetime, backing-page alias rules, capability qualification versus implementation, ID/generation reuse and cancellation acknowledgements. On-core generation is disabled in this version; host-side generation consumes complete core-computed logits.

Capability/status queries and cancellation use an independently serviced control path while a numerical invocation is busy; a cancel request cannot wait behind the invocation it must cancel. Model/context registration and reset require an idle, drained device/context. Cancellation identifies the active command and epoch; stale IDs are rejected. Repeated cancel requests are idempotent and produce one terminal completion for the affected numerical command. A reset while RUNNING must first cancel/drain, not silently discard outstanding transactions.

The **64-byte completion** contains command ID, context ID, epoch and committed token count (four u64); status, failing opcode, layer and flags (four u32); elapsed cycles and valid output bytes (two u64). Status distinguishes bad descriptor/capacity, unsupported profile, arithmetic nonfinite, transport error, timeout, canceled and success. Include a context-valid flag. An output buffer may contain partial bytes after failure, but they are not valid model results.

Before launch, validate checked products/additions, nonzero required extents, dtype/stride alignment, tensor identity, token-ID range, context capacity, region permissions, permitted aliasing, output size, modality counts and current context epoch/committed position. Reject overflow before any DMA or state mutation. Addresses above 4 GiB and tensor spans crossing that boundary are mandatory tests. Double-check at execution time if any descriptor can change; normally descriptors are immutable until completion.

Host fills descriptors, transfers ownership, then rings the doorbell; the core snapshots the command. Completion requires every model output and state write to be visible in its destination domain. An AXI write response or PCIe posted-write submission alone is not a universal cross-domain visibility guarantee; the adapter must define its ordered fence/acknowledgement mechanism. Host reads completion with the driver's acquire/synchronization protocol. IRQ is optional initially; polling and IRQ must observe the same completion semantics.

## 6. State transactions, failure and recovery

Start with a simple explicit state machine:

```text
EMPTY -> INITIALIZING -> READY -> RUNNING -> COMMITTING -> READY
                                  |              |
                                  +--- failure --+-> DRAINING -> INVALID
INVALID -> explicit reset/restore -> INITIALIZING
```

There is **no automatic rollback** in the first design. Delta/conv state may be updated in place. A transport failure, cancel, watchdog expiry or arithmetic failure after mutation invalidates the entire affected context. Keep the last committed count for diagnostics, but do not interpret that count as evidence the corresponding state is still recoverable. Resume only after explicit zero-state initialization or restoration of a complete earlier snapshot. Descriptor rejection before mutation preserves a valid context.

Public completion commits the **whole command**, after all layers, logits and state writes; layer-major chunk barriers do not expose a resumable prefix. Any partial mutation failure invalidates the context. Future snapshot export/import must cover all Delta/conv/KV, valid lengths, modality positions and model/profile/layout identities. Prefix reuse, copy-on-write, paging and multi-sequence eviction remain disabled initially.

Normal cancellation stops new issue and drains under a five-second initial host deadline while retaining ownership. Permanent missing responses, link loss or failed drain cause OFFLINE plus driver-owned quarantine and a host-origin fatal result if no device completion is possible. Epochs cannot cancel posted DMA writes. Release/reuse only after positive transaction completion or OS/platform-confirmed isolation; otherwise keep disabled/quarantined through supported recovery. Full driver teardown/failure tests and positive quiescence evidence are required by the implementation contract.

Use a **progress watchdog**, distinct from maximum legitimate command duration. Count progress at completed DMA beats/operations/state barriers; record the stalled opcode/tag/credits. Under a memory model with finite service bounds, prove a pending command eventually completes or faults. Real hardware timeout values are chosen from measured service behavior and configured workload size, not a guessed 1-ms inference timeout.

Host-side generation bring-up uses greedy argmax, lowest-ID ties, explicit max_new_tokens and EOS **{248046,248044}**; invalid logits fail. ABI 1 implements only evaluation, not on-core generation. Stop after selecting EOS without an unnecessary forward pass. Native defaults enable sampling (temperature1, top-k20, top-p.95); greedy is a declared development policy. [Pinned generation metadata](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/generation_config.json).

The selected next token is not yet represented in KV/Delta state: only tokens actually consumed by a completed forward pass count as committed. The host loop records emitted-token count and pending unconsumed token separately from device completion. A continuing generation loop appends that token exactly once; a stopped/EOS loop must not increment committed length as though another forward pass occurred. Prefix reuse and conversation continuation must honor this distinction.

## 7. Bounded workloads and a real DDR allocation

Native dimensions and the complete graph remain the objective. The first implementation supports one active sequence, no padding in its admitted B=1 input stream, immutable model weights, BF16-P0/REF32 profiles as advertised, and explicit context capacity. Reject unsupported batches, masks, quantization and oversized media before mutation. Unit tests still cover masked/all-masked arithmetic behavior. Do not advertise batch support just because a tensor descriptor has a batch field.

| Stage | Required workload / admission limits |
|---|---|
| Tiny text | Existing four-layer tiny profile, S<=32, 8-token prompt plus resumed decode and reset |
| Tiny VL | Existing two-block tiny vision profile plus complete tiny text; test one and two segments and placeholder mismatch |
| Native text bring-up | All actual dimensions, B=1; first complete pass at S<=32; runtime capacity at most 4,096 until separately expanded; prompt chunks U=1 first, then qualified U=8 |
| Native VL bring-up | First processed image 256x256, repeated temporal pair: N=256, M=64. Then non-square/multiple-image/video fixtures within four temporal segments, each <=256 patches, total <=1,024 raw patches; command prompt <=512 decoder positions including markers |
| Scale qualification | Larger grids, context up to the configured 262,144 and batching require new allocation/performance evidence and capability limits; they are not implied by first-board support |

The old 224x224 example remains correct tensor algebra for pre-normalized input (196 patches), but it is not the default image-processor fixture: the pinned image metadata has a 65,536-pixel lower size setting. Use explicit processor overrides if testing smaller input and record them. Images/videos have checkpoint mean/std `[0.5,0.5,0.5]`; the metadata overrides class defaults. [Pinned preprocessing metadata](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/preprocessor_config.json).

An illustrative **DDR-relative** reservation for S=4,096 is below. It uses no assumed physical base address. The board adapter adds its validated base and rejects extents outside tested memory. The RK target's default 1-GiB mapping must not be treated as tested 2-GiB capacity.

| Region | Start MiB | Size MiB | End MiB, exclusive |
|---|---:|---:|---:|
| Platform/firmware/driver reserve | 0 | 32 | 32 |
| FP32 Delta state | 32 | 144 | 176 |
| BF16 conv ring and alignment | 176 | 4 | 180 |
| BF16 native KV at 4K | 180 | 256 | 436 |
| External operator workspace | 436 | 128 | 564 |
| Weight staging A | 564 | 128 | 692 |
| Weight staging B | 692 | 128 | 820 |
| Descriptors, small constants and tables | 820 | 16 | 836 |

This leaves **188 MiB at 1 GiB or 1,212 MiB at 2 GiB**. It is an allocation proposal, not a proven live-buffer trace. Platform firmware may require a different reserved range. A stage buffer holds chunks of a tensor, not necessarily one whole decoder block. Do not let a whole-tensor API impose a hidden >128-MiB contiguous staging requirement.

External workspace modes are mutually exclusive: text/Delta operation scratch; vision patch/position buffers; vision block attention QKV/residual buffers; vision FFN intermediates; merger/placeholder buffers. At the initial N<=1,024 VL cap, BF16 hidden/QKV/FFN tensors are 2.25/6.75/8.40625 MiB respectively, so 128 MiB is a practical starting envelope, subject to an actual liveness trace. Free pixels after patch projection; free QKV after its last attention consumer; permit in-place elementwise activation only after proving reads complete. Residuals remain live through their add.

Logits must be separately admitted: FP32 transport needs **993,280 bytes per position**, 31,784,960 bytes for 32 positions and **508,559,360 bytes for 512**. The last-position default fits easily. All-position mode must allocate an output extent from remaining DDR or use a credited output stream to host; it cannot silently put 512 vectors in the 128-MiB workspace. A host that stops draining output must cause safe backpressure or timeout, never buffer overwrite.

## 8. Vision and multimodal contract

Host input to the core is normalized **raster** pixels with explicit `[frame,channel,height,width]` BF16 storage, strides, valid frame count and temporal padding description. Host media decoding/resize/rescale/normalization is allowed; learned patch projection, patch gathering, position interpolation, rotary transforms, encoder, merger and decoder insertion stay on-core. The framework processor's already patch-flattened `pixel_values` is a test oracle, not permission to move the required patch gather to the host.

Implement the gather order as `(temporal group, spatial block row, spatial block column, inner row, inner column)`, then flatten each patch in `(channel, temporal-within-patch, pixel row, pixel column)` order. Assert divisibility before applying merge=2. Use coordinate-coded pixels and non-square grids to expose permutations; constant-color images cannot validate ordering.

For each valid grid, attention segments are per temporal patch group, length h_grid*w_grid, with cumulative offsets; do not join unrelated images or temporal groups. Position interpolation uses source coordinate `i*47/max(size-1,1)`, clamped neighboring taps, and the four bilinear weights. A size-one helper axis maps to zero, although a full merge=2 encoder request with an odd spatial grid is rejected. Merger groups the four adjacent entries produced by block-major ordering. These details follow the pinned helpers. [Pinned vision helpers](https://github.com/huggingface/transformers/blob/1a55addd658aaa95b52871f5b72e91a6b91449b6/src/transformers/vision_utils.py).

Video frame sampling, repeated final frames, timestamp formatting and textual markers follow the pinned Qwen3VL processor and video processor. Preserve its selected frame indices and timestamps in fixtures. The inspected decoder groups video grids into temporal entries; timestamps can be represented by text markers. Do not independently multiply rotary temporal indices by seconds unless the pinned helper actually does so. The core position controller must reproduce exact causal and three-axis position arrays plus rope deltas for append/decode. Cached visual features, if later enabled, need content/processor/grid/model/profile identity and may not bypass D8's encoder execution evidence.

## 9. Performance model: include the slowest shared resource

For the candidate padded text layout, let W=51.328 GB/token and M be the memory model's other 4K-context bytes. Under host->DDR->compute staging with no pinned weights:

```text
T_host >= W / host_effective_bandwidth
T_DDR  >= (2*W + M) / shared_DDR_effective_bandwidth
T_core >= core_port_bytes / core_port_effective_bandwidth
T_math >= issued_work / achieved_arithmetic_rate
T_token >= max(T_host, T_DDR, T_core, T_math)  # optimistic overlap floor
```

Use sum-of-service-times only as a deliberately serialized scenario, not a universal upper bound: unknown stalls and other operators can add time. Build a dependency timeline to determine actual overlap. Header/descriptor overhead, padded vision matrices, norm/activation transfers, retries and intermediate spills are not all included in this subtotal.

At hypothetical host service 3 GB/s and DDR service 4 GB/s, staged DDR alone needs **25.876 s/token**, versus **17.109 s** host transfer and **16.014 s** dense math at eight lanes/200 MHz. The memory plan's 6.512-s number assumed a different resident/local single-stream scenario and must not be used for this staging topology. At 100 MHz, dense math alone rises to **32.027 s**.

A 128-bit core port at 100 MHz has a 1.6-GB/s raw per-direction ceiling, irrespective of PCIe link marketing. If its adapter shares one service budget between reads/writes, the modeled core traffic alone needs **32.610 s/token** at that rate; real overhead raises it. Independent AXI read/write channels must still respect shared DDR arbitration. A fast PHY cannot overcome a slower width converter, CDC bridge, queue or scratch port. Record the width, clock and duplex/shared service assumption of every hop.

Do not sum every stage's maximum bandwidth, or give reads and writes each the full shared DDR bandwidth. Report prefill/vision, decode, cold load, reset/restore and simulator wall time separately. The 40–90k LUT estimate remains conditional on the selected arithmetic implementation, controller shell and debug setup; recalculate after actual pipeline and buffer mapping.

## 10. Verification, acceptance and native-run economics

Use this evidence sequence in addition to D0-D9/M0-M6:

1. **Static contracts:** source hashes, exact tensor inventory, byte capacities, checked address products, layouts, command encoding, capability limits, and file/region ownership.
2. **Arithmetic/packing:** primitive special values/subnormals/ties, deterministic coefficients, FMA feedback stalls, pack/unpack round-trip on distinguishable values, masked tails, zero padding and exact source tensor hashes.
3. **Protocol:** randomized read delays and legal reordering, write backpressure, response errors, response after cancel, reset during every phase, descriptor corruption, >4-GiB addresses, undersized output, exhausted credits and non-draining host. No deadlock under a bounded service assumption; no write outside registered writable regions.
4. **Independent module numerics:** all three norms; convolution impulse/kernel direction and cached history; Delta zero/near-zero Q/K and state decay; grouped attention/tails/softmax casts; both GELUs; text/vision RoPE; coordinate-coded image gather and position interpolation.
5. **Whole graph:** tiny text and VL, all intermediate checksums, resumed decode and fresh reset, token-major versus chunks, context fault recovery, first and last layer sentinels, complete logits and all persistent state. Source-based module oracle and RTL-policy oracle both run.
6. **Native checkpoint:** first a short text pass, then multiple decode steps, image and short video; compare all logits, per-layer residuals, KV and recurrent state. The tiny graph cannot satisfy D7/D8. Later long-context claims require actual appropriate scale evidence.

The fixed calibration/holdout token sequences and deterministic image/video recipes are in `qualification-fixtures.json`. Materialize processor-derived inputs and hashes before inspecting RTL results. Compare intermediate tensors, recurrent/KV state, logits and distributions per layer/checkpoint, not only a chosen top token. Include every held-out comparison position in top-1/top-5 denominators; no low-margin filtering. Full fidelity qualification is distinct from the minimum D7/D8 execution proof.

The implementation contract fixes independent **hard fidelity ceilings**: tensor/state NRMSE .01 and coordinate-scaled error .05; logits NRMSE .01/max-absolute .5; distribution KL .002 nats/L1 .02; all-position top-1>=95% and reference-top1-in-top5>=99%, also within text/media subgroups. Calibration may tighten, not enlarge, these ceilings. An inadequate software arithmetic profile must change and be requalified; retain failed results.

Eight lanes require at least **3,202,744,320 dense arithmetic cycles/token** at ideal issue. A simulator sustaining 100,000 cycles/s would spend **8.90 hours per token on that lower bound**; at 1,000,000 cycles/s it is still 53.38 minutes. These are hypothetical simulation rates, not measurements. Representative native matrix/panel runs must measure wall time, cycles, peak resident memory and trace overhead before D7/D8 is scheduled. Disable exhaustive waveforms by default; retain bounded traces around first divergence.

Use compiled simulation when it supports the actual RTL. D8’s first 256-patch image requires **66 decoder positions**, so budgeting one token is invalid. The implementation contract and `refinement-checks.json` separate decoder body/head and full counted vision work; even a hypothetical 1M cycles/s gives a roughly 2.5-day counted floor. Measure representative stages, include a 2x margin and require <=48h/fixture with bounded traces before launching, or improve the simulator/host or defer unchanged D7/D8 proof to qualified actual hardware. Do not replace DUT arithmetic or silently remove required visual tokens.

Host storage admission counts original checkpoint bytes (55.56 GB), packed active copy (~54.71 GB plus layout padding), temporary outputs and frameworks. Keeping original+packed copies already needs over 110 GB decimal before reserve. Stream packing one tensor at a time to avoid a full FP32 copy; a full FP32 active copy alone adds about 109.43 GB. Hash manifests and disk-space checks precede large downloads. Tiny/one-block stages stay possible on much smaller hosts; choose the real full-model strategy from measured available RAM rather than assuming a 32-GB machine can keep everything resident.

## 11. FPGA integration and decision gates

Start with the documented RK-XCKU5P-F V1.2 as a **candidate target**, not a purchased/proven platform. Match the PCB/revision, memory parts, schematic, XDC constraints, power connector/polarity, oscillator, JTAG and PCIe lane wiring. Confirm free device/IP entitlements with the selected tool version. Never borrow constraints just because another board uses the same FPGA. Keep the K325T option conditional on equivalent documentation and working DDR/transport.

Build the board shell independently: clock/reset -> UART/JTAG/status -> DDR calibration/full-range walking/address-pattern tests -> host PCIe enumeration -> DMA known-pattern test -> simultaneous DDR/PCIe traffic -> accelerator connection. Resolve the default 1-GiB versus physical 2-GiB memory mapping before allocating beyond the tested extent. Test transfers above 4 GiB of cumulative model offset even though board RAM is smaller.

Clock-domain contract: document core, DDR user, PCIe user and control clocks and resets. Use proper async FIFOs/handshakes for data/control crossings, synchronize reset deassertion per domain, and preserve outstanding-request drain semantics. Do not blanket-false-path unexplained crossings. Require reviewed CDC/reset reports, no unintended latches, no unconstrained synchronous endpoints, no timing violations at the selected operating clock, and bank/voltage/transceiver constraints matching the board.

Collect hierarchical LUT/FF/DSP/BRAM/URAM use with shell and arithmetic separately, then integrated. Check LUTRAM/BRAM inference, DSP mapping, local congestion, fanout and memory port conflicts. The initial 65% LUT target is headroom, not proof of routeability. Keep counters and compact traces within the free edition's debug limits; do not assume unrestricted ILA/XSIM features.

Record wall-power/rail limits, predicted and observed FPGA power/temperature, cooling, supply stability and DDR/DMA errors during a sustained workload. Accept only operation within the exact board/device ratings with stable timing and data integrity. No wattage, temperature or achievable MHz is asserted before that measurement.

Native Linux is the planned inspected LitePCIe runtime path, but this Snapdragon ARM workstation does not provide a verified compatible PCIe slot or supported x86-64 Vivado host. Confirm compatible build/programming/runtime host access, slot/link, driver, DMA mappings, RAM/storage and added cost before hardware commitment. ABI/bitstream/driver identities must match before DMA enablement; WSL alone supplies neither a physical PCIe link nor vendor-supported ARM programming.

## 12. Concrete next work packets

| Order | Deliverable | Exit condition | Existing gates |
|---|---|---|---|
| 1 | Frozen `numerics`, `layouts`, ABI/capability definitions and independent fixture generator | Dtype trace resolves every boundary; descriptor/layout round-trips; source/dependency manifest complete | Remaining D0, start D1/M0 |
| 2 | One real FP32 lane, casts, nonlinear prototype and SRAM wrappers; target synthesis for KU5P/K325T | Numerical policy passes; actual feedback latency, DSP/BRAM inference and timing reported | D1, M3, resource estimate replacement |
| 3 | Credited memory adapter + deterministic delayed/faulting memory + sequencer/command parser | Ownership, bounds, cancellation and finite-service liveness tests pass | M1/M3 |
| 4 | Eight-lane GEMV/vector/norm and FFN, then Delta/full attention | Native-shape module comparisons; measured utilization/traffic; no hidden software math | D2/D3/M2/M5 |
| 5 | Complete tiny text then vision+text RTL | D4/D5 with memory stalls, reset/resume and independent references | D4/D5/M4 |
| 6 | Native checkpoint execution and frozen holdout quality report | All native text/VL layers actually run; logits/state validated; scope explicitly reported | D6/D7/D8 |
| 7 | Board shell/integration and optimization | Memory/PCIe measurements, routed resources/timing, thermal stability; then evaluate wider lanes/W4/online attention | D9/M6 |

Board-shell investigation can proceed alongside arithmetic qualification, but purchasing is most useful after the target modules and exact board shell synthesize and the host connection is understood. Dates are not promised; advance by exit evidence. Keep failed profiles and abandoned measurements in reports without presenting them as accepted results.

Reproduce the completed planning checks with `python plan_audit_checks.py --out plan-audit-checks.json` beside `memory_model.py` and `reference-sources/`. The source hashes, 836-MiB allocation, 75-MiB padding, output capacities and topology-sensitive timing are checked. No synthesis, driver, numerical RTL or real-model inference was implemented during this audit.
