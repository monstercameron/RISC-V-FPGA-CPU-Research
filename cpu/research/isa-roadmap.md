# ISA and system-feature roadmap: from rv64imb to RVA23U64 (and the S64 track)

Research note by the research engineer, 2026-11-22 00:46 EST (clock). Read-only research: the
repository was not changed. This file is in the ignored `build/research/` directory and is not
committed. Baseline: commit `e8eeae3` on main (released architecture 0.16.2), the 0.17.0 F/D candidate
in release checks (DEVLOG 00:24 to 00:39), and the RVV-subset golden model (DEVLOG 00:22).

**How to read this.** **Fact** marks something taken from a named source: the RVA23 PDF in the repo
(`references/rva23-profile-v1.0.pdf`, "RVA23 Profiles, Version 1.0, 2024-10-17, Ratified"; page
numbers are the PDF's own), a repository file, or an official web page listed in section 8. **Spec
(memory)** marks ISA-manual detail I stated from knowledge without fetching the chapter here. Check it
against the ISA manual before it goes into a contract. **Judgement** marks my recommendation or
estimate. No benchmark number in this file is new: every measured number is quoted from DEVLOG.md or
`cpu/*.md`. Everything else is an expectation.

Size scale (judgement): **S** = one version step, models and RTL together in about a day of agent
work; **M** = several days, usually one version with a review; **L** = several versions or a new
subsystem (weeks).

---

## 1. Gap table against RVA23

### 1.1 RVA23U64: mandatory extensions (Fact, PDF pp. 4-5)

The PDF lists, as mandatory: RV64I base (little-endian); M, A, F, D, C, B, Zicsr, Zicntr, Zihpm, Ziccif,
Ziccrse, Ziccamoa, Zicclsm, Za64rs, Zihintpause, Zic64b, Zicbom, Zicbop, Zicboz, Zfhmin, Zkt (carried from
RVA22U64); and V, Zvfhmin, Zvbb, Zvkt, Zihintntl, Zicond, Zimop, Zcmop, Zcb, Zfa, Zawrs, Supm (new in
RVA23U64). That is 33 items plus the base. `cpu/architecture.md` section 5 already names all 33. Its
status column is out of date for F, D and Zicsr.

| Extension | RVA23U64 | Project status (Fact: architecture.md, FP-/RVV-CONTRACT, DEVLOG) | On user's list? |
|---|---|---|---|
| RV64I | Mandatory base | **Done**, terminal EEI; local tests only, not ISA-certified | n/a |
| M | Mandatory | **Done** (0.4.0) | n/a |
| B = Zba+Zbb+Zbs | Mandatory | **Done** (0.6.0) | n/a |
| F, D | Mandatory | **In progress**: 0.17.0 candidate, out-of-order core only, define `RV64_OOO_FPU`, default off | yes |
| Zicsr | Mandatory | **Partial / in progress**: the six forms on fflags/frm/fcsr only (0.17.0); vector CSRs in the RVV subset; every other CSR is illegal | yes |
| V | Mandatory | **In progress**: Zve64f-level subset (golden model done; RTL not started), `RV64_OOO_V`; not V | yes |
| A (Zaamo+Zalrsc) | Mandatory | **Missing** | yes |
| C (Zca, plus Zcd with D) | Mandatory | **Missing**; 32-bit instruction alignment (cause 0 on 2-aligned targets) | yes |
| Zcb | Mandatory | **Missing** (needs C) | yes |
| Zcmop | Mandatory | **Missing** (needs C) | **no** |
| Zicond | Mandatory | **Missing** | yes |
| Zimop | Mandatory | **Missing**: SYSTEM funct3=100 encodings trap today; Zimop needs them to write 0 to rd | **no** |
| Zihintpause | Mandatory | **Executes, not declared**: `pause` is a FENCE encoding (pred=W, succ=0), and the reference model accepts any FENCE with funct3 0 (`sim/cpu/reference.py` line 220). The RTL has no directed test for it yet | **no** |
| Zihintntl | Mandatory | **Executes, not declared**: `ntl.*` are `add x0, x0, x2..x5` HINTs, which write x0 and so do nothing. `c.ntl.*` needs C | **no** |
| Zicntr | Mandatory | **Missing** (benchmarks use mailbox markers instead) | yes |
| Zihpm | Mandatory | **Missing** | yes |
| Zicbom | Mandatory | **Missing**: no CBO, no cache-block or PMA contract | yes |
| Zicboz | Mandatory | **Missing** | yes |
| Zicbop | Mandatory | **Executes as hints, not declared**: `prefetch.i/r/w` are ORI HINTs with rd=x0 (Spec (memory)), which execute as no-ops today | yes |
| Zic64b | Mandatory | **Missing**: the CBO block must be 64 B; the L1 lines are 8 B (architecture section 2) | **no** |
| Ziccif | Mandatory | **Not qualified**: fetch reads aligned 8-byte beats, which makes 32-bit fetches atomic. No PMA contract states it, and C will need it restated | **no** |
| Ziccrse | Mandatory | **Missing** (needs A) | **no** |
| Ziccamoa | Mandatory | **Missing** (needs A) | **no** |
| Za64rs | Mandatory | **Missing** (needs A; a one-reservation design is trivially within 64 B) | **no** |
| Zicclsm | Mandatory | **Missing**: misaligned loads and stores trap (cause 4/6) | **no** |
| Zfhmin | Mandatory | **Missing**: FP-CONTRACT makes fmt=10 (H) illegal | yes |
| Zfa | Mandatory | **Missing** (FP-CONTRACT section 9 defers it) | yes |
| Zkt | Mandatory | **Not qualified**; risk: the out-of-order core's value prediction covers multiplies (section 2.9) | yes |
| Zvfhmin | Mandatory | **Missing**: needs vector widening and narrowing converts, which are out of the subset | yes |
| Zvbb | Mandatory | **Missing** | yes |
| Zvkt | Mandatory | **Not qualified** | yes |
| Zawrs | Mandatory | **Missing** (needs A) | yes |
| Supm | Mandatory | **Missing**: needs a user execution environment and a means to select PMLEN 0 and 7 | **no** |

Fact (PDF p. 6): "Recommendations: implementations are strongly recommended to raise illegal-instruction
exceptions on attempts to execute unimplemented opcodes". The project already does this; keep it.

### 1.2 RVA23U64: optional extensions (Fact, PDF pp. 5-6)

| Extension | Kind (PDF) | Project status | On user's list? |
|---|---|---|---|
| Zvkng, Zvksg | Localized options | Missing | no |
| Zabha | Development option | Missing | no |
| **Zacas** | Development option, **not mandatory** | Missing | yes |
| Ziccamoc | Development option | Missing | no |
| Zvbc | Development option | Missing | no |
| Zama16b | Development option | Missing | no |
| **Zfh** | Expansion option, **not mandatory** | Missing | yes |
| Zbc | Expansion option | Missing | no |
| Zicfilp, Zicfiss | Expansion options | Missing | no |
| Zvfh | Expansion option | Missing | no |
| Zfbfmin, **Zvfbfmin**, **Zvfbfwma** | Expansion options, **not mandatory** | Missing | Zvfbfmin and Zvfbfwma yes |
| Transitory | none in RVA23U64 | | |

Not in RVA23U64 but implemented: **Zifencei** (done since 0.4.0). Fact (PDF p. 7): it is mandatory in
RVA23S64, not in U64. The **Zve64f** subset is a stepping stone and is not a profile item.

### 1.3 What the user's list leaves out, or gets wrong

- **Mandatory in U64 and missing from the list (Fact, PDF pp. 4-5):** Zimop, Zcmop, Zihintpause,
  Zihintntl, Zic64b, Ziccif, Ziccrse, Ziccamoa, Zicclsm, Za64rs and Supm. Zifencei is done.
- **On the list but optional in RVA23U64:** Zacas (development), Zfh, Zvfbfmin and Zvfbfwma
  (expansion). They are worth doing for the LLM future work, but they do not count toward the
  profile.
- **System features on the list that RVA23U64 does not require:**
  - M-mode CSRs and mret, PMP, U and S modes, Sv39, interrupts, Sstc and Svinval.
  - Fact (PDF p. 4): U64 specifies only what user mode sees. ECALL "causes a requested trap to the
    execution environment".
  - Judgement: an RVA23U64 *core* still needs some of them in practice:
    - Zicntr's `time` needs a timer source.
    - Supm needs a selectable PMLEN.
    - Zicclsm may be met by an invisible trap to M-mode emulation.
    - The official test environments use machine-mode trap handlers (section 3.2).
  - So a minimal M-mode foundation is on the critical path even for U64.

### 1.4 RVA23S64 additions for an OS (Fact, PDF pp. 7-9)

- **Based on** privileged architecture 1.13. RVA23S64 includes all RVA23U64 mandatory extensions, plus
  Zifencei.
- **Mandatory privileged extensions:**
  - Ss1p13.
  - Carried from RVA22S64: Svbare, Sv39, Svade, Ssccptr, Sstvecd, Sstvala, Sscounterenw, Svpbmt and
    Svinval.
  - **New in RVA23S64:** Svnapot, Sstc, Sscofpmf, Ssnpm, Ssu64xl and **Sha**.
  - Sha comprises H, Ssstateen, Shcounterenw, Shvstvala, Shtvala, Shvstvecd, Shvsatpa and Shgatpa.
  - The hypervisor is mandatory for RVA23S64.
- **Expansion options:** Sv48, Sv57, Zkr, Svadu, Sdtrig, Ssstrict, Svvptc and Sspm. Sv48 is
  **optional**, not mandatory. The profile has no localized, development or transitory privileged
  options.
- **ECALL:** from U it traps to S (contained); from S it is a requested trap to the EEI.
- **Not in any RVA23 profile:**
  - PMP and machine mode itself. M-mode is the platform's business, for example Sm1p13 and the
    RVA23 platform specs.
  - Judgement: PMP is still needed for any M+U system that isolates firmware.

Judgement: architecture.md section 6 already says full RVA23S64 is a separate project. The hypervisor
(Sha) alone is an L-sized project on top of S-mode and Sv39. I recommend an explicit milestone named
"S-mode + Sv39 Linux-capable experiment, not RVA23S64", as the document already warns.

---

## 2. Per-extension work

Common rules (Judgement, following the FP-CONTRACT precedent):

- Every extension is a build option with default off: a reference.py/rv_iss flag, a `test_cpu.py`
  flag, and an RTL define or parameter. With the option off, everything stays byte-identical.
- An extension's encodings are cause 2 (illegal) while it is off.
- Each option needs:
  - **Models**: reference.py (the authority; Python), rv_iss.c (speed; benchmarks), or `build/cpu/fp/`
    models until they are merged.
  - **test_cpu**: a flag, directed cases and random program generation.
  - **Contract**: an architecture.md section, an ISA-string change and the trace format.
- Core applicability is my recommendation:
  - The **multicycle** core (MC) is the teaching and integer reference core.
  - The **pipelined** core (PIPE) is the realistic synthesizable path to the C7 FPGA proof.
  - The **out-of-order** core (OOO) is the behavioural flagship. It cannot be synthesized at its
    current width (32-wide fetch, 512-entry ROB).
- "All three" is worth it only where the change is a small ALU or decode change. A "proper" physical
  core would be PIPE, not OOO.

### 2.1 Zicsr (full), M-mode CSRs and mret: the "C1 foundation"

- **Status:**
  - 0.17.0 adds the six CSR forms on CSRs 0x001-0x003 only, with FS treated as permanently Dirty
    (FP-CONTRACT section 2).
  - The RVV subset adds vector CSRs.
  - There is no mstatus or misa. Fact, architecture.md section 1: misa is "not falsely advertised".
- **Models:**
  - A CSR file in reference.py and rv_iss: mstatus (MIE, MPIE, MPP, FS, VS, SD, plus later TW, MPRV,
    SUM and MXR), misa, mtvec (direct, optionally vectored), mepc, mcause, mtval, mscratch, mhartid,
    mvendorid, marchid, and mimpid (architecture.md section 9 suggests it report the version),
    mconfigptr, menvcfg and mcountinhibit.
  - mret.
  - ecall, ebreak and every exception become a jump to mtvec, with mepc, mcause and mtval written.
  - WFI as a no-op (legal: Spec (memory)).
  - Unknown CSRs and writes to read-only CSRs are cause 2.
  - rv_iss needs the same CSRs, plus CSRs in its state file.
- **test_cpu:**
  - Directed tests: trap entry and return for every cause, nested traps, mepc alignment, WARL fields
    (mtvec.MODE, mstatus.MPP, FS/VS), CSR read-only and illegal access, mret with MPP, csrrs/csrrc
    with x0, and exception priority (Spec: the privileged manual's synchronous exception priority
    table).
  - Random programs with a fixed trap handler in the image.
- **Cores:**
  - **All three.** A firmware trap handler is what turns the terminal laboratory EEI into a real
    execution environment.
  - In MC and PIPE it is moderate: one CSR unit, serialized CSR instructions, and trap redirect from
    the stage that already reports traps.
  - In OOO: CSR instructions serialize at the ROB head, as fcsr writes already do (FP-CONTRACT
    section 8). The trap becomes a flush plus a redirect to mtvec instead of a halt, and mret is a
    serializing jump.
  - FS and VS: FP and V instructions trap when Off, and Dirty is set at retirement.
- **Contract:** the largest contract change since 0.1.0.
  - The trap contract (architecture.md section 4) gains a mode in which `trap_valid` is not terminal.
  - Proposed: a define or parameter `RV64_PRIV`, default 0, keeps the terminal record bit for bit.
    With 1, traps vector to mtvec, and a terminal stop happens only through a test-end mechanism
    (mailbox, or `ecall` with a convention).
  - Trace: today `T pc cause tval` ends the trace. Add a non-terminal record, for example
    `E pc cause tval`, followed by `C` records for mepc, mcause, mtval and mstatus.
  - Add a `P m` record whenever the privilege mode changes. Reuse the existing
    `C <csr> <value>` format for every CSR write.
  - MINOR bump, and per section 9 mark it **breaking** if the default ever changes.
- **Size:** L (contract, three cores, handler firmware, the new tests).
- **Depends on:** nothing. It is the prerequisite for FS/VS, Zicntr, Zihpm, interrupts, U and S
  modes, PMP, Supm, Zicclsm by emulation, Zawrs's TW, and the official test environments.

### 2.2 F and D (in progress, 0.17.0)

- **Status:** golden models (`reference_fp.py`, `rv_iss_fp.c`), test_cpu `--fpu` with 630 runs per
  cache size, OOO only, plus a regression watch with the FPU built in (Fact, DEVLOG 00:24 to 00:39).
- **Remaining work** (Judgement):
  - Merge the `build/cpu/fp/` models into `sim/cpu/` (they are outside the maintained tree).
  - Codex review (running).
  - Once 2.1 lands: mstatus.FS with Off trapping and Dirty tracking, a further MINOR (FP-CONTRACT
    section 2 already plans this).
  - Independent IEEE checks: TestFloat-style vectors (section 3), plus riscv-tests rv64uf and rv64ud.
- **Cores:** OOO only for now. For a synthesizable FPGA core, a PIPE FPU is an L-sized project in
  itself: an iterative divide and square root, an FMA with an FPGA DSP mapping, and a 64-bit f
  register file. I recommend deferring it until C7 and labelling every PIPE bitstream rv64imb.
- **Size / depends:** in progress. Then Zfa, Zfhmin, Zcd (C), V FP and the FS bit all depend on it.

### 2.3 V (in progress: Zve64f subset)

- **Status:**
  - Fact (RVV-CONTRACT section 1): Zve64f level, VLEN 128, 256 or 512 as a build parameter, FP32
    vector arithmetic only.
  - Fact (RVV-CONTRACT section 8): out of scope are FP64 vectors, widening and narrowing, fixed point,
    segments, `vfrec7`/`vfrsqrt7`, `vrgatherei16`, `vadc`/`vmadc`, vfncvt/vfwcvt, Zvbb and Zvkt.
  - Golden model done (DEVLOG 00:22): 27,000 random programs matched three ways.
- **Remaining work to full V** (Judgement), as separate versions:
  - (a) RTL for the subset (OOO);
  - (b) Zve64d: FP64 vector arithmetic (needed by smallpt-style double code);
  - (c) widening and narrowing integer and FP ops, and vfwcvt/vfncvt. LLVM already emits vwmulsu and
    vwadd for 32-bit indices (Fact, DEVLOG 00:22);
  - (d) fixed point (vsadd, vssra and vnclip, with vxrm and vxsat made live);
  - (e) segment loads and stores;
  - (f) vfrec7/vfrsqrt7 (exact table semantics), vrgatherei16, vadc/vmadc/vsbc and the remaining
    permutes;
  - (g) vector state in rv_iss state files;
  - (h) mstatus.VS, after 2.1.
- C5 exit evidence (architecture section 6) also asks for restart and vstart, and context save.
  Element-precise traps already set vstart (RVV-CONTRACT section 6), but they only become
  *restartable* once a handler exists (2.1).
- **Cores:** OOO only. A vector unit in MC or PIPE is not worth it before C7. Zve32x on PIPE could be
  a later FPGA option.
- **Size:** L (several versions). **Depends on:** F/D, then 2.1 for VS and restart. Zvfhmin, Zvbb,
  Zvkt and Zvfbf* all depend on it.

### 2.4 Zicond

- **Spec (memory):** `czero.eqz rd, rs1, rs2` gives `rd = (rs2 == 0) ? 0 : rs1`, and `czero.nez` the
  reverse. Both are OP (0x33) with funct7 0000111 and funct3 101 or 111.
- **Models:** about 4 lines in reference.py's `bitmanip_op`-style table and in rv_iss. test_cpu:
  directed cases (rs2 zero and non-zero, rd = rs1 = rs2, x0 operands) plus inclusion in the random
  generator.
- **Cores:** **all three**. It is one 2-input ALU op and can share the existing B function in MC
  (which has 3 issue slots) and PIPE.
  - In OOO it is a simple integer op on any ALU.
  - Fusion and rename folding (0.11.2, 0.14.3) can treat it like other ALU ops. Only the
    folding/fusion tables need an entry.
- **Contract:** ISA string `_zicond` with the option on. No trace change.
- **Size:** S. **Depends on:** none.

### 2.5 Zfa

- **Spec (memory), RV64:**
  - fli.s and fli.d (32-entry constant table; fli.h only with Zfh/Zfhmin);
  - fminm and fmaxm (NaN-propagating);
  - fround and froundnx (round to integral in FP format);
  - fcvtmod.w.d (modular conversion, RTZ only);
  - fleq and fltq (quiet compares).
  - fmvh.x.d and fmvp.d.x are RV32-only, so they do not apply.
- **Models:** reference_fp.py and rv_iss_fp. The fli table must be bit-exact. fround/froundnx flag
  rules: NX only for froundnx, NV for sNaN. fcvtmod.w.d flags: NV for NaN/inf/out of range, NX when
  inexact.
- **test_cpu:** directed corner cases (all 32 fli entries, NaN, ±0, ±inf, halfway values, every rm
  for fround) and random FP programs. riscv-arch-test has a Zfa directory (section 8).
- **Cores:** OOO only (where the FPU is). All of it fits the existing FP add/compare/convert pipes.
- **Contract:** FP-CONTRACT addendum. No new trace records.
- **Size:** S-M. **Depends on:** F/D.

### 2.6 A (Zaamo + Zalrsc), Ziccrse, Ziccamoa, Za64rs

- **Spec (memory):** LR.W/D, SC.W/D and AMO{SWAP, ADD, AND, OR, XOR, MIN, MAX, MINU, MAXU}.{W,D}, with
  aq/rl bits. AMOs and LR/SC must be naturally aligned. Misaligned AMOs give cause 6 (or cause 7 when
  the EEI says so, per the spec's allowance). Atomicity is under RVWMO.
- **Models:**
  - reference.py and rv_iss: a single reservation (address and size).
  - SC succeeds iff the reservation is valid and covers the address. Any SC clears it. A store to the
    reserved set may clear it.
  - Judgement: specify that a trap, a retired store by this hart to the set, and (later) an interrupt
    clear it. Make that deterministic so traces match.
  - LR/SC forward progress (Ziccrse "RsrvEventual") is trivial for a single hart with no other
    agents. A constrained LR/SC loop must succeed.
- **test_cpu:** directed cases for every AMO at both widths (sign extension of .W results), SC
  failure paths, misaligned and access faults (the AMO faults as a store, cause 6/7), aq/rl
  encodings, and LR/SC with intervening stores, traps and fence.i.
- **Cores:**
  - **OOO**: an AMO executes **at retirement**, non-speculatively. It is a read-modify-write that
    holds the bus, the way stores are written at retirement today.
    - In section 3's single-master bus, core-side RMW at retirement is atomic because no other agent
      exists. Judgement: state that explicitly. A bus-level atomic (an AXI exclusive or a ReadUnique)
      is needed only when DMA or a second hart appears.
    - Younger loads to the same bytes must not complete with stale data. The existing
      memory-order-violation machinery (0.11.1 load marking, the 0.15.6 load-wait table) has to treat
      an AMO as a store whose address is known at issue.
    - LR is a load that sets the reservation at retirement. SC is a store whose rd (0/1) is known only
      at retirement, so its consumers wait.
    - Interaction with `N_MISS` split reads: an AMO's read must be a blocking read. The "trap drain
      rule" (section 3) applies.
  - **PIPE**: worth it, because a synthesizable Linux-class core needs A. The read-modify-write
    sequences in M, using the existing X stage.
  - **MC**: worth it only if MC remains the firmware core; otherwise skip. Judgement: skip MC.
- **Contract:**
  - New memory-ordering text in architecture.md section 3: RVWMO for one hart and one master; what
    aq/rl and FENCE mean on this bus; the reservation rules; and the Za64rs reservation size (8 B or
    64 B). Ziccamoa and Ziccrse become statements about main memory in the PMA section.
  - Trace: an AMO emits `W` (if it writes) then `R` (rd = old value). SC emits `W` only on success.
  - Adding PMA attributes ("atomics supported") first needs the PMA mechanism (section 2.11).
- **Size:** M (OOO), M (PIPE). **Depends on:** a stated PMA region for "main memory" (cheap: the
  single RAM region). It does not need privilege, but see Zawrs.

### 2.7 Zawrs

- **Spec (memory):** `wrs.nto` and `wrs.sto` (SYSTEM encodings) stall until the reservation set is
  invalidated, an interrupt is pending, or an implementation-defined condition. They may complete
  immediately. With mstatus.TW=1 in lower modes, an un-terminated `wrs.nto` raises an illegal
  instruction after a bounded time.
- **Judgement:** with one hart and no other writers, the only useful wake sources are interrupts and a
  timeout. Implement it as "complete immediately, or after a fixed timeout". It is legal and
  deterministic for traces.
- **Models:** trivial (a no-op that requires a valid encoding). test_cpu: encoding tests.
- **Cores:** OOO (and PIPE if it gets A).
- **Contract:** one line, plus the TW behaviour once U-mode exists.
- **Size:** S. **Depends on:** A (the reservation set it waits on). Meaningful only after interrupts.

### 2.8 C (Zca, plus Zcd with D), then Zcb and Zcmop

- **Spec (memory):**
  - With C, IALIGN becomes 16. Cause 0 (misaligned target) can then never occur: JALR clears bit 0,
    and branch and JAL offsets are even.
  - On RV64 with D, "C" means Zca+Zcd (no Zcf on RV64).
  - Zcb: c.lbu, c.lhu, c.lh, c.sb, c.sh, c.zext.b, c.sext.b, c.zext.h, c.sext.h, c.zext.w, c.not and
    c.mul. The sign and zero extensions need Zbb or Zba, which exist; c.mul needs M, which exists.
  - Zcmop: c.mop.1, 3, ..., 15, in reserved c.lui encodings. They do not write rd. Zcmop needs Zca.
  - `c.ntl.*` (Zihintntl) also arrives with C.
- **Models:**
  - reference.py and rv_iss: a 16-bit expander (C to the equivalent 32-bit op), PC + 2, and fetch of
    a 32-bit instruction that straddles an 8-byte beat or a cache line.
  - Instruction-access faults on the second half report tval = the address of the faulting half
    (Spec (memory): tval may be the instruction address or the faulting portion; fix a choice).
  - Self-modifying code tests must cover a store that changes half of a straddling instruction.
- **test_cpu:** every compressed encoding, including reserved and illegal ones (c.addi4spn with
  imm=0, c.lui and c.addi16sp with 0, all-zero halfword = illegal); mixed 16/32 streams at every
  alignment; straddling at beats, lines and RAM edges; branches to 2-mod-4 targets; RAS and BTB at
  2-byte granularity; FENCE.I over compressed code.
- **Cores:**
  - **OOO**: the largest front-end change.
    - Fetch currently decodes `FW` = 32 *instructions* per clock from the cache. Each one is a 4-byte
      slot at a fixed offset in the fetched beats. The BTB stores targets with bits 1:0 = 0 and
      checks `d[1:0] == 0` (`btb_fits`).
    - With C, instruction boundaries form a serial length-decode chain over up to 64 parcels for 32
      instructions.
    - The BTB and the loop, TAGE and value-prediction tables are PC-indexed at 4-byte granularity.
      Bit 1 must enter their indexing.
    - Return addresses become PC+2 or PC+4.
    - An instruction can straddle two beats or two cache lines (a fetch miss in the middle of an
      instruction).
    - Predecode (direct jumps, returns) must handle C.J, C.JAL (RV32 only, so not on RV64), C.JR and
      C.JALR.
    - Rename folding of `addi`/`li`/`mv` (0.12.3) must accept their compressed forms. They expand to
      the same ops if expansion happens before rename, which is the recommended approach.
  - **PIPE**: worth it for the FPGA core (code density matters most with small BRAM I-caches).
    - A 4-entry fetch queue holding 16-bit parcels, a realigner, and a BTB indexed by PC[.:1].
    - M (moderate); the realigner is the classic hard part.
  - **MC**: its dual/triple issue reads "the next instruction in the same 8-byte beat". C breaks those
    pairing rules. Judgement: do not add C to MC. Keep MC at IALIGN 32.
- **Contract:**
  - Section 1 "Instruction alignment" changes, and cause 0 behaviour changes when the option is on.
  - The retirement trace `insn` field carries a 16-bit instruction zero-extended. This is
    unambiguous, since 32-bit encodings have bits 1:0 = 11. `next` = pc+2.
  - Ziccif must be restated: naturally aligned fetches up to 32 bits are atomic. A straddling 32-bit
    instruction at 2 mod 4 is not naturally aligned, so it is exempt (Spec (memory)).
- **Size:** C: L on OOO, M on PIPE. Zcb: S after C. Zcmop: S after C and Zimop.
- **Depends on:** D (for Zcd, so "C" can be claimed on RV64D), Zbb, Zba and M (for Zcb), Zimop (for
  Zcmop).

### 2.9 Zkt and Zvkt (data-independent latency)

- **Spec (memory):** Zkt lists base integer ALU ops, shifts, `mul`/`mulh*`/`mulw`, some Zbb/Zbkb ops,
  clmul and the scalar crypto ops. Their latency must not depend on operand values. Division is
  **not** in the list, and loads and stores are out of scope. Zvkt does the same for a list of vector
  instructions.
- **Project-specific finding (Judgement, from architecture.md section 2 text):**
  - Since 0.11.1 the OOO core *value-predicts* loads, multiplies and divides. Since 0.15.1 it does so
    after 32 equal results at a PC. A correctly predicted multiply gives its consumers the value at
    rename; a wrong guess refetches. Consumer timing then depends on the multiply's *values*. That
    likely violates Zkt for `mul*`.
  - Rename-time constant computation (0.14.3) and offset folding (0.12.3) depend on whether operands
    are constants from the instruction stream, not on data values. They are probably fine, but the
    claim needs review.
  - The early-terminating divide is fine (div is not in Zkt).
  - Proposed fix: exclude Zkt-listed ops (`mul`, `mulh`, `mulhsu`, `mulhu`, `mulw`) from value
    prediction when Zkt is claimed. Or prove that the prediction is value-independent, which it is
    not. Measure the Dhrystone and 7-Zip cost.
  - Zvkt: the vector unit must not skip zero elements or shortcut on values. The ISA manual decides
    whether timing may depend on vl, vtype and mask; check the Zvkt chapter before the contract
    states it.
- **Models:** none (timing). **test_cpu:** a timing test bench that runs each listed instruction
  with random operands and checks that its issue-to-wake latency, and that of a dependent chain, is
  constant. This is a new kind of check.
- **Cores:** all that implement the listed ops. MC and PIPE already have fixed latencies.
- **Contract:** a statement listing the instructions and their fixed latencies.
- **Size:** S (MC, PIPE), M (OOO, because of the VP change and its benchmark cost). **Depends on:**
  none; Zvkt depends on V.

### 2.10 Zicntr and Zihpm

- **Spec (memory):** `cycle`, `time` and `instret` (0xC00-0xC02) and `hpmcounter3-31` (0xC03-0xC1F)
  are read-only shadows of mcycle, mtime (memory-mapped) and minstret.
  - U-mode access is gated by mcounteren (and scounteren).
  - hpmcounters may be hard-wired zero. Judgement: Zihpm with all-zero counters is arguably legal,
    but useless for this project; implement real events (branch mispredict, I/D miss, ROB-full
    stall, value-prediction recovery).
- **Models:** `cycle`, `time` and `hpm*` are *non-deterministic* with respect to the ISA models.
  - instret is deterministic (the retired count, minus the reading instruction itself; Spec: instret
    counts instructions retired *before* the read).
  - Trace (Judgement): mark such reads with a new record, for example `N csr value`, meaning "value
    taken from the DUT". The models then adopt the DUT's value, as Spike-based co-simulation does.
    The checker verifies monotonicity and plausibility bounds (cycle ≥ instret since reset, for
    instance).
- **Cores:**
  - **All three**: counters are cheap.
  - OOO: reading `cycle` at execute versus at retirement is a semantic choice. Neither is wrong,
    since CSR reads are not ordered. Pick "at retirement" for reproducibility.
  - minstret must count the RW-wide retirement per clock, and folded instructions too.
- **SoC:** `time` needs mtime. Fact (architecture.md section 3): every address is cacheable today, and
  "before any memory-mapped peripheral is added, a PMA mechanism must mark its region uncacheable".
  So `time` needs the PMA step. Alternative: a core input port `mtime[63:0]` driven by the SoC, which
  avoids MMIO for the read path.
- **Contract:** CSR list, port (if mtime is an input), trace record.
- **Size:** Zicntr S-M (the trace non-determinism is the work), Zihpm S-M (events). **Depends on:**
  2.1 (CSR file; mcounteren needs U), and the PMA or mtime port.
- **Benefit:** benchmarks can self-time. riscv-tests' `benchmarks/common/util.h` (the source of the
  vendored Dhrystone) reads cycle and instret through `setStats`. The project's port layer replaces
  that today (Fact, vendor/dhrystone/SOURCE.txt "the port layer ... supplies util.h").

### 2.11 PMA, ACLINT and interrupts (M-mode)

- **PMA (L-sized foundation):** regions with attributes (cacheable, idempotent, atomics, misaligned,
  fetchable), checked at the LSU and fetch.
  - Needed for MMIO (uart, timer), Zicbom semantics, Ziccamoa, Zicclsm and Ziccif statements.
  - Fact (architecture section 3): fetch reads whole 8-byte beats, and "a later MMIO/PMA adapter must
    not turn this into an over-wide side-effecting peripheral read".
- **ACLINT MTIMER/MSWI** in rv64_bram_soc (mtime, mtimecmp, msip). This changes the memory map, a
  contract item.
- **Interrupts:** mie, mip, mideleg (with S), MTI, MSI and MEI, and WFI that waits for an interrupt.
  - OOO: take interrupts at a retirement boundary with no outstanding split reads (the existing trap
    drain rule).
  - Fact (architecture section 6, C1 exit evidence): the "pending IRQs during memory stalls" case.
- **Models:** the models take an interrupt where the DUT took it (an `I pc cause` record before the
  first handler instruction). The checker verifies that it was pending and enabled.
  - Deterministic directed tests: the testbench asserts the line at a program-order instruction index
    and requires the DUT to take it within K retirements (K: a project-set liveness bound).
- **Cores:** all three, if MC and PIPE get 2.1. Hardest in OOO (interrupt versus a ROB full of
  speculative work, and stores already on the bus).
- **Size:** PMA M, ACLINT S, interrupts M. **Depends on:** 2.1.

### 2.12 Zicbom, Zicboz, Zicbop and Zic64b

- **Spec (memory):** cbo.clean, cbo.flush and cbo.inval (MISC-MEM funct3=010, imm 1/2/0) and
  cbo.zero (imm 4) on the 64-byte block containing rs1 (Zic64b). menvcfg CBCFE, CBIE and CBZE gate
  lower modes. prefetch.i/r/w are ORI HINTs with rd=x0.
- **Project specifics (Judgement):**
  - The D-cache is write-through (Fact, architecture.md section 1), so cbo.clean only needs ordering
    and cbo.flush is an invalidate of 8 beats.
  - With write-through and no allocation on stores, memory is always current. cbo.inval can then
    behave as flush, with no stale-data hazard, but it must also cover the instruction-cache
    question (Spec: CMOs do not affect instruction fetch; FENCE.I is still required).
  - cbo.zero writes 64 bytes, that is 8 beats. OOO's `EXTRA_WRITES` carries up to 4 writes per
    request, so it takes 2 requests; PIPE needs a sequencer.
  - Zicbop: the encodings already execute as no-ops, so the extension can be declared at once. A
    real prefetch into the miss unit (`N_MISS`) is a later performance PATCH.
- **Models:** trivial for clean, flush and inval, since the models have no caches. cbo.zero emits 8
  `W` records (aligned block). Fault and permission behaviour: CBOs fault like stores (cause 7 /
  page faults later) with tval = rs1 (Spec (memory): the address is rs1, not the block base).
- **test_cpu:** cbo.zero at every in-block offset, at block and RAM edges, with faults; cached data
  after cbo.flush and cbo.inval followed by a load; prefetch encodings.
- **Cores:** OOO and PIPE. MC: only if it is kept as the firmware core.
- **Contract:** the block size (64 B, Zic64b), PMA and cache text.
- **Size:** S (Zicbop declaration), M (Zicbom+Zicboz). **Depends on:** PMA (2.11) for semantics on
  MMIO, and 2.1 for menvcfg (only if U-mode exists).

### 2.13 Zimop and the hint extensions (Zihintpause, Zihintntl)

- **Zimop (Spec (memory)):** mop.r.0-31 and mop.rr.0-7 in SYSTEM funct3=100 write **0** to rd. They
  are not no-ops; future extensions redefine them.
  - Models: S.
  - Cores: all three (decode plus a zero write).
  - Note: some existing illegal-encoding tests in test_cpu may cover SYSTEM funct3=100. With the
    option on, their expectations change; list them explicitly.
- **Zihintpause, Zihintntl:** already execute (section 1.1). The work is directed tests in all three
  cores, declaration in the ISA string, and PATCH-free RTL. Judgement: a MINOR version only because
  the ISA string (the contract) changes.
- **Size:** S each. **Depends on:** none (c.ntl and Zcmop need C).

### 2.14 Zicclsm (misaligned loads and stores) and Zama16b

- **Status:** misalignment traps (Fact, architecture.md section 1: "must change for RVA23's specified
  main-memory behavior").
- **Options (Judgement):**
  - (a) Hardware split in OOO: a misaligned access becomes two beat accesses with forwarding and
    fault rules, which is moderate in the behavioural model.
  - (b) A trap to M-mode emulation for MC and PIPE (allowed: Spec (memory), Zicclsm permits very slow
    support, including invisible traps). Needs 2.1 and handler firmware.
  - Atomicity of misaligned accesses is not required, except under optional Zama16b.
- **Models:** remove the cause 4/6 for misaligned main-memory accesses (option on).
  - A misaligned store crossing a beat emits two `W` records.
  - Fault order and partial writes: a split store whose second half faults must not have written the
    first half. That is either a contract choice or guaranteed by "check both, then write".
  - Fault tval rules.
- **Cores:** OOO (hardware), PIPE and MC (emulation) or skip.
- **Size:** M. **Depends on:** PMA (misaligned support is a PMA property), 2.1 for emulation.
- **Benchmark coupling (Fact, vendor/lzma/CpuArch.h lines 437-443):** 7-Zip defines
  `MY_CPU_LE_UNALIGN` on RISC-V only when `__riscv_misaligned_fast` is defined. That opens a
  build-flag A/B, for example clang `-mno-strict-align`, once misaligned access is fast in hardware.

### 2.15 Zfhmin, then Zvfhmin

- **Zfhmin (Spec (memory)):** flh, fsh, fmv.x.h, fmv.h.x, fcvt.s.h, fcvt.h.s, fcvt.d.h and fcvt.h.d.
  Half values are NaN-boxed in 64-bit f registers (upper 48 bits ones).
  - Models: an extension of reference_fp (exact rounding of S/D to H with flags) and of the trace
    (boxed data in the `R` record, already 64 bits).
  - OOO only. Size S-M. Depends on F/D.
- **Zvfhmin:** vfwcvt.f.f.v and vfncvt.f.f.w at SEW=16. Depends on the vector widening and narrowing
  machinery (2.3 c). Size S after that.

### 2.16 Zvbb

- **Spec (memory):** vandn, vbrev, vbrev8, vrev8, vclz, vctz, vcpop.v, vrol, vror and vwsll (Zvbb
  includes Zvkb).
- Models: vec_ref and rv_iss_fp (simple per element). vwsll needs widening group rules.
- OOO only. **Size:** M. **Depends on:** V (and widening for vwsll).

### 2.17 Supm (with Smnpm)

- **Spec (memory):** pointer masking for U-mode. The effective address ignores the top PMLEN bits,
  sign-extended for virtual or zero-extended for physical as specified. It is selected by
  menvcfg.PMM (Smnpm) when there is no S-mode. PMLEN 0 and 7 must be selectable (Fact, PDF p. 5).
- **Models:** an address transform in loads, stores, AMOs and CBOs (not fetch).
- **Cores:** OOO and PIPE (address-generation mux). **Size:** S-M. **Depends on:** U-mode (2.18) and
  menvcfg.

### 2.18 U-mode, PMP, S-mode, Sv39, Sstc and Svinval (system track)

- **U-mode:** MPP=U, ecall from U (cause 8), mcounteren, menvcfg, and illegal access to M CSRs. M.
- **PMP (Spec (memory)):** pmpcfg0-15 and pmpaddr0-63 (0-64 entries; 0 entries is legal). TOR, NA4
  and NAPOT, the L bit, fetch and LSU checks with cause 1/5/7.
  - M. Recommended: 8 or 16 entries.
  - Not required by RVA23 (section 1.4), but needed to protect M firmware from U.
- **S-mode:** sstatus, stvec, sepc, scause, stval, sscratch, satp, medeleg/mideleg, sret, sfence.vma
  and the S-level counters. L.
- **Sv39:** a page-table walker (Ssccptr: hardware PTE reads from cacheable memory), a TLB, page
  faults 12/13/15, and Svade (A/D bits by exception).
  - L; the TLB and walker in OOO interact with speculative loads and the miss unit.
- **Sstc:** stimecmp and menvcfg.STCE. S after S-mode and the timer.
- **Svinval:** sinval.vma, sfence.w.inval and sfence.inval.ir. S after Sv39; they can map to
  sfence.vma.
- **Then for RVA23S64:** Svpbmt (needs PMA memory types), Svnapot, Sscofpmf, Ssnpm, Ssu64xl, and
  Sha/H (L+).
- **Cores:** PIPE (the FPGA Linux path) and OOO. Not MC.
- **Contract:** each is a MINOR. The trace adds `P` mode records and page-fault causes.

### 2.19 Optional extensions on the user's list

- **Zacas (development option):**
  - amocas.w, .d and **.q** (on RV64, .q uses even/odd register pairs: Spec (memory)).
  - In OOO this means 2-register sources and destinations for .q, a rename change. M-L.
  - Depends on A (Zaamo). Judgement: defer until after RVA23U64 closure.
- **Zabha** (development option): S after A.
- **Zfh** (expansion option): full half arithmetic, M after Zfhmin.
- **Zfbfmin, Zvfbfmin, Zvfbfwma** (expansion options):
  - fcvt.bf16.s and fcvt.s.bf16, plus vfncvtbf16, vfwcvtbf16 and vfwmaccbf16.
  - S-M each after Zfhmin and the vector widening machinery.
  - architecture.md section 5 already flags them for the LLM workload. They cannot replace D or full
    V.

### 2.20 Summary matrix

| Extension | Models + test_cpu | MC | PIPE | OOO | Contract/trace | Size | Hard dependencies |
|---|---|---|---|---|---|---|---|
| Zicsr full + M-mode + mret | CSR file, handler, `E`/`P` records | yes | yes | yes | trap contract rework | L | none |
| F/D | in progress | no | later (C7) | yes | FP-CONTRACT; then FS | in progress | (FS: Zicsr full) |
| V (to full) | vec_ref + 6 more steps | no | no | yes | RVV-CONTRACT; VS | L | F/D; Zicsr full for VS and restart |
| Zicond | trivial | yes | yes | yes | ISA string | S | none |
| Zfa | FP models | no | no | yes | FP addendum | S-M | F/D |
| Zimop | trivial | yes | yes | yes | ISA string | S | none |
| Zihintpause, Zihintntl | tests only | yes | yes | yes | ISA string | S | none |
| Zicntr | `N` record | yes | yes | yes | CSRs, mtime | S-M | Zicsr full, mtime |
| Zihpm | events | yes | yes | yes | CSRs | S-M | Zicntr |
| PMA + ACLINT | region model | yes | yes | yes | memory map | M | none |
| Interrupts (M) | `I` record, co-sim | yes | yes | yes | trap contract | M | Zicsr full, ACLINT |
| A + Ziccrse/amoa + Za64rs | reservation | no | yes | yes | memory ordering | M+M | PMA statement |
| Zawrs | trivial | no | if A | yes | one line | S | A (interrupts) |
| Zicclsm | split or emulate | emulate | emulate | hardware | trap change | M | PMA; Zicsr for emulation |
| C (Zca+Zcd) | expander, straddling | no | yes | yes | alignment, `insn` field | L | D |
| Zcb | expander | no | yes | yes | ISA string | S | C, Zbb, Zba, M |
| Zcmop | expander | no | yes | yes | ISA string | S | C, Zimop |
| Zicbom+Zicboz+Zic64b | 8 W records | opt. | yes | yes | block size, PMA | M | PMA |
| Zicbop | none (hints) | yes | yes | yes | ISA string | S | none |
| Zfhmin | FP models | no | no | yes | FP addendum | S-M | F/D |
| Zvfhmin | vec models | no | no | yes | RVV addendum | S | V widening |
| Zvbb | vec models | no | no | yes | RVV addendum | M | V |
| Zkt | timing bench | check | check | VP change | latency list | S/M | none |
| Zvkt | timing bench | no | no | yes | latency list | S | V |
| Supm | address mask | no | yes | yes | menvcfg | S-M | U-mode |
| U-mode + PMP | CSRs | opt. | yes | yes | trap contract | M+M | Zicsr full |
| S, Sv39, Sstc, Svinval | MMU model | no | yes | yes | S64 track | L | U-mode, interrupts |

---

## 3. Testing strategy

### 3.1 Golden-model checks per extension

- **Two-model differential, as today:**
  - Every new instruction goes into reference.py and rv_iss.
  - lzma_run.py already cross-checks rv_iss against reference.py before trusting it (Fact,
    rv_iss.c header). Keep that rule per option.
  - The FP and vector models showed the pattern: three-way random match plus deliberately broken
    model copies that the tests must catch (DEVLOG 00:22). Require both for every extension.
- **An external third model** (Judgement; it closes rubric HG3, which TODO.md lists as the first open
  item):
  - **Sail RISC-V** (Fact, its README: BSD-2-Clause; supports Zicond, Zfa, Zcb, Zacas, Zawrs, Zimop,
    Zcmop, V, Zvbb, Zvfh, Zvkt, Zicbom/Zicboz/Zicbop, Sstc, Svinval, Svpbmt, Svnapot, H and
    Supm/Ssnpm).
  - **Spike** (riscv-isa-sim, BSD-3; commit log for lockstep). Note: riscv-isa-sim's licence was not
    re-fetched today.
  - Build them in the ignored `build/third-party/`, not vendored, recording the commit. Convert their
    commit logs to the project trace format.
  - This does not change the "laboratory model" status of reference.py. It is the independent check
    the ledger asks for (architecture section 8).
- **Per extension:**
  - Zicond, Zimop, Zcb and Zicntr reads: exhaustive small-operand tables plus random.
  - F/D/Zfa/Zfhmin: IEEE corner sets. Berkeley TestFloat/SoftFloat are the usual source (BSD-3,
    github.com/ucb-bar). That is outside the official-source list given for this task, so the
    coordinator must approve it. Otherwise use riscv-tests and ACT FP tests plus the existing
    exact-integer Python model.
  - A: directed reservation-state cases.
  - C: an exhaustive walk of all 65,536 16-bit encodings against an expander written independently
    from the spec table. The Sail or Spike decoder, or LLVM's disassembler, as the cross-check.
  - Privilege and interrupts: directed handler tests plus co-simulation with DUT-chosen interrupt
    points.
  - Zkt: a timing bench (section 2.9).

### 3.2 Official suites, sources, licences and vendoring

Fact (fetched 2026-11-22, URLs in section 8):

| Suite | Source | Licence | What it has that we need | Environment it expects |
|---|---|---|---|---|
| riscv-tests | github.com/riscv-software-src/riscv-tests | BSD-3-Clause, "Copyright (c) 2012-2015, The Regents of the University of California" (LICENSE). Its licence text is already in `licenses/RISCV-TESTS-BSD-3-Clause.txt` | `isa/` dirs incl. rv64ui, rv64um, rv64ua, rv64uc, rv64uf, rv64ud, rv64uzba, rv64uzbb, rv64uzbs, rv64uzicond, rv64uzfh, rv64uzacas, rv64uzabha, rv64mzicbo, rv64mi, rv64si, rv64ssvnapot, rv64uziccid | `riscv_test.h` from an env (`p`, `pm`, `pt`, `v`); the stock env is the riscv-test-env submodule and uses M-mode CSRs (mtvec etc.; Spec (memory)) |
| riscv-arch-test (ACT4) | github.com/riscv/riscv-arch-test, `act4` branch | Code BSD-3-Clause **or** Apache-2.0, docs CC-BY-4.0 (README; COPYING.APACHE, COPYING.BSD, COPYING.CC at root); licence per test file to be read from its SPDX header | `tests/rv64i/` has D, F, I, M, Zaamo, Zabha, Zacas, Zalrsc, Zba, Zbb, Zbc, Zbs, Zca, Zcb, Zcd, Zcmop, Zfa, Zfbfmin, Zfh, Zfhmin, Zicbom, Zicbop, Zicboz, Zicclsm, Zicntr, Zicond, Zicsr, Zifencei, Zihintntl, Zihintpause, Zihpm, Zimop, ...; `tests/priv/` has PMP, Sv, Svade, Svadu, Svbare, Svinval, Svnapot, Svpbmt, Svvptc (listings may be truncated) | UDB config of the DUT, `rvmodel_macros.h` (`RVMODEL_HALT_PASS/FAIL`), linker script with `rvtest_entry_point`; reference signatures from **Sail 0.16**; GCC 15 or clang 22 tested |

Plan (Judgement):

1. **riscv-tests now, without waiting for M-mode.**
   - riscv-tests isolates its environment in `riscv_test.h`. Write a project-owned (MIT) "lab" env,
     for example `sim/cpu/archtest/env/lab/riscv_test.h`, which maps `RVTEST_PASS`/`RVTEST_FAIL`
     to the mailbox convention (or ecall plus a register code) and uses no CSRs.
   - That runs rv64ui, um, uzba, uzbb and uzbs today on all three cores, rv64uf and ud with 0.17.0
     (they use only fcsr CSRs: Spec (memory), check), and uzicond, ua and uc as those land.
   - Tests that check traps (misaligned targets, `rv64mi`) need 2.1 and the stock `p` env.
   - Vendor byte-identical copies under `sim/cpu/vendor/riscv-tests/` (`isa/rv64u*/` sources and
     `isa/macros/scalar/test_macros.h`).
   - Pin the same commit as the vendored Dhrystone (`3df703cd52d5f0d8224e3c50bf03c6cb70efff98`) or a
     newer one, with the reason recorded.
   - Add a `SOURCE.txt` with per-file SHA-256 and the build refusing on a mismatch (as
     `build_bench.py` does for LZMA), and a `licenses/provenance.json` entry. The existing BSD
     licence file covers it.
   - Never edit vendored files. The lab env is a separate, MIT, clearly labelled file.
2. **ACT4 at C1+.**
   - ACT generates self-checking ELFs at build time with Sail as the reference. Treat it as a tool:
     fetch the pinned `act4` commit and Sail 0.16 into ignored `build/third-party/` with a lock file
     (commit, SHA-256 of the tree archive).
   - Vendor only the DUT-side files the project writes: the UDB config, `rvmodel_macros.h` and the
     linker script (MIT, ours). Copy the three COPYING texts into `licenses/` if any ACT file is ever
     vendored.
   - The `CERTIFICATE` and `EXTENSIONS` knobs restrict the run to the configured ISA, and that
     configuration must match the claimed ISA string exactly.
   - Judgement: ACT's trap-checking tests need an M-mode handler, so the full value of ACT comes
     after 2.1. Unprivileged-only subsets may run earlier through the DUT macros; to be confirmed
     when the framework is read.
   - Fact (research.md): ACT is "certification, not verification". It does not replace random and
     microarchitectural tests.
3. **Record** every suite run in DEVLOG (commit, suite commit, toolchain, pass/fail counts).

### 3.3 Keeping existing integer traces byte-identical

Precedent (Fact, DEVLOG 00:24 to 00:39): with the FPU off the regression gave 393 tests at both cache
sizes, LZMA 384,788 / 133,243 clocks and Dhrystone 15,706 / 10,127, "all equal to 0.16.2". The same
numbers held with the FPU *built in*. Make this the standing rule for every option (Judgement):

1. **Trace lock.** Store the SHA-256 of every integer program's trace from the last release, at both
   cache sizes and per core, in a lock file under `sim/cpu/`. Every option-off run must match it. A
   mismatch fails the run; never regenerate the lock to silence it (AGENTS.md).
2. **Option built in, unused.**
   - Run the integer suite with the option on. Traces must match the lock, except a listed set of
     programs that execute encodings the option makes legal (the illegal-encoding tests).
   - For example: Zimop's SYSTEM funct3=100, Zicond's funct7 0000111, C's 16-bit parcels (any test
     that jumps to a 2-aligned target expecting cause 0), Zicclsm's misaligned tests, and A's
     opcode 0x2f.
   - Each listed difference needs a reviewed expected trace for the option-on case.
3. **Benchmark clock identity:** Dhrystone and LZMA clocks identical with the option off and with it
   built in but unused (RTL timing must not move). A difference is a PATCH-level regression to
   explain.
4. **Trace format additions only.** New record letters (`E`, `P`, `I`, `N`), and new field ranges
   (16-bit `insn`) appear only when the option is on, following FP-CONTRACT section 7's rule.

---

## 4. Benchmark impact

### 4.1 Measured facts (quoted, not new)

- **Dhrystone:**
  - Out-of-order core, clang 23.1.5 `-O2 rv64imb`: 18.17 DMIPS/MHz (reference runtime) and 27.98
    (fast runtime) on 0.15.1 (DEVLOG run index, 2026-11-21 20:44 and 20:51).
  - 0.16.2 and the 0.17.0 candidate: 15,706 / 10,127 region clocks, the same with the FPU built in.
  - The 20 DMIPS/MHz goal is met only with the fast runtime.
- **7-Zip d22** (0.16.0, deciding configuration with `--n-miss 4`, L2 20 clocks): compress 2.187 and
  decompress 2.322 MIPS/MHz (goals 2.03 / 2.18; 95% CI ±6.8% / ±10.2%; DEVLOG 23:03 to 00:21).
- **Ray tracing, soft float** (0.16.2, 64 KiB caches): P closest-hit 0.327 rays/kclk, S closest-hit
  0.200, S any-hit 0.210, RT-P 15.36 paths/Mclk. About 70% of RT-T instructions are soft-float
  routines (Fact, `cpu/raytracing-benchmark-targets.md`).
  - Goals: scalar 6.17 / 2.24 / 2.70 and 563 paths/Mclk; SIMD P 18.2, S 9.0.
- **Ray tracing, model bounds (not RTL)** for the accepted RVV build (VLEN = DLEN = 256, 2 FMA pipes):
  - N_MISS 8: P 17.35 and S 9.70 with a 12-clock L2; P 16.3 and S 6.7 with a 20-clock L2.
  - DLEN 512 at N_MISS 8: P 23.2 (DEVLOG 00:23).
- **F/D on the ray tracer:** not yet logged as of DEVLOG 00:39.

### 4.2 Expectations per extension (Judgement unless marked)

General point:
- Dhrystone and 7-Zip are built for `rv64imb`. Changing `-march` changes the binary, so every
  extension's effect is a **-march A/B on one core version**, logged separately from RTL steps
  (AGENTS.md attribution rule).
- Dhrystone's comparability rules also argue for publishing the rv64imb number next to any new one.

| Extension | Dhrystone | 7-Zip kernel | Ray tracer | Why |
|---|---|---|---|---|
| F/D | 0 (measured: identical clocks with the FPU built in; no FP in the program) | 0 (measured identical; integer code) | **Large**: removes the soft-float calls behind about 70% of RT-T instructions. Several-fold rays/kclk expected; the scalar goals become reachable only with a fast FMA/add pipe | Fact for 0 / 0; expectation for RT |
| V (subset, then full) | about 0; build without V to keep the benchmark comparable | Small (<2% expected): LzFind and LzmaEnc are branchy, dependent scalar code; possibly memset/memcpy in the runtime | **Large** for RT-T P/S with the SIMD kernels (model bounds above). RT-P (smallpt, double) gains nothing from Zve64f and needs Zve64d plus restructuring; the laptop's smallpt is scalar too | Model bounds quoted; rest expectation |
| Zicond | ±1%: selects replace a few branches, but the TAGE predictor already predicts Dhrystone's branches well, and a select adds a data dependency | Possibly + on decompress, which is branch-prediction bound (Fact, 7zip-benchmark-targets.md); LzmaDec's range-coder bits are mostly macros with side effects on both paths, so LLVM may keep the branches. Measure | Small +: BVH child-order and hit-test selects | expectation |
| Zfa | 0 | 0 | Small (≤ a few %): `fli` removes constant-pool loads, and `fround` covers floor/ceil if used; fminm/fmaxm only if code uses fminimum/fmaximum | expectation |
| Zfhmin, Zfh, BF16 | 0 | 0 | 0 (FP32/FP64 workloads); relevant to the LLM work | expectation |
| A, Zawrs, Zacas | 0 (no atomics) | 0: built `-DZ7_ST` single-threaded (Fact, vendor/lzma/SOURCE.txt) | 0 | expectation |
| C, Zcb | Instruction count unchanged (C maps 1:1). Code size is commonly 20-30% smaller (literature value, **not measured here**; a cheap first experiment). With the regression's 4 KiB I-cache, Dhrystone's about 4 KB of code could lose its remaining I-misses; at 64-128 KiB, about 0 | About 0 at 64 KiB+ I-cache; + with small caches | About 0 | In the OOO model fetch is counted in instructions, not bytes, so C gives no fetch-bandwidth gain. Wider PC-indexed tables (bit 1) and beat-straddling instructions could cost a little. C is a physical-core (PIPE, BRAM) win |
| Zicbom, Zicboz, Zicbop | 0 | Zicbop: 0 unless the source or runtime uses `__builtin_prefetch` (LLVM then emits prefetch.r/w). Zicboz could speed large memsets (the match-finder hash-table init) if the runtime uses cbo.zero; probably outside the timed region | 0 | expectation |
| Zicntr, Zihpm | 0 (outside the timed region); replaces mailbox markers, and riscv-tests' util.h counters become usable | 0 | 0 | expectation |
| Zicclsm (fast hardware) | 0 | Small +: 7-Zip enables `MY_CPU_LE_UNALIGN` on RISC-V only with `__riscv_misaligned_fast` (Fact, CpuArch.h). It is used in a few places, for example `HASH2_CALC` (GetUi16, LzFind.c line 35), and LLVM may expand memcpy with wider unaligned accesses under `-mno-strict-align` | 0 | A build-flag A/B, not automatic |
| Zimop, hints, Supm | 0 | 0 | 0 | expectation |
| **Zkt** (if mul value prediction must be disabled) | **Possibly negative** | **Possibly negative** | small | Value prediction (0.11.1) predicts multiply results. Measure the cost of excluding `mul*` before claiming Zkt |

---

## 5. Recommended staged plan

Each line is its own version, its own commit, `cpu-vX.Y.Z` tag, history row and DEVLOG entries
(AGENTS.md "never bundle"). Every ISA or contract step is a MINOR. Version numbers are indicative and
assigned in landing order.

**Standard exit evidence for every step** (call it **E0**):
- Regression at both cache sizes for each affected core, option off **and** option on, matching the
  trace lock (section 3.3).
- Dhrystone and 7-Zip probe clocks identical with the option off.
- Logged Dhrystone (and RT once FP exists).
- `check_repo.py`.
- `rubric-evidence.json` reassessed.
- The site gallery and journal updated.
- A Codex (GPT 6.2 Astra) adversarial review for every L/M step.

| # | Version | Step | Cores | Bump | Exit test beyond E0 |
|---|---|---|---|---|---|
| 1 | 0.17.0 | F + D + fcsr (Zicsr forms on 0x001-0x003) | OOO | MINOR | (in release) `--fpu` 630 runs per cache size, Codex review closed, riscv-tests rv64uf/ud through the lab env |
| 2 | 0.18.0 | RVV Zve64f subset (RVV-CONTRACT) | OOO | MINOR | vec_cases at VLEN 128/256/512, 3-way random, element-precise traps; RT-T SIMD kernels checked against native, rays/kclk logged |
| 3 | 0.19.0 | Zicond | all three | MINOR | exhaustive small-operand table, riscv-tests rv64uzicond (lab env), -march A/B on Dhrystone, 7-Zip and RT |
| 4 | 0.20.0 | Zfa | OOO | MINOR | 32 fli entries bit-exact, fround/fcvtmod corner sets, ACT Zfa when ACT runs |
| 5 | 0.21.0 | Zimop | all three | MINOR | illegal-encoding test list updated, option-on expected traces reviewed |
| 6 | 0.22.0 | Hints declared: Zihintpause, Zihintntl (non-compressed), Zicbop (as hints) | all three | MINOR (ISA string only; RTL PATCH-free) | directed tests prove no-op behaviour in each core (FENCE pred=W/succ=0, ADD x0, ORI x0) |
| 7 | 0.23.0 | **C1a: Zicsr full + M-mode CSRs + mret + vectored traps + WFI (no-op)**, `RV64_PRIV` default off | all three | MINOR (**breaking** when the default flips) | every cause through a handler and back; exception priority; WARL fields; FS (and VS) Off traps; riscv-tests rv64mi with the stock `p` env |
| 8 | 0.24.0 | mstatus.FS/VS live (FP-CONTRACT section 2 promise) | OOO | MINOR | FS Off traps for every FP op, Dirty set at retirement, context-switch test |
| 9 | 0.25.0 | Zicntr (cycle, instret; time through an mtime port) + mcycle/minstret/mcountinhibit | all three | MINOR | `N`-record co-simulation, instret exact, benchmarks self-timed and equal to the mailbox counts within the documented offset |
| 10 | 0.26.0 | PMA regions + ACLINT (mtime, mtimecmp, msip) in the SoC, uncacheable MMIO | SoC + all | MINOR | MMIO never cached or over-read; fetch from MMIO faults; check_soc_memory extended |
| 11 | 0.27.0 | M-mode interrupts (MTI, MSI, MEI), real WFI | all three | MINOR | pending IRQ during memory stalls and split reads (C1 evidence), take-within-K bound, nested trap/IRQ |
| 12 | 0.28.0 | Zihpm (real events) | all three | MINOR | event counts against model counts where deterministic (mispredicts by reference replay) |
| 13 | 0.29.0 | A + Ziccrse/Ziccamoa/Za64rs, memory-ordering section | OOO, PIPE | MINOR | riscv-tests rv64ua, LR/SC invalidation cases, AMO versus younger-load ordering in OOO, Codex review |
| 14 | 0.30.0 | Zawrs | OOO, PIPE | MINOR | encoding and timeout tests; wake on interrupt |
| 15 | 0.31.0 | Zicclsm (OOO hardware split; M-mode emulation firmware for MC/PIPE) | all | MINOR (trap behaviour changes when on) | split-beat loads and stores, faults on the second half, no partial store; -march/`-mno-strict-align` A/B on 7-Zip |
| 16 | 0.32.0 | Zicbom + Zicboz + Zic64b | OOO, PIPE | MINOR | cbo.zero 8-W trace at every offset, flush/inval then load, ACT Zicbom/Zicboz |
| 17 | 0.33.0 | Zkt qualification (exclude `mul*` from value prediction if needed) | all | MINOR (latency statement) / PATCH (VP change) | timing bench constant across random operands; Dhrystone and 7-Zip cost logged |
| 18 | 0.34.0 | Zfhmin | OOO | MINOR | conversion corner sets, NaN-boxing of H |
| 19 | 0.35.0 | C (Zca + Zcd) | PIPE, OOO | MINOR (alignment contract) | exhaustive 16-bit decode walk, straddling at beats/lines/RAM edge, SMC over compressed code, riscv-tests rv64uc, code-size and clock A/B |
| 20 | 0.36.0 | Zcb | PIPE, OOO | MINOR | ACT Zcb |
| 21 | 0.37.0 | Zcmop (+ c.ntl) | PIPE, OOO | MINOR | ACT Zcmop, Zihintntl |
| 22 | 0.38.0 to 0.4x | Full V in steps: Zve64d, widening/narrowing + vfwcvt/vfncvt, fixed point, segments, vfrec7/vfrsqrt7 and the remaining permutes; then Zvfhmin, Zvbb, Zvkt | OOO | MINOR each | per-step 3-way random plus broken-model checks; vstart restart through a handler (needs step 7); ACT vector when available |
| 23 | 0.4x | U-mode + mcounteren/menvcfg, then PMP (8-16 entries) | PIPE, OOO (MC optional) | MINOR each | privilege rejection, ecall from U, PMP TOR/NAPOT/NA4/L, ACT PMP |
| 24 | 0.4x | Supm (Smnpm, PMLEN 0/7) | PIPE, OOO | MINOR | masked addresses in loads, stores, AMOs and CBOs, not fetch |
| 25 | gate | **RVA23U64 closure audit (C6)** | | none (evidence) | ACT for the full configured ISA string, Sail lockstep in the regression, versioned ISA/PMA manifest, no mandatory item hidden as software |
| 26+ | S64 track | S-mode, Sv39 + Svade/Svbare, Sstc, Svinval, Svpbmt, Svnapot, Sscofpmf, Ssnpm, Ssu64xl; Sha/H last | PIPE, OOO | MINOR each | Linux boot as an experiment, not labelled RVA23S64 until Sha is done |
| opt. | any time after deps | Zabha, Zacas, Zfh, Zfbfmin/Zvfbfmin/Zvfbfwma, Zvbc, Zbc | OOO | MINOR each | as above |

### 5.1 Departures from the user's order, and why

The user's order: F+D+Zicsr; V; Zfa+Zicond; A+Zawrs; C+Zcb; Zicbom/Zicboz/Zicbop; Zicntr/Zihpm.

1. **Steps 1-2 are kept.** F/D is in release, and the V subset's golden model is done. The ray-tracing
   goal is the active benchmark.
2. **Zfa and Zicond are split** into two versions (steps 3-4), following AGENTS.md "never bundle".
   Zicond goes first because it is S-sized, applies to all three cores and needs nothing.
3. **Added mandatory items the list omits** (Zimop, hints, Zicbop-as-hints, Zic64b, Zicclsm, Ziccif,
   Ziccrse, Ziccamoa, Za64rs, Zcmop, Zkt qualification, Supm). Several are nearly free (steps 5-6),
   and the rest join their natural parents.
4. **The privilege and CSR foundation (step 7) is inserted before A, Zicntr, CBO, C and full V.** It
   is not on the list as a step, but:
   - (a) Zicntr's `time` needs a timer, and an MMIO timer needs the PMA step. Fact, architecture
     section 3: every address is cacheable until a PMA exists.
   - (b) FS and VS are promised contract changes (FP-CONTRACT section 2, RVV-CONTRACT section 1).
     Doing them before more FP and vector work avoids re-specifying both.
   - (c) Vector element-precise traps are only restartable with a handler (C5 evidence).
   - (d) The official suites' trap tests and riscv-tests' stock env use M-mode.
   - (e) Zicclsm on the synthesizable cores is cheapest as M-mode emulation.
   - (f) The 1.0.0 criteria in architecture section 9 start with "C1 complete".
   - A itself does not need privilege. It could move ahead of step 7 if the council wants atomics
     sooner. It is placed after because Zawrs is only meaningful with interrupts, and because the
     memory-ordering text belongs with the PMA step.
5. **Zicntr/Zihpm move from last to right after the foundation** (steps 9, 12). They are cheap with a
   CSR file, unblock self-timed benchmarks and give performance-counter evidence for the optimization
   loop. The real work is the trace's non-determinism, which is better solved once, early.
6. **C moves after A and the CBOs.** It has no hard ordering need, but it is the riskiest front-end
   change in the OOO core (32-wide length decode, 2-byte PC granularity in every predictor table,
   straddling fetch) and gives about 0 benchmark gain in the behavioural model. It needs D first
   (Zcd) to claim "C" on RV64D.
7. **Zacas, Zfh and the BF16 extensions go to the optional tail.** They are not mandatory in
   RVA23U64 (PDF pp. 5-6).

---

## 6. Key risks and open questions for the coordinator

- **Zkt versus value prediction** (section 2.9) is the one place where an existing performance
  feature may conflict with a mandatory extension. It needs a decision and a measurement.
- **The trace format needs non-deterministic records** (`N` for counters, `I` for interrupts) and
  co-simulation, where the models adopt DUT choices. This changes test_cpu's model from "compare two
  independent runs" to "lockstep with injection". Design it once, at step 7 or 9.
- **Zic64b's 64-byte blocks** versus 8-byte L1 lines are legal (the block size is architectural for
  CMOs), but they make cbo.zero a multi-request operation. The DEVLOG 00:23 SIMD study also wants 64 B
  lines for the ray tracer, so the two may align.
- **The PIPE core as the "proper" synthesizable core.** RVA23U64 on an FPGA needs F/D and V in a
  synthesizable core, which today exist only in the behavioural OOO model. Recommend the council
  state, per release, which core carries which ISA string, so no bitstream is labelled with OOO's
  string.
- **Spec facts marked "Spec (memory)"** must be checked against the ISA manual chapters before each
  contract is written. I did not fetch those chapters, to stay within the source and size limits.

## 7. Repository facts used

- `references/rva23-profile-v1.0.pdf` (pp. 4-9; extracted with pdftotext into the session scratchpad,
  not the repo).
- `cpu/architecture.md` sections 1-9.
- `build/cpu/fp/FP-CONTRACT.md` and `RVV-CONTRACT.md`.
- DEVLOG.md rows 00:12 to 00:39 (2026-11-22) and the run index.
- `cpu/raytracing-benchmark-targets.md` and `cpu/7zip-benchmark-targets.md`.
- `sim/cpu/reference.py` (FENCE handling, line 220), `sim/cpu/bench/rv_iss.c` (header),
  `rtl/cpu/rv64_ooo.sv` (`FW = 32`, `btb_fits`).
- `sim/cpu/bench/vendor/*/SOURCE.txt`, `sim/cpu/bench/vendor/lzma/CpuArch.h` (lines 437-443),
  `LzFind.c` (line 35).
- `research.md` (ACT notes), `TODO.md` (HG3 items) and `licenses/`.

## 8. Web sources consulted (official only, 2026-11-22)

- https://github.com/riscv/riscv-arch-test: the `act4` branch README (ACT4 tool, licences, UDB config,
  Sail 0.16, toolchains); root listing with COPYING.APACHE, COPYING.BSD and COPYING.CC.
- https://github.com/riscv/riscv-arch-test/tree/act4/tests and `/tests/rv64i` and `/tests/priv`
  (directory listings, which may be truncated).
- https://raw.githubusercontent.com/riscv/riscv-arch-test/act4/LICENSE (404; there is no single
  LICENSE file).
- https://github.com/riscv-software-src/riscv-tests and `/tree/master/isa` (directory list, envs).
- https://raw.githubusercontent.com/riscv-software-src/riscv-tests/master/LICENSE (BSD-3, Regents of
  the University of California).
- https://github.com/riscv/sail-riscv (README: BSD-2-Clause, supported extensions).

Nothing was downloaded into the repository. No large repository was cloned.
