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
| 01:03:58 | Commit `251ac29`, pipelined core restructured for clock rate (0.8.1); tagged `cpu-v0.8.1`, local only | git |
| 01:03 to 01:30 | ECP5 results for the 0.8.1 steps (512-line caches): step 2 `p081b` (fetch queue and X stage) **24.85 MHz**, 41,002 cells, critical path 40.3 ns (8.9 logic, 31.4 routing) from E's instruction through the E redirect into the return-stack enables; step 4 `p081d` (= tagged 0.8.1) **28.29 MHz**, 41,178 cells, 35.3 ns (7.6 logic, 27.7 routing). 0.8.1 is only 1% faster than 0.8.0 (28.00 MHz) and 50% larger: the logic on the longest path fell from 13.8 to 7.6 ns but routing stayed near 28 ns. Step 3 `p081c` still routing | output |
| 01:05 | New user direction: move toward the Apple M5 (an out-of-order design). Plan: a third implementation, `rtl/cpu/rv64_ooo.sv`, built in stages that each pass the full trace regression | output |
| 01:05 to 01:25 | Out-of-order model added to `sim/cpu/bench/pipeline_model.py` by a side agent (`--ooo`; Python 3.12.10; in-order output unchanged, checked with `cmp`). Caches always hit; ordering (a) loads wait for older stores to retire, (b) loads never wait (an upper bound), (c) loads wait for older stores to issue (store-queue forwarding). `rv64imb` reference trace, DMIPS/MHz: in-order w1 BTB256 0.961, w2 1.361; out-of-order 1-wide (a) 0.954 to 0.972; **2-wide, ROB 32, IQ 16, 2 ALUs, 1 memory port, checkpoint recovery: (a) 1.443, (c) 1.733, (b) 1.749**; 4-wide ROB 64 3 ALUs (b) 2.428. Memory ordering is the largest lever ((a) to (c) +20%), then width; under (a) a load latency of 3 instead of 2 costs 15%; recovery (retire, early, checkpoint) is worth 3% here and 9% on the fast-runtime trace. Limits: no cache misses, no wrong-path occupancy, no clock-rate dimension | output |
| 01:06 to 01:22 | Stage A written (`rtl/cpu/rv64_ooo.sv`, 1,011 lines): the pipelined core's front end; rename of one instruction per clock onto 64 physical registers; 32-entry reorder buffer retiring one per clock; 8-entry issue queue with wakeup and select; an integer port (multiply/divide unit behind it) and a two-stage load/store port; stores write at retirement; loads issue when every older store has retired; mispredict redirects fetch at execute and rename waits for the branch to retire. Decode, B and M logic reused from the pipelined core. `--core ooo` added to `test_cpu.py`, `check_bitmanip.py`, `run_bench.py`, `run_dhrystone.ps1` and the run log | output |
| 01:19 to 01:23 | First regression of stage A: 53 of 55 programs pass; `memory_lanes` and `mul_then_store_pad0` fail at 19 wait cycles with "unstable stalled request". A debug bench (`build/cpu/ooo-debug/`) showed a load miss's held request dropped: completing a store in the load/store port's first stage also cleared its second stage. Fixed; that exposed hangs in three programs: when the first stage finished a store in the same clock the second finished a load, the second stage was not cleared, and the finished load later read an unwritten cache tag (X). Fixed by handling the two cases separately | output |
| 01:23 to 01:25 | Stage A: regression 165/165 with default and 2-line caches; `check_bitmanip.py --core ooo` passes. Unlogged Dhrystone (`rv64imb`, reference): **0.7888 DMIPS/MHz**, below the pipelined core's 0.9670 and the model's 1-wide (a) 0.954: this design's load-to-dependent latency is 3 clocks and loads wait for older stores to retire | output |
| 01:29 to 01:35 | Logged runs, out-of-order core (`-Core ooo -Record`): `rv64imb` reference 0.7888 DMIPS/MHz, fast runtime 0.9306; [devlog-251ac29.md](devlog/devlog-251ac29.md). ECP5 run of stage A (`o090`) started | record |
| 01:37:20 | Commit `f1f94c4`, out-of-order stage A (0.9.0); tagged `cpu-v0.9.0`, local only | git |
| 01:37 to 01:40 | 0.9.1 written (out-of-order core): a load issues once every older store has its address and data; in its second stage it scans the older stores still in the reorder buffer for its 8-byte beat and takes the youngest one's data when it covers every byte the load reads; on a partial overlap it waits for those stores to retire and reads the bus. A store retiring in the clock a load reads the cache passes its bytes into that read. Regression 165/165 with default and 2-line caches; B cross-check passes. Unlogged Dhrystone 0.9428 DMIPS/MHz (from 0.7888, +19.5%; the model predicted about +20% for this ordering change) | output |
| 01:41 to 01:45 | New test `store_load_forwarding` (full, partial, narrower and wider overlaps, the younger of two stores, a dependent chain; run twice): all three cores pass, 56 programs x 3 = 168 runs each, and the out-of-order core with 2-line caches. Mutation check: with forwarding disabled in the out-of-order core, 5 programs fail including the new test; the RTL was restored and checked | output |
| 01:47 to 01:53 | Logged runs, out-of-order 0.9.1 (`-Core ooo -Record`): `rv64imb` reference **0.9428 DMIPS/MHz**, fast runtime **1.0684**; [devlog-f1f94c4.md](devlog/devlog-f1f94c4.md) | record |
| 01:55:04 | Commit `7bf8f3d`, store-to-load forwarding (0.9.1); tagged `cpu-v0.9.1`, local only | git |
| 01:56 to 02:01 | 0.9.2 written: the out-of-order core made two-wide (body rewritten, 1,280 lines): two-instruction fetch from an aligned beat with a second BTB lookup (none after a predicted-taken transfer, call or return), 8-entry fetch queue without the F-to-D bypass, two D slots each checking its prediction, rename and dispatch of two per clock (the second may read the first's result), a second integer port using the multicycle core's `simple_alu` for simple integer and B operations, retirement of two per clock (the second never a store, `fence.i`, mispredicted branch or trap, and not two control transfers at once) | output |
| 02:01 to 02:03 | First run: 55 of 56 programs pass; `store_load_forwarding` hung. The load/store port's second stage held a load waiting (partial overlap) for older stores to retire, while an older memory instruction at the ROB head, still in the issue queue, could not enter the port. Fixed by issuing memory instructions in program order (the port takes the oldest one, when ready) | output |
| 02:03 to 02:05 | 0.9.2: regression 168/168 with default and 2-line caches; B cross-check passes. Unlogged Dhrystone (`rv64imb`, reference): **1.2768 DMIPS/MHz** (from 0.9428, +35%). The model's point for this width (ROB 32, IQ 16, 2 ALUs, checkpoint recovery, store-queue ordering, load latency 2) is 1.733; this design has IQ 8, load latency 3, no checkpoint recovery, in-order memory issue and one more front-end stage | output |
| 02:08 to 02:14 | Logged runs, out-of-order 0.9.2: `rv64imb` reference **1.2768 DMIPS/MHz**, fast runtime **1.4419**; [devlog-7bf8f3d.md](devlog/devlog-7bf8f3d.md) | record |
| 02:14 | ECP5 run of out-of-order stage A (0.9.0, 512-line caches): **does not fit**. Yosys maps it to 107,072 LUT4 (part: 83,640), 31,302 PFUMX, 13,414 L6MUX21, 17,976 flip-flops, 2,133 CCU2C, 388 DPR16X4, 12 DP16KD, 16 MULT18X18D (624.6 s); nextpnr: "Unable to find legal placement for all cells, design is probably at utilisation limit" (1,212.6 s in all). The physical register file and the reorder-buffer fields are flip-flops with many read and write ports. The out-of-order results so far are simulation results only; fitting the design is a separate task | output |
| 02:16:03 | Commit `11acc17`, two-wide out-of-order core (0.9.2); tagged `cpu-v0.9.2`, local only | git |
| 02:16 to 02:18 | A 16-entry issue queue tried: 1.2913 DMIPS/MHz (+1.1%, as the model predicted); not kept, because the design already does not fit and the queue's area doubles. Index widths now follow `IQ_N` | output |
| 02:18 to 02:26 | Stall statistics for the two-wide core on Dhrystone (debug bench `build/cpu/ooo-debug/tb_ostat.sv`, timed region, 222,875 clocks): retire 2 in 50% of clocks, 1 in 23%, none in 27%; issue queue with fewer than two free slots in 43%; a store waiting at the head in 9% (all of it the one-clock-ahead tag read not ready: 20,525 clocks); oldest memory instruction not ready in 38%; memory port used in 45% | output |
| 02:26 to 02:29 | Pending store update: a retiring store writes the bus at once; its data-cache update and instruction-cache invalidation follow one clock later from a register (loads reading that line merge it; fetch treats that index as a miss for that clock). Store wait at the head fell to 11 clocks but Dhrystone stayed at 1.2768: the head now waited for unfinished instructions instead (56,197 clocks, half of them loads). The single in-order memory port is the limit | output |
| 02:30 to 02:36 | Stores split into address and data: a store issues once its address is known and reads its data register at retirement; forwarding reads that register and waits until it is written; loads wait only for older store addresses. Regression 168/168 (default and 2-line caches), B cross-check passes | output |
| 02:37 to 02:40 | WSL crashed during the next run (`Wsl/Service/E_UNEXPECTED`), most likely from memory pressure: several Yosys syntheses (the area study and the 0.7.x ECP5 runs) were running at once on the 15 GB VM. The 0.7.0/0.7.1 ECP5 job (in Yosys since 23:36) ended with exit code 15 and never produced a result; the area study's runs were lost. WSL restarted with `wsl --shutdown`; agents told to run at most two syntheses at a time | output |
| 02:41 to 02:51 | Dhrystone on the split-store core: reference runtime 1.5648 DMIPS/MHz (from 1.2768, +22.6%) with all checks passing; a logged reference run at 02:54:13 used this RTL. The fast-runtime run then failed its differential check at event 8169 (`lw` at 0xa34 read 0xb, reference 0xc). A cache-line watch (`tb_dbg3.sv`) showed the cause: the data-cache write was `if (fill) ... else if (pending store)`, so a fill to any other line in the same clock dropped the store's update. Fixed so both write (the store's update is skipped only for a fill to its own line). Also changed: a load that waited in its second stage reads the bus afterwards | output |
| 07:13 to 07:15 | After a session restart: regression 168/168 (default and 2-line caches), B cross-check passes; the 0.9.3 history row and rubric hashes were re-recorded for the fixed RTL | output |
| 07:15 to 07:21 | Logged runs, out-of-order 0.9.3: `rv64imb` reference **1.5648 DMIPS/MHz**, fast runtime **1.5777**; [devlog-11acc17.md](devlog/devlog-11acc17.md). (The 02:54:13 reference row in the run index is the same result on the RTL before the fill fix) | record |
| 07:21:45 | Commit `8f207a0`, split stores and deferred store cache update (0.9.3); tagged `cpu-v0.9.3`, local only | git |
| 07:22 | Stall statistics on 0.9.3 (181,861 clocks): retire 2 in 62% of clocks, 1 in 28%, none in 11%; rename 2 in 65%; fetch delivered about 1.63 instructions per clock (two only from the start of a beat); memory port used in 55% | output |
| 07:23 to 07:28 | 0.9.4: fetch also reads the next beat, so the second instruction can come from it. Regression 168/168 (default and 2-line caches). Dhrystone `rv64imb` reference 1.5778 DMIPS/MHz (+0.8%), fast runtime 1.6180 (+2.6%): two-wide rename and retirement are now the ceiling | output |
| 07:30 to 07:35 | Logged runs, out-of-order 0.9.4: reference **1.5778**, fast runtime **1.6180**; [devlog-8f207a0.md](devlog/devlog-8f207a0.md) | record |
| 07:25 | User direction: size the core after the Apple M5 (FPGA fit later) and raise IPC. M5 P-core figures from the one independent study (useless-husband/m5-uarch): 10 NOPs per clock, 8 integer ALUs, 3 multipliers, 3 loads and 2 stores per clock, 2 taken branches per clock, about 1,334 instructions in flight for an ordinary mix, 396 integer rename registers, L1I 192 KiB, L1D 128 KiB, 3-clock load-to-use, 16.7-clock mispredict | output |
| 07:39:24 | Commit `af0a3a1`, cross-beat fetch (0.9.4); tagged `cpu-v0.9.4`, local only | git |
| 07:40 to 07:48 | M5 detail from the study's results file (`results/apple-m5/apple-m5.json`, read by a side agent): integer add 1 clock at 6.7 to 7.7 per clock; multiply 3 per clock, 3 clocks; divide 0.5 per clock, 7 clocks; loads 3 per clock, 3 clocks (pointer chase); stores 2 per clock; branches 3 not-taken or 2 taken per clock; store queue 137, load queue 486, unresolved branches 194; move elimination at rename; store-to-load forwarding as low as 0.66 clocks (no explanation given); constant-value load prediction (P core only). BTB, return-stack and scheduler sizes are not measured | output |
| 07:48 to 08:12 | 0.10.0 written: `rtl/cpu/rv64_ooo.sv` replaced by a wide behavioural model sized after those figures (8 instructions per clock fetched, renamed and retired; 128-entry ROB; 160 physical registers; 64-entry issue queue; 8 ALUs, 3 of them full ports for branches, system and M; 3 load and 2 store-address ports, oldest first; loads replay from the issue queue; a rename-map snapshot per branch for recovery in the clock it executes; 128 KiB caches). New outputs `rt_valid`, `rt_pc`, `rt_insn`, `rt_rd`, `rt_data`, `rt_next` (8 slots); `tb_core.sv` and `tb_bench.sv` log them under `WIDE_TRACE`, and a store's write is logged just before that store's own retirement in whatever slot. `test_cpu.py`, `check_bitmanip.py` and `run_bench.py` pass `-DWIDE_TRACE` for `--core ooo` | output |
| about 08:15 | First run: all 56 programs at 3 wait patterns pass with default caches; Dhrystone `rv64imb` reference **4.3167 DMIPS/MHz** (131.8 clocks per run, 4.17 instructions per clock; all checks pass, traces match at 0 and 7 wait cycles) | output |
| 08:15 to 08:35 | With 2-line caches the regression timed out: a load-miss livelock (with a 1-clock bus, the next miss was allocated as soon as a fill arrived, and its fill replaced the line before the first load replayed). Fixed with a one-entry fill buffer that loads can read after the line is replaced (retiring stores update it), the miss unit serving the oldest missing load, and the buffer reserved for that load until it completes. Also: `tb_core.sv` declared the wide trace wires after their first use (Icarus made implicit wires, then merged them); declarations moved first | output |
| about 08:38 | 0.10.0: regression 168/168 with default and 2-line caches; `check_bitmanip.py --core ooo` passes; the multicycle and pipelined cores still pass 168/168 with the changed testbench | output |
| 08:45 to 09:05 | Fast-runtime Dhrystone on 0.10.0 (`run_dhrystone.ps1 -Core ooo -Runtime fast`) never finished; the first reference logged run at 08:51 (4.3169) used this same RTL. First diagnosis: the fill-buffer lock was tested as "owner live and not done", and a reused ROB index held it forever; replaced by an explicit `fb_lock` flag. A reference run with that change then timed out at the old 1,800 s step limit (`vvp ... tb_bench.vvp` TimeoutExpired) | output |
| 09:05 | User direction: 5-minute limits for runs. `run_bench.py` steps, `check_bitmanip.py` and the debug scripts now stop after 300 s (test_cpu.py already 60 s per program) | edit |
| 09:05 to 09:30 | Bounded probes (`build/cpu/ooo-debug/fastprobe.sh`, `tb_wstat.sv`, `+max_cycles`) found two faults. (1) Starvation: the head load replayed every other clock while younger missing loads kept taking the one-clock miss unit; fixed by letting only the oldest unfinished load start a miss. (2) Hang at 5,328 retirements: head load `ld a3, 8(a1)` at 0xdbc waiting, miss unit and bus idle, `fb_lock=1` held by ROB 76, which had already retired, because its fill arrived after it finished (squash or completion before the fill). Fixed: the fill sets the lock only if the miss owner is still in flight (`mu_owner_v`, cleared when the owner is discarded or on a flush) | debug |
| 09:39 to 09:42 | With both fixes: fast-runtime probe finishes (73,947 clocks for the region, 2,000,000-clock bound); reference probe 65,933 clocks (was 65,922). Regression `test_cpu.py --core ooo` 168/168 at default and 2-line caches; `check_bitmanip.py --core ooo` passes. `dual_issue_loads` takes 52 clocks instead of 35 (misses are now served oldest first, one at a time) | output |
| 09:43 to 09:55 | Logged runs, uncommitted 0.10.0 on `af0a3a1` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast`; clang 23.1.5 `-O2`, Icarus Verilog in Ubuntu 24.04): reference **4.3161 DMIPS/MHz** (131.9 clocks per run), fast runtime 3.848 (147.9 clocks per run). Surprise: the word-wise fast runtime is slower than the byte-wise reference on the wide core, the reverse of every earlier core; to be explained (likely store-to-load partial overlaps or the one-store-per-clock retirement). The wide-core wait loop `pgrep -f run_bench.py` matched its own shell and always ran to its 290 s limit | output |
| 09:56:30 | Commit `4ee3a9a`, wide out-of-order core (0.10.0); tagged `cpu-v0.10.0`, local only | git |
| 09:57 to 10:04 | 0.10.1, two predicted-taken transfers per fetch group (one call or return per group), from the staged scratch variant with the fill-buffer fixes. Timing probe (`fastprobe.sh`, `tb_wstat.sv`): reference region 65,933 to 60,935 clocks (-7.6%), fast runtime 73,947 to 65,944 (-10.8%); ROB near full in 15,952 of 60,935 clocks, bus busy 63%. Regression 168/168 with default and 2-line caches, `check_bitmanip.py --core ooo` passes | output |
| 10:04 to 10:16 | Logged runs on `4ee3a9a` plus uncommitted 0.10.1 (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast`; clang 23.1.5 `-O2`): reference **4.6702 DMIPS/MHz** (121.9 clocks per run), fast runtime 4.3154 (131.9 clocks per run) | output |
| 10:06 to 10:20 | Trial, not committed: paired store writes (a store write carries a second store; memory applies it only if the first succeeds, `mem_*2` ports, `PAIR_WRITES` parameter; scratch copies in `build/cpu/ooo-debug/w110root/`). Dhrystone stores are 14.1% of retirements (39,798 W of 281,929 R in `trace-stall0.trace`), so one write per clock caps the core near 77 clocks per run (about 7.4 DMIPS/MHz). Probe: reference 60,935 to 60,925 clocks, fast runtime 65,944 to 66,932 (worse); bus busy 63% to 52%. Conclusion: stores are not the current limit; kept staged for later | output |
| 10:20 to 10:25 | New head-stall profile (`build/cpu/ooo-debug/tb_hstat.sv`, `hprobe.sh`: the first not-done entry of the 8-entry retirement window, weighted by lost slots). Reference: ALU 40,336, branch 35,869, load 17,305, multiply/divide 14,516, empty 7,206, store 1,195 lost slots; hottest are the byte loop of `strcmp` (0xd28 to 0xd50) and `divw` at 0x1e4. Fast runtime: load 74,814, ALU 77,895, branch 63,355 lost slots; hot loads follow the word-wise `memcpy`/`strcpy` stores (partial overlaps wait for the store to retire) | output |
| 10:22 | User direction: get a second opinion from a Codex CLI subagent (GPT 6.2 Astra) reviewing adversarially, and add that to AGENTS.md (done). Not found on PATH or in WSL at first; the user pointed to the ChatGPT desktop app: `codex-cli 0.167.0-alpha.3.2` at `%LOCALAPPDATA%\OpenAI\Codex\bin\5cb1e6583e4c030c\codex.exe`, `~/.codex/config.toml` model `gpt-6.2-astra`, effort `xhigh` | tool |
| 10:24 | Commit `cdcbafc`, two taken branches per fetch group (0.10.1), and `322739e` (DEVLOG path fix); tagged `cpu-v0.10.1`, local only | git |
| 10:25 to 10:40 | Codex CLI (`codex-cli 0.167.0-alpha.3.2`, `gpt-6.2-astra`, effort xhigh; `codex exec -s read-only -C <repo> -`, prompt in the scratchpad file `codex_review_prompt.md`) reviewed `af0a3a1..cdcbafc` adversarially. Findings: (1) a failed fill's error outlives a squash and can fault a correct-path load; (2) a fully forwarded load skips the read access check (`fault_kind=2`); (3) `fence` does not keep a younger load behind older stores; (4) retirement pulses stay set after a store-error halt; (5) `RW>8` corrupts dispatch silently; risks: return-stack pointer not restored after a flush or rename redirect, a store write could be logged one clock before its store retires without failing the bench, regression and Dhrystone use 4 KiB caches (testbench and SoC pass 512 beats) though the core defaults to 128 KiB, the bench profile swaps the start-marker store for the stop one, dependent multiply/divide spacing is 2/6 clocks not 3/7, the oldest-miss rule lets a load without an address block a younger miss, the head-stall probe cannot see the one-store-per-clock retirement stop, and the 0.10.0 history row named the wrong RTL hash. All fixed in 0.11.0 except the bench profile and the oldest-miss rule (open); the history row is corrected | review |
| 10:20 to 10:28 | Mispredict profile (`tb_hstat.sv` with a per-PC count): every remaining mispredict is a loop exit, once per run per loop (`strcmp`/`strcpy` loops, `Func_2`, `main`): 3 per run on the reference runtime, 9 on the fast one | output |
| 10:22 to 10:30 | Loop predictor (scratch `patch_lp.py`): reference 60,935 to 54,465 clocks (-10.6%), fast runtime 65,944 to 51,521 (-21.9%); mispredicts 1,519 to 27 (reference). Regression with candidate options (`test_cpu.py --core-source --out-dir`, new) 168/168 at both cache sizes. The reference run then has the ROB near full in 50,670 of 54,465 clocks and the bus busy 70%: store-write bound | output |
| 10:18 to 10:25 | Trial, not kept: byte-granular forwarding alone (scratch `wfwd`) left the fast runtime at 65,944 clocks; regression passed | output |
| 10:26 | User direction: a separate agent for caches and memory, working at the same time, coordinated, Dhrystone runs launched together. Started; it works on its own copies (`build/cpu/ooo-debug/mem/`, scratch `mem/`) and hands off patch scripts; the lead alone writes `rtl/`, DEVLOG and commits. Its log: `build/cpu/ooo-debug/mem/NOTES.md` | process |
| 10:36 to 10:42 | Codex fixes on the loop-predictor build (scratch `patch_fix_0102.py`). Requiring a successful read before any forwarded load finished cost 7,000 clocks on the fast runtime (51,521 to 58,510; a variant without it 51,523; the multiply/divide latency fix costs about 2); final form: a fully forwarded load wakes consumers at once and finishes after the read, fast runtime 53,019, reference 54,465. Regression 168/168 at both cache sizes. `tb_core.sv` now fails when a successful store write is not followed by its store retiring on the same edge. `hprobe.sh` builds into a temporary file per run (two runs on the same benchmark had overwritten each other's build, invalidating one pair of probes) | output |
| 10:29 to 10:36 | Memory agent (from its NOTES.md): 4 KiB vs 128 KiB caches change nothing on the reference runtime; on the fast runtime conflict misses cost 3,000 clocks (0.10.1) to 5,000 (loop predictor). Hand-off 1a, 2-way set-associative data cache of the same size: fast runtime 51,521 to 46,538 (-9.7%), reference unchanged. Hand-off 1b, paired store writes (the 0.11.0 trial re-expressed): reference 54,465 to 46,010 (-15.5%), fast runtime flat. Regression passed at both cache sizes | output |
| 10:42 to 10:45 | Integration (fixes + 1a + 1b, `build/cpu/ooo-debug/introot`, `int_check.sh`): reference 46,010 clocks, fast runtime 46,528; regression 168/168 at both cache sizes | output |
| 10:45 to 10:49 | 0.11.0 in the repository (`full_check.sh`): out-of-order 168/168 with default and 2-line caches, `check_bitmanip.py --core ooo` passes, multicycle and pipelined cores 168/168 with the changed `tb_core.sv` and `test_cpu.py` | output |
| 10:49 to 11:00 | Joint logged runs, 0.11.0 uncommitted on `322739e` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast -Record`; clang 23.1.5 `-O2`): reference **6.1851 DMIPS/MHz** (92.0 clocks per run), fast runtime **6.1162** (93.1 clocks per run) | output |
| 10:50 to 10:53 | ROB 256 and 512 (288 and 544 physical registers; probe only): reference 46,007 and 46,008 clocks, fast runtime 46,528 both, the same as ROB 128. The reference run fills any window: it is bound by retirement of stores, not by window size | output |
| 10:53 to 11:05 | Value prediction trial (scratch `patch_vp.py`): a load, multiply or divide whose last 8 results were equal gives that value to its consumers at rename; a wrong guess refetches after it retires. Probe: fast runtime 46,528 to 41,118 clocks (-11.6%), reference unchanged (46,010). Regression 168/168 at both cache sizes; new directed test `value_change_after_repeats` (a loaded value repeats 40 times, then changes; a first version with 11 repeats never made the predictor confident because the whole loop fit in the 128-entry window) forces value mispredicts on the load and the multiply (seen with an instrumented copy) and passes | output |
| 11:01:30 | Commit `8721ca2`, architecture 0.11.0 (loop predictor, two-way data cache, paired store writes, review fixes); tagged `cpu-v0.11.0`, local only. A second Codex review (of `322739e..8721ca2`) started in the background | git |
| 11:01 to 11:05 | `full_check.sh` with value prediction in `rtl/`: all three cores 171/171 (57 programs, with `value_change_after_repeats`), 2-line caches and `check_bitmanip.py` pass | output |
| 11:03 to 11:05 | Fetch predecode trial (scratch `patch_predecode.py`): fetch sends direct jumps and calls to their targets, returns to the return stack, and BTB-missing backward branches taken; rename trusts fetch for conditional branches. Rename-stage redirects 2,502 to 0; fast runtime 41,118 to 39,118 clocks (-4.9%), reference 46,010 to 45,990 | output |
| 11:05 to 11:08 | `full_check.sh` with value prediction and predecode: all three cores 171/171, 2-line caches and `check_bitmanip.py` pass. Recorded as 0.11.1 | output |
| 11:10 to 11:14 | New probe counter (`tb_hstat.sv`): retirement slots whose instructions were done but did not retire in the next clock, which is the store rule (one write request per clock, at most two stores, nothing past the second store). Fast runtime 64,510 such slots against about 25,000 lost to unfinished instructions; reference 89,040 against about 3,900. The store rule is now the main limit on both runtimes; passed to the memory agent as its top priority | output |
| 11:08 to 11:15 | Logged runs for the value-prediction + predecode build (`run_dhrystone.ps1 ... -Record`, reference then fast): the reference run finished at 11:14:47 with 6.1878 DMIPS/MHz (92.0 clocks per run; RTL `cc463c46fee9`, an intermediate 0.11.1 build that was not released; its record in `cpu/dhrystone-rv64imb-ooo-results.json` was reverted). The fast run failed: `rtl/cpu/rv64_ooo.sv` was edited during the run and the edit had a syntax error (a statement placed between `end` and `else`), so its compile failed (`syntax error` at line 730). Lesson: do not edit `rtl/` while a logged run is in progress | output |
| 11:05 to 11:16 | Second Codex review (of `322739e..8721ca2`, same command, prompt `codex_review_prompt_0110.md`): no wrong-result, lost-store or deadlock bug found. Risks: a held fetch's fault can reach a redirected fetch of the same beat; no test exercises a paired-write fault; the bench profile moves one instruction across a marker with paired stores (275,031 vs 275,030 and 223,031 vs 223,030; the tb_bench comment claiming equal counts was wrong); `--core-source` reports were hashed from `rtl/`; the return-stack fix restores the pointer only; replaying loads can hold all load ports; the loop predictor can predict an early exit at its 255 limit; documentation said 0.10.2 (never released) and one store per clock. Fixed in 0.11.1: the fetch fault, the 255 limit, report hashes (`simulated_core_sha256`) and cache labels, the comments and documentation; new tests `paired_store_fault_first`, `paired_store_fault_second`, `paired_store_overlap`, `forwarded_load_read_fault`. Open: return-stack entry repair, load-port starvation | review |
| 11:00 to 11:19 | Memory agent final report (its log `build/cpu/ooo-debug/mem/NOTES.md`): hand-off 2, loads wake consumers at issue and memory-dependence speculation with a 256-entry load-wait table (a store that resolves its address marks younger loads that read its bytes; a marked load flushes at the head and refetches); hand-off 3, retirement continues past the clock's store write. On 0.11.1: reference 45,990 to 44,550 clocks (-3.1%), fast runtime 39,118 to 37,609 (-3.9%); six directed memory-dependence programs. Its finding: once retirement passes the store write, most "done but not retired" slots turn into waits on unfinished instructions; more than two stores per write would gain about 5% at most | output |
| 11:19 to 11:27 | Integrated hand-offs 2 and 3 and the six memory-dependence programs into 0.11.1 (`test_cpu.py`, 67 programs). Probe 44,550 / 37,609 clocks (same as the agent's). `full_check.sh`: all three cores 201/201, 2-line caches and `check_bitmanip.py` pass | output |
| 11:05 to 11:27 | User direction: a GitHub Pages site in `/docs` (a Sonnet agent): a gallery of one generated artwork per architecture version (the processor's units drawn after its parameters) styled as an intimate Parisian gallery, and a journal of this log. Built by `scripts/build_site.py` into `docs/` (27 artworks, 226 timeline rows, 60 runs). Checked in the Browser pane through a local server: the lightbox works; at 375 px the gallery (396 px) and home page (430 px) scroll sideways, sent back for fixing. Not published (needs a push) | site |
| 11:22 to 11:27 | User direction: study the SC25 RISC-V HPC workshop slides by S. Nemawarkar (a Sonnet agent; read with `pdftotext`). They describe Condor's Cuzco core: 8-wide, 256-entry ROB, 8 ALUs, 4 load/store units, 64 KB 8-way L1 caches, TAGE-SC-L, time-based scheduling, claimed above 17.5 DMIPS/MHz (configuration and compiler not given). Usable for us: instruction fusion at decode (dependent pairs, store pairs); the scheduler is an area and power measure a behavioural model cannot show | research |
| 11:27 to 11:36 | Joint logged runs, 0.11.1 uncommitted on `8721ca2` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast -Record`; clang 23.1.5 `-O2`): reference **6.3878 DMIPS/MHz** (89.1 clocks per run), fast runtime **7.5667** (75.2 clocks per run) | output |
| 11:37 | Commit `b12c1d4`, architecture 0.11.1; tagged `cpu-v0.11.1`, local only | git |
| 11:30 to 11:38 | Site fixes by its agent: at 375 px no page scrolls sideways (`docs/assets/style.css`: narrower spotlight and hero glow, clipped overflow); regenerated after the 0.11.1 tag (`python -B scripts/build_site.py`: 27 artworks, 233 timeline rows, 62 runs); `check_repo.py` passes. Committed as its own change; not published | site |
| 11:27 to 11:31 | Fusion trial (scratch `patch_fuse.py`; the trace has a simple integer instruction feeding the next one in 15% of instructions: 6.6% into another ALU instruction, 3.7% `jalr`, 3.0% branches, 2.2% store and 1.5% load addresses): fast runtime 37,609 to 37,108 clocks (-1.3%), reference 44,550 to 44,542. The `divw` at 0x1e4 (always 9 / 7 = 1, so value prediction frees its consumers) still holds the head until it finishes | output |
| 11:31 to 11:34 | Remaining mispredicts, 3 per run on the fast runtime at 0x284, 0xac8 and 0xe84. 0x284 and 0xe84 share loop-predictor index `pc[9:2]` = 0xa1; a 1024-entry loop predictor: fast runtime 37,108 to 34,126 (-8.0%). 0x284 is always taken but its BTB entry is evicted by 0xe84 (same index), and 0xac8 is never taken but backward, so predecode predicts it taken and it never enters the BTB | output |
| 11:34 to 11:36 | BTB 1024 entries, and a branch that has gone one way at least 4 times with no exit learned is predicted that way from the loop predictor (scratch `patch_bp2.py`): fast runtime 34,126 to 31,158 clocks (-8.7%), reference 44,542 to 38,103 (-14.5%); about 0 mispredicts per run | output |
| 11:37 to 11:46 | 0.11.2 (fusion + `patch_bp2.py`) in `rtl/`: `full_check.sh` all three cores 201/201, 2-line caches and `check_bitmanip.py` pass. New test `fused_pairs` (a producer that overwrites its own source retires and frees the register before its fused consumer, delayed by a divide, executes; fused load and store addresses and branch operand); its first version looped without end (a filler `addi` also incremented the loop counter: "Reference instruction budget exceeded"), fixed; out-of-order 204/204 at both cache sizes and multicycle 204/204 | output |
| 11:47 to 11:57 | Logged runs, 0.11.2 uncommitted on `1e614fb` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast -Record`; clang 23.1.5 `-O2`): reference **7.4686 DMIPS/MHz** (76.2 clocks per run), fast runtime **9.1333** (62.3 clocks per run) | output |
| 11:48 to 11:56 | Width study (scratch `patch_width.py`: fetch-group and allocation arrays sized by the width, up to 16; probes only). The 8-wide 0.11.2 retires 8 instructions in 24,893 of 31,158 clocks (fast) and 30,332 of 38,103 (reference). Region clocks, reference / fast: 8-wide 38,103 / 31,158; 12-wide 33,632 / 24,194; 16-wide 33,629 / 23,250; with a 256-entry ROB (288 physical registers) and 128-entry issue queue, 12-wide 29,689 / 24,194 and 16-wide 28,749 / 22,269 | output |
| 11:53 | User question: status of the agents. Memory agent (four designs handed over and integrated in 0.11.0 and 0.11.1; restarted at 11:47 on 0.11.2, prototyping four stores per write), Codex reviewer (two reviews, fixes integrated), paper study (fusion, in 0.11.2), site agent (site committed) | process |
| 11:58 | User direction: a researcher agent reviews Tenstorrent Ascalon, Intel Panther Lake and AMD Zen 5 for ideas to try; started | process |
| 11:58 | Commit `b943816`, architecture 0.11.2; tagged `cpu-v0.11.2`, local only | git |
| 11:58 to 12:05 | 0.12.0 in `rtl/` (scratch `patch_width.py`, `patch_win.py`, `patch_tb_width.py`): 16-wide default, ROB 256, 288 physical registers, IQ 128; `tb_core.sv` sets `RW` 16 and `tb_bench.sv` counts `$bits(rt_valid)` slots. `full_check.sh`: all three cores 204/204, 2-line caches and `check_bitmanip.py` pass. A first attempt left `assemble_wide.py` at width 8 (a failed string match after the window patch had already been applied); fixed before the check | output |
| 12:00 to 12:06 | Research agents (secondary sources; summaries in `build/cpu/ooo-debug/council/RESEARCH.md`): SiFive P870 (6-wide, TAGE overriding a zero-bubble predictor, overflow queue before per-port schedulers, 48-entry load and store queues; vendor 17-18 SPECint2006/GHz, no independent measurement found); Zen 5, Lion Cove/Cougar Cove, Skymont/Darkmont and Ascalon (8-wide rename and retire at most, 6-8 ALUs, 2 stores per clock, same-line store coalescing in Zen 5, 0-cycle exact-match forwarding in Lion Cove, rename-stage immediate adds in Skymont, no disclosed value prediction); Arm X1, X4, X925 and C1-Ultra (decode 5 to 10, 8 ALUs with 3 branch units, operation cache removed in X4, measured X925 traits, no value prediction; no published DMIPS/MHz). A further agent is checking the user's list of 14 cores (NVIDIA Olympus, Apple M4, Neoverse V2/V3/N2, Akeana, Oryon, Zen 6, XiangShan, LA664, Veyron) and its estimated DMIPS/MHz figures | research |
| 12:05 | Site updated by a Sonnet agent (`scripts/build_site.py`, `docs/`): works No. 28 (0.11.2) and No. 29 (0.12.0, 16 lanes), a sixth room, the chart's axis extended to fit 9.13; 29 artworks, 243 timeline rows, 64 runs; not committed yet | site |
| 12:07 to 12:12 | User direction (new goal): a council of engineers for frontend, middle, backend and memory, debating and collaborating, with the lead session as coordinator integrating their work, running Dhrystone, managing the project and keeping this log; goal 20 DMIPS/MHz (28.5 clocks per run). Charter, board, roster and research digest in `build/cpu/ooo-debug/council/`; three new engineer agents started, the memory agent became the memory engineer. Hand-offs are patch scripts against the canonical scratch sources; only the coordinator writes `rtl/`, this log and commits. Arithmetic in the charter: the reference binary runs about 550 instructions per Dhrystone run and the fast one about 446, so 20 DMIPS/MHz needs about 19 or 16 instructions per clock on these binaries | process |
| 12:05 to 12:15 | Logged reference run for 0.12.0, uncommitted on `b943816` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`): **9.8986 DMIPS/MHz** (57.5 clocks per run). The fast-runtime run that followed failed ("Dhrystone simulation failed") at about 12:24, while the council's engineers were running 38 simulators at once (load average 24 on 20 cores); a direct rerun to find the failing step started at 12:25 | output |
| 12:14 | User direction: at the end of every successful logged run, add the new CPU to the gallery and the log to the site; added to AGENTS.md | process |
| 12:15 | Research agent on the user's list of 14 cores: none of the list's estimated DMIPS/MHz figures could be traced to a source; the only published high-end RISC-V Dhrystone found is StarFive Dubhe-100, 10.0 DMIPS/MHz (vendor, "legal" build). Mechanisms with sources: XiangShan (move elimination with reference counts, B-extension fusion pairs, a 16-line merged store buffer, an SRT-16 divider), NVIDIA Olympus (value prediction and memory renaming named, no mechanism), Neoverse V3 (measured). Digest in `build/cpu/ooo-debug/council/RESEARCH.md` | research |
| 12:20 | Memory engineer (BOARD.md): on 0.12.0, slots lost at the end of a store group are 74,619 (fast) and 106,229 (reference), but four stores per write request (regression passed) moves clocks only 22,269 to 22,259 and 28,749 to 28,714: the slots become waits on unfinished instructions. Store bandwidth is not the limit; the change is not handed off. Real memory losses: the load at 0xa54 (read before a same-clock store address, then held by the load-wait table every run) and replays at 0x8cc | output |
| about 12:28 | Backend engineer (BOARD.md; its post was headed 12:40, ahead of the clock): ALU and full ports are often all busy, but 12 ALUs, all ports branch-capable, a 2-clock multiply and a 2-clock divide together save only 0.4% / 0.3% (28,639 / 22,205): execution bandwidth and the divide are not the limit; the critical path is a dependency chain (the byte loops' `addi` induction chains in `strcpy`/`strcmp` at one iteration per clock) | output |
| 12:18 to 12:22 | User direction: a Haiku agent added Open Graph, Twitter and canonical tags and a repository link to the site generator, a Pages link to README.md, and enabled GitHub Pages (`gh api -X POST repos/monstercameron/RISC-V-FPGA-CPU-Research/pages`, source `main` `/docs`; https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/). The site appears only once `main` is pushed. The preview image is an SVG, which some link previewers do not render | site |
| 12:26 | Machine budget added to the council charter: at most 3 simulations per engineer, and a pause while the coordinator's logged run is in progress | process |
| 12:25 to 12:32 | Direct rerun of the 0.12.0 fast-runtime benchmark (`run_bench.py --core ooo`, no log, `timeout 900`): passes, 12.7790 DMIPS/MHz, traces match at 0 and 7 wait cycles. The 12:24 failure was a step timeout under load, not a core fault | output |
| 12:32 to 12:38 | Logged fast-runtime run for 0.12.0 (`run_dhrystone.ps1 ... -Runtime fast -Record`), with the council paused: **12.7790 DMIPS/MHz** (44.5 clocks per run) | output |
| about 12:30 | Frontend engineer: on 0.12.0 the fetch queue is empty after rename in almost every clock (rename takes 9.65 / 10.1 per clock); groups end at the second taken transfer or the one call/return. Its hand-off 1 (4 taken transfers and 4 calls+returns per group, parameterised; tests `fetch_many_calls`, `fetch_deep_recursion`; regression 204/204 at both cache sizes): reference 28,749 to 27,735 (-3.5%), fast 22,269 to 20,661 (-7.2%); the limit then moves to the ROB (reference) and issue queue (fast) | output |
| about 12:34 | Middle engineer (prototype): rename-time folding, map entry = physical register + offset; `addi`/`mv`/`li`/`lui`/`auipc` and constant-base jumps finish at rename (shared registers reference-counted), about 36% of instructions; with frontend's patch: reference 25,091 (-12.7% vs 0.12.0), fast 19,197 (-13.8%); limit then ROB full (average 249 of 256). Coordinator: integrate both as 0.13.0; retire width above 16 approved as an experiment | output |
| about 12:36 | Memory engineer: store-address ports before load ports in a clock (fixes a same-clock store/load order at 0xa54): -0.2% / -0.1% on 0.12.0; up to four stores per write request plus that, on frontend's patch: reference 27,735 to 26,659 (-3.9%); runs on the folding stack queued. Load replays at 0x8cc are store-data waits (~4 per run) | output |
| 12:36 | Research agent on unconventional architectures (from memory of the papers; citations to verify): ROB compression, load coalescing, hardware loop replay, a trace cache of optimized traces, RENO extensions; its estimate: about 15-17 DMIPS/MHz on the byte-wise binary even with those, 20 more plausible on the word-wise one | research |
| 12:38 | Board timestamps from agents (and two of the coordinator's) ran ahead of the clock (13:25, 13:30, 13:35); this log's times come from `date` | process |
| 12:39 | User direction: every 15 minutes the Codex reviewer (GPT 6.2 Astra) reviews the project read-only and suggests feasible enhancements and bugs toward 20 DMIPS/MHz to the coordinator; added to AGENTS.md. Loop `build/cpu/ooo-debug/council/codex/periodic.ps1` (prompt `periodic_prompt.md`, reviews `review-<time>.md`, stop by creating `STOP`) started in the background | process |
| 12:41 | Caching research agent: the 2025-2026 cache papers the user listed are mostly verified (ICP, Berti, Prophet, IP-CaT, ICARUS, Bumper, TRRIP, Garibaldi, FURBYS, Victima; "R-Max" not found) but target L2/LLC and long memory latency; on our 1-clock memory and Dhrystone they can give about 0-2%. Plan: a realistic memory model and a wider benchmark set first | research |
| 12:42 | Commit `4ae598a`, architecture 0.12.0 with the site update (gallery works for 0.11.2 and 0.12.0, journal, Open Graph tags, README Pages link) and the AGENTS.md rules; tagged `cpu-v0.12.0`, local only. Council resumed | git |
| 12:43 to 12:46 | 0.13.0 candidate (scratch `w013`: canonical 0.12.0 + middle hand-off 1, folding, + frontend hand-off 1, 4 taken / 4 calls+returns; `test_cpu.py` gains `fetch_many_calls`, `fetch_deep_recursion`, `fold_shared_register`, `fold_byte_loop`, `fold_calls_constants`, `fold_branch_operands`, 74 programs). Probe: reference **25,091** clocks (11.34 DMIPS/MHz), fast **19,197** (14.82), same as the engineers'. `regress_cand.sh`: default caches 222/222 pass; 2-line caches fail on `fold_byte_loop` ("store write without its store retiring on the same clock", `tb_core.sv` line 102). Middle reports the same failure on committed 0.12.0, so released versions have the bug and the new test exposes it; blocking 0.13.0; assigned to the memory engineer | output |
| 12:44 | First periodic Codex review (`build/cpu/ooo-debug/council/codex/review-20261121-1239.md`, 319 s). Bugs: (1) the bus-candidate scan stops at `rb_viol` and `rb_fencei` but not at `rb_vpbad`, while retirement stops at `rb_vpbad`, so a store younger than a value-mispredicted load can be written and then discarded (assigned to memory, a likely cause of the `fold_byte_loop` failure); (2) a correct load can be marked as violating when an older store to its byte resolves after a younger store forwarded the right byte, setting a sticky untagged wait bit (memory, performance); (3) the middle engineer's probe counts 16 retirement lanes and a fixed IQ threshold, wrong for wider builds (middle). Suggestions: load lanes 4-5 and store-address 3 with the four-store path (the reference mix needs about 4.15 loads and 2.67 stores per clock at the goal; backend + memory); compare fetch/rename and retire widths separately (middle + frontend); a fourth branch-capable port (backend). All accepted for measurement | review |
| 12:48 to 12:53 | Memory hand-off 6 (fix): the store-write scan and retirement read one stop wire (`rb_ends = rb_fencei | rb_vpbad`); a load whose bytes came from a younger resolved store is no longer flushed by an older store's address. On the 0.13.0 candidate: 222/222 at both cache sizes, clocks unchanged (25,091 / 19,197). Root cause dates from 0.11.1 (value prediction added `rb_vpbad` to retirement only). New tests `vp_store_scan_12`, `vp_store_scan_16` (fail before the fix with 2-line caches), `mdp_forward_from_younger` | output |
| 12:55 | User stopped the first 0.13.0 full check and asked for 5-minute status updates; added to AGENTS.md. Full check restarted at 12:56 | process |
| 12:51 to 13:00 | Council measurements (board): frontend, wider fetch/rename (24) does not pay while the ROB fills; loop replay and a trace cache would gain about nothing; I-cache prefetch -0.05% / -0.2% (perfect I-cache bound -1.3% / -2.0%), dropped. Middle, on fold + fetch 4/4: ROB 512 alone no gain; two instructions per ROB entry 23,609 / 17,717; ROB 512 + retire 24 22,608 / 16,731; ROB 512 + retire 32 21,629 / 15,743. Backend, on memory's stack (fold + fetch 4/4 + 4 stores + store-first): 4 load ports 19,640 / 16,234; 5 load + 3 store-address 18,572 / 15,333; a fourth branch port about 5 clocks (not pursued); cascade, OFF_LAT 0 and divide 2 clocks under 0.1% | output |
| 12:55 to 13:03 | 0.13.0 candidate full check (`full_check.sh`): all three cores 222/222, 2-line caches and `check_bitmanip.py` pass; with the three new memory tests the out-of-order core passes 231/231 at both cache sizes (13:06, 13:10) | output |
| 13:04 | User direction: a research agent on latency hiding (report back to the coordinator). Summary in `build/cpu/ooo-debug/council/RESEARCH.md`: at idealized latencies, retire-block fixes are worth about 1-3%; the important honesty step is to model realistic latencies (mispredict 10-12 clocks with ~10 stages, 4-clock load-to-use, L2 10-15 clocks), which would lower the present figures; memory renaming, speculative wakeup with replay and better value prediction would recover part of it | research |
| 13:10 to 13:13 | Memory hand-off 4 added to 0.13.0: store-address ports before load ports in a clock, and up to four stores per write request (`EXTRA_WRITES` 2, ports `mem_xaddr`/`mem_xwdata`/`mem_xwstrb`/`mem_xerror`; SoC and `tb_core.sv` patched; tests for faults on stores 2, 3 and 4, same-beat stores, a store patching code ahead, four beats; 83 programs). Probe: reference **20,801** clocks (13.68 DMIPS/MHz), fast **16,235** (17.53), the memory engineer's figures. Recorded as 0.13.0 (MINOR: new parameter and ports); full check started 13:13 | output |
| 13:13 to 13:21 | Combined state (0.12.0 + memory fix + frontend fetch 4/4 + middle folding + memory four-store writes): `full_check.sh` all three cores 249/249 (83 programs), 2-line caches and `check_bitmanip.py` pass | output |
| 13:19 to 13:24 | User direction: no bundling; each change its own semver step, so the history shows the evolution (added to AGENTS.md); keep this log going. The combined change is split into 0.12.1 (fix), 0.12.2 (fetch 4/4), 0.12.3 (folding) and 0.13.0 (four-store writes; new ports, MINOR). Each step was rebuilt from the 0.12.0 sources by applying the hand-offs in that order (scratch `v1`-`v4`; step 4 is byte-identical to the combined state) and checked with its own test set and the 0.12.0 testbench (`build/cpu/ooo-debug/split/check.sh`): 0.12.1 213/213 at both cache sizes, probe 28,749 / 22,269; 0.12.2 219/219, 27,735 / 20,661; 0.12.3 231/231, 25,091 / 19,197; 0.13.0 as the combined state, 20,801 / 16,235 | output |
| about 13:27 | Backend hand-off 2 (4 load + 3 store-address ports; agreed with memory): on 0.13.0, 20,801 / 16,235 to 18,575 / 15,335 (-10.7% / -5.5%); 4/2 19,640 / 16,234; 3/3 20,752 / 15,314; 5/3 18,572 / 15,333; 6/4 18,550 / 15,310; regression 273/273 at both cache sizes (its test set); the divide no longer matters on that stack (divide 2 clocks: 18,562 / 15,315; a variable-latency divider: 18,570 / 15,325; not handed off). Precedent: Zen 5 (4 loads per clock), Lion Cove (3 store-address ports) | output |
| about 13:27 | Frontend stack (probe): 0.13.0 + middle ROB 512 / retire 32 + 5 load / 3 store-address ports + fetch/rename 24: reference **15,797** clocks (18.0 DMIPS/MHz in the probe), fast **11,002** (25.9); the same stack with fetch 16: 18,056 / 14,650; fetch 24 without the ports: 20,772 / 14,728. The three pieces pay only together. Probe numbers on an idealized 5-stage model (1-clock loads, ~3-clock mispredict recovery); not logged runs | output |
| 13:32 | Commits `f879961` (0.12.1), `074cc24` (0.12.2), `c866d19` (0.12.3), `c60e9fa` (0.13.0), tagged `cpu-v0.12.1` to `cpu-v0.13.0`, local only. Mistake: the script that wrote each step's `sim/cpu/test_cpu.py` rebuilt it from the previous commit instead of from 0.12.0, so the files committed at 0.12.2, 0.12.3 and 0.13.0 contain repeated copies of earlier test blocks (the same tests run again; 100 test programs at 0.13.0 instead of 83). Results are unaffected (each repeated test is identical); corrected by a test-only commit without a version bump (83 programs, 249/249 at both cache sizes at 13:35); released tags are not moved | git |
| 13:36 to 13:47 | Logged runs for 0.13.0 on `4d74a0b` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast -Record`; clang 23.1.5 `-O2`), council paused: see the run index (reference 13.6809 DMIPS/MHz, 41.6 clocks per run) | output |
| about 13:40 | Frontend engineer final: hand-off 2 (fetch/rename width separate from retire width, 64-entry fetch queue) applied after middle's wider retirement and backend's ports: with fetch 32 the stack gives reference **15,704** / fast **10,371** clocks (probe; 18.1 / 27.4 DMIPS/MHz), fetch 24 15,724 / 11,002, fetch 16 about 18,060 / 14,650; regression of that stack 249/249 at both cache sizes (its own 32-slot tb_core copy). Taken transfers 8 add under 0.3%. Hand-off 3 (64-entry return stack): no Dhrystone change, 231/231; for a later release | output |
| 13:47 | Commit `4601f4f`: 0.13.0 run records and site (gallery works for 0.12.1 to 0.13.0); logged fast runtime **17.5285 DMIPS/MHz** (32.5 clocks per run) | git |
| 13:48 to 13:52 | 0.13.1 (backend hand-off 2: `N_LD` 4, `N_ST` 3; tests `many_memory_ports`, `ports_load_fault_third`, `ports_load_fault_fourth`, `ports_store_fault_second`, `ports_mixed_fault_last_load`; the backend's divider test was left out with its divider). Probe: reference 20,801 to **18,575** clocks (15.32 DMIPS/MHz), fast 16,235 to **15,335** (18.56). Regression: out-of-order 264/264 at both cache sizes; multicycle and pipelined 264/264 | output |
| 13:52 | Commit `dcae4df`, 0.13.1; tagged `cpu-v0.13.1`, local only. Correction: the header comment of the generated `rtl/cpu/rv64_ooo.sv` still read "architecture 0.12.0" in 0.13.0 and 0.13.1 (the assembler's label was not updated after the split); fixed from 0.14.0 | git |
| 13:53 to 13:58 | 0.14.0 (middle hand-off 2, plain variant: ROB 512, 544 physical registers, retirement `RW` 32 with fetch/rename 16; `tb_core.sv` `RWT` 32; tests `retire_wide_trap`, `retire_wide_stores`, `retire_wide_store_fault`). The two-per-entry variant (2b) measured the same at half the entries and registers; kept on file. Probe: reference 18,575 to **18,059** clocks (15.76 DMIPS/MHz), fast 15,335 to **14,652** (19.43). Regression: out-of-order 273/273 at both cache sizes; multicycle and pipelined 273/273 | output |
| 13:58 | Commit `57ea114`, 0.14.0; tagged `cpu-v0.14.0`, local only | git |
| 13:59 to 14:03 | 0.14.1 (frontend hand-off 2: fetch/rename width `FW` 32, separate from `RW`; 64-entry fetch queue). Probe: reference 18,059 to **15,704** clocks (18.12 DMIPS/MHz), fast 14,652 to **10,371** (27.44). Regression 273/273 at both cache sizes (no test change; other cores unaffected). The fast-runtime binary passes 20 DMIPS/MHz in this simulation; the reference binary needs about 9% fewer clocks (14,230). Probe figures on the idealized 5-stage model; logged runs follow | output |
| 14:03 | Commit `def6fd9`, 0.14.1; tagged `cpu-v0.14.1`, local only. Logged runs for 0.14.1 started 14:03 (council paused) | git |
| 14:05 | Coordinator decisions on the periodic Codex reviews of 12:54, 13:09, 13:24, 13:39 and 13:54 (`build/cpu/ooo-debug/council/codex/DECISIONS.md`). Accepted harness bugs (coordinator): the benchmark checks its run count against its own mailbox value; the profiler decoder mislabels `sh2add` and `divw` and its out-of-order memory-wait estimate is meaningless; `full_check.sh` lacks `pipefail`; a gate checks canonical rather than simulated core hashes; probes discard MAILBOX results; the "half the entries and registers" wording for the two-per-entry variant overstated its saving (only logical entries and allocatable registers halve). Accepted for memory: an `EXTRA_WRITES` range check, a lane-use cover for the four-store fault tests, the return-stack pointer on a head-load replay, a possible false dependence from value-predicted loads, and beat reuse (16,500 of 59,003 reference loads revisit a recently read beat). For middle: more rename-time constant folding (~5,000 more operations), rename-time resolution of ready equality branches, IQ/ROB limits. For backend: port limits at fetch 32, load-then-branch resolution, and with frontend a realistic-latency mode. Rejected: a small-quotient divide path (one operand pair in Dhrystone; the divide no longer limits) | review |
| 14:03 to 14:19 | Logged runs for 0.14.1 on `def6fd9` (`run_dhrystone.ps1 -Isa rv64im_zba_zbb_zbs_zifencei -Core ooo -Record`, then `-Runtime fast -Record`; clang 23.1.5 `-O2`), council paused: reference **18.1212 DMIPS/MHz** (31.4 clocks per run), fast runtime **27.4396** (20.7). The word-wise (fast runtime) binary passes 20 DMIPS/MHz in this simulation; the byte-wise reference binary needs 28.5 clocks per run (14,230 region clocks, -9.4%). Both figures come from an idealized 5-stage model (1-clock loads, ~3-clock mispredict recovery) and are not hardware results | output |
| 14:19 | Site: gallery works for 0.13.1, 0.14.0, 0.14.1 and a seventh room; regenerated (36 artworks, 70 runs) | site |
| 14:20 to 14:28 | Harness fixes from the Codex reviews (coordinator; tooling, no version change): `run_bench.py` now requires the reported run count to equal the build's `NUMBER_OF_RUNS` (500) instead of only matching its own mailbox value; `bench_profile.py` decodes the M and B extensions (it labelled `divw` as `?` and `sh1add`/`sh2add` as ALU base operations); `build/cpu/ooo-debug/full_check.sh` uses `pipefail` and fails loudly unless every step prints PASS. Validation: an unlogged fast-runtime run (`run_bench.py --core ooo`) passes with the new check, 27.4396 DMIPS/MHz as logged | output |
| 14:26 | User direction: raise the goal to 30 DMIPS/MHz and keep going about 4 more hours; agents started for: the user's 80-item optimization table (research), SMT exploration (engineer), native Dhrystone on the user's laptop (comparison), US fab tape-out options and prices (research), an independent Fable performance review, and a GPT 6.2 Astra (Codex) performance study (`build/cpu/ooo-debug/council/codex/perf-review-1.md`). The active session goal hook still states 20; the working target is 30 (19.0 clocks per run on the reference binary) | process |
| 14:28 | Commit `e6c6dd6`: harness fixes (run count against `NUMBER_OF_RUNS`; profile decodes M and B) | git |
| 14:25 | Middle engineer (board): on 0.14.1 the reference IQ is near full in 15,075 of 15,704 clocks, holding on average 58.6 loads (about 54 ready, waiting for a load port) and 49.3 branches; the 4 load ports run at 94% (3.76 loads per clock) | output |
| 14:30 | Research agent on the user's 80-item table (`build/cpu/ooo-debug/council/RESEARCH.md` is not yet updated with it): 30 DMIPS/MHz is 19.0 clocks per run on either binary (the coordinator had written about 14 for the fast runtime; corrected in the charter); a 5th load port measured no gain on the reference, so loads alone cannot be the binding limit; recommends a dataflow limit study, load combining, store-group micro-ops, rename-time reuse of known memory values; Mini-MDP (J. Systems Architecture, Aug 2026) and MORIA (MICRO 2026) exist but matter little here | research |
| 14:31 | Fab research agent (summary for the user; US options): ChipFoundry chipIgnite on SkyWater SKY130 (successor to Efabless, which shut down in 2025) quoted at $14,950 per tape-out with up to 15 mm2 and 100 packaged parts, about 6 months; a Cadence SKY130 aggregation at $10,000 for 40 bare die; MOSIS 2.0 (defense industrial base) lists TSMC, Samsung, SkyWater, GF and Intel 18A shuttles without public prices; GF and TSMC Arizona need NDAs and give no small-customer price; mask sets estimated about $1M at 28 nm. Our 32-wide behavioural core is not synthesizable as a practical chip; the realistic first tape-out is the small pipelined core on SKY130 after a Yosys/OpenROAD run | research |
| 14:36 | Native Dhrystone on the user's laptop (agent; `build/native-dhrystone/`): NVIDIA RTX Spark N1X (Arm Cortex-X925 performance cores, 4,004 MHz maximum), clang 23.1.5 aarch64-pc-windows-msvc `-O2 -std=gnu89 -fno-inline`, 400 million runs, 5 runs pinned to one performance core: 50.61 million Dhrystones/s with `-fno-builtin` (28,806 DMIPS, **7.19 DMIPS/MHz** at 4,004 MHz, 8.88 if the core ran at the 81% performance counter's ~3,243 MHz) and 58.67 million with builtins (8.34 / 10.3). Wall-clock timer, turbo uncertainty; a different ISA, compiler target and library, so indicative only | output |
| 14:42 | GPT 6.2 Astra performance study (`build/cpu/ooo-debug/council/codex/perf-review-1.md`, trace analysis on `def6fd9`): reference floors per run: width 32 17.19, fetch limits 24.50, **3 branch-capable ports 30.33** (87 branches + 3 jumps + 1 divide per iteration; equals the measured warm iteration), 4 load ports 29.50, 3 store-address ports 25.33, retirement with 4 stores 24.00; fast: width 13.94, fetch 17.00, branch ports 17.33, loads 18.25, store addresses 18.33, store retirement 18.00. Ranked: 5 branch-capable ports, beat-reuse loads (68/118 reference loads per iteration), constant-base store addresses at rename (52/76), 8 taken transfers per group, more stores per retirement. Assigned on the board | review |
| 14:32 to 14:49 | 0.14.2 (memory hand-off 7, fixes): `EXTRA_WRITES` range check, return-stack pointer from the violating load's own entry, `rb_ldv` instead of `prf_written` for violation marking; `tb_core.sv` lane counters and a lane-use cover in `test_cpu.py`. Dhrystone unchanged (15,704 / 10,371). `full_check.sh`: out-of-order, multicycle, pipelined 273/273 and `check_bitmanip.py` pass; the 2-line suite exceeded its 5-minute limit under load (273 runs, load average 11) and passed on rerun with a 10-minute ceiling (14:43 to 14:49); suite ceilings raised to 10 minutes because each simulation keeps its own 60-second hang limit | output |
| 14:44 | SMT engineer (design study, no RTL change; `build/cpu/ooo-debug/council/smt/NOTES.md`): what SMT2 needs (per-thread fetch, rename maps, return stacks, partitioned ROB, thread-tagged IQ/LSQ, cross-thread load ordering, per-hart traps and trace; minimal contract: `THREADS` parameter, start PC per hart, `rt_hart`). Experiment 1 (0.14.1 utilisation): load ports 97% / 95%, branch-capable ports 97% / 95%, so two Dhrystone copies can gain at most about +3% reference, +5% to +13% fast. Experiment 2 (half machine per thread): generous ports +2.2% / +5.7%, strict split -32% / -27%. Conclusion: no SMT prototype for Dhrystone now; revisit with realistic latencies or after the port work | output |
| 14:50 | Commit `8f1c5fe`, 0.14.2; tagged `cpu-v0.14.2`, local only | git |
| 14:50 to 15:04 | 0.14.3 (middle hand-off 3: rename-stage constant ALU, one level per rename clock, and conditional branches decided at rename; tests `rename_const_alu`, `rename_branches`; 93 programs). Probe: reference 15,704 to **15,683** (18.15 DMIPS/MHz), fast 10,371 to **10,208** (27.88); per 500 runs 5,391 / 10,208 constant operations and 500 / 4,586 branches resolved at rename. `full_check.sh`: all cores 279/279 at both cache sizes, `check_bitmanip.py` pass | output |
| about 14:55 | Memory engineer: beat reuse (two recently read beats kept coherent by retiring stores; up to 4 reuse lanes take ready loads the 4 ports did not pick) on 0.14.2: 15,801 / 10,116 alone; 5 branch-capable ports alone 15,669 / 10,245; both together **14,123** / 10,112 (20.15 DMIPS/MHz on the reference in the probe). Memory renaming with verification measured worse (16,025 / 10,681): renamed loads become ALU work on the branch ports; parked | output |
| 15:00 | Independent Fable review (`build/cpu/ooo-debug/council/fable/`): both binaries are throughput-bound; loads (4 ports busy every warm clock), branch-capable ports and store-address ports saturate at nearly the same clocks per run, so each looked useless alone. Measured on copies: all 8 ALU ports branch-capable + same-beat load sharing (8 address units, 4 cache reads) + a 4th store-address port + 6 taken per group: 12,584 / 9,648 (22.6 / 29.5 DMIPS/MHz in simulation); then store commit binds (4 stores per clock). Honesty: with 2 stores per clock, 4-clock loads, no value prediction and no fusion, 0.14.1 would score about 13.2 / 18.1 DMIPS/MHz (21,546 / 15,755 clocks), 27% / 34% below the logged figures; the 4-stores-per-clock assumption dominates. Warm-up costs about 7% (fast) of the 500-run region. Its estimate: the reference tops out near 26-28 in this model | review |
| 15:05 | Commit `d920c0d`, 0.14.3; tagged `cpu-v0.14.3`, local only | git |
| 15:05 to 15:10 | 0.14.4 (frontend hand-off 3: 64-entry return stack, parameterised pointer width; robustness, no Dhrystone change): probe 15,683 / 10,208 (same as 0.14.3); regression 279/279 at both cache sizes | output |
| about 15:04 | Frontend engineer: hand-off 4, a realistic-latency knob `FE_DEPTH` (each fetch-queue entry may be renamed only `FE_DEPTH` clocks after fetch; 0 = today, identical). Measured mispredict refill 2.7 / 6.6 / 10.3 clocks at depth 0 / 4 / 8; Dhrystone at depth 8: 16,013 / 10,859 (17.8 / 26.2 DMIPS/MHz, +2.0% / +4.7% clocks). Proposed realistic preset: `FE_DEPTH` 8 with backend's load-to-use 4. Also: a perfectly prefilled I-cache would give -1.6% / -3.0% (the cold first pass; recovering it needs a wider instruction fill, a bus contract change); `TAKEN_MAX` 8 with 5 branch ports measured 15,655 / 10,223, to be re-measured once the load floor is lifted | output |
| 15:10 | Commit `22f9ecb`, 0.14.4; tagged `cpu-v0.14.4`, local only | git |
| 15:11 to 15:27 | 0.14.5 (frontend hand-off 4, `FE_DEPTH` knob, default 0). Integration bug found and fixed by the coordinator: the hand-off omits the rename-time check entirely when applied with depth 0, so later setting the parameter to 8 changed nothing (first depth-8 probe identical to depth 0, 15,683 / 10,208); the check is now always present and gated by `FE_DEPTH > 0`. Probe: depth 0 = 15,683 / 10,208 (unchanged); depth 8 with a 512-entry fetch queue = **15,985 / 10,688** (17.81 / 26.64 DMIPS/MHz). Regression (depth 0): 279/279 at both cache sizes | output |
| 15:22 | User direction: agents to set up the GitHub Pages site and update its CPUs and logs. Site agent: works for 0.14.2-0.14.4, chart axis to 32, regenerated (39 artworks, 307 timeline rows, 70 runs); Pages API: built, source `main` `/docs`, latest build for `5604d56` (the remote `main` was pushed to `5604d56` outside this session) | site |
| about 15:25 | Council stack measurements (probe, on 0.14.4): backend hand-off 3 (4 branch-capable ports, full ports prefer branch-class operations) + memory reuse lanes (4 lanes, 2 entries): 14,112 / 10,185; + middle store addresses at rename: 14,004 / **9,590** (fast 29.7 DMIPS/MHz in the probe); + memory renaming (middle rename side, memory verification): **12,762** / 9,589 (reference 22.3). Memory hand-off 8 (reuse lanes, 4 lanes / 4 entries) with a 5-branch-port stand-in: 13,311 / 10,138. Integration order: backend hand-off 3, memory hand-off 8, middle hand-off 7, then memory renaming | output |
| 15:27 | Commit `44fd723`, 0.14.5 with the site update; tagged `cpu-v0.14.5`, local only. Local `main` is 5 commits ahead of `origin/main` (`5604d56`); not pushed | git |
| 15:27 to 15:42 | 0.14.6 (backend hand-off 3: `N_BR` 4, full ports select branch/jump/system/M first, `MQ_N = N_BR * MUL_LAT` with a `$fatal` on overflow; test `branch_ports_many`; 94 programs). The backend found that the 8-entry multiply queue silently drops a multiply with 5 branch-capable ports (hang in `mul_then_store_pad0`); unreachable at 3-4 ports. Probe: reference 15,683 to **15,658**, fast 10,208 to **10,202**. `full_check.sh`: all cores 282/282 at both cache sizes, `check_bitmanip.py` pass | output |
| 15:28 to 15:31 | Pre-built next steps (scratch `w0147`, `w0148`; probes): 0.14.6 + memory reuse lanes (4 lanes, 4 beats) = **13,306** / 10,156 (21.39 DMIPS/MHz reference); + middle store addresses at rename = 13,505 / **9,590** (fast 29.68, reference 1.5% worse than without it); returned to middle | output |
| 15:42 | Commit `f35b038`, 0.14.6; tagged `cpu-v0.14.6`, local only | git |
| 15:42 to 15:45 | 0.14.7 candidate (memory hand-off 8, reuse lanes 4/4) built and its full check started, then held: periodic Codex reviews (14:54, 15:09, 15:24) found that a reuse lane can read the L1 after its buffered beat was evicted (more than 4 L1 reads per clock counted free, so the 13,306 probe may be optimistic), that the buffer is not cleared on reset, and that the lane tests pass with lanes disabled. Returned to memory (hand-off 8b). Canonical and `rtl/` reset to 0.14.6. While stopping the check, the coordinator's `pkill -f "test_cpu.py --core"` also killed any engineer regression running at 15:43 (engineers told to rerun) | process |
| 15:45 | Coordinator decisions on reviews 14:09-15:24 (`build/cpu/ooo-debug/council/codex/DECISIONS.md`): released-version bugs assigned as their own PATCH steps: 0.14.3 constant ALU folds more than one level per rename group (middle), 0.14.5 `FE_DEPTH` counter wrap (frontend), over-broad self-modifying-code flush at fetch 32 (frontend); memory-renaming correctness issues before any hand-off (memory, middle). Harness: `run_bench.py` now copies the RTL, testbenches and `cpu/VERSION` to `source-snapshot/` at the start of a run and compiles, times and hashes that copy, so a logged run cannot mix two revisions (validation run started) | review |
| 15:45 to 15:48 | User stopped the work and asked to wait; the memory and frontend engineer agents were stopped by the user. The runner snapshot validation (an unlogged fast-runtime run of 0.14.6 via `run_bench.py --core ooo`) passed: 27.8941 DMIPS/MHz (simulation), sources compiled from `build/cpu/bench/dhrystone-rv64imb-fastrt-ooo/source-snapshot/` | output |
| 15:49 | User direction: push. `git push origin main` (`5604d56..f35b038`, six commits through 0.14.6) and `git push origin --tags` (all `cpu-v*` tags); Pages rebuilds from `main` | git |
| 15:50 | User direction (new goal): make 7-Zip the new benchmark program: get its source, compile it, and research other CPUs' scores. Source: official repository `https://github.com/ip7z/7zip` (shallow clone into the ignored `build/third-party/7zip/`): 7-Zip 26.06, commit `d3296e39e1f1f92c7b41c0c3848e65640428d42d` (2026-11-07), 16 MB | tool |
| 15:51 to 15:54 | Native build of the 7-Zip console `7zz` (`CPP/7zip/Bundles/Alone2`) in WSL Ubuntu with clang 18.1.3 (aarch64): WSL has no `make` or `gcc` and no sudo, so the commands were taken from a dry run of `makefile.gcc` with Strawberry Perl's `mingw32-make -n -B CC=clang CXX=clang++ Z7_OS=Linux IS_ARM64=1` (with the Windows `SystemDrive`/`OS` variables cleared), `-Werror` removed, and run in WSL (`build/7zip-bench/run_build.sh`: 322 compiles in parallel, one link; no errors) | tool |
| 15:55 | Native 7-Zip benchmark on the user's laptop (`build/7zip-bench/native_bench.sh`, `7zz b -mmt1 -md22` and `-md25`, pinned to logical CPU 6, a Cortex-X925 core; 7-Zip measured the single-thread clock at 3.7-4.3 GHz): dictionary 22: compressing rating **8,003 MIPS**, decompressing **8,087 MIPS** (about 1.9 per GHz each at ~4.2 GHz); dictionaries 22-25 average 7,085 / 8,042. Output in `build/7zip-bench/native_bench.txt` | output |
| 15:53 | Research agent on 7-Zip scores: the rating is an estimated instruction rate normalised to a Core 2 core (not real instructions); single-thread per-GHz (derived from 7-cpu.com and sbc-bench, versions and dictionaries vary): RISC-V U74 0.79 / 0.90 (compress / decompress), JH7110 and C910 about 0.8 combined, SG2042 (C920) about 0.81, SpacemiT K1 about 0.61; Cortex-A55 0.72 / 0.98, A76 1.18 / 1.19, Skylake about 1.16, Zen 3 1.52 / 2.11, Apple M1 2.22 / 2.52, Oryon about 1.3 combined; no single-thread X925, Zen 4/5, Lion Cove or M2-M4 figures found (the laptop run above fills X925 at ~1.9). Target: about 1.2-1.5 per GHz for A76/Zen 3 class, ~1.9 for X925, 2.2-2.5 for M1 | research |
| 15:57 | An agent started on the bare-metal RV64 port: the LZMA benchmark kernel of 7-Zip (public-domain LZMA SDK C files, vendored with provenance), scaled to fit the simulator, as a second benchmark option in `build_bench.py`/`run_bench.py`, with 7-Zip's own rating formulas per MHz, a native build of the same kernel for calibration, and runs on all three cores | process |
| 16:55 | Goal changed by the user: optimization target is now a 10,000 MIPS single-thread 7-Zip rating. Stated at 4 GHz = 2.5 MIPS/MHz on `7z b -md22` (1.3x the X925 measured at 15:55); on the scaled kernel, using the X925's kernel/`7z b` ratio (4.37x compression, 1.34x decompression), about 10.9 / 3.35 MIPS/MHz. Written to `cpu/7zip-benchmark-targets.md`, the council charter, the Codex periodic prompt and AGENTS.md. Measured so far (0.14.6 RTL, simulation, scaled kernel): multicycle 1.61 / 1.69, pipelined 0.96 / 0.89; out-of-order sampled run in flight. A 5-minute status job was scheduled because updates had lapsed. |
| 17:02 | At the user's request, an agent started a Verilator feasibility study: obtain Verilator from official sources if it isn't installed, build the out-of-order, multicycle and pipelined cores with the bench testbench in `build/verilator/`, check region clocks against Icarus (Dhrystone 10,202 / 15,658 at 0.14.6) and measure the speedup. Reason: under Icarus the out-of-order core can't finish the 3.5M-instruction LZMA kernel in a 300 s run. |
| 17:08 | Interim out-of-order LZMA pieces (0.14.6, Icarus, 150k-instruction pieces after 20k warm-up, clocks per piece): compress 0: 28,422; 4: 55,861; 8: 56,797; 12: 54,719; 19: 60,840 (5 of 21, about 3.45 MIPS/MHz extrapolated, IPC about 2.9; piece 0 is an outlier); decompress 21: 49,366 and 23: 58,220 (IPC 2.59, about 2.65 MIPS/MHz). The sampling method matched the pipelined core's contiguous run within 0.08%. At the user's request a research agent started on what bounds compress IPC at about 2.6 (cache misses, load chains, mispredictions, memory parallelism, IQ/ROB, forwarding), reporting to the coordinator in `build/cpu/ooo-debug/council/lzma-research/`. |
| 16:00 to 16:50 | Port agent: LZMA kernel bring-up runs (uncommitted; clang 23.1.5 for Windows `-O2` rv64imb, Icarus 12.0, Python 3.12.3, WSL). `python -B sim/cpu/bench/build_bench.py --benchmark lzma --out-dir build/cpu/bench/lzma-d12-rv64imb-<core>`, then `python3 -B sim/cpu/bench/run_bench.py --benchmark lzma --core multicycle\|pipe --lzma-mode full`. Multicycle (whole program, trace-checked, liblzma decode matches): compress kernel 2,255,190 clocks, 3,065,962 instructions, IPC 1.360, 1.605 MIPS/MHz; decompress 259,246 clocks, 429,119 instructions, IPC 1.655, 1.691. Pipelined: compress 3,763,359 clocks (IPC 0.815, 0.962), decompress 491,743 (0.873, 0.892); 442 s wall. Failure: the first pipelined full run loaded a checkpoint image that had 3 NUL bytes after a write through `/mnt/c`; the trace check caught it, and `bench_checkpoint.write_images` now reads each file back. Native X925, same kernel (`build/7zip-bench/native/build_native.sh 12`, `taskset -c 19 ./d12/lzma_native 30000`, clang 18.1.3 aarch64, median of 30,000 passes x 3, clock 4.21-4.33 GHz from a dependent-add chain): compress 101.7 us = 8.34 MIPS/MHz, decompress 39.7 us = 2.59. |
| 16:44 to 17:13 | Out-of-order LZMA, sampled (0.14.6 RTL, Icarus): the runner's 24-piece sampled run was stopped at 633 s (exit 143) because it reports only at the end; a scratch driver `build/7zip-bench/ooo_pieces.py` timed the same checkpoint pieces (150k instructions after 20k warm-up, up to 3 at once) and wrote each as it finished, stopping new pieces at 17:12. Compress 13 of 21 pieces (1.87M of 3.07M instructions, 662,620 clocks; IPC per piece 2.1-5.7, the literal-heavy start about 5.5) scaled to about 1,089,000 clocks, about 3.32 MIPS/MHz (3.30-3.39 interpolating the missing pieces); decompress all 3 pieces, 171,624 clocks, IPC 2.50, 2.555 MIPS/MHz. Supersedes the interim 17:08 estimate (decompress 2.65 from 2 pieces). Sampling check: the pipelined core with the same pieces matched its whole run within 0.08% (compress 3,766,251 vs 3,763,359; decompress 491,986 vs 491,743); multicycle with 1.2M pieces +0.04% / identical. No out-of-order piece was trace-checked. Simulation speed: about 800 instructions/s on the out-of-order model; decompress pieces took 266-297 s, near the 300 s limit. Dhrystone confirmation on the out-of-order core (`run_dhrystone.ps1 -Runtime fast -Core ooo -NoDevlog`): 10,202 region clocks, 223,030 instructions, 27.89 DMIPS/MHz, unchanged. Against the 10,000 MIPS goal (10.9 / 3.35 estimated on this kernel): compress about 30%, decompress about 76%. |
| 17:02 to 17:18 | Verilator study (agent, uncommitted, nothing under rtl/ or sim/ edited). Verilator was not installed; official Ubuntu noble arm64 packages fetched with `apt-get download` (no sudo; verilator 5.020-1 = upstream v5.020, .deb sha256 matches the apt index; also make 4.3, flex, bison, m4, libfl), unpacked with `dpkg-deb -x` into `build/third-party/verilator/root/`; `build/verilator/env.sh` sets the paths; with clang 18.1.3 make needs `CFG_CXXFLAGS_STD=-std=gnu++20 CFG_CXXFLAGS_COROUTINES=`. Build: `bash build/verilator/build.sh ooo-bench rtl/cpu/rv64_ooo.sv tb_bench build/verilator/tb_bench_vl.sv -DWIDE_TRACE -GRAM_WORDS=8192`. All three cores build with the SoC, the bench testbench and tb_core. One rejected construct: `mailbox` is a SystemVerilog keyword, used as a variable at `sim/cpu/bench/tb_bench.sv:20,32,37,38` (renamed in copies in `build/verilator/`); otherwise warnings (721 BLKSEQ in rv64_ooo.sv, about 37 width, 20 empty pins in rv64_bram_soc.sv:88-95, missing timescale). Equivalence with Icarus 12.0: identical output in every case: ooo Dhrystone region 10,202 / 15,658 and hprobe WSTAT, tb_core traces at stall 0 and 7 and +profile byte-identical, multicycle and pipelined Dhrystone, multicycle and pipelined full LZMA regions 2,514,708 / 4,255,380, two ooo LZMA windows. Wall time Icarus to Verilator: ooo Dhrystone fast 86.0 s to 0.23 s, reference 129.5 s to 0.32 s, multicycle Dhrystone 17.0 to 0.09 s, pipelined 17.5 to 0.15 s, multicycle LZMA 237.8 to 0.93 s, pipelined 224.0 to 1.35 s, ooo LZMA window 100k-250k 301.8 to 0.96 s (110x to 400x). Caveat: Verilator starts registers at 0, Icarus at X, so reset-dependence bugs could hide; keep Icarus as the cross-check. |
| 17:20 | Out-of-order LZMA, whole program under Verilator 5.020 (0.14.6 RTL, from the run above, `build/verilator/run-ooo-lzma-d12-rv64imb-ooo.txt`, 14.7 s wall): compress kernel 1,067,884 clocks, 3,065,963 instructions, IPC 2.871, **3.389 MIPS/MHz**; decompress kernel 171,494 clocks, 429,119 instructions, IPC 2.502, **2.557 MIPS/MHz**; mailbox passes and equals the multicycle core's. The sampled Icarus estimate (1,089,000 compress clocks from 13 of 21 pieces) was 2.0% high; decompress sampled 171,624 vs 171,494 (0.08%). Against the goal (10.9 / 3.35): 31% / 76%. `cpu/7zip-benchmark-targets.md` updated to the whole-program figure. |
| 17:14 to 17:24 | Full regression after the LZMA testbench additions (`tb_bench.sv` laps and sample window, `tb_core.sv` `+max_retired`, all off by default), uncommitted tree on bfde6eb, Icarus 12.0: `wsl -e bash build/cpu/ooo-debug/full_check.sh`. ooo PASS (94 programs x 3 wait patterns = 282 runs), ooo with 2-line caches PASS (282), bitmanip PASS (12 groups), multicycle PASS (282), pipelined PASS (282); FULL CHECK PASSED in 9 min 54 s with up to 5 other simulations running. `python -B scripts/check_repo.py` PASS. Vendored LZMA files and the two 7-Zip licence texts checked byte-identical to the upstream git blobs at d3296e39 (`git hash-object --no-filters` against the clone). |

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
| 2026-11-21 01:33:28 -0500 | `251ac29` | yes | 0.9.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 721.6 | 0.7888 | 6.1 | [devlog-251ac29.md](devlog/devlog-251ac29.md) |
| 2026-11-21 01:36:43 -0500 | `251ac29` | yes | 0.9.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 611.6 | 0.9306 | 6.1 | [devlog-251ac29.md](devlog/devlog-251ac29.md) |
| 2026-11-21 01:51:24 -0500 | `f1f94c4` | yes | 0.9.1 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 603.7 | 0.9428 | 6.1 | [devlog-f1f94c4.md](devlog/devlog-f1f94c4.md) |
| 2026-11-21 01:54:41 -0500 | `f1f94c4` | yes | 0.9.1 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 532.7 | 1.0684 | 6.1 | [devlog-f1f94c4.md](devlog/devlog-f1f94c4.md) |
| 2026-11-21 02:12:10 -0500 | `7bf8f3d` | yes | 0.9.2 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 445.8 | 1.2768 | 6.1 | [devlog-7bf8f3d.md](devlog/devlog-7bf8f3d.md) |
| 2026-11-21 02:15:12 -0500 | `7bf8f3d` | yes | 0.9.2 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 394.7 | 1.4419 | 6.1 | [devlog-7bf8f3d.md](devlog/devlog-7bf8f3d.md) |
| 2026-11-21 02:54:13 -0500 | `11acc17` | yes | 0.9.3 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 363.7 | 1.5648 | 6.1 | [devlog-11acc17.md](devlog/devlog-11acc17.md) |
| 2026-11-21 07:18:38 -0500 | `11acc17` | yes | 0.9.3 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 363.7 | 1.5648 | 6.1 | [devlog-11acc17.md](devlog/devlog-11acc17.md) |
| 2026-11-21 07:21:14 -0500 | `11acc17` | yes | 0.9.3 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 360.7 | 1.5777 | 6.1 | [devlog-11acc17.md](devlog/devlog-11acc17.md) |
| 2026-11-21 07:33:22 -0500 | `8f207a0` | yes | 0.9.4 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 360.7 | 1.5778 | 6.1 | [devlog-8f207a0.md](devlog/devlog-8f207a0.md) |
| 2026-11-21 07:36:09 -0500 | `8f207a0` | yes | 0.9.4 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 351.8 | 1.6180 | 6.1 | [devlog-8f207a0.md](devlog/devlog-8f207a0.md) |
| 2026-11-21 08:51:11 -0500 | `af0a3a1` | yes | 0.10.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 131.8 | 4.3169 | 6.1 | [devlog-af0a3a1.md](devlog/devlog-af0a3a1.md) |
| 2026-11-21 09:49:20 -0500 | `af0a3a1` | yes | 0.10.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 131.9 | 4.3161 | 6.1 | [devlog-af0a3a1.md](devlog/devlog-af0a3a1.md) |
| 2026-11-21 09:54:57 -0500 | `af0a3a1` | yes | 0.10.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 147.9 | 3.8484 | 6.1 | [devlog-af0a3a1.md](devlog/devlog-af0a3a1.md) |
| 2026-11-21 10:10:26 -0500 | `4ee3a9a` | yes | 0.10.1 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 121.9 | 4.6702 | 6.1 | [devlog-4ee3a9a.md](devlog/devlog-4ee3a9a.md) |
| 2026-11-21 10:15:57 -0500 | `4ee3a9a` | yes | 0.10.1 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 131.9 | 4.3154 | 6.1 | [devlog-4ee3a9a.md](devlog/devlog-4ee3a9a.md) |
| 2026-11-21 10:55:26 -0500 | `322739e` | yes | 0.11.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 92.0 | 6.1851 | 6.1 | [devlog-322739e.md](devlog/devlog-322739e.md) |
| 2026-11-21 11:00:22 -0500 | `322739e` | yes | 0.11.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 93.1 | 6.1162 | 6.1 | [devlog-322739e.md](devlog/devlog-322739e.md) |
| 2026-11-21 11:14:47 -0500 | `8721ca2` | yes | 0.11.1 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 92.0 | 6.1878 | 6.1 | [devlog-8721ca2.md](devlog/devlog-8721ca2.md) |
| 2026-11-21 11:32:21 -0500 | `8721ca2` | yes | 0.11.1 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 89.1 | 6.3878 | 6.1 | [devlog-8721ca2.md](devlog/devlog-8721ca2.md) |
| 2026-11-21 11:36:23 -0500 | `8721ca2` | yes | 0.11.1 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 75.2 | 7.5667 | 6.1 | [devlog-8721ca2.md](devlog/devlog-8721ca2.md) |
| 2026-11-21 11:53:20 -0500 | `1e614fb` | yes | 0.11.2 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 76.2 | 7.4686 | 6.1 | [devlog-1e614fb.md](devlog/devlog-1e614fb.md) |
| 2026-11-21 11:57:29 -0500 | `1e614fb` | yes | 0.11.2 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 62.3 | 9.1333 | 6.1 | [devlog-1e614fb.md](devlog/devlog-1e614fb.md) |
| 2026-11-21 12:14:56 -0500 | `b943816` | yes | 0.12.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 57.5 | 9.8986 | 6.1 | [devlog-b943816.md](devlog/devlog-b943816.md) |
| 2026-11-21 12:38:36 -0500 | `b943816` | yes | 0.12.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 44.5 | 12.7790 | 6.1 | [devlog-b943816.md](devlog/devlog-b943816.md) |
| 2026-11-21 13:42:39 -0500 | `4d74a0b` | yes | 0.13.0 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 41.6 | 13.6809 | 6.1 | [devlog-4d74a0b.md](devlog/devlog-4d74a0b.md) |
| 2026-11-21 13:47:30 -0500 | `4d74a0b` | yes | 0.13.0 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 32.5 | 17.5285 | 6.1 | [devlog-4d74a0b.md](devlog/devlog-4d74a0b.md) |
| 2026-11-21 14:12:48 -0500 | `def6fd9` | yes | 0.14.1 | clang version 23.1.5 `-O2` `rv64imb` out-of-order core | 31.4 | 18.1212 | 6.1 | [devlog-def6fd9.md](devlog/devlog-def6fd9.md) |
| 2026-11-21 14:19:23 -0500 | `def6fd9` | yes | 0.14.1 | clang version 23.1.5 `-O2` `rv64imb` fast runtime out-of-order core | 20.7 | 27.4396 | 6.1 | [devlog-def6fd9.md](devlog/devlog-def6fd9.md) |
