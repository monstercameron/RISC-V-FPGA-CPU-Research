# CPU first: an FPGA RISC-V core

The active project priority is now a custom CPU. The long-term application ISA target is **RVA23U64**; the first implemented milestone is a small **RV64I execution core with FENCE.I and a terminal laboratory trap interface**. It is not yet an RVA23 implementation, a privileged-architecture implementation, or a Linux CPU.

Start with the [interactive core infographic](core-explainer.html), then read the [architecture and stages](architecture.md). The previous LLM accelerator work remains available as research and a future workload. Its earlier review score and LUT estimates do not qualify this CPU.

For a complete C-to-CPU example, see [the C demo and measured simulator cost](c-demo.md). Run `.\sim\cpu\run_c_demo.ps1` to compile sorting, Fibonacci and CRC32 into RISC-V instructions, execute them on the RTL and validate the results.

To watch that program execute and run the simulator from your browser, use the [connected CPU visualizer](visualizer.md): `.\sim\cpu\run_visualizer.ps1`. It connects the Run simulation button to LLVM/Icarus, then lets you step or replay the resulting hardware clocks and inspect the actual output mailbox.

For the smallest example, select **1 + 1** in the viewer. The [addition walkthrough](addition.md) shows its C, actual compiled assembly, every instruction's binary encoding, and the observed result **2**. The viewer also has a Binary tab and displays the current instruction's bits beside the hardware.

For a guided progression, use the [seven study programs](programs.md): addition, decisions, loops, arrays, recursive calls, sorting, and the combined demo. Select a lesson to load its saved run, reveal explanations, and jump to observed hardware events.

To change the examples, use the [editable Program inputs panel](inputs.md). The viewer distinguishes your draft inputs from those used in the displayed capture, then compiles and checks a fresh run when you submit them.

## What exists

The current architecture version is in [VERSION](VERSION). The [architecture document](architecture.md), section 9, gives the versioning rules and history.

- Original [SystemVerilog CPU](../rtl/cpu/rv64_core.sv): 32 x 64-bit integer registers, RV64 integer ALU and word operations, branches/jumps, byte/halfword/word/doubleword memory operations, serialized fences, exact terminal fault records, retirement tracing.
- Original [16 KiB synchronous RAM wrapper](../rtl/cpu/rv64_bram_soc.sv), independent of board pins or vendor IP. RAM contents are initialized from a 64-bit-word hex image; no RAM bulk reset.
- [Simulation suite](../sim/cpu/test_cpu.py) and [sequential software reference](../sim/cpu/reference.py): 32 generated programs under three memory wait patterns; an optional compiled C program adds a 33rd. All 53 implemented instruction names are exercised. This is local verification, not official certification.
- Dedicated reset-during-stalled-store test; synchronous RAM wrapper tests; an LLVM-built C program computes 1+...+8=36 and writes a second bit-manipulation signature.

The source files use only original MIT-licensed code. The older PicoRV32 example remains a separate, attributed third-party reference.

## Run for free

From the repository root on the existing Windows workstation:

```powershell
.\sim\cpu\run.ps1
```

Or inside Ubuntu/WSL with Python 3.11+, Icarus and vvp:

```sh
bash sim/cpu/run.sh
```

No compiler or FPGA is needed for the generated tests. Output is under ignored `build/cpu/`, including retirement traces and `verification.json`. The default suite runs 96 differential simulations plus the reset and RAM-wrapper checks. The recorded expanded run includes compiled firmware: **99 differential simulations plus reset and two RAM-wrapper checks, all passing**.

To build and test the small C firmware using installed LLVM:

```powershell
python -B sim/cpu/build_firmware.py --clang "C:\Program Files\LLVM\bin\clang.exe" --objcopy "C:\Program Files\LLVM\bin\llvm-objcopy.exe"
```

Then in Ubuntu, from the same repository:

```sh
python3 -B sim/cpu/test_cpu.py --image build/cpu/firmware/firmware.bin
```

The compiler target is `rv64i_zifencei`, ABI `lp64`. Do not compile software for `rva23u64` and expect this first core to run it. Existing FP/vector examples in `isa/` target later milestones.

## Immediate next milestone

Add contained machine-mode traps, the selected privileged CSR set, `mret`, timer/external interrupts and a trap-handler firmware test. Preserve the retirement boundary and single-request memory contract. Then compare against an external established ISA model and run relevant architectural tests before broadening ISA support.

The first benchmark, [Dhrystone](dhrystone.md), runs unmodified on the core in simulation at 0.260 DMIPS/MHz with software multiply and divide. Run `.\sim\cpu\bench\run_dhrystone.ps1`.

Reviews use the [CPU review rubric](review-rubric.md) to decide whether the core may be called good or performant. Neither claim is available yet.

Synthesis, place-and-route timing, exact LUT/BRAM/DSP counts, board constraints and physical FPGA operation remain unverified. The next hardware decision follows a small exact-part synthesis experiment; no purchase is required to continue simulation.
