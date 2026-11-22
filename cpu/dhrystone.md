# Dhrystone on our custom CPU

**Last logged result, architecture 0.15.1, out-of-order core: 18.17 DMIPS/MHz** built for `rv64im_zba_zbb_zbs_zifencei` with the reference runtime, and 27.98 with the labelled fast runtime ([later cores](#later-cores-pipelined-and-out-of-order-logged-runs)). The multicycle core's last measured result (0.7.1) is 2.216 DMIPS/MHz (2.174 for `rv64im`, 2.078 for `rv64i`), and 2.624 with the fast runtime. The first 0.1.0 core scored 0.260. All are simulation runs of the core with its synchronous RAM, so they are non-compliant runs under the [review rubric](review-rubric.md), evidence class E1, and do not support calling the core performant.

Dhrystone is the secondary benchmark in the rubric. Report it next to CoreMark once that runs, never on its own.

## Optimization history

Each step was chosen from the previous run's profile, passed the main regression, was committed and tagged with its architecture version, and was then benchmarked. Clang 23.1.5 at `-O2`, 64 KiB RAM, 500 runs. Every run's full record is linked from the run index in [DEVLOG.md](../DEVLOG.md#run-logs).

| Version | Change | Clocks per run | CPI | DMIPS/MHz | vs 0.1.0 |
|---|---|---:|---:|---:|---:|
| 0.1.0 | Baseline multicycle core: fetch 2 clocks, execute 1, loads and stores 2 more | 2,188.2 | 3.647 | 0.2601 | 1.00x |
| 0.1.1 | One-entry fetch buffer | 1,706.2 | 2.843 | 0.3336 | 1.28x |
| 0.2.0 | 4 KiB direct-mapped instruction cache | 988.7 | 1.648 | 0.5756 | 2.21x |
| 0.2.1 | Loads and stores issue from EXECUTE | 794.7 | 1.324 | 0.7162 | 2.75x |
| 0.2.2 | RAM wrapper acknowledges writes in the same clock | 718.7 | 1.198 | 0.7919 | 3.04x |
| 0.3.0 | 4 KiB write-through data cache for loads | 600.8 | 1.001 | 0.9473 | 3.64x |
| 0.4.0, `rv64i` build | M extension; this build does not use it | 600.8 | 1.001 | 0.9473 | 3.64x |
| 0.4.0, `rv64im` build | Hardware divide replaces the software routine; 553 instructions per run instead of 600 | 555.7 | 1.005 | 1.0242 | 3.94x |
| 0.5.0 | Limited dual issue: a simple second instruction from the same 8-byte beat | 435.7 | 0.788 | 1.3062 | 5.02x |
| 0.5.1 | Second slot from the next beat; branches in it | 397.8 | 0.719 | 1.4309 | 5.50x |
| 0.5.2 | Data-cache-hit loads in the second slot | 388.8 | 0.703 | 1.4640 | 5.63x |
| 0.5.3 | Not-taken branch first; JAL/JALR second; load after a store to another beat | 366.8 | 0.663 | 1.5518 | 5.97x |
| 0.5.4 | Stores in the second slot; ALU results forwarded into it | 335.8 | 0.607 | 1.6951 | 6.52x |
| 0.5.5 | Branch folding: a jump or taken branch and its target instruction in one clock | 287.8 | 0.520 | 1.9777 | 7.60x |
| 0.6.0, `rv64imb` build | B extension (Zba, Zbb, Zbs); 550 instructions per run | 285.8 | 0.520 | 1.9916 | 7.66x |
| 0.7.0, `rv64imb` build | ALU-only third issue slot | 256.8 | 0.467 | 2.2163 | 8.52x |
| 0.7.1, `rv64imb` build | Registered multiplier (two clocks); this build does not multiply at run time | 256.8 | 0.467 | 2.2163 | 8.52x |

Rows from 0.4.0 to 0.5.5 are the `rv64im` build with the reference runtime. At 0.7.1 the `rv64im` build runs 261.8 clocks per run (258.8 at 0.7.0: its multiplies take a clock more) and `rv64i` 273.9. With the labelled fast runtime (word-at-a-time `strcpy`/`strcmp`, 470 instead of 553 instructions per run) the same 0.5.x cores run 360.8, 348.9, 310.9, 269.9 and 251.9 clocks per run from 0.5.1 to 0.5.5; 0.5.5 reaches 2.2598 DMIPS/MHz. Fast-runtime results are not compared with reference-runtime results.

Up to 0.4.0 every measured result matched the profile's estimate. From 0.5.0 each step was chosen from a measured count of why instructions issued alone.

**Caution about the 0.5.x gains.** Dual issue, forwarding and branch folding do more work in each clock: two ALUs in a chain, or a branch decision followed by an instruction-cache read and a second instruction. That lengthens the clock. DMIPS/MHz counts clocks, so it improves even when the clock gets slower; only synthesis on a real part shows whether the design still runs fast. A logic-depth measurement with Yosys is the next check, and wider designs wait for it. The caches assume Dhrystone's code and data fit in 4 KiB each and that memory answers in one clock; a slow-memory model, still a to-do, would show how much of the gain survives on board DRAM.

The table above is the multicycle core. The full records are [dhrystone-results.json](dhrystone-results.json) (`rv64i`) and [dhrystone-rv64im-results.json](dhrystone-rv64im-results.json); the `-rv64imb`, `-fastrt`, `-pipe` and `-ooo` files beside them hold the corresponding builds, each as of the run last recorded with `-Record`. DMIPS per MHz is runs x 1,000,000 / (clocks x 1,757); 1,757 Dhrystones per second is the VAX 11/780 reference.

Scope: ISA as built, ABI `lp64`, bare metal with the laboratory terminal trap, multicycle core with the RTL hashes given in each record, 64 KiB synchronous RAM, Icarus Verilog 12.0, no FPGA, no synthesis. The caches and early-issue logic have not been checked for timing; they may lower the achievable clock frequency.

## Later cores: pipelined and out-of-order (logged runs)

From 0.8.0 the same benchmark also runs on the pipelined core (`rv64_pipe.sv`) and from 0.9.0 on the out-of-order core (`rv64_ooo.sv`), both built for `rv64imb` (`rv64im_zba_zbb_zbs_zifencei`) with clang 23.1.5 `-O2`, 64 KiB RAM and 4 KiB caches, as above. The rows are the last logged run of each listed version, copied from the run index in [DEVLOG.md](../DEVLOG.md#run-logs), which links each run's full record; versions in between are in that index.

| Version | Core | Reference runtime: clocks per run | DMIPS/MHz | Fast runtime: clocks per run | DMIPS/MHz |
|---|---|---:|---:|---:|---:|
| 0.8.0 | pipelined | 588.6 | 0.9670 | 484.6 | 1.1744 |
| 0.9.0 | out-of-order | 721.6 | 0.7888 | 611.6 | 0.9306 |
| 0.10.0 | out-of-order | 131.9 | 4.3161 | 147.9 | 3.8484 |
| 0.11.2 | out-of-order | 76.2 | 7.4686 | 62.3 | 9.1333 |
| 0.12.0 | out-of-order | 57.5 | 9.8986 | 44.5 | 12.7790 |
| 0.13.0 | out-of-order | 41.6 | 13.6809 | 32.5 | 17.5285 |
| 0.14.1 | out-of-order | 31.4 | 18.1212 | 20.7 | 27.4396 |
| 0.15.1 | out-of-order | 31.3 | 18.1745 | 20.3 | 27.9792 |

After 0.15.1 no logged Dhrystone run was made; each release instead reports the 500-run timing probe in the [architecture history](architecture.md#history) (0.17.4: 15,706 clocks reference, 10,127 fast runtime, within 0.5% of the 0.15.1 run). From 0.10.0 the out-of-order core is wider and more speculative in every release; the DMIPS/MHz figures count clocks of an unsynthesized model and say nothing about the clock rate it could reach (see the caution above). Fast-runtime figures stay separate from reference-runtime ones.

## What the number depends on

- **The compiler.** On the 0.1.0 core the same source scored 0.260 DMIPS/MHz with clang 23.1.5, 0.249 with clang 21.1.6 and 0.217 with clang 18.1.3. Compare only results built with the same compiler and flags.
- **The ISA used to build it.** The `rv64im` build replaces the software divide in [runtime.c](../sim/cpu/bench/runtime.c) with one `divw` instruction. Dhrystone never multiplies at run time; the compiler uses shifts.
- **Memory.** The simulated RAM answers reads one clock after the request and writes in the same clock, and both caches hold the whole benchmark. Real board memory would be slower.

## What the first profile showed (architecture 0.1.0)

This analysis drove the first optimizations; it describes the original core.

| Finding | Value |
|---|---:|
| Clocks spent fetching instructions | 54.8% |
| Instructions inside `strcpy` and `strcmp` (byte at a time) | 281 of 600 (47%) |
| Clocks inside software divide (`__divdi3`, one call) | 4.9% |
| Instructions in the same 8-byte fetch beat as the one before | 241 (40%) |

Every run now profiles its instruction stream ([bench_profile.py](../sim/cpu/bench/bench_profile.py)) from clocks measured on the core: FETCH, EXECUTE and MEMORY clocks per instruction, by class, function and address, with instruction-cache replay and what-if estimates. Word-at-a-time `strcpy` and `strcmp` would cut many instructions, but that changes the runtime, so results built with a different runtime would not be comparable.

## How the run is checked

1. **Results.** After the timed loop, the port layer copies Dhrystone's final global values into a mailbox. The runner checks all 17 against the values Dhrystone itself says they should be, including `Arr_2_Glob[8][7]` = runs + 10. The program's local variables are not reachable and are not checked.
2. **Instruction trace.** The same image runs on the trace testbench with 0 and up to 7 random memory wait cycles. Every retirement, write and trap event (347,135 for the `rv64i` build) must match the project's sequential reference model.
3. **Counts agree.** The timing run and the traced runs must retire the same number of instructions overall and inside the timed region.

The reference model is project-written, so this is not independent verification. Lockstep comparison with Spike or Sail is still a to-do.

## How it is timed

The core has no cycle counter yet. Dhrystone's `setStats(1)` and `setStats(0)` hooks, called just before and after the timed loop, write 1 and then 2 to a marker word. The testbench counts clocks and retired instructions between those two writes. The region includes the start-marker store and Dhrystone's own two timer reads, and excludes the stop-marker store.

Dhrystone's built-in timer is given a counter that returns 1, 2, 3, so the program runs its loop exactly once; the time it prints goes to an empty `printf` and means nothing.

## Build rules followed

Dhrystone's ground rules are separate compilation, no merging of procedures and stated optimization. Each file is compiled separately and linked without link-time optimization. Upstream asks for no inlining through a GCC pragma that clang ignores, so the upstream files are compiled with `-fno-inline`. The 1988-era K&R C is compiled as `-std=gnu89`. The port layer and runtime are compiled with `-Wall -Wextra -Werror`.

## Files

| File | Purpose |
|---|---|
| [vendor/dhrystone/](../sim/cpu/bench/vendor/dhrystone/SOURCE.txt) | riscv-tests Dhrystone, byte-identical to upstream commit `3df703c`, BSD-3-Clause |
| [dhrystone_port.c](../sim/cpu/bench/dhrystone_port.c) | Timer hooks, markers and result capture |
| [runtime.c](../sim/cpu/bench/runtime.c) | `memcpy`, `memset`, `strcpy`, `strcmp`, empty `printf`, software multiply and divide |
| [include/](../sim/cpu/bench/include/bench.h) | Minimal headers replacing the C library and riscv-tests' `util.h` |
| [start.S](../sim/cpu/bench/start.S) | Stack setup, `.bss` clearing, call `main`, `ebreak` |
| [build_bench.py](../sim/cpu/bench/build_bench.py) | Compiles, links with a generated linker script for the chosen RAM size, writes images |
| [tb_bench.sv](../sim/cpu/bench/tb_bench.sv) | Core plus RAM wrapper; counts the marked region |
| [run_bench.py](../sim/cpu/bench/run_bench.py) | Timing run, result checks, differential traces, report |
| [rubric_score.py](../sim/cpu/bench/rubric_score.py) | Rubric scorecard from [rubric-evidence.json](rubric-evidence.json) plus the run |
| [bench_profile.py](../sim/cpu/bench/bench_profile.py) | Trace profile: clocks by class and function, hot instructions, what-if estimates |
| [runlog.py](../sim/cpu/bench/runlog.py) | Per-commit run logs in `devlog/` and the run index in DEVLOG.md |
| [run_dhrystone.ps1](../sim/cpu/bench/run_dhrystone.ps1) | Windows launcher: LLVM build, then the run in Ubuntu/WSL |

The benchmark needs about 15.4 KiB (15,728 bytes, `program_end` in the `rv64i` build's `build.json`) for code, data and arrays, more than the 16 KiB layout leaves after the stack, so it uses 64 KiB of RAM. The RTL is unchanged: `RAM_WORDS` in the RAM wrapper and a new `MEM_BYTES` parameter in the trace testbench set the size. The main regression keeps 16 KiB because its unmapped-address tests rely on that boundary.

Memory layout for 64 KiB: program from address 0, stack growing down from `0xff00`, mailbox in the top 256 bytes at `0xff00`. The build fails if the program would leave less than 8 KiB of stack.

## Run it

From the repository root in PowerShell, with the installed LLVM and Ubuntu WSL tools:

```powershell
.\sim\cpu\bench\run_dhrystone.ps1
```

Add `-Isa rv64im_zifencei` to build with the M extension (architecture 0.4.0 or later; the build goes to `build/cpu/bench/dhrystone-rv64im/`) or `-Isa rv64im_zba_zbb_zbs_zifencei` for M and B (`dhrystone-rv64imb`). `-Core pipe` or `-Core ooo` runs the pipelined or out-of-order core (folder suffix `-pipe` or `-ooo`), `-Runtime fast` the labelled fast runtime (`-fastrt`) and `-Sim verilator` the faster simulator. Every run writes its result, rubric scorecard and trace profile to `devlog/devlog-<commit>.md` and adds a row to the run index in [DEVLOG.md](../DEVLOG.md); add `-NoDevlog` for a throwaway run. The profile is also saved as `build/cpu/bench/dhrystone/profile.md`. Add `-Record` to overwrite [dhrystone-results.json](dhrystone-results.json), or `-RamKiB 128` for a larger memory. A run takes about a minute; most of it is the two traced runs.

On Linux with clang, lld, LLVM tools, Icarus and Python 3.11+:

```sh
python3 -B sim/cpu/bench/build_bench.py
python3 -B sim/cpu/bench/run_bench.py
```

Generated files go under ignored `build/cpu/bench/dhrystone/`: object files, `bench.elf`, disassembly, symbol map, both memory images, traces and `results.json`. The runner refuses a build whose sources or artifacts changed after building.

### Verilator (optional)

`run_bench.py --sim verilator` (or `run_dhrystone.ps1 -Sim verilator`) builds and runs the same testbenches with Verilator instead of Icarus Verilog; `sim/cpu/test_cpu.py --sim verilator` does the same for the regression. The out-of-order timing run takes under a second instead of 1.5-2 minutes (a whole runner call, with builds and the reference model, about 20-40 s), and the region clocks, mailbox and traces match Icarus exactly. The helper [simulator.py](../sim/cpu/simulator.py) finds Verilator through `VERILATOR_ROOT`, `PATH` or an unpacked copy in `build/third-party/verilator/root`, uses clang++ with C++20 flags when g++ is absent, and caches each build under `build/sim-cache/verilator/`. Results record `simulator_name` and the `verilator --version` string. Verilator is a 2-state simulator: registers and memories start at 0, where Icarus starts them at X, so a bug that depends on reset values can pass under Verilator. Icarus stays the default and the cross-check, and logged runs use it unless `--sim verilator` is given.
