# To do

Working list for the custom CPU, in priority order. The [architecture document](cpu/architecture.md) owns the C0-C7 gates and the RVA23 ledger; the [review rubric](cpu/review-rubric.md) owns what counts as evidence. This list tracks the work in between. Tick an item only when its "done when" evidence exists, and link that evidence.

Last updated November 20, 2026.

## Now: make the C0 core measurable and independently checked

- [ ] **External model in the regression.** Compare every retirement against Spike or Sail in lockstep. Done when the default suite fails on any disagreement. Rubric HG3, R1.1, R3.1.
- [ ] **Official architectural tests.** Run riscv-arch-test for `rv64i_zifencei`. Done when all applicable tests pass and the revision used is recorded. Rubric HG3, R1.1.
- [ ] **Wider random programs.** The random generator draws only register and immediate arithmetic. Add loads, stores, branches and jumps with bounded targets. Rubric R3.4.
- [ ] **Lint.** Add a Verilator lint run with no unwaived warnings. Rubric HG7, R8.1.
- [ ] **First synthesis.** Run Yosys on the core and RAM wrapper for a candidate exact part. Done when block RAM inference and a LUT/flip-flop count are recorded. Rubric HG7, R5.1, R5.2.
- [x] **Tag the first architecture version.** Annotated tag `cpu-v0.1.0` on commit `0483d99`, where the 0.1.0 RTL first landed; pushed November 20, 2026. Versioning rules: [cpu/architecture.md](cpu/architecture.md) section 9.
- [ ] **Known-issue list.** Start one so reviews can check for open correctness defects. Rubric HG6.
- [ ] **Commit or discard the regenerated visualizer records.** `cpu/programs-verification.json` and `cpu/visualizer-verification.json` were rebuilt locally on November 20, 2026, last on architecture 0.4.0 after its visualizer testbench fix, and are uncommitted.

## Next: first benchmark

Targets: **CoreMark** (primary, the number people compare cores by) and **Dhrystone** (secondary, small and widely quoted, never reported alone). Both run in simulation first, so every result is labelled non-compliant until a board run meets the benchmark's own rules.

Shared groundwork:

- [x] **Benchmark markers.** The program writes start and stop markers to a mailbox word; [tb_bench.sv](sim/cpu/bench/tb_bench.sv) counts clocks and retired instructions between them. Replaces hardware counters until Zicntr arrives in C1. Done November 20, 2026.
- [x] **Larger memory for benchmarks.** The RAM wrapper's `RAM_WORDS`, a new `MEM_BYTES` parameter in [tb_core.sv](sim/cpu/tb_core.sv) and a generated linker script set the size; the reference model already follows the image size. The main regression in [test_cpu.py](sim/cpu/test_cpu.py) stays at 16 KiB on purpose, because its unmapped-address tests rely on that boundary. Done November 20, 2026.
- [x] **Small runtime.** [start.S](sim/cpu/bench/start.S) with `.bss` clearing, and [runtime.c](sim/cpu/bench/runtime.c) with `memcpy`/`memset`/`strcpy`/`strcmp` and software multiply and divide. Done November 20, 2026.
- [ ] **Licensing.** Add each benchmark's upstream license, provenance and source revision to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `licenses/` before committing its source. Done for Dhrystone; CoreMark still needs it.

CoreMark:

- [ ] **Port CoreMark.** Bare-metal `core_portme` for `rv64i` with software multiply, using the markers for timing and the default 2,000-byte data set.
- [ ] **Size it.** Build it and record code, data and stack size against 16 KiB; set `RAM_WORDS` from the result.
- [ ] **Budget the run.** Time one iteration in simulation, then pick an iteration count that finishes in about 10 minutes. The simulator runs roughly 17,000 instructions per second.
- [ ] **Validate.** Done when the run passes CoreMark's own list, matrix and state CRC checks for the performance seeds and the retirement trace matches the reference model.
- [ ] **Report.** CoreMark per MHz (iterations x 1,000,000 / clocks) and clocks per instruction, with compiler version, flags, ISA string, RAM size and iteration count, labelled "non-compliant run, simulation". Rubric R4.1, R4.2.

Dhrystone:

First result: **0.260 DMIPS/MHz**, non-compliant simulation run, November 20, 2026. See [cpu/dhrystone.md](cpu/dhrystone.md).

- [x] **Port Dhrystone.** The riscv-tests edition (version string 2.2, the same benchmark loop as 2.1), unmodified, with a port layer for timing and result capture. Done November 20, 2026.
- [x] **Guard against compiler distortion.** Each file compiled separately at `-O2`, no link-time optimization, `-fno-inline` on the upstream files; every command recorded. Done November 20, 2026.
- [x] **Validate.** All 17 reachable final values match Dhrystone's expected values, and the retirement trace matches the reference model with 0 and 7 wait cycles. The benchmark's local variables are not reachable and are not checked. Done November 20, 2026.
- [x] **Runs in CI.** A CI job builds with Ubuntu's clang and runs the checks on every push.
- [ ] **Report beside CoreMark.** DMIPS per MHz (runs x 1,000,000 / (clocks x 1,757)) is recorded in [cpu/dhrystone-results.json](cpu/dhrystone-results.json). Done when it is published next to a CoreMark result, never on its own. Rubric section 9.
- [x] **Hardware multiply and divide.** Architecture 0.4.0 adds M; the `rv64im` build runs 555.7 clocks per run against 600.8 for `rv64i`, 1.08x. Done November 20, 2026.

Optimizations the Dhrystone profile points to, measured on every run (see [cpu/dhrystone.md](cpu/dhrystone.md)):

- [x] **Fetch buffer.** Architecture 0.1.1: 2,188.2 to 1,706.2 clocks per run (1.28x), as estimated. Superseded by the instruction cache in 0.2.0.
- [x] **Instruction cache, loads and stores from EXECUTE, same-clock writes, data cache.** Architectures 0.2.0 to 0.3.0: down to 600.8 clocks per run, CPI 1.001. See the [optimization history](cpu/dhrystone.md#optimization-history).
- [ ] **Overlap fetch with execute.** No longer worth doing for Dhrystone: with the instruction cache, fetch is 0.1% of clocks. Revisit with a slow-memory model or code larger than the cache.
- [x] **Limited dual issue.** Architectures 0.5.0 to 0.5.5: a second instruction per clock, including loads, stores, branches, jumps, forwarding and branch folding; Dhrystone `rv64im` 555.7 to 287.8 clocks per run. See the [optimization history](cpu/dhrystone.md#optimization-history).
- [ ] **Measure logic depth before going wider.** Dual issue, forwarding and folding lengthen the clock. Record the longest path in LUT levels for each version (`sim/cpu/synth_depth.py`) and report it beside DMIPS/MHz; a gain that costs more in clock than it saves in clocks is not real.
- [ ] **Three-wide issue.** Modelled at about 2.7 DMIPS/MHz (reference runtime) with one level of forwarding. Only after the depth measurement, and after an external model is in the regression.
- [ ] **Synthesize the caches.** The cache lookups use the just-computed next PC and data address in the same clock; check their timing on a real part before relying on these clock counts.
- [x] **Runtime string routines.** A labelled `--runtime fast` build moves 8 bytes per step, shifting misaligned words together; 553 to 470 instructions per run. The byte-at-a-time runtime stays the reference.

Then:

- [ ] **PicoRV32 comparator.** Run CoreMark and Dhrystone on the vendored core with the same compiler flags, and build it with the same tools and settings. Rubric section 9.
- [ ] **Port Embench-IoT.** Secondary benchmark set once CoreMark runs.
- [ ] **Cycle-count regression record.** Save benchmark clock counts per RTL hash and flag changes over 2%. Rubric R4.8.

## Memory hierarchy: main memory, L1 and L2

Today the core has **no caches** and a single 16 KiB RAM that answers in one clock. Caches only speed things up when main memory is slow, so first record benchmark numbers without caches, then add a slow main-memory model, then the caches, and measure each step.

CoreMark and Dhrystone are small enough to fit in a modest L1, so L2 will mostly matter for larger workloads.

Main memory:

- [ ] **Larger simulated main memory.** At least 1 MiB in the testbench, RAM wrapper and reference model, set by one parameter and recorded with each result. Builds on "Larger memory everywhere" above.
- [ ] **Slow-memory model.** Configurable latency and bandwidth to imitate board DRAM, with the latency recorded with each result.
- [ ] **Board memory plan.** Choose between on-chip block RAM and DDR once the FPGA part is chosen; block RAM capacity limits both main memory and L2 size.

L1 caches:

- [ ] **Design note first.** Sizes, associativity, 64-byte lines (RVA23's Zic64b expects 64-byte cache blocks), write policy, and which address ranges are uncached for future peripherals. Update the memory and FENCE.I sections of the architecture document to match.
- [x] **L1 instruction cache.** Architecture 0.2.0: direct-mapped, 8-byte lines, `ICACHE_BEATS` (default 4 KiB); `fence.i` and stores keep it coherent; the self-modifying-code test passes. 64-byte lines are still to do.
- [x] **L1 data cache.** Architecture 0.3.0: write-through, so stores complete on the bus before retiring and faults stay precise; direct-mapped, 8-byte lines, `DCACHE_BEATS` (default 4 KiB). Every address is treated as cacheable until a PMA exists.
- [ ] **Cache verification.** Partly done: the full regression passes with 2-line and 512-line caches under random memory stalls, and the self-modifying-code test covers stores followed by fetches. Still to add: directed eviction and conflict tests, and a check with caches effectively off.

L2 cache:

- [ ] **Unified L2** behind both L1 caches, sized after the FPGA part is chosen. Done when the cache verification above passes with L2 present.

Results:

- [ ] **Measure each step.** Report CoreMark and Dhrystone with no cache, L1 only, and L1 plus L2, at several main-memory latencies, with the full cache configuration recorded. Rubric R4.6.
- [ ] **Cache-management instructions** (Zicbom, Zicboz, Zicbop) come later with the RVA23 platform work in C6.

## C1: real execution environment

- [ ] **Zicsr** and the machine-mode trap CSRs: `mstatus`, `mtvec`, `mepc`, `mcause`, `mtval`, `mie`, `mip`, `mscratch`.
- [ ] **`mret`** and a firmware trap handler that resumes execution.
- [ ] **Timer and external interrupts**, taken only at instruction boundaries, including while pending during memory stalls.
- [ ] **Zicntr counters**: `cycle`, `time`, `instret`.
- [ ] **Readable version.** Consider reporting the architecture version in the implementation-defined `mimpid` CSR.
- [ ] **User mode, PMP and access controls** as the architecture document's C1 row specifies.

## Milestone: RV64GC

RV64GC is RV64IMAFDC plus Zicsr and Zifencei. It is the usual baseline for general-purpose 64-bit RISC-V software, including Linux distributions and large runtimes such as V8. Reaching it means passing C1 through C4, in this order:

- [x] **I**: base integer, done in C0. Local simulation evidence only: [verification record](cpu/verification.json).
- [x] **Zifencei**: `fence.i`, done in C0, including a self-modifying-code test. Same evidence.
- [ ] **Zicsr**: C1, above.
- [ ] **M** (C2): implemented in architecture 0.4.0, with divide-by-zero, overflow and high-product cases matching the project reference model. Done when they also match an external model.
- [ ] **C** (C2): compressed instructions, 16-bit alignment and fetch across 64-bit beat boundaries. Done when compressed-fetch and illegal-encoding cases match the external model.
- [ ] **A** (C3): LR/SC with a reservation tracker and AMOs. Done when reservation, invalidation and atomicity tests pass, including multi-agent memory tests.
- [ ] **F and D** (C4): single and double precision, the FP register file and `fcsr`. Done when NaN boxing, signed zero, subnormals, all rounding modes and exception flags match an independent IEEE reference, with no silent flush-to-zero.
- [ ] **RV64GC compiler target.** Done when unmodified `-march=rv64gc -mabi=lp64d` compiler output runs, including CoreMark and Embench.
- [ ] **Architectural tests for `rv64gc`.** Done when riscv-arch-test passes for the full ISA string and lockstep comparison with the external model passes.

RV64GC is a stepping stone, not the project target. RVA23U64 needs much more, including B, V and the other extensions in the architecture document's ledger. Do not describe an RV64GC core as RVA23.

## Research: matrix extensions

No RISC-V matrix extension was ratified as of mid-2026. RISC-V International has been exploring two approaches, and a few vendors ship their own. This is research only: no matrix RTL until the V extension works, and no matrix extension is part of RVA23.

| Approach | Idea | Comparable to |
|---|---|---|
| Integrated matrix (IME) | Matrix multiply instructions that reuse the existing vector registers. Cheaper; builds directly on V. | Matrix instructions added to a vector unit |
| Attached matrix (AME) | A separate matrix unit with its own tile registers and state. Faster for large matrix multiplies, but more hardware and more state to save on context switches. | Arm SME, Intel AMX |

- [ ] **Current status.** Check the RISC-V International task groups for IME and AME: names, latest draft, ratification stage and any change since mid-2026. Record the date and source links.
- [ ] **Read the drafts and vendor implementations.** Include T-Head's published matrix specification and SpacemiT's integrated matrix instructions in the K1. Note which encodings are vendor-specific.
- [ ] **Compare IME and AME for this core.** Cover:
  - extra architectural state and context-switch cost;
  - dependence on V, `VLEN` and the vector register file;
  - supported data types: int8 with 32-bit accumulation, BF16, FP16, FP32;
  - FPGA cost in DSP slices, block RAM and LUTs, and the effect on timing;
  - fit with the LLM workload in the earlier accelerator research.
- [ ] **Related smaller options.** Compare with the BF16 vector extensions (Zvfbfmin, Zvfbfwma) and any integer dot-product extension, which may give much of the benefit at lower cost.
- [ ] **Recommendation.** Done when a dated research note in the repository recommends IME, AME or neither, with sources, open questions and what would change the decision.

## Later

- [ ] **C7 board bring-up**: exact part, constraints, reset synchronizer, timing closure and a programmed board running firmware. Can start on the C0 core.
- [ ] **Remaining RVA23U64 extensions**: V, Zfhmin, Zfa and the rest of the architecture ledger (C2-C6).
- [x] **B extension (Zba, Zbb, Zbs).** Architecture 0.6.0, in both issue slots; checked by directed and random tests and by building the same C with and without B (`sim/cpu/check_bitmanip.py`). Still needs an external-model comparison.
- [ ] **Supervisor mode, Sv39 MMU and Linux boot**: a separate platform design, needed before large software runs.
- [ ] **Large-software stress test**: V8 or a similar runtime, only after RV64GC, an MMU and Linux run on an FPGA board. It is too slow to run in RTL simulation.
