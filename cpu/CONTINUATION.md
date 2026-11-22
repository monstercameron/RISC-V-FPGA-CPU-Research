# Continuation: where the project paused (2026-11-22, about 14:55)

Read this first when resuming, then AGENTS.md, README.md, cpu/architecture.md (sections 2, 3, 9) and the
latest part of DEVLOG.md. Every number here is a simulation result unless it says otherwise. Nothing is a
hardware measurement.

## 1. State of the repository

- **Branch:** `main`. The latest CPU version is **0.21.0** (`cpu/VERSION`, tag `cpu-v0.21.0`). It is pushed to
  GitHub with a GitHub Release.
- **Released on 2026-11-22**, each its own semver step with a tag, a history row and a GitHub Release:

  | Version | Change |
  |---|---|
  | 0.19.0 | D-side 64 B lines (`RV64_OOO_DLINE`) |
  | 0.19.1 | ITTAGE (`RV64_OOO_ITTAGE`) |
  | 0.19.2 | SoC 64-bit DRAM delays |
  | 0.19.3 | Instruction-cache ways (`RV64_OOO_IWAYS`) |
  | 0.19.4 | Last-writer-table fusion |
  | 0.19.5 | S3: entry 0 adopts an in-flight line read |
  | 0.20.0 | L2 stream prefetcher (`L2_PF`) |
  | 0.21.0 | M-mode CSR file S1 on the multicycle core (`RV64_PRIV`, `rtl/cpu/rv64_csr.sv`) |

- **Committed but not pushed** (the push rule covers only version releases, so these need the user's yes):
  - `a718aba`, the 7-Zip-matched decompression CRC benchmark plus the new suite baseline;
  - `18b2158` and `dc55aff`, site gallery and journal updates.
- **Suite baseline:** `sim/cpu/baselines/0.21.0-release-patch.json`. Use
  `python -B sim/cpu/suite.py release-patch fpu vector --expect sim/cpu/baselines/0.21.0-release-patch.json`.
  For a MINOR, use `release-minor`, plus `soc` or `sys` when they are touched. The release presets include the
  Spike lockstep suite.
- **Site:** https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/ (the Atelier landing page, gallery and
  journal, built by `scripts/build_site.py`). The GitHub repo's About box links it.

## 2. Goals and the latest measured numbers

- **7-Zip, 10,000 MIPS at 4 GHz:** met on cpu-v0.18.0 at the deciding config (d22, 4 MiB L2), with the
  7-Zip-matched CRC bench.

  | Phase | MIPS/MHz | Share of phase goal | Low end | Low end share |
  |---|---:|---:|---:|---:|
  | Compress | 2.211 | 109% of 2.02 | 2.072 | 103% |
  | Decompress | 2.975 | 120% of 2.47 (provisional) | 2.887 | 117% |

  The average is 2.593, or 10,372 MIPS at 4 GHz; the low ends average 9,918. The decompress goal is
  provisional: the laptop reference was measured under load and needs a quiet re-measure. Later versions were
  not measured at d22. Table: `cpu/7zip-benchmark-targets.md`.
- **Ray tracing:** the goal is the Apple M6 reference, `cpu/raytracing-benchmark-targets.md`. At the deciding
  config, the last measured rates (0.19.0 with DLINE 64) were primary 3.71 and secondary 1.96 rays/kclk,
  against goals of 5.92 and 8.64. Since then:
  - fusion: -0.5% to -1.0% clocks;
  - the L2 prefetcher: -0.2% to -3.1% with a warm L2;
  - RSPW, below.

  The big remaining levers are RSPW bandwidth and the out-of-order vector work (SIMD step 2a).
- **JS:** goal 1.30x the laptop. With ITTAGE plus IWAYS 4: 121.6% of the goal flat and 91.4% at the deciding
  config with FDIP's ceiling; without FDIP, 84.7% at the deciding config.
- **User decision (07:08):** goal status is judged on the current deciding config. The realistic-pipeline
  column (FE_DEPTH 12, LD_LAT 3, no L0) is for information only.

## 3. Work in flight when paused

- **RSPW (wider split-read answers, bus-contract MINOR): rev 3 is ready to release.** Nothing is running.
  - **Files:** package `build/cpu/ooo-debug/council/bw/rspw-on-main.diff` (7 files, sha256 ddec974094895a7a,
    base dc55aff), built by `bw/rspw-rev3.py`. Text and history row (version blank) are in
    `bw/architecture-rspw.md`, DEVLOG rows in `bw/rspw-devlog.md`, the tree is `bw/wtr`, and the status is in
    `bw/HANDOFF-SONNET.md`.
  - **New tests:**
    - `line_fault_lane1/2/3` put a fault in answer lanes above 0.
    - `line_store_lane_sweep` sweeps stores into lanes above 0.
    - Two broken-core negative controls fail them at RSPW 2/4/8. They were not re-run after the last edits.
  - **Evidence:**
    - test_cpu DLINE 64, N_MISS 4, RSPW 1/2/4/8 at both cache sizes: 884 runs each, PASS.
    - N_MISS 8 with RSPW 8, and DLINE 16 with RSPW 2: PASS.
    - `release-minor fpu vector soc --expect 0.21.0-release-patch.json`: 70/70, the same as the baseline.
    - Codex: no counterexample. Its fixes are in, and what was declined is reasoned in the DEVLOG rows.
  - **Bounds:**
    - L2-resident reads at RSPW 1 / 4 / 8: 7.62 / 13.68 / 14.23 B/clk.
    - With DRAM as the limit, RSPW does not help: D1 + DLINE 64 + N_MISS 8 reads 6.52 B/clk at RSPW 1 and
      6.48 at RSPW 4.
  - **Ray tracing at the deciding config,** sampled mode (cold L2): RSPW 4 alone gains 1.3% on primary rays and
    0.0-0.2% elsewhere. **Ray tracing is not bandwidth-bound there.** The prefetcher combination (D1 + DLINE 64
    + N_MISS 8) halves primary clocks against the default, 682,755 -> 337,993, but cold-L2 sampling overstates
    that.
  - **Not done:**
    - Full-mode rt does not fit in 300 s; it needs splitting into pieces.
    - A bus-level SoC test (Codex finding 2).
    - Scratch to clean: bw/negA, bw/negB, bw/negP, and the wtr worktree.
  - **To release:** apply the diff on main, run the coordinator check, assign the next MINOR (0.22.0) and
    publish as usual.
  - **Implication for the ray-tracing goal:** after RSPW, the next lever is the out-of-order vector work and
    latency, not bandwidth.

## 4. Docket, in order (each step its own version)

1. **RSPW** (above), then 16 data tags (MINOR), then L2_MSHR (`bw/l2mshr.py`), then a higher prefetcher fill cap.
2. **Front end** (`council/frontend/HANDOFF-SONNET.md`): I-line (non-blocking instruction-line reads on tags 8-15,
   MINOR; rev 2 core `js/cores/c3r2_off.sv`, text `handoff-il/architecture-iline.md`, untested since the disk
   incident), then FDIP (ceiling -10.7% js at the deciding config).
3. **SIMD step 2a** (out-of-order vector execution, PATCH), then RVV coverage 2b, 2c, 2d (each a MINOR)
   (`build/research/rvv-complete.md`). An rv_iss vector mode comes before 2b.
4. **Privilege** (`build/research/priv-rtl.md`): P2 (S1 in the out-of-order core), P2b, P3 (Zicntr), P4
   (interrupts and WFI, with a `wfi_sleep` port), P5 (U), P6 (S and delegation). The S1 follow-ups are in
   `coord/HANDOFF-SYS-SONNET.md`: nested trap, vectored mode, stall > 0 pair-store fault.
5. **Small ISA steps** (`build/research/counters-rva23.md`): declared hints, Zicond, Zimop, read-only counters,
   the counter event bus.
6. **Atomics** (`build/research/atomics-rtl.md`): A0 models and tests, A1 in the out-of-order core, then fences,
   Zawrs, PMA, snoop.
7. **Misaligned access**, then the **C extension** (`build/research/rvc-misaligned.md`).
8. **MMU** (`build/research/mmu-rtl.md`): T0 test-only, then the Sv39 contract, then TLBs.
9. **Middle queue:** a fusion probe that prefers the unwritten source; the js adjacency preference (lwfuse2);
   FP move elimination; I-side line fill and next-line prefetch.
10. **Pipelining** (`build/research/pipelining.md`): FE_DEPTH/Q_N defines and a "realistic" suite preset
    (PATCH), MUL_LAT, and split decode/execute redirects.

## 5. How to release a version (the coordinator's kit)

- The kit is in `build/cpu/ooo-debug/coord/release-kit/`. It was copied out of the session scratchpad because
  the scratchpad can be cleared.
  - `release.py`: installs the candidate, syncs the canonical sources, adds the architecture sentence and the
    history row (through `record_version.py`, which updates VERSION, the title and the rubric hashes) and the
    DEVLOG row, runs check_repo, commits and tags.
  - `specs/rel*/`: earlier specs, useful as templates.
  - `devrow.py`: adds a row to today's DEVLOG timeline.
  - `relnotes.py`: GitHub release notes from a history row.
  - `canon.py` and `assemble_wide_dl.py`: the out-of-order core is assembled from `canon_*/wide_body.sv` and
    `wide_clock.sv`. `canon_0195` is the current one; its body equals `rtl/cpu/rv64_ooo.sv` from the `module`
    line on.
- **Steps:**
  1. Apply the package and build the candidate.
  2. Run the release check on main (both cache sizes; Dhrystone and 7-Zip numbers).
  3. Write the spec and run `release.py`.
  4. Push main fast-forward, push the tag, then
     `gh release create cpu-vX.Y.Z --verify-tag --notes-file <relnotes output>`, newest marked latest.
- If a version changes default-build timing, its check's `results.json` becomes the new baseline (LF
  line endings). Register it in `scripts/check_repo.py` and point the docs at it.

## 6. Standing rules learned on 2026-11-22 (in addition to AGENTS.md)

- **Models:** subagents run on Sonnet; site updates run on Haiku. The user is short on usage.
- **Publishing:** for each released version, push main (never force), its tag and its GitHub Release. Any
  other outward action (other pushes, repo settings, renames, deleting tags or releases) needs asking.
- **Disk:** check that C: has at least 5 GB free before runs. A runaway trace filled the disk twice on
  2026-11-22.
  - Every lockstep or penv path needs `+max_retired` and a trace cap.
  - The Verilator cache is bounded, at 300 builds (`sim/cpu/simulator.py`).
  - The WSL image can be compacted with an elevated `diskpart` (`compact vdisk`); Windows Home has no
    Optimize-VHD.
- **Git:** use Windows Git Bash only. Never run git (above all `worktree prune` or `gc`) from WSL: it sees the
  `C:/` worktree paths as missing. Worktrees are locked, and `gc.worktreePruneExpire=never` is set.
- **Scratch files:** delete only scratch you created, after checking `ps -eo args`, and never with broad
  `/tmp` globs.
- **Suite scratch:** suite.py keeps per-run native scratch, so concurrent suites in different trees no longer
  collide.
- **Codex reviewer (GPT 6.2 Astra):** runs hourly (`build/cpu/ooo-debug/council/codex/periodic.ps1`), checking
  completeness, bugs and performance. Paused at this stop; restart it in the background.
- **Reporting:** report only numbers read from output. An unmeasured figure went out once and was withdrawn.

## 7. The active ray/path-tracing goal: what is done and what is left

The user's standing goal is a vectorized ray/path-tracing benchmark (TinyBVH traversal plus a smallpt-style path
tracer, RVV 1.0 at VLEN 128/256/512) with a goal of the laptop plus 50%. In the 03:37 decision, "M6
everywhere", the user replaced that goal with the Apple M6 reference.

**Done:**
- The benchmark: `sim/cpu/bench/rt_bench.c`, `rt_math.c`, `rt_runtime.c`, `rt_native.c` and `rt_export.cpp`,
  run by `rt_run.py`, with the workloads in `cpu/raytracing-benchmark-targets.md`.
- The scalar FP32 reference, with correctness checks (hit IDs, distances, image checksums, differential traces
  against rv_iss).
- The laptop measurement (2026-11-21 23:14 to 23:28), then the goals: laptop + 50%, now the M6 reference.
- F/D in the out-of-order core (0.17.0 to 0.17.4, with realistic FADD 2, FMUL 3 and Lion Cove divide/sqrt
  latencies).
- RVV step 1, in order at the ROB head (0.18.0, `RV64_OOO_V`, VLEN 128/256/512).
- The memory side for irregular access: 64 B lines, the L2 prefetcher and RSPW.

**Not done:**
- Out-of-order vector execution (SIMD step 2a) and the RVV coverage the vector kernels need: integer, mask,
  permute, gather/scatter and compaction (steps 2b to 2d; plan in `build/research/rvv-complete.md`).
- Measured scalar against 4/8/16-lane runs on our core at VLEN 128/256/512, with lane utilization and
  divergence counters (the counter event bus is docketed).
- The native Apple M5, Panther Lake and Zen 5 comparisons on identical workloads. None of those machines is
  available here, so only cited or bridged figures exist (`build/research/performance-targets.md`). Do not
  present them as measured.
- The ray-tracing goal itself: at the deciding config the core is at roughly 60% (primary) and 25% (secondary)
  of the M6 rays-per-clock goal.

**Next for this goal:** SIMD 2a, then RVV 2b/2c with gather and compaction, then a vectorized `rt_bench` kernel
measured at the three VLENs.

## 8. Open questions for the user

- Push `a718aba`, `18b2158` and `dc55aff`?
- Which docket item comes next after RSPW?
- The repository rename for the Atelier brand: the name is still undecided. The rename is outward, and the
  Pages URL changes with it.
- Lower the 5-minute status cadence while little is running?
- Quiet-laptop re-measure of the 7-Zip decompress goal (provisional 2.47).
