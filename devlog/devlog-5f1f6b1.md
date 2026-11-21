# Development log for commit `5f1f6b1`

Commit subject: Fold jumps and taken branches into the second slot (architecture 0.5.5)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-20 22:58:24 -0500

- **Architecture:** version 0.5.5
- **Commit:** `5f1f6b1`, uncommitted changes: yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zifencei`, 64 KiB RAM, reference runtime
- **RTL:** `rv64_core.sv` 295688213e26, `rv64_bram_soc.sv` 94a9e078dbd9
- **Result:** 287.8 clocks per run, 553.1 instructions per run, CPI 0.520, **1.9777 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -14.29% clocks per run against the previous run with the same build settings (2026-11-20 22:48:39 -0500, `241a9af`, architecture 0.5.4). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.5.5` for architecture 0.5.5. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.520 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 138 runs, 66 instruction names.)

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

Measured on the core and synchronous RAM: 276,529 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 143,891; the timed region measured 143,891 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.2% |
| EXECUTE | 287.1 | 99.8% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **287.8** | |

Instructions that needed a bus fetch: 0.3 of 553.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 238.0 | 120.3 | 41.8% | 0.3 | 120.1 | 0.0 |
| branch | 87.0 | 66.0 | 22.9% | 0.0 | 66.0 | 0.0 |
| store | 76.0 | 50.1 | 17.4% | 0.1 | 50.0 | 0.0 |
| load | 118.0 | 37.3 | 12.9% | 0.1 | 37.1 | 0.1 |
| jump | 34.0 | 14.1 | 4.9% | 0.0 | 14.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 79.0 | 27.5% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 62.1 | 21.6% | 0.0 | 0.0 | 1.0 |
| `main` | 68.0 | 37.2 | 12.9% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 28.2 | 9.8% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 30.0 | 16.1 | 5.6% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 13.1 | 4.5% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 13.1 | 4.5% | 0.1 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 7.0 | 2.4% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 7.0 | 2.4% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 2.4% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 7.0 | 2.4% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 6.0 | 2.1% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 4.0 | 1.4% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 1.0 | 0.3% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 281.0 instructions per run.

Control flow per run: 59.0 branches taken, 28.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 332.0 | 0.0 |
| 2 beats (16 bytes) | 302.0 | 0.0 |
| 4 beats (32 bytes) | 167.0 | 0.0 |
| 8 beats (64 bytes) | 155.0 | 0.0 |
| 16 beats (128 bytes) | 151.0 | 0.0 |
| 32 beats (256 bytes) | 145.0 | 0.0 |
| 64 beats (512 bytes) | 133.1 | 0.0 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d38` | `strcmp` | `bne a2, a3, 0xd4c <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0d40` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 9,502 | 2 | 0 |
| `0x0d48` | `strcmp` | `bnez a2, 0xd34 <strcmp+0xc>` | 9,500 | 9,502 | 2 | 0 |
| `0x0d14` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 8,000 | 0 | 0 |
| `0x0d1c` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 8,000 | 0 | 0 |
| `0x0d10` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 7,510 | 0 | 5 |
| `0x0d18` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 7,500 | 0 | 0 |
| `0x0d20` | `strcpy` | `bnez a3, 0xd10 <strcpy+0x4>` | 15,500 | 7,500 | 0 | 0 |
| `0x01e8` | `main` | `divw s6, s5, s8` | 500 | 1,502 | 2 | 0 |
| `0x0a00` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 1,002 | 2 | 0 |
| `0x0a08` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,002 | 2 | 0 |
| `0x0a8c` | `Func_1` | `zext.b a1, a1` | 1,500 | 998 | 0 | 0 |
| `0x0a94` | `Func_1` | `li a0, 0x0` | 1,500 | 998 | 0 | 0 |
| `0x0d34` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 505 | 0 | 3 |
| `0x0a88` | `Func_1` | `xor a1, a1, a0` | 1,500 | 504 | 2 | 0 |

**Instruction mix** (per run): `addi` 177.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `add` 14.0, `lw` 13.0, `andi` 8.0, `beq` 7.0, `sltiu` 3.0, `xor` 3.0, `slli` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `or` 1.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| Issue loads and stores in EXECUTE | 553.1 | 287.7 | 0.520 | 1.9782 | 1.00x |
| Issue the next fetch in EXECUTE | 553.1 | 287.5 | 0.520 | 1.9797 | 1.00x |
| Hardware multiply and divide (M) | 553.1 | 287.8 | 0.520 | 1.9777 | 1.00x |
| No fetch clocks at all | 553.1 | 287.2 | 0.519 | 1.9817 | 1.00x |
| One clock per instruction | 553.1 | 553.1 | 1.000 | 1.0291 | 0.52x |

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

- Timed region: 143,891 clocks, 276,529 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 148,161 clocks, 283,428 instructions.
- Differential run, up to 0 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=147694`.
- Differential run, up to 7 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=301318`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 20.9 s, reference model 0.4 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mul`, `mulw`, `or`, `sb`, `sd`, `slli`, `sltiu`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64im\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64im\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64im\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64im\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64im\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64im\link.ld .\build\cpu\bench\dhrystone-rv64im\start.o .\build\cpu\bench\dhrystone-rv64im\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64im\dhrystone.o .\build\cpu\bench\dhrystone-rv64im\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64im\runtime.o -o .\build\cpu\bench\dhrystone-rv64im\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-20 22:58:24 -0500","architecture_version":"0.5.5","commit":"5f1f6b1","dirty":"yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zifencei","ram_bytes":65536,"runtime":"reference","cycles_per_run":287.782,"cpi":0.5203468713950435,"dmips_per_mhz":1.9777191192439914,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"295688213e26a0f94fe2a124ed41bff61e05eb35187f1b8bd6c8ff010ef35d99","rtl/cpu/rv64_bram_soc.sv":"94a9e078dbd90cf124fb58f360ee95d6e7e7cc3d29f5ff03a0af8d6811e0760d"}} -->

## Run 2026-11-20 22:59:36 -0500

- **Architecture:** version 0.5.5
- **Commit:** `5f1f6b1`, uncommitted changes: yes (`EVLOG.md`, `cpu/dhrystone-rv64im-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-5f1f6b1.md`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zifencei`, 64 KiB RAM, fast runtime
- **RTL:** `rv64_core.sv` 295688213e26, `rv64_bram_soc.sv` 94a9e078dbd9
- **Result:** 251.9 clocks per run, 470.1 instructions per run, CPI 0.536, **2.2598 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -6.67% clocks per run against the previous run with the same build settings (2026-11-20 22:49:50 -0500, `241a9af`, architecture 0.5.4). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.5.5` for architecture 0.5.5. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.536 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 138 runs, 66 instruction names.)

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

Measured on the core and synchronous RAM: 235,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 125,931; the timed region measured 125,931 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.3% |
| EXECUTE | 247.1 | 98.1% |
| MEMORY (loads and stores) | 4.1 | 1.6% |
| **Total** | **251.9** | |

Instructions that needed a bus fetch: 0.3 of 470.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 253.0 | 133.4 | 53.0% | 0.4 | 133.0 | 0.0 |
| load | 77.0 | 43.3 | 17.2% | 0.1 | 39.0 | 4.1 |
| store | 55.0 | 39.1 | 15.5% | 0.1 | 39.0 | 0.0 |
| branch | 49.0 | 24.1 | 9.6% | 0.0 | 24.0 | 0.0 |
| jump | 36.0 | 12.1 | 4.8% | 0.0 | 12.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 108.0 | 55.0 | 21.8% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 90.0 | 45.2 | 17.9% | 0.1 | 0.0 | 1.0 |
| `main` | 68.0 | 39.2 | 15.5% | 0.1 | 1.0 | 0.0 |
| `Proc_1` | 53.0 | 29.2 | 11.6% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 30.0 | 17.1 | 6.8% | 0.1 | 1.0 | 1.0 |
| `Proc_6` | 23.0 | 14.1 | 5.6% | 0.1 | 1.0 | 1.0 |
| `Func_2` | 23.0 | 13.1 | 5.2% | 0.1 | 1.0 | 1.0 |
| `Func_1` | 15.0 | 8.0 | 3.2% | 0.0 | 0.0 | 3.0 |
| `Proc_3` | 11.0 | 7.0 | 2.8% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 7.0 | 2.8% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 6.0 | 2.4% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 2.4% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 4.0 | 1.6% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 1.0 | 0.4% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 198.0 instructions per run.

Control flow per run: 21.0 branches taken, 28.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 263.0 | 0.0 |
| 2 beats (16 bytes) | 259.0 | 0.0 |
| 4 beats (32 bytes) | 240.0 | 0.0 |
| 8 beats (64 bytes) | 205.0 | 0.0 |
| 16 beats (128 bytes) | 201.0 | 0.0 |
| 32 beats (256 bytes) | 197.0 | 0.0 |
| 64 beats (512 bytes) | 191.0 | 0.0 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x01e8` | `main` | `divw s6, s5, s8` | 500 | 1,502 | 2 | 0 |
| `0x0a00` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 1,501 | 2 | 0 |
| `0x0a08` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,501 | 2 | 0 |
| `0x0e08` | `strcpy` | `addi a1, a1, 0x1` | 2,500 | 1,499 | 0 | 0 |
| `0x0e10` | `strcpy` | `addi a2, a2, 0x1` | 2,500 | 1,499 | 0 | 0 |
| `0x0d9c` | `strcpy` | `ld t2, 0x0(t1)` | 1,500 | 1,004 | 0 | 3 |
| `0x0a88` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,003 | 2 | 0 |
| `0x0a90` | `Func_1` | `beqz a1, 0xa9c <Func_1+0x14>` | 1,500 | 1,003 | 2 | 0 |
| `0x0a98` | `Func_1` | `ret` | 1,500 | 1,003 | 2 | 0 |
| `0x0ac8` | `Func_2` | `lbu a1, 0x3(s0)` | 500 | 1,002 | 2 | 500 |
| `0x0ebc` | `strcmp` | `ld a2, 0x0(t2)` | 1,000 | 1,002 | 0 | 2 |
| `0x0a40` | `Proc_8` | `lw a0, 0x10(t0)` | 500 | 1,002 | 2 | 500 |
| `0x09f0` | `Proc_6` | `ld s1, 0x8(sp)` | 500 | 1,002 | 2 | 500 |
| `0x0e04` | `strcpy` | `lbu a3, 0x0(a1)` | 2,500 | 1,001 | 0 | 0 |
| `0x0e0c` | `strcpy` | `sb a3, 0x0(a2)` | 2,500 | 1,001 | 0 | 0 |

**Instruction mix** (per run): `addi` 131.0, `ld` 42.0, `jalr` 32.0, `auipc` 27.0, `bne` 24.0, `sd` 23.0, `sw` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `or` 14.0, `add` 14.0, `lw` 13.0, `sub` 12.0, `sb` 9.0, `srl` 7.0, `sll` 7.0, `and` 6.0, `slli` 5.0, `jal` 4.0, `sltiu` 3.0, `xor` 3.0, `srli` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| Issue loads and stores in EXECUTE | 470.1 | 247.8 | 0.527 | 2.2969 | 1.02x |
| Issue the next fetch in EXECUTE | 470.1 | 251.5 | 0.535 | 2.2628 | 1.00x |
| Hardware multiply and divide (M) | 470.1 | 251.9 | 0.536 | 2.2598 | 1.00x |
| No fetch clocks at all | 470.1 | 251.2 | 0.534 | 2.2658 | 1.00x |
| One clock per instruction | 470.1 | 470.1 | 1.000 | 1.2108 | 0.54x |

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

- Timed region: 125,931 clocks, 235,029 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 130,222 clocks, 241,814 instructions.
- Differential run, up to 0 wait cycles: PASS, 271,071 events, `DONE retirements=241814 cycles=127696`.
- Differential run, up to 7 wait cycles: PASS, 271,071 events, `DONE retirements=241814 cycles=248066`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 19.6 s, reference model 0.3 s.
- Instructions executed: `add`, `addi`, `addiw`, `and`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mul`, `mulw`, `or`, `sb`, `sd`, `sll`, `slli`, `sltiu`, `srl`, `srli`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64im-fastrt\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -DBENCH_FAST_STRINGS -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64im-fastrt\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64im-fastrt\link.ld .\build\cpu\bench\dhrystone-rv64im-fastrt\start.o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone.o .\build\cpu\bench\dhrystone-rv64im-fastrt\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64im-fastrt\runtime.o -o .\build\cpu\bench\dhrystone-rv64im-fastrt\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-20 22:59:36 -0500","architecture_version":"0.5.5","commit":"5f1f6b1","dirty":"yes (`EVLOG.md`, `cpu/dhrystone-rv64im-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-5f1f6b1.md`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zifencei","ram_bytes":65536,"runtime":"fast","cycles_per_run":251.862,"cpi":0.5358104744520888,"dmips_per_mhz":2.259777034940858,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"295688213e26a0f94fe2a124ed41bff61e05eb35187f1b8bd6c8ff010ef35d99","rtl/cpu/rv64_bram_soc.sv":"94a9e078dbd90cf124fb58f360ee95d6e7e7cc3d29f5ff03a0af8d6811e0760d"}} -->

## Run 2026-11-20 23:01:05 -0500

- **Architecture:** version 0.5.5
- **Commit:** `5f1f6b1`, uncommitted changes: yes (`EVLOG.md`, `cpu/dhrystone-rv64im-fastrt-results.json`, `cpu/dhrystone-rv64im-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-5f1f6b1.md`)
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM, reference runtime
- **RTL:** `rv64_core.sv` 295688213e26, `rv64_bram_soc.sv` 94a9e078dbd9
- **Result:** 308.9 clocks per run, 600.1 instructions per run, CPI 0.515, **1.8428 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -13.93% clocks per run against the previous run with the same build settings (2026-11-20 22:51:16 -0500, `241a9af`, architecture 0.5.4). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.5.5` for architecture 0.5.5. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.515 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 138 runs, 66 instruction names.)

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

Measured on the core and synchronous RAM: 300,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 154,430; the timed region measured 154,430 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.2% |
| EXECUTE | 308.1 | 99.8% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **308.9** | |

Instructions that needed a bus fetch: 0.3 of 600.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 276.0 | 133.4 | 43.2% | 0.4 | 133.1 | 0.0 |
| branch | 94.0 | 70.1 | 22.7% | 0.1 | 70.0 | 0.0 |
| store | 76.0 | 52.1 | 16.9% | 0.1 | 52.0 | 0.0 |
| load | 118.0 | 37.2 | 12.1% | 0.1 | 37.1 | 0.1 |
| jump | 36.0 | 16.1 | 5.2% | 0.1 | 16.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 79.0 | 25.6% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 62.1 | 20.1% | 0.0 | 0.0 | 1.0 |
| `main` | 72.0 | 36.2 | 11.7% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 28.2 | 9.1% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 37.0 | 20.1 | 6.5% | 0.1 | 0.0 | 1.0 |
| `__divdi3` | 36.0 | 18.1 | 5.8% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 13.1 | 4.2% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 13.1 | 4.2% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 7.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 7.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 2.3% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 7.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 6.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 4.0 | 1.3% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 1.0 | 0.3% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 36.0 instructions and 18.1 clocks per run (5.8%), from `__divdi3` 1.0 calls per run. String and memory routines: 281.0 instructions per run.

Control flow per run: 62.0 branches taken, 32.0 not taken, 16.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 359.0 | 0.0 |
| 2 beats (16 bytes) | 329.0 | 0.0 |
| 4 beats (32 bytes) | 188.0 | 0.0 |
| 8 beats (64 bytes) | 180.0 | 0.0 |
| 16 beats (128 bytes) | 174.0 | 0.0 |
| 32 beats (256 bytes) | 172.0 | 0.0 |
| 64 beats (512 bytes) | 162.1 | 0.0 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d98` | `strcmp` | `bne a2, a3, 0xdac <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0da0` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 9,502 | 2 | 0 |
| `0x0da8` | `strcmp` | `bnez a2, 0xd94 <strcmp+0xc>` | 9,500 | 9,502 | 2 | 0 |
| `0x0d74` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 8,000 | 0 | 0 |
| `0x0d7c` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 8,000 | 0 | 0 |
| `0x0d70` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 7,510 | 0 | 5 |
| `0x0d78` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 7,500 | 0 | 0 |
| `0x0d80` | `strcpy` | `bnez a3, 0xd70 <strcpy+0x4>` | 15,500 | 7,500 | 0 | 0 |
| `0x0a44` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 999 | 0 | 0 |
| `0x0a4c` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 999 | 0 | 0 |
| `0x0aec` | `Func_1` | `zext.b a1, a1` | 1,500 | 998 | 0 | 0 |
| `0x0af4` | `Func_1` | `li a0, 0x0` | 1,500 | 998 | 0 | 0 |
| `0x0d94` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 505 | 0 | 3 |
| `0x0ae8` | `Func_1` | `xor a1, a1, a0` | 1,500 | 504 | 2 | 0 |
| `0x0af0` | `Func_1` | `beqz a1, 0xafc <Func_1+0x14>` | 1,500 | 504 | 2 | 0 |

**Instruction mix** (per run): `addi` 184.0, `lbu` 79.0, `bne` 78.0, `jalr` 34.0, `sb` 33.0, `ld` 26.0, `auipc` 24.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `add` 13.0, `slli` 11.0, `beq` 8.0, `andi` 8.0, `sub` 8.0, `xor` 6.0, `and` 4.0, `srli` 4.0, `sltiu` 3.0, `or` 3.0, `bltu` 3.0, `jal` 2.0, `bge` 2.0, `addiw` 2.0, `bgeu` 2.0, `srai` 2.0, `sltu` 2.0, `lui` 1.0, `blt` 1.0, `addw` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 600.1 | 308.9 | 0.515 | 1.8428 | 1.00x |
| Issue loads and stores in EXECUTE | 600.1 | 308.8 | 0.515 | 1.8432 | 1.00x |
| Issue the next fetch in EXECUTE | 600.1 | 308.5 | 0.514 | 1.8447 | 1.00x |
| Hardware multiply and divide (M) | 564.1 | 291.8 | 0.517 | 1.9505 | 1.06x |
| No fetch clocks at all | 600.1 | 308.2 | 0.514 | 1.8467 | 1.00x |
| One clock per instruction | 600.1 | 600.1 | 1.000 | 0.9485 | 0.51x |

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

- Timed region: 154,430 clocks, 300,029 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 158,888 clocks, 307,336 instructions.
- Differential run, up to 0 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=158394`.
- Differential run, up to 7 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=311695`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 24.5 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-20 23:01:05 -0500","architecture_version":"0.5.5","commit":"5f1f6b1","dirty":"yes (`EVLOG.md`, `cpu/dhrystone-rv64im-fastrt-results.json`, `cpu/dhrystone-rv64im-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-5f1f6b1.md`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"runtime":"reference","cycles_per_run":308.86,"cpi":0.5147169106986325,"dmips_per_mhz":1.8427506429264855,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"295688213e26a0f94fe2a124ed41bff61e05eb35187f1b8bd6c8ff010ef35d99","rtl/cpu/rv64_bram_soc.sv":"94a9e078dbd90cf124fb58f360ee95d6e7e7cc3d29f5ff03a0af8d6811e0760d"}} -->
