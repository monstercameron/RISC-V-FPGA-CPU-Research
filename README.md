# FPGA CPU Research

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Evidence: simulation only](https://img.shields.io/badge/evidence-simulation%20only-lightgrey.svg)](cpu/architecture.md)

**Website:** [Atelier site](https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/) · [gallery](https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/gallery.html) · [journal](https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/journal.html)

An original 64-bit RISC-V processor for an FPGA, written in SystemVerilog and developed in simulation against a sequential golden model. Three implementations share one architecture contract, and the long-term target is the RVA23U64 profile, reached in stages. The earlier LLM-accelerator research for the same board is preserved under [llm-accelerator/](llm-accelerator/plan/README.md) as future work.

**Status (simulation only).** Architecture version: see [cpu/VERSION](cpu/VERSION), currently 0.18.0 ([semantic versioning and history](cpu/architecture.md#9-versioning)). Not RVA23, not a Linux-capable CPU, not an ISA certification and not a physical FPGA result: no board run, board timing or hardware measurement is claimed.

## What the cores implement

The contract is [cpu/architecture.md](cpu/architecture.md) ([section 1](cpu/architecture.md#1-target-and-first-implementation)).

| Core | RTL | Since |
|---|---|---|
| Multicycle (the reference design) | [rv64_core.sv](rtl/cpu/rv64_core.sv) | 0.1.0 |
| Four-stage pipelined | [rv64_pipe.sv](rtl/cpu/rv64_pipe.sv) | 0.8.0 |
| Out-of-order (the one being optimized) | [rv64_ooo.sv](rtl/cpu/rv64_ooo.sv) | 0.9.0 |

All three run `rv64im_zba_zbb_zbs_zifencei` with instruction and data caches, serialized FENCE.I and a terminal laboratory trap interface. The out-of-order core also has two build options, both off by default: RV64F and RV64D (`RV64_OOO_FPU`, since 0.17.0) and a **subset** of the V extension (`RV64_OOO_V`, since 0.18.0, contract [cpu/RVV-CONTRACT.md](cpu/RVV-CONTRACT.md); integer, mask-logical, permute, integer-reduction and indexed instructions still trap). There is no A or C extension, no privileged architecture and no MMU yet.

## Benchmarks and goals

- **Current goal:** a 10,000 MIPS single-thread 7-Zip rating at 4 GHz ([7-Zip targets](cpu/7zip-benchmark-targets.md)). Every benchmark goal is an Apple M6 per-clock reference set on 2026-11-22; each is an estimate bridged from laptop measurements, not an M6 measurement.
- **Last logged Dhrystone** (0.15.1, out-of-order core, `rv64imb`): 18.17 DMIPS/MHz with the reference runtime and 27.98 with the labelled fast runtime; the timing probe has stayed within 0.5% of it through 0.17.4 ([Dhrystone page](cpu/dhrystone.md)).
- **Regression:** each release records its counts in the [architecture history](cpu/architecture.md#history); for 0.18.0 that is `suite.py release-minor fpu vector` with 39 of 39 steps passing.
- Other targets: [ray tracing](cpu/raytracing-benchmark-targets.md), [JavaScript](cpu/js-benchmark-targets.md), [matrix kernels](cpu/mm-benchmark-targets.md), [ternary GEMV](cpu/ternary-benchmark-targets.md) and the [LZMA kernel](cpu/lzma-benchmark.md). Their sources are in [cpu/research/](cpu/research/README.md).

## Quick start

Python 3.11+ and Icarus Verilog are required (Verilator and an LLVM RISC-V toolchain are optional). From the repository root, in Ubuntu/WSL or on Windows:

```sh
python -B sim/cpu/suite.py --list                  # every suite, preset and step
python -B sim/cpu/suite.py unit --jobs 1           # the default multicycle regression
python -B sim/cpu/suite.py release-patch --dry-run # the commands a patch release runs
python -B scripts/check_repo.py                    # repository, link and licence checks
```

Nothing is downloaded and no FPGA is needed. `.\sim\cpu\run.ps1` or `bash sim/cpu/run.sh` run the default suite directly. The [CPU quick start](cpu/README.md) and the [tools index](sim/cpu/README.md) cover the rest; generated output goes under `build/`.

### Test and benchmark suites (one front end)

`sim/cpu/suite.py` runs every test and benchmark entry point as named suites, from Windows or WSL, from any worktree, with each invocation under the 5-minute limit. It wraps `test_cpu.py`, `bench/run_bench.py` and the other checkers without changing their command lines; `sim/cpu/suite_manifest.py` lists the suites and is where new ones go.

```sh
python -B sim/cpu/suite.py --list                                   # suites, presets, steps
python -B sim/cpu/suite.py release-patch --core-source cand.sv --dry-run    # exact commands
python -B sim/cpu/suite.py release-patch --core-source cand.sv     --expect sim/cpu/baselines/0.21.0-release-patch.json --devlog-row   # same counts and clocks as 0.21.0?
python -B sim/cpu/suite.py release-minor --jobs 3                   # plus the full Icarus run (sharded)
python -B sim/cpu/suite.py isa fpu --cache-sizes default,2,64 --only 'fpu-*'
```

Suites: `unit`, `isa`, `fpu`, `vector`, `bitmanip`, `bench-smoke`, `bench`, `icarus-full`, `soc`, `negative`, `repo`; presets `release-patch` (`isa` + `bench-smoke`, the coordinator's former `vcheck.sh`) and `release-minor` (adds `icarus-full`, the former `full_check.sh`). A step passes only with exit 0 and a positive pass count or result line; the summary table, `results.json` and exit code (0 pass, 1 fail, 2 usage, 3 nothing ran) report it. `--help` lists every option.

To build and run the Dhrystone benchmark with the installed LLVM, see [the Dhrystone page](cpu/dhrystone.md):

```powershell
.\sim\cpu\bench\run_dhrystone.ps1
```

## Gallery and journal

Generated drawings of every version and the simulated results: <https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/> (built from `docs/` by `scripts/build_site.py`). Also see the [interactive core infographic](cpu/core-explainer.html), [seven selectable C programs](cpu/programs.md) and [editable program inputs](cpu/inputs.md).

## Read the project

| Document | Purpose |
|---|---|
| [CPU quick start](cpu/README.md) | Files, commands, tested behavior and current limits |
| [CPU architecture](cpu/architecture.md) | Datapath, memory/trap contracts, RVA23 obligations, C0-C7 stages and version history |
| [CPU review rubric](cpu/review-rubric.md) | Gates, scores and evidence needed before calling the CPU good or performant |
| [CPU tools index](sim/cpu/README.md) | Every test, benchmark and helper script under `sim/cpu/` |
| [To do](cpu/TODO.md) | CPU work list and RV64GC milestone (last revised 2026-11-20; DEVLOG.md has the current work) |
| [Development log](DEVLOG.md) | Dated record of sessions, commits and findings; per-commit run records are in `devlog/` |
| [Research reports](cpu/research/README.md) | Standards, ISA roadmap, test inventory and the performance-target sources |
| [LLM accelerator files](llm-accelerator/plan/README.md) | Preserved plan, contracts ([implementation](llm-accelerator/plan/implementation-contract.md), [ABI](llm-accelerator/plan/abi-v1.md), [adapter](llm-accelerator/plan/adapter-v1.md)), reviews and checkers; [operations to RVA23](llm-accelerator/plan/llm-rva23-mapping.md) and [assembly examples](isa/README.md) |
| [FPGA analysis](llm-accelerator/plan/fpga-resource-and-board-analysis.md) | Dated board research and conditional hardware choices |

## Repository layout

```text
README.md, LICENSE, THIRD_PARTY_NOTICES.md, CONTRIBUTING.md, SECURITY.md,
CHANGELOG.md, AGENTS.md, DEVLOG.md   Front matter, rules and the development log
cpu/                  Architecture contract, benchmark pages and targets, result records, infographic
cpu/research/         Research reports cited by the targets pages and plans
rtl/cpu/              Original RV64 cores (multicycle, pipelined, out-of-order) and the RAM/SoC wrapper
sim/cpu/              Differential tests, golden models, suite.py front end, benchmarks (bench/)
sim/starter/          Historical third-party PicoRV32 smoke simulation (its own START-HERE.md)
isa/                  RVA23 floating/vector assembly examples for the future accelerator
fpga/                 Future exact-board constraints and build scripts
scripts/              Repository checks (check_repo.py) and the site generator (build_site.py)
docs/                 Generated GitHub Pages gallery and journal (do not edit by hand)
devlog/               Per-commit run records linked from DEVLOG.md
llm-accelerator/      Preserved LLM-accelerator research: plan/ (plans, contracts, checkers, locks)
                      and planning-evidence/ (historical snapshots)
reference-sources/    Frozen Qwen/Transformers sources and metadata (byte-locked)
notes/, references/   Qwen compute notes; the RVA23 profile PDF
licenses/             Upstream licence texts and provenance.json
.github/              CI, issue forms and pull-request template
```

## Development constraints

- Keep the multicycle reference core serial and observable; add contained traps/CSRs and an external architectural oracle before expanding its ISA.
- Track every mandatory RVA23 capability. Do not label a partial core RVA23 compliant or reuse the accelerator LUT estimates as CPU measurements.
- Measure exact-part synthesis, RAM inference and timing before board selection. FPGA synthesis/programming and supported host access remain pending.
- Preserve reviewed source/fixture identities. Existing LLM storage, RAM and native-run admission rules still apply to any resumed model work.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [CHANGELOG.md](CHANGELOG.md). CI is configured for repository/planning checks, the custom CPU suite and the historical smoke test; GitHub-hosted execution is separate from the recorded local results.

## License

Original work is released under the [MIT License](LICENSE). Third-party material keeps its upstream terms: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) lists each bundled or fetched component with its licence, and the licence texts and their SHA-256 identities are in [licenses/](licenses/README.md). Bundled Transformers/Qwen material, PicoRV32, the RISC-V specification and the benchmark sources (Dhrystone, the 7-Zip LZMA SDK, LLVM compiler-rt, TinyBVH-derived code, smallpt, QuickJS-ng, Berkeley SoftFloat/TestFloat) are not under the MIT licence.
