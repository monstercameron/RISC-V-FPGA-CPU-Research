# Research reports

Snapshots of the research reports that the CPU documents and benchmark tools cite. Each was written on 2026-11-22 by a research agent for the coordinator, who set the goals; a report states its own sources and marks each fact as fetched, searched, recalled or judged. They are evidence for decisions, not specifications: [cpu/architecture.md](../architecture.md) governs the CPU, and the targets pages state the goals.

Reports mention `build/research/...` data folders (fetched pages, probe output). Those folders are ignored by git and are not part of this snapshot; the reports' tables are the record.

| Report | Cited by |
|---|---|
| [performance-targets.md](performance-targets.md) | Apple M6 per-clock reference ratios in the 7-Zip, ray-tracing, JavaScript, matrix and ternary targets pages and their run scripts |
| [bitnet-ternary.md](bitnet-ternary.md) | [ternary targets](../ternary-benchmark-targets.md) |
| [riscv-matrix.md](riscv-matrix.md) | [matrix targets](../mm-benchmark-targets.md) |
| [js-engines.md](js-engines.md) | [JavaScript targets](../js-benchmark-targets.md) |
| [standards.md](standards.md), [isa-roadmap.md](isa-roadmap.md), [test-suite-inventory.md](test-suite-inventory.md), [rv64gc-linux.md](rv64gc-linux.md), [cpu-catalog.md](cpu-catalog.md) | Gap fixes and plans; ISA roadmap, standards references, test inventory, Linux-capable core survey, comparison cores |
| [fp-contract-draft-0.17.0.md](fp-contract-draft-0.17.0.md) | Superseded draft of the F/D contract, folded into architecture section 1 at 0.17.0 |

Other reports (memory compression, prefetch, MLP/MSHR, FFmpeg, RPCS3 SIMD, CPU ideas) stay in ignored `build/research/` until their recommendations are acted on.
