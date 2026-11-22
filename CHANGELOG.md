# Changelog

This file was last extended at architecture 0.4.0 (November 20, 2026). Every later CPU release, 0.5.0 to the current [cpu/VERSION](cpu/VERSION), is recorded with its evidence in the [architecture version history](cpu/architecture.md#history) and tagged `cpu-vX.Y.Z`; benchmark, test and tooling additions since then (the pipelined and out-of-order cores, the 7-Zip, ray-tracing, JavaScript, matrix and ternary benchmarks, the TestFloat oracle, `sim/cpu/suite.py`) are in [DEVLOG.md](DEVLOG.md).

## Unreleased

### Added

- CPU optimization loop, architecture 0.1.1 to 0.4.0, each step profiled, regressed, tagged and benchmarked: fetch buffer, 4 KiB instruction cache, loads and stores issued from EXECUTE, same-clock RAM writes, 4 KiB write-through data cache and the M extension. Dhrystone: 2,188.2 to 555.7 clocks per run (3.94x), 0.260 to 1.024 DMIPS/MHz in simulation. The regression grows to 111 runs and 66 instructions, with options to shrink both caches.
- Trace profile on every Dhrystone run (clocks by instruction class and function, hot instructions, fetch-reuse share, what-if estimates) and per-commit run logs in `devlog/devlog-<commit>.md`, indexed from DEVLOG.md.
- Semantic versioning for the CPU architecture: version 0.1.0 for the existing C0 core, bump rules, a release process with `cpu-vX.Y.Z` tags, a version history, a repository check that the version is consistent, and the version recorded in benchmark results and scorecards.
- Rubric scorecard for every Dhrystone run, computed from a per-criterion evidence file and the run's own measurements and appended to the development log; AGENTS.md now requires every experiment to be logged there.
- Development log with timestamped events, commit messages and findings, starting November 20, 2026.
- Dhrystone benchmark: riscv-tests source pinned with license and provenance, a freestanding runtime with software multiply and divide, marker-based timing, a 64 KiB build, result and differential-trace checks, a CI job and a first recorded simulation result of 0.260 DMIPS/MHz.
- Trace testbench memory size and cycle limit are now parameters; defaults are unchanged.
- CPU to-do list with an RV64GC milestone mapped to the C1-C4 gates, benchmark work and later large-software goals.
- CPU review rubric: scope label, evidence classes, hard gates, 0-4 scoring across nine weighted dimensions, benchmark rules and the claims each result permits, with the current core's gate status.

- Editable inputs for all seven CPU lessons, separate draft/recorded values, generated C with input-specific result checks, bounded validation, and zero-input firmware support.

- Seven selectable CPU study lessons with verified saved runs, questions and explanations, opcode-grounded checkpoints, and a command to rebuild the complete library.

- Selectable 1 + 1 C workload, proof of an actual ADD with operands 1 and 1, and binary instruction/byte views alongside C and assembly.
- CPU execution viewer connected to LLVM/Icarus through a local Run simulation button, with captured clock states, C/assembly mapping, registers, memory writes, rewind and verified output.
- Reproducible compiled C sorting/Fibonacci/CRC32 demo with checked outputs, instruction-trace comparison and measured simulator runtime/memory.
- CPU-first architecture and staged RVA23U64 completion ledger; the earlier accelerator design remains preserved research.
- Original RV64I/FENCE.I execution core, synchronous RAM wrapper, differential tests, reset/fault coverage and compiled bare-metal firmware.
- Offline interactive HTML core infographic with component explanations and add/load/branch/fault lessons.
- Complete LLM-operation-to-RVA23 mapping, five assembly example files and 23 checked instruction encodings; RISC-V runtime execution remains unverified.
- Complete Qwen3.8-27B text/vision accelerator plan, memory/resource analysis and bounded implementation contracts.
- Versioned command/adapter protocols, frozen source and fixture manifests, and reproducible planning checks.
- Three adversarial plan-review rounds closing 13 findings; native numerical, RTL and hardware gates remain pending.
- MIT license for original work, bundled upstream licenses and third-party attribution.
- Repository conventions, contribution/security guidance, issue/PR templates and pinned GitHub Actions CI.
- A dependency-free repository runner that checks a temporary copy and preserves reviewed evidence.

### Preserved

- Earlier RISC-V research, the ISC-licensed PicoRV32 CPU starter and historical model/FFN planning evidence.

No stable accelerator release or measured full-model FPGA result has been published.
