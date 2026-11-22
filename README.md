# FPGA CPU Research

**CPU core first.** Architecture version: [cpu/VERSION](cpu/VERSION) ([semantic versioning and history](cpu/architecture.md#9-versioning)). We are building an original 64-bit RISC-V processor for an FPGA, with RVA23U64 as the long-term ISA target. The implemented core is a small multicycle RV64IM core (`rv64im_zifencei` since architecture 0.4.0) with instruction and data caches, serialized FENCE.I and a terminal laboratory trap interface.

Start with the [interactive CPU infographic](cpu/core-explainer.html), the [CPU quick start](cpu/README.md), and the [architecture and staged RVA23 checklist](cpu/architecture.md).

Gallery and journal (generated drawings and simulated results): https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/

**Current evidence (architecture 0.4.0):** 111 differential program simulations passed, plus reset and synchronous-RAM checks, covering 66 `rv64im_zifencei` instructions. Compiled C produced the expected result, 36. Dhrystone runs at 1.024 DMIPS/MHz in simulation, 3.94x the first 0.1.0 core; see the [optimization history](cpu/dhrystone.md#optimization-history). This is an integer foundation, not yet RVA23, a Linux-capable CPU or a physical FPGA result. See the [verification record](cpu/verification.json).

Study the core with [seven selectable C programs](cpu/programs.md), from 1 + 1 to sorting and CRC32. The connected visualizer includes C/assembly/binary views, study questions, hardware checkpoints and verified outputs.

You can [view and edit program inputs](cpu/inputs.md), then compile and run them from the visualizer.

## Run the custom CPU

From the repository root on the existing Windows workstation:

```powershell
.\sim\cpu\run.ps1
```

Or in Ubuntu/WSL with Python 3.11+ and Icarus installed:

```sh
bash sim/cpu/run.sh
```

The default suite downloads nothing and needs no FPGA or cross compiler. It runs 108 differential simulations plus reset and synchronous-RAM checks. The expanded 111-run record also includes LLVM-compiled firmware; instructions are in the CPU quick start. Generated traces and reports go under `build/cpu/`.

### Test and benchmark suites (one front end)

`sim/cpu/suite.py` runs every test and benchmark entry point as named suites, from Windows or WSL, from any worktree, with each invocation under the 5-minute limit. It wraps `test_cpu.py`, `bench/run_bench.py` and the other checkers without changing their command lines; `sim/cpu/suite_manifest.py` lists the suites and is where new ones go.

```sh
python -B sim/cpu/suite.py --list                                   # suites, presets, steps
python -B sim/cpu/suite.py release-patch --core-source cand.sv --dry-run    # exact commands
python -B sim/cpu/suite.py release-patch --core-source cand.sv     --expect sim/cpu/baselines/0.17.2-release-patch.json --devlog-row   # same counts and clocks as 0.17.2?
python -B sim/cpu/suite.py release-minor --jobs 3                   # plus the full Icarus run (sharded)
python -B sim/cpu/suite.py isa fpu --cache-sizes default,2,64 --only 'fpu-*'
```

Suites: `unit`, `isa`, `fpu`, `vector`, `bitmanip`, `bench-smoke`, `bench`, `icarus-full`, `soc`, `negative`, `repo`; presets `release-patch` (the coordinator's `vcheck.sh`) and `release-minor` (plus `full_check.sh`). A step passes only with exit 0 and a positive pass count or result line; the summary table, `results.json` and exit code (0 pass, 1 fail, 2 usage, 3 nothing ran) report it. `--help` lists every option.

To build and run the Dhrystone benchmark with the installed LLVM, see [the Dhrystone page](cpu/dhrystone.md):

```powershell
.\sim\cpu\bench\run_dhrystone.ps1
```

Repository and preserved accelerator-planning checks remain available:

```sh
python -B scripts/check_repo.py
```

## Read the project

| Document | Purpose |
|---|---|
| [Interactive core infographic](cpu/core-explainer.html) | Plain-language component tour and instruction walkthrough |
| [CPU quick start](cpu/README.md) | Files, commands, tested behavior and current limits |
| [CPU architecture](cpu/architecture.md) | Datapath, memory/trap contracts, RVA23 obligations and C0-C7 stages |
| [Dhrystone result](cpu/dhrystone.md) | Benchmark results from 0.260 to 1.024 DMIPS/MHz across architecture versions, how they were checked and how to rerun them |
| [CPU review rubric](cpu/review-rubric.md) | Gates, scores and evidence needed before calling the CPU good or performant |
| [To do](TODO.md) | Prioritized CPU work list, including the RV64GC milestone |
| [Development log](DEVLOG.md) | Dated record of sessions, commits and findings |
| [CPU RTL](rtl/cpu/rv64_core.sv) / [RAM wrapper](rtl/cpu/rv64_bram_soc.sv) | Original SystemVerilog implementation |
| [LLM operations to RVA23](llm-rva23-mapping.md) / [assembly examples](isa/README.md) | Future workload mapping and optional BF16 instruction examples |
| [Earlier accelerator plan](plan.md) / [memory plan](memory-plan.md) | Preserved LLM architecture and bandwidth research |
| [Accelerator contract](implementation-contract.md), [ABI](abi-v1.md), [adapter](adapter-v1.md) | Normative for that accelerator design, not the current CPU bus |
| [FPGA analysis](fpga-resource-and-board-analysis.md) | Dated board research and conditional hardware choices |
| [Gap audit](plan-gap-audit.md) / [prior review](refinement-review.md) | Historical accelerator review; its score does not apply to this new CPU |
| [Research](research.md) | Original tool/ISA/FPGA investigations |

## Repository layout

```text
cpu/                              Current design, infographic and compact verification record
rtl/cpu/                          Original RV64 execution core and synchronous-RAM wrapper
sim/cpu/                          Differential tests, reset/SoC benches and optional C firmware
isa/                              Future RVA23 floating/vector assembly examples
scripts/                          Dependency-free repository check runner
sim/starter/                      Historical third-party PicoRV32 smoke simulation
fpga/                             Future exact-board constraints and build scripts
reference-sources/                Frozen LLM sources and metadata
llm-accelerator/planning-evidence/ Historical accelerator analysis snapshots
licenses/                         Upstream licenses and provenance
.github/                          CI, issue forms and pull-request template
```

The historical PicoRV32 starter still runs with `bash sim/starter/run.sh`; it is separate from our custom RV64 implementation. The previous complete Qwen3.8-27B text/vision accelerator remains research and a possible future workload. No full-model run is claimed by the CPU tests.

## Development constraints

- Keep the first CPU serial and observable; add contained traps/CSRs and an external architectural oracle before expanding its ISA.
- Track every mandatory RVA23 capability. Do not label a partial core RVA23 compliant or reuse the accelerator LUT estimates as CPU measurements.
- Measure exact-part synthesis, RAM inference and timing before board selection. FPGA synthesis/programming and supported host access remain pending.
- Preserve reviewed source/fixture identities. Existing LLM storage, RAM and native-run admission rules still apply to any resumed model work.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [CHANGELOG.md](CHANGELOG.md). CI is configured for repository/planning checks, the custom CPU suite and the historical smoke test; GitHub-hosted execution is separate from the recorded local results.

## License

Original work is available under the [MIT License](LICENSE). Bundled Transformers/Qwen material, PicoRV32 and the RISC-V specification retain upstream terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
