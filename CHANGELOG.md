# Changelog

## Unreleased

### Added

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
