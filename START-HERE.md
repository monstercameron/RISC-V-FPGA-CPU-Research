# Start here: free RISC-V CPU simulation

## What is ready

This project starts with a real Verilog CPU simulated on your computer: PicoRV32, configured for its default RV32I base. The included testbench runs five machine-code instructions, checks that 5 + 7 is stored as 12 at address 0x100, and stops on EBREAK. It produces a waveform and a PASS/FAIL result. No FPGA, paid license, cross compiler, or online account is needed for this first experiment.

The CPU is third-party reference RTL, not our custom implementation. Its purpose is to establish the memory interface and simulation workflow before writing our own core. One passing smoke test verifies this example, not the complete ISA. The testbench supports only aligned word accesses within its 1 KiB RAM; it must be expanded before testing byte/halfword operations or general firmware.

## Tools

- Ubuntu 24.04 under WSL2: already present on this workstation.
- Icarus Verilog: compiles the RTL; vvp executes the simulation.
- Optional GTKWave: opens the generated VCD waveform. Install later with `sudo apt install gtkwave`; GUI use requires working WSLg.
- Any existing text editor: edit the Verilog files.

No synthesis tools are required yet. Verilator, cocotb, compiler tools, and formal verification can be added when they solve a concrete next-step need.

## Run from Windows

In PowerShell, change into this document's folder and run:

```powershell
.\run.ps1
```

Or open Ubuntu, change to the project's `sim/starter` directory, and run:

```bash
bash run.sh
```

If setting up a different Ubuntu installation:

```bash
sudo apt update
sudo apt install iverilog
```

The expected output includes:

```text
STORE address=0x00000100 data=12
PASS: simulated RISC-V CPU computed 5 + 7 = 12 (... cycles)
```

Outputs are `build/cpu.vcd` and `build/simulation.log`. With GTKWave installed, run `gtkwave build/cpu.vcd` from Ubuntu. Start by examining resetn, mem_valid, mem_ready, mem_addr, mem_wdata, mem_wstrb, and trap.

## Files

- `vendor/picorv32.v`: pinned upstream reference CPU; keep original license header.
- `vendor/COPYING`: upstream ISC license.
- `tb_cpu.v`: clock/reset, RAM, five-instruction program, timeout, result check.
- `run.sh`: compile and simulate in Ubuntu.
- `run.ps1`: Windows launcher using the installed Ubuntu distribution.
- `SOURCE.txt`: exact upstream commit and download information.

## First experiments and next milestones

1. Run unchanged and confirm PASS.
2. Change the first ADDI immediate from 5 to 9 (`00500093` to `00900093`), and update the expected result from 12 to 16. Rerun and inspect the store transaction.
3. Change only the expected result to an incorrect value. Confirm the check fails, then restore the file.
4. Write our custom register file, immediate decoder, and ALU in `rtl/`, with small directed simulations.
5. Build a multicycle custom RV32I core and adapt this harness to its memory interface. Use a valid/ready protocol that supports synchronous memory latency.
6. Add directed assembly programs, retirement traces, load/store lane checks, branches, traps, and stalled memory responses. Add a GNU bare-metal compiler when hand encoding becomes inconvenient.
7. Expand toward all declared RV32I semantics and compare with a reference model. Choose the FPGA after initial synthesis provides resource evidence.

RVA23 is a much larger 64-bit application-profile target. This RV32I exercise establishes the workflow; it does not implement or claim RVA23 compatibility. The long-term architecture choice remains open.

## Primary sources

- Icarus workflow: https://steveicarus.github.io/iverilog/usage/getting_started.html
- Icarus simulation documentation: https://steveicarus.github.io/iverilog/usage/simulation.html
- PicoRV32 source and configuration: https://github.com/YosysHQ/picorv32
- RV32I specification: https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html

Prepared October 23, 2026. PicoRV32 upstream is archived; pinning its source makes this reference exercise reproducible.
