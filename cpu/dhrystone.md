# Dhrystone on our custom CPU

**First benchmark result, November 20, 2026: 0.260 DMIPS/MHz.** That is 2,188 clocks per Dhrystone run at 3.65 clocks per instruction. It comes from a simulation run of the unchanged RV64I core with its synchronous RAM, so it is a non-compliant run under the [review rubric](review-rubric.md), evidence class E1. It does not support calling the core performant.

Dhrystone is the secondary benchmark in the rubric. Report it next to CoreMark once that runs, never on its own.

## Result

| Measurement | Value |
|---|---:|
| Dhrystone runs in the timed region | 500 |
| Clocks in the timed region | 1,094,103 |
| Instructions retired in the timed region | 300,029 |
| Clocks per run | 2,188.2 |
| Instructions per run | 600.1 |
| Clocks per instruction | 3.647 |
| **DMIPS per MHz** | **0.2601** |
| Whole program, including startup and result capture | 1,120,105 clocks, 307,336 instructions |

DMIPS per MHz is runs x 1,000,000 / (clocks x 1,757); 1,757 Dhrystones per second is the VAX 11/780 reference. The full record, including the compiler commands, every check and source hashes, is [dhrystone-results.json](dhrystone-results.json).

Scope: `rv64i_zifencei`, ABI `lp64`, bare metal with the laboratory terminal trap, multicycle core with the RTL hashes given in the record, 64 KiB synchronous RAM with no added wait cycles, Icarus Verilog 12.0, no FPGA. Compiler: clang 23.1.5 at `-O2`.

## What the number depends on

- **Software multiply and divide.** The core has no M extension, so each run calls the shift-and-add and shift-subtract routines in [runtime.c](../sim/cpu/bench/runtime.c). Their cost is inside the result.
- **The compiler.** The same source built with Ubuntu's clang 18.1.3 scores 0.217 DMIPS/MHz (2,622 clocks per run). Always compare results built with the same compiler and flags.
- **Memory latency.** The RAM answers every request one clock after it is made. Each instruction fetch therefore takes 2 clocks and execution 1, so most instructions take 3 clocks and loads and stores take 5. That explains the 3.65 average.

## How the run is checked

1. **Results.** After the timed loop, the port layer copies Dhrystone's final global values into a mailbox. The runner checks all 17 against the values Dhrystone itself says they should be, including `Arr_2_Glob[8][7]` = runs + 10. The program's local variables are not reachable and are not checked.
2. **Instruction trace.** The same image runs on the trace testbench with 0 and up to 7 random memory wait cycles. All 347,135 retirement, write and trap events must match the project's sequential reference model.
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
| [run_dhrystone.ps1](../sim/cpu/bench/run_dhrystone.ps1) | Windows launcher: LLVM build, then the run in Ubuntu/WSL |

The benchmark needs about 15.7 KB for code, data and arrays, more than the 16 KiB layout leaves after the stack, so it uses 64 KiB of RAM. The RTL is unchanged: `RAM_WORDS` in the RAM wrapper and a new `MEM_BYTES` parameter in the trace testbench set the size. The main regression keeps 16 KiB because its unmapped-address tests rely on that boundary.

Memory layout for 64 KiB: program from address 0, stack growing down from `0xff00`, mailbox in the top 256 bytes at `0xff00`. The build fails if the program would leave less than 8 KiB of stack.

## Run it

From the repository root in PowerShell, with the installed LLVM and Ubuntu WSL tools:

```powershell
.\sim\cpu\bench\run_dhrystone.ps1
```

Add `-Record` to overwrite [dhrystone-results.json](dhrystone-results.json), or `-RamKiB 128` for a larger memory. A run takes about a minute; most of it is the two traced runs.

On Linux with clang, lld, LLVM tools, Icarus and Python 3.11+:

```sh
python3 -B sim/cpu/bench/build_bench.py
python3 -B sim/cpu/bench/run_bench.py
```

Generated files go under ignored `build/cpu/bench/dhrystone/`: object files, `bench.elf`, disassembly, symbol map, both memory images, traces and `results.json`. The runner refuses a build whose sources or artifacts changed after building.
