# Implementation contract, revision 1

This document, [ABI 1](abi-v1.md) and [adapter protocol 1](adapter-v1.md) are the normative decisions from adversarial refinement. They replace conflicting tentative choices in `plan.md`, `memory-plan.md` and `plan-gap-audit.md`. Scope is the complete learned text/vision forward graph, with a bounded first implementation and explicit later scale qualification. These specifications are not evidence that the implementation passes. Changes to a numerical policy, layout, ABI or qualification ceiling require a new version and a recorded review; failed results do not authorize silently loosening a requirement.

## 1. Current workstation and stage admission — C01

Read-only inventory on October 23, 2026, is saved in `host-development-inventory.json`. The current machine has a Snapdragon X2 Elite Extreme ARM processor, 18 cores, 51,127,103,488 physical RAM bytes (about 47.61 GiB), and a snapshot of 48,557,871,104 free bytes on C: (about 45.22 GiB). Space changes and must be rechecked before each substantial job. Ubuntu-24.04 WSL is **aarch64**; `/usr/bin/iverilog`, `/usr/bin/vvp` and `/usr/bin/python3` were found. Verilator and Yosys were not found on that distribution's current PATH. The default WSL distribution is NixOS; use `wsl -d Ubuntu-24.04` explicitly for the established simulation environment.

AMD's current supported Vivado host architecture is **x86-64**. Native Windows on this ARM workstation is not a verified synthesis/programming route. x86 emulation, WSL and a Windows installer do not establish supported drivers or PCIe access. Access to a supported x86-64 build/programming host and a suitable native Linux PCIe runtime host is a prerequisite for the hardware phase. One compatible x86-64 Linux desktop could fill both roles. No such host, available PCIe slot or connection to the current machine has been verified. [AMD 2026.1 host requirements](https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Operating-Systems).

| Stage | Admission and fallback |
|---|---|
| Tiny software/RTL now | Use the existing ARM Python/Icarus path. Before compiling, check versions and run the actual arithmetic/module smoke test; a path lookup is not a compile result. Install/build additional free ARM-compatible tools only as a later implementation action. |
| One native tensor/layer now | Bound downloaded/packed data to 4 GiB, temporary data to 2 GiB and traces to 2 GiB. Require that budget plus at least 10 GiB free reserve and a measured process/WSL RAM budget. Fetch a selected tensor's verified byte range or one shard only after checking its size; process/pack incrementally. Do not keep a whole model or FP32 copy. |
| Complete native-model data | Full original payload is 55.56 GB, already greater than present free disk and physical RAM. Reserve at least **155 GB decimal free space** on the selected storage volume for an original-copy allowance, packed-copy allowance, temporary/trace data and headroom; compute the actual requirement if a different storage strategy is chosen. Prohibit a full download on the current volume until admission passes. |
| Full software/RTL run | Measure free RAM inside WSL/process limits, host available RAM, page faults and sample peak memory. Admit only if predicted peak plus 30% margin fits the smaller effective memory limit, with no unbudgeted swap dependence. Stream bounded tensors from adequately provisioned local storage when full residency is impossible. |
| FPGA synthesis/programming | Verify an available supported x86-64 host, exact tool/IP entitlement, install/workspace disk, programmer/USB access and a successful small target build. No assumption of free cloud hours or ARM emulation. |
| PCIe accelerator runtime | Verify host/slot/link/driver/IOMMU and physical power/cooling, then DMA/DDR measurements. A USB cable or remote shell does not supply a PCIe data link. |

The under-$500 comparison is a **board budget**, not a proven all-in project cost. Record board/shipping/tax/accessories, supported host access, additional RAM/storage, power and any paid remote usage separately. Borrowed/already-owned compatible infrastructure may keep added costs low, but that access must be confirmed. Until then, KU5P is a conditional candidate and CPU simulation is the immediate free route. Do not purchase hardware to conceal an unresolved host prerequisite.

## 2. Independent fidelity ceilings and immutable workloads — C02

`qualification-fixtures.json` revision2 fixes eight calibration and sixteen held-out pseudo-random native text sequences, two repetition/alternation sequences per split, two calibration and four held-out semantic text recipes (plain language/code/numerals/repeated prose), four calibration and four held-out media recipes, and the explicit 66-token baseline D8 image input. Total text coverage is12 calibration and22 holdout fixtures. Every media recipe compares all expanded prompt positions and freezes consumed-token state checkpoints at run boundaries and specified lengths. Semantic tokenization and media expansion are locked before numerical qualification; a missing materialization cannot silently reduce the fixture count. The anchored fixture digest changed deliberately for C12 while all hard ceilings remained identical. Text IDs are present in full, not generated from an unrecorded RNG. Media recipes fix pixels, dimensions, item/frame identity, raw timestamps, input text and processor overrides. The pinned processor must materialize token IDs, modality runs, normalized pixels and their hashes **before RTL results are inspected**. Missing materialized fixture identities block that fixture's qualification; they cannot be replaced with a convenient passing example.

All comparisons are teacher-forced on the same tokens/inputs to separate numerical drift from divergent sampling. Snapshot Delta/conv/KV per layer at every fixed fixture checkpoint and at lengths8,16,32,64 where present. Media checkpoints use consumed-token counts, including each run start/end and following marker; use short/rerun diagnostic executions as needed to capture chronological states under layer-major schedules. The full state oracle must retain semantic chronology even if physical execution is layer-major. First-token/last-position-only D7/D8 proof runs are subsets, not completion of this fidelity suite. Model-size or long-context claims require extending the suite without weakening existing cases.

For reference y and candidate x define:

```text
NRMSE = sqrt(mean((x-y)^2)) / max(sqrt(mean(y^2)), 1e-6)
coordinate_scaled_error = max_i abs(x_i-y_i) / max(1, abs(y_i))
p = FP64 stable_softmax(reference_logits)
q = FP64 stable_softmax(candidate_logits)
KL = sum_i p_i * (log(p_i) - log(q_i)), using stable log-softmax
```

Use separate metrics per tensor/layer/sequence/checkpoint; do not average a failed layer away. Any unexpected nonfinite value fails. These are provisional **hard engineering ceilings**, fixed independently of calibration:

| Compared result | Maximum permitted degradation |
|---|---|
| Native intermediate tensor / residual | NRMSE <=0.01 and coordinate-scaled error <=0.05 |
| Delta state at every checked time/layer | NRMSE <=0.01 and coordinate-scaled error <=0.05; no exception for an accumulating drift trend |
| Full logits at each requested position | NRMSE <=0.01 and maximum absolute error <=0.5 |
| Output distribution at each position | KL(reference || candidate) <=0.002 nats and L1 distance <=0.02 |
| Greedy top-1 | At least 95% agreement over **all** held-out comparison positions; each text/media subgroup also meets 95% |
| Reference top-1 within candidate top-5 | At least 99% over all positions and within each subgroup |

For integer counts, require `matches >= ceil(fraction * count)`. Low-margin positions remain in the denominator; no discard/reweighting is allowed. A reference top-two gap greater than 1.0 additionally requires exact greedy agreement under the 0.5 maximum-logit-error ceiling. Report every mismatch and its margin. These fixture-level criteria do not establish downstream task accuracy or universal language quality.

Calibration may select **tighter** per-operator/RTL bounds within these ceilings, never larger ones. Basic operation/cast and prescribed accumulation traces must match the deterministic policy oracle bit-for-bit; the independent framework comparison must also meet the ceilings. If the emulated arithmetic fails, change arithmetic/approximation precision or schedule and version the profile; repeat calibration and unchanged holdout tests. If a ceiling itself proves inappropriate, record a separate design decision and independent review before changing it, with the old failures retained. The plan cannot declare the current fidelity goal met by redefining its tolerance after a failure.

## 3. BF16-P0 operation order — C07

Notation: `R32`/`R16` are RNE casts with defined subnormal handling; `add32`, `mul32`, `div32`, `sqrt32` round once at their FP32 output; `fma32` rounds only the final product-plus-add. `BADD(a,b)=R16(add32(F32(a),F32(b)))` and similarly for BF16 multiplication. F32 widening from BF16 is exact. Constants use the stored FP32 bits in the numerical manifest, not a compiler's unrecorded literal conversion.

**One deterministic serial baseline:** `sum32(v)` starts +0 and executes `s=add32(s,v[i])` in increasing logical index. `dot_sep(a,b)` is `sum32(mul32(a[i],b[i]))`. `dot_fma(a,b)` starts +0 and executes `s=fma32(a[i],b[i],s)` in increasing logical index. Masked elements are skipped entirely. Physical lane/context scheduling preserves each logical recurrence; reassociation, partial-sum trees or implicit multiply/add contraction require a different profile. A tile boundary does not reset the accumulator.

| Operation | Ordered baseline and casts |
|---|---|
| Linear/GEMV | `dot_fma`, then one `add32(acc,F32(bias))` if bias exists, then R16. REF32 uses the same order without R16. |
| Depthwise convolution | Four source-ordered products via `dot_fma`, oldest-to-current kernel index, then R16; SiLU on the widened result then **R16 again**. The conv ring stores raw BF16 projection values. |
| RMSNorm | Squared values by mul32; sum32; div32 by dimension; add32 epsilon; `div32(1,sqrt32(...))`; mul32 per element; affine multiply in its stated order, then required R16. Text gamma is `add32(1,F32(w))`. |
| L2 norm | mul32 squares, sum32, add32 epsilon, reciprocal sqrt as above, mul32 x. Delta query scaling is a subsequent mul32 by the stored inverse-root constant. |
| LayerNorm | sum32 x then div32 for mean; sub32 each centered value; mul32 squares; sum32 then div32 population variance; add epsilon; reciprocal sqrt; mul32 centered x, mul32 gamma, add32 beta, R16. |
| Full/vision attention QK | dot_fma in head-coordinate order; R16; mul32 by stored scale constant; R16. Recompute all three passes with exactly this score recipe. |
| Softmax | Ascending valid-position max with first-index tie choice; sub32(score,max); EXP32; ascending sum32 denominator; div32 per probability; R16 before AV. Zero valid entries follow the explicit error/zero-row policy. |
| AV | dot_fma in ascending valid-position order on widened BF16 probabilities and V; R16; then declared gate/product/output-projection boundaries. |
| Delta matrix update | mul32 decay*old-state; prediction=dot_sep over increasing key; delta=mul32(beta,sub32(v,prediction)); new-state=add32(decayed,mul32(k,delta)); readout=dot_sep(q_scaled,new-state); state remains FP32, readout R16. No FMA contraction in these expressions. |
| Delta gated norm | FP32 RMS recipe; R16 normalized values; BF16 multiply by learned gamma; FP32 multiply by SiLU32(z); R16. Beta is R16(SIGMOID32(b)) before recurrence; a/bias/A_log/softplus/decay use the declared FP32 path. |
| FFN and vision MLP | Each projection follows GEMV; SiLU32 or the appropriate GELU32 followed by **R16**; SwiGLU multiplication is BF16; down projection follows GEMV. Merger uses erf-GELU; vision blocks use tanh-GELU. |
| Position interpolation | Compute FP32 tap coordinates/fractions; form four weights with mul32; accumulate four products with dot_sep in `(h0,w0),(h0,w1),(h1,w0),(h1,w1)` order; R16, then BF16 addition to patch output. |
| Text rotary | phase=mul32(position,F32(frequency)); SIN32/COS32 then R16; two BF16 products and a BF16 addition for each rotated coordinate. |
| Vision rotary | FP32 phase/trig; two mul32 products and add32, then R16. |
| Residual / logits | BF16 residual add. BF16 LM projection result may widen to FP32 transport; no extra precision is retained across the projection boundary. |

Nonlinear expression order is part of the profile: sigmoid is `div32(1,add32(1,EXP32(-x)))` for x>=0 and, with e=EXP32(x), `div32(e,add32(1,e))` for x<0; SiLU is `mul32(x,SIGMOID32(x))`; softplus is `add32(max(x,0),LOG1P32(EXP32(-abs(x))))`; erf-GELU is `mul32(mul32(0.5,x),add32(1,ERF32(mul32(x,inv_sqrt_2))))`; tanh-GELU computes x² then x³ with mul32, `mul32(0.044715,x³)`, add32 x, multiply by sqrt(2/pi), TANH32, add32 one, then multiply by `mul32(0.5,x)`. Use separate operations throughout those formulas. The selected approximation primitive returns FP32 before these surrounding operations/casts.

The transcendental implementation is parameterized by a **mandatory immutable kernel manifest**: coefficients/ROM bits, evaluation order/opcodes, reduction method/width, domains, exceptional-value branches and generator/oracle versions. BF16-P0 fixes graph/order semantics; its effective identity is `(P0 version, kernel-manifest SHA256, constant-manifest SHA256)`. An absent kernel manifest blocks D1 completion and any claim of bit-exact policy execution. Numerical reference functions cannot be replaced by the same untested implementation as their sole oracle: use independent high-precision evaluation for approximation error, a separate interpreter of the frozen operation manifest for exact policy traces, and the pinned framework for fidelity. Nonlinear error targets from the gap audit remain required; they are not substitutes for the model-level ceilings above.

Constant generation: use a recorded MPFR tool/version at >=256-bit precision, round once to binary32 RNE, and emit hexadecimal bits plus a SHA256 manifest. Exact rationals (epsilon=1/1,000,000, 1/16, 0.5, 0.044715) are parsed as rationals; inverse roots, pi-derived constants and frequency powers use the high-precision definitions. Freeze processor-compatible FP32 positional phases separately from ideal real-number phases. Seed checks include epsilon `0x358637bd`, 1/16 `0x3d800000`, 0.5 `0x3f000000` and 1.0 `0x3f800000`. Do not invent an MPFR install/version in the plan: record the chosen executable and generated constants before D1.

Directed order tests include `(1+2^-23)*(1-2^-23)-1`: fused output is `-2^-46`, while separately rounded multiply/add yields zero; and ascending sum `[1e20,-1e20,3]` versus a reassociated tree. Tests must exercise the chosen order under stalls and tile/context boundaries. These examples are fixtures, not substitutes for SoftFloat/TestFloat coverage or native fidelity.

## 4. Full-prompt multimodal positions and lifetime — C04

Fresh media is accepted only when the context has **zero committed tokens and initialized zero state**. Appending new media to a nonempty cache is rejected before encoder execution or mutation. To add new media, reset/create a context and replay the full desired prompt under the same admitted limits. Text-only continuation of an already evaluated VL prompt is supported using its committed rope delta. This matches the selected bounded path; it does not invent new-media cache semantics absent from the inspected helper.

For every fresh VL command, the input contains the **entire command prompt**, token IDs, modality types, ordered media descriptors and runs before numerical execution starts. The on-core position controller validates each contiguous placeholder run against its grid/feature count. Split video descriptors into temporal entries with t=1 exactly as the pinned helper; timestamp markers are ordinary already-tokenized text between those runs. The host may tokenize and provide media metadata; it does not compute substitute position arrays for the DUT.

Before the first U=1/U=8 chunk, generate the full `[T,4]` signed-64-bit positional plan on-core: causal index plus three rotary axes. Causal positions are the actual cached token indices; rotary positions follow the complete source modality grouping. Compute signed `rope_delta=max(rotary_positions)+1-T` for the full fresh prompt. Store the plan in external workspace (32*T bytes: 16 KiB at T=512); it stays immutable until the whole command completes. Chunks read slices of this plan and never call the source grouping algorithm independently. Store the proposed delta separately from the publicly committed context metadata.

Full-command success atomically publishes the new committed length and rope delta after every layer/output/state write is visible. Internal chunk barriers do not publish a resumable prefix or READY state. A failure during any chunk invalidates the context as specified below. After successful VL prefill, text decode uses `rotary_index = causal_cached_index + committed_rope_delta` on all three axes; use checked signed arithmetic. The delta is not a byte offset, token count or timestamp multiplier.

Verification: materialize a pinned **full-prompt** oracle, then run token-major and U=8 schedules with chunk boundaries immediately before/after each marker, at every position inside every placeholder run, and between every video temporal group. Compare the full four-stream plan, signed delta, encoder insertion indices, per-layer K/V, Delta state and logits. Resume text decode from the committed state and compare again. Also test fresh-media append rejection without any DMA write. Positional-only fixtures can exhaust all boundaries cheaply before expensive full native inference.

## 5. Normal cancel, reset and fatal transport failure — C03/C09/C10

ABI1 now specifies atomic successful-reset rebind of all context-owned mutable region epochs, failed-clear metadata preservation and retry. Adapter1 specifies session nonce bootstrap, uploaded/sealed descriptors, tagged model byte requests and stage ownership. Both lifecycle paths must pass simulated and actual-driver gates; planning byte fixtures are not implementation evidence.

Add distinct states `DRAINING`, `QUARANTINED` and `OFFLINE`. Advancing an FPGA epoch prevents stale internal-response reuse; it does **not** cancel a PCIe posted write or prove host memory is safe to unmap.

Normal cancel: independently accept the cancel control request, stop new issue, retain all owned buffers/mappings, drain known operations and complete the numerical command as CANCELED with context invalid. A cancel acknowledgement is not that terminal numerical completion. The cancel drain has a configurable bounded deadline (initial development default 5 seconds of host monotonic time, shortened in fault tests). This deadline is independent of legitimate inference duration and core progress-watchdog settings.

On permanent missing responses, PCIe link loss, driver/device teardown, failed reset or drain expiry:

1. Host marks the device/context OFFLINE/invalid, stops new submissions, and returns a host-originated terminal `DEVICE_OFFLINE` result after the bounded wait. If the device cannot write its completion, the host result records `origin=host` and `device_completion_present=false`; it must not fabricate device success.
2. All buffers reachable by outstanding DMA enter a quarantine registry owned by the kernel/driver recovery layer. User mappings, queues and pin references remain owned; the application may exit without causing unsafe early release. Reject new registrations/submissions that would reuse those buffers or device slots.
3. The driver requests endpoint/bus-master disable, reset or removal and IOMMU isolation through its OS/PCI recovery path. A failed config access, reset timeout or mere epoch change is **not** proof of quiescence. The adapter/driver implementation must document its platform-specific positive isolation/drain guarantee and receive an independent review before hardware DMA enablement.
4. Release a mapping only after either (a) all relevant DMA and writes have positively completed under the adapter's visibility contract, or (b) the OS/platform recovery path positively establishes that the endpoint and all in-flight transactions can no longer reach it. Keep the exact evidence with the mapping generation. Clearing a software table is insufficient.
5. If neither condition is provable, keep the device disabled and mappings quarantined. Escalate to supported host reset/reboot/device removal recovery; do not permit endless automatic retries or reuse. New work may use a different verified host, but this device does not return READY. Kernel teardown must not unload its quarantine owner while unsafe mappings exist. If a driver cannot uphold that lifecycle, it fails the hardware gate and must not be used.

Bound quarantine: first fatal event disables this device until recovery, so repeated submissions cannot accumulate an unbounded series of newly pinned buffers. Reserve a configured mapping/pin budget before starting a command. A host failure/reboot is a terminal run failure, not a successful graceful cancel. After recovery perform fresh enumeration, handshake, DDR/DMA tests and new region generations; all prior contexts are invalid.

Required fault tests: permanently absent read response; link loss during posted writes; late write after user timeout; repeated/stale cancel; driver close/restart with owned mappings; successful and unsuccessful reset/isolation; host-origin result versus genuine device completion; and prevention of mapping reuse until positive quiescence. Test normal drain independently. The successful hardware gate requires observed recovery behavior on the actual supported host/driver, not only a behavioral RTL memory model.

## 6. Workload-level simulation budgets — C08

`refinement_checks.py` derives workload floors and writes `refinement-checks.json`. Count decoder-body MACs separately from the untied head: 25,621,954,560 total dense MACs/token minus 1,271,398,400 head MACs gives **24,350,556,160 body MACs/token**. A T-token prefill with last-position logits therefore costs at least `T*body + head`; all-position logits cost `T*(body+head)`. Generated/teacher-forced decode steps each add body+head. These lower bounds omit text attention, Delta/vector/nonlinear work and stalls.

D7 first proof fixture: one native text token, all 64 layers and one head. Subsequent fidelity qualification must execute the fixed suite; a single-token proof is not the full numerical gate. D8 baseline has the explicit image-start token, **64 image placeholders**, image-end token and one final head: **T=66**, not T=1. Its decoder dense work is `66*body+head`. Add the entire 256-patch vision encoder/merger; the script also counts a three-pass-attention vision MAC subtotal. The actual processor-based fidelity fixtures may be longer and must be budgeted using their materialized lengths.

At eight ideal MACs/cycle and a hypothetical 100,000 simulator cycles/s, the D7 dense floor is 8.90 hours. D8's decoder alone is roughly **23.27 days** and the counted vision work adds roughly **1.69 days**. These are hypothetical lower bounds, not a measured forecast; at 1,000,000 cycles/s the combined counted work is still about **2.50 days**. Last-position logits are already accounted for. Reducing decoder context below the required visual placeholder count would invalidate this fixture.

Before a native job, benchmark representative GEMV, Delta, attention, nonlinear and DMA traces with the actual simulator/build and enough iterations to include steady-state stalls. Record cycles/s and wall seconds/operator, peak RAM, page faults and log/trace bytes. Use those measured rates and the actual full workload to estimate elapsed time, then multiply by **2** as an admission margin until predictions are calibrated. The initial per-fixture wall-time admission ceiling is **48 hours**, process memory follows section 1, and waveform/trace allocation is capped at **8 GiB per admitted long run** with bounded first-divergence capture. No default unlimited waveform dump.

If that admission fails: improve compiled simulation/model performance without replacing DUT arithmetic; use an available stronger compatible simulation host with measured cost; or defer D7/D8 completion to actual FPGA execution after the hardware gates, still running every learned operator and comparing the same outputs/state. The fidelity suite remains incomplete until it actually passes. A reduced-layer proxy or a smaller image is not silently substituted for the declared fixture; a separate smaller legal processed-pixel fixture can add evidence under a distinct ID. Keep the 66-token D8 requirement visible. Do not launch an unbudgeted multi-week run merely to tick a gate.

## 7. Frozen source enforcement — C06

`reference-source-lock.json` lists the path, immutable origin/revision, length and expected SHA256 of all 16 source/metadata identity files. `reference-sources/README.md` is explicitly mutable documentation, not source identity evidence. The checker verifies the lock's own recorded digest, exact source inventory, lengths and digests; missing, changed, extra or symlinked source entries fail. The three original config/index/model-source digests remain independent anchors. A source update changes the lock/version through a recorded review, never by blindly accepting freshly computed hashes.

Disposable-copy negative checks mutate a vision helper, remove a processor source, add an unexpected file and alter the manifest; each must fail. The positive check must then pass on the original snapshots. Main source links use immutable revisions; moving URLs in historical research are discovery context only. No native-weight content verification is claimed by these metadata/source checks.

## 8. Gate dependencies and failure paths

| Gate | Required evidence and pass condition | On failure |
|---|---|---|
| Reference/fixture freeze | Locked snapshots; resolved runtime and kernel manifests; fixed materialized fixtures; source negative tests pass | Stop numerical qualification; repair identity/runtime setup |
| Arithmetic policy | Basic bit tests and ordered reductions pass; nonlinear manifest meets primitive targets; software profile meets every section-2 ceiling | Revise arithmetic/profile; rerun unchanged qualification; do not widen bounds automatically |
| ABI/ownership | Independent codec examples round-trip; invalid tables/IDs/aliases reject before writes; cancellation/quarantine tests pass | Correct protocol or driver; DMA hardware enablement remains blocked |
| Tiny full graph | All operators execute in RTL under ordinary and faulting memory; position/chunk/commit tests pass | Diagnose first divergence; no native-completion claim |
| Native-run admission | Source payload identity and storage/RAM budgets pass; measured time with margin <=48h/fixture or separately recorded execution plan; traces bounded | Improve host/simulator, provision storage, or defer full proof to validated hardware |
| Native fidelity | Actual named text/media fixtures and state checkpoints meet hard ceilings; complete-graph traces available | Keep scope unqualified; fix arithmetic/implementation and rerun |
| FPGA purchase/build | Supported host access, exact board collateral, host/board/accessory costs, target arithmetic/shell synthesis and entitlement resolved | Stay with free simulation; candidate board recommendation remains conditional |
| Hardware release | Exact ABI/bitstream/driver match; post-route timing/CDC; complete DDR/DMA and fatal-recovery tests; measured operating/thermal limits | Reduce clock/resources or repair implementation; no deployment-rate claim |

The critic reviews whether these gates are concrete and consistent. It does not replace the empirical evidence each gate requires.
