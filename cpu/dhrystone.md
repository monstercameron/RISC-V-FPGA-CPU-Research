# Dhrystone on our custom CPU

**Current result, architecture 0.4.0: 1.024 DMIPS/MHz** built for `rv64im_zifencei`, and 0.947 DMIPS/MHz built for `rv64i_zifencei`. The first 0.1.0 core scored 0.260. All are simulation runs of the core with its synchronous RAM, so they are non-compliant runs under the [review rubric](review-rubric.md), evidence class E1, and do not support calling the core performant.

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

Every measured result matched the estimate the profile made before the change.

**Where it stopped.** On 0.4.0 the core completes almost exactly one instruction per clock: 2.6 of 555.7 clocks per run are not instruction execution (two divide steps, 0.6 fetch, 0.1 memory). Going lower needs fewer instructions, which is a compiler or runtime change rather than a core change, or more than one instruction per clock, which is a superscalar redesign rather than a refinement. The caches assume Dhrystone's code and data fit in 4 KiB each and that memory answers in one clock; a slow-memory model, still a to-do, would show how much of the gain survives on board DRAM.

The full records are [dhrystone-results.json](dhrystone-results.json) (`rv64i`) and [dhrystone-rv64im-results.json](dhrystone-rv64im-results.json). DMIPS per MHz is runs x 1,000,000 / (clocks x 1,757); 1,757 Dhrystones per second is the VAX 11/780 reference.

Scope: ISA as built, ABI `lp64`, bare metal with the laboratory terminal trap, multicycle core with the RTL hashes given in each record, 64 KiB synchronous RAM, Icarus Verilog 12.0, no FPGA, no synthesis. The caches and early-issue logic have not been checked for timing; they may lower the achievable clock frequency.

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

The benchmark needs about 15.7 KB for code, data and arrays, more than the 16 KiB layout leaves after the stack, so it uses 64 KiB of RAM. The RTL is unchanged: `RAM_WORDS` in the RAM wrapper and a new `MEM_BYTES` parameter in the trace testbench set the size. The main regression keeps 16 KiB because its unmapped-address tests rely on that boundary.

Memory layout for 64 KiB: program from address 0, stack growing down from `0xff00`, mailbox in the top 256 bytes at `0xff00`. The build fails if the program would leave less than 8 KiB of stack.

## Run it

From the repository root in PowerShell, with the installed LLVM and Ubuntu WSL tools:

```powershell
.\sim\cpu\bench\run_dhrystone.ps1
```

Add `-Isa rv64im_zifencei` to build with the M extension (architecture 0.4.0 or later); that build goes to `build/cpu/bench/dhrystone-rv64im/`. Every run writes its result, rubric scorecard and trace profile to `devlog/devlog-<commit>.md` and adds a row to the run index in [DEVLOG.md](../DEVLOG.md); add `-NoDevlog` for a throwaway run. The profile is also saved as `build/cpu/bench/dhrystone/profile.md`. Add `-Record` to overwrite [dhrystone-results.json](dhrystone-results.json), or `-RamKiB 128` for a larger memory. A run takes about a minute; most of it is the two traced runs.

On Linux with clang, lld, LLVM tools, Icarus and Python 3.11+:

```sh
python3 -B sim/cpu/bench/build_bench.py
python3 -B sim/cpu/bench/run_bench.py
```

Generated files go under ignored `build/cpu/bench/dhrystone/`: object files, `bench.elf`, disassembly, symbol map, both memory images, traces and `results.json`. The runner refuses a build whose sources or artifacts changed after building.
