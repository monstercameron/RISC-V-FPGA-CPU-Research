# CPU architecture, version 0.5.5

Versioned with [semantic versioning](https://semver.org/); rules and history are in section 9. "Revision 0" in this document is version 0.1.0.

Decision date: October 23, 2026. User priority: **CPU core first**. This design starts a programmable FPGA processor and keeps RVA23 as a tracked destination. It supersedes the previous accelerator-first priority, while preserving the old accelerator contracts as historical/future-work references.

## 1. Target and first implementation

Long-term target: little-endian **RVA23U64**, including its mandatory scalar, vector and execution-environment behavior. Full RVA23S64 is a separate later project scope: it adds supervisor, virtual-memory and hypervisor requirements. A CPU with RV64I plus a vector MAC is insufficient to claim either profile. [RVA23 specification](https://github.com/riscv/riscv-profiles/blob/main/src/rva23-profile.adoc).

The implemented foundation is an RV64I instruction execution engine, plus local FENCE.I semantics and, since 0.4.0, the M extension (ISA string `rv64im_zifencei`), with a terminal laboratory execution environment. Its supported operations are tested but not ISA-certified. No A/C/B/F/D/V, CSR instructions, contained privilege traps, interrupts or MMU are implemented; instruction and data caches were added in 0.2.0 and 0.3.0. Unsupported operations trap; hardware capabilities are not falsely advertised through a fabricated `misa` CSR.

| Choice | Revision 0 decision | Reason |
|---|---|---|
| RTL language | Synthesizable SystemVerilog constructs | Clear state and bit widths; current Icarus simulation route |
| Integer width | XLEN=64 from the beginning | Avoid rebuilding the datapath after an RV32-only prototype |
| Execution | One instruction at a time, multicycle | No speculation, hazard forwarding, reorder buffer or branch predictor needed |
| Register file | 32 x64, combinational reads, one sequential write; x0 reads zero | Simple initial implementation; synthesis must measure mux/register cost |
| ALU | Add/subtract, shifts, comparisons, bitwise, RV64 word operations | A complete useful base arithmetic path |
| Memory port | Unified 64-bit, byte strobes, one outstanding transaction | Compatible with simple synchronous RAM and later adapters |
| Instruction cache (0.2.0) | Direct-mapped, 8-byte lines, `ICACHE_BEATS` lines, store-coherent | Fetch was more than half of all clocks |
| Multiply and divide (0.4.0) | Multiply in one clock; divide and remainder by shift-subtract from the quotient's highest bit, one step per clock in a DIVIDE state | Dhrystone's one software divide per run cost about 36 instructions |
| Dual issue (0.5.0) | Second simple integer instruction from the same 8-byte beat retires in the same clock through a second retirement port | The core had reached one instruction per clock |
| Data cache (0.3.0) | Direct-mapped, write-through, no store allocation, 8-byte lines, `DCACHE_BEATS` lines | Loads waited a clock for the synchronous RAM |
| Instruction alignment | 32 bits until C arrives | Explicitly trap taken misaligned branches/jumps |
| Data alignment | Naturally aligned accesses; misalignment traps | Keeps first LSU bounded; must change for RVA23's specified main-memory behavior |
| Trap handling | Sticky external record and halt until reset | Laboratory EEI; no implicit software handler or hidden emulation |
| First SoC memory | 16 KiB single-clock synchronous RAM | No DDR controller, PCIe endpoint or cache-coherence dependency |
| Initial clock goal | Start board timing experiments at 50 MHz | A synthesis target only; no measured Fmax claim |

[RV64 integer semantics](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/rv64.adoc) build on [base instruction semantics](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/rv32.adoc). Word results sign-extend bit 31; LUI sign-extends its 32-bit result; 64-bit shifts use six count bits, word shifts five. Tests exercise those differences.

## 2. Datapath and control

```text
 PC -> aligned instruction read -> instruction register -> decode
                                                      |
                                 x-registers -> integer ALU
                                                      |
                        +-----------------------------+----------------+
                        |                             |                |
                   register result               next PC       load/store request
                        |                             |                |
                        +------- retire once ---------+         unified memory port
                                                                      |
                                                         synchronous RAM / later bus

 Any fault -> precise external trap record -> HALTED
```

States are FETCH, EXECUTE, MEMORY and HALTED. Instruction fetch and data accesses use the same bus. Fetch holds its request until completion, then captures the selected 32-bit half of the 64-bit response. Since 0.2.0 every fetched beat also goes into a direct-mapped instruction cache of `ICACHE_BEATS` 8-byte lines (default 512, 4 KiB; a power of two of at least 2, checked at elaboration). When the next instruction hits, the core goes straight to EXECUTE without a bus request. Reset and `fence.i` clear the whole cache and a successful store clears the line holding its beat, so fetched instructions always reflect completed stores, as before. The hit check reads the cache with the just-computed next PC; its timing cost must be checked at synthesis. EXECUTE decodes and either retires a non-memory instruction, records a memory operation, or faults. Since 0.5.0 EXECUTE can also complete the next instruction in the same 8-byte beat in the same clock: it must be a simple integer operation (OP, OP-IMM, their word forms, LUI or AUIPC), must not read or overwrite the register the first instruction writes, and the first must finish that clock (an integer operation other than a divide, a load that hits the data cache, or a store to a different beat). Since 0.5.1 the second instruction may come from the next beat when it is cached and may be a conditional branch with an aligned target; since 0.5.2 it may be an aligned load that hits the data cache, through a second read port, when the first is not a store to the same beat. Since 0.5.3 the first may also be a conditional branch that is not taken, and the second may be a JAL or JALR with an aligned target. Since 0.5.4 the second may be an aligned store when the first does not use the bus; if the bus stalls, the first retires and the store waits in MEMORY with its request held, and a bus error traps precisely at the store. Also since 0.5.4 an integer result of the first (not a load or multiply) is forwarded to the second's operands in the same clock, which chains two ALUs in one clock; its timing cost must be checked at synthesis. Since 0.5.5, when the first is a jump or a taken branch, the second slot executes the instruction at its target, read from the instruction cache in the same clock, and JAL/JALR links are forwarded; this adds the branch decision, the target addition and a cache read to the same clock. Since 0.3.0 a direct-mapped, write-through data cache of `DCACHE_BEATS` 8-byte lines (default 512, 4 KiB) serves loads: a successful load fills its line, a successful store updates a line that holds its beat (no allocation on stores), and a load that hits completes in EXECUTE with no bus request. Since 0.2.1 a load or store puts its request on the bus during EXECUTE, as soon as its address is known and no exception is pending; if the bus completes in that clock the instruction retires from EXECUTE, otherwise MEMORY holds the identical request until completion. MEMORY waits for exactly one completion and only then retires a successful load/store. HALTED issues nothing.

Register and next-PC updates happen at retirement. A faulting instruction does not retire or update its destination register. Stores become visible through the memory adapter's successful completion contract; an error response must have no write side effect. The testbench separately compares committed writes and retirement events to a sequential byte-addressed model.

ALU/branch decode is combinational in revision 0. This may infer more than one physical adder or large muxes; RTL operators are not a resource report. Later timing measurements may justify explicit resource sharing or extra execution states. Register-file reset is acceptable for this small prototype but has fanout and inference costs. RAM is not reset in a loop.

## 3. Memory interface contract

| Signal | Meaning |
|---|---|
| `mem_valid` | Request exists; remain asserted until completion |
| `mem_ready` | Request completes at this rising edge when valid is also 1 |
| `mem_instr` | Instruction fetch; otherwise data access |
| `mem_addr[63:0]` | Byte address aligned down to 8 bytes |
| `mem_wstrb[7:0]` | Zero for reads; set lane i to write byte i |
| `mem_wdata[63:0]` | Store data shifted into addressed byte lanes |
| `mem_rdata[63:0]` | Entire aligned 64-bit read beat, stable at completion |
| `mem_error` | Fault indication sampled only at completion; no store side effect |

All request fields remain stable under backpressure. A successful handshake represents one access, never one access per cycle while valid is high. The bus adapter owns address decoding, permissions, access width/PMA restrictions and any timeout. There is no silent core timeout that discards an outstanding transaction. An absent response stalls until a coordinated fabric reset or an adapter-reported error.

Since 0.3.0 the core treats every address as cacheable: a load that hits the data cache, and an instruction that hits the instruction cache, makes no bus request. Before any memory-mapped peripheral is added, a PMA mechanism must mark its region uncacheable. The current wrapper has one readable/writable/executable region 0x0000..0x3fff. Everything else returns an access fault. It performs no address truncation before the range check. Instruction fetch reads an entire aligned 8-byte RAM beat; a later MMIO/PMA adapter must not turn this into an over-wide side-effecting peripheral read. Vector, cache and bus adapters will need explicit access-size and attribute metadata before general platform integration.

Reset is synchronous and must reset/quiesce the core and its memory adapter together. The dedicated reset test cancels a store **before acknowledgement** in that shared-reset environment. It does not establish rollback of completed stores, safe cancellation of AXI/PCIe writes, or permission to reset a live external fabric independently. Later system-reset logic must drain or isolate outstanding external accesses.

The sample SoC uses byte write enables and a synchronous read. Since 0.2.2 it acknowledges a write in the clock the request is presented, writing on that clock edge, with the out-of-range error decided combinationally; reads still answer one clock later. `RAM_WORDS` must be a power of two >=2; default 2048. Hex initialization has 2048 lines of 16 hexadecimal digits, each a little-endian 64-bit memory word. The RAM wrapper is simulation-tested, but actual BRAM inference and read/write behavior must be checked in the selected FPGA tool.

## 4. Trap and retirement contract

`trap_valid` remains set until reset; `trap_pc`, `trap_cause`, `trap_tval` remain stable. Causes use standard exception numbers for diagnostics:

| Cause | Revision 0 behavior |
|---:|---|
| 0 | Misaligned instruction target; tval=bad target; a not-taken branch does not fault |
| 1 | Instruction bus/access fault; tval=current PC |
| 2 | Unsupported/illegal instruction; tval=32-bit instruction zero-extended |
| 3 | EBREAK; tval=0 |
| 4 /5 | Misaligned load / load access fault; tval=effective byte address |
| 6 /7 | Misaligned store / store access fault; tval=effective byte address |
| 11 | ECALL from this laboratory M-origin environment; tval=0 |

The processor does not yet implement architectural machine mode just because it emits cause 11. The next stage replaces terminal reporting with a real CSR/privilege/trap implementation and a firmware handler. Unknown CSRs currently cause illegal instruction. FENCE is satisfied by the serial memory model; FENCE.I is satisfied by completing stores before a new, uncached instruction fetch. Self-modifying code is tested.

Retirement exports PC, instruction, destination/data and successor PC with a one-cycle valid pulse. Since 0.5.0 a second set of ports (`retire2_*`) reports a second instruction retired in the same clock; it always follows the first in program order, so a trace that logs slot one and then slot two is the sequential order. Destination zero denotes no architectural register write and reports data 0. This is useful debug visibility, not the full RVFI formal interface. Add memory, privilege and trap fields needed by an external architectural checker without changing commit order. [Machine-level reference](https://github.com/riscv/riscv-isa-manual/blob/main/src/priv/machine.adoc).

## 5. RVA23 completion ledger

The following covers every mandatory entry named in RVA23U64. Entries group related requirements, not implementation claims. Consult the linked specification for their exact semantics and dependencies.

| Required group | Current status | Planned gate |
|---|---|---|
| RV64I | Base execution with terminal EEI; local tests pass | C0/C1 plus architectural testing |
| Zicsr | Unsupported | C1 |
| Zicntr, Zihpm | Unsupported | C1/C6; counters and access controls |
| M | Implemented in 0.4.0: single-clock multiply, early-terminating iterative divide; local tests pass | C2 external-model comparison |
| A, Ziccrse, Ziccamoa, Za64rs, Zawrs | Unsupported | C3; atomicity/reservation/fabric together |
| C, B, Zcb, Zcmop | Unsupported | C2 |
| Zicond, Zimop, Zihintpause, Zihintntl | Not qualified as extensions | C2 |
| F, D, Zfhmin, Zfa, Zkt | Unsupported | C4 |
| V, Zvfhmin, Zvbb, Zvkt | Unsupported | C5 |
| Ziccif, Zicclsm | Platform behavior not qualified; misaligned data currently traps | C3/C6 |
| Zic64b, Zicbom, Zicbop, Zicboz | No implemented cache/PMA contract | C6 |
| Supm | No user environment or pointer masking | C1/C6 |

Zfbfmin, Zvfbfmin and Zvfbfwma are optional BF16 additions worth considering for the later LLM workload. They cannot replace required D or the complete V behavior. Likewise, executing the previous assembly examples is an integration test, not profile certification.

## 6. Staged development with exit evidence

| Gate | Deliverable | Required exit evidence |
|---|---|---|
| C0: working integer foundation | Current multicycle core, RAM, firmware and local tests | Directed/random instruction traces, memory lanes, faults, backpressure, reset and self-modifying fetch; local results recorded |
| C1: real execution environment | Machine trap CSRs/mret, interrupts, counters; then U-mode/PMP and needed access controls | Trap entry/return, exception priority, pending IRQs during memory stalls, counter writes/reads, reset, privilege rejection; external ISA model comparison |
| C2: scalar breadth | M, C, B and remaining scalar/compressed helpers | M divide-by-zero/overflow/high products; compressed fetch across beat boundaries; illegal encodings; hint behavior; all extension tests |
| C3: memory correctness | A, reservation tracker, PMAs and required misaligned accesses | LR/SC eventuality and invalidation; AMO indivisibility; aq/rl and fences; split access/fault policy; MMIO rejection; multi-agent memory litmus tests |
| C4: scalar floating point | F/D, conversions, FP16-minimal, Zfa, fcsr | Independent IEEE results including NaN boxing, signed zero, subnormal, rounding modes, exception flags and arithmetic corner cases; no silent FTZ |
| C5: complete vector engine | VLEN128, ELEN64 initially; narrow iterative lanes, vector CSRs/registers/LSU | All mandatory V semantics, masks/tails, LMUL/EEW legality, FP32/FP64, reductions, restart/vstart, fault-only-first, memory faults, context save and required vector helpers |
| C6: profile/platform closure | User environment, pointer masking, cache-block/PMA behavior, remaining counters and data-independent-latency requirements | Versioned ISA/PMA manifest; relevant architectural suite; privilege and environment tests; no missing mandatory item hidden as software support |
| C7: FPGA proof | Exact FPGA part, clocks, reset synchronizer, constraints, memory adapter and firmware path | Synthesis/inference, timing, CDC/reset checks, resource/thermal/power evidence, actual programmed board result |

Physical C7 work can begin on the C0 core before the full profile is complete. Label that bitstream by its implemented ISA. Keep long-operation units behind explicit start/busy/done/error interfaces and retire only after completion. Preserve precise exceptions when adding iterative divide or FP operations.

The initial vector architecture is a **proposal**, not implemented RTL: VLEN128 gives32 x128=4096 architectural register bits, with banked synchronous storage; execution can process fewer elements per cycle. A small implementation still needs FP64, legal element widths/groups, masks/tails and complete memory/restart semantics. A BF16-only vector MAC would be a workload accelerator, not V compliance. [V requirements](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/v-st-ext.adoc).

Supervisor/Linux work requires a separate platform design. Full RVA23S64 additionally includes Ss1p13, Svbare/Sv39/Svade, translation and memory-type extensions, supervisor timers/counters/pointer masking, and Sha with hypervisor-related requirements. Do not quietly rename an Sv39 Linux experiment as complete RVA23S64.

## 7. FPGA budget and measurement plan

Known architectural storage now: 2048 register bits, plus PC/instruction/LSU/control state; example RAM 131072 bits. That is a storage inventory, not an inferred FF/LUT/BRAM count. Shift networks, register muxes, ALU carry chains and reset choices need synthesis. The old accelerator resource spreadsheet cannot predict these costs.

Keep revision 0 vendor-independent. Before buying a board, synthesize the standalone core and RAM wrapper for candidate exact parts, report utilization with and without debug traces, inspect RAM inference, and constrain a real board clock. Start timing experiments at 50 MHz, then record achieved timing rather than adopting an unsupported frequency. Choose BRAM/programming access and usable free tool support before LUT count alone. The earlier [board analysis](../fpga-resource-and-board-analysis.md) supplies dated research, not a refreshed CPU recommendation.

Free work today uses the existing ARM workstation, LLVM cross compilation and Ubuntu Icarus. Yosys/Verilator were not on the inspected WSL PATH; no synthesis run is claimed. The previously documented supported x86-64 Vivado-host requirement still matters for an AMD hardware route.

## 8. Evidence and limitations

Recorded expanded run on version 0.4.0: 37 programs under zero, up-to-7 and up-to-19 response wait cycles; 111 differential runs; 66 instruction names covered, including divide by zero and signed overflow, every branch outcome, memory widths/lanes, invalid encodings, misaligned and unmapped accesses, injected instruction/load/store faults, x0 behavior and ordered retirement. Separate reset and RAM-wrapper checks pass. Compiled C produces 36 and 0x000000240000007e through the actual synchronous wrapper.

The reference model was written separately as a sequential byte-memory interpreter, but remains project code and can share conceptual mistakes. External Sail/Spike comparison, official architectural tests, formal proofs, privileged behavior, independent review, synthesis and physical timing remain pending. The infographic is an educational state animation; it is not a live RTL waveform or a performance estimate.

## 9. Versioning

The CPU architecture has one [semantic version](https://semver.org/), `MAJOR.MINOR.PATCH`. It is stored in [VERSION](VERSION) and in this document's title, and the repository check fails if the two differ. Benchmark results and rubric scorecards record it.

### What the version covers

The version tracks the architectural contract that software, adapters and testbenches rely on:

- the implemented ISA string and the semantics of every implemented instruction;
- the execution environment: trap causes, the trap record, privilege modes and CSRs;
- the ports of `rv64_core` and `rv64_bram_soc`, the memory-bus handshake and the retirement trace;
- parameters and their defaults, the reset PC and the sample SoC's memory map;
- documented behavior others may depend on, such as one outstanding memory request.

It does not cover tests, testbenches, tools, benchmarks or documentation wording. The preserved accelerator design keeps its own ABI and adapter version numbers.

### Which number changes

From 1.0.0 onward:

| Bump | When | Examples |
|---|---|---|
| MAJOR | Incompatible change to the contract | Removing or renaming a port; changing the bus handshake; changing a trap cause or the trap record's meaning; changing a parameter default; removing an instruction |
| MINOR | Backward-compatible addition | Adding Zicsr, M or C; a new port or parameter whose default keeps existing behavior; new trap causes for a new feature |
| PATCH | RTL change with no contract change | A bug fix that restores documented behavior; timing, area or clocks-per-instruction improvements with identical architectural behavior |

A bug fix that changes behavior software may already rely on counts as incompatible. Documentation corrections that do not change the contract need no bump.

Before 1.0.0, anything may change (semantic versioning, item 4). This project then bumps MINOR for any contract change, breaking or additive, and PATCH for any other RTL change, and marks every breaking change in the history below.

Proposed criteria for 1.0.0, when the core and bus interfaces are frozen: C1 complete, an external-model comparison in the regression (rubric HG3), and a first exact-part synthesis. Changing these criteria is itself recorded here.

### Releasing a version

For every change to `rtl/cpu/` or to the contract in this document:

1. Decide the bump from the table. A change to tests or wording only needs none.
2. Update [VERSION](VERSION) and this document's title together.
3. Add a row to the history: version, date, commit, summary, whether it breaks compatibility, and the short RTL hashes.
4. After the change lands on `main`, tag that commit `cpu-vX.Y.Z` with an annotated tag.
5. Record the release in [DEVLOG.md](../DEVLOG.md). If the RTL changed, rerun the regression and Dhrystone and reassess [rubric-evidence.json](rubric-evidence.json).

Once Zicsr arrives in C1, consider reporting the version in the implementation-defined `mimpid` CSR so software can read it.

### History

| Version | Date | Commit | Summary | Breaking | RTL hashes: core / RAM wrapper |
|---|---|---|---|---|---|
| 0.1.0 | Designed 2026-10-23; first committed 2026-11-20 | `0483d99`, tag `cpu-v0.1.0` | C0 integer foundation: multicycle RV64I and FENCE.I core, terminal laboratory trap record, unified 64-bit memory bus, retirement trace, 16 KiB synchronous RAM wrapper. Called "revision 0" before versioning began. | Initial version | `831101d3f376` / `a38d2ca4a051` |
| 0.1.1 | 2026-11-20 | tag `cpu-v0.1.1` | Fetch buffer: the last fetched 8-byte beat serves the next instruction when it is in the same beat, skipping FETCH. Cleared by reset, `fence.i` and stores to the beat. Dhrystone: 2,188.2 to 1,706.2 clocks per run. | No | `93117e8a6f97` / `a38d2ca4a051` |
| 0.2.0 | 2026-11-20 | tag `cpu-v0.2.0` | Instruction cache replaces the fetch buffer: direct-mapped, `ICACHE_BEATS` 8-byte lines (default 512, 4 KiB), new parameter on `rv64_core` and `rv64_bram_soc`; same coherence rules. Dhrystone: 1,706.2 to 988.7 clocks per run. | No (new parameter) | `38287831f747` / `143e07b2bbef` |
| 0.2.1 | 2026-11-20 | tag `cpu-v0.2.1` | Loads and stores issue their bus request from EXECUTE; MEMORY holds the same request if needed. One clock less per data access with the synchronous RAM. Bus protocol unchanged. | No | `019ba2dc2dc5` / `143e07b2bbef` |
| 0.2.2 | 2026-11-20 | tag `cpu-v0.2.2` | RAM wrapper acknowledges writes in the clock they are presented; reads unchanged. Stores now retire from EXECUTE. | No | `019ba2dc2dc5` / `5d0323d3916c` |
| 0.3.0 | 2026-11-20 | tag `cpu-v0.3.0` | Data cache for loads: direct-mapped, write-through, `DCACHE_BEATS` 8-byte lines (default 512, 4 KiB), new parameter on `rv64_core` and `rv64_bram_soc`. Loads that hit complete in EXECUTE with no bus request; all memory treated as cacheable. | No (new parameter; loads that hit no longer reach the bus) | `d8359ad08ebe` / `385b91fe9a8a` |
| 0.4.0 | 2026-11-20 | tag `cpu-v0.4.0` | M extension: `mul`, `mulh`, `mulhsu`, `mulhu`, `div`, `divu`, `rem`, `remu` and the `w` forms. Multiply completes in EXECUTE; divide-by-zero, signed overflow and small dividends complete in EXECUTE; other divides use a DIVIDE state, one step per clock from the quotient's highest possible bit. ISA string `rv64im_zifencei`. | No (instructions added) | `e7bf693e3b31` / `385b91fe9a8a` |
| 0.5.0 | 2026-11-20 | tag `cpu-v0.5.0` | Dual issue: the instruction after an integer operation, a data-cache-hit load or a store to another beat executes in the same clock when it is a simple integer operation in the same 8-byte beat, independent of the first. New second retirement port `retire2_*` on `rv64_core` and `retire2_valid` on `rv64_bram_soc`. | No (new ports; trace order unchanged) | `ecd87864afb3` / `94a9e078dbd9` |
| 0.5.1 | 2026-11-20 | tag `cpu-v0.5.1` | Second slot widened: it may come from the next 8-byte beat when that beat is in the instruction cache, and may be a conditional branch with an aligned target. | No | `58d055bc8e34` / `94a9e078dbd9` |
| 0.5.2 | 2026-11-20 | tag `cpu-v0.5.2` | Second slot may also be an aligned load that hits the data cache, read through a second data-cache port, when the first slot is not a store. | No | `84e51832c785` / `94a9e078dbd9` |
| 0.5.3 | 2026-11-20 | tag `cpu-v0.5.3` | Pairing widened again: a not-taken branch may be first; JAL or JALR with an aligned target may be second; a data-cache-hit load may pair after a store to a different beat. | No | `f08610530ed5` / `94a9e078dbd9` |
| 0.5.4 | 2026-11-20 | tag `cpu-v0.5.4` | Second slot may be an aligned store when the first slot does not use the bus (it waits in MEMORY if the bus stalls, and traps precisely on a bus error); integer results of the first slot are forwarded to the second slot's operands in the same clock; same-destination pairs allowed. | No | `07851e6f58ea` / `94a9e078dbd9` |
| 0.5.5 | 2026-11-20 | tag `cpu-v0.5.5` | Branch folding: when the first slot is a jump or a taken branch, the second slot executes the instruction at its target, read from the instruction cache in the same clock; JAL/JALR links are forwarded. | No | `295688213e26` / `94a9e078dbd9` |
