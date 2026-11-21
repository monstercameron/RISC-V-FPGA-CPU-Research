# CPU review rubric, revision 1

Adopted November 20, 2026. This rubric decides, in a review, whether we may call the CPU **good** and whether we may call it **performant**. Both words are claims. Each needs the gates and scores below, a stated scope and a named evidence class. A rubric score is a summary of evidence; it is never evidence by itself.

The rubric adds review criteria. It does not change the design contracts or the C0-C7 gates in the [CPU architecture](architecture.md), and it does not grant any ISA-profile, compatibility or certification statement.

## 1. How to run a review

1. Write the scope label (section 2).
2. Check the hard gates (section 4). A failed gate blocks the claim whatever the score.
3. Score every criterion from 0 to 4 using the anchors in section 5 and the bars in section 6.
4. Compute dimension scores and the total (section 7).
5. Decide which claims are allowed (section 8) and file the record (section 10).

Performance numbers must follow the measurement rules in section 9.

## 2. Scope label

Every review, and every sentence that repeats its conclusion, carries this label:

| Field | Content |
|---|---|
| ISA | Exact ISA string, for example `rv64i_zifencei`; nothing implied beyond it |
| Environment | Privilege modes implemented; laboratory terminal trap or real trap handlers |
| Class | Multicycle, in-order pipelined, or out-of-order |
| RTL identity | Commit and SHA-256 of every file under `rtl/cpu/` |
| Configuration | Parameter values; debug trace included or removed |
| Platform | Memory wrapper or bus, RAM size, added wait cycles |
| Hardware | Exact FPGA part and speed grade, board and PCB revision, tool and version; "none" for simulation-only reviews |
| Target | The clock frequency and throughput this core is expected to reach, set before measuring |

An unqualified "good CPU" needs at least machine-mode traps, CSRs and interrupts (gate C1). Before that, the strongest available wording names the limit, for example "good RV64I laboratory core".

## 3. Evidence classes

| Class | Name | Meaning |
|---|---|---|
| E0 | Stated | Design intent or documentation only |
| E1 | Local simulation | RTL simulation checked by project-written tests or the project reference model |
| E2 | Independent | Official architectural tests, lockstep comparison with an established external ISA model, or a formal proof |
| E3 | Implemented | Post-route results for the exact FPGA part with real constraints |
| E4 | Measured | Observed on a programmed board |

Each criterion names the minimum class needed to score 3. Evidence of a lower class caps that criterion at 2. Synthesis-only numbers without place and route are E0 for timing and E3 only for inference checks.

## 4. Hard gates

Gates for **good**:

| Gate | Requirement |
|---|---|
| HG1 | The scope label is complete and the RTL hashes are recorded. |
| HG2 | The full regression for the declared ISA passes on those hashes, rerun by the reviewer. |
| HG3 | Correctness is checked against something the project did not write: the official architectural tests for the ISA string pass, and an established external model agrees in lockstep. |
| HG4 | Every implemented trap cause is shown to be precise: correct PC, cause and value; the faulting instruction does not retire and has no side effect. |
| HG5 | Nothing unimplemented is advertised, in CSRs or in documents, and every unimplemented encoding traps. |
| HG6 | No correctness defect is open in the declared scope. The known-issue list was read during the review. |
| HG7 | A lint run and one synthesis run complete with no latches, combinational loops, multiply driven nets or unreviewed serious warnings. |
| HG8 | The reviewer reproduced the cited results from a clean checkout and is not the author of the change under review. |

Additional gates for **performant**:

| Gate | Requirement |
|---|---|
| PG1 | HG1-HG8 pass. A fast core that is not shown correct earns no performance claim. |
| PG2 | Post-route timing is met on the exact part at the declared clock, for setup and hold, with tool version and settings recorded. |
| PG3 | Benchmark results are valid under section 9. |
| PG4 | The RTL hashes behind the performance numbers equal those behind the correctness evidence. No benchmark-only configuration. |
| PG5 | At least one benchmark is measured on a programmed board and agrees with the post-route prediction within 10%. |

## 5. Scoring anchors

| Score | Meaning |
|---:|---|
| 0 | Absent. Not implemented, or no evidence. |
| 1 | Stated. E0 only, or evidence exists and shows failures. |
| 2 | Partial. Evidence below the required class, or it covers only part of the declared scope. |
| 3 | Meets. The "meets" bar is satisfied at the required class across the whole declared scope. |
| 4 | Exceeds. The "exceeds" bar is satisfied. |

Mark a criterion N/A only when it lies outside the declared scope and the scope label says so. N/A criteria are left out of the dimension average. They also limit the wording of the claim (section 8).

## 6. Dimensions and criteria

Nine dimensions, 100 points. Counts written as 1e6 mean one million.

### R1. Architectural correctness, 25 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R1.1 | Instruction semantics | Official architectural tests pass for every extension in the ISA string, and at least 1e6 retired instructions match an external model in lockstep | At least 1e8 lockstep instructions with no mismatch, or the instruction checks are formally proven | E2 |
| R1.2 | Decode legality | Every unimplemented or reserved encoding traps as illegal; at least 1e6 random 32-bit words plus directed reserved-field cases agree with the external model | Exhaustive or formally proven over all 32-bit encodings | E2 |
| R1.3 | Arithmetic corner cases | A written corner table per extension passes: sign extension of word results, shift-amount limits, extreme operands, and later divide-by-zero, overflow, NaN and rounding cases | Corners come from a coverage model and every bin is hit | E1 |
| R1.4 | Memory access semantics | Every width, byte lane and sign or zero extension is correct, and misaligned behaviour matches the declared platform policy | The policy is the one the claimed profile requires for main memory, checked against the external model | E1 |
| R1.5 | State invariants | x0 reads zero, the PC stays legally aligned and a trapping instruction changes no register or memory; checked by assertions active in every simulation | Formally proven | E1 |
| R1.6 | Completeness against the claim | Every mandatory item of the claimed ISA or profile has a ledger row naming its RTL and passing tests; nothing is claimed beyond the ledger | An independent reviewer audited the ledger against the ratified specification text | E1 |

### R2. Traps, interrupts, privilege and reset, 10 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R2.1 | Precise exceptions | Every implemented cause is triggered in a test with correct PC, cause and value, and no retirement of the faulting instruction | Priority among simultaneous exceptions matches the privileged specification, checked against the external model | E1 |
| R2.2 | Trap entry and return | Trap CSRs and `mret` behave as specified in handler firmware that resumes execution | Lockstep with the external model, including nested and back-to-back traps | E2 |
| R2.3 | Interrupts | Taken only at instruction boundaries, including while pending during memory stalls; enables, masks and priority verified; worst-case latency in clocks stated and tested | Random interrupt injection in lockstep with the external model for at least 1e6 instructions | E2 |
| R2.4 | CSRs | Reset value, writable bits and side effects of every implemented CSR are checked; access to an unimplemented or insufficiently privileged CSR traps | Field-by-field comparison with the external model | E2 |
| R2.5 | Reset | All architectural and control state is defined after reset; reset asserted in every control state and in the middle of a transaction, then a program runs correctly | Simulation from unknown initial values shows nothing unknown reaching an output after reset, or the property is proven | E1 |
| R2.6 | Data-independent timing | Instructions listed by a claimed timing extension take the same number of clocks for all operand classes | Proven, or measured over an exhaustive operand classification | E1 |

R2.2-R2.4 are N/A for a laboratory terminal-trap core. R2.6 is N/A until such an extension is claimed.

### R3. Verification depth and independence, 15 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R3.1 | Oracle independence | An established external model is the comparison oracle for the regression | Two independent oracles, or one plus formal proof | E2 |
| R3.2 | Functional coverage | The suite fails unless every declared instruction, both outcomes of every branch, every trap cause and every access width and lane is hit | Cross coverage of instruction class, memory wait pattern and injected fault, with every bin hit | E1 |
| R3.3 | Structural coverage | At least 95% line coverage and 100% of control states and legal transitions; each exclusion justified in writing | At least 99% line and 90% toggle coverage | E1 |
| R3.4 | Random testing volume | At least 1e6 random instructions drawn from the whole declared ISA, including loads, stores, branches and jumps, under random waits and faults | At least 1e8, with scheduled recurring runs | E1 |
| R3.5 | Formal verification | Bus-protocol properties and the R1.5 invariants pass bounded model checking to a stated depth | A complete riscv-formal run: instruction, PC, register, liveness and uniqueness checks | E2 |
| R3.6 | Fault detection | At least 20 deliberately injected RTL defects, spread over decode, ALU, load/store and control, are all caught by the suite | Automated mutation testing with at least 95% of mutants caught | E1 |
| R3.7 | Regression discipline | The full suite runs in CI on every change and each recorded result names the RTL hashes it covers | A longer scheduled run with a kept history | E1 |

### R4. Performance, 20 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R4.1 | Clocks per instruction on the benchmark set, through the real memory wrapper | At or under the class "meets" value below | At or under the class "exceeds" value | E1 |
| R4.2 | Benchmark efficiency, CoreMark per MHz | At or over the class "meets" value | At or over the class "exceeds" value | E1 |
| R4.3 | Clock frequency | Post-route timing met on the exact part at the declared clock, which is at least the 50 MHz starting target in the architecture document; setup and hold slack not negative | Setup slack of at least 10% of the period on each of three placement seeds | E3 |
| R4.4 | Absolute throughput | Benchmark score at the achieved frequency is reported and reaches the target in the scope label | Measured on the board within 5% of the post-route prediction | E3 |
| R4.5 | Latency accounting | The cost in clocks of each instruction class, taken branch, load, store and any long operation is documented and matches measurement | Worst-case interrupt latency is also measured, once interrupts are in scope | E1 |
| R4.6 | Sensitivity to memory latency | Clocks per instruction reported at 0, 1, 2 and 4 added wait cycles | Also reported with the intended board memory | E1 |
| R4.7 | Performance per area | CoreMark per MHz per 1,000 LUTs is reported beside the comparator built with the same tool, part and settings | At least equal to the comparator | E3 |
| R4.8 | Regression tracking | Cycle counts for the fixed benchmark set are recorded per RTL hash, and any change over 2% is explained | An automated check fails on an unexplained regression | E1 |

Class values for R4.1 and R4.2:

| Class | Clocks per instruction: meets / exceeds | CoreMark per MHz: meets / exceeds |
|---|---:|---:|
| Multicycle | 4.0 / 3.0 | 0.4 / 0.8 |
| In-order pipelined | 1.6 / 1.3 | 2.0 / 3.0 |
| Out-of-order | 1.0 / 0.7 | 4.0 / 6.0 |

These values are project-chosen starting points, not measurements of other cores. Recalibrate them at the first review that has a comparator built under section 9, and record the change as a new rubric revision. They apply to the ISA as built: a core without the M extension runs CoreMark with software multiplication and must say so.

### R5. FPGA implementation quality, 12 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R5.1 | Resource use | Post-route LUT, flip-flop, block RAM and DSP counts on the exact part, with and without debug trace and broken down by module; at least 30% of each resource left free | At least 50% left free | E3 |
| R5.2 | Inference as intended | Reports confirm RAM maps to block RAM and the register file maps as designed, with no latches, combinational loops or multiply driven nets | The same result from a second toolchain | E3 |
| R5.3 | Constraints | Every clock constrained, no unconstrained endpoints, I/O timing constrained and every timing exception justified in writing | Constraints checked by a second person and the tool's methodology report is clean | E3 |
| R5.4 | Critical path | The ten worst setup paths are listed with start, end and logic levels, and each is an intended path | A recorded experiment shows what limits the frequency and the measured effect of changing it | E3 |
| R5.5 | Reset and clock crossings | External reset is synchronized; with more than one clock, the crossing report has no unwaived violation; reset fanout reviewed | At least 1,000 reset or power cycles on the board with no failed start | E3 |
| R5.6 | Power | Tool estimate driven by switching activity from a benchmark simulation | Measured on the board while running the benchmark | E3 |
| R5.7 | Portability | The core builds unmodified in one complete flow, with no vendor primitive inside the core | Builds unmodified in two flows or two FPGA families | E3 |

### R6. Interfaces and integration, 8 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R6.1 | Bus protocol | Requests stay stable while stalled, one transaction is outstanding at a time and nothing is issued after a terminal trap; checked by assertions in every simulation | Formally proven | E1 |
| R6.2 | Backpressure | Correct under random waits, including a stall of at least 1,000 clocks for fetch, load and store; no silent timeout in the core | Also correct under adversarial response patterns from constrained-random or formal stimulus | E1 |
| R6.3 | Error responses | Fetch, load and store errors each produce the right precise trap with no memory side effect | Errors injected at random points over at least 1e5 transactions, checked against the oracle | E1 |
| R6.4 | Side-effect safety | The core never issues a read wider than the access into a region with read side effects, and access size and type are visible to the adapter | Verified with a memory-mapped peripheral model in simulation and on the board | E1 |
| R6.5 | Parameters | Every exposed parameter is tested at two or more values, including a non-default one | Illegal values are rejected at elaboration | E1 |
| R6.6 | Toolchain compatibility | Unmodified upstream compiler output for the declared `-march` and `-mabi` runs, including the benchmark set | An unmodified RTOS or operating system suited to the scope boots | E1 |

### R7. Observability and debug, 4 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R7.1 | Retirement trace | Per retired instruction: PC, instruction, source values, destination and value, memory address, mask and data, trap and interrupt flags | Standard RVFI signals connected to riscv-formal | E1 |
| R7.2 | Trap diagnostics | Cause, PC and value stay stable and externally readable after any trap | Readable on the board through a UART or debug port | E1 |
| R7.3 | Debug access | Halt, single step and register and memory access through a documented path on the board | A debug module following the RISC-V debug specification works with a standard debugger | E4 |
| R7.4 | Cost of visibility | Trace logic can be removed by a parameter, with area and timing reported both ways | Removing it changes no architectural behaviour, shown by rerunning the regression | E3 |

R7.3 is N/A for simulation-only reviews.

### R8. Design quality and maintainability, 3 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R8.1 | Lint | A dedicated lint run and the simulator's full warnings show nothing unwaived | The synthesis tool also reports no unwaived serious warning | E1 |
| R8.2 | Synthesizable style | Files under `rtl/` use only synthesizable constructs and contain no simulation-only behaviour | Accepted unchanged by a second synthesis front end | E1 |
| R8.3 | Documents match RTL | States, signals, trap causes and contracts in the architecture document match the RTL at the reviewed commit, checked item by item | The check is automated | E1 |
| R8.4 | Structure for growth | Long operations sit behind start, busy, done and error interfaces, and adding an extension does not change retirement order | Shown by an extension added since the previous review without rewriting the control state machine | E1 |

### R9. Reproducibility and claim hygiene, 3 points

| ID | Criterion | Meets (3) | Exceeds (4) | Class |
|---|---|---|---|---|
| R9.1 | Reproduction | Documented commands reproduce every cited result from a clean checkout, and the reviewer ran them | Reproduced on a second machine or in CI | E1 |
| R9.2 | Identity | Tool versions, compiler flags, RTL hashes and firmware hashes are recorded with each result | Results are rejected automatically when a recorded hash no longer matches | E1 |
| R9.3 | Claim wording | Every public statement carries the scope label and evidence class, with limitations beside the result | A second reader found no statement stronger than its evidence | E1 |
| R9.4 | Review independence | Scored by someone other than the author of the change | Two independent reviewers reconciled their scores | E1 |

## 7. Computing the score

For each dimension:

```text
dimension score = weight x (sum of criterion scores) / (4 x number of scored criteria)
```

The total is the sum of the nine dimension scores, reported to one decimal place. Example: R7 scored 3, 3, N/A and 2 gives 4 x 8 / 12 = 2.7 of 4 points. Report each dimension as points and as a percentage of its weight.

## 8. What may be claimed

| Claim | Requirements |
|---|---|
| "Verified in simulation" | HG1, HG2, HG4, HG5 and HG6 pass; R1 at least 60% and R3 at least 50%. Must be worded with class E1 and the oracle named. |
| "Good", with its scope label | HG1-HG8 pass; total at least 75; R1 at least 80% with no R1 criterion under 3; R2, R3 and R6 each at least 70%; no dimension under 50%. |
| "Performant for a <class> FPGA core" | "Good" is granted; PG1-PG5 pass; R4 at least 75% with R4.1, R4.2 and R4.3 each at least 3; R5 at least 60%. |
| "Performant" or "fast" without a class qualifier | The line above, in the in-order pipelined class or better, with R4 at least 85%. |

The total also gives a progress band, which is a description and not a claim: under 40 foundation, 40-59 developing, 60-74 solid, 75-89 good, 90 and over excellent. Without the gates, quote the band only together with the failed gates.

Wording allowed by evidence class, whatever the score:

| Class | Example of permitted wording |
|---|---|
| E1 | "Passes N local differential simulations against the project reference model"; "X clocks per instruction in simulation on workload W" |
| E2 | "Matches <model> over N instructions"; "passes the architectural tests for <ISA string>" |
| E3 | "Post-route estimate: F MHz and U LUTs on <exact part>" |
| E4 | "Measured on <board>: ..." |

Without the matching claim above, do not write "good", "performant", "fast", "production ready", "compliant" or "certified" about the CPU. Profile statements such as RVA23 remain governed by the ledger in the [architecture document](architecture.md), section 5.

## 9. Benchmark and measurement rules

- **Workloads.** [CoreMark](https://github.com/eembc/coremark) is the primary benchmark and [Embench-IoT](https://github.com/embench/embench-iot) the secondary one. The project's own C demo and lessons are for regression tracking only. Dhrystone is optional and never the only number.
- **Build.** Compile for exactly the declared ISA string and ABI. Record compiler, version and every flag. Use the same binary in simulation and on the board.
- **Validity.** The benchmark's self-check must pass. Follow the benchmark's own run and reporting rules; a run that cannot, such as a shortened simulation run, is labelled "non-compliant run, simulation".
- **Counting.** Clocks per instruction is the number of clocks between the benchmark's start and stop markers divided by the instructions retired between the same markers, taken from the retirement trace. Reset and startup code are excluded.
- **Per-MHz and absolute scores.** Per-MHz scores from simulation cycle counts are class E1, because they do not depend on the clock period. Absolute scores need a post-route frequency (E3) or a board measurement (E4).
- **Frequency.** Post-route only, on the exact part and speed grade, at the slowest corner the tool reports. Record the constraint, worst setup slack, worst hold slack, tool version and strategy.
- **Memory.** State RAM size, wrapper and wait cycles. The default 16 KiB RAM may be too small for a benchmark; `RAM_WORDS` is a parameter and its value is part of the result.
- **Timing source.** Until the core has a cycle counter, time hardware runs with an external counter and say so.
- **Same design.** State whether debug trace was included. PG4 forbids a benchmark-only configuration.
- **Comparator.** Build the vendored [PicoRV32](../sim/starter/vendor/picorv32.v), or another named open core, with the same tool, part and settings, and record its configuration and results. PicoRV32 is a 32-bit core, so this is a reference point and not a pass mark. Published numbers for other cores may be quoted only with source and date, and are not like-for-like.

Tools commonly used for class E2: [riscv-arch-test](https://github.com/riscv-non-isa/riscv-arch-test), [Spike](https://github.com/riscv-software-src/riscv-isa-sim), the [Sail RISC-V model](https://github.com/riscv/sail-riscv) and [riscv-formal](https://github.com/YosysHQ/riscv-formal). Record the exact revision of whichever is used.

## 10. Review record

File each review as `cpu/reviews/<date>-<short commit>.md` and keep earlier records. Use this outline:

```text
Scope label: all eight fields from section 2
Reviewers and their relation to the change
Commands rerun, with tool versions and result
Gates: HG1-HG8 and PG1-PG5, each pass or fail with evidence
Scores: every criterion, 0-4 or N/A, each with an evidence link
Dimension scores and total
Claims granted, in their exact permitted wording
Findings: ID, severity, criterion affected, closure condition
Pending evidence and the next gate
```

Between reviews, [rubric-evidence.json](rubric-evidence.json) holds the current self-assessment of every gate and criterion. Each Dhrystone run computes a scorecard from it, scoring R4.1, HG2 and PG1 from the run and local records, and appends it to the development log. That scorecard is a progress measure; it is not a review record and cannot satisfy HG8 or R9.4.

A review applies only to the recorded RTL hashes. Any RTL change voids the R1-R6 scores until the regression is rerun on the new hashes, and a change to decode, arithmetic, load/store or control needs the affected criteria scored again. A change of FPGA part, tool version or constraints voids R4.3, R4.4, R4.7 and R5. An earlier review's score is never inherited.

## 11. Where revision 0 stands

This is the author's reading of the hard gates on November 20, 2026 at commit `0483d99`, with scope `rv64i_zifencei`, laboratory terminal trap, multicycle, simulation only. It is not an independent review and assigns no score.

| Gate | Status | Evidence or gap |
|---|---|---|
| HG1 | Met | Scope in the [architecture document](architecture.md); RTL hashes in the [verification record](verification.json) |
| HG2 | Met at class E1 | The 96 default runs plus reset and RAM-wrapper checks passed when rerun on this date; the record lists 99 with compiled firmware |
| HG3 | Not met | The reference model is project-written; external model comparison and architectural tests are pending |
| HG4 | Met for the terminal trap record | Causes 0-7 and 11 are each triggered by the [suite](../sim/cpu/test_cpu.py); there is no architectural trap handling yet |
| HG5 | Met | No capability CSR exists; multiply and CSR encodings are tested to trap |
| HG6 | Open | No correctness issue is recorded, but no known-issue list exists to review |
| HG7 | Not met | Only an Icarus compile with full warnings; no dedicated lint or synthesis run |
| HG8 | Not met | No independent reviewer has reproduced the results |
| PG1-PG5 | Not met | No synthesis, timing, benchmark or board result exists |

Consequences:

- Neither "good" nor "performant" may be claimed. The wording available today is class E1.
- One indicative number exists: the C demo retires 22,674 instructions in 69,157 clocks through the RAM wrapper, about 3.05 clocks per instruction (see the [C demo record](c-demo.md)). It counts startup code and is not a section 9 benchmark result.
- Known gaps against R3: the random programs draw only from register and immediate arithmetic, and there is no structural coverage, formal or mutation evidence.
- The shortest route to the first scored review is a lint and exact-part synthesis run (HG7, R5), an external model in the regression (HG3, R1, R3), then the C1 environment for an unqualified claim.
