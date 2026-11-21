# Adversarial refinement record

**Completed: three independent review rounds, 13 findings closed, final score10/10 with no actionable planning findings.** Ratings progressed7/10 ->8.5/10 ->10/10. The final review is [saved verbatim](critic-round-3.md), with [reviewed artifact hashes](critic-round3-reviewed-hashes.json).

Scope: implementation-plan quality for the complete Qwen3.8-27B text/vision FPGA accelerator. A review score is not evidence that RTL, numerical quality or hardware performance has passed. The critic is an independent subagent instructed to inspect source and artifacts, challenge every relevant dimension, and withhold 10/10 while actionable plan issues remain.

## Round 1: 7/10

The critic verified the main dimension/traffic calculations and identified eight actionable findings:

| ID | Severity | Finding | Closure status |
|---|---|---|---|
| C01 | High | Actual ARM workstation, RAM and disk do not support the assumed Vivado/full-checkpoint path | Implementation contract section 1 and measured host inventory; independently closed by round3 |
| C02 | High | Calibration-defined tolerances have no independent model-fidelity ceilings | Contract section 2 and fixed qualification fixtures; independently closed by round3 |
| C03 | High | Lost DMA responses/link loss can defeat drain and make buffer release unsafe | Contract section 5; ABI terminal-result/ownership rules; independently closed by round3 |
| C04 | High | Full-prompt multimodal positions are not specified across token/chunk schedules | Contract section 4; ABI media/input lifetime; independently closed by round3 |
| C05 | Medium | Fixed ABI omits operation-specific payload, cancellation and table details | ABI 1, byte codec and rejection examples; generation opcode disabled; independently closed by round3 |
| C06 | Medium | Most frozen-source files are rehashed rather than checked against fixed expected hashes | 16-file anchored source lock with four negative tests; independently closed by round3 |
| C07 | Medium | BF16-P0 lacks complete deterministic arithmetic/reduction ordering | Contract section 3 ordered arithmetic and manifest gates; independently closed by round3 |
| C08 | Medium | Native VL runtime ignores the mandatory visual-token prefill length | Contract section 6 and executable whole-workload lower bounds; independently closed by round3 |

Round-1 baseline copies and hashes are retained in `work/refinement-baseline/` and `work/refinement-round-0-hashes.json` in the working chat. Subsequent entries below record the independent findings and ratings after each revision.

## Round 2 submission

All eight findings have concrete revisions. Current documents were reconciled to remove earlier conflicting tolerance, generation, commit and host assumptions. `refinement-checks.json` records passing planning tests; no native-model/RTL/driver result is claimed. The independent critic returned **8.5/10**. Both check programs passed in its own runs; C01/C03/C04/C06/C07/C08 and C02’s ceilings were accepted. C05 required further lifecycle/interface refinement.

## Round 2: 8.5/10; five further findings

| ID | Severity | Finding | Revision for round 3 |
|---|---|---|---|
| C09 | High | Reset leaves mutable region ownership at old epoch | Atomic all-owner epoch publication after successful clear; failed-reset metadata unchanged; retry/stale/wrap cases |
| C10 | High | Missing session/upload/weight-service transport | Adapter1 register/record definitions, COPY/SEAL, nonce init, tagged byte service, SG/stage credits and cancellation lifecycle |
| C11 | Medium | Ambiguous INPUT pointers and run versus pixel-item counts | Sealed kind8 tensor arena, exact typed offsets/counts, four-run/one-pixel-tensor byte fixture and pointer rejection checks |
| C12 | Medium | Random-only text and unspecified media comparison positions | Version2 fixed semantic/stress cases; all media positions and fixed state checkpoints; unchanged fidelity ceilings |
| C13 | Low | Conflicting U1/U8 starting order | Main plan now U1 first, qualified U8 next, optional U16 later |

Round3 submission: `adapter-v1.md`, updated ABI/codec, `abi-lifecycle-example.json`, fixture revision2 and reconciled docs. Required hardware/RTL lifecycle tests remain gates. The executable metadata/encoding examples are planning checks only. Independent round3 review accepted all C09–C13 fixes and found no regression.

## Round 3: 10/10 — accepted

The critic independently reread the normative contracts, checked the revisions against the main/memory/resource plans and ran both check programs successfully. Its exact conclusion:

> Round 3: 10/10 for the implementation plan. No actionable planning findings remain.

All C01–C13 are closed. The final artifact identities match the critic’s recorded SHA256 values. Both check programs passed again during delivery verification. The revised current documents and evidence were synchronized to the Desktop research project; earlier CPU/FFN research remains preserved.

The accepted plan still requires actual numerical kernels/constants, runtime/processor materialization, RTL/parser/driver implementation, native-model fidelity, supported-host access and physical synthesis/memory/DMA/thermal evidence. Those are explicit implementation gates, not omitted work or achieved results. A10/10 plan review does not predict measured resource use or performance.
