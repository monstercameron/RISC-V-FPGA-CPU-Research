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

- [ ] **Cycle counter.** Readable cycle and retired-instruction counters. Comes with Zicsr/Zicntr in C1; until then, time runs from the testbench.
- [ ] **Larger RAM option.** Run with `RAM_WORDS` large enough for the benchmarks, and record the value with each result.
- [ ] **Port CoreMark.** Bare-metal port for the current ISA with software multiply. Done when a short simulation run passes its self-check and reports clocks per instruction, labelled non-compliant. Rubric R4.1, R4.2.
- [ ] **PicoRV32 comparator.** Build the vendored core with the same tools and settings. Rubric section 9.
- [ ] **Port Embench-IoT.** Secondary benchmark set once CoreMark runs.
- [ ] **Cycle-count regression record.** Save benchmark clock counts per RTL hash and flag changes over 2%. Rubric R4.8.

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

## Later

- [ ] **C7 board bring-up**: exact part, constraints, reset synchronizer, timing closure and a programmed board running firmware. Can start on the C0 core.
- [ ] **Remaining RVA23U64 extensions**: B, V, Zfhmin, Zfa and the rest of the architecture ledger (C2-C6).
- [ ] **Supervisor mode, Sv39 MMU and Linux boot**: a separate platform design, needed before large software runs.
- [ ] **Large-software stress test**: V8 or a similar runtime, only after RV64GC, an MMU and Linux run on an FPGA board. It is too slow to run in RTL simulation.
