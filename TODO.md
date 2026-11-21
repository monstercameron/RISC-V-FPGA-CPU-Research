# To do

Working list for the custom CPU, in priority order. The [architecture document](cpu/architecture.md) owns the C0-C7 gates and the RVA23 ledger; the [review rubric](cpu/review-rubric.md) owns what counts as evidence. This list tracks the work in between. Tick an item only when its "done when" evidence exists, and link that evidence.

Last updated November 20, 2026.

## Now: make the C0 core measurable and independently checked

- [ ] **External model in the regression.** Compare every retirement against Spike or Sail in lockstep. Done when the default suite fails on any disagreement. Rubric HG3, R1.1, R3.1.
- [ ] **Official architectural tests.** Run riscv-arch-test for `rv64i_zifencei`. Done when all applicable tests pass and the revision used is recorded. Rubric HG3, R1.1.
- [ ] **Wider random programs.** The random generator draws only register and immediate arithmetic. Add loads, stores, branches and jumps with bounded targets. Rubric R3.4.
- [ ] **Lint.** Add a Verilator lint run with no unwaived warnings. Rubric HG7, R8.1.
- [ ] **First synthesis.** Run Yosys on the core and RAM wrapper for a candidate exact part. Done when block RAM inference and a LUT/flip-flop count are recorded. Rubric HG7, R5.1, R5.2.
- [ ] **Known-issue list.** Start one so reviews can check for open correctness defects. Rubric HG6.
- [ ] **Commit or discard the regenerated visualizer records.** `cpu/programs-verification.json` and `cpu/visualizer-verification.json` were rebuilt locally on November 20, 2026 and are uncommitted.

## Next: first benchmark

Targets: **CoreMark** (primary, the number people compare cores by) and **Dhrystone** (secondary, small and widely quoted, never reported alone). Both run in simulation first, so every result is labelled non-compliant until a board run meets the benchmark's own rules.

Shared groundwork:

- [ ] **Benchmark markers.** The program writes start and stop markers to a reserved address; the testbench counts clocks and retired instructions between them. Replaces hardware counters until Zicntr arrives in C1. Rubric section 9.
- [ ] **Larger memory everywhere.** `RAM_WORDS` already scales the RAM wrapper, but [tb_core.sv](sim/cpu/tb_core.sv), [test_cpu.py](sim/cpu/test_cpu.py) and the reference model assume exactly 16 KiB. Make the size a parameter in all of them and record it with each result.
- [ ] **Small runtime.** Startup code, a stack sized for the benchmark, `memcpy`/`memset`/`strcpy`/`strcmp`, and the compiler's software multiply and divide routines for `rv64i`.
- [ ] **Licensing.** Add each benchmark's upstream license, provenance and source revision to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `licenses/` before committing its source.

CoreMark:

- [ ] **Port CoreMark.** Bare-metal `core_portme` for `rv64i` with software multiply, using the markers for timing and the default 2,000-byte data set.
- [ ] **Size it.** Build it and record code, data and stack size against 16 KiB; set `RAM_WORDS` from the result.
- [ ] **Budget the run.** Time one iteration in simulation, then pick an iteration count that finishes in about 10 minutes. The simulator runs roughly 17,000 instructions per second.
- [ ] **Validate.** Done when the run passes CoreMark's own list, matrix and state CRC checks for the performance seeds and the retirement trace matches the reference model.
- [ ] **Report.** CoreMark per MHz (iterations x 1,000,000 / clocks) and clocks per instruction, with compiler version, flags, ISA string, RAM size and iteration count, labelled "non-compliant run, simulation". Rubric R4.1, R4.2.

Dhrystone:

- [ ] **Port Dhrystone 2.1.** Bare-metal, using the markers for timing. A RISC-V bare-metal harness already exists in riscv-tests and can be the starting point.
- [ ] **Guard against compiler distortion.** Compile each file separately with fixed flags, no link-time optimization and no inlining across files; record the flags. A result built differently is not comparable.
- [ ] **Validate.** Done when the program's final variable values match the published expected values and the retirement trace matches the reference model.
- [ ] **Report.** DMIPS per MHz (1,000,000 / (clocks per iteration x 1,757)), always next to the CoreMark result and never alone. Rubric section 9.

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
- [ ] **L1 instruction cache.** `fence.i` must invalidate it; the existing self-modifying-code test must still pass.
- [ ] **L1 data cache.** Faults must stay precise. A write-back cache can hit a bus error when it evicts a line long after the store retired, so decide how that is reported before choosing write-back.
- [ ] **Cache verification.** The retirement and write trace must be identical with caches on and off. Add tests for evictions, conflicting addresses, stores followed by fetches of the same line, and random memory stalls.

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
- [ ] **User mode, PMP and access controls** as the architecture document's C1 row specifies.

## Milestone: RV64GC

RV64GC is RV64IMAFDC plus Zicsr and Zifencei. It is the usual baseline for general-purpose 64-bit RISC-V software, including Linux distributions and large runtimes such as V8. Reaching it means passing C1 through C4, in this order:

- [x] **I**: base integer, done in C0. Local simulation evidence only: [verification record](cpu/verification.json).
- [x] **Zifencei**: `fence.i`, done in C0, including a self-modifying-code test. Same evidence.
- [ ] **Zicsr**: C1, above.
- [ ] **M** (C2): multiply and divide behind a start/busy/done interface. Done when divide-by-zero, overflow and high-product cases match the external model.
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
- [ ] **Remaining RVA23U64 extensions**: B, V, Zfhmin, Zfa and the rest of the architecture ledger (C2-C6).
- [ ] **Supervisor mode, Sv39 MMU and Linux boot**: a separate platform design, needed before large software runs.
- [ ] **Large-software stress test**: V8 or a similar runtime, only after RV64GC, an MMU and Linux run on an FPGA board. It is too slow to run in RTL simulation.
