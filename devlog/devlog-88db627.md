# Development log for commit `88db627`

Commit subject: Add the M extension (architecture 0.4.0)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-20 21:48:47 -0500

- **Architecture:** version 0.4.0
- **Commit:** `88db627`, uncommitted changes: yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zifencei`, 64 KiB RAM
- **RTL:** `rv64_core.sv` e7bf693e3b31, `rv64_bram_soc.sv` 385b91fe9a8a
- **Result:** 555.7 clocks per run, 553.1 instructions per run, CPI 1.005, **1.0242 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** first run with these build settings

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.4.0` for architecture 0.4.0. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 1.005 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 108 runs, 66 instruction names.)

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

Measured on the core and synchronous RAM: 276,529 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 277,855; the timed region measured 277,855 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.1% |
| EXECUTE | 555.1 | 99.9% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **555.7** | |

Instructions that needed a bus fetch: 0.3 of 553.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 238.0 | 240.3 | 43.2% | 0.3 | 240.0 | 0.0 |
| load | 118.0 | 118.2 | 21.3% | 0.1 | 118.0 | 0.1 |
| branch | 87.0 | 87.0 | 15.7% | 0.0 | 87.0 | 0.0 |
| store | 76.0 | 76.1 | 13.7% | 0.1 | 76.0 | 0.0 |
| jump | 34.0 | 34.1 | 6.1% | 0.0 | 34.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 157.0 | 28.3% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 124.0 | 22.3% | 0.0 | 0.0 | 1.0 |
| `main` | 68.0 | 70.2 | 12.6% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 53.1 | 9.6% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 30.0 | 30.1 | 5.4% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 23.1 | 4.2% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 23.1 | 4.1% | 0.1 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 15.0 | 2.7% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 15.0 | 2.7% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 12.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 12.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 11.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 7.0 | 1.3% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 3.0 | 0.5% | 0.0 | 0.0 | 1.0 |
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
| `0x0d10` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 15,505 | 0 | 5 |
| `0x0d14` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d18` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,500 | 0 | 0 |
| `0x0d1c` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d20` | `strcpy` | `bnez a3, 0xd10 <strcpy+0x4>` | 15,500 | 15,500 | 0 | 0 |
| `0x0d34` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 10,003 | 0 | 3 |
| `0x0d38` | `strcmp` | `bne a2, a3, 0xd4c <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0d3c` | `strcmp` | `lbu a2, 0x0(a0)` | 9,500 | 9,503 | 0 | 3 |
| `0x0d40` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 9,502 | 2 | 0 |
| `0x0d48` | `strcmp` | `bnez a2, 0xd34 <strcmp+0xc>` | 9,500 | 9,502 | 2 | 0 |
| `0x0d44` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,500 | 0 | 0 |
| `0x0a88` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,502 | 2 | 0 |
| `0x0a90` | `Func_1` | `beqz a1, 0xa9c <Func_1+0x14>` | 1,500 | 1,502 | 2 | 0 |
| `0x0a98` | `Func_1` | `ret` | 1,500 | 1,502 | 2 | 0 |
| `0x09fc` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,502 | 2 | 0 |

**Instruction mix** (per run): `addi` 177.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `add` 14.0, `lw` 13.0, `andi` 8.0, `beq` 7.0, `sltiu` 3.0, `xor` 3.0, `slli` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `or` 1.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| Issue loads and stores in EXECUTE | 553.1 | 361.7 | 0.654 | 1.5736 | 1.54x |
| Issue the next fetch in EXECUTE | 553.1 | 555.4 | 1.004 | 1.0247 | 1.00x |
| Hardware multiply and divide (M) | 553.1 | 555.7 | 1.005 | 1.0242 | 1.00x |
| No fetch clocks at all | 553.1 | 555.1 | 1.004 | 1.0253 | 1.00x |
| One clock per instruction | 553.1 | 553.1 | 1.000 | 1.0291 | 1.00x |

- *Measured:* Clocks measured on the core and synchronous RAM.
- *Instruction cache, 2 beats (16 bytes):* Direct-mapped, filled on every fetch; a hit costs no fetch clocks. Stores to cached code are ignored by this estimate.
- *Issue loads and stores in EXECUTE:* The data request starts in EXECUTE, so each load or store spends one fewer clock waiting in MEMORY.
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

- Timed region: 277,855 clocks, 276,529 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 285,322 clocks, 283,428 instructions.
- Differential run, up to 0 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=284855`.
- Differential run, up to 7 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=425610`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 16.9 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-20 21:48:47 -0500","architecture_version":"0.4.0","commit":"88db627","dirty":"yes (`pu/programs-verification.json`, `cpu/visualizer-verification.json`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zifencei","ram_bytes":65536,"cycles_per_run":555.71,"cpi":1.004795157108296,"dmips_per_mhz":1.0241888099445293,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"e7bf693e3b3145465437778d1a693ee8c07c5b249af6411eff8613e30bb27df7","rtl/cpu/rv64_bram_soc.sv":"385b91fe9a8a9d768e7deadd976b718d1668c389da4cb74fed3634758769ae72"}} -->

## Run 2026-11-20 21:49:53 -0500

- **Architecture:** version 0.4.0
- **Commit:** `88db627`, uncommitted changes: yes (`EVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `cpu/dhrystone-rv64im-results.json`, `devlog/devlog-88db627.md`)
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM
- **RTL:** `rv64_core.sv` e7bf693e3b31, `rv64_bram_soc.sv` 385b91fe9a8a
- **Result:** 600.8 clocks per run, 600.1 instructions per run, CPI 1.001, **0.9473 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.00% clocks per run against the previous run with the same build settings (2026-11-20 21:43:28 -0500, `90ee1ea`, architecture 0.3.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.4.0` for architecture 0.4.0. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 1.001 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 108 runs, 66 instruction names.)

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

Measured on the core and synchronous RAM: 300,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 300,395; the timed region measured 300,395 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.1% |
| EXECUTE | 600.1 | 99.9% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **600.8** | |

Instructions that needed a bus fetch: 0.3 of 600.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 276.0 | 276.4 | 46.0% | 0.4 | 276.0 | 0.0 |
| load | 118.0 | 118.2 | 19.7% | 0.1 | 118.0 | 0.1 |
| branch | 94.0 | 94.1 | 15.7% | 0.1 | 94.0 | 0.0 |
| store | 76.0 | 76.1 | 12.7% | 0.1 | 76.0 | 0.0 |
| jump | 36.0 | 36.1 | 6.0% | 0.1 | 36.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 157.0 | 26.1% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 124.0 | 20.6% | 0.0 | 0.0 | 1.0 |
| `main` | 72.0 | 72.2 | 12.0% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 53.1 | 8.8% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 37.0 | 37.1 | 6.2% | 0.1 | 0.0 | 1.0 |
| `__divdi3` | 36.0 | 36.1 | 6.0% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 23.1 | 3.8% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 23.1 | 3.8% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 15.0 | 2.5% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 15.0 | 2.5% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 12.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 12.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 11.0 | 1.8% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 7.0 | 1.2% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 3.0 | 0.5% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 36.0 instructions and 36.1 clocks per run (6.0%), from `__divdi3` 1.0 calls per run. String and memory routines: 281.0 instructions per run.

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
| `0x0d70` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 15,505 | 0 | 5 |
| `0x0d74` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d78` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,500 | 0 | 0 |
| `0x0d7c` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,500 | 0 | 0 |
| `0x0d80` | `strcpy` | `bnez a3, 0xd70 <strcpy+0x4>` | 15,500 | 15,500 | 0 | 0 |
| `0x0d94` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 10,003 | 0 | 3 |
| `0x0d98` | `strcmp` | `bne a2, a3, 0xdac <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0d9c` | `strcmp` | `lbu a2, 0x0(a0)` | 9,500 | 9,503 | 0 | 3 |
| `0x0da0` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 9,502 | 2 | 0 |
| `0x0da8` | `strcmp` | `bnez a2, 0xd94 <strcmp+0xc>` | 9,500 | 9,502 | 2 | 0 |
| `0x0da4` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,500 | 0 | 0 |
| `0x0ae8` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,502 | 2 | 0 |
| `0x0af0` | `Func_1` | `beqz a1, 0xafc <Func_1+0x14>` | 1,500 | 1,502 | 2 | 0 |
| `0x0af8` | `Func_1` | `ret` | 1,500 | 1,502 | 2 | 0 |
| `0x0a40` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,502 | 2 | 0 |

**Instruction mix** (per run): `addi` 184.0, `lbu` 79.0, `bne` 78.0, `jalr` 34.0, `sb` 33.0, `ld` 26.0, `auipc` 24.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `add` 13.0, `slli` 11.0, `beq` 8.0, `andi` 8.0, `sub` 8.0, `xor` 6.0, `and` 4.0, `srli` 4.0, `sltiu` 3.0, `or` 3.0, `bltu` 3.0, `jal` 2.0, `bge` 2.0, `addiw` 2.0, `bgeu` 2.0, `srai` 2.0, `sltu` 2.0, `lui` 1.0, `blt` 1.0, `addw` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 600.1 | 600.8 | 1.001 | 0.9473 | 1.00x |
| Issue loads and stores in EXECUTE | 600.1 | 406.8 | 0.678 | 1.3992 | 1.48x |
| Issue the next fetch in EXECUTE | 600.1 | 600.5 | 1.001 | 0.9479 | 1.00x |
| Hardware multiply and divide (M) | 564.1 | 565.7 | 1.003 | 1.0060 | 1.06x |
| No fetch clocks at all | 600.1 | 600.1 | 1.000 | 0.9484 | 1.00x |
| One clock per instruction | 600.1 | 600.1 | 1.000 | 0.9485 | 1.00x |

- *Measured:* Clocks measured on the core and synchronous RAM.
- *Instruction cache, 2 beats (16 bytes):* Direct-mapped, filled on every fetch; a hit costs no fetch clocks. Stores to cached code are ignored by this estimate.
- *Issue loads and stores in EXECUTE:* The data request starts in EXECUTE, so each load or store spends one fewer clock waiting in MEMORY.
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

- Timed region: 300,395 clocks, 300,029 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 308,255 clocks, 307,336 instructions.
- Differential run, up to 0 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=307761`.
- Differential run, up to 7 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=448631`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 18.2 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-20 21:49:53 -0500","architecture_version":"0.4.0","commit":"88db627","dirty":"yes (`EVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `cpu/dhrystone-rv64im-results.json`, `devlog/devlog-88db627.md`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"cycles_per_run":600.79,"cpi":1.0012198820780658,"dmips_per_mhz":0.9473392759105084,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"e7bf693e3b3145465437778d1a693ee8c07c5b249af6411eff8613e30bb27df7","rtl/cpu/rv64_bram_soc.sv":"385b91fe9a8a9d768e7deadd976b718d1668c389da4cb74fed3634758769ae72"}} -->
