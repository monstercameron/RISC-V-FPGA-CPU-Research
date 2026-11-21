# Development log for commit `53c6772`

Commit subject: Keep both cores on main: add the pipelined implementation (architecture 0.8.0)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-21 00:41:58 -0500

- **Architecture:** version 0.8.0
- **Commit:** `53c6772`, uncommitted changes: yes (`cpu/programs-verification.json`, `cpu/visualizer-verification.json`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, pipe core
- **RTL:** `rv64_pipe.sv` da2caf82aff0, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 588.6 clocks per run, 550.1 instructions per run, CPI 1.070, **0.9670 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** first run with these build settings

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.8.0` for architecture 0.8.0. Automated self-assessment, not a review.

**RTL or architecture version changed since the evidence was assessed: hand-scored R1-R6 criteria count as 0 until `cpu/rubric-evidence.json` is reassessed.**

| Dimension | Points | Of | Score |
|---|---:|---:|---:|
| R1 Architectural correctness | 0.0 | 25 | 0% |
| R2 Traps, interrupts, privilege and reset | 0.0 | 10 | 0% |
| R3 Verification depth and independence | 0.0 | 15 | 0% |
| R4 Performance | 1.2 | 20 | 6% |
| R5 FPGA implementation quality | 0.0 | 12 | 0% |
| R6 Interfaces and integration | 0.0 | 8 | 0% |
| R7 Observability and debug | 1.7 | 4 | 42% |
| R8 Design quality and maintainability | 1.3 | 3 | 44% |
| R9 Reproducibility and claim hygiene | 1.9 | 3 | 62% |
| **Total** | **6.1** | **100** | **foundation** |

- **Gates met:** HG2, HG4, HG5, PG4. **Not met:** HG1, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG6; R1 0% < 60%; R3 0% < 50%.
- **"Good":** not granted: HG1; HG3; HG6; HG7; HG8; total 6.1 < 75; R1 0% < 80%; an R1 criterion under 3; R2 0% < 70%; R3 0% < 70%; R6 0% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 6% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 1.070 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 165 runs, 106 instruction names.)

| Criterion | Score |
|---|---:|
| R1.1 | 0 |
| R1.2 | 0 |
| R1.3 | 0 |
| R1.4 | 0 |
| R1.5 | 0 |
| R1.6 | 0 |
| R2.1 | 0 |
| R2.2 | N/A |
| R2.3 | N/A |
| R2.4 | N/A |
| R2.5 | 0 |
| R2.6 | N/A |
| R3.1 | 0 |
| R3.2 | 0 |
| R3.3 | 0 |
| R3.4 | 0 |
| R3.5 | 0 |
| R3.6 | 0 |
| R3.7 | 0 |
| R4.1 | 2 |
| R4.2 | 0 |
| R4.3 | 0 |
| R4.4 | 0 |
| R4.5 | 0 |
| R4.6 | 0 |
| R4.7 | 0 |
| R4.8 | 0 |
| R5.1 | 0 |
| R5.2 | 0 |
| R5.3 | 0 |
| R5.4 | 0 |
| R5.5 | 0 |
| R5.6 | 0 |
| R5.7 | 0 |
| R6.1 | 0 |
| R6.2 | 0 |
| R6.3 | 0 |
| R6.4 | 0 |
| R6.5 | 0 |
| R6.6 | 0 |
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

Measured on the core and synchronous RAM: 275,030 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 294,298; the timed region measured 294,298 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.2 | 0.0% |
| EXECUTE | 588.3 | 99.9% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **588.6** | |

Instructions that needed a bus fetch: 0.2 of 550.1 per run (0.0%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 235.0 | 245.3 | 41.7% | 0.1 | 245.2 | 0.0 |
| load | 118.0 | 121.2 | 20.6% | 0.0 | 121.1 | 0.1 |
| branch | 87.0 | 110.0 | 18.7% | 0.0 | 110.0 | 0.0 |
| store | 76.0 | 76.1 | 12.9% | 0.0 | 76.0 | 0.0 |
| jump | 34.0 | 36.0 | 6.1% | 0.0 | 36.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 159.0 | 27.0% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 148.0 | 25.1% | 0.0 | 0.0 | 1.0 |
| `main` | 66.0 | 73.1 | 12.4% | 0.0 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 54.1 | 9.2% | 0.0 | 0.0 | 1.0 |
| `Proc_8` | 29.0 | 29.0 | 4.9% | 0.0 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 25.1 | 4.3% | 0.0 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 23.1 | 3.9% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 15.0 | 2.6% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 15.0 | 2.6% | 0.0 | 0.0 | 3.0 |
| `Proc_2` | 12.0 | 13.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 12.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 12.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 7.0 | 1.2% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 3.0 | 0.5% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 281.0 instructions per run.

Control flow per run: 59.0 branches taken, 28.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 313.0 | 0.0 |
| 2 beats (16 bytes) | 265.0 | 0.0 |
| 4 beats (32 bytes) | 167.0 | 0.0 |
| 8 beats (64 bytes) | 158.0 | 0.0 |
| 16 beats (128 bytes) | 150.0 | 0.0 |
| 32 beats (256 bytes) | 143.0 | 0.0 |
| 64 beats (512 bytes) | 127.1 | 0.0 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 20,000 | 0 | 0 |
| `0x0d04` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 15,505 | 0 | 5 |
| `0x0d08` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d0c` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,500 | 0 | 0 |
| `0x0d10` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d14` | `strcpy` | `bnez a3, 0xd04 <strcpy+0x4>` | 15,500 | 15,500 | 0 | 0 |
| `0x0d28` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 10,005 | 0 | 4 |
| `0x0d30` | `strcmp` | `lbu a2, 0x0(a0)` | 9,500 | 9,505 | 0 | 3 |
| `0x0d38` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,501 | 1 | 0 |
| `0x0d34` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 9,500 | 0 | 0 |
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 9,500 | 0 | 0 |
| `0x02ac` | `main` | `lw s6, 0xdc(sp)` | 1,000 | 2,003 | 1 | 1 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 2,000 | 1 | 0 |
| `0x09f4` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,508 | 2 | 0 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,506 | 2 | 0 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 588.5 | 1.070 | 0.9671 | 1.00x |
| Issue the next fetch in EXECUTE | 550.1 | 588.4 | 1.070 | 0.9673 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 588.6 | 1.070 | 0.9670 | 1.00x |
| No fetch clocks at all | 550.1 | 588.4 | 1.070 | 0.9673 | 1.00x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 1.07x |

- *Measured:* Clocks measured on the core and synchronous RAM.
- *Instruction cache, 2 beats (16 bytes):* Direct-mapped, filled on every fetch; a hit costs no fetch clocks. Stores to cached code are ignored by this estimate.
- *Issue loads and stores in EXECUTE:* The data request starts in EXECUTE, so each load or store that waited in MEMORY waits one clock less.
- *Issue the next fetch in EXECUTE:* A fetch that misses starts one clock earlier, during the previous instruction's EXECUTE. Upper bound: not possible after a load or store, which uses the bus.
- *Hardware multiply and divide (M):* Each helper call becomes one 1-clock instruction. Best case: an iterative divider takes longer.
- *No fetch clocks at all:* Perfect instruction supply: a lower bound for fetch work.
- *One clock per instruction:* The floor for a core that executes one instruction per clock.

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

- Timed region: 294,298 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 301,725 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=301390 slot2=0 slot3=0 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=441889 slot2=0 slot3=0 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 23.5 s, reference model 0.4 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `slli`, `sltiu`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb-pipe\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb-pipe\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb-pipe\link.ld .\build\cpu\bench\dhrystone-rv64imb-pipe\start.o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb-pipe\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb-pipe\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb-pipe\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-21 00:41:58 -0500","architecture_version":"0.8.0","commit":"53c6772","dirty":"yes (`cpu/programs-verification.json`, `cpu/visualizer-verification.json`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"pipe","cycles_per_run":588.596,"cpi":1.070057811875068,"dmips_per_mhz":0.9669653948961161,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_pipe.sv":"da2caf82aff03ad44c2e59e7bb3c1fe8f559f4e6f080df1de28ce46d705ac022","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-21 00:43:03 -0500

- **Architecture:** version 0.8.0
- **Commit:** `53c6772`, uncommitted changes: yes (`DEVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `cpu/dhrystone-rv64imb-pipe-results.json`, `devlog/devlog-53c6772.md`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, fast runtime, pipe core
- **RTL:** `rv64_pipe.sv` da2caf82aff0, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 484.6 clocks per run, 446.1 instructions per run, CPI 1.086, **1.1744 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** first run with these build settings

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.8.0` for architecture 0.8.0. Automated self-assessment, not a review.

**RTL or architecture version changed since the evidence was assessed: hand-scored R1-R6 criteria count as 0 until `cpu/rubric-evidence.json` is reassessed.**

| Dimension | Points | Of | Score |
|---|---:|---:|---:|
| R1 Architectural correctness | 0.0 | 25 | 0% |
| R2 Traps, interrupts, privilege and reset | 0.0 | 10 | 0% |
| R3 Verification depth and independence | 0.0 | 15 | 0% |
| R4 Performance | 1.2 | 20 | 6% |
| R5 FPGA implementation quality | 0.0 | 12 | 0% |
| R6 Interfaces and integration | 0.0 | 8 | 0% |
| R7 Observability and debug | 1.7 | 4 | 42% |
| R8 Design quality and maintainability | 1.3 | 3 | 44% |
| R9 Reproducibility and claim hygiene | 1.9 | 3 | 62% |
| **Total** | **6.1** | **100** | **foundation** |

- **Gates met:** HG2, HG4, HG5, PG4. **Not met:** HG1, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG6; R1 0% < 60%; R3 0% < 50%.
- **"Good":** not granted: HG1; HG3; HG6; HG7; HG8; total 6.1 < 75; R1 0% < 80%; an R1 criterion under 3; R2 0% < 70%; R3 0% < 70%; R6 0% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 6% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 1.086 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 165 runs, 106 instruction names.)

| Criterion | Score |
|---|---:|
| R1.1 | 0 |
| R1.2 | 0 |
| R1.3 | 0 |
| R1.4 | 0 |
| R1.5 | 0 |
| R1.6 | 0 |
| R2.1 | 0 |
| R2.2 | N/A |
| R2.3 | N/A |
| R2.4 | N/A |
| R2.5 | 0 |
| R2.6 | N/A |
| R3.1 | 0 |
| R3.2 | 0 |
| R3.3 | 0 |
| R3.4 | 0 |
| R3.5 | 0 |
| R3.6 | 0 |
| R3.7 | 0 |
| R4.1 | 2 |
| R4.2 | 0 |
| R4.3 | 0 |
| R4.4 | 0 |
| R4.5 | 0 |
| R4.6 | 0 |
| R4.7 | 0 |
| R4.8 | 0 |
| R5.1 | 0 |
| R5.2 | 0 |
| R5.3 | 0 |
| R5.4 | 0 |
| R5.5 | 0 |
| R5.6 | 0 |
| R5.7 | 0 |
| R6.1 | 0 |
| R6.2 | 0 |
| R6.3 | 0 |
| R6.4 | 0 |
| R6.5 | 0 |
| R6.6 | 0 |
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

Measured on the core and synchronous RAM: 223,030 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 242,314; the timed region measured 242,314 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.2 | 0.1% |
| EXECUTE | 476.3 | 98.3% |
| MEMORY (loads and stores) | 8.1 | 1.7% |
| **Total** | **484.6** | |

Instructions that needed a bus fetch: 0.2 of 446.1 per run (0.0%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 234.0 | 250.3 | 51.6% | 0.1 | 250.2 | 0.0 |
| load | 73.0 | 84.2 | 17.4% | 0.0 | 76.0 | 8.1 |
| store | 55.0 | 57.1 | 11.8% | 0.0 | 57.0 | 0.0 |
| branch | 48.0 | 51.0 | 10.5% | 0.0 | 51.0 | 0.0 |
| jump | 36.0 | 42.0 | 8.7% | 0.0 | 42.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 97.0 | 103.0 | 21.3% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 80.0 | 86.1 | 17.8% | 0.1 | 0.0 | 1.0 |
| `main` | 66.0 | 78.1 | 16.1% | 0.0 | 1.0 | 0.0 |
| `Proc_1` | 53.0 | 56.1 | 11.6% | 0.0 | 2.0 | 1.0 |
| `Proc_8` | 29.0 | 30.0 | 6.2% | 0.0 | 1.0 | 1.0 |
| `Func_2` | 23.0 | 27.1 | 5.6% | 0.0 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 25.0 | 5.2% | 0.0 | 2.0 | 1.0 |
| `Proc_7` | 15.0 | 15.0 | 3.1% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 15.0 | 3.1% | 0.0 | 0.0 | 3.0 |
| `Proc_2` | 12.0 | 14.0 | 2.9% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 13.0 | 2.7% | 0.0 | 1.0 | 1.0 |
| `Proc_3` | 11.0 | 12.0 | 2.5% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 7.0 | 1.4% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 3.0 | 0.6% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 177.0 instructions per run.

Control flow per run: 21.0 branches taken, 27.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 252.0 | 0.0 |
| 2 beats (16 bytes) | 248.0 | 0.0 |
| 4 beats (32 bytes) | 224.0 | 0.0 |
| 8 beats (64 bytes) | 200.0 | 0.0 |
| 16 beats (128 bytes) | 194.0 | 0.0 |
| 32 beats (256 bytes) | 191.0 | 0.0 |
| 64 beats (512 bytes) | 181.0 | 0.0 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0dd0` | `strcpy` | `lbu a3, 0x0(a1)` | 2,500 | 2,500 | 0 | 0 |
| `0x0dd4` | `strcpy` | `addi a1, a1, 0x1` | 2,500 | 2,500 | 0 | 0 |
| `0x0dd8` | `strcpy` | `sb a3, 0x0(a2)` | 2,500 | 2,500 | 0 | 0 |
| `0x0ddc` | `strcpy` | `addi a2, a2, 0x1` | 2,500 | 2,500 | 0 | 0 |
| `0x0de0` | `strcpy` | `bnez a3, 0xdd0 <strcpy+0xd0>` | 2,500 | 2,500 | 0 | 0 |
| `0x02ac` | `main` | `lw s6, 0xdc(sp)` | 1,000 | 2,003 | 1 | 1 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 2,000 | 1 | 0 |
| `0x09f4` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,508 | 2 | 0 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,506 | 2 | 0 |
| `0x0d7c` | `strcpy` | `ld t1, 0x0(t0)` | 1,500 | 1,503 | 0 | 3 |
| `0x0df8` | `strcmp` | `lbu a4, 0x0(a1)` | 1,500 | 1,503 | 1 | 2 |
| `0x0a00` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,502 | 1 | 1 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 1,501 | 1 | 0 |
| `0x0a88` | `Func_1` | `li a0, 0x0` | 1,500 | 1,501 | 1 | 0 |
| `0x0df4` | `strcmp` | `lbu a3, 0x0(a0)` | 1,500 | 1,501 | 0 | 0 |

**Instruction mix** (per run): `addi` 127.0, `ld` 38.0, `jalr` 32.0, `auipc` 23.0, `sd` 23.0, `sw` 23.0, `bne` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `lw` 13.0, `xor` 13.0, `or` 11.0, `sb` 9.0, `srli` 8.0, `srl` 7.0, `sll` 7.0, `sub` 6.0, `jal` 4.0, `add` 4.0, `sltiu` 3.0, `slli` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| Issue loads and stores in EXECUTE | 446.1 | 476.5 | 1.068 | 1.1944 | 1.02x |
| Issue the next fetch in EXECUTE | 446.1 | 484.4 | 1.086 | 1.1749 | 1.00x |
| Hardware multiply and divide (M) | 446.1 | 484.6 | 1.086 | 1.1744 | 1.00x |
| No fetch clocks at all | 446.1 | 484.4 | 1.086 | 1.1750 | 1.00x |
| One clock per instruction | 446.1 | 446.1 | 1.000 | 1.2760 | 1.09x |

- *Measured:* Clocks measured on the core and synchronous RAM.
- *Instruction cache, 2 beats (16 bytes):* Direct-mapped, filled on every fetch; a hit costs no fetch clocks. Stores to cached code are ignored by this estimate.
- *Issue loads and stores in EXECUTE:* The data request starts in EXECUTE, so each load or store that waited in MEMORY waits one clock less.
- *Issue the next fetch in EXECUTE:* A fetch that misses starts one clock earlier, during the previous instruction's EXECUTE. Upper bound: not possible after a load or store, which uses the bus.
- *Hardware multiply and divide (M):* Each helper call becomes one 1-clock instruction. Best case: an iterative divider takes longer.
- *No fetch clocks at all:* Perfect instruction supply: a lower bound for fetch work.
- *One clock per instruction:* The floor for a core that executes one instruction per clock.

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

- Timed region: 242,314 clocks, 223,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 249,663 clocks, 229,793 instructions.
- Differential run, up to 0 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=245278 slot2=0 slot3=0 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=362940 slot2=0 slot3=0 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 17.6 s, reference model 0.4 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `orc.b`, `orn`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `sll`, `slli`, `sltiu`, `srl`, `srli`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -DBENCH_FAST_STRINGS -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\link.ld .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\start.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-pipe\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-21 00:43:03 -0500","architecture_version":"0.8.0","commit":"53c6772","dirty":"yes (`DEVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `cpu/dhrystone-rv64imb-pipe-results.json`, `devlog/devlog-53c6772.md`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"fast","core":"pipe","cycles_per_run":484.628,"cpi":1.086463704434381,"dmips_per_mhz":1.1744099878138992,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_pipe.sv":"da2caf82aff03ad44c2e59e7bb3c1fe8f559f4e6f080df1de28ce46d705ac022","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->
