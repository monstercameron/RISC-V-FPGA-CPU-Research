# Qwen3.8-27B: calculations and accelerator requirements

Engineering analysis | October 23, 2026

## 1. What the hardware actually has to do

Inference is repeated evaluation of a numerical network. Most work is weighted dot products: multiply input numbers by learned weights, add the products, then apply normalization and nonlinear functions. A general-purpose CPU instruction set is unnecessary for the central datapath; the useful FPGA building blocks are tiled multiply-accumulate engines, buffers, DMA, reductions, and nonlinear-function units.

For Qwen3.8-27B, the decoder's large projections require approximately **25.62 billion multiply-accumulates per generated token**, or **51.24 GFLOP-equivalent** if one multiply plus one addition counts as two operations. Full-attention work then grows with context length. These are analytical counts, not measured speed or energy; quantized integer operations are not literally floating-point operations.

The immediate practical bottleneck for batch-one generation is likely weight movement. Nominal 27B weights occupy 13.5 GB even at ideal 4-bit packing, before quantization metadata, recurrent state, attention cache, or runtime workspace. A cheap FPGA can explore useful kernels, but a complete model requires a credible external-memory capacity and bandwidth plan.

Scope: text inference first, one sequence, ordinary one-token decoding, no speculative decoding. Vision, training, and multi-token prediction are described separately. No model weights were downloaded and no model performance benchmark was run.

## 2. Verified architecture and calculation basis

The official model card calls this a dense vision-language model. The downloaded configuration uses the Qwen3.5 implementation family; that internal architecture identifier is compatible with the Qwen3.8 model name. The text stack has 64 layers arranged as 16 groups of three Gated DeltaNet layers and one gated full-attention layer. [1, 2]

| Quantity | Configured value |
|---|---|
| Hidden width H | 5,120 |
| FFN intermediate width I | 17,408 |
| Layer types | 48 linear/recurrent; 16 full attention |
| Full attention | 24 query heads; 4 KV heads; head width 256 |
| DeltaNet | 16 Q/K heads; 48 value heads; head widths 128 |
| Local depthwise convolution | Kernel length 4 |
| Vocabulary V | 248,320; input/output embeddings untied |
| Native configured context | 262,144 tokens |

The model card describes context extension beyond the native configuration, but extended serving limits do not establish affordable memory or latency. The estimates below use explicit context sizes. The source implementation was inspected to establish projection widths and gate behavior; it is a moving upstream reference, not a pinned executable environment. [2, 3]

## 3. One token through the network

**Embedding.** Tokenization happens before the network. A token ID selects a row of a V-by-H embedding table, producing 5,120 numbers. This is a lookup, not a full matrix multiplication. Position information is applied inside attention.

**Normalization and residuals.** RMS normalization computes x / sqrt(mean(x*x) + epsilon), then scales by a learned vector. Residual connections add a block's output to its input. Hardware needs sums of squares, reciprocal square root, vector multiplication, and addition. Q/K normalization and DeltaNet normalization add further reductions.

**Feed-forward network in every layer.** Compute u = x W_up; g = x W_gate; y = (SiLU(g) elementwise-multiplied by u) W_down. SiLU(x) = x / (1 + exp(-x)). This means two H-to-I projections and one I-to-H projection, plus gating. Each layer uses 3HI = 267,386,880 MACs. Across 64 layers this is 17.113 billion MACs/token, approximately 66.8% of the counted projection work.

**Full attention in 16 layers.** Project to queries, keys, values, and an output gate. The implementation's Q projection has twice the query width because it emits both queries and gate values. Apply normalization and rotary position encoding, compute scores Q K-transpose / sqrt(256), apply a causal mask and stable softmax, then multiply by V. Apply the output gate and project back to H. Grouped-query attention shares four KV heads among 24 query heads; it reduces stored KV, not the number of query heads whose scores are computed.

**DeltaNet in 48 layers.** Project Q/K/V and gate/control values; run a short depthwise convolution and activation. Each value head maintains a 128-by-128 recurrent state. A schematic decode recurrence is: decay S; predict v_hat = k-transpose S; form delta = beta*(v-v_hat); update S = S + k outer-product delta; read y = q-transpose S. The implementation also normalizes Q/K and applies output normalization/gating. This is a decayed, content-dependent memory update, not conventional softmax attention. Prompt processing can use a chunked equivalent rather than a serial loop. [3]

**Output and sampling.** Final normalization feeds a 5,120-to-248,320 output projection. Sampling applies temperature/filtering and selects the next token. Greedy decoding can use argmax without materializing a normalized probability vector. Repeat the decode pass for every generated token, including reasoning tokens.

## 4. Reproducible arithmetic budget

For x W, with W of shape input-by-output, MACs/token = input width times output width. The following counts include large text projections and the full-vocabulary output head. They exclude embedding lookup, vision, MTP, normalization, activations, attention score/value products, convolution, and recurrent updates.

| Component | MACs per layer or output | Count | Total GMAC/token |
|---|---|---|---|
| FFN: 3 x 5120 x 17408 | 267,386,880 | 64 | 17.113 |
| Delta projections: 5120 x (10240+6144+96+6144) | 115,834,880 | 48 | 5.560 |
| Full-attention projections: 5120 x (12288+1024+1024+6144) | 104,857,600 | 16 | 1.678 |
| Output head: 5120 x 248320 | 1,271,398,400 | 1 | 1.271 |
| Total | | | **25.622** |

Delta widths: QKV = 2*(16*128) + 48*128 = 10,240; output gate = 6,144; two per-head controls = 96; output projection input = 6,144. Full attention: doubled Q/gate width = 12,288; K and V = 1,024 each; output projection input = 6,144.

For one generated token attending to S positions, score and weighted-value products add approximately 4*16*24*256*S FLOPs. That is 1.61 GFLOPs at S=4,096; 12.88 at 32,768; 51.54 at 131,072; and 103.08 at 262,144. Add these to the 51.24 GFLOP-equivalent projection budget. Softmax and other vector operations are additional. A literal scalar implementation of recurrent state decay, prediction, update, and readout adds roughly 0.26 GFLOPs/token, excluding projections and other gates.

Prefill differs from decode: T prompt tokens use matrix-matrix operations, permitting weight reuse. Projection work is approximately 51.24*T GFLOPs if logits are computed at every position. At T=4,096 that is about 210 TFLOPs; computing logits only at the final prompt position saves about 10.41 TFLOPs. Ideal causal full-attention products add 2*16*24*256*T*(T+1) FLOPs, about 3.30 TFLOPs at that prompt length. Actual kernels may execute extra masked work. These counts do not predict wall-clock time.

## 5. Memory: weights, cache, and recurrent state

Nominal weight storage uses P=27 billion and P*bits/8 bytes. GB is decimal; GiB is binary. This table is a coarse sizing convention, not an exact checkpoint-file size or a verified allocation total.

| Weight format | Ideal bytes | Binary size |
|---|---|---|
| BF16 / FP16 | 54.0 GB | 50.29 GiB |
| INT8 | 27.0 GB | 25.15 GiB |
| INT4 | 13.5 GB | 12.57 GiB |

Quantization adds scales, possibly zero points, alignment/padding, and tensors retained at higher precision. For scale only, a two-byte scale per 128 four-bit weights adds 3.125% to those packed weights. Exact deployed storage depends on which tensors are quantized and on the runtime. Four-bit weights do not imply four-bit activations, cache, state, or accumulators.

With BF16/FP16 KV entries, full-attention cache bytes per sequence = 16 layers * 2 (K,V) * 4 KV heads * 256 values/head * S * 2 bytes = 65,536*S. Store the four native KV heads; do not physically duplicate them for all 24 query heads.

| Cached sequence length | Full-attention KV cache |
|---|---|
| 4,096 | 0.25 GiB |
| 32,768 | 2 GiB |
| 131,072 | 8 GiB |
| 262,144 | 16 GiB |

DeltaNet does not need an S-length KV cache in recurrent decoding. Its matrix state is 48 layers * 48 value heads * 128 * 128 = 37,748,736 values, or **144 MiB at FP32**. The configuration specifies FP32 state. A four-slot convolution buffer over 10,240 channels for each linear layer adds approximately 3.75 MiB at two bytes/value; runtime layout can differ. State and KV scale with the number of concurrent sequences, while weights can be shared.

An ideal 4-bit 27B weight payload plus a 32K BF16 KV cache and FP32 recurrent state already totals approximately **14.71 GiB**, before quantization overhead and workspace. At 262K context that subtotal is approximately **28.71 GiB**. A 16 GiB device is therefore not a comfortable general-purpose 32K deployment assumption. Actual feasibility requires a measured runtime allocation.

## 6. Bandwidth and FPGA feasibility

If every weight is streamed once per batch-one decode token, bandwidth required = weight bytes/token * tokens/second. Using the nominal ideal INT4 payload of 13.5 GB, 1 token/s requires 13.5 GB/s; 5 tokens/s requires 67.5 GB/s; 10 requires 135 GB/s. This is an illustrative whole-weight-stream model: embedding lookup avoids streaming that input table, vision can be inactive for text, and active projection weights differ from the nominal parameter total. Conversely, metadata and inefficient traffic increase bytes moved.

Under that simplified model, sustained weight bandwidth of 25 / 50 / 100 GB/s caps generation at approximately 1.85 / 3.70 / 7.41 tokens/s, before compute, cache, recurrent-state, and scheduling costs. Use sustained useful bandwidth rather than advertised peak bandwidth. At long context, KV reads become a major additional term. Off-chip FP32 recurrent-state read plus write is approximately 288 MiB per token if each state is transferred once each way.

At short context, 10 tokens/s requires about 0.512 TFLOP-equivalent/s just for projections; 30 requires about 1.537. Quantized hardware should be sized in native MAC/s with realistic precision, utilization, and memory stalls. For example, 256 independent one-MAC-per-cycle lanes at 200 MHz provide 51.2 GMAC/s peak, an arithmetic-only upper bound of approximately 2 tokens/s for the counted projections. This assumes every lane stays occupied; it is not a prediction for any particular FPGA or DSP configuration.

Many boards previously discussed have only tens or hundreds of megabytes of external RAM. Even a board advertised with 16 Gb DDR4 has 2 GB, not 16 GB. Such a board cannot hold the complete nominal INT4 weights locally; it would need host streaming, a larger memory system, partitioning, or a much smaller model. More LUTs do not resolve this capacity limit.

## 7. A sensible accelerator exploration plan

1. Start with a text-only numerical reference and record tensor shapes and precision. Test one block before attempting the full network.
2. Simulate a tiled matrix-vector MAC engine with a chosen quantization scheme, explicit scales, saturation rules, and accumulator widths. Compare against floating-point outputs and set an error tolerance.
3. Implement and test a complete FFN block. Its three projections dominate the counted work, so it is the best first accelerator target.
4. Add reductions and nonlinear units: RMSNorm, SiLU/sigmoid, exp/softplus where required, and stable softmax. LUT or polynomial approximations need error tests over realistic ranges.
5. Implement one DeltaNet state update, then one grouped-query attention block with a bounded cache. Validate multiple-token sequences, not only a single step; recurrence can accumulate numerical error.
6. Build a memory-traffic simulator covering weights, KV, state, metadata, and transfers. Estimate capacity, sustained bandwidth, and tokens/s for proposed boards before buying.
7. Only after kernel correctness and bandwidth estimates, select FPGA hardware and measure synthesis resources, timing, and achievable memory utilization.

Do not begin by writing a CPU. Start with a small dot-product engine and an FFN workload representative of this model. Full Qwen inference is a longer-term system goal; useful kernel simulation is achievable without owning an FPGA or loading the full checkpoint.

## 8. Vision, MTP, and training boundaries

Image/video inference adds patch embedding, a vision transformer, spatial merging, and projection into the language width. Vision cost depends on resolution, frames, and processor tokenization; there is no single defensible per-image FLOP count without those inputs. The config has a 27-layer vision encoder with width 1,152 and FFN width 4,304. Vision tokens also consume decoder context. The text decode counts above exclude the encoder.

The config contains an auxiliary MTP layer. Speculative use can change work per accepted token and requires an acceptance/verification analysis; no speedup is assumed here. Training adds backpropagation, gradients, optimizer state, saved activations, and communication. Its memory and compute requirements cannot be inferred from the inference tables alone.

## Sources and reproducibility

[1] Official model card: https://huggingface.co/Qwen/Qwen3.8-27B

[2] Official checkpoint configuration: https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/config.json

[3] Hugging Face implementation: https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen3_5/modeling_qwen3_5.py

All accessed October 23, 2026. Configuration and implementation snapshots are saved with this project. Calculated quantities are analytical estimates derived from the listed dimensions. The companion calculation script reproduces the principal numbers without downloading weights or requiring a GPU. The source URLs use moving branches; repeat analysis if a configuration changes.
