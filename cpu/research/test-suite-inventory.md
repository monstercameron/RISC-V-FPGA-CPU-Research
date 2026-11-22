# Test and benchmark inventory, and the unified front end

Test-infrastructure engineer, 2026-11-22. Written in an ignored folder (build/research), so it is a working note, not a tracked document. "Runtime" is wall time measured on this workstation (WSL2, 20 threads, 14 GB shared) unless marked as an estimate. The front end is `sim/cpu/suite.py`, with its manifest in `sim/cpu/suite_manifest.py` (patch `build/cpu/ooo-debug/coord/suite.diff`).

## 1. Tracked entry points

| Entry point | What it checks | Simulator | Options | Runtime | Suite step(s) |
|---|---|---|---|---|---|
| `sim/cpu/test_cpu.py` | 131 generated programs (227 with `--fpu` on 567c07c) at 3 wait patterns. Traces are compared with `reference.py`, plus reset, SoC elaboration, a SoC smoke run, slot and lane use, instruction coverage and branch outcomes. Writes verification.json | icarus (default) / verilator | `--core {multicycle,pipe,ooo}`, `--core-source`, `--icache/--dcache-beats`, `--fpu`, `--n-miss`, `--ld-lat`, `--l0`, `--l0-lat`, `--image`, `--out-dir`; new: `--shard K/N`, `--merge-shards` | Verilator ooo 32-36 s with a cached build, about 2 min with a fresh build. Icarus ooo about 400 s (one quarter 102 s); Icarus ooo 2-beat about 550 s (one eighth 68 s); multicycle 54 s and pipe 47-56 s | `isa-*`, `fpu-*`, `vector-*`, `full-*`, `negative-xor-or` |
| `sim/cpu/run.sh` / `run.ps1` | `test_cpu.py` with the defaults (multicycle, Icarus) | icarus | pass-through | ~3 min | `isa --core multicycle --sim icarus` |
| `sim/cpu/reference.py` | Sequential golden model (library, no CLI) | - | `fp=True`, `state=` | - | used by every differential step |
| `sim/cpu/fp_cases.py` | FP directed cases on the golden model (`__main__`) | none | - | <1 s | `unit-fp-golden` |
| `sim/cpu/fp_ooo_cases.py`, `fp_timing_cases.py` | F/D cases and FP latency/throughput checks, imported by `test_cpu --fpu` | via test_cpu | - | - | `fpu-*` |
| `sim/cpu/fp_ref_core.py` | Golden FP arithmetic (library) | - | - | - | via the above |
| `sim/cpu/test_program_inputs.py` | unittest: program-input validation for the lessons and visualizer | none | - | 1 s | `unit-program-inputs` |
| `sim/cpu/check_bitmanip.py` | B build of bitmanip_check.c against a base build; traces against the reference. **Broken on main since 4c64892:** `KeyError: 'extra'` from build_bench's new LINKER_SCRIPT field; fixed in the suite patch | icarus only | `--core` (no `--core-source`) | see the DEVLOG rows | `bitmanip-*`, `full-bitmanip` |
| `sim/cpu/check_soc_memory.py` | SoC L2 and memory-latency directed checks (tb_soclat) | icarus | `--out-dir` | ~1 min (estimate) | `soc-memory` |
| `sim/cpu/check_btb_reach.py` | BTB encoding across 4 GiB boundaries (hand-off 15) | icarus / verilator | positional `core out`, `--sim` | ~1 min (estimate) | `soc-btb-reach` |
| `sim/cpu/build_programs.py --check-library` | Lessons and viewer match their sources (programs verification) | icarus + clang | `--check-library` | minutes | not wrapped (it rewrites `cpu/programs-verification.json` without the flag) |
| `sim/cpu/build_visualizer.py` | Visualizer capture (visualizer verification) | WSL Icarus | `--capture-only`, `--reuse-capture` | minutes | not wrapped (writes tracked JSON) |
| `sim/cpu/run_c_demo.py` / `.ps1` | C demo on the SoC, differential | icarus | `--repetitions` | ~1 min | not wrapped (gap: could join `soc`) |
| `sim/cpu/synth_fmax.py`, `synth_depth.py` | Yosys ECP5 + nextpnr timing / logic depth | yosys, nextpnr | `--rtl`, cache beats, `--device`, `--seed` | the ooo core exceeds 300 s (estimate) | not wrapped: needs a split or a smaller target first |
| `sim/cpu/bench/build_bench.py` | Builds benchmark images (dhrystone, lzma, rt, js) and hashes inputs and artifacts | Windows LLVM clang 23.1.5 (or clang on PATH) | `--benchmark`, `--isa`, `--runtime`, `--ram-kib`, `--lzma-dict-log`, `--rt-data`, `--js-ref`, tools, `--out-dir` | 1-2 s | `build:<folder>` steps (reused while hashes and compiler match) |
| `sim/cpu/bench/run_bench.py` | Timing run, mailbox checks, differential traces at stalls 0/7, profile, rubric | icarus / verilator | `--benchmark {dhrystone,lzma,rt,js}`, `--core-source`, L1 beats, memory knobs (`--l2-*`, `--mem-lat`, `--mem-gap`, `--write-fill`, `--n-miss`), core knobs (`--ld-lat`, `--l0`, `--l0-lat`, `--fpu`), sampling (`--lzma-mode`, `--sample-pieces`, `--pieces A:B\|merge`, `--warm-l2`, `--jobs`, `--no-differential`, `--differential-every`, `--functional`), `--rt-mode`, `--js-mode`, `--devlog`, `--record` | Dhrystone 23 s; LZMA d12 64 KiB (24 trace runs) ~2-3 min; 4 KiB ~2 min; js 9 pieces >300 s in one invocation (split into 3) | `dhry-*`, `lzma-*`, `bench-rt`, `bench-js-*` |
| `sim/cpu/bench/lzma_run.py`, `rt_run.py`, `js_run.py` | Benchmark-specific runners behind run_bench (phases, checkpoints, rv_iss) | as run_bench | through run_bench | - | through run_bench |
| `sim/cpu/bench/bench_checkpoint.py`, `rv_iss.c` | Checkpoints and the fast functional ISS (`--fp 1`, `--fp-soft`) | gcc/clang | - | - | through run_bench. The uncommitted FP work adds `test_cpu.iss_fp_check` |
| `sim/cpu/bench/run_dhrystone.ps1` | Windows LLVM build + WSL run + `--devlog` row | as run_bench | `-Core -Sim -Isa -Runtime -Record -NoDevlog` | ~1 min | kept: it is the logged Dhrystone path (`--devlog`). The suite's DEVLOG row is a different, per-run row |
| `sim/cpu/bench/pipeline_model.py`, `bench_profile.py`, `rubric_score.py`, `lzma_rating.py` | Analysis models and report helpers | none | - | - | not tests |
| `scripts/check_repo.py` | Required files, metadata, planning programs | host Python | - | ~1 min | `repo-check` |
| `scripts/build_site.py` | Regenerates docs/ from DEVLOG and history | host Python | - | ~10 s | `repo-site` (tagged writes-docs) |
| `sim/starter/run.sh` | Historical PicoRV32 starter | icarus | - | - | not wrapped (not the CPU under development) |

## 2. The coordinator's release checks (today)

`build/cpu/ooo-debug/coord/vcheck.sh <cand> <out>` runs Verilator steps under `timeout 300`: tests (default caches), tests2 (2-beat), lzma64k, lzma4k (`--no-differential`), dhry_ref, dhry_fast, and, if the candidate defines RV64_OOO_FPU, lzma64k_fpu, dhry_ref_fpu and dhry_fast_fpu. A step fails if its rc is nonzero or no line starts with `PASS`. Weaknesses:
- Any `^PASS` line counts, so a test_cpu run of zero programs would pass.
- It runs serially (16 min for 0.17.2).
- lzma64k and lzma64k_fpu (and the Dhrystone pairs) share one `--out-dir`, so results.json from the plain run is overwritten by the FPU run.
- It needs prebuilt bench folders in `coord/bench`.

`build/cpu/ooo-debug/full_check.sh` runs Icarus test_cpu ooo, ooo 2-line, check_bitmanip, multicycle and pipe. It used **timeout 600 and 1500**, which breaks the 5-minute rule; 28 min on 0.17.0.

The suite equivalents are `release-patch` (= vcheck) and `release-minor` (= vcheck + `icarus-full`). Mapping:
- tests → `isa-ooo`; tests2 → `isa-ooo-2beat`
- lzma64k / lzma4k → `lzma-64k` / `lzma-4k`
- dhry_ref / dhry_fast → `dhry-ref` / `dhry-fast`
- the `*_fpu` steps → `*-fpu`
- full_check ooo / ooo-2line → `full-ooo` (6 shards + merge) / `full-ooo-2line` (12 shards + merge). With 4 and 8 shards, loaded shards took up to 211 s and 252 s, too close to the limit
- full_check bitmanip / multicycle / pipe → `full-bitmanip` / `full-multicycle` / `full-pipe`

## 3. Overlaps and gaps

**Overlaps.**
- `isa-ooo` (Verilator) and `full-ooo` (Icarus) run the same programs. Both are kept because Verilator is 2-state, so Icarus stays the reference.
- bench-smoke and bench share `dhry-ref` and `lzma-64k`. They are declared once and belong to both suites, so they run only once.
- run_dhrystone.ps1 and `dhry-ref` run the same simulation; only the .ps1 writes the `--devlog` run index.
- About 1450 snapshot-tree copies of sim/cpu under build/ duplicate tracked code (section 5).

**Gaps (no tracked runner).**
- `--vector` and `--dline` exist only in engineers' trees. The `vector` suite and the `--vector`/`--dline` pass-through turn on by themselves once test_cpu.py or run_bench.py has the flag; until then the suite reports "unavailable" or stops with an error.
- `--benchmark mm` and `ternary` landed at fbc5add. bench-ternary PASSes through the generic parser in about 125 s. bench-mm needs `build/cpu/bench/mm-data/small` (from mm_export.sh), which main's checkout does not have.
- `sim/cpu/fp_oracle.py` (TestFloat oracle, 6c989be) is not wrapped yet: its runtime is unmeasured; `--muladd-offset` and `--only` would allow a split.
- js needs 9 one-piece invocations: 3 pieces took more than 300 s at load 15. A full `bench` run is about 25 min serial and was not run end to end.
- Fuzzers (FP trace fuzz, vector fuzz), FPU random RTL differentials, crosscheck, and mutation testing: these exist only in build/cpu/fp and council/backend|memory.
- The SMT probe, coverage-counter probes, and all the `tb_*stat` perf probes.
- check_bitmanip.py takes no `--core-source`, so with a candidate it tests the rtl/cpu file. The suite prints the core file each step tested.
- synth_fmax/synth_depth on the ooo core do not fit in 300 s without splitting.
- There is no machine-wide run lock. The council's BOARD.md "LOGGED RUN IN PROGRESS" polling is ad hoc; the suite's `--jobs` limits only its own run.

## 4. Harness bugs found in the ad-hoc runners

- **Exit 0 on failure:**
  - `council/simd/review/vtest.py` (build/ copy: no `sys.exit`, passes with zero programs, skips a missing second model)
  - `backend/fp/fptest*.py`, `fp_lat.py`, `fp_tput.py`
  - `mem/mdp_test.py`, `mem/x4_test.py`, `find_fail.py`
  - every `tail -3 | head -1` wrapper (`regress_*.sh`, `other.sh`, `int_check.sh`, `split/check.sh`, `reg_h2*.sh`, `regress_be.sh`, `reg32.sh`)
  - the `st()`/`rc=` batches (`backend/cl/run*.sh`, `rtpkg*/chk17x.sh`, `middle/p3/ev17*.sh`, `dl_ev*.sh`)
  - `fp/run_crosscheck.sh` (`|| true`)
  - `vmutate.sh` and `run_mut*.sh` (no killed-mutant verdict)
- **Timeouts over 300 s:** `full_check.sh` (600/1500), `rb.sh` (900), `middle/p3/dl_ev2.sh` (600), `fm_runs.sh` (900), `rt_runs.sh` (1200). `7zip-bench/run_lzma.sh` and `area/run.sh` have no timeout at all.
- **Sharding pitfall:** the middle engineer's `test_*_p0..p2.py` forks keep the instruction-coverage assert in each third, so a third can fail falsely. `test_cpu --shard` skips the whole-suite checks per shard and runs them once on the union in `--merge-shards`, which also refuses an incomplete or mixed set of shards.

## 5. Ad-hoc runners under build/ and what replaces them

Counts are from a read-only sweep, excluding worktrees (`*/wt*`), third-party and sim-cache. There are about 1911 scripts in all: about 1454 are snapshot/mirror trees and about 457 are hand-written.

| Group | Wraps | Redundant with the suite? |
|---|---|---|
| `coord/vcheck.sh` | test_cpu + run_bench (Verilator) | **Yes**: `release-patch` |
| `ooo-debug/full_check.sh` | Icarus test_cpu x3 cores + bitmanip | **Yes**: `icarus-full` / `release-minor` |
| `ooo-debug/{regress_cand,regress_ooo,other,int_check,rb}.sh`, `../regress_both.sh`, `split/check.sh` | test_cpu default/2-beat, bitmanip, Dhrystone | **Yes**: `isa`, `bitmanip`, `dhry-ref` |
| `coord/v150/check_soc_memory.py` | copy of the tracked script | **Yes**: `soc-memory` |
| `council/backend/{tc,tc2,t7}.sh`, `fpx/chk*.sh`, `rtpkg2/pre173.sh` | test_cpu Verilator with knobs (`--ld-lat`, `--l0`, `--fpu`) | **Yes**: `isa`/`fpu` with pass-through knobs |
| `council/backend/{lz,lzd,dh,r7,lfrun*,sweep_f,sweep_ld,refresh}.sh` | run_bench lzma/Dhrystone | **Yes**: `bench-smoke` (+ `--compare`) |
| `council/backend/cl/run*.sh`, `rtpkg/chk171.sh`, `rtpkg2/chk172.sh` | vcheck + rt | **Yes**: `release-patch` + `bench --only bench-rt` |
| `council/backend/{pr,pr16,pr16w}.sh`, `preset/batch*.sh`, `dec/{run,batch}.sh`, `rt/{rrun,rrunf,batch}.sh`, `rtpkg/proof*.sh` | run_bench sampled lzma d16/d18 and rt with `--pieces` and DEC knobs | **Mostly**: pass-through knobs + `--bench-args`. The d16/d18 bench folders are not in the manifest yet (adding them is a BENCH_RUNS row with a split) |
| `council/backend/{test_backend,test_backend_v2}.py`, `regress_be.sh`, `one.sh`, `rest.sh` | test_cpu plus directed cases | Yes, once the cases are merged into test_cpu |
| `council/middle/test_*_p[012].py` (15) and other `test_cpu_*` forks (9), `mk_test.py`, `reg_h2*.sh` | forked test_cpu, thirds | **Yes**: `--shard` + `--merge-shards` |
| `council/middle/p3/{ev17,ev17b,dl_ev1-4,h14_all,h14b_all,fm_runs,rt_runs,dhry}.sh` | release-evidence matrices (N_MISS, DLINE) | Yes, once `--dline` is tracked (`--n-miss` passes through today) |
| `council/memory/sh/{tcpu,lz,dh,h2official,h2tests}.sh` | test_cpu / run_bench | **Yes** |
| `council/frontend/{test_cpu_fe,test_cpu_tb,test_cpu_x,gen_tb}.py`, `reg32.sh`, `regsplit.sh`, `p3/treg.sh`, `p3/{tplain,tsplit}/run.sh`, `dh.sh`, `lz*.sh`, `p3/d16/run.sh` | test_cpu forks (ONLY lists, halves per cache size) | **Yes**: `--shard`, `--only` |
| `council/bench/{run_d22_*,rerun_*,val_d16_*,run_mdp_check,probe_154}.sh`, `7zip-bench/run_lzma.sh`, `7zip-bench/ooo_*.py`, `research/memcomp/scripts/knob_runs.sh` | run_bench lzma d16/d22 pieces | Partly: the mechanism exists (`--pieces` split + merge); the folders and piece plans need manifest rows |
| `cpu/fp/{run_fpu_rtl,run_off}.sh` | test_cpu `--fpu` / FPU-off | **Yes**: `fpu`, `isa` |
| Snapshot trees (`introot`, `w110root`, `mem/*root`, `split/root*`, `backend/{cl/root,rootF,rootH*,rt17*,rtpkg*,tchk}`, `middle/p3/{dl17,dl172,dlb,repo17,rt17,...}`, `bench/root*`) | patched copies of sim/cpu | Yes for `--core-source` candidates. Trees that carry tb or SoC changes still need them (a `--tb-source` option is future work) |
| Perf probes (`fastprobe.sh`, `hprobe.sh`, `wstat.sh`, `*/p3/vb*.sh`, `vr*.sh`, `mprobe.sh`, `sprobe.sh`, `fable/*`, `lzma-research/*`) | `tb_*stat` benches | No: research instruments, not pass/fail tests |
| Fuzz, crosscheck, mutation (`cpu/fp/{run_fuzz,run_vfuzz,vmutate,run_mut*,run_crosscheck,run_shards}.sh`, `backend/fp/fptest*.py`, `memory/sh/covrun.sh`) | unique capabilities | No: gaps. Candidates for future suites (`fuzz`, `mutation`); the `negative` suite is the first mutant-must-fail step |
| `cpu/area/*`, `synth/run_variants.sh` | yosys/nextpnr queues | No (synthesis, not in scope) |
| Process kill, mirror and patch helpers, analysis/aggregation scripts | infrastructure | No |

Nothing in build/ was deleted or edited. These scripts are only marked redundant here, because other engineers may still be using them.

## 6. The front end

`sim/cpu/suite.py` (named like `test_cpu.py` and next to it, where agents already look; "suite" because the user asked for one test suite, and a name that is not tied to one simulator or runner). The manifest is a Python table, `sim/cpu/suite_manifest.py`, rather than TOML: suites are generated per core and per cache size, steps carry conditions such as "the core defines RV64_OOO_FPU" or "run_bench has --benchmark mm", and Python needs no parser dependency.

- **Suites:** `unit`, `isa`, `fpu`, `vector`, `bitmanip`, `bench-smoke`, `bench`, `icarus-full`, `soc`, `negative`, `repo`.
- **Presets:** `release-patch` and `release-minor`.
- **Flags:**
  - selection: `--list`, `--dry-run`, `--only`/`--skip` (globs over step, suite or tag)
  - core and simulator: `--core`, `--sim`, `--core-source`, `--cache-sizes`
  - pass-through knobs: `--fpu`, `--vector`, `--dline`, `--n-miss`, `--ld-lat`, `--l0`, `--l0-lat`, `--l2-kib`, `--l2-ways`, `--l2-line`, `--l2-lat`, `--mem-lat`, `--mem-gap`, `--write-fill`, plus free-form `--test-args`/`--bench-args`
  - running: `--jobs` (default 2), `--out-dir`, `--bench-root`, `--rebuild`
  - results: `--expect` (fail on a difference), `--compare` (report only), `--json`, `--devlog-row`, `--who`
- **Exit codes:** 0 pass, 1 fail/timeout/diff/blocked, 2 usage, 3 nothing ran.
- **Pass rule:** exit 0 and a positive count. test_cpu's PASS line must also agree with its verification.json or shard.json. A Traceback after a PASS fails. A timeout is TIMEOUT, never a pass.
- **Self-test:** `suite.py --self-test` holds 26 harness negative controls.
- **Negative suite:** a real mutant (xor becomes or) must fail with a trace mismatch.
- **Limit:** every invocation runs under `timeout -k 10 300`, with a Python-side backstop at 330 s.
- **Long Icarus runs** become `test_cpu --shard K/N` steps plus `--merge-shards`. Shards are balanced by golden-model trace length, because every-N-th interleaving put the two longest programs in one shard (266 s under load); balanced, the worst loaded shard took 194 s. The merge checks that all shards come from the same configuration and the same file hashes, and that each program is covered exactly once.
- **js** runs as three `--pieces` invocations plus `merge`.
- **Bench folders** sharing one build are serialized by a lock. Each step's results.json is copied into the run folder, which fixes vcheck's overwrite.
- **Bench images** are built with the Windows LLVM from either side; from WSL through `python.exe` interop. They are reused only while input hashes, artifact hashes and the compiler match.
- **Worktrees:** Verilator and TinyBVH come from the main worktree as directory junctions, which Windows and WSL both see. A WSL `ln -s` link is invisible to Windows Python. Benchmark inputs (quickjs-ng, compiler-rt, smallpt, rt/js/mm/ternary data) are copied instead, because build_bench.py resolves them and a junction resolves outside the worktree.
