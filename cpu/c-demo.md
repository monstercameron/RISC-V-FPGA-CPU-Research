# C running on our custom CPU

**Passed on October 23, 2026.** The [C program](../sim/cpu/c_demo.c) compiled into a 768-byte RISC-V firmware image and ran on the original SystemVerilog core with its 16 KiB synchronous RAM wrapper. All eight result words matched independent expected values. The complete instruction, memory-write and terminal-trap trace also matched the project's sequential interpreter.

## What it does

| Work | Observed result | Independent check |
|---|---|---|
| Insertion-sort 16 signed numbers | Sorted fingerprint `0x87101f1288184441` | Python `sorted()` plus fingerprint |
| Sum, minimum and maximum | `1242`, `-300`, `1024` | Python integer operations |
| Fibonacci, term 40 | `102334155` | Python recurrence |
| CRC32 over 344 bytes | `0x97f65c54` | Python standard-library `zlib.crc32()` |
| Completion and internal status | `CPUDEMO1`, status `0` | Mailbox and return-register checks |

The numbers, message and Fibonacci iteration count are volatile inputs, so the compiler cannot substitute precomputed answers. The program uses integer additions, shifts, comparisons, branches, loads and stores. It needs no OS, libc, floating-point unit, multiply instruction or FPGA board.

## The pipeline, in plain language

1. **C source:** describes sorting, Fibonacci and CRC32.
2. **LLVM compiler/linker:** translates it into 64-bit RISC-V machine instructions, adds the tiny stack/startup routine and assigns addresses. The target is `rv64i_zifencei`, ABI `lp64`, optimization `-O1`.
3. **RAM image:** converts the executable into a binary and then 2,048 little-endian 64-bit hex words for the simulated RAM.
4. **Icarus/vvp:** simulates the actual CPU and RAM RTL. The CPU fetches and executes the compiled instructions, writes its answers at address `0x3000`, returns from `main`, and stops on the startup routine's `EBREAK`.
5. **Checker:** reads those answers and compares them with independently calculated results. A separate run compares every retired instruction and memory write against the project's software interpreter.

There is no `printf` or terminal driver on this bare-metal CPU yet. The Python test runner prints the results that it reads from the simulated RAM.

## Is the simulator heavy?

For this small CPU, **memory use is light and the turnaround is short**. Measurements on this workstation using Icarus 12.0 in Ubuntu 24.04/WSL2 on ARM64:

| Measurement | Result |
|---|---:|
| Firmware instructions retired | 22,674 |
| CPU/RAM clock cycles after reset | 69,157 |
| Median simulation wall time, five runs | 1.360 seconds |
| Range of measured wall times | 1.068–1.448 seconds |
| Maximum vvp peak resident memory across five runs | 7.24 MiB |
| C compilation, linking and image creation in this run | 1.479 seconds |
| RTL compilation in this run | 0.373 seconds |
| Differential events compared | 22,765, all matching |
| Separate retirement trace file | 1,477,373 bytes |

The simulation timing includes process launch, the GNU `time` wrapper and image loading. It excludes WSL startup, both compilation steps, and the separate differential verification run. The memory figure is for the `vvp` process, **not the whole WSL virtual machine, editor or Windows**. No waveform dumping was enabled for these measurements. The one-command launcher runs five measurements plus a separate trace check, so its total duration exceeds a single simulation's time.

RTL simulation models circuit activity; it is much slower than executing the C program natively. Longer workloads and larger designs can therefore take much longer. Waveform recording also creates additional output. This current demo does not need a GPU. The measured clock-cycle count is a simulation result, not a proven FPGA clock frequency or physical-board speed.

## Run it again

From the project root in PowerShell, with the installed LLVM and Ubuntu WSL tools:

```powershell
.\sim\cpu\run_c_demo.ps1
```

For one measured execution instead of five:

```powershell
.\sim\cpu\run_c_demo.ps1 -Repetitions 1
```

The [launcher](../sim/cpu/run_c_demo.ps1) builds the C firmware before calling the [RTL runner](../sim/cpu/run_c_demo.py). Both commands still perform the separate trace comparison. Tool paths and WSL distribution can be overridden with `-LLVMDirectory` and `-Distribution`.

On Linux with RISC-V-capable Clang/LLD, `llvm-objcopy`, Icarus, Python and GNU `time` already installed:

```sh
python3 -B sim/cpu/build_firmware.py --source sim/cpu/c_demo.c --out-dir build/cpu/c-demo
python3 -B sim/cpu/run_c_demo.py
```

An optional `--objdump` argument to the builder writes a readable assembly listing. Generated artifacts stay under ignored `build/cpu/c-demo/`: `firmware.elf`, `firmware.bin`, `firmware-bram.hex`, `firmware.disasm.txt` when objdump is available, `build.json`, simulator executables, trace, timings and `results.json`. The runner rejects firmware whose recorded source or artifact hashes no longer match. Rebuild after editing the C source.

The [recorded result and measurements](c-demo-results.json) include all five raw samples, exact compiler flags and source/binary SHA-256 identities. They describe the checked source snapshot; reruns write fresh results into `build/`.

## What this proves

Our existing RV64I/FENCE.I execution core can run this compiled, independently checked C workload through the memory wrapper. The extra trace check uses the project's own sequential interpreter and zero injected wait cycles; the earlier general regression covers multiple memory wait patterns. See the [broader verification record](verification.json).

This adds software evidence for the current core. Full RVA23, privileged traps/interrupts, Linux boot, official architectural certification, synthesis and physical FPGA timing remain later milestones in the [architecture plan](architecture.md).
