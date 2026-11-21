# LLM accelerator demo: detailed implementation and feasibility plan

Status: proposed implementation plan; feasibility probes completed, accelerator not implemented.

Date: October 23, 2026. Budget: $0 for software and simulation. Destination: existing desktop research project. Scope: inference acceleration, with Qwen3.8-27B as the motivating workload.

## 1. Decision and intended demonstration

Build a small, synthesizable **quantized SwiGLU feed-forward accelerator**. A Python program will generate inputs and weights, run floating-point and bit-exact integer references, launch an RTL simulation, and compare every output. The hardware will execute all three FFN projections plus SiLU, elementwise multiplication, and requantization. A behavioral memory model will supply weight tiles with controllable latency and stalls.

The first complete demo uses **W8A8**: signed 8-bit weights, signed 8-bit matrix inputs, 32-bit dot-product accumulators, and explicit higher-precision intermediates. After that, add packed **W4A8** through the same datapath and measure its numerical quality. The current simple W4 quantization experiment does not meet the proposed quality gate; it must not be presented as ready for accurate Qwen inference.

Default dimensions: H=128 and I=384. Compute y = W_down * (SiLU(W_gate*x) elementwise-multiplied by (W_up*x)). Canonical reference matrices are output-major: gate/up are I-by-H; down is H-by-I. An offline packer rearranges them into the accelerator's tile-major stream described below. This is the same class of FFN computation used in the researched model, at a size appropriate for rapid simulation. The default ratio I/H=3 is a convenient demo choice; Qwen's actual ratio is 17,408/5,120=3.4. Dimensions are configurable, not a claim of architectural identity.

The visible demo is a terminal report: dimensions, numerical formats, exact RTL/reference match, floating-point error, accepted MAC count, simulated cycles, useful bytes transferred, stall cycles, and waveforms for a selected failure. It demonstrates a working LLM computation accelerator. It does not claim to generate text, run all Qwen layers, or outperform a GPU.

**Recommendation: proceed with this demo.** Arithmetic, memory size, and available free tooling make it credible. Whole-model Qwen3.8-27B on an inexpensive FPGA remains a separate capacity and bandwidth problem.

## 2. Connection to the existing research

The existing `research.md` compared HDL, simulators, and FPGA flows. The existing `notes/qwen3.8-27b/qwen3.8-27b-compute-analysis.md` and saved config/implementation established the workload dimensions and operation types.

- Qwen text stack: 64 layers, H=5,120, FFN width I=17,408. Three FFN projections per layer use 3HI=267,386,880 MACs.
- FFNs account for approximately 66.8% of the previous report's large text-projection MAC count, making them a strong first target. That percentage excludes context-dependent attention, vector operations, and vision.
- Attention softmax, rotary encoding, grouped KV storage, and DeltaNet state updates are different kernels; this FFN demo intentionally does not pretend to cover them.
- Nominal 27B four-bit weights alone occupy approximately 13.5 GB before overhead. The previous candidate boards' small memories do not automatically support complete model residency.

This plan does not require the CPU project, its ISA, a soft processor, an AXI subsystem, a board purchase, model weights, GPU access, or a paid HDL simulator. Keep earlier CPU files intact as prior work.

## 3. Feasibility evidence obtained now

The accompanying `planning-evidence/` files are planning probes, not finished accelerator components. Their results must not be substituted for future accelerator acceptance tests.

| Check performed | Observed result | What it establishes |
|---|---|---|
| Existing Ubuntu WSL environment | Ubuntu-24.04; Python 3.12.3 available | A Linux command-line environment already exists |
| Installed RTL simulator | Icarus Verilog 12.0 | No new HDL simulator purchase or installation is needed to start |
| Tiny W4A8 and W8A8 MAC RTL probes | Both PASS for signed extrema, valid stalls, reset | This installed tool handles the basic arithmetic and sequential constructs; not proof of the future tiled engine |
| Synthetic complete FFN, W8A8 | NRMSE 0.04208; cosine 0.99912 | Proposed simple numerical path is plausible on this fixture |
| Same FFN, W4A8 | NRMSE 0.33716; cosine 0.94898 | Simple four-bit power-of-two scales fail the initial W4 quality target |
| SiLU integer approximation sweep | Maximum absolute error 0.002674 over all 65,536 signed 16-bit inputs | The specified LUT/tail approximation is reasonable independently of projection quantization |

Numerical experiment: NumPy 2.4.6 / Python 3.11.9 on Windows, seed 23010, H=128/I=384, 32 calibration vectors and 32 separate holdout vectors. Weight entries are Gaussian with standard deviation 1/sqrt(fan-in); input entries have standard deviation 0.5. W8 had one saturated intermediate activation out of 12,288; neither configuration saturated final outputs. This is synthetic data from one weight fixture and is not an accuracy result for trained Qwen weights or language tasks.

The script measures a software model. It does not execute a whole RTL FFN. Each MAC probe checks four accepted products, including activation -128 and weight -8 or -128 depending on weight width. Synthesis fit, mapped resource counts, board clock, memory throughput, and complete RTL behavior are still unverified.

## 4. Smallest free tool stack

| Function | Initial choice | Reason / constraint |
|---|---|---|
| RTL | Conservative synthesizable SystemVerilog | Explicit signed widths, registers, arrays, synchronous memory; avoid classes, UVM, vendor primitives, and advanced frontend features |
| Simulator | Existing Icarus Verilog / vvp | Supports the intended subset; use `-g2012`; compile each new construct early |
| Reference and runner | Python 3 + NumPy 2.4.6 | Integer reference, float baseline, fixtures, comparisons, cycle model, JSON reports |
| Testbench interface | Plain SV testbench plus generated hex files | Avoid VPI/cocotb setup in the critical first path; Python orchestrates processes and checks output files |
| Waveforms | VCD; optional GTKWave | Dump only selected or failed tests to limit file size |
| Synthesis check | Yosys after RTL simulation works | Free generic synthesis checks inferred structure; it does not prove a routed FPGA clock |
| Larger regressions | Optional Verilator later | Add when measured Icarus runtime justifies it; not required to finish the first demo |

Use Ubuntu WSL for the eventual reproducible implementation environment. Prefer a checkout inside the Linux filesystem for repeated builds, with exports copied to the existing desktop project. Source files remain reviewable from Windows. The planning numerical probe ran with Windows NumPy; repeat it in the implementation environment before freezing fixtures. Do not mix Python paths or virtual environments across Windows and WSL.

Proposed setup commands, to run when implementation begins:

```bash
sudo apt update
sudo apt install python3-venv iverilog
python3 -m venv .venv
. .venv/bin/activate
python -m pip install numpy==2.4.6
iverilog -V
```

Pin the actual Python, NumPy, Icarus, and later Yosys versions in `tool-versions.txt`. Do not force a simulator upgrade just to match newer documentation. Install GTKWave or Yosys only when their milestone is reached. No hosted CI, proprietary IP, HLS license, account, or internet connection is needed to rerun the eventual offline demo after setup.

## 5. Datapath and memory architecture

### 5.1 One reusable engine

Default P=8 output lanes and Q=1 reduction element per lane per cycle: eight signed MACs per compute cycle. Broadcast one activation to eight independent output accumulators. Gate, up, and down reuse this engine sequentially. Start with one tile buffer and separate load/compute phases; implement overlap only after the reference and counters are trustworthy.

Use K_TILE=32 and N_TILE=8. A W8 weight tile is 8*32=256 bytes, organized into eight banks. Each bank supplies one signed weight per compute cycle. The activation buffer supplies the corresponding input element synchronously. Eight 32-bit accumulators persist across all K tiles for an output group, then pass to requantization and a single-result-per-cycle output interface.

Register the multiplier result and use an explicit accumulator stage; align `last`, output index, and valid through the pipeline. Measure actual drain cycles in the implementation. A partial final tile must zero masked terms and suppress nonexistent output rows. H=129/I=385 must work without padding leaking into output or address counts.

Top-level limits for the first implementation: MAX_H=256, MAX_I=768, P=8, K_TILE=32. Implement dimension counters wide enough for these limits, reject zero/out-of-range dimensions, and test both minimum and maximum dimensions. Full Qwen dimensions exceed this demo's buffer limits; scale-up would require larger or retiled activation/scratch storage.

### 5.2 Data movement contract

- External-memory model: 64-bit read data, byte addresses, one outstanding request. W8 beat holds eight weights, lane 0 in the least significant byte. Gate/up/down bases are eight-byte aligned.
- Packed order is `[output_group][K_tile][k_offset][output_lane]`, with a matrix base selecting gate/up/down. Thus a contiguous W8 beat feeds eight output rows at one k, instead of incorrectly treating eight contiguous elements of a canonical row-major matrix as eight output lanes. Pad incomplete rows/K tiles with zero in the packed file; count physical padded bytes separately from useful payload. Scale metadata remains indexed by canonical output row. Prove the packer/unpacker round trip before RTL tests.
- W4 extension: low nibble holds the earlier indexed signed weight; explicitly sign-extend each nibble. A 64-bit beat holds two compute stripes of eight W4 weights. This saves traffic, not automatically compute cycles at P=8/Q=1.
- `req_valid/req_ready`: accept a request only on both asserted at the active edge. Hold address/control stable while stalled.
- `rsp_valid/rsp_ready`: accept returned data only on both asserted. Hold data stable while stalled. Check that every accepted request has exactly one accepted response.
- Behavioral memory supports configurable 1-20 cycle response latency, randomized request backpressure, and bounded response delays. It models a contract, not a calibrated DDR controller.
- One tile is loaded, then consumed. A subsequent K tile accumulates onto the same output partial sum. Metadata/scales are loaded before a layer and counted separately.
- `out_valid/out_ready`: result index and signed data remain stable under backpressure. Exactly H final outputs are accepted in order. `done` may assert only after the last output handshake; keep it asserted until reset or an accepted new start.
- `start` is accepted only while idle. A busy `start` raises a documented error without corrupting the job. The host supplies dimensions, base addresses, and exponent metadata before start; no CPU or bus fabric is needed.
- Reset clears busy/valid/partial sums and discards the current job. The testbench memory shares reset and flushes pending responses, avoiding stale post-reset replies. No hidden promise of independent memory reset or transaction tagging is made.

The whole weight array is testbench/host memory, not inferred accelerator registers. Synchronous read timing in synthesizable local RAM wrappers must be explicit. Do not clear large RAM arrays with a reset loop: reset their valid state and initialize contents via the load protocol.

## 6. Numerical contract: write this before optimizing

Represent a quantized tensor value as q * 2^e. Use symmetric quantization with power-of-two scales: one exponent per weight output row, one for x, and one for the post-gating activation vector. Synthetic calibration chooses scales from maximum magnitudes; it is a starting policy, not a trained-model quantization solution.

| Stage | Representation / rule |
|---|---|
| Matrix weights | Signed W8 initially, W4 later; quantizer uses [-127,127] or [-7,7]; decoder must still handle legal -128/-8 bit patterns |
| Input and post-gating activation | Signed 8-bit; supported storage [-128,127]; calibration quantizer starts symmetric [-127,127] |
| Dot product | Explicit signed product, sign-extended into signed 32-bit accumulator; no intermediate truncation |
| Up/gate projection result | Signed 16-bit with scale 2^-8; range [-128,127.99609375] |
| SiLU | Input/output at scale 2^-8; LUT plus the tail rule below |
| Elementwise multiply | Signed 32-bit product of two 16-bit values; scale 2^-16 |
| Post-gating requantization | Round, shift to calibrated eight-bit scale, then saturate |
| Down projection output | Signed 16-bit at scale 2^-8 |

For each projection row: q_pre = saturate16(round(acc * 2^(e_activation+e_weight+8))). After the elementwise product: q_hidden = saturate8(round(product * 2^(-16-e_hidden))). Down uses the same projection formula with e_activation=e_hidden.

Rounding is nearest with ties away from zero, applied identically in Python and RTL. Saturate after rounding; do not rely on wraparound, unsigned shifts, or implementation-defined negative rounding. Use signed 64-bit intermediates for requantization and explicit sign extension. Supported exponents: input/weight [-16,0], hidden [-24,0]; validate and reject metadata outside those ranges. These bounds keep relevant left shifts within safe 64-bit arithmetic for the supported matrix lengths. Track saturation counters for each stage.

SiLU LUT: 4,097 entries for signed input q=-2048..2048 (real -8..8), output rounded to scale 2^-8. Above +8, return x; below -8, return zero. The saved exhaustive sweep measured maximum error 0.002674. Negative rounding, endpoints, zero, tails, and extreme int16 inputs receive dedicated tests. This approximation is separate from quantization error.

Do not compare an RTL integer result directly to floating-point with an arbitrary tolerance. First require **bit-exact agreement with the independent integer specification**. Then evaluate approximation quality against floating point as a separate gate.

## 7. Capacity, arithmetic, and performance sanity checks

### 7.1 Demo size

For H=128/I=384, weights and MACs = 3HI = 147,456. W8 weight payload is **144 KiB**; packed W4 is **72 KiB**. There are 2I+H=896 weight-row exponents, 896 bytes if stored as signed eight-bit values. The SiLU LUT is 8,194 bytes, approximately 8 KiB.

At maximum demo dimensions, two 16-bit up/gate buffers occupy 3,072 bytes; a hidden eight-bit buffer occupies 768 bytes; final output storage is 512 bytes; the tile buffer is 256 bytes; scale metadata is 1,792 bytes; and the largest reusable eight-bit activation buffer is 768 bytes. Including LUT, accumulators, and control, an initial **under-20-KiB local-storage design budget** is reasonable. Exact packing, ROM implementation, and RAM primitive overhead await synthesis. The behavioral 144-KiB default weight store is outside this local-storage budget.

Accumulator bound: at the default longest dot product K=384, W8 worst-case magnitude is at most 384*128*128=6,291,456. At MAX_I=768 it is 12,582,912. Even Qwen's K=17,408 gives 285,212,672 for W8 or 17,825,792 for W4; signed 32-bit is sufficient for these individual dot products. This does not prove that subsequent scaling, activation multiplication, or extended batching is safe; those use separately specified widths.

### 7.2 Timing model and honest performance claims

At P=8/Q=1, the default FFN has an arithmetic-only lower bound of **18,432 compute cycles**. With a single buffer, ideal W8 loading at one 64-bit beat/cycle also needs at least 18,432 cycles. Because initial loading and computation do not overlap, the combined lower bound is **36,864 cycles**, before requests, tile transitions, pipeline drains, nonlinear work, and output stalls. Do not use the max(load,compute) formula for this non-overlapped design.

A no-stall job below roughly 60,000 cycles is an initial engineering target, not a measured guarantee. The ideal load term assumes a one-beat-per-cycle refill path; a simpler one-outstanding controller that takes two cycles per read instead spends at least 36,864 load cycles and 55,296 combined load/compute cycles. Extra descriptor/tile/output overhead is still additional. Publish the implemented scheduler's cycle equation before making it a regression limit. At a hypothetical 100 MHz, 36,864 cycles is 0.369 ms; the actual elapsed job time is greater. An HDL simulation's wall-clock runtime is unrelated to that hypothetical silicon clock.

Required useful weight bandwidth during W8 compute is 8 bytes/cycle, or 0.8 GB/s at hypothetical 100 MHz; W4 uses 0.4 GB/s. This requirement is for keeping the chosen eight-lane engine supplied, not a measured board capability. The initial load/compute schedule has lower average utilization. Report MAC utilization = useful accepted MACs / (8 * total busy cycles), with padding explicitly excluded from useful MACs.

Later ping-pong tiles could overlap loading and compute, approaching max(load,compute) plus overhead; two W8 buffers occupy 512 bytes. A P=8/Q=4 experiment provides 32 MACs/cycle but needs 32 W8 bytes/cycle or 16 W4 bytes/cycle during compute. A 64-bit external feed cannot sustain either without reuse, wider memory, or buffering that only hides temporary bursts. Increasing multipliers alone does not create bandwidth.

### 7.3 Why this does not imply a full Qwen accelerator is solved

One actual Qwen FFN requires 267,386,880 MACs and approximately 255 MiB W8 or 127.5 MiB W4 weight payload. At eight MACs/cycle and hypothetical 100 MHz, arithmetic alone takes **0.334 seconds per FFN**. Sixty-four such blocks take approximately **21.39 seconds per generated token for FFNs alone**, even before the rest of the model and memory overhead. The full earlier projection budget is 25.62 billion MACs/token, approximately 32 seconds on the same ideal engine.

These figures justify a small accelerator demo but rule out promises of interactive full-model performance for this architecture. External storage capacity, host transfers, real sustained bandwidth, precision quality, and additional kernels would all need redesign. Simulation of a few full-sized projections might be useful later; simulating many whole-model tokens in event-driven RTL is not the initial development loop.

## 8. Proposed repository and command contract

Create a new `llm-accelerator/` directory inside the existing desktop project when implementation starts. The following files and commands are **planned**, except the saved planning evidence and this plan. They are not already implemented.

```text
llm-accelerator/
  README.md                    scope, setup, quick demonstration
  spec/numerics.md             widths, scales, rounding, layout, errors
  spec/interface.md            control and memory handshakes
  rtl/mac_lane.sv
  rtl/gemv_tile.sv
  rtl/weight_buffer.sv
  rtl/requantize.sv
  rtl/silu_lut.sv
  rtl/ffn_top.sv
  sim/tb_ffn.sv
  sim/memory_model.sv
  reference/float_ffn.py
  reference/integer_ffn.py
  tools/generate_vectors.py
  tools/run_demo.py
  tools/run_regression.py
  tools/estimate_workload.py
  tests/                       directed and seeded fixtures
  synth/check.ys
  planning-evidence/           existing planning probes and results
  build/                       generated executables, vectors, waveforms
  reports/                     machine-readable results and provenance
```

Planned entry points after implementation:

```bash
python tools/run_demo.py --preset tiny --precision w8a8 --seed 23010
python tools/run_regression.py --suite acceptance
python tools/estimate_workload.py --preset qwen3.8-27b
yosys -s synth/check.ys
```

The demo runner owns compilation with `iverilog -g2012 -s tb_ffn`, executing vvp, timeout/error handling, parsing outputs, and generating a report. Any compile error, simulator failure, timeout, unknown output, output-count mismatch, bit mismatch, protocol violation, or required quality failure must result in a nonzero exit code. No silent fallback to the Python model when RTL fails.

Fixtures include tensor shapes, scale metadata, packing format, seed, checksum, and generator version. Reports include tool versions, test ID, precision, errors, saturation counts, useful MACs, memory bytes, cycle categories, and simulator wall time. Keep hardware-cycle estimates distinct from measured host time. Run the synthetic fixture without downloading a checkpoint.

## 9. Milestones and acceptance gates

| Milestone | Work and deliverable | Completion evidence |
|---|---|---|
| M0: freeze contracts | Specify layout, signedness, numerical stages, legal descriptors and reset | Reviewed numerical/interface docs; reference round/shift/packing tests |
| M1: reference | Implement separate float and integer FFN paths, LUT generator and calibration/holdout fixtures | Reproduce planning W8 result within stated precision; exhaustive LUT sweep; deliberate corrupt vector causes failure |
| M2: arithmetic RTL | MAC lane, tile accumulator, requantizer, LUT | Exact directed/random tests, width/sign edge cases, stall/reset probe expanded beyond planning smoke test |
| M3: tiled GEMV | Banked synchronous buffers, loader, partial K/N tiles, memory handshake | Exact match for all required shapes; byte/request accounting; no duplicate/missing terms under stalls |
| M4: complete W8 FFN | Schedule gate/up, SiLU/product, hidden requantization, down | One command produces all H correct outputs, quality metrics and cycle/traffic report; reference never substituted for RTL |
| M5: regression and synthesis | Test full accepted parameter range; generic synthesis of synthesizable hierarchy | Acceptance suite passes; no unintended latch or undriven signals; inspect multipliers and inferred RAM; archived report |
| M6: W4 evaluation | Nibble unpacking and equivalent datapath; independent quality study | Exact integer match required; report quality gate failure if simple scales remain inadequate; do not require failure to disappear to finish honest W8 demo |
| M7: performance experiment | Compare single-buffer to optional double-buffer schedule | Exact same outputs; measured cycle reduction and traffic explanation; no claimed FPGA clock without routing |

M0-M5 are required for the first completed demo. M6 is a planned follow-on experiment, with failure explicitly allowed and reported; M7 is optional optimization. This turn delivers the detailed plan and feasibility evidence, not completion of these implementation milestones.

### Required test coverage

- Numerical: every W4 encoding, representative/full-byte W8 encodings, signed extrema, zeros, mixed signs, maximum positive/negative dot products; saturation on both bounds; rounding ties on both signs; all supported exponent limits.
- Matrix shapes: H/I = 1/1, 8/32, 31/63, 128/384, 129/385, and 256/768. Add at least eight seeded legal random shapes. Down projection changes input/output dimensions and must be checked independently.
- Protocol: zero stalls; randomized request/response/output backpressure; bounded long stalls; back-to-back jobs; busy start; invalid dimensions; reset during load, compute, nonlinear processing, and output wait. Validate stable signals while stalled and zero ghost results after reset.
- Distinct data: all-zero, impulses, alternating signs, deterministic ramps, and Gaussian calibration/holdout. Use at least 32 seeded jobs across the randomized protocol suite, with reproducible failing seeds.
- Exactness gate: all accepted RTL outputs equal the independent integer reference, in order, with exactly the expected count. Unknown/high-impedance bits fail; do not cast them silently to zero.
- W8 fixture quality gate: global NRMSE <=0.08 and flattened cosine >=0.995, no final saturation, hidden saturation <=0.1%. If float reference norm is zero, use an absolute-error rule instead of dividing by zero. Also report per-vector worst errors rather than hiding them behind the aggregate.
- W4 initial quality target: NRMSE <=0.15 and cosine >=0.98 on separate holdout data. Current 0.337/0.949 result fails. A future trained-weight study must set its own task-level accuracy criteria; this synthetic gate cannot certify language quality.
- Negative controls: intentionally corrupt one packed weight, one output word, and a scale exponent; confirm checker fails. Explicit RTL tests must exercise saturation and tail handling even though normal fixtures rarely do.

### Synthesis and simulation boundary

Use Yosys `read_verilog -sv`, hierarchy checking, process lowering, and `check` on the accelerator modules. Testbench delays, file I/O, and behavioral external RAM are excluded. Inspect RAM inference rather than immediately flattening all memories into registers. Generic synthesis is structural feasibility evidence; technology mapping and place-and-route are later board-specific gates.

If an entirely open future FPGA flow is desired, ECP5/Yosys/nextpnr remains a researched route. The larger AMD surplus boards have a free proprietary Vivado path with device/tier details to recheck at purchase. Neither is required for this software-only demo. Do not budget a fixed LUT/DSP count from the MAC count: signed widths, mapping, packing and memories change the result.

## 10. Risks, mitigations, and go/no-go decisions

| Risk | Evidence or consequence | Mitigation / decision |
|---|---|---|
| Four-bit accuracy | Current simple scheme has 33.7% NRMSE | Deliver W8 first; investigate per-group/per-row mantissa scales or better calibration separately; keep numerical contracts versioned |
| Synthetic tests look better than trained tensors | No actual checkpoint used | Label all quality results synthetic; later test an actual FFN layer with documented calibration and holdout activations before model claims |
| Scale/rounding mismatch | Integer RTL can look plausible while being wrong | Independent exact reference, signed-shift rules, exhaustive small-domain tests and negative controls |
| Memory throttles utilization | Initial loader/compute phases do not overlap | Measure all phases; compare later overlap; do not claim arithmetic peak as sustained throughput |
| Large simulation runtime | Event-driven full-network simulation is expensive | Small default tensor, failure-only waves, measured runtime budget; optional Verilator after proving a need |
| Tool syntax or RAM inference | Icarus and Yosys support subsets | Conservative RTL, small compile/synthesis probes, registered memory wrappers; avoid dependence on paid frontends |
| Premature board purchase | Capacity and documentation matter more than advertised logic cells | Finish simulation plus traffic/structural reports before choosing hardware |
| Scope expands into all LLM operators | Qwen also needs DeltaNet, full attention, normalization, vision | Finish explicit FFN scope first; keep later kernels and complete model integration as separate decisions |

**Go now:** implement M0-M1, then the W8 arithmetic datapath. **Do not buy hardware yet.** Reassess if the independent integer reference cannot meet the W8 quality gate on expanded fixtures, if the chosen RTL subset cannot synthesize, or if the measured simulation runtime prevents useful iteration. Such results change the design before optimization, not the labels on the report.

Allow roughly 8-15 focused implementation/debugging sessions for M0-M5 as an initial planning estimate; experience and failures can change this substantially. Treat milestone evidence as the schedule, not a promised completion date. The first session should finish the numerical contract, reproducible float/integer reference, and a documented failing negative control.

## 11. Route from the demo to actual model work

After the first demo, possible next steps are: validate a real checkpoint FFN tensor and activation distribution; improve four-bit scaling; add a batched matrix-matrix path for prompt prefill; build a DeltaNet state-update kernel; or add grouped-query attention and cache traffic modeling. Choose one based on the measured bottleneck.

A later token-generating system must integrate embedding, normalization/residuals, all decoder layers, attention/DeltaNet state, output projection, tokenizer and sampling. Host-assisted execution can accelerate selected kernels while the host runs the rest, but transfer cost belongs in the performance report. A host software model invoking this RTL simulator will normally be slow; its value is correctness and architecture exploration. Actual speedup requires implemented hardware or an appropriate measured deployment.

## 12. Sources, saved evidence, and completion checklist

Existing local research: project-root `research.md`; `notes/qwen3.8-27b/qwen3.8-27b-compute-analysis.md`; saved `qwen-config.json`; saved `modeling_qwen3_5.py`. These support workload selection and dimensions, not measured board throughput.

Primary references checked October 23, 2026:

- [Official Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [Official configuration](https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/config.json)
- [Qwen3.5-family implementation used by the checkpoint](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen3_5/modeling_qwen3_5.py)
- [Icarus compiler flags and language modes](https://steveicarus.github.io/iverilog/usage/command_line_flags.html)
- [Yosys Verilog/SystemVerilog support](https://yosyshq.readthedocs.io/projects/yosys/en/latest/using_yosys/verilog.html)
- [nextpnr supported FPGA architectures](https://github.com/YosysHQ/nextpnr)
- [cocotb simulator support](https://docs.cocotb.org/en/stable/simulator_support.html), useful if later integration needs justify it

Planning evidence is stored in `llm-accelerator/planning-evidence/`: numerical probe, result JSON, MAC RTL probe, run log, and environment record. The numeric probe can run with `python llm_feasibility.py` when NumPy is installed. From Ubuntu, `bash run_mac_probes.sh` compiles and runs both RTL precision probes. These are the only accelerator-related simulations completed at plan time.

Before calling the later demo complete: verify M0-M5 artifacts and commands exist; all required numerical, protocol and negative tests pass; the complete W8 FFN ran in RTL; synthesis structure was inspected; report actual cycle/byte/error metrics; document remaining W4 quality limitations; and verify the README can reproduce the demo from a clean environment without paid tools or model downloads.
