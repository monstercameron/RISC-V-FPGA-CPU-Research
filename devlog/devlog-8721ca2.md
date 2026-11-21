# Development log for commit `8721ca2`

Commit subject: Out-of-order core: loop predictor, two-way data cache, paired store writes, review fixes (architecture 0.11.0)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-21 11:14:47 -0500

- **Architecture:** version 0.11.1
- **Commit:** `8721ca2`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/test_cpu.py`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, ooo core
- **RTL:** `rv64_ooo.sv` cc463c46fee9, `rv64_bram_soc.sv` bf386fa7c326
- **Result:** 92.0 clocks per run, 550.1 instructions per run, CPI 0.167, **6.1878 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -0.04% clocks per run against the previous run with the same build settings (2026-11-21 10:55:26 -0500, `322739e`, architecture 0.11.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.11.1` for architecture 0.11.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.167 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 171 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 275,031 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 45,990; the timed region measured 45,990 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.7% |
| EXECUTE | 32.2 | 35.0% |
| MEMORY (loads and stores) | 59.2 | 64.3% |
| **Total** | **92.0** | |

Instructions that needed a bus fetch: 0.3 of 550.1 per run (0.0%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 235.0 | 51.4 | 55.9% | 0.3 | 12.1 | 39.0 |
| load | 118.0 | 13.3 | 14.5% | 0.2 | 3.0 | 10.1 |
| branch | 87.0 | 13.1 | 14.3% | 0.0 | 12.1 | 1.0 |
| store | 76.0 | 9.1 | 9.9% | 0.0 | 0.0 | 9.0 |
| jump | 34.0 | 5.0 | 5.5% | 0.0 | 5.0 | 0.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 31.0 | 33.8% | 0.0 | 31.0 | 1.0 |
| `strcmp` | 124.0 | 16.1 | 17.5% | 0.0 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 11.2 | 12.1% | 0.1 | 10.0 | 1.0 |
| `main` | 66.0 | 7.1 | 7.7% | 0.1 | 2.0 | 0.0 |
| `Proc_8` | 29.0 | 6.1 | 6.6% | 0.1 | 6.0 | 1.0 |
| `Proc_7` | 15.0 | 5.0 | 5.5% | 0.0 | 3.0 | 1.0 |
| `Proc_6` | 23.0 | 4.1 | 4.4% | 0.1 | 2.0 | 1.0 |
| `Func_2` | 23.0 | 3.1 | 3.4% | 0.1 | 2.0 | 1.0 |
| `Proc_4` | 12.0 | 2.0 | 2.2% | 0.0 | 1.0 | 1.0 |
| `Proc_2` | 12.0 | 2.0 | 2.2% | 0.0 | 1.0 | 1.0 |
| `Proc_5` | 7.0 | 2.0 | 2.2% | 0.0 | 1.0 | 1.0 |
| `Proc_3` | 11.0 | 1.0 | 1.1% | 0.0 | 0.0 | 1.0 |
| `Func_1` | 15.0 | 1.0 | 1.1% | 0.0 | 0.0 | 3.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
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
| 16 beats (128 bytes) | 150.0 | 0.2 |
| 32 beats (256 bytes) | 143.0 | 0.2 |
| 64 beats (512 bytes) | 127.1 | 0.2 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d10` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,001 | 0 | 14,996 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 2,518 | 0 | 6 |
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 2,504 | 1 | 0 |
| `0x0d34` | `strcmp` | `addi a1, a1, 0x1` | 9,500 | 1,995 | 0 | 2 |
| `0x0a04` | `Proc_7` | `ret` | 1,500 | 1,004 | 3 | 2 |
| `0x0a54` | `Proc_8` | `lw a1, 0x0(a6)` | 500 | 505 | 4 | 501 |
| `0x0a84` | `Func_1` | `beqz a1, 0xa90 <Func_1+0x14>` | 1,500 | 504 | 1 | 0 |
| `0x07b8` | `Proc_1` | `ld a1, 0x28(a0)` | 500 | 504 | 0 | 502 |
| `0x0d1c` | `strcmp` | `lbu a2, 0x0(a0)` | 500 | 503 | 4 | 0 |
| `0x07c8` | `Proc_1` | `ld a1, 0x18(a0)` | 500 | 503 | 2 | 501 |
| `0x0afc` | `Func_2` | `ld s0, 0x10(sp)` | 500 | 502 | 4 | 498 |
| `0x09f8` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 502 | 0 | 502 |
| `0x07d8` | `Proc_1` | `ld a1, 0x8(a0)` | 500 | 502 | 0 | 502 |
| `0x0ab0` | `Func_2` | `mv s0, a1` | 500 | 501 | 2 | 0 |
| `0x0a30` | `Proc_8` | `sh2add a0, a2, a2` | 500 | 501 | 2 | 498 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 92.0 | 0.167 | 6.1878 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 91.9 | 0.167 | 6.1964 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 91.9 | 0.167 | 6.1964 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 91.8 | 0.167 | 6.1968 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 91.8 | 0.167 | 6.1982 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 91.8 | 0.167 | 6.1983 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 91.8 | 0.167 | 6.1984 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 32.9 | 0.060 | 17.3163 | 2.80x |
| Issue the next fetch in EXECUTE | 550.1 | 91.7 | 0.167 | 6.2050 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 92.0 | 0.167 | 6.1878 | 1.00x |
| No fetch clocks at all | 550.1 | 91.4 | 0.166 | 6.2300 | 1.01x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.17x |

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

- Timed region: 45,990 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 48,347 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=47862 slot2=45284 slot3=42995 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=154922 slot2=47763 slot3=42882 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 78.6 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-21 11:14:47 -0500","architecture_version":"0.11.1","commit":"8721ca2","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/test_cpu.py`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"ooo","cycles_per_run":91.98,"cpi":0.16721812165945532,"dmips_per_mhz":6.187779556145622,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"cc463c46fee91ddbd63e9a8f32458177312c82d663273f5c42a56d62c63ccf0f","rtl/cpu/rv64_bram_soc.sv":"bf386fa7c326798714dcefec841ea70d395e8b278006bf0ebbb7935bd9b8497b"}} -->

## Run 2026-11-21 11:32:21 -0500

- **Architecture:** version 0.11.1
- **Commit:** `8721ca2`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/bench/tb_bench.sv`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, ooo core
- **RTL:** `rv64_ooo.sv` f452bd4dfc01, `rv64_bram_soc.sv` bf386fa7c326
- **Result:** 89.1 clocks per run, 550.1 instructions per run, CPI 0.162, **6.3878 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -3.13% clocks per run against the previous run with the same build settings (2026-11-21 11:14:47 -0500, `8721ca2`, architecture 0.11.1). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.11.1` for architecture 0.11.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.162 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 201 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 275,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 44,550; the timed region measured 44,550 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.7% |
| EXECUTE | 34.3 | 38.5% |
| MEMORY (loads and stores) | 54.2 | 60.8% |
| **Total** | **89.1** | |

Instructions that needed a bus fetch: 0.2 of 550.1 per run (0.0%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| store | 76.0 | 31.1 | 34.8% | 0.0 | 0.0 | 31.0 |
| branch | 87.0 | 25.1 | 28.1% | 0.0 | 22.0 | 3.0 |
| alu | 235.0 | 17.5 | 19.6% | 0.3 | 8.1 | 9.1 |
| load | 118.0 | 9.4 | 10.6% | 0.2 | 0.2 | 9.1 |
| jump | 34.0 | 6.1 | 6.8% | 0.1 | 4.0 | 2.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 24.0 | 27.0% | 0.0 | 24.0 | 1.0 |
| `strcmp` | 124.0 | 21.1 | 23.7% | 0.0 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 10.2 | 11.4% | 0.1 | 10.0 | 1.0 |
| `main` | 66.0 | 9.2 | 10.4% | 0.1 | 4.0 | 0.0 |
| `Func_2` | 23.0 | 7.1 | 8.0% | 0.1 | 2.0 | 1.0 |
| `Proc_6` | 23.0 | 4.1 | 4.6% | 0.1 | 4.0 | 1.0 |
| `Proc_8` | 29.0 | 4.1 | 4.6% | 0.1 | 4.0 | 1.0 |
| `Proc_7` | 15.0 | 2.0 | 2.3% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 2.0 | 2.3% | 0.0 | 1.0 | 1.0 |
| `Proc_3` | 11.0 | 2.0 | 2.3% | 0.0 | 2.0 | 1.0 |
| `Func_1` | 15.0 | 1.1 | 1.2% | 0.0 | 0.0 | 3.0 |
| `Proc_2` | 12.0 | 1.0 | 1.2% | 0.0 | 1.0 | 1.0 |
| `Proc_5` | 7.0 | 1.0 | 1.1% | 0.0 | 1.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
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
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 9,470 | 1 | 1 |
| `0x0d0c` | `strcpy` | `sb a3, 0x0(a2)` | 15,500 | 7,500 | 0 | 7,500 |
| `0x0d04` | `strcpy` | `lbu a3, 0x0(a1)` | 15,500 | 1,510 | 0 | 1,510 |
| `0x0acc` | `Func_2` | `mv a0, s1` | 500 | 1,501 | 4 | 0 |
| `0x0d14` | `strcpy` | `bnez a3, 0xd04 <strcpy+0x4>` | 15,500 | 1,007 | 0 | 1,007 |
| `0x0d10` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 1,000 | 0 | 1,000 |
| `0x0d08` | `strcpy` | `addi a1, a1, 0x1` | 15,500 | 998 | 0 | 998 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 518 | 0 | 1 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 511 | 1 | 0 |
| `0x0270` | `main` | `jalr 0x79c(ra) <Proc_8>` | 500 | 503 | 4 | 497 |
| `0x0868` | `Proc_1` | `li a0, 0x6` | 500 | 503 | 5 | 498 |
| `0x0888` | `Proc_1` | `lw a0, 0x10(s1)` | 500 | 502 | 3 | 499 |
| `0x0ad8` | `Func_2` | `jalr 0x248(ra) <strcmp>` | 500 | 501 | 2 | 0 |
| `0x07e8` | `Proc_1` | `sd a0, 0x0(s1)` | 500 | 501 | 2 | 499 |
| `0x09d8` | `Proc_6` | `sw s1, 0x0(s0)` | 500 | 501 | 2 | 499 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 89.1 | 0.162 | 6.3878 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 89.0 | 0.162 | 6.3945 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 89.0 | 0.162 | 6.3950 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 89.0 | 0.162 | 6.3953 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 89.0 | 0.162 | 6.3965 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 89.0 | 0.162 | 6.3967 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 89.0 | 0.162 | 6.3967 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 35.0 | 0.064 | 16.2643 | 2.55x |
| Issue the next fetch in EXECUTE | 550.1 | 88.9 | 0.162 | 6.4050 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 89.1 | 0.162 | 6.3878 | 1.00x |
| No fetch clocks at all | 550.1 | 88.5 | 0.161 | 6.4320 | 1.01x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.16x |

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

- Timed region: 44,550 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 46,881 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=46414 slot2=44761 slot3=42491 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=116688 slot2=46025 slot3=36929 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 73.9 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-21 11:32:21 -0500","architecture_version":"0.11.1","commit":"8721ca2","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/bench/tb_bench.sv`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"ooo","cycles_per_run":89.1,"cpi":0.16198232920045086,"dmips_per_mhz":6.387788592303864,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"f452bd4dfc01530c73ccf00362e2e7e616ca9e7bb278ce2e7df6b54add25ab08","rtl/cpu/rv64_bram_soc.sv":"bf386fa7c326798714dcefec841ea70d395e8b278006bf0ebbb7935bd9b8497b"}} -->

## Run 2026-11-21 11:36:23 -0500

- **Architecture:** version 0.11.1
- **Commit:** `8721ca2`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, fast runtime, ooo core
- **RTL:** `rv64_ooo.sv` f452bd4dfc01, `rv64_bram_soc.sv` bf386fa7c326
- **Result:** 75.2 clocks per run, 446.1 instructions per run, CPI 0.169, **7.5667 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -19.17% clocks per run against the previous run with the same build settings (2026-11-21 11:00:22 -0500, `322739e`, architecture 0.11.0). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.11.1` for architecture 0.11.1. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.169 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 201 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 223,029 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 37,609; the timed region measured 37,609 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.9% |
| EXECUTE | 35.3 | 47.0% |
| MEMORY (loads and stores) | 39.2 | 52.1% |
| **Total** | **75.2** | |

Instructions that needed a bus fetch: 0.3 of 446.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 234.0 | 31.6 | 41.9% | 0.4 | 19.1 | 12.0 |
| store | 55.0 | 17.0 | 22.7% | 0.0 | 0.0 | 17.0 |
| branch | 48.0 | 13.1 | 17.4% | 0.0 | 10.0 | 3.0 |
| load | 73.0 | 9.4 | 12.6% | 0.2 | 2.1 | 7.1 |
| jump | 36.0 | 4.1 | 5.5% | 0.1 | 4.0 | 0.1 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcmp` | 80.0 | 15.1 | 20.1% | 0.1 | 0.0 | 1.0 |
| `strcpy` | 97.0 | 12.1 | 16.1% | 0.0 | 9.0 | 1.0 |
| `main` | 66.0 | 11.2 | 14.9% | 0.1 | 3.0 | 0.0 |
| `Proc_1` | 53.0 | 10.2 | 13.5% | 0.1 | 10.0 | 1.0 |
| `Proc_8` | 29.0 | 7.1 | 9.4% | 0.1 | 6.0 | 1.0 |
| `Func_2` | 23.0 | 4.1 | 5.5% | 0.1 | 2.0 | 1.0 |
| `Proc_6` | 23.0 | 3.1 | 4.2% | 0.1 | 3.0 | 1.0 |
| `Func_1` | 15.0 | 3.0 | 4.0% | 0.0 | 0.0 | 3.0 |
| `Proc_7` | 15.0 | 3.0 | 4.0% | 0.0 | 2.0 | 1.0 |
| `Proc_2` | 12.0 | 2.0 | 2.7% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 2.0 | 2.7% | 0.0 | 1.0 | 1.0 |
| `Proc_3` | 11.0 | 1.0 | 1.4% | 0.0 | 1.0 | 1.0 |
| `Proc_5` | 7.0 | 1.0 | 1.3% | 0.0 | 1.0 | 1.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `Func_3` | 3.0 | 0.0 | 0.0% | 0.0 | 0.0 | 1.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 177.0 instructions per run.

Control flow per run: 21.0 branches taken, 27.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 252.0 | 0.1 |
| 2 beats (16 bytes) | 248.0 | 0.1 |
| 4 beats (32 bytes) | 224.0 | 0.1 |
| 8 beats (64 bytes) | 200.0 | 0.1 |
| 16 beats (128 bytes) | 194.0 | 0.1 |
| 32 beats (256 bytes) | 191.0 | 0.1 |
| 64 beats (512 bytes) | 181.0 | 0.1 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 2,004 | 6 | 499 |
| `0x0a84` | `Func_1` | `beqz a1, 0xa90 <Func_1+0x14>` | 1,500 | 1,003 | 1 | 0 |
| `0x0d2c` | `strcpy` | `bnez a4, 0xd10 <strcpy+0x10>` | 1,000 | 982 | 0 | 491 |
| `0x02ac` | `main` | `lw s6, 0xdc(sp)` | 1,000 | 515 | 4 | 2 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 509 | 1 | 0 |
| `0x0a54` | `Proc_8` | `lw a1, 0x0(a6)` | 500 | 507 | 2 | 500 |
| `0x09f8` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 505 | 3 | 502 |
| `0x0ed0` | `strcmp` | `zext.b a2, a2` | 500 | 504 | 5 | 0 |
| `0x0a34` | `Proc_8` | `lw a2, 0x10(a3)` | 500 | 503 | 2 | 2 |
| `0x0e90` | `strcmp` | `beq t0, a7, 0xe64 <strcmp+0x7c>` | 500 | 502 | 0 | 0 |
| `0x0888` | `Proc_1` | `lw a0, 0x10(s1)` | 500 | 502 | 3 | 499 |
| `0x0de0` | `strcpy` | `bnez a3, 0xdd0 <strcpy+0xd0>` | 2,500 | 501 | 0 | 499 |
| `0x0ad8` | `Func_2` | `jalr 0x314(ra) <strcmp>` | 500 | 501 | 2 | 0 |
| `0x07f8` | `Proc_1` | `sd a0, 0x0(s1)` | 500 | 501 | 2 | 499 |
| `0x09d8` | `Proc_6` | `sw s1, 0x0(s0)` | 500 | 501 | 2 | 499 |

**Instruction mix** (per run): `addi` 127.0, `ld` 38.0, `jalr` 32.0, `auipc` 23.0, `sd` 23.0, `sw` 23.0, `bne` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `lw` 13.0, `xor` 13.0, `or` 11.0, `sb` 9.0, `srli` 8.0, `srl` 7.0, `sll` 7.0, `sub` 6.0, `jal` 4.0, `add` 4.0, `sltiu` 3.0, `slli` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 446.1 | 75.2 | 0.169 | 7.5667 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 446.1 | 75.1 | 0.168 | 7.5798 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 446.1 | 75.1 | 0.168 | 7.5806 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 446.1 | 75.1 | 0.168 | 7.5810 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 446.1 | 75.1 | 0.168 | 7.5818 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 446.1 | 75.1 | 0.168 | 7.5818 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 446.1 | 75.1 | 0.168 | 7.5818 | 1.00x |
| Issue loads and stores in EXECUTE | 446.1 | 36.1 | 0.081 | 15.7616 | 2.08x |
| Issue the next fetch in EXECUTE | 446.1 | 74.9 | 0.168 | 7.5946 | 1.00x |
| Hardware multiply and divide (M) | 446.1 | 75.2 | 0.169 | 7.5667 | 1.00x |
| No fetch clocks at all | 446.1 | 74.5 | 0.167 | 7.6382 | 1.01x |
| One clock per instruction | 446.1 | 446.1 | 1.000 | 1.2760 | 0.17x |

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

- Timed region: 37,609 clocks, 223,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 39,988 clocks, 229,793 instructions.
- Differential run, up to 0 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=39461 slot2=34765 slot3=31475 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=96894 slot2=35932 slot3=31949 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 57.9 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-21 11:36:23 -0500","architecture_version":"0.11.1","commit":"8721ca2","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"fast","core":"ooo","cycles_per_run":75.218,"cpi":0.16862753889611262,"dmips_per_mhz":7.5666989759668475,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"f452bd4dfc01530c73ccf00362e2e7e616ca9e7bb278ce2e7df6b54add25ab08","rtl/cpu/rv64_bram_soc.sv":"bf386fa7c326798714dcefec841ea70d395e8b278006bf0ebbb7935bd9b8497b"}} -->
