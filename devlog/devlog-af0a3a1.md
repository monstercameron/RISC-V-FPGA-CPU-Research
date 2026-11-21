# Development log for commit `af0a3a1`

Commit subject: Out-of-order core: fetch the second instruction from the next beat (architecture 0.9.4)

Detailed records of benchmark runs made while this commit was checked out. Each entry says whether the working tree had uncommitted changes. Daily summaries and the index of all runs are in [DEVLOG.md](../DEVLOG.md).

## Run 2026-11-21 08:51:11 -0500

- **Architecture:** version 0.10.0
- **Commit:** `af0a3a1`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/bench/run_bench.py`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, ooo core
- **RTL:** `rv64_ooo.sv` d71a5889c2fa, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 131.8 clocks per run, 550.1 instructions per run, CPI 0.240, **4.3169 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -63.45% clocks per run against the previous run with the same build settings (2026-11-21 07:33:22 -0500, `8f207a0`, architecture 0.9.4). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.10.0` for architecture 0.10.0. Automated self-assessment, not a review.

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

- **Gates met:** HG4, HG5, PG4. **Not met:** HG1, HG2, HG3, HG6, HG7, HG8, PG1, PG2, PG3, PG5.
- **"Verified in simulation":** not granted: HG1; HG2; HG6; R1 0% < 60%; R3 0% < 50%.
- **"Good":** not granted: HG1; HG2; HG3; HG6; HG7; HG8; total 6.1 < 75; R1 0% < 80%; an R1 criterion under 3; R2 0% < 70%; R3 0% < 70%; R6 0% < 70%; a dimension under 50%.
- **"Performant for a multicycle FPGA core":** not granted: "Good" not granted; PG1; PG2; PG3; PG5; R4 6% < 75%; R4.1 = 2 < 3; R4.2 = 0 < 3; R4.3 = 0 < 3; R5 0% < 60%.
- **Computed this run:** R4.1 = 2 (CPI 0.240 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 not met (Latest local regression ran on different RTL; rerun sim/cpu/run.sh.)

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

Measured on the core and synchronous RAM: 275,030 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 65,922; the timed region measured 65,922 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.5% |
| EXECUTE | 55.0 | 41.8% |
| MEMORY (loads and stores) | 76.2 | 57.8% |
| **Total** | **131.8** | |

Instructions that needed a bus fetch: 0.3 of 550.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 235.0 | 66.4 | 50.3% | 0.3 | 22.0 | 44.0 |
| branch | 87.0 | 26.1 | 19.8% | 0.0 | 23.0 | 3.0 |
| store | 76.0 | 17.1 | 13.0% | 0.0 | 0.0 | 17.1 |
| load | 118.0 | 16.3 | 12.3% | 0.2 | 6.0 | 10.1 |
| jump | 34.0 | 6.1 | 4.6% | 0.1 | 4.0 | 2.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 32.0 | 24.3% | 0.0 | 32.0 | 1.0 |
| `strcmp` | 124.0 | 29.0 | 22.0% | 0.0 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 17.2 | 13.0% | 0.1 | 16.0 | 1.0 |
| `main` | 66.0 | 11.1 | 8.5% | 0.1 | 3.0 | 0.0 |
| `Proc_8` | 29.0 | 10.1 | 7.6% | 0.1 | 9.0 | 1.0 |
| `Proc_6` | 23.0 | 6.1 | 4.6% | 0.1 | 4.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 4.6% | 0.0 | 4.0 | 1.0 |
| `Func_2` | 23.0 | 5.1 | 3.9% | 0.1 | 3.0 | 1.0 |
| `Proc_2` | 12.0 | 5.0 | 3.8% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 3.0 | 2.3% | 0.0 | 2.0 | 1.0 |
| `Func_1` | 15.0 | 3.0 | 2.3% | 0.0 | 0.0 | 3.0 |
| `Proc_5` | 7.0 | 3.0 | 2.3% | 0.0 | 2.0 | 1.0 |
| `Proc_3` | 11.0 | 1.0 | 0.8% | 0.0 | 0.0 | 1.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
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
| 64 beats (512 bytes) | 127.1 | 0.2 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x0d10` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,500 | 0 | 15,496 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 9,498 | 2 | 7 |
| `0x0d40` | `strcmp` | `zext.b a0, a2` | 500 | 2,000 | 4 | 0 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 1,503 | 7 | 499 |
| `0x0a04` | `Proc_7` | `ret` | 1,500 | 1,500 | 2 | 500 |
| `0x0d50` | `strcmp` | `sub a0, a0, a1` | 500 | 1,000 | 2 | 0 |
| `0x08d4` | `Proc_2` | `sub a2, a2, a1` | 500 | 999 | 0 | 0 |
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 508 | 0 | 1 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 506 | 4 | 0 |
| `0x0a00` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 504 | 2 | 502 |
| `0x07d8` | `Proc_1` | `ld a1, 0x8(a0)` | 500 | 504 | 2 | 502 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 503 | 2 | 0 |
| `0x0d1c` | `strcmp` | `lbu a2, 0x0(a0)` | 500 | 503 | 4 | 0 |
| `0x09f8` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 503 | 4 | 499 |
| `0x07c0` | `Proc_1` | `ld a1, 0x20(a0)` | 500 | 503 | 2 | 501 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 131.8 | 0.240 | 4.3169 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 131.7 | 0.240 | 4.3202 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 131.7 | 0.240 | 4.3203 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 131.7 | 0.239 | 4.3207 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 131.7 | 0.239 | 4.3215 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 131.7 | 0.239 | 4.3216 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 131.7 | 0.239 | 4.3219 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 55.7 | 0.101 | 10.2108 | 2.37x |
| Issue the next fetch in EXECUTE | 550.1 | 131.5 | 0.239 | 4.3266 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 131.8 | 0.240 | 4.3169 | 1.00x |
| No fetch clocks at all | 550.1 | 131.2 | 0.239 | 4.3377 | 1.00x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.24x |

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

- Timed region: 65,922 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 68,493 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=68072 slot2=52068 slot3=43476 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=197210 slot2=43151 slot3=41141 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 73.8 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-21 08:51:11 -0500","architecture_version":"0.10.0","commit":"af0a3a1","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, `sim/cpu/bench/run_bench.py`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"ooo","cycles_per_run":131.844,"cpi":0.23969021561284223,"dmips_per_mhz":4.316859042309656,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"d71a5889c2faba44103321fed42cae96de2543b9f2b8a07b3bc57467ae925537","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-21 09:49:20 -0500

- **Architecture:** version 0.10.0
- **Commit:** `af0a3a1`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, reference runtime, ooo core
- **RTL:** `rv64_ooo.sv` c406a99e9105, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 131.9 clocks per run, 550.1 instructions per run, CPI 0.240, **4.3161 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** +0.02% clocks per run against the previous run with the same build settings (2026-11-21 08:51:11 -0500, `af0a3a1`, architecture 0.10.0)

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.10.0` for architecture 0.10.0. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.240 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 168 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 275,030 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 65,933; the timed region measured 65,933 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.6 | 0.5% |
| EXECUTE | 55.1 | 41.8% |
| MEMORY (loads and stores) | 76.2 | 57.8% |
| **Total** | **131.9** | |

Instructions that needed a bus fetch: 0.3 of 550.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 235.0 | 66.3 | 50.3% | 0.3 | 22.0 | 44.0 |
| branch | 87.0 | 26.0 | 19.8% | 0.0 | 23.0 | 3.0 |
| store | 76.0 | 17.1 | 12.9% | 0.0 | 0.0 | 17.0 |
| load | 118.0 | 16.3 | 12.4% | 0.2 | 6.0 | 10.1 |
| jump | 34.0 | 6.1 | 4.6% | 0.0 | 4.0 | 2.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 157.0 | 32.0 | 24.3% | 0.0 | 32.0 | 1.0 |
| `strcmp` | 124.0 | 29.1 | 22.0% | 0.0 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 17.2 | 13.0% | 0.1 | 16.0 | 1.0 |
| `main` | 66.0 | 11.2 | 8.5% | 0.1 | 3.0 | 0.0 |
| `Proc_8` | 29.0 | 10.1 | 7.6% | 0.1 | 9.0 | 1.0 |
| `Proc_6` | 23.0 | 6.1 | 4.6% | 0.1 | 4.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 4.6% | 0.0 | 4.0 | 1.0 |
| `Func_2` | 23.0 | 5.1 | 3.9% | 0.1 | 3.0 | 1.0 |
| `Proc_2` | 12.0 | 5.0 | 3.8% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 3.0 | 2.3% | 0.0 | 2.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 2.3% | 0.0 | 2.0 | 1.0 |
| `Func_1` | 15.0 | 3.0 | 2.3% | 0.0 | 0.0 | 3.0 |
| `Proc_3` | 11.0 | 1.0 | 0.8% | 0.0 | 0.0 | 1.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
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
| `0x0d10` | `strcpy` | `addi a2, a2, 0x1` | 15,500 | 15,500 | 1 | 15,493 |
| `0x0d2c` | `strcmp` | `bne a2, a3, 0xd40 <strcmp+0x24>` | 10,000 | 9,495 | 2 | 5 |
| `0x0d40` | `strcmp` | `zext.b a0, a2` | 500 | 2,000 | 4 | 0 |
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 1,503 | 7 | 499 |
| `0x0a04` | `Proc_7` | `ret` | 1,500 | 1,500 | 2 | 500 |
| `0x0d50` | `strcmp` | `sub a0, a0, a1` | 500 | 1,000 | 2 | 0 |
| `0x08d4` | `Proc_2` | `sub a2, a2, a1` | 500 | 999 | 0 | 0 |
| `0x0d3c` | `strcmp` | `bnez a2, 0xd28 <strcmp+0xc>` | 9,500 | 509 | 0 | 2 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 506 | 4 | 0 |
| `0x07c0` | `Proc_1` | `ld a1, 0x20(a0)` | 500 | 505 | 4 | 501 |
| `0x0d1c` | `strcmp` | `lbu a2, 0x0(a0)` | 500 | 503 | 4 | 0 |
| `0x09f8` | `Proc_7` | `addi a1, a0, 0x2` | 1,500 | 503 | 3 | 500 |
| `0x0a00` | `Proc_7` | `sw a1, 0x0(a2)` | 1,500 | 503 | 2 | 501 |
| `0x07c8` | `Proc_1` | `ld a1, 0x18(a0)` | 500 | 503 | 2 | 501 |
| `0x0a80` | `Func_1` | `zext.b a1, a1` | 1,500 | 502 | 1 | 0 |

**Instruction mix** (per run): `addi` 175.0, `lbu` 79.0, `bne` 75.0, `sb` 33.0, `jalr` 32.0, `ld` 26.0, `auipc` 23.0, `sw` 23.0, `sd` 20.0, `lw` 13.0, `xor` 12.0, `andi` 8.0, `beq` 7.0, `add` 4.0, `sltiu` 3.0, `or` 3.0, `jal` 2.0, `sub` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 550.1 | 131.9 | 0.240 | 4.3161 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 550.1 | 131.8 | 0.240 | 4.3198 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 550.1 | 131.8 | 0.240 | 4.3199 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 550.1 | 131.7 | 0.239 | 4.3203 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 550.1 | 131.7 | 0.239 | 4.3211 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 550.1 | 131.7 | 0.239 | 4.3213 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 550.1 | 131.7 | 0.239 | 4.3213 | 1.00x |
| Issue loads and stores in EXECUTE | 550.1 | 55.8 | 0.101 | 10.2046 | 2.36x |
| Issue the next fetch in EXECUTE | 550.1 | 131.6 | 0.239 | 4.3255 | 1.00x |
| Hardware multiply and divide (M) | 550.1 | 131.9 | 0.240 | 4.3161 | 1.00x |
| No fetch clocks at all | 550.1 | 131.2 | 0.239 | 4.3371 | 1.00x |
| One clock per instruction | 550.1 | 550.1 | 1.000 | 1.0347 | 0.24x |

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

- Timed region: 65,933 clocks, 275,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 68,514 clocks, 281,929 instructions.
- Differential run, up to 0 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=68089 slot2=52065 slot3=43473 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 321,728 events, `DONE retirements=281929 cycles=197213 slot2=43153 slot3=41108 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 77.9 s, reference model 0.4 s.
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

<!-- dhrystone-run {"time":"2026-11-21 09:49:20 -0500","architecture_version":"0.10.0","commit":"af0a3a1","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"reference","core":"ooo","cycles_per_run":131.866,"cpi":0.23973021124968186,"dmips_per_mhz":4.316138834682741,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"c406a99e9105841472d2273f42cb840d7a781563b8230c5aa79f31127c140dc4","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->

## Run 2026-11-21 09:54:57 -0500

- **Architecture:** version 0.10.0
- **Commit:** `af0a3a1`, uncommitted changes: yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)
- **Build:** clang version 23.1.5, `-O2`, `rv64im_zba_zbb_zbs_zifencei`, 64 KiB RAM, fast runtime, ooo core
- **RTL:** `rv64_ooo.sv` c406a99e9105, `rv64_bram_soc.sv` 1043cf332225
- **Result:** 147.9 clocks per run, 446.1 instructions per run, CPI 0.332, **3.8484 DMIPS/MHz** (500 runs; non-compliant simulation run, evidence class E1)
- **Checks:** 17/17 result values; traces match the reference model at 0 and 7 wait cycles
- **Trend:** -57.96% clocks per run against the previous run with the same build settings (2026-11-21 07:36:09 -0500, `8f207a0`, architecture 0.9.4). **Change over 2%: explain it in DEVLOG.md for this day.**

### Rubric scorecard

Rubric revision 1; evidence assessed 2026-11-20 at `cpu-v0.10.0` for architecture 0.10.0. Automated self-assessment, not a review.

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
- **Computed this run:** R4.1 = 2 (CPI 0.332 against the multicycle bars of 4.0 (meets) and 3.0 (exceeds) gives 4; capped at 2 because the benchmark set lacks CoreMark); HG2 met (Regression PASS on the current RTL: 168 runs, 106 instruction names.)

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

Measured on the core and synchronous RAM: 223,030 retired instructions over 500 runs, with the clocks each spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to 73,947; the timed region measured 73,947 (difference +0, from where the region starts and stops inside the marker stores).

| Core state | Clocks per run | Share |
|---|---:|---:|
| FETCH (waiting for instructions) | 0.7 | 0.5% |
| EXECUTE | 84.0 | 56.8% |
| MEMORY (loads and stores) | 63.2 | 42.7% |
| **Total** | **147.9** | |

Instructions that needed a bus fetch: 0.3 of 446.1 per run (0.1%).

**By instruction class** (per run):

| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |
|---|---:|---:|---:|---:|---:|---:|
| alu | 234.0 | 62.4 | 42.2% | 0.4 | 44.0 | 18.0 |
| load | 73.0 | 29.4 | 19.8% | 0.2 | 12.0 | 17.1 |
| branch | 48.0 | 20.1 | 13.6% | 0.1 | 14.0 | 6.0 |
| store | 55.0 | 19.1 | 12.9% | 0.0 | 0.0 | 19.0 |
| jump | 36.0 | 17.1 | 11.5% | 0.1 | 14.0 | 3.0 |

**By function** (per run; calls counted at the call instruction):

| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |
|---|---:|---:|---:|---:|---:|---:|
| `strcpy` | 97.0 | 28.1 | 19.0% | 0.0 | 10.0 | 1.0 |
| `strcmp` | 80.0 | 25.1 | 17.0% | 0.1 | 0.0 | 1.0 |
| `Proc_1` | 53.0 | 21.2 | 14.3% | 0.1 | 18.0 | 1.0 |
| `main` | 66.0 | 21.1 | 14.3% | 0.1 | 5.0 | 0.0 |
| `Proc_8` | 29.0 | 12.1 | 8.2% | 0.1 | 11.0 | 1.0 |
| `Func_2` | 23.0 | 9.1 | 6.1% | 0.1 | 4.0 | 1.0 |
| `Proc_6` | 23.0 | 7.1 | 4.8% | 0.1 | 6.0 | 1.0 |
| `Proc_7` | 15.0 | 6.0 | 4.1% | 0.0 | 4.0 | 1.0 |
| `Func_1` | 15.0 | 6.0 | 4.1% | 0.0 | 0.0 | 3.0 |
| `Proc_2` | 12.0 | 5.0 | 3.4% | 0.0 | 1.0 | 1.0 |
| `Proc_4` | 12.0 | 3.0 | 2.1% | 0.0 | 2.0 | 1.0 |
| `Proc_5` | 7.0 | 3.0 | 2.0% | 0.0 | 2.0 | 1.0 |
| `Proc_3` | 11.0 | 1.0 | 0.7% | 0.0 | 0.0 | 1.0 |
| `bench_timer` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `setStats` | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 |
| `Func_3` | 3.0 | 0.0 | 0.0% | 0.0 | 0.0 | 1.0 |

Software multiply and divide: 0.0 instructions and 0.0 clocks per run (0.0%), from no calls per run. String and memory routines: 177.0 instructions per run.

Control flow per run: 21.0 branches taken, 27.0 not taken, 15.0 calls.

**Direct-mapped instruction cache, replayed on this instruction stream:**

| Size | Misses per run | Fetch clocks saved per run |
|---|---:|---:|
| 1 beats (8 bytes) | 252.0 | 0.2 |
| 2 beats (16 bytes) | 248.0 | 0.2 |
| 4 beats (32 bytes) | 224.0 | 0.2 |
| 8 beats (64 bytes) | 200.0 | 0.2 |
| 16 beats (128 bytes) | 194.0 | 0.2 |
| 32 beats (256 bytes) | 191.0 | 0.2 |
| 64 beats (512 bytes) | 181.0 | 0.2 |

**Most expensive instructions** (whole region):

| Address | Function | Instruction | Times | Clocks | Fetch | Memory |
|---|---|---|---:|---:|---:|---:|
| `0x01e4` | `main` | `divw s6, s5, s0` | 500 | 3,000 | 8 | 499 |
| `0x0ddc` | `strcpy` | `addi a2, a2, 0x1` | 2,500 | 2,500 | 0 | 1,000 |
| `0x0da4` | `strcpy` | `j 0xdd0 <strcpy+0xd0>` | 500 | 2,000 | 0 | 0 |
| `0x0de4` | `strcpy` | `ret` | 500 | 2,000 | 3 | 0 |
| `0x02ac` | `main` | `lw s6, 0xdc(sp)` | 1,000 | 1,505 | 4 | 0 |
| `0x0dfc` | `strcmp` | `beqz a3, 0xf04 <strcmp+0x11c>` | 1,500 | 1,501 | 1 | 0 |
| `0x0d7c` | `strcpy` | `ld t1, 0x0(t0)` | 1,500 | 1,500 | 0 | 3 |
| `0x0e18` | `strcmp` | `slli a3, a1, 0x3d` | 500 | 1,500 | 3 | 0 |
| `0x0a04` | `Proc_7` | `ret` | 1,500 | 1,500 | 2 | 500 |
| `0x0a54` | `Proc_8` | `lw a1, 0x0(a6)` | 500 | 1,500 | 1 | 1,499 |
| `0x07d0` | `Proc_1` | `ld a1, 0x10(a0)` | 500 | 1,500 | 0 | 1,500 |
| `0x0a7c` | `Func_1` | `xor a1, a1, a0` | 1,500 | 1,004 | 4 | 0 |
| `0x0ed0` | `strcmp` | `zext.b a2, a2` | 500 | 1,004 | 9 | 0 |
| `0x0df8` | `strcmp` | `lbu a4, 0x0(a1)` | 1,500 | 1,003 | 3 | 2 |
| `0x0adc` | `Func_2` | `mv a1, a0` | 500 | 1,002 | 4 | 0 |

**Instruction mix** (per run): `addi` 127.0, `ld` 38.0, `jalr` 32.0, `auipc` 23.0, `sd` 23.0, `sw` 23.0, `bne` 23.0, `lbu` 22.0, `beq` 20.0, `andi` 18.0, `lw` 13.0, `xor` 13.0, `or` 11.0, `sb` 9.0, `srli` 8.0, `srl` 7.0, `sll` 7.0, `sub` 6.0, `jal` 4.0, `add` 4.0, `sltiu` 3.0, `slli` 2.0, `addiw` 2.0, `bltu` 2.0, `bge` 1.0, `lui` 1.0, `blt` 1.0, `bgeu` 1.0, `slt` 1.0, `?` 1.0.

**What-if estimates** from the measured stream (model estimates, not measured RTL):

| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |
|---|---:|---:|---:|---:|---:|
| Measured | 446.1 | 147.9 | 0.332 | 3.8484 | 1.00x |
| Instruction cache, 2 beats (16 bytes) | 446.1 | 147.7 | 0.331 | 3.8526 | 1.00x |
| Instruction cache, 4 beats (32 bytes) | 446.1 | 147.7 | 0.331 | 3.8526 | 1.00x |
| Instruction cache, 8 beats (64 bytes) | 446.1 | 147.7 | 0.331 | 3.8530 | 1.00x |
| Instruction cache, 16 beats (128 bytes) | 446.1 | 147.7 | 0.331 | 3.8533 | 1.00x |
| Instruction cache, 32 beats (256 bytes) | 446.1 | 147.7 | 0.331 | 3.8533 | 1.00x |
| Instruction cache, 64 beats (512 bytes) | 446.1 | 147.7 | 0.331 | 3.8534 | 1.00x |
| Issue loads and stores in EXECUTE | 446.1 | 89.8 | 0.201 | 6.3383 | 1.65x |
| Issue the next fetch in EXECUTE | 446.1 | 147.6 | 0.331 | 3.8573 | 1.00x |
| Hardware multiply and divide (M) | 446.1 | 147.9 | 0.332 | 3.8484 | 1.00x |
| No fetch clocks at all | 446.1 | 147.2 | 0.330 | 3.8678 | 1.01x |
| One clock per instruction | 446.1 | 446.1 | 1.000 | 1.2760 | 0.33x |

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

- Timed region: 73,947 clocks, 223,030 instructions (from the start-marker store to the instruction before the stop-marker store).
- Whole program: 76,572 clocks, 229,793 instructions.
- Differential run, up to 0 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=76108 slot2=43540 slot3=31439 slot3_branches=0`.
- Differential run, up to 7 wait cycles: PASS, 259,050 events, `DONE retirements=229793 cycles=149710 slot2=32606 slot3=29292 slot3_branches=0`.
- Simulator: Icarus Verilog version 12.0 (stable) (). Host: Linux-6.18.33.2-microsoft-standard-WSL2-aarch64-with-glibc2.39, Python 3.12.3.
- Wall time: timing run 83.3 s, reference model 0.3 s.
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

<!-- dhrystone-run {"time":"2026-11-21 09:54:57 -0500","architecture_version":"0.10.0","commit":"af0a3a1","dirty":"yes (`DEVLOG.md`, `cpu/VERSION`, `cpu/architecture.md`, `cpu/dhrystone-rv64imb-ooo-results.json`, `cpu/programs-verification.json`, `cpu/rubric-evidence.json`, `cpu/visualizer-verification.json`, `rtl/cpu/rv64_ooo.sv`, ...)","compiler":"clang version 23.1.5","optimization":"O2","isa":"rv64im_zba_zbb_zbs_zifencei","ram_bytes":65536,"runtime":"fast","core":"ooo","cycles_per_run":147.894,"cpi":0.33155629287539795,"dmips_per_mhz":3.8483776459780272,"rubric_total":6.1,"rtl_sha256":{"rtl/cpu/rv64_ooo.sv":"c406a99e9105841472d2273f42cb840d7a781563b8230c5aa79f31127c140dc4","rtl/cpu/rv64_bram_soc.sv":"1043cf3322255e6eddc1349d4fe7228ff876afc582b66dd7037fb8bfbe925a4b"}} -->
