# Qwen3.8-27B: caching, bandwidth and latency refinement

**Current normative refinement:** [implementation contract](implementation-contract.md) and [ABI 1](abi-v1.md). The [review record](refinement-review.md) tracks independent findings; [checks](refinement-checks.json) are planning evidence, not RTL or hardware qualification.

Updated October 23, 2026. This extends `plan.md` and supersedes its original two-scan Delta state schedule. It is an architecture and measurement plan, with analytical estimates and synthetic software checks. No complete RTL inference, FPGA fit, board bandwidth or checkpoint accuracy is claimed.

The main decisions are explicit scratchpad management, streamed weights, six-query-head reuse of each native KV stream, Delta state panels that are read and written once, and a separate schedule for prefill. The first implementation remains free and simulated. Memory timing must be configurable from the start.

## 1. Workloads and the three different memory problems

Treat capacity, sustained bandwidth and dependent-access latency separately. Enough address space does not imply enough physical memory; enough physical memory does not imply an interactive generation rate.

| Workload | Reuse opportunity | Principal scheduling constraint |
|---|---|---|
| Single-sequence decode | Activation vectors across matrix rows; native KV across six queries; one Delta panel during update | The next token ID is unknown until the preceding token completes |
| Prompt prefill | A weight tile across U known prompt rows; a Delta panel across U successive recurrence steps | Maintain causal attention and exact recurrence order within each sequence |
| Batched independent decode | Same weights across B sequences | KV, convolution and recurrent state scale with B; per-request latency may rise |
| Vision encode | Weights across many patch rows; K/V tiles across query rows | Bidirectional attention is restricted to the actual vision segment |
| Reused prompt/media | Saved prefix state or encoder features | Content, positions, model revision, arithmetic and masks must match |

Measure time to first token, inter-token latency, aggregate tokens/s and peak live bytes separately. A larger batch can improve aggregate throughput while making an individual sequence wait longer. U is a prompt chunk size, B is a count of independent sequences; neither is a license to generate unknown future tokens in parallel.

All estimates below use GB/s = 10^9 bytes/s and GiB/MiB/KiB = binary units. Bandwidth scenarios are assumed **effective payload rates**, not product specifications. Decode uses B=1, BF16 KV, FP32 Delta state, S including the current token, and one output logit vector.

## 2. Memory hierarchy and residency policy

```text
checkpoint on disk -> host RAM / simulation backing store
                          |
                explicit DMA / modeled transport
                          |
             optional board DDR staging + persistent state
                          |
        credit-controlled burst DMA, tagged completion queues
                          |
       banked SRAM scratchpad + local accumulator registers
                          |
              shared numerical execution units
```

Disk is a cold-load tier. Do not rely on demand paging or rereading checkpoint files every token for a performance claim. Simulation may use sparse/file-backed byte storage for functionality, but report host page faults, resident memory and wall-clock simulation throughput independently of modeled accelerator cycles.

| Data | Residency and cache policy | Lifetime / invalidation |
|---|---|---|
| Dense weights | Sequential packed tiles; bypass a general-purpose cache; prefetch upcoming tiles | Immutable model/layout/precision version |
| Normalized GEMV input | Retain the complete input when it fits, broadcast across output lanes | Current operator; invalidate on producer completion |
| Weight DMA tiles | Explicit ping-pong buffers with ready/consumed fences | One or several prompt/batch rows |
| Attention K/V | External native-head storage; current blocks reused across all six corresponding query heads | Per sequence, layer, epoch, position and dtype |
| Delta state | External FP32; retain a full key dimension for a small group of value columns | Read-modify-write panel; never evict dirty state silently |
| Conv history | External per-layer circular ring; cache current channel block | Sequence/layer/epoch; advance only after commit |
| Residuals and intermediates | External ping-pong scratch; alias only after last consumer | Graph liveness, not arbitrary eviction |
| Small weights, tables, descriptors | Pack adjacent accesses; optionally pin selected hot data | Model/profile/context identity |
| Vision features / prefix snapshots | Optional explicit persistent objects | Input digest, grid/timestamps, positions, masks, model and numerical profile |

A conventional LRU cache smaller than a cyclic scan of all weights can have effectively zero inter-token hits. Do not assume its hit rate equals cache-size/model-size. If C bytes of useful weight tensors are explicitly pinned, the best possible external weight saving is C per token; the remaining tensors still stream. Small on-chip SRAM should first prevent repeated input-vector reads and exploit current-tile reuse. An embedding row lookup needs only 10 KiB BF16; caching the whole 2.543-GB embedding table is not a priority for one-token decoding.

KV is semantic model state, not an approximate sliding window. Full-attention positions cannot be evicted because they are old without changing the model. Paged allocation may remove unused capacity and permit prefix sharing; it does not remove the required scan of valid keys/values. Keep hot page/descriptor translations local, preallocate contiguous extents for B=1, and include page walks in traffic if paging is later enabled. Delta state is compressed history: arbitrary old prefixes cannot be recovered from the latest matrix. Reusable prefix checkpoints must include all Delta matrices, conv rings, KV valid lengths and positional metadata; branch reuse needs copy-on-write or independent ownership of mutable state.

## 3. Exact traffic accounting and quantitative limits

The verified text inventory has 26,895,998,464 elements. It includes an embedding table of 248,320 x 5,120. A decode token reads only one row of that table, while reading the untied output head and every decoder weight. Thus the ideal BF16 weight stream is:

`2 * (26,895,998,464 - 248,320*5,120 + 5,120) = 51,249,210,368 bytes/token`.

This is smaller than total resident weights, but still about 51.25 GB. It assumes each required weight is fetched once; re-reading tiles, padding, metadata or cache thrashing can increase it. Vision weights are used for media encoding, not reread for each later text decode token.

The following hypothetical quantized profiles pack **all text 2D matrices, including embedding/head**, with symmetric group size 128 and one BF16 scale per row/group. Other text weights and all vision weights remain BF16. The model counts row rounding and scales. It does not assume W4 accuracy, packed arithmetic throughput, or that any current quantizer is acceptable. W4 previously failed the synthetic FFN quality gate; these are memory sensitivities only.

| Text weight format | Text + BF16 vision capacity, GB | Decode weight reads, GB/token |
|---|---|---|
| 16 bit | 54.713 | 51.249 |
| 8 bit | 28.240 | 26.028 |
| 4 bit | 14.794 | 13.217 |

For the revised reference schedule, define `Ckv = 65,536*S` bytes across the 16 full-attention layers. Per generated token the modeled subtotal is:

`weight reads + 2*144 MiB Delta matrix traffic + 2*3.75 MiB conv-ring traffic + 2*Ckv attention reads + 65,536-byte KV append + 993,280-byte FP32 logits write`.

The conv term is a conservative read/write of the complete four-slot ring; a three-history-read plus one-slot-write circular implementation can reduce it after verification. Input embedding bytes are already in weight reads. Current K/V forwarding may save a small read; the table conservatively includes the appended row in the scan. All-position prefill logits have a different output volume.

| Weights | Context S | Modeled traffic, GB/token | At 2 GB/s, s/token | At 8 GB/s | At 16 GB/s | At 32 GB/s |
|---|---|---|---|---|---|---|
| 16 bit | 4,096 | 52.097 | 26.048 | 6.512 | 3.256 | 1.628 |
| 16 bit | 32,768 | 55.855 | 27.928 | 6.982 | 3.491 | 1.745 |
| 16 bit | 262,144 | 85.920 | 42.960 | 10.740 | 5.370 | 2.685 |
| 8 bit | 4,096 | 26.875 | 13.438 | 3.359 | 1.680 | 0.840 |
| 8 bit | 32,768 | 30.633 | 15.317 | 3.829 | 1.915 | 0.957 |
| 8 bit | 262,144 | 60.698 | 30.349 | 7.587 | 3.794 | 1.897 |
| 4 bit | 4,096 | 14.064 | 7.032 | 1.758 | 0.879 | 0.440 |
| 4 bit | 32,768 | 17.822 | 8.911 | 2.228 | 1.114 | 0.557 |
| 4 bit | 262,144 | 47.887 | 23.944 | 5.986 | 2.993 | 1.496 |

These are **memory-only lower-bound times for the listed traffic on one effective shared memory service**. They omit activation spills, transport padding/metadata, initialization and latency bubbles. They are not end-to-end throughput predictions. Never add a fresh efficiency penalty to an already measured effective bandwidth unless it represents an additional unmodeled effect.

Compute can impose a much larger limit. Dense projections plus LM head require 25,621,954,560 MACs per decode token. At an assumed 200 MHz with one accepted MAC per lane per cycle, they take at least 128.11 s with one lane, 16.01 s with eight lanes, 2.00 s with 64 lanes, or 0.500 s with 256 lanes. These exclude attention, recurrence, norms/nonlinear work and stalls. FP pipeline feedback may prevent one MAC/cycle without multiple independent accumulators. Quantized storage does not automatically accelerate an FP32 compute engine.

Use a per-operator bound `t >= max(compute_work/sustained_compute, bytes/effective_bandwidth)` only when transfer and execution actually overlap. Sum operator critical paths, add exposed setup/fence delays, and account for shared resources. For an unoverlapped operator, transfer and execution times add. A global max is an optimistic lower bound, not an execution schedule.

For a throughput goal r tokens/s, the listed traffic alone demands at least `r * bytes_per_token` sustained bytes/s. At S=4,096, 1 token/s requires about 52.10 GB/s for the BF16 reference schedule or 14.06 GB/s for the unqualified W4 scenario. The dense arithmetic alone requires about 25.62 billion MAC/s for either storage format unless the arithmetic implementation itself changes. This makes target throughput a concrete design input rather than an assumption derived from LUT count.

For reference attention, MACs for its three QK passes plus one AV pass are `16*24*256*S*4`, in addition to projections. At S=262,144 that is about 103.08 billion MACs/token. Long context can become compute-limited even after memory reuse. Dense BF16 decode has roughly one FLOP per weight byte; ideal reuse across U prompt rows raises this toward U FLOP/byte before activation traffic.

Resident capacity is a separate calculation. The table includes active text/vision weights, FP32 Delta state, BF16 conv rings and BF16 KV for one sequence; scratch, allocation reserve, packed padding and extra sequences still need room.

| Weights | S | Known capacity floor, GiB |
|---|---|---|
| 16 bit | 4,096 | 51.350 |
| 16 bit | 32,768 | 53.100 |
| 16 bit | 262,144 | 67.100 |
| 8 bit | 4,096 | 26.695 |
| 8 bit | 32,768 | 28.445 |
| 8 bit | 262,144 | 42.445 |
| 4 bit | 4,096 | 14.172 |
| 4 bit | 32,768 | 15.922 |
| 4 bit | 262,144 | 29.922 |

A nominal 16-GiB configuration has virtually no spare space at the hypothetical W4/32K point. Native context at BF16 exceeds 64 GiB before workspace. Reduce text-only capacity by the 921,460,192-byte vision weights if the workload permits loading them separately; do not subtract them from a simultaneous full-model residency claim.

## 4. DeltaNet: retain column panels, not the whole head

The earlier two-state-read schedule costs 432 MiB/token. It is unnecessary: columns of a state head are independent until the later output normalization. Keep all 128 key rows for C=16 value columns locally. That panel is `128*16*4 = 8 KiB`; two DMA panels need 16 KiB. A full 64-KiB head need not reside locally.

For each head and value-column panel J:

1. Read `S[:,J]` once; retain q, k, decay and the relevant v values.
2. Apply the decay locally. Reduce all 128 keys to obtain `prediction[J]`.
3. Compute `delta[J] = beta*(v[J]-prediction[J])`.
4. Update the same local panel with `k outer delta[J]`; reduce q against the **updated** values to obtain `y[J]`.
5. Write the updated panel once and retain/spill its output columns. After all panels, perform the full 128-wide gated norm.

All recurrence equations and required reductions are preserved. External state traffic becomes **288 MiB/token**, a one-third reduction from the prior schedule. Within SRAM the panel is still accessed multiple times; those port cycles and arithmetic costs remain. Avoid changing FMA/cast/reduction order without numerical qualification.

Pack state physically as `[layer][sequence][head][value_panel][key][value_lane]`, retaining the logical `[key,value]` contract. With C=16, each panel is contiguous 8 KiB, split into legal bursts. A naive narrow panel sliced out of row-major storage creates 128 scattered 64-byte reads. The exporter/state initializer and inverse unpacker must agree on this permutation, including tails for other profiles.

For prompt chunks, the recurrence can retain the same panel while processing U known tokens in chronological order, then write it once. Matrix traffic per prompt token approaches `288 MiB/U`, **provided** all q/k/v/decay/beta inputs for that layer/chunk are available and outputs are spilled for later full-head normalization. No subsequent decoder layer may consume partial head output. This is not cross-token speculation, and it cannot eliminate sequential dependencies during autoregressive single-sequence decode.

The new synthetic probe tested 128x128 state with panel widths 1, 8, 16, 31 and 128, and chunk sizes 1, 4 and 9. It checked output/final-state agreement and exactly one read/write per panel per chunk. Maximum output difference was 8.94e-8 in FP32. This supports the scheduling transformation; it does not validate full pretrained numerics or RTL.

## 5. Attention: share native KV reads and retain numerical choices

There are four KV heads and 24 query heads. Process the six query heads belonging to one KV head together. A loaded key or value block is reused for all six, even if a single arithmetic lane handles them sequentially. Store six independent maxima, denominators and output accumulators; do not combine their softmax distributions.

| Decode attention schedule | External KV read bytes across all layers | Probability handling |
|---|---:|---|
| Prior ungrouped, three passes per query | `12*Ckv` | Three QK scans plus one V scan, repeated six times |
| Revised reference: grouped three-pass | `2*Ckv` | Preserve global max, denominator, BF16 probability cast, then AV |
| Optional grouped two-pass | `1.5*Ckv` | Online max/denominator first; second QK pass forms cast probabilities and AV |
| Optional grouped one-pass online attention | `Ckv` | Online output rescaling; different finite-precision/cast contract |

At 4,096 context the reference KV read traffic falls from 3 GiB to 512 MiB/token. At maximum context it falls from 192 GiB to 32 GiB. One-pass online would read 16 GiB at that maximum. None of these factors includes query projections or compute reuse across heads: the six query dot products still differ and must all be calculated.

The new probe reused three-pass KV reads across six heads at D=256 with a non-tile-aligned S=37, including a BF16 probability cast. Outputs were identical to independent-head calculation; read bytes fell exactly sixfold. Native multi-layer correctness, causal masks and RTL burst traces remain tests.

Keep grouped three-pass attention as the first correctness schedule. Online attention carries running maximum m, exponential sum l and unnormalized output o; a new block rescales old l/o by `exp(m_old-m_new)` before adding the new terms. It avoids a full score matrix, following the IO-aware tiling principle in [FlashAttention](https://arxiv.org/abs/2205.14135). Our small-FPGA layouts and byte estimates here are derived design choices. A mathematically exact attention algorithm need not be bit-equivalent to the pinned implementation: one-pass attention cannot reproduce a BF16 cast of each fully normalized probability before AV without another pass or saved scores. Assign it a distinct numerical profile and validate logits/state quality.

Saving scores is another optional trade: six FP32 score rows cost `24*S` bytes per group, or 96 KiB at S=4,096. External score write plus two rereads costs `72*S` bytes/group but can replace repeated K scans. Compare this against available SRAM, local bandwidth and extra storage traffic; do not silently introduce an S-squared buffer. For prefill, bounded query tiles introduce an additional query-row dimension in the live working set and attention traffic.

Suggested native KV layout is `[layer][sequence][KV_head][position_block][position_lane][D]`, separate K and V planes. Eight positions at D=256 BF16 make a 4-KiB block. Tail positions are masked by valid length. Current-token writes may be small; stage/merge them carefully without inventing nonexistent future rows. Page sizes, block tables and alignment are storage decisions; temporal order and causal visibility remain semantic requirements.

## 6. Scratchpad capacity, bandwidth and layout

Use explicit scratchpad modes. The following is a **logical 64-KiB payload budget**, not measured FPGA BRAM consumption. Modes reuse the same storage at different times; they are not simultaneous reservations. FIFOs counted here must not also be hidden inside a DMA block without accounting.

| SRAM use | GEMV mode | Grouped decode attention | Delta decode mode |
|---|---:|---:|---:|
| Resident input / queries / scalar controls | 36 KiB | 6 KiB queries + 4 KiB scores/stats | 4 KiB q/k/v/control |
| DMA tiles or panels | 16 KiB | 16 KiB K/V ping-pong | 16 KiB state ping-pong |
| Accumulators / output | 4 KiB | 6 KiB AV accumulators | 4 KiB output/norm workspace |
| Descriptor / completion / control payload | 4 KiB | 4 KiB | 4 KiB |
| Unassigned allowance | 4 KiB | 28 KiB | 36 KiB |
| Total | 64 KiB | 64 KiB | 64 KiB |

GEMV's largest text BF16 input is the 17,408-element FFN down input: 34 KiB. A separate residual remains external. Retaining this vector eliminates external rereads for each eight-output group. Without input retention, eight-output tiling adds approximately dense BF16 weight bytes / 8, or **6.41 GB of input reads/token** across projections. Norm parameters and other workspaces have separate phases; document their lifetimes before aliasing this allocation.

The 64-KiB budget assumes source-defined BF16 activation boundaries. A diagnostic all-FP32 17,408-wide input needs 68 KiB by itself; choose a larger scratch profile or explicitly count tiling/spills. Never truncate a vector to preserve the budget. Provide optional 128-KiB and 512-KiB profiles for more transport buffering and prompt tiles, subject to actual device mapping. Constant ROMs, arithmetic internal storage, CDC FIFOs, ECC, RAM width/depth rounding and bank replication all belong in the physical total.

For eight BF16 weight lanes at 200 MHz, the local weight banks must deliver 16 bytes/cycle, or 3.2 GB/s, plus broadcast activation, accumulator and DMA refill traffic. A single RAM port cannot simultaneously supply arbitrary lanes and incoming bursts. Bank by output lane, pack reduction coordinates contiguously, separate read/write phases or ports, and use true dual-port behavior only where supported. State updates need multiple local reads and writes per panel. If bank conflicts, FP recurrence hazards or nonlinear pipelines stall, lower the sustained compute estimate accordingly.

Offline weight packing should use output groups and contiguous reduction tiles, with complete precision groups and adjacent scales. A logical 8x32 BF16 arithmetic tile is 512 bytes; DMA should coalesce consecutive tiles into aligned larger bursts where possible. Wider load buses do not require wider arithmetic. Vision tails such as width 72 and FFN 4,304 need padding/masks, and the traffic model must count transferred padding rather than only useful elements.

## 7. Hiding latency: burst DMA, credits and prefetch

Distinguish first-byte latency L from payload time P/B, queueing latency, full-burst completion, and write acknowledgement. For one outstanding request the ideal bandwidth is `P/(L+P/B)`. With Q requests and independent responses, an optimistic bound is `min(B, Q*P/(L+P/B))`. To keep a serial response bus busy when slots release on the last beat, provision roughly `ceil(1+B*L/P)` slots, plus practical margin; `B*L` alone is only the bandwidth-delay product.

For an 8-GB/s response bus, the included ideal finite-stream model gives:

| Payload | First-byte delay | Outstanding | Simulated GB/s | Reserved response bytes |
|---|---|---|---|---|
| 64 | 500 ns | 1 | 0.126 | 64 |
| 4096 | 500 ns | 1 | 4.047 | 4,096 |
| 4096 | 500 ns | 2 | 7.998 | 8,192 |
| 4096 | 2000 ns | 1 | 1.631 | 4,096 |
| 4096 | 2000 ns | 4 | 6.518 | 16,384 |
| 4096 | 2000 ns | 8 | 7.992 | 32,768 |

This model has fixed latency, unlimited issue capacity and a serialized response bus. It excludes DDR bank/row effects, refresh, host overhead and computation. The figures demonstrate sensitivity, not hardware performance. At 2 us, five 4-KiB request slots suffice in this ideal model; eight give headroom but need 32 KiB of reserved destination capacity. A 16-KiB DMA bank budget cannot magically accept 32 KiB of responses. Buffers already holding unconsumed data reduce available credits further.

Initial custom RTL target, refined by the gap audit: parameterized **128-bit data beats**, preferred 64-byte alignment, up-to-4-KiB bursts, four read tags, separately credited writes, and safe backpressure. A 4-KiB burst is 256 such beats and is split at 4-KiB address boundaries. These are design parameters, not a board requirement. Benchmark burst payloads 64/512/1,024/4,096 bytes and depths 1/2/4/8/16. Increase queue depth only alongside actual response/FIFO capacity. A 128-bit port at 100 MHz provides at most 1.6 GB/s per direction before overhead. At 200 MHz a 256-bit bus has a 6.4-GB/s raw ceiling; an 8-GB/s scenario requires a wider/faster/multi-channel service and is not implied by either bus.

The DMA needs independent request, response and completion handling; tensor tags and offsets; alignment/tail masks; read-after-write dependency fences; and fair service for mutable-state writes. Responses may reorder across permitted IDs, but must land in the correct tile and obey ordering rules within an ID. Never require a response to complete before issuing the next independent read. Never announce operation completion before all state writes are acknowledged and visible. Cancellation stops new issue and retains mappings during bounded drain. Fatal loss uses OFFLINE/quarantine until positive DMA quiescence; an epoch cannot stop an already issued host write.

Burst lengths and 4-KiB boundaries must obey AXI rules. AMD documents the relationship among burst sizing, outstanding requests and buffering in its [burst-control guide](https://docs.amd.com/r/en-US/ug1399-vitis-hls/Options-for-Controlling-AXI4-Burst-Behavior). These protocol concepts apply to the proposed custom SystemVerilog DMA; adopting HLS is not required.

Prefetch distance must cover latency plus transfer time at the consumer's actual pace. For a tile with compute time tc, request at least `ceil((L+P/B)/tc)` tiles ahead when capacity and dependencies allow. Fetch only immutable weights or already-produced inputs. For bank-switched buffers, wait for both DMA completion and prior-consumer release. Sustained overlap is not proved by allocating two buffers: record fill, compute and drain timelines and credit stalls.

Read/write channels may be logically separate while sharing one DDR data bus. Model turnaround and arbitration; do not assign full measured read-only bandwidth independently to simultaneous reads and writes. With multiple memory channels, map weights and mutable state to channels deliberately and report each channel's traffic/occupancy. DDR row locality, bank conflicts, refresh, controller limits, IOMMU/page faults and transport retries are sources of exposed latency; numerical scenarios here assume none of those has been measured yet.

## 8. Host-backed weights and board DDR staging

For a small-memory FPGA, host-backed execution can satisfy the functional boundary: the host supplies bytes, all inference math remains on core. A memory interface alone does not make that path practical. Record installed DDR capacity, usable bytes after controller/runtime reservation, DMA transport, driver support, address limits and measured directional throughput for any candidate board.

Let W be weight bytes consumed per token, C explicitly pinned useful weight bytes, M local non-weight traffic, and Hlink effective host-to-device bandwidth. If missing weights are staged through the same board DDR that serves compute:

- Host transfer bytes are at least `W-C` per token.
- Board DDR sees `(W-C)` staging writes plus `W` weight reads plus M.
- Even with ideal overlap, `t >= max((W-C)/Hlink, (2*W-C+M)/Bddr, compute_time)`.

For BF16, C=0, S=4,096, the modeled weight/state/KV subtotal gives **about 103.35 GB of board-DDR traffic/token**, versus 52.10 GB when weights are already resident. A direct host-to-SRAM stream can avoid the staging write/read pair, but needs its own supported transport, buffering and arbitration; apply the correct topology rather than the staging equation. PCIe/USB/Ethernet label rates are not end-to-end payload rates. Host RAM bandwidth is also shared with DMA writes/reads and other work.

Large host DMA slabs can amortize driver/request overhead and be subdivided into legal AXI bursts at the core. Slabs consume board DDR or host buffers, not free SRAM. Pin immutable regions only after allocating sequence state and working space. A software-managed ring of upcoming weights improves overlap but is not an inter-token weight cache if it is overwritten before reuse. At single-sequence decode, cross-token layer reordering is blocked by the next-token dependency.

Cold load has a separate duration `checkpoint_bytes / loading_bandwidth`, plus conversion/packing. Prefill, generation, context switches and cold start must have separate reported timing. Include RAM pressure on the development computer; a 54.7-GB BF16 active model plus copies, framework reference and 16-GiB KV can exceed available host RAM even if a behavioral memory API permits 64-bit addressing.

## 9. Prefill, batching and vision scheduling

Keep token-major execution as the golden control path. Add layer-major prompt chunks U=8, then 16, with U=1 as fallback. For each layer: retain/stream its input rows, project a tile across U rows, perform the correct mixer, complete residuals/FFN, then publish all chunk rows to the next layer. Delta convolution and recurrence remain chronological; attention masks include only the valid preceding prefix and current causal chunk positions.

In the ideal matrix schedule, each weight tile serves U rows before eviction, reducing dense weight traffic per prompt token by roughly U. This is not an end-to-end U-fold speedup: attention, normalization, intermediate writes and local capacity impose other limits. All-position logits can share head tiles across U rows; last-position-only prompt logits instead run the head once after the required final hidden row is ready. Record which mode is timed.

Input retention is the critical capacity trade. U=16 BF16 hidden rows occupy 160 KiB, while U=16 FFN down-input rows occupy 544 KiB. They do not fit a 64-KiB scratchpad, and the latter alone exceeds 512 KiB. A loop order that rereads input tiles for every eight-output group can retain approximately the same **6.41-GB per-token activation-read penalty** even when weights are reused. Use larger row tiles only where they fit, choose U separately per operator, improve output-tile width or count the spills explicitly. Candidate 512-KiB mode can reserve 272 KiB for U=8 FFN input and space for tiles/accumulators, but needs a complete liveness and physical mapping report.

For Delta chunks, panel-resident recurrence saves state reads/writes, but its q/k/v streams and partial y rows add scratch traffic. For attention, group query rows and the six query heads only to the extent that accumulators fit. Do not assume one global KV read for all prompt queries; explicitly count how often a KV tile is reloaded for each query tile.

Without reuse across different query positions, grouped three-pass attention for T new prompt tokens after an existing prefix S0 reads `2*65,536*(T*S0 + T*(T+1)/2)` KV bytes across the full-attention layers. This excludes append writes and projections. It exposes the quadratic prefill cost that a decode-only table hides; query tiling/online attention may lower IO but still needs its own numerical and capacity accounting. Every independent sequence also contributes its own `144 MiB + 3.75 MiB + 65,536*S` persistent bytes. Batch weight reuse reduces average weight bytes per output across requests; it does not divide any sequence's state capacity by B.

Vision should already run layer-major. Reuse projection weights across patches, retain bounded K/V blocks across a query tile, and spill complete hidden/QKV tensors to external scratch. There is no sixfold GQA opportunity: vision has 16 Q and 16 KV heads. A 196-patch example has 451,584 bytes per BF16 hidden buffer and 1,354,752 bytes of QKV, before FFN and attention workspace. Segment length controls quadratic attention work; bound actual image/video grids, number of items and per-segment allocations. BF16 position interpolation tables, patch gather strides, merger grouping and both GELU variants retain their existing semantics.

Cache the merged media features for repeated use of unchanged media within a compatible request; do not rerun the 27 vision blocks on every text decode token. Reusing an existing decoder prefix additionally requires matching causal and mRoPE positions. Feature caching and prefix caching are distinct objects with different invalidation conditions.

## 10. Measurement and verification gates

The plan adds a memory gate alongside D0/D1, before performance promises. These are future implementation tasks; the present deliverables only include the analytical model and two software scheduling checks.

| Gate | Required evidence |
|---|---|
| M0: analytical ledger | Per-operator useful/read/write/padded bytes; peak-live buffers; exact format/stride; complete tier topology. Initial subtotal model is supplied; activation/padding trace is still required |
| M1: deterministic memory model | Configurable first-byte delay, beat rate, outstanding limit, read/write sharing, backpressure, response ordering and errors; finite response queues |
| M2: schedule equivalence | Reference vs grouped attention, column-panel and chunked Delta, token-major vs layer-major graph; actual native numerical comparisons remain necessary |
| M3: SRAM and DMA trace | Every live allocation and port use, no overcommit; no premature overwrite; aligned bursts/tails; measured outstanding depth and stall causes |
| M4: whole-graph timed simulation | D4/D5 tiny graphs with zero-latency, constrained-bandwidth and long-latency models; equal results and reconciled byte counts |
| M5: native traffic/runtime sample | Representative native GEMV, Delta and short-context attention; measured simulator cycles/wall time; extrapolation labels and error bars |
| M6: target feasibility | Real controller/transport bandwidth, latency distribution, simultaneous read/write tests, resource and timing reports; only then a deployment performance claim |

Sweep S={32,4,096,32,768,262,144} analytically; use short S and bounded samples in costly RTL tests. Sweep U={1,8,16}, Qoutstanding={1,2,4,8,16}, payload={64,512,1,024,4,096}, first-byte delay={100,500,2,000 ns}, and effective service={2,8,16,32 GB/s} as independent hypothetical knobs. Convert time to cycles using the actual simulated clock. Include variable delay, refresh pauses, mixed read/write pressure, row/bank penalties, partial final bursts and deliberate slow consumers; use a fixed random seed for reproducibility.

Collect useful bytes versus wire bytes separately for weights/scales/activations/KV/Delta/conv/logits/page tables; per-tier and per-channel reads/writes; p50/p95/p99 first-byte and completion latency; burst-size histogram; outstanding occupancy; scratch high-water marks; load/compute/store overlap; cache hit rate by data class; compute-utilization and cycles lost to credits, ports, dependencies or memory. End-to-end simulation wall time is not modeled accelerator time.

Protocol checks must include delayed write acknowledgements, reordered read IDs, read-after-append, reset with transactions outstanding, chunk tails, sequence switches, dirty-state eviction, page faults and memory errors. Preserve zero-initial-state semantics. A failed partial token/chunk invalidates the context or restores a prior complete snapshot; it must never be resumed as committed. Measure initialization/restore traffic separately. On real hardware, test read-only, write-only and simultaneous traffic; AMD's [memory-test documentation](https://xilinx.github.io/xbtest/doc/main/user-guide/build/html/docs/test-cases/memory-test-case-description.html) provides an example of controlling burst size and outstanding requests and measuring their effect.

## 11. Implementation decisions and reproducibility

Proceed in this order: freeze physical layouts and SRAM liveness -> build the finite-bandwidth/latency memory harness -> implement credited burst DMA and counters -> qualify grouped three-pass attention and column-panel Delta -> add complete tiny-graph timed tests -> introduce prompt chunks -> evaluate quantized weights and online attention under separate quality gates -> measure an actual board/transport before choosing deployment hardware.

Keep D7 and D8 from the full plan: all 64 native decoder blocks and, for multimodal input, all 27 vision blocks must actually execute on core with checkpoint weights. A fast memory benchmark or a passing synthetic panel test does not replace those gates.

Reproduce the arithmetic with `python memory_model.py --out memory-model-results.json` (standard library only). It generates format capacities, decode subtotals, bandwidth-only times, dense-compute bounds and the ideal burst-latency sweep. `memory_schedule_probe.py` and `memory-schedule-probe.json` use NumPy for the synthetic state/head-reuse tests. These files are saved alongside the project planning evidence. The frozen config SHA-256 is `191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab`; dimensions and counts come from the existing independently audited checkpoint ledger. Model outputs remain estimates until M1-M6 produce traces and measurements.

## 12. Gap audit decisions that complete the memory contract

The [plan gap audit](plan-gap-audit.md), sections 4-9, supplies the missing physical/transport contracts. Its candidate eight-lane schedule keeps 16 independent output rows per lane to hide measured FMA feedback latency, rather than assuming a dependent accumulation can issue every cycle. Two packed 128x32 BF16 tiles occupy 16 KiB; 128 FP32 accumulators occupy 512 bytes. This layout adds **75 MiB/token** of padded native text weights, separately checked in `plan-audit-checks.json`. The earlier model remains a useful-byte subtotal, not a padded bus trace.

DMA credits include both in-flight reserved responses and filled/unconsumed data. With one 8-KiB tile retained by compute, only the other 8 KiB is available for two 4-KiB requests. The nominal four-tag count does not permit overwriting occupied destinations. Host pointers and model-file offsets are translated through registered region handles; bounded pinned host chunks feed board DDR staging. Direct host streaming is not assumed.

The proposed 4K-context DDR map reserves **836 MiB**, including state, 128 MiB workspace, two 128-MiB staging windows and platform/constants reserves. It leaves 188 MiB at 1 GiB or 1,212 MiB at 2 GiB, contingent on a tested address map and actual liveness. Full logits for 512 prompt positions require **508,559,360 bytes** in FP32 transport, so output extent/stream admission is separate from the 128-MiB workspace. Default last-position output avoids this allocation.

For padded BF16 decode with hypothetical 3-GB/s host service and 4-GB/s shared DDR service, staging imposes **25.876 s/token** for DDR alone. The independent 128-bit/100-MHz core port may impose another 1.6-GB/s service ceiling; widths, clocks and duplex assumptions must be recorded per hop. Use the maximum resource service time only as an optimistic overlap floor, then validate the dependency timeline. These hypothetical bounds are not board measurements.

BF16-P0 now fixes score/scale, probability, Delta beta/gated-norm/logit casts and operation order in the implementation contract. The old synthetic probe remains schedule/traffic evidence only. A failed partial command invalidates context immediately; normal drain is bounded, while fatal loss quarantines mappings until positive quiescence. Full-prompt `[T,4]` positional plans and proposed rope delta remain immutable across U1/U8 chunks; only whole-command completion commits them. Fresh-media append to nonempty context is rejected. Snapshot/prefix sharing stay disabled.
