# Repository guidance

- Start with README.md and cpu/architecture.md. The user changed the active priority to CPU CORE FIRST on October 23, 2026: an original FPGA RV64 core with a staged RVA23U64 target. The LLM accelerator documents are preserved research/future work.
- CPU behavior is governed by cpu/architecture.md. Run sim/cpu/run.sh for RTL changes. Keep ISA/profile, privilege, simulation and physical-hardware claims distinct. For accelerator changes, read its implementation, ABI and adapter contracts first.
- Root plans/helpers are maintained. Files in llm-accelerator/planning-evidence/ are historical snapshots; avoid changing duplicate copies casually.
- Preserve exact bytes and upstream headers in reference-sources/, source/fixture locks and vendored code. Intentional identity changes need provenance, a versioned reason and independent review; never regenerate anchors solely to silence a failure.
- Run `python -B scripts/check_repo.py` for applicable repository/planning changes. Run focused RTL/numerical checks when their implementation changes. Record unavailable empirical validation accurately.
- Keep generated files in build/ or another ignored directory. Do not download model weights or start long native runs without the plan's storage/RAM/runtime admission checks.
- Keep MIT original-work licensing separate from third-party terms. Add provenance/license notices when importing material.
- Do not invent repository owners, private contacts, CI results, releases or measured hardware performance. Changes to a previously reviewed artifact do not inherit its old review score automatically.
