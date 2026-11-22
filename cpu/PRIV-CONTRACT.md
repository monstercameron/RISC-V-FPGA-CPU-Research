# Privilege and platform contract: lab-virt (DRAFT)

**Status: draft proposal, not a version.** Nothing here is implemented in RTL, and nothing here is part of
the architectural contract in `cpu/architecture.md` until the council adopts it as a MINOR version with
its own history row. It describes what the golden model `rv_iss --sys` (milestone M1) implements, so that
the RTL stages S1-S6 (`build/research/rv64gc-linux.md`, section 3) have a fixed target. Where this text
is silent, the RISC-V specifications govern: the unprivileged ISA, the privileged architecture v1.12
(Machine and Supervisor levels), the SiFive CLINT / ACLINT layout and the PLIC 1.0.0 specification.

Claims are kept apart. *Model* means `rv_iss --sys` behaviour (simulation, checked against Spike and
riscv-tests). *RTL* means a hardware stage, none of which exists yet. No physical-hardware claim is made.
This platform is an "S-mode + Sv39 Linux experiment"; it is **not** RVA23S64 (no H, Sstc, Svpbmt, Sscofpmf,
Svinval and others).

## 1. ISA

ISA string: **`rv64imafdc_zicsr_zifencei_zicntr`** (RV64GC plus the base counters), as `riscv,isa` in the
device tree. `misa` = MXL 2 and A, C, D, F, I, M, S, U (0x800000000014112d), read-only (writes are ignored).

| Extension | How it is enabled in the model | Notes |
|---|---|---|
| I, M | always | as `cpu/architecture.md` sections 1 and 4 |
| A | always in `--sys` | LR/SC and all AMOs, .W and .D (section 5) |
| F, D | always in `--sys`; the existing `--fp` arithmetic paths (FP-CONTRACT rules of architecture.md section 1) | `mstatus.FS`: Off makes every FP instruction and fflags/frm/fcsr access cause 2; any f-register write, any fcsr write and any raised flag sets FS = Dirty (3) and SD |
| C | always in `--sys` | RV64C = Zca + Zcd. Reserved and illegal encodings (all-zero parcel, C.ADDI4SPN imm 0, C.ADDIW rd 0, C.ADDI16SP imm 0, C.LUI imm 0, C.LWSP/C.LDSP rd 0, C.JR rs1 0, quadrant 0 funct3 4, C.SUBW-family reserved slots) are cause 2 with tval = the 16-bit parcel. HINT encodings execute as their base instruction |
| Zicsr | always | the CSR set of section 3 |
| Zifencei | always | FENCE.I is a no-op for the model (no decoded-instruction cache) |
| Zicntr | always | cycle, time, instret; gated by mcounteren/scounteren |
| B (Zba/Zbb/Zbs) | **not** in `--sys` | the user-mode cores have it; adding it to the Linux platform is a later decision |
| Misaligned data | not supported | any misaligned load, store or AMO raises cause 4 or 6 (AMO and SC: 6), before translation; OpenSBI emulates misaligned loads and stores for S and U |

The RTL target per core (architecture.md and the plan): the multicycle and pipelined cores would carry
`rv64ima_zicsr_zifencei_zicntr` + S/U + Sv39 (not RV64GC); only the out-of-order core, which has F and D,
can claim RV64GC once it has C. The model implements the full RV64GC so that the same Linux build serves
every stage.

## 2. Privilege modes and traps

- Modes M (3), S (1) and U (0). Reset: M-mode, pc = 0x1000 (the boot ROM), mstatus = UXL 2, SXL 2, everything
  else 0 (MPP = U, FS = Off); all other CSRs 0 except as listed.
- **Trap entry** (exception or interrupt): delegated to S when the current mode is S or U and the cause's
  bit is set in medeleg (exceptions) or mideleg (interrupts); otherwise taken in M. xEPC = pc of the
  trapping instruction (or of the next instruction to execute, for an interrupt), xCAUSE, xTVAL, xPIE := xIE,
  xIE := 0, xPP := previous mode. Vectored xtvec mode (1) applies to interrupts only (base + 4 x cause).
  xtvec bit 1 is read-only zero.
- **xTVAL values:** illegal instruction: the instruction bits (16-bit parcel for a compressed one); EBREAK
  and C.EBREAK: the pc; misaligned, access and page faults: the faulting virtual address (for a 32-bit
  instruction whose second half faults, pc + 2); ECALL and interrupts: 0.
- **Exception causes used:** 1 fetch access, 2 illegal, 3 breakpoint, 4/5 load misaligned/access, 6/7 store-AMO
  misaligned/access, 8/9/11 ECALL from U/S/M, 12/13/15 fetch/load/store-AMO page fault. Cause 0 cannot occur
  (with C every pc is 2-byte aligned and xEPC bit 0 is cleared).
- **medeleg** writable bits: 1-9, 12, 13, 15 (0xb3fe). Bit 0 is not delegable with C, bit 11 never.
  **mideleg** writable bits: SSIP, STIP, SEIP (0x222).
- **MRET:** M only. mstatus.MIE := MPIE, MPIE := 1, MPP := U, MPRV := 0 when the new mode is not M; pc := mepc.
  **SRET:** S or M, and illegal in S when TSR = 1. SIE := SPIE, SPIE := 1, SPP := U, MPRV := 0; pc := sepc.
- **WFI:** illegal in U; illegal in S when TW = 1. Otherwise it retires and the hart waits until
  (mip & mie) != 0, regardless of the global enables; then execution continues after the WFI, or the
  interrupt is taken if it is enabled.
- **SFENCE.VMA:** illegal in U, and in S when TVM = 1. It flushes all cached translations (rs1/rs2 ignored).
  satp access from S with TVM = 1 is cause 2.
- **Interrupt priority:** MEI > MSI > MTI > SEI > SSI > STI; M-level interrupts (not delegated) are enabled
  when mode < M or (mode = M and MIE); delegated ones when mode < S or (mode = S and SIE).
- **When interrupts are taken:** see section 6 (time models).

## 3. CSRs

Any CSR not listed raises cause 2. Access needs the privilege in address bits 9:8; writes to addresses
with bits 11:10 = 3 are cause 2. CSRRS/CSRRC with rs1 = x0 (and the immediate forms with 0) do not write.

| CSR | Behaviour |
|---|---|
| fflags 0x001, frm 0x002, fcsr 0x003 | as architecture.md section 1; cause 2 when FS = Off; a write sets FS = Dirty |
| cycle 0xC00, time 0xC01, instret 0xC02 | read-only views of mcycle, mtime, minstret; from S need mcounteren bit, from U also scounteren bit, else cause 2 |
| sstatus 0x100 | view of mstatus: read mask SIE, SPIE, UBE (0), SPP, FS, SUM, MXR, UXL, SD; write mask SIE, SPIE, SPP, FS, SUM, MXR |
| sie 0x104, sip 0x144 | mie & mideleg, mip & mideleg; sie writes bits in mideleg; sip writes only SSIP and only if delegated |
| stvec 0x105, sepc 0x141, scause 0x142, stval 0x143, sscratch 0x140 | WARL as mtvec/mepc; others full 64 bits |
| scounteren 0x106, mcounteren 0x306 | bits 0-2 writable |
| senvcfg 0x10A, menvcfg 0x30A | only FIOM (bit 0) writable; every other field reads 0 (no Zicbo*, Svpbmt, Sstc, Svadu) |
| satp 0x180 | MODE 0 (Bare) or 8 (Sv39); ASID 16 bits; PPN 44 bits. A write with any other MODE has no effect on any field (the specification; Spike does the same) |
| mstatus 0x300 | writable SIE, MIE, SPIE, MPIE, SPP, MPP, FS, MPRV, SUM, MXR, TVM, TW, TSR; MPP = 2 is written as 0; UXL = SXL = 2; SD = (FS == 3); UBE/SBE/MBE 0 |
| misa 0x301 | 0x800000000014112d, writes ignored |
| medeleg 0x302, mideleg 0x303 | section 2 |
| mie 0x304, mip 0x344 | mie writable SSIE, MSIE, STIE, MTIE, SEIE, MEIE; mip: SSIP, STIP, SEIP writable by software; MSIP (CLINT msip), MTIP (mtime >= mtimecmp), MEIP (PLIC context 0) are read-only; read SEIP = software SEIP OR PLIC context 1 |
| mtvec 0x305 | bit 1 reads 0; modes 0 and 1 |
| mcountinhibit 0x320 | CY (bit 0) and IR (bit 2) writable |
| mhpmevent3-31 0x323-0x33F, mhpmcounter3-31 0xB03-0xB1F | read 0, writes ignored (no Zihpm; the user hpmcounter CSRs do not exist) |
| mscratch 0x340, mepc 0x341, mcause 0x342, mtval 0x343 | mepc bit 0 reads 0 |
| pmpcfg0-15 (0x3A0-0x3AF), pmpaddr0-63 (0x3B0-0x3EF) | 0 PMP entries: every access is cause 2, as Spike with no PMP regions (the specification also allows read-only zero; OpenSBI's probe sees 0 entries either way) |
| mcycle 0xB00, minstret 0xB02 | count retired instructions (a CPI-1 clock); a write sets the value seen after that instruction; inhibited by mcountinhibit |
| mvendorid 0xF11, marchid 0xF12, mimpid 0xF13, mhartid 0xF14, mconfigptr 0xF15 | 0 (marchid is a model option, set to Spike's 5 for comparisons) |
| tselect 0x7A0, tdata1-3 0x7A1-0x7A3, tinfo 0x7A4, mcontext 0x7A8, scontext 0x5A8, mseccfg 0x747 | read 0, writes ignored: Sdtrig with zero triggers, as Spike `--triggers=0` (OpenSBI probes tselect) |

## 4. Virtual memory: Sv39 with Svade

- satp MODE 8 selects Sv39 for S and U (and for M loads/stores when MPRV = 1, with the privilege in MPP).
  Virtual addresses must be sign extensions of bit 38, else a page fault.
- PTE fields: V R W X U G A D, PPN (44 bits). Bits 63:54 (N, PBMT, reserved) must be 0, else a page fault
  (Svnapot and Svpbmt are not implemented). A non-leaf PTE with D, A or U set faults. W without R faults.
- Permission: U pages are not executable from S; S accesses U pages only for loads/stores with SUM = 1;
  U accesses need U = 1; MXR makes X pages readable.
- **Svade:** a leaf with A = 0, or with D = 0 for a store or AMO, raises a page fault; the walker never
  writes memory. Superpage leaves with misaligned PPN fault.
- A PTE address outside DRAM raises an access fault of the original access type.
- Translation caching: any cached translation may be used until the next SFENCE.VMA, satp write, privilege
  change or write of mstatus MPP/MPRV/SUM/MXR (the model flushes on each of these, as Spike does). Software
  must SFENCE.VMA after changing a PTE, as the specification requires; a model that caches less is still
  conforming.
- AMOs and SC translate and fault as stores (cause 6, 7 or 15). LR translates as a load.

## 5. A

- LR.W/D register a reservation set that covers the naturally aligned word or doubleword addressed (the
  A extension's minimum). The model records the LR's physical address, and an SC.W/D succeeds only if a
  reservation is valid and the SC's physical address equals that address (an SC to another address inside
  the set fails, which the specification allows; Spike behaves the same). SC always clears the reservation.
  Ordinary stores do not clear it (a single hart, no other agents).
- **The reservation is also cleared** by any trap (exception or interrupt) in the lab time model, and at
  every chunk end in the Spike time model (section 6). An SC therefore fails only for those reasons.
- AMOs (swap, add, xor, and, or, min, max, minu, maxu) are atomic in this single-hart platform; aq/rl are
  accepted and have no further effect. AMOs and LR/SC to non-DRAM addresses raise an access fault.

## 6. Time models

Both are deterministic in the instruction stream. `mtime` is a 64-bit CLINT register at 10 MHz nominal
(`timebase-frequency` = 10000000 in the device tree).

- **lab (the contract):** mtime advances by 1 every 100 retired instructions, counted from reset or from a
  software write of mtime (the writing store is the first of the next 100). Pending interrupts are evaluated
  before every instruction. WFI with nothing pending and enabled: scripted UART input, when present, is
  delivered first; else, if MTIE is set and mtimecmp > mtime, mtime jumps to mtimecmp (the skipped ticks are
  reported as `idle_ticks`); mtimecmp = 2^64-1 counts as "never"; if nothing can wake the hart the run stops
  with `wfi_deadlock`. The model's mcycle does not advance while idle. A run in which a million traps
  follow one another without a retirement stops with `trap_loop`.
- **This is a laboratory timebase, not a clock.** The 10 MHz in the device tree is nominal: lab time runs
  at 1 tick per 100 retirements whatever the core's clock and IPC, so a stalled core sees time stand still
  and a wide core sees it run fast. That is the price of bit-exact agreement between models and RTL; a
  real-time mode (mtime from clocks, with an `I` record that the models obey) is left for performance runs.
- **spike (comparison only):** reproduces Spike's scheduling: the hart runs in chunks of 5000 steps; a chunk
  ends early after a trap or a WFI; at each chunk end mtime += 50, MTIP is re-evaluated, the LR reservation
  is dropped and the UART may take one input byte. Interrupts are checked at the start of each chunk,
  immediately before each CSR instruction (Spike serializes there), and after each CSR instruction, MRET and
  SRET; minstret/mcycle advance only at those points, by the instructions retired since the last one. While
  waiting in WFI a chunk passes with no instruction; chunks that only the timer can end are skipped together.

RTL stages would implement the lab model (mtime from instret, interrupt check at each retirement boundary;
an out-of-order core cuts its retirement group there).

## 7. Platform: lab-virt (Spike's memory map)

| Region | Base | Size | Behaviour |
|---|---|---|---|
| Boot ROM | 0x0000_1000 | 4 KiB multiple | Spike's reset code: `auipc t0,0; addi a1,t0,32; csrr a0,mhartid; ld t0,24(t0); jr t0`, a zero word, the 64-bit entry address (0x8000_0000), then the DTB at 0x1020. Read and execute only; stores fault |
| SiFive test finisher | 0x0010_0000 | 0x1000 | a 32-bit store at offset 0: 0x5555 = pass (exit 0), 0x3333 = fail (exit code in bits 31:16), 0x7777 = reset (ends the run); reads return 0. Not present in Spike |
| CLINT | 0x0200_0000 | 0xC000 | msip (0x0, bit 0), mtimecmp (0x4000), mtime (0xBFF8); 8-byte accesses to msip are two 4-byte accesses; sub-word accesses select bytes |
| PLIC | 0x0C00_0000 | 0x100_0000 | 31 sources, 4 priority bits, contexts 0 (M) and 1 (S); 4- and 8-byte accesses only; behaviour as Spike's model, including its claim/complete rules. **Deviation from PLIC 1.0, kept to match Spike:** a claim returns only an interrupt whose priority exceeds the context's threshold (PLIC 1.0 lets a claim ignore the threshold), and a level change of a source updates only the first context that enables it |
| ns16550a | 0x1000_0000 | 0x1000 (8 registers) | reg-shift 0, 1-byte accesses only, IRQ 1; THR writes go to the console immediately (LSR THRE/TEMT always 1); RX bytes come from a scripted file: in the lab model one byte is offered, while IER.RDI is set and the RX FIFO is empty (and the FIFO is enabled), at every 5000th retired instruction and whenever the hart idles in WFI; in the spike model one byte per chunk end, as Spike; register behaviour as Spike's model |
| DRAM | 0x8000_0000 | 64 MiB (`--ram`) | read, write, execute |
| HTIF tohost | ELF symbol | | only when the loaded ELF defines `tohost` (riscv-tests): a non-zero store ends the run; 1 = pass |

Other addresses raise access faults. Load layout for Linux: OpenSBI `fw_payload` at 0x8000_0000 with the
kernel `Image` (initramfs built in) at 0x8020_0000; OpenSBI copies the DTB to 0x8220_0000. ELF loading
follows Spike: an ET_EXEC file is loaded at its physical addresses, an ET_DYN file (OpenSBI 1.9 always links
`fw_payload.elf` position-independent at 0) at 0x8000_0000 + its addresses, entry and symbols included.

The device tree source is `sim/cpu/sys/lab-virt.dts` (MIT, ours).

## 8. Trace and checkpoint additions

**Trace (`--trace`, reference.py format) in system mode:** R and W records as today, with virtual
addresses; `insn` of a compressed instruction is the 16-bit parcel zero-extended, `next` = pc + 2. New:
`E pc cause tval` before a trap is taken (exception) and `I pc cause tval` (interrupt, tval 0). A trapping
instruction emits only its E record. Proposed for the RTL stages but not yet emitted: `P m` on a mode change,
`C csr val` for implicit CSR writes, `W va pa bytes` once Sv39 exists in RTL.

**Commit log (`--commit-log`):** Spike's `--log-commits` format (`core   0: P PC (INSN) xN VAL ... mem ADDR
[VAL]`), without Spike's CSR records; `sim/cpu/sys/commit_compare.py` compares the two.

**Full-system state "RVISSST3"** (little-endian u64 unless noted):

| Field | Content |
|---|---|
| magic | "RVISSST3" |
| version | 1 |
| count, pc | instructions retired, next pc |
| x0..x31, f0..f31 | 64 words |
| nkv | number of named words that follow |
| nkv x (name, value) | name: 24 bytes, NUL-padded ASCII; value: u64. Names: prv, fcsr, every CSR of section 3 by name (mstatus ... minstret), mip_sw (software SSIP/STIP/SEIP), mip_dev (device MSIP/MTIP/MEIP/SEIP), wfi, mtime, mtimecmp, tick_accum, chunk_steps, time_spike, idle_ticks, tohost_addr, fromhost_addr, marchid_val, the UART registers (uart_ier ... uart_dlm), the PLIC state (plic_level, plic_cN_enable/pending/claimed/threshold, plic_prioI, plic_cN_pprioI), uart_rx_count, uart_rx_head, uart_in_pos |
| rx queue | 64 words (one byte each) |
| DRAM | base, bytes, then the bytes |
| ROM | base, bytes, then the bytes |

The model also saves its LR reservation (`resv_addr`) and its pending counter and interrupt-check state
(`irq_check`, `iter_n`, `iter_inh`, `csr_serialized`, `mcycle_written`, `minstret_written`), so that a model
restore continues exactly; an RTL restore may drop the reservation, which is legal (an SC may then fail).
The translation cache is not saved (it is flushed on restore).

**RTL restore (sketch, not implemented; the RTL has no privilege support before S1):** an M-mode restore stub
placed in the boot ROM or in a reserved DRAM page, following `bench_checkpoint.py`: (1) write the device
state through MMIO (CLINT mtime and mtimecmp, PLIC priorities, enables and thresholds, UART registers);
(2) restore f0-f31 and fcsr with FS = Dirty; (3) write the S CSRs, satp, then medeleg/mideleg/mie/mtvec/
mscratch/mcounteren/menvcfg; (4) write mstatus with MPP = the saved mode, MPIE = the saved MIE and MPRV as
saved, and mepc = the saved pc; (5) load x1-x31 from a table (x31 last, through an M-mode scratch register);
(6) MRET. The stub's own instructions are not part of the checkpointed program and are excluded from trace
comparisons, as the user-mode stub's are. mcycle/minstret and mtime are written last so the stub's own
instructions do not disturb them (or the comparison window starts after the MRET with the counters as saved
plus the stub length, a contract choice to make with S1). A checkpoint taken in M-mode (inside OpenSBI)
cannot use MRET to resume the same mode transparently; checkpoints should be taken in S or U mode.

## 9. Differences from Spike (the comparison reference)

Configured to match as closely as possible: the same DTB (`--dtb`, which sets Spike's ISA string, PMP count
(0) and MMU type (Sv39)), `--triggers=0`, `-m64`, marchid 5. Known differences:

- The SiFive test finisher exists only in rv_iss; Spike ends a Linux run through HTIF or by an instruction
  limit.
- Spike's misa is writable (M, A, F, D, C); rv_iss ignores misa writes. riscv-tests `rv64mi-ma_fetch` clears
  misa.C and so differs from Spike's commit log (both pass the test).
- The lab time model differs from Spike's scheduling by design; comparisons use `--time spike`.
- Spike fetches instructions from any MMIO device; rv_iss only from DRAM and the boot ROM.
- AMOs on MMIO addresses: Spike performs them on the device; rv_iss raises an access fault.

**Measured agreement (model only, 2026-11-22):** riscv-tests p environment, 132 of 134 pass on rv_iss
(`rv64ui-ma_data` needs misaligned data, `rv64mi-pmpaddr` needs PMP entries); 133 of 134 commit logs equal
Spike's (the misa.C case above). The OpenSBI + Linux + busybox boot to power-off: 43,139,225 instructions
equal in `--time spike`, up to the test-finisher read that only rv_iss models, after which rv_iss powers off
through the finisher (exit 0) at instruction 43,139,255. (Recorded in the
DEVLOG rows of the M1 hand-off; these are model results, not RTL or hardware results.)

## 10. Open questions for adoption

1. The PLIC claim rule: Spike's (threshold applies to claims, as now) or PLIC 1.0's.
2. ASIDLEN: 16 in the model (as Spike); RTL may want 0 (then the contract must allow both, and comparisons
   must configure Spike to match, which needs a Spike patch).
3. Whether the RTL multicycle core's Linux variant must carry C, F and D, or a separate rv64ima kernel is
   kept for it.
4. Misaligned data: trap (now) or the RVA23 Zicclsm behaviour.
5. The lab timebase (section 6) against a real-time mode for performance runs.
