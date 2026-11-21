# Development log for commit `129e37e`

Commit subject: Register the multiplier operands (architecture 0.7.1)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-20 23:53:49 -0500

- **Architecture:** version 0.7.1
- **Commit:** `129e37e`, uncommitted changes: yes (`pu/dhrystone-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/synth_fmax.py`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime
- **RTL:** `rv64_core.sv` dd153c8d943a, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 256.8 clocks per run, 550.1 instructions per run, CPI 0.467, **2.2163 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.00% clocks per run against the previous run with the same build settings (2026-11-20 23:23:03 -0500, `a6e3f87`, architecture 0.7.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.7.1` for architecture 0.7.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.467 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 150 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 275,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 128,403; the timed region measured 128,403 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.2% |
| EXECUTE | 256.2 | 99.8% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **256.8** | |

Instructions that needed a bus fetch: 0.3 of 550.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| store | 76.0 | 71.1 | 27.7% | 0.1 | 71.0 | 0.0 |
| alu | 235.0 | 65.4 | 25.5% | 0.3 | 65.1 | 0.0 |
| branch | 87.0 | 59.0 | 23.0% | 0.0 | 59.0 | 0.0 |
| load | 118.0 | 41.3 | 16.1% | 0.1 | 41.1 | 0.1 |
| jump | 34.0 | 20.0 | 7.8% | 0.0 | 20.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 63.0 | 24.5% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 62.0 | 24.2% | 0.0 | 0.0 | 1.0 |
| `main` | 66.0 | 33.2 | 12.9% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 27.2 | 10.6% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 29.0 | 14.1 | 5.5% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 11.1 | 4.3% | 0.0 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 11.1 | 4.3% | 0.1 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 2.7% | 0.0 | 0.0 | 3.0 |
| `Proc_4` | 12.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 5.0 | 2.0% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 1.2% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 2.0 | 0.8% | 0.0 | 0.0 | 1.0 |
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
| `0x0d0c` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,495 | 0 | 0 |
| `0x0d14` | `strcpy` | `bnez a3, 0xd04 <strcpy+0x4>` | 15,500 | 15,495 | 0 | 0 |
| `0x0d28` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 10,002 | 2 | 3 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 10,000 | 0 | 0 |
| `0x0d38` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,499 | 2 | 0 |
| `0x0a00` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,502 | 2 | 0 |
| `0x09f4` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,501 | 2 | 0 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 1,500 | 0 | 0 |
| `0x0a8c` | `Func_1` | `ret` | 1,500 | 1,499 | 0 | 0 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 1,002 | 2 | 0 |
| `0x029c` | `main` | `lbu a0, 0x0(s10)` | 1,000 | 999 | 0 | 0 |
| `0x02a4` | `main` | `zext.b a1, s0` | 1,000 | 999 | 0 | 0 |
| `0x0d04` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 514 | 0 | 5 |
| `0x0ab8` | `Func_2` | `lbu a0, 0x2(s1)` | 500 | 503 | 2 | 1 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 503 | 2 | 0 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 256.7 | 0.467 | 2.2169 | 1.00x |
| Issue the next fetch in EXECUTE | 550.1 | 256.5 | 0.466 | 2.2187 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 256.8 | 0.467 | 2.2163 | 1.00x |
| No fetch clocks at all | 550.1 | 256.2 | 0.466 | 2.2212 | 1.00x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.47x |

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

- Timed region: 128,403 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 132,595 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=132132`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=292665`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 30.0 s, reference model 0.5 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `slli`, `sltiu`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb\link.ld .\build\cpu\bench\dhrystone-rv64imb\start.o .\build\cpu\bench\dhrystone-rv64imb\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-20 23:53:49 -0500","architecture_version":"0.7.1","commit":"129e37e","dirty":"yes (`pu/dhrystone-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/synth_fmax.py`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","cycles_per_run":256.806,"cpi":0.46686906882885504,"dmips_per_mhz":2.2162720636366533,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"dd153c8d943a348dda45b02c5636048f5f6e201f839ca1da2753c1666983e4eb","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-20 23:55:03 -0500

- **Architecture:** version 0.7.1
- **Commit:** `129e37e`, uncommitted changes: yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, `sim/cpu/synth_fmax.py`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, fast runtime
- **RTL:** `rv64_core.sv` dd153c8d943a, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 216.9 clocks per run, 446.1 instructions per run, CPI 0.486, **2.6243 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.00% clocks per run against the previous run with the same build settings (2026-11-20 23:24:16 -0500, `a6e3f87`, architecture 0.7.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.7.1` for architecture 0.7.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.486 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 150 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 223,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 108,440; the timed region measured 108,440 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.3% |
| EXECUTE | 208.2 | 96.0% |
| MEMORY (loads and stores) | 8.1 | 3.7% |
| **Total** | **216.9** | |

Instructions that needed a bus fetch: 0.3 of 446.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 234.0 | 78.5 | 36.2% | 0.4 | 78.1 | 0.0 |
| store | 55.0 | 49.1 | 22.6% | 0.1 | 49.0 | 0.0 |
| load | 73.0 | 42.2 | 19.5% | 0.1 | 34.1 | 8.1 |
| branch | 48.0 | 27.0 | 12.5% | 0.0 | 27.0 | 0.0 |
| jump | 36.0 | 20.0 | 9.2% | 0.1 | 20.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 97.0 | 38.0 | 17.5% | 0.0 | 0.0 | 1.0 |
| `main` | 66.0 | 34.2 | 15.8% | 0.1 | 1.0 | 0.0 |
| `strcmp` | 80.0 | 33.2 | 15.3% | 0.1 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 32.1 | 14.8% | 0.1 | 2.0 | 1.0 |
| `Proc_8` | 29.0 | 16.1 | 7.4% | 0.1 | 1.0 | 1.0 |
| `Proc_6` | 23.0 | 14.1 | 6.5% | 0.1 | 2.0 | 1.0 |
| `Func_2` | 23.0 | 11.1 | 5.1% | 0.0 | 0.0 | 1.0 |
| `Proc_4` | 12.0 | 8.0 | 3.7% | 0.0 | 1.0 | 1.0 |
| `Proc_2` | 12.0 | 7.0 | 3.2% | 0.0 | 1.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 3.2% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 6.0 | 2.8% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 5.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 1.4% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 2.0 | 0.9% | 0.0 | 0.0 | 1.0 |
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
| `0x0dd8` | `strcpy` | `sb a3, 0x0(a2)` | 2,500 | 2,500 | 0 | 0 |
| `0x0de0` | `strcpy` | `bnez a3, 0xdd0 <strcpy+0xd0>` | 2,500 | 2,500 | 0 | 0 |
| `0x0a00` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,502 | 2 | 0 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 1,500 | 0 | 0 |
| `0x0a8c` | `Func_1` | `ret` | 1,500 | 1,499 | 0 | 0 |
| `0x0e14` | `strcmp` | `bnez a3, 0xdf4 <strcmp+0xc>` | 1,500 | 1,499 | 0 | 0 |
| `0x0d78` | `strcpy` | `sd a7, 0x0(a2)` | 1,500 | 1,498 | 0 | 0 |
| `0x0d84` | `strcpy` | `sll a7, t1, a6` | 1,500 | 1,497 | 0 | 0 |
| `0x0d90` | `strcpy` | `addi a1, a1, 0x8` | 1,500 | 1,497 | 0 | 0 |
| `0x0d9c` | `strcpy` | `mv a5, t1` | 1,500 | 1,497 | 0 | 0 |
| `0x0df8` | `strcmp` | `lbu a4, 0x0(a1)` | 1,500 | 1,003 | 2 | 1 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 1,002 | 2 | 0 |
| `0x0e00` | `strcmp` | `bne a3, a4, 0xf04 <strcmp+0x11c>` | 1,500 | 1,002 | 2 | 0 |
| `0x09f4` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,002 | 2 | 0 |
| `0x07d0` | `Proc_1` | `ld a1, 0x10(a0)` | 500 | 1,002 | 2 | 500 |

**Instruction mix** (per run): `addi` 127.0, `ld` 38.0, `jalr` 32.0, `auipc` 23.0, `sd` 23.0, `sw` 23.0, `bne` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `lw` 13.0, `xor` 13.0, `or` 11.0, `sb` 9.0, `srli` 8.0, `srl` 7.0, `sll` 7.0, `sub` 6.0, `jal` 4.0, `add` 4.0, `sltiu` 3.0, `slli` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| Issue loads and stores in EXECUTE | 446.1 | 208.8 | 0.468 | 2.7256 | 1.04x |
| Issue the next fetch in EXECUTE | 446.1 | 216.6 | 0.485 | 2.6282 | 1.00x |
| Hardware multiply and divide (M) | 446.1 | 216.9 | 0.486 | 2.6243 | 1.00x |
| No fetch clocks at all | 446.1 | 216.2 | 0.485 | 2.6322 | 1.00x |
| One clock per instruction | 446.1 | 446.1 | 1.000 | 1.2760 | 0.49x |

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

- Timed region: 108,440 clocks, 223,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 112,635 clocks, 229,793 instructions.
- Differential run, up to 0 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=108124`.
- Differential run, up to 7 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=236989`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 19.6 s, reference model 0.4 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `orc.b`, `orn`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `sll`, `slli`, `sltiu`, `srl`, `srli`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -DBENCH_FAST_STRINGS -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb-fastrt\link.ld .\build\cpu\bench\dhrystone-rv64imb-fastrt\start.o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb-fastrt\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb-fastrt\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb-fastrt\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-20 23:55:03 -0500","architecture_version":"0.7.1","commit":"129e37e","dirty":"yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, `sim/cpu/synth_fmax.py`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"fast","cycles_per_run":216.88,"cpi":0.48621261713670805,"dmips_per_mhz":2.624271318582969,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"dd153c8d943a348dda45b02c5636048f5f6e201f839ca1da2753c1666983e4eb","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-20 23:56:41 -0500

- **Architecture:** version 0.7.1
- **Commit:** `129e37e`, uncommitted changes: yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64imb-fastrt-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, `sim/cpu/synth_fmax.py`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zifencei`, 64 KiB RAM, reference runtime
- **RTL:** `rv64_core.sv` dd153c8d943a, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 261.8 clocks per run, 553.1 instructions per run, CPI 0.473, **2.1739 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +1.16% clocks per run against the previous run with the same build settings (2026-11-20 23:25:56 -0500, `a6e3f87`, architecture 0.7.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.7.1` for architecture 0.7.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.473 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 150 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 276,529 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 130,907; the timed region measured 130,907 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.2% |
| EXECUTE | 261.2 | 99.8% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **261.8** | |

Instructions that needed a bus fetch: 0.3 of 553.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| store | 76.0 | 71.1 | 27.1% | 0.1 | 71.0 | 0.0 |
| alu | 238.0 | 68.4 | 26.1% | 0.3 | 68.1 | 0.0 |
| branch | 87.0 | 59.0 | 22.5% | 0.0 | 59.0 | 0.0 |
| load | 118.0 | 42.3 | 16.1% | 0.1 | 42.1 | 0.1 |
| jump | 34.0 | 21.0 | 8.0% | 0.0 | 21.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 63.0 | 24.1% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 62.1 | 23.7% | 0.0 | 0.0 | 1.0 |
| `main` | 68.0 | 35.2 | 13.4% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 27.2 | 10.4% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 30.0 | 17.1 | 6.5% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 11.1 | 4.2% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 11.1 | 4.2% | 0.1 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 2.7% | 0.0 | 0.0 | 3.0 |
| `Proc_4` | 12.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 2.3% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 5.0 | 1.9% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 1.2% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 2.0 | 0.8% | 0.0 | 0.0 | 1.0 |
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
| `0x0d18` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,495 | 0 | 0 |
| `0x0d20` | `strcpy` | `bnez a3, 0xd10 <strcpy+0x4>` | 15,500 | 15,495 | 0 | 0 |
| `0x0d38` | `strcmp` | `bne a2, a3, 0xd4c <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0d34` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 9,999 | 0 | 3 |
| `0x0d44` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,496 | 0 | 0 |
| `0x0a98` | `Func_1` | `ret` | 1,500 | 1,502 | 2 | 0 |
| `0x0a08` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,502 | 2 | 0 |
| `0x01e8` | `main` | `divw s6, s5, s8` | 500 | 1,502 | 2 | 0 |
| `0x09fc` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,002 | 2 | 0 |
| `0x0a18` | `Proc_8` | `mul a6, a4, a5` | 500 | 1,002 | 2 | 0 |
| `0x0a44` | `Proc_8` | `mul a2, a2, a5` | 500 | 1,000 | 0 | 0 |
| `0x0a8c` | `Func_1` | `zext.b a1, a1` | 1,500 | 999 | 0 | 0 |
| `0x02a4` | `main` | `lbu a0, 0x0(s10)` | 1,000 | 999 | 0 | 0 |
| `0x02ac` | `main` | `zext.b a1, s5` | 1,000 | 999 | 0 | 0 |
| `0x0d10` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 514 | 0 | 5 |

**Instruction mix** (per run): `addi` 177.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `add` 14.0, `lw` 13.0, `andi` 8.0, `beq` 7.0, `sltiu` 3.0, `xor` 3.0, `slli` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `or` 1.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| Issue loads and stores in EXECUTE | 553.1 | 261.7 | 0.473 | 2.1745 | 1.00x |
| Issue the next fetch in EXECUTE | 553.1 | 261.5 | 0.473 | 2.1763 | 1.00x |
| Hardware multiply and divide (M) | 553.1 | 261.8 | 0.473 | 2.1739 | 1.00x |
| No fetch clocks at all | 553.1 | 261.2 | 0.472 | 2.1787 | 1.00x |
| One clock per instruction | 553.1 | 553.1 | 1.000 | 1.0291 | 0.47x |

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

- Timed region: 130,907 clocks, 276,529 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 135,098 clocks, 283,428 instructions.
- Differential run, up to 0 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=134631`.
- Differential run, up to 7 wait cycles: PASS, 323,227 events, `DONE retirements=283428 cycles=295650`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 27.1 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-20 23:56:41 -0500","architecture_version":"0.7.1","commit":"129e37e","dirty":"yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64imb-fastrt-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, `sim/cpu/synth_fmax.py`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zifencei","ram_bytes":65536,"runtime":"reference","cycles_per_run":261.814,"cpi":0.4733933873119998,"dmips_per_mhz":2.1738790269973123,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"dd153c8d943a348dda45b02c5636048f5f6e201f839ca1da2753c1666983e4eb","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-20 23:58:24 -0500

- **Architecture:** version 0.7.1
- **Commit:** `129e37e`, uncommitted changes: yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64im-results.json`, `cpu/dhrystone-rv64imb-fastrt-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64i_zifencei`, 64 KiB RAM, reference runtime
- **RTL:** `rv64_core.sv` dd153c8d943a, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 273.9 clocks per run, 600.1 instructions per run, CPI 0.456, **2.0780 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -11.32% clocks per run against the previous run with the same build settings (2026-11-20 23:01:05 -0500, `5f1f6b1`, architecture 0.5.5). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.7.1` for architecture 0.7.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.456 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 150 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 300,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 136,949; the timed region measured 136,949 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.2% |
| EXECUTE | 273.2 | 99.7% |
| MEMORY (loads and stores) | 0.1 | 0.0% |
| **Total** | **273.9** | |

Instructions that needed a bus fetch: 0.3 of 600.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 276.0 | 74.5 | 27.2% | 0.4 | 74.1 | 0.0 |
| store | 76.0 | 71.1 | 25.9% | 0.1 | 71.0 | 0.0 |
| branch | 94.0 | 63.1 | 23.0% | 0.1 | 63.0 | 0.0 |
| load | 118.0 | 42.2 | 15.4% | 0.1 | 42.1 | 0.1 |
| jump | 36.0 | 23.1 | 8.4% | 0.1 | 23.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 63.0 | 23.0% | 0.0 | 0.0 | 1.0 |
| `strcmp` | 124.0 | 62.1 | 22.7% | 0.0 | 0.0 | 1.0 |
| `main` | 72.0 | 34.2 | 12.5% | 0.1 | 0.0 | 0.0 |
| `Proc_1` | 53.0 | 27.2 | 9.9% | 0.1 | 0.0 | 1.0 |
| `Proc_8` | 37.0 | 16.1 | 5.9% | 0.1 | 0.0 | 1.0 |
| `__divdi3` | 36.0 | 14.1 | 5.1% | 0.1 | 0.0 | 1.0 |
| `Func_2` | 23.0 | 11.1 | 4.0% | 0.1 | 0.0 | 1.0 |
| `Proc_6` | 23.0 | 11.1 | 4.0% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 7.0 | 2.6% | 0.0 | 0.0 | 3.0 |
| `Proc_4` | 12.0 | 6.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_2` | 12.0 | 6.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 2.2% | 0.0 | 0.0 | 1.0 |
| `Proc_3` | 11.0 | 5.0 | 1.8% | 0.0 | 0.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 1.1% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 2.0 | 0.7% | 0.0 | 0.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |

Software multiply and divide: 36.0 instructions and 14.1 clocks per run (5.1%), from `__divdi3` 1.0 calls per run. String and memory routines: 281.0 instructions per run.

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
| `0x0d78` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 15,495 | 0 | 0 |
| `0x0d80` | `strcpy` | `bnez a3, 0xd70 <strcpy+0x4>` | 15,500 | 15,495 | 0 | 0 |
| `0x0d98` | `strcmp` | `bne a2, a3, 0xdac <strcmp+0x24>` | 10,000 | 10,002 | 2 | 0 |
| `0x0d94` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 9,999 | 0 | 3 |
| `0x0da4` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 9,496 | 0 | 0 |
| `0x0af8` | `Func_1` | `ret` | 1,500 | 1,502 | 2 | 0 |
| `0x0a4c` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 1,499 | 0 | 0 |
| `0x0a40` | `Proc_7` | `add a0, a0, a1` | 1,500 | 1,002 | 2 | 0 |
| `0x0aec` | `Func_1` | `zext.b a1, a1` | 1,500 | 999 | 0 | 0 |
| `0x02b4` | `main` | `lbu a0, 0x0(s11)` | 1,000 | 999 | 0 | 0 |
| `0x02bc` | `main` | `zext.b a1, s8` | 1,000 | 999 | 0 | 0 |
| `0x0d70` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 514 | 0 | 5 |
| `0x0970` | `Proc_4` | `lw a3, 0xc(a1)` | 500 | 503 | 2 | 1 |
| `0x0ae8` | `Func_1` | `xor a1, a1, a0` | 1,500 | 503 | 2 | 0 |
| `0x0af0` | `Func_1` | `beqz a1, 0xafc <Func_1+0x14>` | 1,500 | 503 | 2 | 0 |

**Instruction mix** (per run): `addi` 184.0, `lbu` 79.0, `bne` 78.0, `jalr` 34.0, `sb` 33.0, `ld` 26.0, `auipc` 24.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `add` 13.0, `slli` 11.0, `beq` 8.0, `andi` 8.0, `sub` 8.0, `xor` 6.0, `and` 4.0, `srli` 4.0, `sltiu` 3.0, `or` 3.0, `bltu` 3.0, `jal` 2.0, `bge` 2.0, `addiw` 2.0, `bgeu` 2.0, `srai` 2.0, `sltu` 2.0, `lui` 1.0, `blt` 1.0, `addw` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 600.1 | 273.9 | 0.456 | 2.0780 | 1.00x |
| Issue loads and stores in EXECUTE | 600.1 | 273.8 | 0.456 | 2.0785 | 1.00x |
| Issue the next fetch in EXECUTE | 600.1 | 273.6 | 0.456 | 2.0805 | 1.00x |
| Hardware multiply and divide (M) | 564.1 | 260.8 | 0.462 | 2.1821 | 1.05x |
| No fetch clocks at all | 600.1 | 273.2 | 0.455 | 2.0830 | 1.00x |
| One clock per instruction | 600.1 | 600.1 | 1.000 | 0.9485 | 0.46x |

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

- Timed region: 136,949 clocks, 300,029 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 141,279 clocks, 307,336 instructions.
- Differential run, up to 0 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=140785`.
- Differential run, up to 7 wait cycles: PASS, 347,135 events, `DONE retirements=307336 cycles=301815`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 28.2 s, reference model 0.5 s.
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

<!-- dhrystone-run {"time":"2026-11-20 23:58:24 -0500","architecture_version":"0.7.1","commit":"129e37e","dirty":"yes (`EVLOG.md`, `cpu/dhrystone-results.json`, `cpu/dhrystone-rv64im-results.json`, `cpu/dhrystone-rv64imb-fastrt-results.json`, `cpu/dhrystone-rv64imb-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `devlog/devlog-129e37e.md`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64i_zifencei","ram_bytes":65536,"runtime":"reference","cycles_per_run":273.898,"cpi":0.45645254292085097,"dmips_per_mhz":2.077970498412819,"rubric_total":37.1,"rtl_sha256":{"rtl/cpu/rv64_core.sv":"dd153c8d943a348dda45b02c5636048f5f6e201f839ca1da2753c1666983e4eb","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->
