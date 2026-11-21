# Development log

A dated record of work sessions: what was done, the commits that came out of it, and what was learned. Newest day first.

Detailed run records live in [devlog/](devlog/), one file per commit (`devlog-<commit>.md`), so this file stays small. The [run index](#run-logs) at the end lists every run with a link to its record.

Every experiment must be recorded here, as [AGENTS.md](AGENTS.md) requires: simulations, regressions, benchmarks, synthesis or timing runs, board tests, tool installs, and failed or abandoned trials. Give the time and its source, the goal, exact commands, tool versions, the commit hash or "uncommitted", results with units, and the conclusion. Add to the log; do not rewrite earlier entries except to correct a fact, and say so when you do.

Times are US Eastern (UTC-05:00). Each timestamp names its source:

| Source | Meaning |
|---|---|
| git | Author time recorded in the commit |
| CI | GitHub Actions run start and finish |
| apt | Ubuntu's package history log |
| record | Timestamp written into a result file |
| file | File modification time on the workstation |
| output | Printed by a command during the session |
| approx. | Inferred from the order of events; no record exists |

---

## 2026-11-21: slot-3 branch trial, validation of 0.7.1, pipelining plan

### Findings

- A third-slot conditional branch does not pay: it moves branches from the start of a group to the end of the previous one, but a branch at the start of a group already folds its target into the second slot, so the clock count barely changes (+0.4% DMIPS/MHz). Dropped.
- The independent review of 0.7.1 found no bug in the committed design but a missing test: allowing a multiply to pair (the pre-0.7.1 rule) puts a store on the bus early, and the regression did not notice. The test is now in the regression and catches it.
- Absolute performance, not DMIPS/MHz, decides the next steps: 0.3.0 reaches 22.49 MHz on ECP5 (about 21 DMIPS), with 79% of its critical path in routing. A pipelining plan was drafted (below); its figures are estimates until measured.

### Timeline

| Time | Event | Source |
|---|---|---|
| 00:00 to 00:02 | Candidate 0.7.2 written: conditional branch in the third slot (compare on the third slot's operands, target `pc3 + imm`, taken target misaligned does not issue there; the group's successor is the branch's outcome). New tests `triple_branch`, `triple_branch_misaligned`. Testbench `tb_core.sv` now counts second-slot, third-slot and third-slot-branch retirements on its DONE line, and `test_cpu.py` checks that `dual_issue_fold` and `triple_issue` use their slot (default caches, no wait cycles) | output |
| 00:02:25 | Regression: 52 programs x 3 wait patterns = 156 runs pass with default caches (15.7 s) and with 2-line caches (11.8 s); `triple_branch` retires 2 branches from the third slot | output |
| 00:04:31 | Unlogged Dhrystone run on the candidate (`rv64imb`, reference runtime, `-NoDevlog`): 2.2250 DMIPS/MHz, 255.8 clocks per run against 256.8 (-0.4%) | output |
| about 00:06 | Blocker count on the candidate's trace (a scratch script groups the measured profile trace into issue groups): pairs stopped by a third-slot branch fell from 36.0 to 3.0 per run, but pairs stopped by a third-slot store rose from 18.0 to 48.0; triples rose by only 1.0 per run. The branch used to start the next group and fold its target into the second slot; now that target starts a group of its own. Candidate reverted; tests kept as plain differential tests | output |
| 00:00 to 00:07 | Independent validation of 0.7.1 by a review agent in a separate worktree at `c1b113f`: regression 150/150 (14.1 s) and 150/150 with 2-line caches (12.3 s); `check_bitmanip.py` passes (6.3 s, 28 B instructions, 33,124 and 15,003 retired); visualizer lessons pass after a rebuild (15.9 s); `check_repo.py` passes; RTL hashes, `cpu/VERSION`, tag and the 0.7.1 run rows agree with the records. No bug found in the multiply path. Mutants: reverting the pairing rule (`!m_op` to `!is_div`) passed the whole regression; three other multiply mutants were caught. Its focused scratch test caught the first. Tools: Icarus Verilog 12.0, Python 3.12.3 (WSL) and 3.12.10 (Windows), clang 18.1.3 (WSL) and 23.1.5 (Windows) | output |
| 00:07 | Review follow-ups: new tests `mul_then_store_pad0`, `mul_then_store_pad1` (a store after each multiply kind) and `mul_into_x0`; regression 55 programs x 3 = 165 runs pass with default and 2-line caches; with the pairing mutant applied, `mul_then_store_pad1` fails at event 14 (a store's W line before the multiply's R line). `runlog.py` no longer strips the leading space of `git status` output, which had cut the first character from the first dirty file name in run logs (for example "`EVLOG.md`"). `cpu/architecture.md` now lists the DIVIDE and MULTIPLY states and excludes multiplies from first-slot pairing in its text. Also reported: `cpu/programs-verification.json` and `cpu/visualizer-verification.json` still hold the RTL hashes of the initial commit (the regenerated copies in the working tree are current), and `cpu/dhrystone-rv64im-fastrt-results.json` is still the 0.6.0 run | output |
| about 00:05 | Pipelining plan drafted by a planning agent from the RTL and the measurements: five short stages (PC, cache read, decode and register read, execute, memory and retire), instruction and data caches in block RAM, register file in LUT RAM (two copies for two read ports; a live-value table for two-wide), forwarding from two registered stages, static then BTB prediction, two-wide issue at most (slot 3 dropped), traps acted on at retirement. Estimates, not measurements: single-issue pipeline about 0.8 DMIPS/MHz at 60 to 75 MHz; two-wide about 1.3 DMIPS/MHz at 50 to 60 MHz (65 to 80 DMIPS, against about 21 for 0.3.0) | output |
| 00:07:44 | ECP5 synthesis of 0.7.0 and 0.7.1 still running after 30 minutes in Yosys `synth_ecp5` (0.3.0 took 59.5 s) | output |
| 00:08:39 | Commit `15074b8`: multiply-pairing and slot-use tests, slot-3 branch trial record, `runlog.py` fix | git |
| 00:09 to 00:13 | Pipeline what-if model `sim/cpu/bench/pipeline_model.py` (written by a side agent; Python 3.12.10) replayed the measured Dhrystone traces through an in-order pipeline with configurable prediction, width and stalls (instruction and data caches assumed to hit; redirect from E costs 3 bubbles, from D 2). Note: the `rv64imb` trace it read came from the reverted slot-3 branch candidate (255.8 clocks per run, against 256.8 for 0.7.1). `rv64imb` reference, clocks per run: single issue, not-taken 858.1 (0.663 DMIPS/MHz); static 813.1 (0.700); 64-entry BTB with a 4-entry return stack 639.3 (0.890); perfect prediction 579.1 (0.983); two-wide with a 64-entry BTB 465.2 (1.223); two-wide with perfect prediction 405.1 (1.405). Branch handling is the largest lever (about 279 of 858 clocks are control penalties without prediction); two-wide issue saves 145 to 175. Break-even: even two-wide with perfect prediction needs 1.58x the clocks of the measured core, single issue with a 64-entry BTB 2.50x, so a pipeline only wins if its clock is that much faster. Command: `python -B sim/cpu/bench/pipeline_model.py` plus sensitivity runs (BTB 32 to 256 entries, return stack 4 to 16 (no difference), tagless BTB, no late store data, fixed divide cost) | output |
| 00:12 to 00:19 | Branch `pipeline` created from `15074b8`. Candidate 0.8.0 written: `rv64_core.sv` replaced by a four-stage single-issue pipeline (F: registered instruction-cache read with fill bypass; D: register read, JAL and backward branches redirect F (1 bubble); E: execute, forwarding from M's integer result and from the last retirement, mispredict redirect (2 bubbles); M: data cache read registered as the instruction enters M, bus access, retirement, traps). Load or multiply result used by the next instruction: 1 clock; store data from a load is taken in M without a stall. A store to the beat of a younger fetched instruction flushes and refetches; traps wait until no fetch is outstanding. Register file has no reset loop; a sequencer zeroes it in 32 clocks after reset. Decode, B, multiply and divide logic reused; ports and trace unchanged (retire2/retire3 stay 0). `test_cpu.py` slot-use checks emptied on this branch (single issue) | output |
| 00:17 to 00:19 | Pipeline candidate: compiles with `iverilog -g2012 -Wall` without warnings; regression 55 programs x 3 = 165 runs pass on the first full run with default caches and with 2-line caches; `check_bitmanip.py` passes. Unlogged Dhrystone (`rv64imb`, reference runtime): **0.7944 DMIPS/MHz**, about 716 clocks per run (0.7.1: 2.2163). Better than the model's 0.700 for static prediction because this design's redirects cost 1 and 2 bubbles, not 2 and 3 | output |
| 00:20:37 | ECP5 runs started for the pipeline candidate (snapshot `build/cpu/synth/p080a.sv`): 4-line caches, and default 512-line caches to check block-RAM inference. The 0.7.0 and 0.7.1 runs are still in Yosys after 42 minutes | output |
| 00:21 to 00:23 | Pipeline candidate with a branch target buffer (64 entries, direct-mapped on pc[7:2], 10-bit partial tags, 2-bit counters, a return flag) read in F, and a 4-entry return-address stack updated in E; D's static prediction is kept for BTB misses. Regression 165/165 with default and 2-line caches. Unlogged Dhrystone (`rv64imb`, reference): **0.9216 DMIPS/MHz**, about 618 clocks per run (+16% over 0.7944; model 0.890 with 3-bubble redirects) | output |
| 00:24:29 | Yosys `synth_ecp5` of the first pipeline candidate (no BTB): 4-line caches 15,171 LUT4, 1,323 CCU2C, 141 TRELLIS_DPR16X4 (register file in LUT RAM), 16 MULT18X18D, 1,985 flip-flops (0.3.0: 22,887 LUT4, 3,662 flip-flops); default 512-line caches add 10 DP16KD block RAMs (caches inferred as block RAM), 19,844 LUT4, 3,104 flip-flops. Place and route running | output |
| 00:24:45 | Commit `ba38182` on branch `pipeline`: pipeline candidate with BTB, and the pipeline model (not versioned; local only) | git |
| 00:26:26 | Return stack moved from E to D (calls push and returns pop as they leave D; a return in F can take the target of a call leaving D in the same clock). Regression 165/165 (default and 2-line caches). Unlogged Dhrystone: 0.9216 DMIPS/MHz, unchanged: the remaining JALR misses are not return-stack timing (the model attributes them to BTB conflicts) | output |
| about 00:26 | ECP5 place and route of the first pipeline candidate (`p080a`, no BTB; LFE5U-85F speed 6, seed 1): **21.09 MHz** with 512-line caches (23,072 of 83,640 cells; critical path 47.4 ns, 16.5 ns logic, 30.9 ns routing) and **19.87 MHz** with 4-line caches (18,861 cells; 17.4 ns logic, 32.9 ns routing). No faster than 0.3.0 (22.49 MHz): the critical path runs from M's exception flag through the stall logic and E's operand forwarding into the divider's set-up (operand magnitudes, leading-zero counts, early results) and on to M's result register | output |
| 00:27 to 00:29 | Divider set-up moved from E to M: divide operands are registered as the instruction enters M; M's first clock completes the early cases or sets up the loop. E's result for multiply and divide is now 0. Regression 165/165 (default and 2-line caches); unlogged Dhrystone 0.9202 DMIPS/MHz (one more clock per divide). ECP5 runs of the BTB version (`p080b`) were stopped as superseded; `p080c` (this version, 512-line caches) started at 00:31:17 | output |
| 00:31 to 00:34 | 256-entry BTB tried in simulation: 0.9670 DMIPS/MHz (+5% over 64 entries, as the model predicted from conflict misses); kept, with only target bits 31:2 stored (upper bits from the PC; a target in another 4 GiB region is mispredicted and corrected in E). Regression 165/165 with default and 2-line caches; Dhrystone 0.9670 unchanged by the compression | output |
| about 00:35 | On request, work moved back to `main`: the uncommitted pipeline changes were stashed, `main` fast-forwarded from `15074b8` to the branch's one commit `ba38182`, and the stash restored. `origin/main` was already at `15074b8`, pushed from outside this session. Then, on `main`: the pipelined core moved to its own file `rtl/cpu/rv64_pipe.sv` and `rtl/cpu/rv64_core.sv` restored byte for byte to 0.7.1 (SHA-256 `dd153c8d...`), so both implementations are kept. `test_cpu.py`, `check_bitmanip.py`, `run_bench.py` and `run_dhrystone.ps1` take `--core multicycle|pipe` (default multicycle); pipe runs use build folders and records ending in `-pipe`, and run logs and trends keep the two cores apart | output |
| about 00:38 | Both cores, regression 55 programs x 3 = 165 runs with default and 2-line caches, and `check_bitmanip.py`: all pass (`build/cpu/regress_both.sh`) | output |
| 00:40:17 | `origin/main` found at `ba38182`: the pipeline commit had been pushed from outside this session's commands after the fast-forward | git |
| about 00:40 | Recorded as architecture 0.8.0 (MINOR: a second implementation whose instruction fetches are speculative, visible on the bus; ISA, ports and trace unchanged). `cpu/architecture.md` describes the pipelined implementation | output |
| 00:40:29 | Commit `53c6772`, both cores on `main` (0.8.0); tagged `cpu-v0.8.0` | git |
| 00:40 to 00:43 | Logged runs, pipelined core (`--core pipe`, `-Record`): `rv64imb` reference **0.9670 DMIPS/MHz**, fast runtime **1.1744**; [devlog-53c6772.md](devlog/devlog-53c6772.md) | record |
| about 00:43 | ECP5 place and route of the pipeline with the divider set-up in M (`p080c`, 64-entry BTB, 512-line caches): **24.30 MHz** (from 21.09), 25,039 cells, 456.5 s; critical path 41.2 ns (12.3 ns logic, 28.9 ns routing) from the data-cache tag block RAM through M's hit check, M's completion, E's and D's advance and the next-fetch-PC select into `f_pc`. The stall decision runs the length of the pipeline in one clock and its enables drive hundreds of flip-flops. Estimate: 0.3.0 21.3 DMIPS (22.49 MHz x 0.9473); this pipeline about 23 DMIPS (24.3 MHz x 0.9670 for the 256-entry BTB, whose own clock is not yet measured). Next: decouple fetch from the stall chain | output |
| 00:44 to 00:47 | Candidate 0.8.1, step 1 (`rv64_pipe.sv`): fetch decoupled from the stall chain. A 4-entry fetch queue sits between F and D (D takes F's instruction directly when the queue is empty); F advances whenever the queue is not full, a registered condition. E and D redirects are sent once, as soon as the stage knows, instead of when the stage advances (E waits for valid operands first). Store-to-fetched-beat and `fence.i` flushes are registered and act one clock after the retirement, discarding everything younger, including an instruction that entered M at that edge; the check also covers queue entries. The return stack moved to F (calls and returns update it as they are fetched). Regression (pipe core) 165/165 with default and 2-line caches; Dhrystone 0.9670, unchanged. A first attempt to start its ECP5 run died silently: a background job started from a WSL command that exited at once did not survive; later jobs wait a few seconds before the command exits | output |
| 00:49 to 00:53 | Step 2: X stage. M finishes its instruction in one clock without waiting: it retires it (integer result, load hit, multiply, or a bus access completed in that clock) or hands an unfinished bus access to X, which holds the identical request until the bus completes and then retires it; M waits while X is busy. So whether E may advance depends only on registers (X busy, divide still running), not on the data-cache hit; a bus error in M's first clock traps from X one clock later. Divides always take their set-up clock. X's data-cache write also updates the line M already read. Regression 165/165 (default and 2-line caches), B cross-check passes, Dhrystone 0.9670 | output |
| about 00:55 | ECP5 result for the tagged 0.8.0 pipelined core (`p080d`, 512-line caches): **28.00 MHz**, 27,495 cells, 348.1 s; critical path 35.7 ns (13.8 ns logic, 21.9 ns routing) from E's instruction through operand forwarding, the load/store misalignment check, E's exception flag and E's mispredict redirect into the next-fetch-PC select and the instruction-cache block-RAM address. About 27 DMIPS (28.0 x 0.9670) against about 21 for 0.3.0: the first absolute gain | output |
| 00:55 to 00:57 | Step 3: redirect checks split between D and E. D compares fetch's prediction with what it can compute itself (JAL target; conditional-branch target with the BTB's direction, or taken if backward without a BTB entry; fall-through for anything else; JALR keeps the prediction) and redirects once on a mismatch. E checks only a conditional branch's direction and a JALR's target, and no longer waits for its exception flag (a faulting instruction traps in M either way). Regression 165/165 (default and 2-line caches), B cross-check passes, Dhrystone 0.9670. ECP5 runs of steps 1, 2 and 3 (`p081a`, `p081b`, `p081c`) started | output |
| about 00:59 | ECP5 result for step 1 alone (`p081a`): **25.67 MHz**, 28,026 cells, critical path 39.0 ns (9.1 ns logic, 29.9 ns routing), slower than 0.8.0's 28.00. The path runs from the data-cache tag through M's hit check and "M needs the bus" into bus arbitration (a fetch waits for a data access), fetch completion, F's advance and the return-stack enables. Steps 2 and 3 keep that dependency | output |
| 01:00 to 01:02 | Step 4: a new fetch no longer waits on whether M needs the bus this clock; it waits whenever M holds a load or store (a registered condition). Regression 165/165 (default and 2-line caches), B cross-check passes, Dhrystone 0.9669 (from 0.9670). ECP5 run `p081d` started | output |
| 01:02 to 01:04 | Tried to add a `--noabc9` option to `synth_fmax.py` so the 0.7.x syntheses (in Yosys for 85 minutes) could finish faster: Yosys 0.33 rejected it, because in 0.33 `synth_ecp5` already maps with ABC by default and ABC9 is the opt-in. Option removed; reports now name the mapper | output |

---

## 2026-11-20: setup, review rubric, roadmap and first benchmark

### Findings

1. **The local toolchain did not match the docs.** The README and quick start say Ubuntu 24.04 under WSL with Icarus is already installed. On this ARM64 Windows workstation WSL 2.7.10 was present but had no distribution. Installed Ubuntu 24.04, Icarus Verilog 12.0 and Python 3.12.3. Windows has Python 3.12.10 (ARM64) and LLVM 23.1.5.
2. **The core passes its own tests.** The main regression passed 96 of 96 differential runs plus the reset and RAM-wrapper checks, in about 12 seconds. The historical PicoRV32 smoke test passed in 26 cycles.
3. **GitHub Pages is not enabled for the repository.** The Pages API returns 404 and there is no Pages branch or workflow. The project's pages (CPU visualizer and core explainer) are served locally by `sim/cpu/serve_visualizer.py`.
4. **Building the visualizer lessons rewrites two tracked files.** `cpu/programs-verification.json` and `cpu/visualizer-verification.json` change on every lesson build, and again when **Run simulation** is clicked in the viewer. Both are modified and uncommitted; the decision is tracked in [TODO.md](TODO.md).
5. **The core cannot yet be called "good" or "performant".** A review rubric was written ([cpu/review-rubric.md](cpu/review-rubric.md)). The author's gate reading at commit `0483d99`: external-model check, lint and synthesis, known-issue list and independent review are not met, and no performance gate can be met without synthesis or a board.
6. **V8 is not a usable benchmark.** It needs an operating system, an MMU, RV64GC-class hardware and hundreds of megabytes of memory, and would take many hours per billion instructions in RTL simulation. Chosen instead: CoreMark (primary) and Dhrystone (secondary), with the riscv-tests benchmark programs as the next small set.
7. **RISC-V has a ratified vector extension but no ratified matrix extension** (as of mid-2026). Integrated (IME) and attached (AME) matrix approaches are recorded as research in the to-do list.
8. **The core has no caches.** Main memory is a 16 KiB RAM that answers in one clock, so caches cannot speed up today's simulation. A staged plan (slow memory model, then L1, then L2, measured at each step) is in the to-do list.
9. **Dhrystone runs on the unchanged core: 0.260 DMIPS/MHz** in simulation (non-compliant run, rubric evidence class E1). Details below.
10. **Benchmark scores depend heavily on the compiler.** The same Dhrystone source scores 0.260 DMIPS/MHz with clang 23.1.5, 0.249 with clang 21.1.6 (the CI runner) and 0.217 with Ubuntu's clang 18.1.3. All three pass every check.
11. **Clocks per instruction follow from the memory timing.** The RAM acknowledges one clock after each request, so a fetch takes 2 clocks and execution 1. Most instructions take 3 clocks; loads and stores take 5. Dhrystone averages 3.65; the earlier C demo, with fewer memory operations, averages about 3.05.
12. **The simulator is faster than first estimated.** The C demo record implies about 17,000 instructions per second. The Dhrystone timing run retired 307,336 instructions over 1,120,105 clocks in 9.0 seconds: about 34,000 instructions or 124,000 clocks per second, including process start-up.
13. **This LLVM installation has no RISC-V runtime library.** Bare-metal programs that multiply or divide need their own helper routines; the benchmark runtime now provides them.
14. **Existing verification records contain local user paths.** `cpu/verification.json` and `cpu/c-demo-results.json` include absolute paths from the machine that produced them. The new Dhrystone record stores repository-relative paths instead. The older records are unchanged.
15. **The repository check script could not be run locally** in this session because the assistant's permission settings blocked it. CI runs it on every push, and it passed for each commit below.
16. **First rubric scorecard: 37.1 of 100, the lowest ("foundation") band, no claims granted.** Strongest: traps and reset (R2) and reproducibility (R9), both 62%. Weakest: FPGA implementation (R5) at 0%, performance (R4) at 22% and verification depth (R3) at 25%. It is an automated self-assessment, recomputed on every Dhrystone run from `cpu/rubric-evidence.json`.
17. **Correction to the rubric's section 11 reading.** That reading listed HG1 (scope label) as met, but the scope label has no performance target, which rubric section 2 requires. The evidence file records HG1 as not met until a target is declared. Section 11 is left as written, since it is a dated reading.

18. **The CPU architecture is now versioned: 0.1.0.** The unchanged C0 core, called "revision 0" until now, becomes 0.1.0. Before 1.0.0, MINOR changes for any change to the architectural contract and PATCH for any other RTL change. Proposed criteria for 1.0.0: C1 complete, an external-model check (rubric HG3) and a first exact-part synthesis. Rules and history: [cpu/architecture.md](cpu/architecture.md) section 9.

19. **Profile of Dhrystone: fetching is 54.8% of all clocks.** Each instruction spends 2 clocks being fetched and 1 executing; loads and stores add 2. The per-instruction clock model reproduces the measured timed region exactly (1,094,103 clocks); the whole-program counts differ by 3 clocks, the final `ebreak`.
20. **The byte-at-a-time string routines dominate.** `strcpy` and `strcmp` from `sim/cpu/bench/runtime.c` execute 47% of all instructions (281 of 600 per run). Software divide is only 5% of clocks (one `__divdi3` call per run); multiplication never reaches `__muldi3` because the compiler uses shifts. This corrects advice given earlier in the session that hardware multiply and divide would be the biggest gain for Dhrystone: the profile estimates only 1.05x.
21. **40% of instructions could reuse the previous fetch.** 241 of 600 instructions per run are the second half of an 8-byte fetch beat that was just read. Model estimates: a one-entry fetch buffer gives 1.12x to 1.28x (2,188 down to 1,947 or 1,706 clocks per run); an ideal pipeline gives at most 3.65x. These are estimates from the trace, not measured RTL.
22. **Run logs are now split by commit.** The two runs previously logged at the end of this file were moved unchanged to [devlog/devlog-3110337.md](devlog/devlog-3110337.md).
23. **The optimization loop took Dhrystone from 2,188.2 to 555.7 clocks per run, 3.94x** (0.260 to 1.024 DMIPS/MHz, simulation). Order of gains: instruction fetch first (fetch buffer 1.28x, then a 4 KiB instruction cache 1.73x), then memory waits (early issue 1.24x, same-clock writes 1.11x, a data cache 1.20x), then instruction count (M, 1.08x on the `rv64im` build).
24. **The loop stopped at about one instruction per clock.** On 0.4.0 only 2.6 of 555.7 clocks per run are not instruction execution: two divide steps, 0.6 fetch and 0.1 memory. Lower needs fewer instructions (compiler or runtime, not the core) or more than one instruction per clock (a superscalar redesign, not a refinement).
25. **The gains depend on assumptions not yet tested.** Both 4 KiB caches hold all of Dhrystone, and the RAM answers in one clock. The cache lookups use the just-computed next PC and data address in the same clock, which may lower the clock frequency; nothing has been synthesized. A slow-memory model and a first synthesis are the checks that matter next.
26. **Two tooling problems found and fixed during the loop.** The visualizer testbench detected writes in a way that stopped working at 0.2.2. The profiler's "issue loads and stores in EXECUTE" estimate overstated the gain for 0.3.0 and 0.4.0; the run logs [devlog-90ee1ea.md](devlog/devlog-90ee1ea.md) and [devlog-88db627.md](devlog/devlog-88db627.md) still show the old figure and are left as written.
27. **The core contract changed in three MINOR steps.** `ICACHE_BEATS` (0.2.0) and `DCACHE_BEATS` (0.3.0) are new parameters, every address is now treated as cacheable, and 0.4.0 adds M. Each version has a history row in [cpu/architecture.md](cpu/architecture.md) and a local `cpu-vX.Y.Z` tag.

### Timeline

| Time | Event | Source |
|---|---|---|
| 19:58:44 | Initial commit `0483d99` (from an earlier session) | git |
| 19:59:44 to 20:00:07 | CI for `0483d99`: passed | CI |
| 20:00:41, 20:00:46 | Dependabot opens [PR 1](https://github.com/monstercameron/RISC-V-FPGA-CPU-Research/pull/1) (`actions/checkout` 7.0.1) and [PR 2](https://github.com/monstercameron/RISC-V-FPGA-CPU-Research/pull/2) (`actions/setup-python` 7.1.0); both pass CI and remain open | CI |
| before 20:04 | Repository cloned to the Desktop; docs, RTL, tests and CI reviewed | approx. |
| 20:04:55 | Ubuntu 24.04 installed in WSL; Icarus Verilog 12.0 and Python 3 installed | apt |
| about 20:05 | Main regression: 96/96 pass; PicoRV32 smoke test passes | approx. |
| 20:06:49 to 20:07:07 | Seven visualizer lessons rebuilt and verified; local page server started | record |
| 20:08:03 | "Decisions" lesson re-run from the viewer's **Run simulation** button | record |
| about 20:10 | Main regression re-run on request: 96/96 pass in 11.8 s | approx. |
| 20:24:24 | Review rubric written | file |
| 20:29:09 | Commit `55727ca`, review rubric; pushed | git |
| 20:29:25 to 20:29:44 | CI for `55727ca`: all six jobs pass | CI |
| 20:33:04 | Commit `aaa3693`, to-do list with RV64GC milestone; pushed | git |
| 20:33:08 to 20:33:34 | CI for `aaa3693`: all six jobs pass | CI |
| 20:40:02 | Commit `2b29966`, benchmark, memory-hierarchy and matrix to-dos; pushed | git |
| 20:40:06 to 20:40:29 | CI for `2b29966`: all six jobs pass | CI |
| 20:41 | Dhrystone sources and license downloaded from riscv-tests commit `3df703c` | file |
| 20:43:19 | Sources and license copied into the repository | file |
| 20:45:30 | Benchmark runtime written | file |
| about 20:47 | First Dhrystone run on the RTL: all checks pass, 0.260 DMIPS/MHz | approx. |
| 20:48:58 | Main regression after the trace-testbench change: 96/96 pass | file |
| 20:49:05 to 20:49:18 | clang 18.1.3, lld and LLVM tools installed in Ubuntu | apt |
| 20:50:03 | Dhrystone built and run entirely in Ubuntu: all checks pass, 0.217 DMIPS/MHz | record |
| 20:52:51 | Dhrystone result recorded in `cpu/dhrystone-results.json` | record |
| 20:54:20 | To-do list updated with the Dhrystone results | file |
| 20:55 | Development log written | approx. |
| 20:57:06 | Commit `3110337`, Dhrystone benchmark and development log; pushed | git |
| 20:57:13 to 20:58:25 | CI for `3110337`: all seven jobs pass, including the new Dhrystone job. Built with clang 21.1.6: 2,281.2 clocks per run, CPI 3.615, 0.2495 DMIPS/MHz | CI |
| about 21:00 | AGENTS.md now requires every experiment to be recorded in this log | approx. |
| 21:02:41 | Scorer dry run on the recorded Dhrystone result, nothing written: 37.1/100 | output |
| 21:04:14 | Dhrystone rerun through the launcher, scorecard appended to the run log below: unchanged 2,188.2 clocks per run; 37.1/100, foundation band, no claims granted | record |
| about 21:06 | Semantic versioning adopted for the CPU architecture; existing C0 core declared version 0.1.0 | approx. |
| 21:08:12 | Dhrystone rerun to check the version reaches results and scorecards: version 0.1.0 recorded; +0.00% clocks per run against the 21:04 run; 37.1/100 | record |
| 21:09:20 | Commit `699ad6c`, rubric scorecards, devlog rule and architecture versioning; pushed | git |
| about 21:09 | Annotated tag `cpu-v0.1.0` created on `0483d99`, where the 0.1.0 RTL first landed, and pushed | approx. |
| 21:09:28 to 21:10:39 | CI for `699ad6c`: all seven jobs pass. Repository check passes with the new version check; Dhrystone in CI (clang 21.1.6) scores 0.2495 DMIPS/MHz and 37.1/100 | CI |
| 21:11:34 | Commit `35565c0`, records the 0.1.0 release in this log; pushed | git |
| 21:11:38 to 21:13:05 | CI for `35565c0`: all seven jobs pass | CI |
| about 21:18 | Trace profiler written; dry run on the 21:08 trace: model matches the measured timed region exactly | approx. |
| 21:21:17 | First profiled Dhrystone run, logged to [devlog/devlog-35565c0.md](devlog/devlog-35565c0.md): unchanged 2,188.2 clocks per run, 37.1/100 | record |
| about 21:25 | Optimization loop started (user goal: optimize from the profile, re-benchmark, repeat until clocks stop dropping, record every change and run). Commit `04b19db` (profiler and per-commit logs), local only | approx. |
| 21:27:12 | Baseline run on `04b19db`, 0.1.0 core: 2,188.2 clocks per run; [devlog-04b19db.md](devlog/devlog-04b19db.md) | record |
| before 21:31 | 0.1.1 fetch buffer written; main regression 96/96 pass plus reset and RAM-wrapper checks | approx. |
| before 21:31 | Profiler switched from a fixed clock model to measured per-state clocks from the benchmark testbench. Unlogged tooling check on the uncommitted 0.1.1 tree: 1,706.2 clocks per run, per-instruction clocks equal the timed region exactly | output |
| 21:31:14 | Commit `df7f489`, fetch buffer (0.1.1); tagged `cpu-v0.1.1`, local only | git |
| 21:32:24 | 0.1.1 run: 1,706.2 clocks per run, 0.3336 DMIPS/MHz, 1.28x over 0.1.0; [devlog-df7f489.md](devlog/devlog-df7f489.md). Profile: instruction-cache replay predicts 988.8 clocks per run with 512 beats (4 KiB), since Dhrystone's code is about 4 KB | record |
| after 21:32 | 0.2.0 instruction cache written. Main regression 96/96 pass with the default 512-beat cache and 96/96 with a 2-beat cache; a 3-beat cache is rejected at elaboration | output |
| 21:34:58 | Commit `7197bd1`, instruction cache (0.2.0); tagged `cpu-v0.2.0`, local only | git |
| 21:35:53 | 0.2.0 run: 988.7 clocks per run, 0.5756 DMIPS/MHz, 2.21x over 0.1.0, matching the 988.8 estimate; [devlog-7197bd1.md](devlog/devlog-7197bd1.md). Fetch is now 0.1% of clocks; EXECUTE 61%, MEMORY 39% | record |
| after 21:36 | 0.2.1 early data-request issue written. Main regression 96/96 pass with 512-beat and 2-beat caches | output |
| 21:37:44 | Commit `f18223e`, loads and stores issue from EXECUTE (0.2.1); tagged `cpu-v0.2.1`, local only | git |
| 21:38:42 | 0.2.1 run: 794.7 clocks per run, 0.7162 DMIPS/MHz, 2.75x over 0.1.0, as estimated; [devlog-f18223e.md](devlog/devlog-f18223e.md). Every load and store still spends 1 clock in MEMORY because the RAM wrapper acknowledges a clock late | record |
| after 21:39 | 0.2.2 same-clock write acknowledge in the RAM wrapper written. Main regression 96/96 pass with 512-beat and 2-beat caches | output |
| 21:39:58 | Commit `0573f1a`, same-clock write acknowledge (0.2.2); tagged `cpu-v0.2.2`, local only | git |
| 21:40:59 | 0.2.2 run: 718.7 clocks per run, CPI 1.198, 0.7919 DMIPS/MHz, 3.04x over 0.1.0, as estimated; [devlog-0573f1a.md](devlog/devlog-0573f1a.md). Remaining waits: 118 loads per run, 1 MEMORY clock each | record |
| after 21:41 | 0.3.0 data cache written. Main regression 96/96 pass with default 512-beat caches and with 2-beat instruction and data caches | output |
| 21:42:29 | Commit `90ee1ea`, data cache (0.3.0); tagged `cpu-v0.3.0`, local only | git |
| 21:43:28 | 0.3.0 run: 600.8 clocks per run, CPI 1.001, 0.9473 DMIPS/MHz, 3.64x over 0.1.0; [devlog-90ee1ea.md](devlog/devlog-90ee1ea.md). The core now completes about one instruction per clock, the floor for a design that executes one instruction at a time; only fewer instructions can lower clocks further without executing several instructions per clock | record |
| after 21:44 | 0.4.0 M extension written: core, reference model and regression (directed M tests over zero divisors, overflow, extremes; two random programs with M). Reference M results checked against hand-computed spec values. Main regression 108/108 pass, 66 instruction names, with default and 2-beat caches. Benchmark build gains `--isa rv64im_zifencei` | output |
| 21:47:46 | Commit `88db627`, M extension (0.4.0); tagged `cpu-v0.4.0`, local only | git |
| 21:48:47 | 0.4.0 run, Dhrystone built for `rv64im`: 555.7 clocks per run, 553.1 instructions, CPI 1.005, 1.0242 DMIPS/MHz, 3.94x over 0.1.0; [devlog-88db627.md](devlog/devlog-88db627.md) | record |
| 21:49:53 | 0.4.0 run, Dhrystone built for `rv64i`: unchanged 600.8 clocks per run, as expected since that build has no M instructions; same log | record |
| after 21:50 | Loop stopped: only 2.6 of 555.7 clocks per run are not instruction execution. Profiler fix: the "issue loads and stores in EXECUTE" estimate counted every load and store, even those that no longer wait; it now counts only loads and stores that waited, and gives 555.6 instead of 361.7 for 0.4.0 | output |
| after 21:50 | Visualizer testbench fixed: it recognized RAM writes as "accepted but not yet acknowledged", which no longer happens since 0.2.2. All seven lessons rebuilt and verified on 0.4.0 at 21:51:24; the C demo takes 22,859 clocks instead of 69,157 | record |
| 21:51:40 | Expanded regression with compiled C firmware on 0.4.0: 111/111 runs, 37 programs, 66 instruction names, reset and both RAM-wrapper checks pass; saved as `cpu/verification.json` with local paths removed | file |
| 21:42:14 | Found afterwards: `main` on GitHub had been pushed to `0573f1a` by a push outside the assistant's commands; CI for it passed | CI |
| 21:48:08 | Found afterwards: a second outside push moved `main` on GitHub to `88db627`; CI passed all jobs, including Dhrystone | CI |
| 21:54 | Commit `186e8ca`, loop results and records, local only. The commit rows above that say "local only" were true when written; the two outside pushes later published every loop commit up to `88db627`. Tags after `cpu-v0.1.0` are still local | git |
| before 21:57 | Dual-issue estimate from the 0.4.0 `rv64im` profile trace, pairing an instruction with the next one in the same 8-byte beat when they are independent: ALU after ALU or load saves 82.9 clocks per run (472.8, 1.175x); also allowing a branch second and a store first saves 120.9 (434.8, 1.278x, about 1.31 DMIPS/MHz). Estimate only; not built | output |
| before 21:57 | New user goal: 20 DMIPS/MHz. Needs 28.5 clocks per Dhrystone run, about 19.4 instructions per clock on this 553-instruction build; an ideal 2-wide core reaches 2.06 and an ideal 4-wide core 4.12. Not reachable by core changes without breaking Dhrystone's rules; reported to the user instead of attempted | output |
| after 21:57 | Pushed `ec2ff65` and tags `cpu-v0.1.1` to `cpu-v0.4.0` on request; CI passed all seven jobs | CI |
| after 21:57 | New user goal: aim for 20 DMIPS/MHz and keep optimizing and documenting. Plan: dual issue (0.5.0), a labelled word-at-a-time runtime, the B extension, then whatever the profile shows | approx. |
| before 22:18 | 0.5.0 dual issue written. First regression failed on `random_m_404`: `sraw` on the second slot gave 1 instead of -1, because a Verilog `?:` mixing a signed and an unsigned arm is evaluated unsigned. Fixed by using `if`/`else` as the first slot does; the differential check caught it | output |
| before 22:18 | Added `dual_issue_store_pairs`: a store rewriting the next instruction in its own beat must not pair and the new instruction must run (it did: x20 = 42), and a store followed by an ALU instruction pairs. Regression 111/111 with default and 2-line caches. Visualizer carries the second retirement slot; all seven lessons verify; C demo 22,859 to 16,755 clocks | output |
| 22:18:19 | Commit `ba03c09`, limited dual issue (0.5.0); tagged `cpu-v0.5.0`, local only | git |
| 22:19:24, 22:20:37 | 0.5.0 runs: `rv64im` 435.7 clocks per run, CPI 0.788, 1.3062 DMIPS/MHz (estimate 434.8); `rv64i` 471.8 clocks, 1.2063 DMIPS/MHz; [devlog-ba03c09.md](devlog/devlog-ba03c09.md) | record |
| after 22:20 | Issue-width model on the 0.5.0 stream (matches 0.5.0 within 0.4%): pairing across beats 417.1; plus branch second 395.1; plus load or store second 391.1; two memory ports 367.1; 3-wide 317.0; 4-wide 293.0; even 8-wide in-order 283.0 clocks per run, about 2.0 DMIPS/MHz. In-order issue saturates near 2.0 on Dhrystone because dependencies and branches end issue groups | output |
| before 22:23 | 0.5.1 written: second slot from the next beat, and conditional branches in it. Regression 117/117 with default and 2-line caches, with new tests `misaligned_branch_after_alu` and `branch_depends_on_alu` | output |
| 22:23:14 | Commit `4ca8908`, pair across beats and pair branches (0.5.1); tagged `cpu-v0.5.1`, local only | git |
| 22:24:21, 22:25:39 | 0.5.1 runs: `rv64im` 397.8 clocks per run, CPI 0.719, 1.4309 DMIPS/MHz (estimate 395.1); `rv64i` 424.9 clocks, 1.3396 DMIPS/MHz; [devlog-4ca8908.md](devlog/devlog-4ca8908.md) | record |
| after 22:25 | Fast-runtime option added (`--runtime fast`, a separate labelled configuration). First version handled only strings with equal alignment: unlogged run 413.8 clocks per run, slower than the reference 397.8. A trace replay showed why: every call is misaligned against the other string (`strcpy` from `0x11f5` to `0xfe4e`, `strcmp` of `0xfe6d` with `0xfe4e`), so the word path never ran | output |
| after 22:25 | Second version reads aligned words and shifts neighbours together, as C libraries do: unlogged run 360.8 clocks per run, 470.1 instructions, 1.5773 DMIPS/MHz with `rv64im` on 0.5.1 | output |
| 22:30:06 | Commit `5db3914`, fast runtime option; logged fast-runtime run on 0.5.1: 360.8 clocks per run, 1.5773 DMIPS/MHz; [devlog-5db3914.md](devlog/devlog-5db3914.md) | record |
| after 22:31 | Zba/Zbb check: compiling Dhrystone and the fast runtime for `rv64im_zba_zbb` changes only a few instructions (`sh2add`, `add.uw`, `max`); the compiler never emits `orc.b` from portable C. Estimated 5 to 7% on the fast runtime, about 1% on the reference. Deferred | output |
| after 22:31 | Issue-width model on the fast-runtime stream: a second memory port for loads in the second slot gives 318.1 clocks per run (about 1.79 DMIPS/MHz); 3-wide 275.0; 8-wide in-order 241.0 (2.36) | output |
| before 22:33 | 0.5.2 written: data-cache-hit loads in the second slot. New test `dual_issue_loads` (two hits pair, dependent address waits, store then load sees the store). Regression 120/120 with default and 2-line caches | output |
| 22:33:28 | Commit `c05a1ce`, second-slot loads (0.5.2); tagged `cpu-v0.5.2`. Runs: `rv64im` reference 388.8 clocks per run, 1.4640 DMIPS/MHz; `rv64im` fast runtime 348.9, 1.6315; `rv64i` reference 416.9, 1.3653; [devlog-c05a1ce.md](devlog/devlog-c05a1ce.md). Less than the model predicted (318.1 fast), because the model also let a load pair after any store | record |
| after 22:37 | Pairing-blocker analysis on the 0.5.2 fast-runtime stream (clocks per run issued alone, by reason): branch first 40.0, store second 37.1, ALU-to-ALU dependency 32.0, JALR first 32.0, JALR second 22.1, load after store 14.0, ALU-to-branch dependency 14.0 | output |
| before 22:39 | 0.5.3 written: not-taken branch first, JAL/JALR second, load after a store to another beat. New tests `dual_issue_jumps` and `misaligned_jalr_after_alu`. Regression 126/126 with default and 2-line caches | output |
| 22:39:39 | Commit `73c1fbc`, branches first and jumps second (0.5.3); tagged `cpu-v0.5.3`. Runs: `rv64im` reference 366.8 clocks per run, 1.5518 DMIPS/MHz; fast runtime 310.9, 1.8309; `rv64i` reference 391.9, 1.4524; [devlog-73c1fbc.md](devlog/devlog-73c1fbc.md) | record |
| after 22:43 | Blockers on the 0.5.3 fast-runtime stream: store second 31.1 clocks per run, ALU-to-ALU dependency 24.1, JALR first 22.0, branch first (taken) 17.0, ALU-to-branch dependency 14.0 | output |
| before 22:47 | 0.5.4 written: second-slot stores (held in MEMORY under stalls, precise bus-error trap) and ALU forwarding into the second slot. Trace testbench and visualizer now log a second-slot store's write after the first slot's retirement, matching program order. New tests `dual_issue_store_second` and `store2_bus_fault`. Regression 132/132 with default and 2-line caches; all seven visualizer lessons verify | output |
| before 22:47 | Visualizer lesson build failed (`decisionNotTaken` missing): since 0.5.1 a branch can retire on the second slot, and the lesson checkpoints only looked at the first slot. Not caught at 0.5.1 to 0.5.3 because the lessons were not rebuilt then. Checkpoints now come from both slots' retirement records; all seven lessons verify; C demo 12,990 clocks | output |
| 22:47:19 | Commit `241a9af`, second-slot stores and forwarding (0.5.4); tagged `cpu-v0.5.4`. Runs: `rv64im` reference 335.8 clocks per run, 1.6951 DMIPS/MHz; fast runtime 269.9, 2.1091 (first build past 2 DMIPS/MHz); `rv64i` reference 358.8, 1.5861; [devlog-241a9af.md](devlog/devlog-241a9af.md) | record |
| after 22:51 | Blockers on 0.5.4: fast runtime issues 413.8 of 470.1 instructions per run in pairs (2-wide floor about 235 clocks); remaining: JALR first 18.0, taken branch first 15.0, store second 10.1 clocks per run. Reference runtime: taken branch first 55.0, load-to-branch dependency 23.0, JALR first 20.0 | output |
| before 22:57 | 0.5.5 branch folding written. Regression 135/135 passed, but the visualizer lesson build failed: when a fetch completed, the next instruction was captured from `pc2`, which since 0.5.5 is the folding target computed from the stale previous instruction. In the lesson it captured `j .` from 0x10 instead of the instruction at 0x30. Fixed (use pc+4 in FETCH). New test `fetch_after_stale_jump` reproduces it: with the bug put back it fails (x5 = 7 at 0x30 instead of x7 = 2); with the fix it passes. Regression 138/138 with default and 2-line caches; all lessons verify; C demo 11,568 clocks. Lesson rebuilds are now part of every step | output |
| about 22:57 | Commit `5f1f6b1`, branch folding (0.5.5); tagged `cpu-v0.5.5`. Runs: `rv64im` reference 287.8 clocks per run, 1.9777 DMIPS/MHz (7.60x over 0.1.0); fast runtime 251.9, 2.2598; `rv64i` reference 308.9, 1.8428; [devlog-5f1f6b1.md](devlog/devlog-5f1f6b1.md) | record |
| about 22:59 | Second issue model, with folding, forwarding depth and port limits, calibrated against 0.5.5 (287.0 modelled against 287.8 measured, reference runtime). 3-wide with one level of forwarding: 213 clocks per run reference (2.67 DMIPS/MHz), 182 fast (3.13). 4-wide with two taken branches and three levels of forwarding: 144 reference (3.95), 123 fast (4.63). 8-wide with forwarding chains of seven: 73 and 63 (7.8 and 9.0) | output |
| about 22:59 | Caution recorded: forwarding chains raise DMIPS/MHz by doing more work per clock, which lengthens the clock; at the extreme a whole program fits in one very long clock. DMIPS/MHz gains from deeper logic are not real performance unless synthesis shows the clock survives. Decided to measure logic depth before going wider | output |
| 23:02:08 | Yosys 0.33 installed in Ubuntu; `sim/cpu/synth_depth.py` written to map the core to 6-input LUTs and report the longest path in LUT levels | apt |
| after 23:02 | First depth synthesis of 0.5.5 stopped after a long run without finishing: the 0.4.0 multiply logic built three 128x128-bit products. Replaced by one signed 65x65 product with a sign or zero bit per operand (same results; M tests pass). Depth synthesis restarted in the background | output |
| after 23:02 | 0.6.0 B extension written: one `bitmanip` function used by both slots; encodings taken from LLVM's assembler; reference model extended. New tests: `b_extension` (all 40 instructions over extreme operands) and `random_b_606`/`random_b_707`. Regression 147/147, 106 instruction names, with default and 2-line caches; all seven lessons verify | output |
| after 23:02 | Independent B check (`sim/cpu/check_bitmanip.py`): the same C built without B and with Zba/Zbb/Zbs gives identical results on the RTL in all 12 groups; the B build uses 28 distinct B instructions; both traces match the reference. Benchmark builds gain `rv64imb` (`rv64im_zba_zbb_zbs_zifencei`), and the fast runtime uses `orc.b` when Zbb is available | output |
| 23:08:47 | Commit `f78d62a`, B extension and single multiplier (0.6.0); tagged `cpu-v0.6.0`, local only | git |
| after 23:08 | First `rv64imb` run failed a consistency check: timing run and trace disagreed by one instruction on the timed region. Both retire the same instructions in the same order; the difference is at the region's edges, where a marker store can retire in the same clock as the next instruction. The runner now requires exact totals, allows the region edges to differ by up to two, and takes the region's instruction count from the trace in program order. Earlier results are unaffected (their counts matched exactly) | output |
| 23:12:36 to 23:16:18 | 0.6.0 runs: `rv64imb` reference 285.8 clocks per run, 1.9916 DMIPS/MHz; `rv64imb` fast 247.8, 2.2964; `rv64im` reference unchanged 287.8; `rv64im` fast unchanged 251.9; [devlog-f78d62a.md](devlog/devlog-f78d62a.md). B gains 0.7% (reference) and 1.6% (fast), as the static check predicted | record |
| before 23:15 | Depth synthesis of 0.6.0 completed but recorded nothing: Yosys quiet mode hid the reports. The script now saves them to files; 0.3.0 and 0.6.0 are being measured | output |
| 23:17:11 | Commit `c281389`: 0.6.0 benchmark records and runner fix | git |
| after 23:17 | Third-slot sizing on the 0.6.0 streams (issue model, calibrated on the measured 2-wide results): an ALU-only third slot that never uses the second slot's result saves about 12% (reference) to 16% (fast); a direct count of ALU instructions issued alone suggested zero, because the gain comes from regrouping, not from single issues | output |
| before 23:21 | 0.7.0 third slot written, with a third retirement port carried through the RAM wrapper, testbenches and visualizer. New test `triple_issue` (forwarding from slot one, a third that depends on the second, three writes to one register). Regression 150/150 with default and 2-line caches; B cross-check passes; all lessons verify; C demo 8,756 clocks | output |
| 23:21:28 | Commit `a6e3f87`, third issue slot (0.7.0); tagged `cpu-v0.7.0`. Runs: `rv64imb` reference 256.8 clocks per run, CPI 0.467, 2.2163 DMIPS/MHz (8.52x over 0.1.0); `rv64imb` fast 216.9, 2.6243; `rv64im` reference 258.8, 2.1991; [devlog-a6e3f87.md](devlog/devlog-a6e3f87.md) | record |
| 23:17 to 23:24 | First logic-depth results (generic Yosys + ABC, 6-input LUTs, 4-line caches): 0.3.0 has a longest path of 30 LUT levels, 6,309 LUTs, 3,662 flip-flops; the run started on 0.6.0 reports 78 levels, 33,046 LUTs, 4,250 flip-flops. That report was stamped "0.7.0" because the script read the version and hash at the end, after the working copy had moved on; the RTL it synthesized was read at the start (0.6.0). The script now snapshots and hashes its source first | output |
| about 23:25 | Finding: depth grew 2.6x from 0.3.0 while DMIPS/MHz grew about 2.1x. If clock frequency fell in proportion to depth, absolute performance would not have improved. Three variants of 0.7.0 are being synthesized (as built, multiplier removed, multiplier removed with forwarding and folding off) to find what the deep path is | output |
| about 23:25 | Both syntheses contain only flip-flops and LUTs: no latches (part of rubric gate HG7; a dedicated lint run is still missing). Size note: up to three instructions per clock needs six register-file read ports and three write ports, which an FPGA builds from flip-flops and wide multiplexers rather than LUT RAM; LUTs grew from 6,309 to 33,046 | output |
| 23:26 | First variant-synthesis attempt did nothing: PowerShell passed an escaped shell variable through literally. Rerun from a script file | output |
| 23:28 to 23:32 | Candidate 0.7.1, registered multiplier: operands registered in EXECUTE, product taken in a new MULTIPLY state one clock later. Regression 150/150 with default and 2-line caches; B cross-check passes. Unlogged Dhrystone run (`rv64imb`, reference runtime): unchanged 256.8 clocks per run, because this build never multiplies at run time | output |
| 23:34 | Correction to earlier rows: from "before 21:57" to "23:28 to 23:32", 41 rows had estimated times 20 to 60 minutes later than the events (some later than the time of writing). They now use the commit author times and the run-table times, or a bound from them | git |
| about 23:35 | Variant `v070-nomul-nofwd` (0.7.0 with the multiplier removed, and with folding (`control0`) and slot-1-to-slot-2 forwarding (`slot0_forward`) forced off): 40 LUT levels, 28,149 LUTs, 4,483 flip-flops, 442.4 s. Its longest path runs from the register file through about 20 single-LUT steps in a row, the pattern of a 64-bit adder carry built from generic LUTs. A generic LUT mapping has no carry chain, so LUT levels overstate adder delay compared with an FPGA, which has dedicated carry logic | output |
| 23:35:50 | `nextpnr-ecp5` 0.6-3build5 (arm64) installed in Ubuntu with `apt-get install nextpnr-ecp5`, to get post-route clock estimates on a real FPGA family (Lattice ECP5) instead of LUT levels. New script `sim/cpu/synth_fmax.py` (Yosys `synth_ecp5`, then nextpnr out of context, 4-line caches); first runs on 0.3.0, 0.7.0 and the 0.7.1 candidate started | apt |
| 23:49 | Variant results (same flow, 4-line caches, run three at a time): 0.7.0 as built 80 LUT levels, 37,991 LUTs, 4,473 flip-flops, 1,266.6 s; multiplier removed 54 levels, 30,188 LUTs, 1,199.3 s; multiplier removed with folding and forwarding off 40 levels, 28,149 LUTs. The multiplier (a 65x65 product after register read and decode in the same clock) accounts for 26 levels and folding plus slot-1-to-slot-2 forwarding for 14 more. (The 0.7.0 RTL gives 80 levels against the 78 of the 0.6.0 run; ABC results vary a little with the design) | output |
| 23:50 | Candidate 0.7.1 (registered multiplier) depth: 52 LUT levels against 80 for 0.7.0, 40,187 LUTs (+2,196, from holding the 130-bit product's operands and selecting its result), 4,606 flip-flops (+133), 1,252.4 s. The deepest path no longer goes through the multiplier: it runs from the register file to a register-file write (the issue and forwarding logic). Adopted as 0.7.1 (PATCH: a multiply takes two clocks and no longer pairs; the ISA and ports do not change). Dhrystone does not multiply at run time, so its clocks do not change (256.8, unlogged run at 23:28 to 23:32) | output |
| 23:51:50 | Commit `129e37e`, registered multiplier (0.7.1); tagged `cpu-v0.7.1`, local only | git |
| 23:52:42 | First ECP5 place and route (0.3.0, LFE5U-85F, CABGA381, speed 6, seed 1, 4-line caches, target 50 MHz): routed, **22.49 MHz** achieved; 23,911 of 83,640 logic cells, 3,662 flip-flops; 945.2 s. Critical path 44.5 ns, of which 9.2 ns logic and 35.3 ns routing: instruction register, load address, data-cache hit, result select, register-file write. nextpnr exits 1 when the target is missed, so the script reported "nextpnr exit 1"; the report was corrected from the log and the script now passes `--timing-allow-fail` and records the critical path | output |
| 23:52 to 23:58 | 0.7.1 runs: `rv64imb` reference 256.8 clocks per run, 2.2163 DMIPS/MHz (unchanged); `rv64imb` fast 216.9, 2.6243 (unchanged); `rv64im` 261.8, 2.1739 (+3.0 clocks per run against 0.7.0: that build multiplies at run time, and each multiply now takes an extra clock and no longer pairs); `rv64i` 273.9, 2.0780 (first `rv64i` record since 0.5.5's 308.9); [devlog-129e37e.md](devlog/devlog-129e37e.md) | record |
| 23:58 | Absolute-performance estimate for 0.3.0: 0.9473 DMIPS/MHz x 22.49 MHz = 21.3 DMIPS on this part (one seed, open timing model, not hardware). The 0.7.0 and 0.7.1 routes are running; their DMIPS/MHz gain (2.34x) is real only if their clock stays above 22.49 / 2.34 = 9.6 MHz | output |

### Optimization loop

Each step changes the core, passes the main regression, is committed and tagged with its architecture version, and is then benchmarked with Dhrystone (clang 23.1.5 `-O2`, 64 KiB RAM). Run records are linked from the run index at the end of this file.

| Version | Change | Clocks per run | CPI | DMIPS/MHz | vs 0.1.0 | Gain over previous |
|---|---|---:|---:|---:|---:|---:|
| 0.1.0 | Baseline multicycle core | 2,188.2 | 3.647 | 0.2601 | 1.00x | |
| 0.1.1 | One-entry fetch buffer | 1,706.2 | 2.843 | 0.3336 | 1.28x | 1.28x |
| 0.2.0 | 4 KiB direct-mapped instruction cache | 988.7 | 1.648 | 0.5756 | 2.21x | 1.73x |
| 0.2.1 | Loads and stores issue from EXECUTE | 794.7 | 1.324 | 0.7162 | 2.75x | 1.24x |
| 0.2.2 | RAM wrapper acknowledges writes in the same clock | 718.7 | 1.198 | 0.7919 | 3.04x | 1.11x |
| 0.3.0 | 4 KiB write-through data cache for loads | 600.8 | 1.001 | 0.9473 | 3.64x | 1.20x |
| 0.4.0, `rv64i` build | M extension, not used by this build | 600.8 | 1.001 | 0.9473 | 3.64x | 1.00x |
| 0.4.0, `rv64im` build | M extension: hardware divide replaces the software routine | 555.7 | 1.005 | 1.0242 | 3.94x | 1.08x |
| 0.5.0, `rv64im` build | Limited dual issue within an 8-byte beat | 435.7 | 0.788 | 1.3062 | 5.02x | 1.28x |
| 0.5.0, `rv64i` build | Same core, `rv64i` build | 471.8 | 0.786 | 1.2063 | 4.64x | 1.27x |
| 0.5.1, `rv64im` build | Pair across beats; branches in the second slot | 397.8 | 0.719 | 1.4309 | 5.50x | 1.10x |
| 0.5.1, `rv64i` build | Same core, `rv64i` build | 424.9 | 0.708 | 1.3396 | 5.15x | 1.11x |
| 0.5.1, `rv64im`, fast runtime | Word-at-a-time `strcpy`/`strcmp` (labelled; not compared with the reference runtime) | 360.8 | 0.768 | 1.5773 | | |
| 0.5.2, `rv64im` build | Data-cache-hit loads in the second slot | 388.8 | 0.703 | 1.4640 | 5.63x | 1.02x |
| 0.5.2, `rv64im`, fast runtime | Same core, fast runtime | 348.9 | 0.742 | 1.6315 | | 1.03x |
| 0.5.3, `rv64im` build | Not-taken branch first; JAL/JALR second; load after store to another beat | 366.8 | 0.663 | 1.5518 | 5.97x | 1.06x |
| 0.5.3, `rv64im`, fast runtime | Same core, fast runtime | 310.9 | 0.661 | 1.8309 | | 1.12x |
| 0.5.4, `rv64im` build | Second-slot stores; ALU forwarding into the second slot | 335.8 | 0.607 | 1.6951 | 6.52x | 1.09x |
| 0.5.4, `rv64im`, fast runtime | Same core, fast runtime | 269.9 | 0.574 | 2.1091 | | 1.15x |
| 0.5.5, `rv64im` build | Branch folding: jump or taken branch plus its target instruction in one clock | 287.8 | 0.520 | 1.9777 | 7.60x | 1.17x |
| 0.5.5, `rv64im`, fast runtime | Same core, fast runtime | 251.9 | 0.536 | 2.2598 | | 1.07x |
| 0.5.5, `rv64i` build | Same core, `rv64i` build | 308.9 | 0.515 | 1.8428 | 7.08x | |
| 0.6.0, `rv64imb` build | B extension (Zba, Zbb, Zbs) | 285.8 | 0.520 | 1.9916 | 7.66x | 1.01x |
| 0.6.0, `rv64imb`, fast runtime | Same core, fast runtime using `orc.b` | 247.8 | 0.556 | 2.2964 | | 1.02x |
| 0.7.0, `rv64imb` build | ALU-only third issue slot | 256.8 | 0.467 | 2.2163 | 8.52x | 1.11x |
| 0.7.0, `rv64imb`, fast runtime | Same core, fast runtime | 216.9 | 0.486 | 2.6243 | | 1.14x |
| 0.7.1, `rv64imb` build | Registered multiplier (LUT depth 80 to 52); this build does not multiply at run time | 256.8 | 0.467 | 2.2163 | 8.52x | 1.00x |
| 0.7.1, `rv64im` build | Same core; this build multiplies, each multiply now one clock longer | 261.8 | | 2.1739 | | 0.99x |

Every step measured what the previous profile estimated. The loop stopped after 0.4.0 because the core completes about one instruction per clock; see findings 23 to 27.

### Commits

Messages are reproduced as committed.

#### `0483d99`, 2026-11-20 19:58:44, Claude

```text
Initial commit: RV64I multicycle core, simulation suite, and research

Original 64-bit RISC-V CPU for FPGA targeting RVA23U64 long term.
Includes the multicycle RV64I core RTL, differential simulation suite,
CPU visualizer and study programs, ISA/ABI/memory plans, FPGA resource
analysis, and preserved LLM-accelerator planning evidence.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `55727ca`, 2026-11-20 20:29:09, earl cameron

```text
Add CPU review rubric for good and performant claims

Defines the scope label, evidence classes E0-E4, hard gates, 0-4 scoring
across nine weighted dimensions, benchmark and measurement rules, and the
claims each result permits. Records the current core's gate status.
Links the rubric from the README, CPU quick start, contributing guide,
PR template and changelog, and adds it to the repository link checks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `aaa3693`, 2026-11-20 20:33:04, earl cameron

```text
Add CPU to-do list with an RV64GC milestone

Prioritized work list: external model and architectural tests, lint and
first synthesis, CoreMark and Embench porting, the C1 environment, and an
RV64GC milestone mapped onto the C1-C4 gates. Each item names the
evidence that marks it done. Linked from the README and changelog and
added to the repository link checks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `2b29966`, 2026-11-20 20:40:02, earl cameron

```text
Expand to-do list: benchmarks, memory hierarchy, matrix research

Targets CoreMark and Dhrystone with shared groundwork (markers, larger
memory, runtime, licensing) and per-benchmark porting, validation and
reporting steps. Adds a memory hierarchy plan (larger and slower main
memory model, L1 instruction and data caches, unified L2, measured at
each step) and a research section comparing integrated (IME) and
attached (AME) RISC-V matrix extensions.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `3110337`, 2026-11-20 20:57:06, earl cameron

```text
Add Dhrystone benchmark and development log

Runs the riscv-tests Dhrystone unmodified on the RV64I core in
simulation: 0.260 DMIPS/MHz with clang 23 at -O2, a non-compliant
simulation run. Adds a freestanding runtime with software multiply and
divide, marker-based timing, a 64 KiB build, result and differential
trace checks, a Windows launcher, a CI job, license and provenance
records, and a development log of the work and findings to date.
The trace testbench's memory size and cycle limit become parameters
with unchanged defaults.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

This section first listed the message as proposed, before the commit existed; it was updated with the hash once committed.

#### `699ad6c`, 2026-11-20 21:09:20, earl cameron

```text
Add rubric scorecards, devlog rule and architecture versioning

Every Dhrystone run now computes a review-rubric scorecard from
cpu/rubric-evidence.json plus the run's own measurements and appends it,
with the result and its trend, to the run log in DEVLOG.md. The first
self-assessment scores 37.1 of 100 with no claims granted.

AGENTS.md now requires every experiment to be documented in DEVLOG.md.

The CPU architecture adopts semantic versioning: the existing C0 core is
version 0.1.0, with bump rules, a release process using cpu-vX.Y.Z tags,
a version history, a repository consistency check, and the version
recorded in benchmark results and scorecards.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `35565c0`, 2026-11-20 21:11:34, earl cameron

```text
Record the 0.1.0 release in the devlog

Logs commit 699ad6c, the cpu-v0.1.0 tag on 0483d99 and its CI result,
ticks the tagging to-do and names the tag in the version history.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `04b19db`, 2026-11-20 21:25:53, earl cameron

```text
Profile every Dhrystone run and split run logs by commit

Each run now profiles its instruction trace: clocks by instruction class
and function, hot instructions, fetch-reuse share and what-if estimates
from a per-instruction clock model that reproduces the measured clocks
exactly. Fetch is 54.8% of clocks and byte-at-a-time strcpy/strcmp are
47% of instructions; hardware multiply and divide would gain only 1.05x.

Detailed run records move to devlog/devlog-<commit>.md, one file per
commit, indexed from DEVLOG.md, which keeps daily summaries. The two
earlier run entries move unchanged to devlog/devlog-3110337.md. Run logs
list exactly which files were uncommitted.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `df7f489`, 2026-11-20 21:31:14, earl cameron

```text
Add a one-entry fetch buffer (architecture 0.1.1)

The core keeps the last fetched 8-byte beat. When the next instruction is
in the same beat it goes straight to EXECUTE with no bus request, saving
2 clocks. Reset, fence.i and any successful store to the buffered beat
clear the buffer, so fetched instructions still reflect every completed
store and architectural behaviour is unchanged (PATCH).

Main regression: 96/96 pass with reset and RAM-wrapper checks.
Unlogged Dhrystone check: 2,188.2 -> 1,706.2 clocks per run.

The benchmark testbench now records the clocks each retired instruction
spends in FETCH, EXECUTE and MEMORY, and the profiler uses these measured
clocks instead of a fixed model, with direct-mapped instruction-cache
estimates. Rubric evidence is reassessed for the new RTL hashes.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `7197bd1`, 2026-11-20 21:34:58, earl cameron

```text
Replace the fetch buffer with an instruction cache (architecture 0.2.0)

A direct-mapped instruction cache of ICACHE_BEATS 8-byte lines (default
512, 4 KiB) replaces the one-entry fetch buffer. Every bus fetch fills a
line; a next instruction that hits goes straight to EXECUTE. Reset and
fence.i clear the cache and a successful store clears the line holding
its beat, so behaviour is unchanged. ICACHE_BEATS is a new parameter on
rv64_core and rv64_bram_soc (MINOR); illegal sizes fail at elaboration.

Main regression: 96/96 pass with 512 lines and with 2 lines. The 0.1.1
profile predicted 988.8 clocks per run for Dhrystone with 512 lines.
test_cpu.py gains --icache-beats; tb_core passes the size through.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `f18223e`, 2026-11-20 21:37:44, earl cameron

```text
Issue loads and stores from EXECUTE (architecture 0.2.1)

A load or store now puts its bus request out during EXECUTE, as soon as
its address is known and no exception is pending. If the bus completes
in that clock the instruction retires from EXECUTE; otherwise MEMORY
holds the identical request from the pending registers, so requests stay
stable under backpressure and faults stay precise. With the synchronous
RAM each data access takes one clock less. Bus protocol and behaviour
are unchanged (PATCH).

Main regression: 96/96 pass with 512-line and 2-line instruction caches,
including the reset-during-store and RAM-wrapper checks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `0573f1a`, 2026-11-20 21:39:58, earl cameron

```text
Acknowledge RAM writes in the same clock (architecture 0.2.2)

The synchronous RAM wrapper now completes a write in the clock the
request is presented: block RAM writes on that clock edge anyway, and the
out-of-range error is decided combinationally from the address. Reads
still answer one clock later. Stores therefore retire from EXECUTE.
Core unchanged; bus protocol unchanged (PATCH).

Main regression: 96/96 pass with 512-line and 2-line instruction caches,
including the RAM-wrapper smoke test.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `90ee1ea`, 2026-11-20 21:42:29, earl cameron

```text
Add a write-through data cache for loads (architecture 0.3.0)

A direct-mapped data cache of DCACHE_BEATS 8-byte lines (default 512,
4 KiB) serves loads. A successful load fills its line; a successful store
updates a line already holding its beat (write-through, no allocation on
stores). A load that hits completes in EXECUTE without a bus request.
Behaviour is unchanged for this single-master system, but every address
is now treated as cacheable: a PMA must mark peripheral regions
uncacheable before any are added. DCACHE_BEATS is a new parameter on
rv64_core and rv64_bram_soc (MINOR); illegal sizes fail at elaboration.

Main regression: 96/96 pass with default caches and with 2-line
instruction and data caches. test_cpu.py gains --dcache-beats.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### `88db627`, 2026-11-20 21:47:46, earl cameron

```text
Add the M extension (architecture 0.4.0)

Implements mul, mulh, mulhsu, mulhu, div, divu, rem, remu and the word
forms. Multiplies complete in EXECUTE. Divides complete in EXECUTE for
divide-by-zero, signed overflow and dividends smaller than the divisor;
otherwise a DIVIDE state runs one shift-subtract step per clock from the
quotient's highest possible bit, so small quotients finish in a few
clocks. ISA string becomes rv64im_zifencei (MINOR).

The reference model implements M per the specification, checked against
hand-computed results. The regression adds directed M tests (zero
divisors, overflow, -1, extremes, long and short quotients) and two
random programs mixing M operations: 108/108 pass, 66 instruction names,
with default and 2-line caches. Dhrystone can now be built for
rv64im_zifencei.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

#### Tags

`cpu-v0.1.0` on `0483d99`, `cpu-v0.1.1` on `df7f489`, `cpu-v0.2.0` on `7197bd1`, `cpu-v0.2.1` on `f18223e`, `cpu-v0.2.2` on `0573f1a`, `cpu-v0.3.0` on `90ee1ea`, `cpu-v0.4.0` on `88db627`. Tags after `cpu-v0.1.0` are local until pushed. Commits up to `88db627` reached GitHub through two pushes outside the assistant's commands (21:42:14 and 21:48:08).

#### Tag `cpu-v0.1.0` on `0483d99`

```text
CPU architecture 0.1.0: C0 integer foundation (multicycle RV64I and FENCE.I core, terminal laboratory trap record, unified 64-bit memory bus, retirement trace, synchronous RAM wrapper). See cpu/architecture.md section 9.
```

### Details

#### Environment

| Item | Version or state |
|---|---|
| Workstation | Windows 11 on ARM64 |
| WSL | 2.7.10, distribution Ubuntu 24.04 installed this session |
| Simulator | Icarus Verilog 12.0 in Ubuntu |
| Python | 3.12.10 on Windows, 3.12.3 in Ubuntu |
| Compilers | LLVM/clang 23.1.5 on Windows; clang 18.1.3 with lld in Ubuntu |
| Not installed | Yosys, Verilator, Spike, Sail |

Git commits use the repository owner's GitHub noreply address, set for this repository only.

#### Review rubric (`55727ca`)

[cpu/review-rubric.md](cpu/review-rubric.md) defines what a review must show before the CPU may be called "good" or "performant": a scope label, evidence classes E0 to E4, eight hard gates for "good" and five more for "performant", 0-4 scoring across nine weighted dimensions totalling 100 points, benchmark rules and the wording each result permits.

Gate reading at `0483d99`, by the author and not an independent review:

| Gate | Status |
|---|---|
| HG1 scope label and RTL hashes | Met |
| HG2 regression passes | Met at class E1 |
| HG3 independent correctness check | Not met: project-written reference model only |
| HG4 precise traps | Met for the terminal trap record |
| HG5 nothing falsely advertised | Met |
| HG6 no open correctness defect | Open: no known-issue list exists |
| HG7 lint and synthesis | Not met |
| HG8 independent reproduction | Not met |
| PG1-PG5 performance gates | Not met: no synthesis, timing, benchmark or board result |

The clocks-per-instruction and CoreMark-per-MHz pass marks in the rubric are project-chosen starting points, to be recalibrated against a like-for-like comparator.

#### Roadmap (`aaa3693`, `2b29966`)

[TODO.md](TODO.md) now holds, in order:

- external-model comparison, architectural tests, wider random tests, lint, first synthesis and a known-issue list;
- CoreMark and Dhrystone, with shared groundwork;
- a memory hierarchy plan;
- the C1 execution environment;
- an RV64GC milestone (RV64IMAFDC plus Zicsr and Zifencei) mapped onto gates C1 to C4;
- research on matrix extensions;
- later work: board bring-up, the rest of RVA23, a Linux-capable platform, and large software such as V8.

#### Dhrystone (`3110337`)

Result with clang 23.1.5 at `-O2`, 64 KiB RAM, no added wait cycles:

| Measurement | Value |
|---|---:|
| Runs | 500 |
| Timed region | 1,094,103 clocks, 300,029 instructions |
| Clocks per run | 2,188.2 |
| Instructions per run | 600.1 |
| Clocks per instruction | 3.647 |
| DMIPS per MHz | 0.2601 |
| Whole program | 1,120,105 clocks, 307,336 instructions |

How it was checked:

- All 17 reachable final values match Dhrystone's expected values.
- All 347,135 trace events match the reference model, with 0 and up to 7 memory wait cycles.
- The timing and trace runs retire identical instruction counts.

What the result depends on and leaves out:

- **Software multiply and divide:** the core has no M extension, so these routines run inside the timed loop.
- **Timing method:** the core has no cycle counter, so the testbench counts clocks between start and stop marker writes.
- **Unchecked values:** Dhrystone's local variables are not reachable from the port layer and are not checked.

Design notes:

- **Memory size:** the program needs about 15.7 KB, so it runs with 64 KiB of RAM. The RTL is unchanged; the main regression stays at 16 KiB because its unmapped-address tests rely on that boundary.
- **Upstream sources:** copied byte-for-byte from riscv-tests `3df703c` under BSD-3-Clause, compiled as `gnu89` with `-fno-inline`, each file separately.
- **Port layer:** `setStats()` writes the markers and captures results; the program's own timer returns 1, 2, 3 so its loop runs once.
- **CI:** a new job builds with Ubuntu's clang and runs every check on each push.

Full write-up: [cpu/dhrystone.md](cpu/dhrystone.md). Record: [cpu/dhrystone-results.json](cpu/dhrystone-results.json).

#### Open at the end of the day

- Push the records commit `186e8ca` and its follow-up, and the tags `cpu-v0.1.1` to `cpu-v0.4.0`; commits up to `88db627` are already on GitHub.
- Declare a performance target for the scope label (HG1).
- Decide whether to commit or discard the two regenerated visualizer records, now rebuilt on 0.4.0.
- Synthesize the core with its caches on a candidate part, and add a slow-memory model, before trusting the clock counts on hardware.
- Merge or close Dependabot PRs 1 and 2.
- Next benchmark: CoreMark. Next correctness step: an external model (Spike or Sail) in the regression.

---

## Run logs

One row per benchmark run, oldest first. Each run's full record (result, rubric scorecard, profile, build commands and checks) is in its per-commit log under [devlog/](devlog/). Rows are added automatically by `sim/cpu/bench/run_bench.py --devlog`, which the Windows launcher passes on every run.

| Run time | Commit | Uncommitted changes | Architecture | Compiler | Clocks per run | DMIPS/MHz | Rubric | Log |
|---|---|---|---|---|---:|---:|---:|---|
| 2026-11-20 21:04:14 -0500 | `3110337` | yes | unrecorded | clang version 23.1.5 `-O2` | 2,188.2 | 0.2601 | 37.1 | [devlog-3110337.md](devlog/devlog-3110337.md) |
| 2026-11-20 21:08:12 -0500 | `3110337` | yes | 0.1.0 | clang version 23.1.5 `-O2` | 2,188.2 | 0.2601 | 37.1 | [devlog-3110337.md](devlog/devlog-3110337.md) |
| 2026-11-20 21:21:17 -0500 | `35565c0` | yes | 0.1.0 | clang version 23.1.5 `-O2` | 2,188.2 | 0.2601 | 37.1 | [devlog-35565c0.md](devlog/devlog-35565c0.md) |
| 2026-11-20 21:27:12 -0500 | `04b19db` | yes | 0.1.0 | clang version 23.1.5 `-O2` | 2,188.2 | 0.2601 | 37.1 | [devlog-04b19db.md](devlog/devlog-04b19db.md) |
| 2026-11-20 21:32:24 -0500 | `df7f489` | yes | 0.1.1 | clang version 23.1.5 `-O2` | 1,706.2 | 0.3336 | 37.1 | [devlog-df7f489.md](devlog/devlog-df7f489.md) |
| 2026-11-20 21:35:53 -0500 | `7197bd1` | yes | 0.2.0 | clang version 23.1.5 `-O2` | 988.7 | 0.5756 | 37.1 | [devlog-7197bd1.md](devlog/devlog-7197bd1.md) |
| 2026-11-20 21:38:42 -0500 | `f18223e` | yes | 0.2.1 | clang version 23.1.5 `-O2` | 794.7 | 0.7162 | 37.1 | [devlog-f18223e.md](devlog/devlog-f18223e.md) |
| 2026-11-20 21:40:59 -0500 | `0573f1a` | yes | 0.2.2 | clang version 23.1.5 `-O2` | 718.7 | 0.7919 | 37.1 | [devlog-0573f1a.md](devlog/devlog-0573f1a.md) |
| 2026-11-20 21:43:28 -0500 | `90ee1ea` | yes | 0.3.0 | clang version 23.1.5 `-O2` | 600.8 | 0.9473 | 37.1 | [devlog-90ee1ea.md](devlog/devlog-90ee1ea.md) |
| 2026-11-20 21:48:47 -0500 | `88db627` | yes | 0.4.0 | clang version 23.1.5 `-O2` | 555.7 | 1.0242 | 37.1 | [devlog-88db627.md](devlog/devlog-88db627.md) |
| 2026-11-20 21:49:53 -0500 | `88db627` | yes | 0.4.0 | clang version 23.1.5 `-O2` | 600.8 | 0.9473 | 37.1 | [devlog-88db627.md](devlog/devlog-88db627.md) |
| 2026-11-20 22:19:24 -0500 | `ba03c09` | yes | 0.5.0 | clang version 23.1.5 `-O2` | 435.7 | 1.3062 | 37.1 | [devlog-ba03c09.md](devlog/devlog-ba03c09.md) |
| 2026-11-20 22:20:37 -0500 | `ba03c09` | yes | 0.5.0 | clang version 23.1.5 `-O2` | 471.8 | 1.2063 | 37.1 | [devlog-ba03c09.md](devlog/devlog-ba03c09.md) |
| 2026-11-20 22:24:21 -0500 | `4ca8908` | yes | 0.5.1 | clang version 23.1.5 `-O2` | 397.8 | 1.4309 | 37.1 | [devlog-4ca8908.md](devlog/devlog-4ca8908.md) |
| 2026-11-20 22:25:39 -0500 | `4ca8908` | yes | 0.5.1 | clang version 23.1.5 `-O2` | 424.9 | 1.3396 | 37.1 | [devlog-4ca8908.md](devlog/devlog-4ca8908.md) |
| 2026-11-20 22:31:05 -0500 | `5db3914` | yes | 0.5.1 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 360.8 | 1.5773 | 37.1 | [devlog-5db3914.md](devlog/devlog-5db3914.md) |
| 2026-11-20 22:34:43 -0500 | `c05a1ce` | yes | 0.5.2 | clang version 23.1.5 `-O2` `rv64im` | 388.8 | 1.4640 | 37.1 | [devlog-c05a1ce.md](devlog/devlog-c05a1ce.md) |
| 2026-11-20 22:35:51 -0500 | `c05a1ce` | yes | 0.5.2 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 348.9 | 1.6315 | 37.1 | [devlog-c05a1ce.md](devlog/devlog-c05a1ce.md) |
| 2026-11-20 22:37:10 -0500 | `c05a1ce` | yes | 0.5.2 | clang version 23.1.5 `-O2` `rv64i` | 416.9 | 1.3653 | 37.1 | [devlog-c05a1ce.md](devlog/devlog-c05a1ce.md) |
| 2026-11-20 22:40:50 -0500 | `73c1fbc` | yes | 0.5.3 | clang version 23.1.5 `-O2` `rv64im` | 366.8 | 1.5518 | 37.1 | [devlog-73c1fbc.md](devlog/devlog-73c1fbc.md) |
| 2026-11-20 22:41:52 -0500 | `73c1fbc` | yes | 0.5.3 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 310.9 | 1.8309 | 37.1 | [devlog-73c1fbc.md](devlog/devlog-73c1fbc.md) |
| 2026-11-20 22:43:07 -0500 | `73c1fbc` | yes | 0.5.3 | clang version 23.1.5 `-O2` `rv64i` | 391.9 | 1.4524 | 37.1 | [devlog-73c1fbc.md](devlog/devlog-73c1fbc.md) |
| 2026-11-20 22:48:39 -0500 | `241a9af` | yes | 0.5.4 | clang version 23.1.5 `-O2` `rv64im` | 335.8 | 1.6951 | 37.1 | [devlog-241a9af.md](devlog/devlog-241a9af.md) |
| 2026-11-20 22:49:50 -0500 | `241a9af` | yes | 0.5.4 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 269.9 | 2.1091 | 37.1 | [devlog-241a9af.md](devlog/devlog-241a9af.md) |
| 2026-11-20 22:51:16 -0500 | `241a9af` | yes | 0.5.4 | clang version 23.1.5 `-O2` `rv64i` | 358.8 | 1.5861 | 37.1 | [devlog-241a9af.md](devlog/devlog-241a9af.md) |
| 2026-11-20 22:58:24 -0500 | `5f1f6b1` | yes | 0.5.5 | clang version 23.1.5 `-O2` `rv64im` | 287.8 | 1.9777 | 37.1 | [devlog-5f1f6b1.md](devlog/devlog-5f1f6b1.md) |
| 2026-11-20 22:59:36 -0500 | `5f1f6b1` | yes | 0.5.5 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 251.9 | 2.2598 | 37.1 | [devlog-5f1f6b1.md](devlog/devlog-5f1f6b1.md) |
| 2026-11-20 23:01:05 -0500 | `5f1f6b1` | yes | 0.5.5 | clang version 23.1.5 `-O2` `rv64i` | 308.9 | 1.8428 | 37.1 | [devlog-5f1f6b1.md](devlog/devlog-5f1f6b1.md) |
| 2026-11-20 23:12:36 -0500 | `f78d62a` | yes | 0.6.0 | clang version 23.1.5 `-O2` `rv64imb` | 285.8 | 1.9916 | 37.1 | [devlog-f78d62a.md](devlog/devlog-f78d62a.md) |
| 2026-11-20 23:13:45 -0500 | `f78d62a` | yes | 0.6.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime | 247.8 | 2.2964 | 37.1 | [devlog-f78d62a.md](devlog/devlog-f78d62a.md) |
| 2026-11-20 23:15:11 -0500 | `f78d62a` | yes | 0.6.0 | clang version 23.1.5 `-O2` `rv64im` | 287.8 | 1.9777 | 37.1 | [devlog-f78d62a.md](devlog/devlog-f78d62a.md) |
| 2026-11-20 23:16:18 -0500 | `f78d62a` | yes | 0.6.0 | clang version 23.1.5 `-O2` `rv64im` fast runtime | 251.9 | 2.2598 | 37.1 | [devlog-f78d62a.md](devlog/devlog-f78d62a.md) |
| 2026-11-20 23:23:03 -0500 | `a6e3f87` | yes | 0.7.0 | clang version 23.1.5 `-O2` `rv64imb` | 256.8 | 2.2163 | 37.1 | [devlog-a6e3f87.md](devlog/devlog-a6e3f87.md) |
| 2026-11-20 23:24:16 -0500 | `a6e3f87` | yes | 0.7.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime | 216.9 | 2.6243 | 37.1 | [devlog-a6e3f87.md](devlog/devlog-a6e3f87.md) |
| 2026-11-20 23:25:56 -0500 | `a6e3f87` | yes | 0.7.0 | clang version 23.1.5 `-O2` `rv64im` | 258.8 | 2.1991 | 37.1 | [devlog-a6e3f87.md](devlog/devlog-a6e3f87.md) |
| 2026-11-20 23:53:49 -0500 | `129e37e` | yes | 0.7.1 | clang version 23.1.5 `-O2` `rv64imb` | 256.8 | 2.2163 | 37.1 | [devlog-129e37e.md](devlog/devlog-129e37e.md) |
| 2026-11-20 23:55:03 -0500 | `129e37e` | yes | 0.7.1 | clang version 23.1.5 `-O2` `rv64imb` fast runtime | 216.9 | 2.6243 | 37.1 | [devlog-129e37e.md](devlog/devlog-129e37e.md) |
| 2026-11-20 23:56:41 -0500 | `129e37e` | yes | 0.7.1 | clang version 23.1.5 `-O2` `rv64im` | 261.8 | 2.1739 | 37.1 | [devlog-129e37e.md](devlog/devlog-129e37e.md) |
| 2026-11-20 23:58:24 -0500 | `129e37e` | yes | 0.7.1 | clang version 23.1.5 `-O2` `rv64i` | 273.9 | 2.0780 | 37.1 | [devlog-129e37e.md](devlog/devlog-129e37e.md) |
| 2026-11-21 00:41:58 -0500 | `53c6772` | yes | 0.8.0 | clang version 23.1.5 `-O2` `rv64imb` pipelined core | 588.6 | 0.9670 | 6.1 | [devlog-53c6772.md](devlog/devlog-53c6772.md) |
| 2026-11-21 00:43:03 -0500 | `53c6772` | yes | 0.8.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime pipelined core | 484.6 | 1.1744 | 6.1 | [devlog-53c6772.md](devlog/devlog-53c6772.md) |
