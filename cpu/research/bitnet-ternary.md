# BitNet / ternary-weight inference on our RV64 core: maps, ISA gaps, a benchmark and a plan

Research agent report, 2026-11-22 01:33-01:55 EST (times from `date`). Repository read-only except
`build/research/` (ignored). Baseline: main at `c607485` (architecture 0.17.0), with the RVV subset as
proposed in `build/cpu/fp/RVV-CONTRACT.md` (golden models only, no RVV RTL yet). No model weights were
downloaded; only papers, code pages and Hugging Face metadata (file sizes, config, licence) were read.
Prototypes are in `build/research/bitnet/` (original MIT code; nothing copied from bitnet.cpp or llama.cpp).

**How to read this.** **Fact** = taken from a named source (URL and commit). **Measured** = from a run in
this session (section 8 lists the runs). **Judgement** = my estimate or recommendation.

## 0. Answer in brief

* "Maps" in this field means four things, and they stack:
  1. the **operation map**: multiply becomes add, subtract or skip;
  2. the **weight-encoding map**: trits to 2-bit codes (I2_S, TQ2_0), base-3 bytes (TQ1_0) or group indices
     (TL1, TL2);
  3. the **lookup-table map** (T-MAC, TL1/TL2): a packed group of weights indexes a table of precomputed
     activation sums;
  4. the **SIMD map**: unpacking with shifts and masks, then a dot-product instruction (MAD kernels) or a
     byte-permute table lookup (LUT kernels).

  **Judgement:** in the papers, the distinctive reading is the lookup-table map. T-MAC and bitnet.cpp's TL
  kernels are what the "1-bit AI infra" literature sells. In shipped practice, however, the MAD kernel
  (I2_S, 2 bits per weight plus an int8 dot product) is the default and is as fast or faster where dot-product
  instructions exist (section 2.4).
* On our SoC, **decode is memory-bound by a wide margin**. Each data miss fetches one 8-byte beat, and only
  `N_MISS` misses are in flight. Little's law then caps DRAM streaming at about **0.52 B/clk** at the
  deciding configuration. That is about **1.8 tokens/s** at 4 GHz for BitNet b1.58 2B4T as bitnet.cpp ships
  it (I2_S plus an F16 head, 1.18 GB/token), or **2.6 tokens/s** with TQ1_0/TL2 weights and a Q8_0 head
  (Judgement, section 5).
  * Scalar code already computes faster than that (Measured: about 1.1 instructions per weight).
  * The lever for decode is memory-level parallelism: more misses in flight, 64-byte L1 fills, prefetch.
    New instructions are not the lever.
* For prefill, batched decode or L2-resident models, the vector path needs these additions to the RVV
  subset, in this order (Judgement):
  1. integer ALU on every vector pipe;
  2. widening integer MACs, `vwmacc*` (1.8x fewer vector slots than the subset);
  3. Zvqdotq `vqdot*` (2.5x; **not ratified**, draft v0.0.2).

## 1. The model's compute (official sources)

### 1.1 BitNet b1.58 and BitNet b1.58 2B4T

Facts:
* **Weights and activations** ([2B4T report, arXiv 2504.12285](https://arxiv.org/abs/2504.12285)):
  * weights are ternary {-1, 0, +1}, quantized with **absmean**;
  * activations are **8-bit absmax per token** ("W1.58A8");
  * the model has no bias terms, uses SubLN, RoPE and a squared-ReLU FFN, and the LLaMA 3 tokenizer (vocabulary
    128,256);
  * non-embedding memory is **0.4 GB**;
  * CPU decoding takes **29 ms/token**: bitnet.cpp, 8 threads, i7-13800H;
  * energy is **0.028 J/token**, which the report labels as estimated.
* **Configuration** ([HF config, model sha `04c3b9ad`, MIT](https://huggingface.co/microsoft/bitnet-b1.58-2B-4T)):
  * hidden size 2560, 30 layers, 20 heads, 5 KV heads (head dimension 128), FFN 6912;
  * `hidden_act relu2`, `rope_theta` 500000, `rms_norm_eps` 1e-5;
  * **tied embeddings**, context 4096, stored in BF16.
* **Forward graph** ([transformers `modular_bitnet.py`](https://github.com/huggingface/transformers/blob/main/src/transformers/models/bitnet/modular_bitnet.py)):
  * the MLP is gated: `down(ffn_sub_norm(act(gate(x)) * up(x)))`;
  * attention is Llama attention with `attn_sub_norm` applied before `o_proj`.
* The original b1.58 paper ([arXiv 2402.17764](https://arxiv.org/abs/2402.17764)) frames the matmul as
  integer additions. I did not re-read it this session; the 2B4T report restates the same scheme.

Derived (Judgement; arithmetic from the config):
* **Ternary weights:** 69,468,160 per layer and 2,084,044,800 in all. Per layer that is q and o (2560x2560
  each), k and v (2560x640 each), and gate, up and down (2560x6912 each).
* **Embedding:** 328,335,360 parameters, shared with the LM head. The head must read all of it for every
  token.
* **The published gguf** ([`ggml-model-i2_s.gguf`](https://huggingface.co/microsoft/bitnet-b1.58-2B-4T-gguf),
  size from HF metadata) is 1,187,801,280 bytes.
  * That matches 521.0 MB of I2_S weights (2 bpw) plus 656.7 MB of embedding at 16 bits.
  * So in the shipped format, **the LM head is the larger half of the bytes read per token**.

**Arithmetic.** Ternary MAC = add (w = +1), subtract (w = -1) or skip (w = 0).

| Implementation | How the multiply disappears |
|---|---|
| MAD kernels | Keep a real multiply or dot product on 2-bit codes, which is cheaper than unpacking to masks |
| LUT kernels | Precompute the sums of activation groups and replace per-weight work with one lookup per group |
| Bit-serial (popcount) | `sum_i c_i * (cpop(A_i & P) - cpop(A_i & N))` over the 8 two's-complement activation planes A_i, with weight masks P (+1) and N (-1), c_i = 2^i and c_7 = -128 |

The bit-serial form was measured here (section 3.1).

**Accumulators.**
* Facts and derivation:
  * |a| <= 127 and |w| <= 1, so a K = 6912 dot product reaches at most 877,824. That needs **int32**
    (21 bits), just as the accelerator plan's bound in `ffn-demo-plan.md` section 7.1 shows int32 is enough.
  * int16 partial sums are safe for at most 258 products.
* I2_S (Fact, code below): AVX2 `maddubs` pairs go into int16 and are widened to int32 with
  `madd_epi16(ones)` every 32 blocks.
* TL1/TL2 (Fact, arXiv 2502.11880): the `_1` variants keep the table and sums at int16 and are lossless;
  the `_0` variants quantize the table to int8 and are lossy. WikiText2 perplexity is 11.29 for `_1` against
  11.30 for `_0`.
* My prototypes widen every 64 blocks (64 x 4 x 127 = 32,512) and are exact.

**Output scale.**
* The float output is `acc_int32 * (gamma_w * absmax_a / 127)`.
* I2_S stores **one float per tensor** after the packed data (Fact). TQ2_0 and TQ1_0 store an fp16 scale per
  256 weights, which is redundant for BitNet.

**Other layers per token** (Judgement, from the config).
* Normalisation and activation:
  * 4 RMSNorms per layer: input, post-attention, `attn_sub_norm`, `ffn_sub_norm`;
  * 4 activation absmax quantizations, one per BitLinear input group;
  * ReLU² times up over 6912 elements;
  * RoPE over 2560 + 640 elements.
* Attention at context L: 30 x 20 x 128 x 2 x L = 153,600 x L MACs, which is 157M at L = 1024.
  * The KV cache costs 76,800 B per position at FP16: 78.6 MB/token at L = 1024, 315 MB at L = 4096.
  * Neither the report nor `modular_bitnet.py` states the KV precision. bitnet.cpp inherits llama.cpp's
    cache, F16 by default; I did not verify which type it selects.
* LM head: 328M MACs per token, done in FP16, Q8 or Q6 depending on the export.

**Arithmetic intensity** (Judgement).
* Decode GEMV at 2 bpw: 2 ops per 0.25 B = **8 ops/B** for the ternary part. FP16 GEMV is about 1 op/B.
* The whole 2B4T token with the F16 head comes to about 4 ops/B.
* Prefill over N tokens reuses each weight N times: about 8N ops/B for the projections.
* LUT kernels amortize table construction over the M rows and re-index per token. Vec-LUT
  ([arXiv 2512.06443](https://arxiv.org/abs/2512.06443), MobiSys 2026,
  [vlut.cpp](https://github.com/OpenBitSys/vlut.cpp), MIT) builds one table across N tokens for prefill.
  It reports up to 4.2x over baselines; the devices are not named on the abstract page.

### 1.2 bitnet.cpp: I2_S, TL1, TL2

Source: [github.com/microsoft/BitNet](https://github.com/microsoft/BitNet), commit `0b341e582afb`
(2026-07-27). Facts from its README:
* 2B4T supports **I2_S on x86 and Arm, TL2 on x86 and TL1 on Arm**.
* Speedups are 1.37-5.07x on Arm and 2.37-6.17x on x86.
* A 100B model runs at 5-7 tokens/s on one CPU; the README names no CPU.
* "Parallel kernels" (2026-01-15) add 1.15-2.1x.
* **RISC-V is not mentioned.**

**I2_S** (Fact, [`src/ggml-bitnet-mad.cpp`](https://github.com/microsoft/BitNet/blob/main/src/ggml-bitnet-mad.cpp)):
* Codes: -1 -> 0, 0 -> 1, +1 -> 2 (2 bits). The scale is a per-tensor absmax float stored after the data.
* **x86 layout**: blocks of 128 weights in 32 bytes. Byte k holds weights k, 32+k, 64+k and 96+k in bit
  pairs 7-6, 5-4, 3-2 and 1-0. Arm uses 64-weight blocks in 16 bytes.
* **AVX2 kernel**:
  * `_mm256_srli_epi16` by 2, 4 or 6, then `_mm256_and_si256` with 0x03;
  * `_mm256_maddubs_epi16` (unsigned code times signed activation, adjacent pairs to int16), then
    `_mm256_add_epi16`;
  * every 32 blocks, `_mm256_madd_epi16(ones)` widens to int32.
  * The functions compute sum(code x a). I did not locate where the -sum(a) correction and the scales are
    applied.
* **NEON kernel**: `vdotq_s32` when `__ARM_FEATURE_DOTPROD`, otherwise `vmlal_s8` into int16, then
  `vmovl` and `vaddlvq`.

**TL1 and TL2** (Fact, [arXiv 2502.11880](https://arxiv.org/abs/2502.11880) and the BitNet generators
`utils/codegen_tl1.py`, `utils/codegen_tl2.py`):
* **TL1**: g = 2 weights per 4-bit index (2 bpw). The table holds the 9 sums (+-a0 +-a1, 0) built per pair of
  activations, as int16 split into low-byte and high-byte 16-byte tables. Lookups use **`vqtbl1q_s8`**, the
  halves are re-zipped, and sums accumulate in int16 before widening to int32.
* **TL2**: g = 3 weights as **1 sign bit plus a 4-bit index** (5 bits per 3 weights = 1.67 bpw).
  * Mirror consolidation stores the half of the 27 sums with a non-negative leading term, so 16 entries
    suffice.
  * Lookups use **`_mm256_shuffle_epi8`** (pshufb) with the 128-bit table broadcast to both lanes.
  * The int16 value is rebuilt from the byte tables with `unpacklo/hi_epi8`.
  * The sign is applied branch-free: shift the sign bit to the top, `srai` to make a mask, then add and XOR.
  * Leftover K (when K is not a multiple of BK) goes through the TL1-like 2-weight path.

Facts from the paper:
* Table 7 (tokens/s):
  * 100B model on i7-13700H: TL2_0 1.69, I2_S 1.65, TQ1_0 1.48, T-MAC 0.73, Q4_0 0.67;
  * 100B on Apple M2 (Ultra): TL2_0 7.45, I2_S 6.50, T-MAC 6.45;
  * 3.8B on M2: I2_S 91.65, TL2_0 92.12.
* I2_S reaches up to 6.25x over FP16.
* Appendix (element-wise LUT): a 128-bit table limits g to 3 or less.

Fact ([1-bit AI Infra, arXiv 2410.16144](https://arxiv.org/abs/2410.16144), Table 5, 2 threads, tokens/s):

| Model | i7-13700H, llama.cpp FP16 | i7-13700H, bitnet.cpp | M2, llama.cpp FP16 | M2, bitnet.cpp |
|---|---|---|---|---|
| 3.8B | 3.49 | 20.51 | 11.88 | 26.75 |
| 700M | 18.56 | 80.13 | | |

### 1.3 T-MAC

Fact ([arXiv 2407.00088](https://arxiv.org/abs/2407.00088); [repo](https://github.com/microsoft/T-MAC) commit
`7042f8f73330`, 2025-06-03):
* **Method**:
  * bit-serial decomposition `A x W = sum 2^i A x W_i` over 1-bit weight planes;
  * g = 4 activations per 16-entry subset-sum table;
  * mirror consolidation plus int8 table quantization, which cuts table storage to a quarter;
  * the table lives in a register: Arm `vqtbl1q_u8`, x86 `_mm256_shuffle_epi8`;
  * weights are permuted and interleaved offline so unpacking needs no shuffles;
  * scales are applied after the lookups.
* **Results**:
  * BitNet b1.58 3B: **30 tokens/s single core, 71 on 8 cores** (M2 Ultra); **11 tokens/s** on Raspberry
    Pi 5;
  * up to 6.6x kernel speedup over llama.cpp (3.6x average);
  * Llama-2-7B-2bit: Surface Laptop 7 (12 Oryon cores) 31.83 against llama.cpp 9.39 tokens/s.

### 1.4 llama.cpp TQ1_0 and TQ2_0, and RISC-V ports

Fact ([PR #8151](https://github.com/ggml-org/llama.cpp/pull/8151), merged 2024-09-06 as `9bc6db2`;
[`ggml-common.h`](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-common.h); the
[packing post](https://compilade.net/blog/ternary-packing)):
* **TQ2_0**: 66 B per 256 weights = **2.0625 bpw**. 2-bit codes {0, 1, 2} for {-1, 0, 1}, 4 per byte, and an
  fp16 scale.
* **TQ1_0**: 54 B per 256 = **1.6875 bpw**. 48 bytes hold 5 trits each, 4 bytes hold 4 trits each, plus an
  fp16 scale.
  * Each byte stores the base-3 number b (0-242) as the fixed-point fraction q = ceil(b x 256/243).
  * A trit is extracted with `x *= 3; d = x >> 8; x &= 255`, most significant first, about 3 integer ops
    per trit.
* **vec_dot throughput** (PR, GB/s of float32-equivalent weights):
  * Core m3-8100Y AVX2: TQ2_0 141.83, TQ1_0 70.31, Q4_K 64.17, F16 30.60;
  * AWS t4g with DOTPROD: TQ2_0 65.76, TQ1_0 40.44.

Fact (RISC-V): llama.cpp main `8a97fa98ab1a` (2026-11-22),
[`ggml/src/ggml-cpu/arch/riscv/quants.c`](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/arch/riscv/quants.c):
* **RVV kernels** `ggml_vec_dot_tq1_0_q8_K_vl128/256/512` and `tq2_0_q8_K_vl128/256` exist. The file was last
  changed 2026-06-04.
* The TQ2_0 VLEN-256 kernel, per 128 weights:
  * 1 `vle8` of weights and 4 `vle8` of activations;
  * 3 `vand` plus 3 `vsrl` to unpack, then 4 `vsub` of 1;
  * **4 `vwmacc.vv` (e8 to e16)**;
  * **`vwredsum`** to int32 plus `vmv.x.s` per 32-byte chunk.
* The TQ1_0 kernels use `vmul` by powers of 3 at e8 (wrapping), then **`vwmulu.vx` by 3** and `vsrl` 8,
  `vwcvt` and `vsub`.

**Every one of these uses widening ops outside our contract.** No RISC-V port of bitnet.cpp or T-MAC was
found. T-SAR ([arXiv 2511.13676](https://arxiv.org/abs/2511.13676)) builds tables in registers on AVX2 and
says RVV would need only parameter changes; that is a claim, not a demonstration.

## 2. Kernel maps in detail

### 2.1 Weight encodings

| Encoding | Bits/weight | Unit | Map | Used by |
|---|---|---|---|---|
| I2_S | 2 (+ one float per tensor) | 4 trits/byte, interleaved across a 128-weight block (x86) or 64 (Arm) | code = w+1; dot(code, a) - sum(a) | bitnet.cpp default |
| TQ2_0 | 2.0625 | 4 trits/byte, 256-weight block + fp16 | code = w+1 | llama.cpp |
| TQ1_0 | 1.6875 | 5 trits/byte as ceil(b x 256/243) | multiply-by-3 digit extraction | llama.cpp |
| TL1 | 2 | 4-bit index per 2 weights (9 used) | index into a 16-entry table of pair sums | bitnet.cpp Arm |
| TL2 | 1.67 | 1 sign + 4-bit index per 3 weights | mirrored 16-entry table, sign applied after lookup | bitnet.cpp x86 |
| T-MAC planes | 2 (ternary as 2 planes) | 1 bit per plane, 4 per index | 16-entry subset sums, shift-add over planes | T-MAC |
| Ideal | log2 3 = 1.585 | | | |

### 2.2 SIMD maps (Fact, sources above)

| Kernel | x86 | Arm | Ops per weight (Judgement, from the instruction lists) |
|---|---|---|---|
| I2_S | srli/and unpack, **pmaddubsw**, padd w, pmaddwd(ones) widen | shl/shr unpack, **SDOT** (`vdotq_s32`) or `vmlal_s8` | about 4 unpack + 1 dot per 32 (AVX2) or 16 (NEON) weights, so 0.1-0.3 |
| TL1/TL2 | **pshufb** on broadcast table halves, unpack lo/hi, add/xor sign | **TBL** (`vqtbl1q_s8`), zip, add | 2 lookups + 2-3 combine per 16-32 lanes x g weights |
| T-MAC | pshufb | TBL | per plane: 1 lookup per 4 weights x 16 lanes |
| TQ1_0 | mul-by-3 unpack, then maddubs | same, then sdot | about 3 per trit to unpack |

**Fact, performance with hardware:** see the tables in 1.2-1.4. T-MAC on BitNet 3B reaches 30 tokens/s on one
M2 Ultra core. bitnet.cpp's 2B4T runs at 29 ms/token on 8 threads of an i7-13800H.

## 3. Mapping to RISC-V and our core

### 3.1 Prototypes (Measured)

`build/research/bitnet/tgemv.c` computes y = W a exactly in int32, using the 2B4T layer shapes. Projections
that share an input are merged: QKV is 3840x2560, o is 2560x2560, gate+up is 13824x2560 and down is
2560x6912, for 69.5M weights per layer. Weights are uniform random trits and activations int8 in
[-127, 127], from a hash. Every kernel matched the int8 reference and the native FNV checksums exactly
(0 mismatches) at every size and VLEN.

Instruction counts come from the RVV golden ISS (`build/cpu/fp/bin/rv_iss_fp`, `--vector 1 --vlen N`,
subset only). They are counts, not clocks.

| Kernel (ours) | Map | Bits/weight | **Instructions/weight**, 2B4T layer shapes | Small shapes (SIZESET 1) |
|---|---|---|---|---|
| `i2` scalar | I2_S codes, `mul` per weight | 2 | 5.50 | 5.53 |
| `tmac4` scalar | 2 bit planes, 16-entry subset table per 4 activations | 2 | 3.26 | 3.29 |
| `lut5` scalar | **TQ1_0 bytes used directly as indices into a 256-entry int16 table per 5 activations** (32 KiB tiles) | 1.6 (+ padding to 320) | 1.50 | 2.71 |
| `lut5w` scalar | same, with 8 index bytes per `ld` | 1.6 | **1.13** | 2.30 |
| `bs8` scalar | bit-serial popcount (Zbb `cpop`), 8 activation planes | 2 | **1.08** | 1.30 |
| `vmad` RVV subset | I2_S interleave with VLENB in place of 32; 2-bit two's complement (`vsll`+`vsra`), `vmul` e8, `vsext.vf2`, `vadd` e16, fold to e32 | 2 | 0.648 / **0.328** / 0.167 at VLEN 128/256/512 | 0.657 / 0.337 / 0.177 |
| `vlut` RVV subset | TL1: rows in lanes, 4-bit index per 2 weights, `vzext`, **`vrgather.vv` e16** on 16-entry tables | 2 | **0.286** / 0.145 at VLEN 256/512 (needs VLEN >= 256) | 0.342 / 0.200 |

Notes and conclusions:
* At VLEN 256, `vmad`'s layout is exactly bitnet.cpp's x86 I2_S interleave. Only the code map differs: two's
  complement instead of w+1.
* The `lut5` "map" is an idea from this session. As far as I found, neither bitnet.cpp nor llama.cpp does
  this: they unpack TQ1_0 and then use a MAD kernel.
  * It uses the TQ1_0 byte as a table index with no decoding. Each lookup consumes 5 weights for one load
    and three ALU ops.
  * Table construction is 243 entries per 5 activations per token. That is why small M costs more
    (2.3-2.7 instructions/weight).
  * Merging projections that share an input (QKV, gate+up) amortizes the table.
* Natively on this laptop (Measured, single thread, Snapdragon X2 Elite at about 3.8 GHz by a dependent-add
  chain, clang 18.1.3, cache-warm repeats of one layer):

  | Kernel | Weights/clk | Gweights/s |
  |---|---|---|
  | `ndot` (NEON SDOT I2_S-like) | **19-22** | 74-86 |
  | `lut5w` | 5.0-6.7 | |
  | `lut5` | 4.6-6.1 | |
  | `bs8` | 3.5-4.0 | |
  | `tmac4` | 1.7-2.0 | |
  | `i2`, scalar | about 1.0 | |
  | `i2`, auto-vectorized | 3.7-3.9 | |

* A scalar estimate for our core (Judgement): `lut5w` or `bs8` at about 1.1 instructions/weight and a
  sustained IPC of 6-8 gives **about 5-7 weights/clk**. The ALUs bind first, not the 4 load ports.

### 3.2 Scalar rv64imb plus F/D

* Shifts, masks and adds alone (the `i2` decode with a multiply) cost about 5.5 instructions/weight.
* The table forms (`lut5w`) and Zbb `cpop` (`bs8`) are about 5x better.
* `andn` saves little here, because `bs8` needs `B & P` and `B & N` separately (2 `and`, 2 `cpop`, 1 `sub` and
  1 `sh1add` per plane per 64 weights). Binary (+-1) weights would need one `xnor`+`cpop` per plane instead.
* The cost of `bs8` is the activation-plane transpose: once per token, about 8 x 64 bit-extract steps per
  64 activations, amortized over M rows.
* F/D are used only for norms, softmax, RoPE and scales. They are about 10% of the operations at L = 1024
  and are not on the weight path.

### 3.3 RVV mapping

| Need | Standard RVV | In our subset? | Cost without it (measured or estimated) |
|---|---|---|---|
| Table lookup (TL, T-MAC) | `vrgather.vv` (e8 or e16) | **yes** | none; the permute pipe count limits it |
| Tables of 256 or more entries | `vrgatherei16`, or `vluxei16` indexed loads | vrgatherei16 **no**; indexed loads yes | `lut5` stays scalar |
| Widening MAC | `vwmacc(u/su/us).vv/vx`, `vwmul`, `vwadd(.wv)` | **no** | `vmul` + `vsext.vf2` + `vadd`: 27 instead of 15 vector slots per 128 weights at DLEN 256 (1.8x) |
| Widening reduction | `vwredsum(u)` | **no** | `vsext` + `vredsum` at e32 (small; once per row) |
| Quad dot product | **Zvqdotq** `vqdot/vqdotu/vqdotsu.vv/vx`, `vqdotus.vx`: an e32 accumulator += a 4 x int8 dot per element | **no**, and **not ratified** | 11 slots per 128 weights instead of 27 (2.5x) |
| Mask add/subtract | `vmseq` + masked `vadd`/`vsub`, or `vmerge` | yes | worse than `vmul` e8 by sign (more ops) |
| Reduce | `vredsum` | yes | |
| Narrowing for activation quantization | `vnsrl`, `vnclip`, `vfncvt.x.f.w` | **no** (fixed point is also storage-only) | `vfcvt.x.f.v` e32, `vse32`, then `vlse8` with stride 4 to take the low bytes; per token only, negligible |

Facts:
* **Zvqdotq status**: [riscv/riscv-dot-product](https://github.com/riscv/riscv-dot-product), commit
  `813cba14c9f0` (2026-03-10), `header.adoc` says **v0.0.2, 14 March 2025**, docgroup SiFive.
* Semantics: SEW 32 only, with four 8-bit values per 32-bit bundle accumulating into the same-index 32-bit
  element. Future SEW 16 (4-bit) and SEW 64 (16-bit) variants are noted.
* LLVM treats it as experimental ("not ratified yet"), and QEMU had a v5 patch series in January 2026.
* It is **not part of RVA23**. Widening integer MACs **are** part of mandatory V.

Judgement, slot counts per 128 weights at VLEN = DLEN = 256 for the MAD map:

| ISA level | Vector slots | Weights/clk with 3 pipes | With integer ops on VP2 only (current backend plan) |
|---|---|---|---|
| Subset | 27 | 14 | **4.7**: no better than scalar |
| + `vwmacc` | 15 | 26 | |
| + `vqdot` | 11 | 35 | |

The TL1 map (`vlut`) needs 14 slots plus 6 loads per 128 weights and 2 `vrgather`s per 64 weights on the
permute pipe. Integer ALU on all vector pipes (the RPCS3 report's top item) is therefore a requirement for
this workload too.

### 3.4 Throughput against our memory model

SoC parameters: architecture.md section 3, at the deciding configuration of DEVLOG 22:52 and 00:54.
* 8-byte beats per data miss, L2 line 64 B, `N_MISS` 4;
* L2 4 MiB / 20 clocks, `MEM_LAT` 350, `MEM_GAP` 8.

Fact: the L1 fills one beat per miss, and each split read holds one entry until its answer arrives.

Judgement, using Little's law:
* **DRAM streaming bound**: each 64-B line costs about 350 + 7 x 20 = 490 entry-clocks, so
  4 x 64 / 490 = **0.52 B/clk** (2.1 GB/s at 4 GHz). `N_MISS` 8 gives 1.04 B/clk.
* `MEM_GAP` 8 alone would allow 8 B/clk (32 GB/s), but only with about 350 beats (44 lines) in flight.
* **L2-resident bound**: 4 x 8 / 20 = 1.6 B/clk.
* Unmeasured on RTL, and the architecture's own optimism list makes the real value lower, not higher.

Tokens/s at 4 GHz for 2B4T decode at short context (KV traffic excluded):

| Bytes/token | Format | 0.52 B/clk (`N_MISS` 4) | 1.04 (`N_MISS` 8) | 8 B/clk (`MEM_GAP` 8 saturated) | Compute needed at 8 B/clk |
|---|---|---|---|---|---|
| 1.178 GB | I2_S + F16 head (shipped gguf) | **1.8** | 3.5 | 27 | 32 weights/clk |
| 0.789 GB | TQ1_0/TL2 + Q8_0 head | 2.6 | 5.3 | 40 | 38 weights/clk |
| 0.521 GB | ternary only, I2_S | 4.0 | 8.0 | 61 | 32 weights/clk |

**Decode is memory-bound on our SoC.** To keep up with 0.52 B/clk at 2 bpw takes only about 2.1 weights/clk,
which scalar `lut5w` or `bs8` exceed. Only a saturated `MEM_GAP` 8 link would make compute the limit, and
then RVV with `vwmacc` or `vqdot` and 3 integer-capable pipes is needed.

For comparison, the published laptop figure is 29 ms/token, about 34 tokens/s, on 8 threads of an
i7-13800H (Fact).

## 4. A benchmark to optimise against

Proposed port `ternary` (`run_bench.py --benchmark ternary`), built like the rt port.

* **Generator.** At build time, a native C generator (the `tgemv.c` hash, seed fixed) writes the packed
  weights for each kernel's layout and the expected int32 output checksums. It emits them as a data object,
  like `rt_data.c`.
* **The RISC-V program**:
  * generates the activations (hash), then runs the selected kernel over the shape set;
  * uses markers 1/2 for the region and laps 16-255 per layer;
  * compares every output in-program and writes the FNV checksums to the mailbox.
* **No weights are generated or packed on the core**: packing costs about 20 instructions/weight.
* **Kernels**:
  * scalar `lut5w`, `bs8`, `i2`, `tmac4`;
  * RVV `vmad` and `vlut` once the RVV RTL exists;
  * later `vmad-w` (`vwmacc`) and `vqdot`.
* **Shapes**:
  * `T-small` (RTL, under 300 s): (256x1280), (512x1024), (128x2560), 1.18M weights, about 0.3 MB at 2 bpw.
    Measured instructions:

    | Kernel | Instructions | Per weight |
    |---|---|---|
    | `lut5w` | 2.72M | 2.30 |
    | `bs8` | 1.54M | 1.30 |
    | `i2` | 6.52M | 5.53 |
    | `vmad` at VLEN 256 | 0.40M | 0.34 |
    | `vlut` at VLEN 256 | 0.40M | 0.34 |

    OoO Verilator ran about 59K instructions/s on rt (10.2M instructions in 172 s), so `lut5w` takes about
    50 s.
  * `T-2B4T`: one full 2B4T layer, 69.5M weights. ISS-only or sampled. Measured: `lut5w` 78.6M, `bs8` 74.9M,
    `vmad` 22.8M at VLEN 256 (11.6M at 512), `vlut` 19.9M (10.0M at 512).
  * `T-block` (step 2): a mini BitNet block (d 512, FFN 1376, 4 heads of 128, 1 KV head, 2.77M ternary
    weights). It adds activation absmax quantization, RMSNorm and SubLN, ReLU² GLU, RoPE and softmax
    attention over a 128-position synthetic KV cache (FP32 first, an int8 option later).
    * The FP code is compiled with `-ffp-contract=off` and our own `expf`/`rsqrtf` polynomials, so the
      native and RISC-V outputs must be **bit-identical**. The integer GEMV outputs are exact.
    * Expect about 3-6M scalar instructions per token.
* **Memory regimes to report**:
  * flat;
  * the deciding configuration with `--warm-l2` (L2-resident);
  * the deciding configuration with `--l2-kib 256` (0.3 MB of weights do not fit, so DRAM streaming).
  * Report weights/clk and achieved B/clk. Clocks per 2B4T token are projected as 30 x layer clocks plus the
    head.
* **A tiny real model.** The smallest open ternary checkpoints found are SpectraSuite TriLM 99M and 190M
  (Apache-2.0, HF shas `61cd2c76` and `847eb383`) and 1bitLLM `bitnet_b1_58-large` (0.7B, MIT).
  * Even 99M parameters is about 30M vector instructions per token, too long for RTL.
  * Downloads need the plan's admission checks.
  * Keep synthetic weights for the CPU benchmark. A real-weights accuracy check, if ever, would run on the
    ISS only, after admission.
* **Laptop reference (no goal set).**
  1. The same kernels natively, single thread, as here: `ndot` 19-22 weights/clk, `lut5w` 5-6.7, `bs8` 3.5-4.
     Per-clock figures use a measured clock (dependent-add chain 3.78-3.86 GHz; 7-Zip measured 3.7-4.3 GHz).
  2. bitnet.cpp with the official 2B4T I2_S gguf (1.19 GB), aarch64 WSL, `-t 1`, decode tokens/s. This
     needs the storage/RAM admission check before downloading.
  3. The usual "laptop + 50% per clock" rule is applied by the coordinator, not here.

## 5. Plan (each step its own version or experiment)

| # | Step | Kind | Why / expected |
|---|---|---|---|
| E1 | RTL streaming probe on released 0.17.0: `T-small` scalar `lut5w`/`bs8` at flat, deciding with `--warm-l2`, and deciding with `--l2-kib 256`, `N_MISS` 1/4/8 | experiment | Check the 0.52 B/clk Little bound and the 5-7 weights/clk scalar estimate |
| S1 | `ternary` benchmark port (generator, data object, scalar kernels, checksums, devlog rows, rubric unaffected) | bench-only commit, no CPU version | The thing to optimise against |
| E2 | Laptop reference: native kernels (done here as a prototype) plus admitted bitnet.cpp 2B4T `-t 1` | experiment | Per-clock anchor |
| S2 | Run `vmad`/`vlut` on the RVV subset RTL when it lands; record lane utilisation | experiment on that MINOR | Measure the integer-on-VP2-only penalty (estimated 3x) |
| S3 | Microarchitecture: integer ALU, logic, shift and merge on every vector pipe; 1/clk e16/e8 `vrgather` | PATCH | Estimated 4.7 to 14 weights/clk on `vmad` |
| S4 | Integer widening and narrowing: `vwmul*`, `vwmacc*`, `vwadd*`, `vwredsum*`, `vnsrl`, `vncvt` | MINOR (needed for V and RVA23 anyway) | Estimated 1.8x fewer slots; llama.cpp's RVV TQ kernels then run unmodified |
| S5 | **Memory-level parallelism for streaming**: 64-B L1 line fills (or the whole L2 line into L1), `N_MISS` 8 or more, the parked next-line/stream prefetcher, then Zicbop `prefetch.r` (RVA23-mandatory) | PATCH or MINOR each, separately | The only step that moves decode tokens/s: estimated 2x (`N_MISS` 8) up to about 15x (`MEM_GAP` 8 saturated) |
| S6 | Zvqdotq v0.0.2 behind a define, default off, advertised as experimental/non-ratified | MINOR, optional | Estimated 1.4x over S4 for compute-bound prefill only |
| S7 | Ternary custom unit: decide after S5 and S6 | decision | see below |

**Custom ternary unit versus standard RVV** (Judgement):
* **Not worth it on the CPU now.** Decode is memory-bound: compute already exceeds the 0.52 B/clk feed.
  A hypothetical `vtdot` (packed 2-bit weights times int8, unpacked in hardware) would cut about 11 slots to
  about 5 per 128 weights. That only pays where compute binds: prefill or batched decode with weights
  in L2.
* The llm-accelerator documents point the same way, and I build on them rather than contradicting them:
  * `llm-rva23-mapping.md` section 6 allocates no custom instruction. It keeps the MMIO ABI and requires any
    tightly coupled op to be a separately versioned ISA proposal outside RVA23.
  * `ffn-demo-plan.md` section 7.2 notes that "increasing multipliers alone does not create bandwidth".
  * Both say quantized profiles need their own qualification.
* If ternary is pursued in hardware, the natural place is a **W1.58 mode of the accelerator's GEMV engine**
  (route 2 there). The same 64-bit beat then carries 32 trits instead of 8 W8 weights, and the MACs become
  add/subtract muxes with no DSPs. That is a 4x weight bandwidth gain per beat at the same beat rate.
  * This needs its own numerical-profile entry: absmean/absmax scales, int32 accumulation and the
    per-tensor scale.
  * It is not a substitute for the BF16-P0 Qwen path, which stays normative there.

## 6. Gaps summary (ISA and SIMD)

1. Widening integer ops (`vwmacc*`, `vwmul*`, `vwadd*`, `vwredsum*`): the biggest compute gap, 1.8x. Every
   published RVV ternary kernel uses them.
2. Integer ALU on only one vector pipe: about 3x on every integer-SIMD kernel.
3. Zvqdotq: 2.5x over the subset; draft, not ratified.
4. Narrowing and fixed point (`vnsrl`, `vnclip`, `vfncvt`): activation quantization only; there is a
   workaround with `vlse8`.
5. `vrgatherei16`: only for tables over 256 entries; scalar `lut5` covers that.
6. **Memory, not ISA**: 8-byte beat fills with 4 misses in flight cap decode at about 0.5 B/clk.

## 7. Facts, judgements and limits

* Not done:
  * no RTL simulation (the core has no RVV RTL, and the scalar RTL probe is step E1);
  * no bitnet.cpp run (it needs a weight download);
  * no Codex review (research only, no RTL change).
* ISS instruction counts are not clocks. The weights/clk estimates for our core and the B/clk bounds are
  Judgement from architecture.md parameters.
* The native figures are cache-warm repeats of one layer. They are not a decode measurement.

## 8. Experiments run (for DEVLOG)

| Time (EST) | Goal | Commands (in `build/research/bitnet/`) | Versions | Result | Conclusion |
|---|---|---|---|---|---|
| 01:45:14 | Native correctness and speed of ternary GEMV maps | `wsl -e bash -c 'clang -O2 -fno-vectorize -fno-slp-vectorize -march=armv8.2-a+dotprod -DNATIVE -DSIZESET={0,1} tgemv.c; timeout 300 ./tgemv_native_s1 20; timeout 300 ./tgemv_native_s0 3'` | Ubuntu clang 18.1.3, WSL2 kernel 6.18.33.2, Snapdragon X2 (CPU part 0xd85), 20 vCPU | All kernels 0 mismatches; 2B4T shapes, weights/clk at 3.86 GHz: ndot 19.2-22.1, lut5 5.0-6.0, tmac4 1.95, i2 1.02 (`native_run1.log`) | MAD with SDOT about 4x the best scalar table map natively |
| 01:45:42 | Instruction counts on the golden ISS | `sh build.sh` (clang 23.1.5 `--target=riscv64-unknown-elf -O2 -fno-vectorize`, `-march=rv64im_zba_zbb_zbs` / `rv64imfd_zve64f_zba_zbb_zbs`); `rv_iss_fp --ram 16777216 --mailbox ffff00 [--fp 1 --vector 1 --vlen 128/256/512]` | LLVM 23.1.5; rv_iss_fp sha256 `b90b23f8da20` | Scalar and VLEN 128/256 all 0 mismatches; **surprise:** VLEN 512 small set 512 mismatches | Shape (512x640) breaks vmad's K multiple of 4 x VLENB at VLEN 512 (a kernel precondition, not an ISS bug); sizes changed to (512x1024) |
| 01:47:46 | Rerun after the size fix, plus `lut5w` (8 index bytes per load) | `sh build.sh; wsl -e bash -c 'bash run_iss.sh'` (`iss_summary.log`) | as above; tgemv.c `0dde972e` | 0 mismatches everywhere; per weight on 2B4T shapes: i2 5.50, lut5 1.50, lut5w 1.13, tmac4 3.26; vmad 0.648/0.328/0.167 and vlut 0.286/0.145 (VLEN 128/256/512) | Scalar table maps about 1.1 instructions/weight; RVV subset 0.29-0.33 at VLEN 256 |
| 01:48:30 | Native rerun with `lut5w` and an auto-vectorized build | `clang -O2 ... -DSIZESET={0,1}` with and without `-fno-vectorize`; `timeout 300` runs (`native_run2.log`) | as row 1 | lut5w 5.0-6.7 weights/clk; auto-vectorized i2 3.7-3.9; ndot 19.3-21.7; all exact | The auto-vectorizer does not reach SDOT; the hand NEON kernel is the laptop anchor |
| 01:51:42 | Bit-serial popcount (`bs8`, Zbb `cpop`) | `sh build.sh; bash run_iss.sh;` native s0 run (`run3.log`) | tgemv.c `5dd16d9d` | ISS 1.078 instructions/weight (2B4T shapes), 1.30 (small); native 3.5-4.0 weights/clk; 0 mismatches | Popcount map matches the best table map in instruction count on our ISA |
