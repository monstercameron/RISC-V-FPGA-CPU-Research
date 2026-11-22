# CPU simulation, tests and benchmarks: tools index

Every tracked script and testbench under `sim/cpu/`, grouped by job. Each Python tool prints its options with `--help`; the one-line purpose comes from the file's own header. Run everything from the repository root. Generated output goes to the ignored `build/` folder. The contracts these tools check are in [cpu/architecture.md](../../cpu/architecture.md). The benchmark pages are linked from the [root README](../../README.md#read-the-project).

## Start here

| Entry point | Purpose |
|---|---|
| [suite.py](suite.py) | One front end for every test and benchmark: named suites (`--list`), presets `release-patch` and `release-minor`, one summary table and `results.json`, each step under the 300 s limit |
| [suite_manifest.py](suite_manifest.py) | The declarative table of suites and steps that `suite.py` runs; add new suites here |
| [run.sh](run.sh) / [run.ps1](run.ps1) | Default regression: `test_cpu.py` on the multicycle core (Linux/WSL, or Windows through WSL) |
| [bench/run_dhrystone.ps1](bench/run_dhrystone.ps1) | Windows launcher: LLVM build of Dhrystone, then the checked run in WSL, logged to `devlog/` ([cpu/dhrystone.md](../../cpu/dhrystone.md)) |

## Regression and golden models

| File | Purpose |
|---|---|
| [test_cpu.py](test_cpu.py) | Differential suite: generated and directed programs on any core (`--core multicycle/pipe/ooo`), three memory wait patterns, Icarus or Verilator (`--sim`), FP option (`--fpu`), latency knobs, sharding |
| [reference.py](reference.py) | Independent sequential RV64 laboratory interpreter, the trace oracle (not a certified ISA model) |
| [fp_ref_core.py](fp_ref_core.py) | RISC-V F and D semantics with exact integer significand arithmetic, used by `reference.py` |
| [fp_cases.py](fp_cases.py) | Directed F/D test programs for every rounding mode |
| [fp_ooo_cases.py](fp_ooo_cases.py) | F/D cases for the out-of-order core's rename and retirement |
| [fp_timing_cases.py](fp_timing_cases.py) | FP latency and throughput cases for `test_cpu.py --fpu` |
| [fp_oracle.py](fp_oracle.py) / [fetch_softfloat.sh](fetch_softfloat.sh) | Independent FP oracle: Berkeley TestFloat 3e against the golden model, `rv_iss` and the RTL FPU; the fetch script builds SoftFloat/TestFloat 3e from source into `build/third-party/` |
| [simulator.py](simulator.py) | Icarus and Verilator back ends shared by the test and benchmark scripts (finds Verilator, caches builds in `build/sim-cache/`) |
| [check_bitmanip.py](check_bitmanip.py) / [bitmanip_check.c](bitmanip_check.c) | B extension check against the compiler's reading of C |
| [check_soc_memory.py](check_soc_memory.py) | Directed checks of the SoC memory model (L2, memory latency, split reads) |
| [check_btb_reach.py](check_btb_reach.py) | Branch-target-buffer reach check (PC-relative targets, since 0.15.5) |
| [tb_core.sv](tb_core.sv), [tb_reset.sv](tb_reset.sv), [tb_soc.sv](tb_soc.sv), [tb_soclat.sv](tb_soclat.sv) | Testbenches: traced core with fault injection, reset during a stalled store, RAM wrapper, SoC read latency |
| [baselines/](baselines/0.21.0-release-patch.json) | Expected counts and clocks for `suite.py --expect` |

## Lessons, demo and visualizer

| File | Purpose |
|---|---|
| [build_firmware.py](build_firmware.py), [firmware.c](firmware.c), [start.S](start.S), [link.ld](link.ld) | Tiny RV64I firmware built with LLVM into binary and RAM images |
| [c_demo.c](c_demo.c), [run_c_demo.py](run_c_demo.py), [run_c_demo.ps1](run_c_demo.ps1), [tb_c_demo.sv](tb_c_demo.sv) | C demo (sorting, Fibonacci, CRC32) on the RTL with measured simulator cost ([cpu/c-demo.md](../../cpu/c-demo.md)) |
| [program_catalog.py](program_catalog.py), [program_inputs.py](program_inputs.py), [programs/](programs/arrays.c), [add_one.c](add_one.c) | Built-in C lessons, typed inputs and independent expected answers |
| [build_programs.py](build_programs.py), [test_program_inputs.py](test_program_inputs.py) | Compile, simulate and verify every lesson; input boundary tests |
| [build_visualizer.py](build_visualizer.py), [serve_visualizer.py](serve_visualizer.py), [run_visualizer.ps1](run_visualizer.ps1), [tb_visualizer.sv](tb_visualizer.sv) | Offline HTML viewer from a real RTL clock capture, and its local simulator connection ([cpu/visualizer.md](../../cpu/visualizer.md)) |

## Synthesis estimates

| File | Purpose |
|---|---|
| [synth_depth.py](synth_depth.py) | Logic depth and size from a generic Yosys synthesis |
| [synth_fmax.py](synth_fmax.py) | Clock-frequency estimate on a real FPGA family with an open flow (an estimate, not a board measurement) |

## Benchmarks (`bench/`)

| File | Purpose |
|---|---|
| [bench/build_bench.py](bench/build_bench.py) | Build any benchmark (`--benchmark dhrystone/lzma/rt/js/mm/ternary`) with LLVM; records every input |
| [bench/run_bench.py](bench/run_bench.py) | Run a built benchmark on the RTL, check results, report clocks; `--devlog` logs the run |
| [bench/tb_bench.sv](bench/tb_bench.sv), [bench/start.S](bench/start.S), [bench/runtime.c](bench/runtime.c), [bench/include/](bench/include/bench.h) | Timing testbench, startup code, freestanding runtime and headers shared by the benchmarks |
| [bench/rv_iss.c](bench/rv_iss.c) | Fast sequential RV64 functional simulator for the benchmark runners (checkpoints, sampled runs) |
| [bench/bench_checkpoint.py](bench/bench_checkpoint.py) | Checkpoint images: start a benchmark part-way through from reference-model state |
| [bench/bench_profile.py](bench/bench_profile.py), [bench/pipeline_model.py](bench/pipeline_model.py) | Trace profile with what-if estimates; trace-driven CPI model of an in-order pipeline |
| [bench/rubric_score.py](bench/rubric_score.py), [bench/runlog.py](bench/runlog.py) | Review-rubric scorecard; per-commit run logs in `devlog/` and the DEVLOG.md index |
| [bench/dhrystone_port.c](bench/dhrystone_port.c), [bench/vendor/dhrystone/](bench/vendor/dhrystone/SOURCE.txt) | Dhrystone port layer and vendored source |
| [bench/lzma_run.py](bench/lzma_run.py), [bench/lzma_bench.c](bench/lzma_bench.c), [bench/lzma_bench_data.c](bench/lzma_bench_data.c), [bench/lzma_runtime.c](bench/lzma_runtime.c), [bench/lzma_native.c](bench/lzma_native.c), [bench/lzma_rating.py](bench/lzma_rating.py), [bench/include-lzma/](bench/include-lzma/lzma_bench.h), [bench/vendor/lzma/](bench/vendor/lzma/SOURCE.txt) | Scaled 7-Zip LZMA kernel, native harness and 7-Zip's rating formulas ([cpu/lzma-benchmark.md](../../cpu/lzma-benchmark.md)) |
| [bench/rt_run.py](bench/rt_run.py), [bench/rt_bench.c](bench/rt_bench.c), [bench/rt_trace.c](bench/rt_trace.c), [bench/smallpt_rt.cpp](bench/smallpt_rt.cpp), [bench/rt_math.c](bench/rt_math.c), [bench/rt_runtime.c](bench/rt_runtime.c), [bench/rt_native.c](bench/rt_native.c), [bench/rt_export.cpp](bench/rt_export.cpp), [bench/rt_export.sh](bench/rt_export.sh), [bench/include-rt/](bench/include-rt/rt_bench.h), [bench/vendor/compiler-rt/](bench/vendor/compiler-rt/SOURCE.txt) | Ray tracing (RT-T traversal, RT-P smallpt): inputs, native reference, soft-float builtins ([cpu/raytracing-benchmark-targets.md](../../cpu/raytracing-benchmark-targets.md)) |
| [bench/js_run.py](bench/js_run.py), [bench/js/](bench/js/js_bench.c) (`fetch_quickjs.sh`, `gen_src.py`, `kernels.js`, `libc.c`, `js_native.sh`, `js_laptop.py`, `include/`) | QuickJS-ng JavaScript benchmark ([cpu/js-benchmark-targets.md](../../cpu/js-benchmark-targets.md)) |
| [bench/mm_build.py](bench/mm_build.py), [bench/mm_run.py](bench/mm_run.py), [bench/mm/](bench/mm/mm_bench.h) | Matrix and LLM-style kernels, generator, native and laptop references ([cpu/mm-benchmark-targets.md](../../cpu/mm-benchmark-targets.md)) |
| [bench/ternary_run.py](bench/ternary_run.py), [bench/ternary/](bench/ternary/tern_bench.c) | Ternary-weight GEMV: build helpers, data export, laptop reference ([cpu/ternary-benchmark-targets.md](../../cpu/ternary-benchmark-targets.md)) |
| [bench/fp_oracle_iss.c](bench/fp_oracle_iss.c) | `rv_iss.c`'s F/D execution on a file of vectors, for `fp_oracle.py` |

Vendored third-party code is under `bench/vendor/` (exact upstream bytes, with `SOURCE.txt` provenance) or is fetched into the ignored `build/third-party/`. Four files outside `vendor/` are derived from upstream code and keep its terms: `bench/smallpt_rt.cpp` (smallpt), `bench/rt_trace.c` (TinyBVH), and `bench/lzma_bench_data.c` and `bench/lzma_rating.py` (7-Zip); see [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md). The rest is original MIT-licensed work.
