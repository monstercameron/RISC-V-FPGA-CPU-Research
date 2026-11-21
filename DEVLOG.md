# Development log

A dated record of work sessions: what was done, the commits that came out of it, and what was learned. Newest day first.

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

- Commit the AGENTS.md devlog rule, the rubric scorer and this log update.
- Declare a performance target for the scope label (HG1).
- Tag `cpu-v0.1.0` on `0483d99` and push the tag.
- Decide whether to commit or discard the two regenerated visualizer records.
- Merge or close Dependabot PRs 1 and 2.
- Next benchmark: CoreMark. Next correctness step: an external model (Spike or Sail) in the regression.

---

## Dhrystone run log

Appended automatically by `sim/cpu/bench/run_bench.py --devlog`; the Windows launcher `run_dhrystone.ps1` does this on every run. Each entry records the run and a rubric scorecard computed from [cpu/rubric-evidence.json](cpu/rubric-evidence.json) plus the run's own measurements. A scorecard is an automated self-assessment, not an independent review, and grants only the claims rubric section 8 allows. Oldest run first.

### Run 2026-11-20 21:04:14 -0500

- **Commit:** `3110337`, uncommitted changes: yes
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM
- **RTL:** `rv64_core.sv` 831101d3f376, `rv64_bram_soc.sv` a38d2ca4a051
- **Result:** 2,188.2 clocks per run, 600.1 instructions per run, CPI 3.647, **0.2601 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** first run with these build settings

Rubric scorecard (revision 1; evidence assessed 2026-11-20 at `3110337`; automated self-assessment, not a review):

| Dimension | Points | Of | Score |
|---|---:|---:|---:|
| R1 Architectural correctness | 13.5 | 25 | 54% |
| R2 Traps, interrupts, privilege and reset | 6.2 | 10 | 62% |
| R3 Verification depth and independence | 3.8 | 15 | 25% |
| R4 Performance | 4.4 | 20 | 22% |
| R5 FPGA implementation quality | 0.0 | 12 | 0% |
| R6 Interfaces and integration | 4.3 | 8 | 54% |
| R7 Observability and debug | 1.7 | 4 | 42% |
| R8 Design quality and maintainability | 1.3 | 3 | 44% |
| R9 Reproducibility and claim hygiene | 1.9 | 3 | 62% |
| **Total** | **37.1** | **100** | **foundation** |

- **Gates met:** HG2, HG4, HG5, PG4. **Not met:** HG1, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG6; R1 54% < 60%; R3 25% < 50%.
- **"Good":** not granted: HG1; HG3; HG6; HG7; HG8; total 37.1 < 75; R1 54% < 80%; an R1 criterion under 3; R2 62% < 70%; R3 25% < 70%; R6 54% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 22% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 3.647 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 3; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 96 runs, 53 instruction names.)

<!-- dhrystone-run {"time":"2026-11-20 21:04:14 -0500","commit":"3110337","dirty":"yes","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"cycles_per_run":2188.206,"cpi":3.6466574897759885,"dmips_per_mhz":0.2600998094211762,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"831101d3f376ed35f96e4549eb0e9cf67fd59ef79bdf025b3ddbf432aebd75d1","rtl/cpu/rv64_bram_soc.sv":"a38d2ca4a05142f1982635fb9824a29b80abc94e31635415d3b341df0c06ae57"}} -->

### Run 2026-11-20 21:08:12 -0500

- **Architecture:** version 0.1.0
- **Commit:** `3110337`, uncommitted changes: yes
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM
- **RTL:** `rv64_core.sv` 831101d3f376, `rv64_bram_soc.sv` a38d2ca4a051
- **Result:** 2,188.2 clocks per run, 600.1 instructions per run, CPI 3.647, **0.2601 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.00% clocks per run against the previous run with the same build settings (2026-11-20 21:04:14 -0500, `3110337`, architecture unrecorded)

Rubric scorecard (revision 1; evidence assessed 2026-11-20 at `3110337`; automated self-assessment, not a review):

| Dimension | Points | Of | Score |
|---|---:|---:|---:|
| R1 Architectural correctness | 13.5 | 25 | 54% |
| R2 Traps, interrupts, privilege and reset | 6.2 | 10 | 62% |
| R3 Verification depth and independence | 3.8 | 15 | 25% |
| R4 Performance | 4.4 | 20 | 22% |
| R5 FPGA implementation quality | 0.0 | 12 | 0% |
| R6 Interfaces and integration | 4.3 | 8 | 54% |
| R7 Observability and debug | 1.7 | 4 | 42% |
| R8 Design quality and maintainability | 1.3 | 3 | 44% |
| R9 Reproducibility and claim hygiene | 1.9 | 3 | 62% |
| **Total** | **37.1** | **100** | **foundation** |

- **Gates met:** HG2, HG4, HG5, PG4. **Not met:** HG1, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG6; R1 54% < 60%; R3 25% < 50%.
- **"Good":** not granted: HG1; HG3; HG6; HG7; HG8; total 37.1 < 75; R1 54% < 80%; an R1 criterion under 3; R2 62% < 70%; R3 25% < 70%; R6 54% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 22% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 3.647 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 3; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 96 runs, 53 instruction names.)

<!-- dhrystone-run {"time":"2026-11-20 21:08:12 -0500","architecture_version":"0.1.0","commit":"3110337","dirty":"yes","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"cycles_per_run":2188.206,"cpi":3.6466574897759885,"dmips_per_mhz":0.2600998094211762,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"831101d3f376ed35f96e4549eb0e9cf67fd59ef79bdf025b3ddbf432aebd75d1","rtl/cpu/rv64_bram_soc.sv":"a38d2ca4a05142f1982635fb9824a29b80abc94e31635415d3b341df0c06ae57"}} -->
