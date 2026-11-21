# Development log for commit `04b19db`

Commit subject: Profile every Dhrystone run and split run logs by commit

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-20 21:27:12 -0500

- **Architecture:** version 0.1.0
- **Commit:** `04b19db`, uncommitted changes: yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM
- **RTL:** `rv64_core.sv` 831101d3f376, `rv64_bram_soc.sv` a38d2ca4a051
- **Result:** 2,188.2 clocks per run, 600.1 instructions per run, CPI 3.647, **0.2601 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.00% clocks per run against the previous run with the same build settings (2026-11-20 21:21:17 -0500, `35565c0`, architecture 0.1.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `3110337` for architecture 0.1.0. Automated self-assessment, not a review.

| Dimension | Points | Of | Score |
|---|---:|---:|---:|
| R1 Architectural correctness | 13.5 | 25 | 54% |
| R2 Traps, interrupts, privilege and reset | 6.2 | 10 | 62% |
| R3 Verification depth and independence | 3.8 | 15 | 25% |
| R4 Performance | 4.4 | 20 | 22% |
| R5 FPGA implementation quality | 0.0 | 12 | 0% |
| R6 Interfaces and integration | 4.3 | 8 | 54% |
| R7 Observability and debug | 1.7 | 4 | 42% |
| R8 Design quality and maintainability | 1.3 | 3 | 44% |
| R9 Reproducibility and claim hygiene | 1.9 | 3 | 62% |
| **Total** | **37.1** | **100** | **foundation** |

- **Gates met:** HG2, HG4, HG5, PG4. **Not met:** HG1, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG6; R1 54% < 60%; R3 25% < 50%.
- **"Good":** not granted: HG1; HG3; HG6; HG7; HG8; total 37.1 < 75; R1 54% < 80%; an R1 criterion under 3; R2 62% < 70%; R3 25% < 70%; R6 54% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 22% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 3.647 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 3; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 96 runs, 53 instruction names.)

| Criterion | Score |
|---|---:|
| R1.1 | 2 |
| R1.2 | 2 |
| R1.3 | 2 |
| R1.4 | 3 |
| R1.5 | 2 |
| R1.6 | 2 |
| R2.1 | 3 |
| R2.2 | N/A |
| R2.3 | N/A |
| R2.4 | N/A |
| R2.5 | 2 |
| R2.6 | N/A |
| R3.1 | 1 |
| R3.2 | 2 |
| R3.3 | 0 |
| R3.4 | 1 |
| R3.5 | 0 |
| R3.6 | 0 |
| R3.7 | 3 |
| R4.1 | 2 |
| R4.2 | 0 |
| R4.3 | 0 |
| R4.4 | 0 |
| R4.5 | 2 |
| R4.6 | 1 |
| R4.7 | 0 |
| R4.8 | 2 |
| R5.1 | 0 |
| R5.2 | 0 |
| R5.3 | 0 |
| R5.4 | 0 |
| R5.5 | 0 |
| R5.6 | 0 |
| R5.7 | 0 |
| R6.1 | 3 |
| R6.2 | 2 |
| R6.3 | 3 |
| R6.4 | 1 |
| R6.5 | 2 |
| R6.6 | 2 |
| R7.1 | 2 |
| R7.2 | 3 |
| R7.3 | N/A |
| R7.4 | 0 |
| R8.1 | 1 |
| R8.2 | 2 |
| R8.3 | 2 |
| R8.4 | 2 |
| R9.1 | 3 |
| R9.2 | 4 |
| R9.3 | 2 |
| R9.4 | 1 |

### Profile of the timed region

Source: the zero-wait differential trace, 300,029 retired instructions over 500 runs. Clock model: fetch 2, execute 1, load or store +2.

| Model check | Model | Measured | Difference |
|---|---:|---:|---:|
| Timed region, core + synchronous RAM | 1,094,103 | 1,094,103 | +0 |
| Whole program, core + synchronous RAM | 1,120,102 | 1,120,105 | +3 |
| Whole program, trace testbench (1-clock memory) | 713,719 | 713,722 | +3 |

The whole-program differences are the final `ebreak`, which is fetched and executed but never retires.

**Where the clocks go, by instruction class** (per run):

| Class | Instructions | Share | Clocks | Share |
|---|---:|---:|---:|---:|
| alu | 276.0 | 46.0% | 828.1 | 37.8% |
| load | 118.0 | 19.7% | 590.0 | 27.0% |
| branch | 94.0 | 15.7% | 282.0 | 12.9% |
| store | 76.0 | 12.7% | 380.1 | 17.4% |
| jump | 36.0 | 6.0% | 108.0 | 4.9% |
| **total** | **600.1** | | **2,188.2** | |

Fetching instructions takes 1,200.1 clocks per run, 54.8% of all clocks; executing takes 600.1 (27.4%); the extra memory access of loads and stores takes 388.0 (17.7%).

**Where the clocks go, by function** (per run; calls counted at the call instruction):

| Function | Instructions | Share | Clocks | Share | Calls |
|---|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 26.2% | 595.0 | 27.2% | 1.0 |
| `strcmp` | 124.0 | 20.7% | 454.0 | 20.7% | 1.0 |
| `main` | 72.0 | 12.0% | 240.1 | 11.0% | 0.0 |
| `Proc_1` | 53.0 | 8.8% | 229.0 | 10.5% | 1.0 |
| `Proc_8` | 37.0 | 6.2% | 131.0 | 6.0% | 1.0 |
| `__divdi3` | 36.0 | 6.0% | 108.0 | 4.9% | 1.0 |
| `Func_2` | 23.0 | 3.8% | 85.0 | 3.9% | 1.0 |
| `Proc_6` | 23.0 | 3.8% | 85.0 | 3.9% | 1.0 |
| `Proc_7` | 15.0 | 2.5% | 51.0 | 2.3% | 1.0 |
| `Func_1` | 15.0 | 2.5% | 45.0 | 2.1% | 3.0 |
| `Proc_4` | 12.0 | 2.0% | 44.0 | 2.0% | 1.0 |
| `Proc_2` | 12.0 | 2.0% | 44.0 | 2.0% | 1.0 |
| `Proc_3` | 11.0 | 1.8% | 43.0 | 2.0% | 1.0 |
| `Proc_5` | 7.0 | 1.2% | 25.0 | 1.1% | 1.0 |
| `Func_3` | 3.0 | 0.5% | 9.0 | 0.4% | 1.0 |
| `bench_timer` | 0.0 | 0.0% | 0.1 | 0.0% | 0.0 |
| `setStats` | 0.0 | 0.0% | 0.1 | 0.0% | 0.0 |

Software multiply and divide (`__muldi3`, `__divdi3`, `__moddi3`, `__udivdi3`, `__umoddi3`): 36.0 instructions and 108.0 clocks per run (4.9% of clocks), from 1.0 calls per run (`__divdi3` 1.0). String and memory routines: 281.0 instructions per run.

Control flow per run: 62.0 branches taken, 32.0 not taken, 16.0 calls, 16.0 returns.

Loads and stores per run by width: `lbu` 79.0, `ld` 26.0, `lw` 13.0, `sb` 33.0, `sd` 20.0, `sw` 23.0.

Fetch reuse: 241.0 instructions per run (40.2%) were in the same 8-byte fetch beat as the instruction just before them, so a one-entry fetch buffer could serve them without a new memory read.

**Most-executed instructions** (whole region):

| Address | Function | Instruction | Times | Clocks |
|---|---|---|---:|---:|
| `0x0d70` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 77,500 |
| `0x0d74` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 46,500 |
| `0x0d78` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 77,500 |
| `0x0d7c` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 46,500 |
| `0x0d80` | `strcpy` | `bnez a3, 0xd70 <strcpy+0x4>` | 15,500 | 46,500 |
| `0x0d94` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 50,000 |
| `0x0d98` | `strcmp` | `bne a2, a3, 0xdac <strcmp+0x24>` | 10,000 | 30,000 |
| `0x0d9c` | `strcmp` | `lbu a2, 0x0(a0)` | 9,500 | 47,500 |
| `0x0da0` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 28,500 |
| `0x0da4` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 28,500 |
| `0x0da8` | `strcmp` | `bnez a2, 0xd94 <strcmp+0xc>` | 9,500 | 28,500 |
| `0x0ae8` | `Func_1` | `xor a1, a1, a0` | 1,500 | 4,500 |
| `0x0aec` | `Func_1` | `zext.b a1, a1` | 1,500 | 4,500 |
| `0x0af0` | `Func_1` | `beqz a1, 0xafc <Func_1+0x14>` | 1,500 | 4,500 |
| `0x0af4` | `Func_1` | `li a0, 0x0` | 1,500 | 4,500 |

**Instruction mix** (per run): `addi` 184.0, `lbu` 79.0, `bne` 78.0, `jalr` 34.0, `sb` 33.0, `ld` 26.0, `auipc` 24.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `add` 13.0, `slli` 11.0, `beq` 8.0, `andi` 8.0, `sub` 8.0, `xor` 6.0, `and` 4.0, `srli` 4.0, `sltiu` 3.0, `or` 3.0, `bltu` 3.0, `jal` 2.0, `bge` 2.0, `addiw` 2.0, `bgeu` 2.0, `srai` 2.0, `sltu` 2.0, `lui` 1.0, `blt` 1.0, `addw` 1.0.

**What-if estimates** from the same trace (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Current core (model) | 600.1 | 2,188.2 | 3.647 | 0.2601 | 1.00x |
| Reuse the fetched beat, saving 1 clock | 600.1 | 1,947.2 | 3.245 | 0.2923 | 1.12x |
| Reuse the fetched beat, saving 2 clocks | 600.1 | 1,706.2 | 2.843 | 0.3336 | 1.28x |
| Hardware multiply and divide (M) | 564.1 | 2,080.2 | 3.688 | 0.2736 | 1.05x |
| M plus fetch reuse (1 clock) | 564.1 | 1,855.2 | 3.289 | 0.3068 | 1.18x |
| Ideal pipeline, today's instructions | 600.1 | 600.1 | 1.000 | 0.9485 | 3.65x |
| Ideal pipeline with M | 564.1 | 564.1 | 1.000 | 1.0090 | 3.88x |

- *Current core (model):* Per-instruction model of today's core; compare with the measured clocks above.
- *Reuse the fetched beat, saving 1 clock:* A one-entry fetch buffer serves the second instruction of each 8-byte beat with 1 clock of fetch instead of 2.
- *Reuse the fetched beat, saving 2 clocks:* The buffered instruction goes straight to execute with no fetch clock.
- *Hardware multiply and divide (M):* Each helper call becomes one instruction costing the same as an add; the call instruction is replaced by it. Best case: an iterative divider would take more clocks.
- *M plus fetch reuse (1 clock):* Both changes above; fetch reuse counted only for instructions outside the removed helpers.
- *Ideal pipeline, today's instructions:* Every instruction completes in 1 clock on average; no stalls. An upper bound, not a design.
- *Ideal pipeline with M:* Upper bound with hardware multiply and divide.

### Result checks

| Value | Expected | Actual | Pass |
|---|---:|---:|---|
| magic | 5642821575076104260 | 5642821575076104260 | yes |
| number_of_runs | 500 | 500 | yes |
| Int_Glob | 5 | 5 | yes |
| Bool_Glob | 1 | 1 | yes |
| Ch_1_Glob | 65 | 65 | yes |
| Ch_2_Glob | 66 | 66 | yes |
| Arr_1_Glob[8] | 7 | 7 | yes |
| Arr_2_Glob[8][7] | 510 | 510 | yes |
| Ptr_Glob->Discr | 0 | 0 | yes |
| Ptr_Glob->Enum_Comp | 2 | 2 | yes |
| Ptr_Glob->Int_Comp | 17 | 17 | yes |
| Ptr_Glob->Str_Comp matches | 1 | 1 | yes |
| Next_Ptr_Glob->Discr | 0 | 0 | yes |
| Next_Ptr_Glob->Enum_Comp | 1 | 1 | yes |
| Next_Ptr_Glob->Int_Comp | 18 | 18 | yes |
| Next_Ptr_Glob->Str_Comp matches | 1 | 1 | yes |
| Ptr_Comp equal in both records | 1 | 1 | yes |

### Runs and tools

- Timed region: 1,094,103 clocks, 300,029 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 1,120,105 clocks, 307,336 instructions.
- Differential run, up to 0 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=713722`.
- Differential run, up to 7 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=2133797`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 9.2 s, reference model 0.5 s.
- Instructions executed: `add`, `addi`, `addiw`, `addw`, `and`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `or`, `sb`, `sd`, `slli`, `sltiu`, `sltu`, `srai`, `srli`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64i_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone\link.ld .\build\cpu\bench\dhrystone\start.o .\build\cpu\bench\dhrystone\dhrystone_main.o .\build\cpu\bench\dhrystone\dhrystone.o .\build\cpu\bench\dhrystone\dhrystone_port.o .\build\cpu\bench\dhrystone\runtime.o -o .\build\cpu\bench\dhrystone\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-20 21:27:12 -0500","architecture_version":"0.1.0","commit":"04b19db","dirty":"yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"cycles_per_run":2188.206,"cpi":3.6466574897759885,"dmips_per_mhz":0.2600998094211762,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"831101d3f376ed35f96e4549eb0e9cf67fd59ef79bdf025b3ddbf432aebd75d1","rtl/cpu/rv64_bram_soc.sv":"a38d2ca4a05142f1982635fb9824a29b80abc94e31635415d3b341df0c06ae57"}} -->
