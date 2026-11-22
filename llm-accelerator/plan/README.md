# LLM accelerator planning files

The preserved research for the LLM accelerator (a future workload; the active work is the CPU core, see the [repository README](../../README.md)). These files lived in the repository root until 2026-11-22. They moved together, byte for byte, so their relative links and the SHA-256 identities in `critic-round3-reviewed-hashes.json` still hold. Do not edit the locked ones; see [CONTRIBUTING.md](../../CONTRIBUTING.md).

| Group | Files |
|---|---|
| Plans | [plan.md](plan.md), [memory-plan.md](memory-plan.md), [plan-gap-audit.md](plan-gap-audit.md), [fpga-resource-and-board-analysis.md](fpga-resource-and-board-analysis.md), [ffn-demo-plan.md](ffn-demo-plan.md), [research.md](research.md) |
| Contracts | [implementation-contract.md](implementation-contract.md), [abi-v1.md](abi-v1.md), [adapter-v1.md](adapter-v1.md), [llm-rva23-mapping.md](llm-rva23-mapping.md), [dimension-ledger.md](dimension-ledger.md) |
| Reviews | [critic-round-2.md](critic-round-2.md), [critic-round-3.md](critic-round-3.md), [refinement-review.md](refinement-review.md), `critic-round3-reviewed-hashes.json` |
| Tools | `memory_model.py`, `abi_v1.py`, `plan_audit_checks.py`, `refinement_checks.py`, `fpga_resource_estimate.py` |
| Results and fixtures | `memory-model-results.json`, `plan-audit-checks.json`, `refinement-checks.json`, `fpga-resource-estimate.json`, `abi-lifecycle-example.json`, `qualification-fixtures.json`, `reference-source-lock.json` |

The tools read their siblings by relative name, and the source snapshots in the root `reference-sources/`, which stays where it is. `python -B scripts/check_repo.py` copies the inputs beside `reference-sources/` in a scratch directory, runs `plan_audit_checks.py` and `refinement_checks.py` there and compares the lifecycle fixture, so nothing here is rewritten. The older snapshot in [planning-evidence/](../planning-evidence/README.md) is historical.
