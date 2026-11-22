# FPGA CPU Research

**CPU core first.** Architecture version: [cpu/VERSION](cpu/VERSION) ([semantic versioning and history](cpu/architecture.md#9-versioning)). We are building an original 64-bit RISC-V processor for an FPGA, with RVA23U64 as the long-term ISA target. Three original implementations share one contract ([architecture section 1](cpu/architecture.md#1-target-and-first-implementation)): the multicycle core `rv64_core.sv` (the reference design), the four-stage pipelined core `rv64_pipe.sv` (since 0.8.0) and the out-of-order core `rv64_ooo.sv` (since 0.9.0), which is the one being optimized. All run `rv64im_zba_zbb_zbs_zifencei` with instruction and data caches, serialized FENCE.I and a terminal laboratory trap interface. The out-of-order core adds RV64F and RV64D as a build option, `RV64_OOO_FPU`, off by default (since 0.17.0). There are no A, C or V extensions, no privileged architecture and no MMU yet.

Start with the [interactive CPU infographic](cpu/core-explainer.html), the [CPU quick start](cpu/README.md), and the [architecture and staged RVA23 checklist](cpu/architecture.md).

Gallery and journal (generated drawings and simulated results): https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/

**Current evidence (simulation only).** The [architecture version history](cpu/architecture.md#history) records each release's regression; for 0.17.4 it gives `test_cpu.py --fpu` 681 of 681 runs passing at both cache sizes, with the FPU-off build bit-exact against 0.17.3 (393 of 393). The last logged Dhrystone run (0.15.1, out-of-order core, `rv64imb`) gives 18.17 DMIPS/MHz with the reference runtime and 27.98 with the labelled fast runtime; the timing probe in the history has stayed within 0.5% of it through 0.17.4 (15,706 and 10,127 clocks) ([Dhrystone page](cpu/dhrystone.md)). The current optimization goal is a 10,000 MIPS single-thread 7-Zip rating at 4 GHz ([7-Zip targets](cpu/7zip-benchmark-targets.md)). None of this is RVA23, a Linux-capable CPU, an ISA certification or a physical FPGA result. The compact [verification record](cpu/verification.json) is still the architecture 0.4.0 one.

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

The default suite downloads nothing and needs no FPGA or cross compiler. It runs `sim/cpu/test_cpu.py` on the multicycle core: generated differential programs under three memory wait patterns, checked against the sequential reference model, plus reset and synchronous-RAM checks. `--core pipe` or `--core ooo` selects another core, `--sim verilator` the faster simulator and `--fpu` the out-of-order FP option; `--help` lists the rest. Optional LLVM-compiled firmware is described in the CPU quick start. Generated traces and reports go under `build/cpu/`.

### Test and benchmark suites (one front end)

`sim/cpu/suite.py` runs every test and benchmark entry point as named suites, from Windows or WSL, from any worktree, with each invocation under the 5-minute limit. It wraps `test_cpu.py`, `bench/run_bench.py` and the other checkers without changing their command lines; `sim/cpu/suite_manifest.py` lists the suites and is where new ones go.

```sh
python -B sim/cpu/suite.py --list                                   # suites, presets, steps
python -B sim/cpu/suite.py release-patch --core-source cand.sv --dry-run    # exact commands
python -B sim/cpu/suite.py release-patch --core-source cand.sv     --expect sim/cpu/baselines/0.17.2-release-patch.json --devlog-row   # same counts and clocks as 0.17.2?
python -B sim/cpu/suite.py release-minor --jobs 3                   # plus the full Icarus run (sharded)
python -B sim/cpu/suite.py isa fpu --cache-sizes default,2,64 --only 'fpu-*'
```

Suites: `unit`, `isa`, `fpu`, `vector`, `bitmanip`, `bench-smoke`, `bench`, `icarus-full`, `soc`, `negative`, `repo`; presets `release-patch` (`isa` + `bench-smoke`, the coordinator's former `vcheck.sh`) and `release-minor` (adds `icarus-full`, the former `full_check.sh`). A step passes only with exit 0 and a positive pass count or result line; the summary table, `results.json` and exit code (0 pass, 1 fail, 2 usage, 3 nothing ran) report it. `--help` lists every option.

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
| [Dhrystone result](cpu/dhrystone.md) | Benchmark results from 0.260 DMIPS/MHz (0.1.0) to 18.17 (0.15.1, out-of-order), how they were checked and how to rerun them |
| Benchmark targets: [7-Zip](cpu/7zip-benchmark-targets.md) ([kernel](cpu/lzma-benchmark.md)), [ray tracing](cpu/raytracing-benchmark-targets.md), [JavaScript](cpu/js-benchmark-targets.md), [matrix kernels](cpu/mm-benchmark-targets.md), [ternary GEMV](cpu/ternary-benchmark-targets.md) | Reference measurements, goals (Apple M6 per clock since 2026-11-22) and our simulated results |
| [CPU tools index](sim/cpu/README.md) | Every test, benchmark and helper script under `sim/cpu/`, with its entry point |
| [CPU review rubric](cpu/review-rubric.md) | Gates, scores and evidence needed before calling the CPU good or performant |
| [To do](TODO.md) | CPU work list and the RV64GC milestone (last revised 2026-11-20; DEVLOG.md has the current work) |
| [Development log](DEVLOG.md) | Dated record of sessions, commits and findings |
| CPU RTL: [multicycle](rtl/cpu/rv64_core.sv), [pipelined](rtl/cpu/rv64_pipe.sv), [out-of-order](rtl/cpu/rv64_ooo.sv) / [RAM wrapper and SoC memory model](rtl/cpu/rv64_bram_soc.sv) | Original SystemVerilog implementation |
| [LLM operations to RVA23](llm-rva23-mapping.md) / [assembly examples](isa/README.md) | Future workload mapping and optional BF16 instruction examples |
| [Earlier accelerator plan](plan.md) / [memory plan](memory-plan.md) | Preserved LLM architecture and bandwidth research |
| [Accelerator contract](implementation-contract.md), [ABI](abi-v1.md), [adapter](adapter-v1.md) | Normative for that accelerator design, not the current CPU bus |
| [FPGA analysis](fpga-resource-and-board-analysis.md) | Dated board research and conditional hardware choices |
| [Gap audit](plan-gap-audit.md) / [prior review](refinement-review.md) | Historical accelerator review; its score does not apply to this new CPU |
| [Research](research.md) | Original tool/ISA/FPGA investigations |

## Repository layout

```text
cpu/                              Architecture contract, benchmark pages and targets, infographic, result records
rtl/cpu/                          Original RV64 cores (multicycle, pipelined, out-of-order) and the RAM/SoC wrapper
sim/cpu/                          Differential tests, golden models, suite.py front end, benchmarks (bench/)
isa/                              Future RVA23 floating/vector assembly examples
scripts/                          Repository checks (check_repo.py) and the site generator (build_site.py)
docs/                             Generated GitHub Pages gallery and journal (do not edit by hand)
devlog/                           Per-commit run records linked from DEVLOG.md
sim/starter/                      Historical third-party PicoRV32 smoke simulation
fpga/                             Future exact-board constraints and build scripts
reference-sources/                Frozen LLM sources and metadata
notes/, references/               Qwen compute notes; the RVA23 profile PDF
llm-accelerator/planning-evidence/ Historical accelerator analysis snapshots
licenses/                         Upstream licenses and provenance
.github/                          CI, issue forms and pull-request template
```

The historical PicoRV32 starter still runs with `bash sim/starter/run.sh`; it is separate from our custom RV64 implementation. The previous complete Qwen3.8-27B text/vision accelerator remains research and a possible future workload. No full-model run is claimed by the CPU tests.

## Development constraints

- Keep the multicycle reference core serial and observable; add contained traps/CSRs and an external architectural oracle before expanding its ISA.
- Track every mandatory RVA23 capability. Do not label a partial core RVA23 compliant or reuse the accelerator LUT estimates as CPU measurements.
- Measure exact-part synthesis, RAM inference and timing before board selection. FPGA synthesis/programming and supported host access remain pending.
- Preserve reviewed source/fixture identities. Existing LLM storage, RAM and native-run admission rules still apply to any resumed model work.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [CHANGELOG.md](CHANGELOG.md). CI is configured for repository/planning checks, the custom CPU suite and the historical smoke test; GitHub-hosted execution is separate from the recorded local results.

## License

Original work is available under the [MIT License](LICENSE). Bundled Transformers/Qwen material, PicoRV32, the RISC-V specification and the benchmark sources (Dhrystone, the 7-Zip LZMA SDK, LLVM compiler-rt, TinyBVH-derived code, smallpt, QuickJS-ng, Berkeley SoftFloat/TestFloat) retain upstream terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
