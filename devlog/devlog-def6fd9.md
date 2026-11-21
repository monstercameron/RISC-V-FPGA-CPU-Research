# Development log for commit `def6fd9`

Commit subject: Out-of-order core: fetch and rename 32 per clock (architecture 0.14.1)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-21 14:12:48 -0500

- **Architecture:** version 0.14.1
- **Commit:** `def6fd9`, uncommitted changes: yes (`DEVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/bench/bench_profile.py`, `.claude/`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, ooo core
- **RTL:** `rv64_ooo.sv` 71d9321dddc9, `rv64_bram_soc.sv` 7fdbaec4cda6
- **Result:** 31.4 clocks per run, 550.1 instructions per run, CPI 0.057, **18.1212 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -24.50% clocks per run against the previous run with the same build settings (2026-11-21 13:42:39 -0500, `4d74a0b`, architecture 0.13.0). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.14.1` for architecture 0.14.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.057 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 273 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 275,028 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 15,704; the timed region measured 15,704 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 1.9% |
| EXECUTE | 10.3 | 32.6% |
| MEMORY (loads and stores) | 20.6 | 65.4% |
| **Total** | **31.4** | |

Instructions that needed a bus fetch: 0.2 of 550.1 per run (0.0%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| store | 76.0 | 16.8 | 53.4% | 0.1 | 0.0 | 16.7 |
| branch | 87.0 | 8.1 | 25.9% | 0.0 | 7.1 | 1.0 |
| load | 118.0 | 3.1 | 9.9% | 0.2 | 1.8 | 1.1 |
| alu | 235.0 | 2.7 | 8.5% | 0.2 | 1.4 | 1.0 |
| jump | 34.0 | 0.7 | 2.2% | 0.0 | 0.0 | 0.7 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcmp` | 124.0 | 9.5 | 30.2% | 0.0 | 0.4 | 1.0 |
| `strcpy` | 157.0 | 7.4 | 23.5% | 0.0 | 7.4 | 1.0 |
| `Proc_1` | 53.0 | 4.5 | 14.3% | 0.1 | 4.4 | 1.0 |
| `main` | 66.0 | 3.2 | 10.2% | 0.1 | 2.4 | 0.0 |
| `Proc_6` | 23.0 | 1.8 | 5.6% | 0.1 | 1.7 | 1.0 |
| `Proc_8` | 29.0 | 1.8 | 5.6% | 0.1 | 1.7 | 1.0 |
| `Func_2` | 23.0 | 1.1 | 3.5% | 0.1 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 1.0 | 3.3% | 0.0 | 1.0 | 1.0 |
| `Proc_2` | 12.0 | 1.0 | 3.3% | 0.0 | 0.7 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.1% | 0.0 | 0.0 | 0.0 |
| `Proc_3` | 11.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 0.0 | 0.1% | 0.0 | 0.0 | 3.0 |
| `bench_timer` | 0.0 | 0.0 | 0.1% | 0.0 | 0.0 | 0.0 |
| `Proc_5` | 7.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 0.0 | 0.0% | 0.0 | 0.0 | 1.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 281.0 instructions per run.

Control flow per run: 59.0 branches taken, 28.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 313.0 | 0.1 |
| 2 beats (16 bytes) | 265.0 | 0.1 |
| 4 beats (32 bytes) | 167.0 | 0.1 |
| 8 beats (64 bytes) | 158.0 | 0.1 |
| 16 beats (128 bytes) | 150.0 | 0.1 |
| 32 beats (256 bytes) | 143.0 | 0.1 |
| 64 beats (512 bytes) | 127.1 | 0.1 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d0c` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 3,652 | 0 | 3,652 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 2,009 | 0 | 172 |
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 1,686 | 1 | 2 |
| `0x08cc` | `Proc_2` | `lw a2, 0x0(a0)` | 500 | 504 | 0 | 330 |
| `0x0d28` | `strcmp` | `lbu a3, 0x0(a1)` | 10,000 | 503 | 2 | 2 |
| `0x0228` | `main` | `sw a0, 0xdc(sp)` | 500 | 342 | 4 | 338 |
| `0x093c` | `Proc_4` | `sw a2, 0xc(a1)` | 500 | 337 | 0 | 337 |
| `0x09d8` | `Proc_6` | `sw s1, 0x0(s0)` | 500 | 336 | 4 | 332 |
| `0x0d38` | `strcmp` | `addi a0, a0, 0x1` | 9,500 | 335 | 0 | 0 |
| `0x0964` | `Proc_6` | `sd ra, 0x18(sp)` | 500 | 334 | 2 | 332 |
| `0x0a50` | `Proc_8` | `sw a2, 0x10(a3)` | 500 | 332 | 0 | 332 |
| `0x07f8` | `Proc_1` | `sd a0, 0x0(s1)` | 500 | 332 | 0 | 332 |
| `0x0a24` | `Proc_8` | `sw a3, 0x18(a0)` | 500 | 331 | 0 | 331 |
| `0x0794` | `Proc_1` | `sd s0, 0x10(sp)` | 500 | 331 | 0 | 331 |
| `0x07bc` | `Proc_1` | `sd a1, 0x28(s1)` | 500 | 331 | 0 | 331 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 31.4 | 0.057 | 18.1212 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 31.3 | 0.057 | 18.1873 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 31.3 | 0.057 | 18.1919 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 31.3 | 0.057 | 18.1942 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 31.3 | 0.057 | 18.2047 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 31.3 | 0.057 | 18.2047 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 31.3 | 0.057 | 18.2047 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 10.9 | 0.020 | 52.0439 | 2.87x |
| Issue the next fetch in EXECUTE | 550.1 | 31.2 | 0.057 | 18.2491 | 1.01x |
| Hardware multiply and divide (M) | 550.1 | 31.4 | 0.057 | 18.1212 | 1.00x |
| No fetch clocks at all | 550.1 | 30.8 | 0.056 | 18.4742 | 1.02x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.06x |

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

- Timed region: 15,704 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 16,954 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=16608 slot2=15845 slot3=15757 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=53507 slot2=14086 slot3=13886 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 135.2 s, reference model 0.4 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `slli`, `sltiu`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb-ooo\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb-ooo\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb-ooo\link.ld .\build\cpu\bench\dhrystone-rv64imb-ooo\start.o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb-ooo\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb-ooo\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb-ooo\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-21 14:12:48 -0500","architecture_version":"0.14.1","commit":"def6fd9","dirty":"yes (`DEVLOG.md`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/bench/bench_profile.py`, `.claude/`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"ooo","cycles_per_run":31.408,"cpi":0.05709922553903211,"dmips_per_mhz":18.121241835655702,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"71d9321dddc917efbb313e6aab8155370c8a7597c30a92e105cfc830fd6255f6","rtl/cpu/rv64_bram_soc.sv":"7fdbaec4cda68342ac51c382b1c830c03ac624c8a1661b97c0e3335e6b17874e"}} -->

## Run 2026-11-21 14:19:23 -0500

- **Architecture:** version 0.14.1
- **Commit:** `def6fd9`, uncommitted changes: yes (`DEVLOG.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/bench/bench_profile.py`, `.claude/`, `devlog/devlog-def6fd9.md`)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, fast runtime, ooo core
- **RTL:** `rv64_ooo.sv` 71d9321dddc9, `rv64_bram_soc.sv` 7fdbaec4cda6
- **Result:** 20.7 clocks per run, 446.1 instructions per run, CPI 0.047, **27.4396 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -36.12% clocks per run against the previous run with the same build settings (2026-11-21 13:47:30 -0500, `4d74a0b`, architecture 0.13.0). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.14.1` for architecture 0.14.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.047 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 273 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 223,028 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 10,371; the timed region measured 10,371 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 3.3% |
| EXECUTE | 3.8 | 18.3% |
| MEMORY (loads and stores) | 16.3 | 78.4% |
| **Total** | **20.7** | |

Instructions that needed a bus fetch: 0.3 of 446.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| store | 55.0 | 10.1 | 48.9% | 0.1 | 0.0 | 10.0 |
| alu | 233.0 | 4.4 | 21.4% | 0.3 | 2.1 | 2.0 |
| branch | 48.0 | 3.2 | 15.4% | 0.0 | 1.1 | 2.0 |
| load | 73.0 | 2.8 | 13.5% | 0.3 | 0.4 | 2.1 |
| muldiv | 1.0 | 0.1 | 0.5% | 0.0 | 0.1 | 0.0 |
| jump | 36.0 | 0.1 | 0.3% | 0.0 | 0.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `Proc_1` | 53.0 | 5.2 | 25.0% | 0.1 | 5.0 | 1.0 |
| `strcmp` | 80.0 | 3.3 | 15.7% | 0.1 | 1.0 | 1.0 |
| `strcpy` | 97.0 | 3.1 | 15.2% | 0.0 | 3.1 | 1.0 |
| `main` | 66.0 | 2.3 | 11.0% | 0.1 | 1.0 | 0.0 |
| `Proc_8` | 29.0 | 2.1 | 10.1% | 0.1 | 2.0 | 1.0 |
| `Proc_2` | 12.0 | 1.3 | 6.2% | 0.0 | 1.0 | 1.0 |
| `Proc_6` | 23.0 | 1.1 | 5.4% | 0.1 | 1.0 | 1.0 |
| `Func_2` | 23.0 | 1.1 | 5.4% | 0.1 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 1.1 | 5.1% | 0.0 | 1.0 | 1.0 |
| `Func_1` | 15.0 | 0.0 | 0.2% | 0.0 | 0.0 | 3.0 |
| `setStats` | 0.0 | 0.0 | 0.2% | 0.0 | 0.0 | 0.0 |
| `Proc_3` | 11.0 | 0.0 | 0.2% | 0.0 | 0.0 | 1.0 |
| `Proc_7` | 15.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |
| `bench_timer` | 0.0 | 0.0 | 0.1% | 0.0 | 0.0 | 0.0 |
| `Proc_5` | 7.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |
| `Func_3` | 3.0 | 0.0 | 0.1% | 0.0 | 0.0 | 1.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 177.0 instructions per run.

Control flow per run: 21.0 branches taken, 27.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 252.0 | 0.1 |
| 2 beats (16 bytes) | 248.0 | 0.1 |
| 4 beats (32 bytes) | 224.0 | 0.2 |
| 8 beats (64 bytes) | 200.0 | 0.2 |
| 16 beats (128 bytes) | 194.0 | 0.2 |
| 32 beats (256 bytes) | 191.0 | 0.2 |
| 64 beats (512 bytes) | 181.0 | 0.2 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x08cc` | `Proc_2` | `lw a2, 0x0(a0)` | 500 | 627 | 0 | 489 |
| `0x0da0` | `strcpy` | `beq t2, a4, 0xd78 <strcpy+0x78>` | 1,500 | 499 | 0 | 497 |
| `0x07f0` | `Proc_1` | `sw a1, 0x10(s1)` | 500 | 498 | 6 | 492 |
| `0x0790` | `Proc_1` | `sd ra, 0x18(sp)` | 500 | 497 | 5 | 492 |
| `0x0d4c` | `strcpy` | `ld a5, 0x8(t0)` | 500 | 496 | 0 | 493 |
| `0x0990` | `Proc_6` | `sw a1, 0x0(s0)` | 500 | 495 | 2 | 493 |
| `0x0290` | `main` | `li s5, 0x3` | 500 | 495 | 5 | 0 |
| `0x0dd8` | `strcpy` | `sb a3, 0x0(a2)` | 2,500 | 494 | 0 | 494 |
| `0x086c` | `Proc_1` | `sw a0, 0x10(s1)` | 500 | 494 | 2 | 492 |
| `0x02a8` | `main` | `bltu a0, a1, 0x1dc <main+0x198>` | 1,000 | 494 | 1 | 489 |
| `0x093c` | `Proc_4` | `sw a2, 0xc(a1)` | 500 | 492 | 0 | 492 |
| `0x0aa8` | `Func_2` | `sd s0, 0x10(sp)` | 500 | 492 | 0 | 492 |
| `0x0dfc` | `strcmp` | `beqz a3, 0xf04 <strcmp+0x11c>` | 1,500 | 492 | 0 | 2 |
| `0x0e58` | `strcmp` | `sub a5, a5, a3` | 500 | 492 | 2 | 0 |
| `0x0a4c` | `Proc_8` | `sw a4, 0x4(a5)` | 500 | 492 | 0 | 492 |

**Instruction mix** (per run): `addi` 127.0, `ld` 38.0, `jalr` 32.0, `auipc` 23.0, `sd` 23.0, `sw` 23.0, `bne` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `lw` 13.0, `sb` 9.0, `sh2add` 9.0, `or` 8.0, `srl` 7.0, `sll` 7.0, `sub` 6.0, `orc.b` 6.0, `jal` 4.0, `xor` 4.0, `add` 4.0, `sltiu` 3.0, `slli` 2.0, `srli` 2.0, `addiw` 2.0, `sh3add` 2.0, `bltu` 2.0, `orn` 1.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `sh1add` 1.0, `divw` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 446.1 | 20.7 | 0.047 | 27.4396 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 446.1 | 20.6 | 0.046 | 27.6368 | 1.01x |
| Instruction cache, 4 beats (32 bytes) | 446.1 | 20.6 | 0.046 | 27.6475 | 1.01x |
| Instruction cache, 8 beats (64 bytes) | 446.1 | 20.6 | 0.046 | 27.6529 | 1.01x |
| Instruction cache, 16 beats (128 bytes) | 446.1 | 20.6 | 0.046 | 27.6663 | 1.01x |
| Instruction cache, 32 beats (256 bytes) | 446.1 | 20.6 | 0.046 | 27.6663 | 1.01x |
| Instruction cache, 64 beats (512 bytes) | 446.1 | 20.6 | 0.046 | 27.6663 | 1.01x |
| Issue loads and stores in EXECUTE | 446.1 | 4.6 | 0.010 | 124.7046 | 4.54x |
| Issue the next fetch in EXECUTE | 446.1 | 20.5 | 0.046 | 27.7771 | 1.01x |
| Hardware multiply and divide (M) | 446.1 | 20.7 | 0.047 | 27.4396 | 1.00x |
| No fetch clocks at all | 446.1 | 20.1 | 0.045 | 28.3866 | 1.03x |
| One clock per instruction | 446.1 | 446.1 | 1.000 | 1.2760 | 0.05x |

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

- Timed region: 10,371 clocks, 223,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 11,682 clocks, 229,793 instructions.
- Differential run, up to 0 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=11284 slot2=10436 slot3=10295 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=40130 slot2=11603 slot3=11373 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 92.6 s, reference model 0.3 s.
- Instructions executed: `add`, `addi`, `addiw`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`, `bseti`, `div`, `divw`, `ebreak`, `jal`, `jalr`, `lbu`, `ld`, `lui`, `lw`, `lwu`, `mulw`, `or`, `orc.b`, `orn`, `sb`, `sd`, `sh1add`, `sh2add`, `sh3add`, `sll`, `slli`, `sltiu`, `srl`, `srli`, `sub`, `subw`, `sw`, `xor`.

Build commands:

```text
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -c .\sim\cpu\bench\start.S -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\start.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone_main.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone_main.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=gnu89 -fno-inline -Wno-unknown-pragmas -Wno-implicit-int -Wno-implicit-function-declaration -Wno-deprecated-non-prototype -Wno-return-type -c .\sim\cpu\bench\vendor\dhrystone\dhrystone.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -c .\sim\cpu\bench\dhrystone_port.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone_port.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -mcmodel=medany -msmall-data-limit=0 -mno-relax -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-common -nostdlibinc -I .\sim\cpu\bench\include -I .\sim\cpu\bench\vendor\dhrystone -std=c11 -Wall -Wextra -Werror -DBENCH_FAST_STRINGS -c .\sim\cpu\bench\runtime.c -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\runtime.o
C:\Program Files\LLVM\bin\clang.exe --target=riscv64-unknown-elf -march=rv64im_zba_zbb_zbs_zifencei -mabi=lp64 -nostdlib -fuse-ld=lld -Wl,--no-relax -Wl,-T,.\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\link.ld .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\start.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone_main.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\dhrystone_port.o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\runtime.o -o .\build\cpu\bench\dhrystone-rv64imb-fastrt-ooo\bench.elf
```

<!-- dhrystone-run {"time":"2026-11-21 14:19:23 -0500","architecture_version":"0.14.1","commit":"def6fd9","dirty":"yes (`DEVLOG.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/visualizer-verification.json`, `sim/cpu/bench/bench_profile.py`, `.claude/`, `devlog/devlog-def6fd9.md`)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"fast","core":"ooo","cycles_per_run":20.742,"cpi":0.046500470788683135,"dmips_per_mhz":27.439589411545384,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"71d9321dddc917efbb313e6aab8155370c8a7597c30a92e105cfc830fd6255f6","rtl/cpu/rv64_bram_soc.sv":"7fdbaec4cda68342ac51c382b1c830c03ac624c8a1661b97c0e3335e6b17874e"}} -->
