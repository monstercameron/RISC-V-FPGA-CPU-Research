> Superseded draft. This text was folded into [cpu/architecture.md](../architecture.md) section 1 at 0.17.0; the architecture document governs. Kept as history (copied unchanged from the ignored build/cpu/fp/FP-CONTRACT.md on 2026-11-22, apart from this note).

# F and D contract proposal (laboratory EEI)

Status: proposal by the FP ISA engineer, 2026-11-21. Not yet part of `cpu/architecture.md`; integrating it
there is a contract change (MINOR bump). Golden models: `build/cpu/fp/reference_fp.py` (Python, exact
integer significand arithmetic) and `build/cpu/fp/rv_iss_fp.c` (C, hardware FPU with RISC-V fix-ups plus an
exact software path). Semantics follow the RISC-V unprivileged specification, chapters "F" and "D"
(IEEE 754-2008 binary32/binary64), and the Zicsr chapter for the three FP CSRs. This text is a summary for
implementers; where it is silent, the specification governs.

## 1. Enablement and the integer-only cores

* FP is an option: `reference_fp.execute(..., fp=True)`, `rv_iss_fp --fp 1`; RTL: a parameter/define
  `RV64_FP` is the ISA option name in this contract, the models and the tests; in the out-of-order core the build define `RV64_OOO_FPU` (`rtl/cpu/rv64_ooo.sv`, matching its other `RV64_OOO_*` knobs) enables it. The only supported configuration is RV64FD with FLEN=64. F without D is not offered.
* **Disabled (the default):** behaviour is exactly today's. Every instruction with major opcode LOAD-FP
  (0x07), STORE-FP (0x27), MADD/MSUB/NMSUB/NMADD (0x43/0x47/0x4b/0x4f) or OP-FP (0x53), and every
  SYSTEM instruction other than ECALL/EBREAK (all CSR instructions), raises cause 2 (illegal instruction),
  tval = the 32-bit instruction zero-extended. Traces of every existing program are byte-identical to
  `sim/cpu/reference.py`. The existing cores stay valid unchanged.
* **Enabled:** the encodings in section 4 execute. Every other encoding in those opcodes is still cause 2:
  fmt 10 (H) and 11 (Q), unused funct5/funct3/rs2 combinations, LOAD-FP/STORE-FP widths other than W/D
  (the V vector memory forms), and CSR instructions on any CSR other than 0x001-0x003.

## 2. Architectural state

| State | Width | Reset | Notes |
|---|---|---|---|
| f0-f31 | 64 bits each | 0 | f0 is an ordinary register (not hard-wired) |
| fcsr (0x003) | 8 bits: frm[7:5], fflags[4:0] | 0 | bits 31:8 read 0, writes ignored |
| fflags (0x001) | alias of fcsr[4:0] | | NV=0x10, DZ=0x08, OF=0x04, UF=0x02, NX=0x01 |
| frm (0x002) | alias of fcsr[7:5] | | may hold 5-7; only dynamic-rounding instructions then trap |

mstatus.FS: the project has no mstatus or any other CSR. With FP enabled the laboratory EEI behaves as if
FS were permanently Dirty; with FP disabled, as if FS were Off (every FP instruction is illegal). No `misa`
is fabricated. When the privilege stage (C1) adds mstatus, FS (with Off trapping and Dirty tracking) must be
added then; that will be a further contract change. A register value 0 is not a NaN-boxed single, so a reset
register read as single precision is the canonical NaN.

## 3. Values, NaN-boxing, NaNs

* **NaN-boxing.** A single-precision result is written as `0xffffffff_xxxxxxxx`. A single-precision operand
  whose upper 32 bits are not all ones reads as the canonical single NaN 0x7fc00000 (a quiet NaN, so no NV
  for it). Exempt *transfer* operations: FLW boxes the loaded word; FSW stores bits 31:0 unchecked;
  FMV.X.W moves bits 31:0 sign-extended, unchecked; FMV.W.X boxes. FSGNJ*.S, FCLASS.S, FMIN/FMAX.S,
  compares and FCVT.D.S **do** check the boxing.
* **Canonical NaN.** Every arithmetic NaN result (add, sub, mul, div, sqrt, FMA, FMIN/FMAX of two NaNs,
  FCVT.S.D, FCVT.D.S) is the canonical NaN: 0x7fc00000 (boxed) or 0x7ff8000000000000. Payloads never
  propagate. FSGNJ*, FMV*, loads and stores copy bits, NaN or not, and never signal.
* **sNaN** = exponent all ones, quiet bit (MSB of the fraction) 0, fraction non-zero.

## 4. Instructions (RV64F and RV64D, 2 x 30 = 60 plus FCVT.S.D/FCVT.D.S)

R4 (FMA): `rs3[31:27] fmt[26:25] rs2 rs1 rm rd opcode`. OP-FP: `funct5[31:27] fmt[26:25] rs2 rs1 rm/funct3 rd 0x53`. fmt 00 = S, 01 = D.

| Group | Instructions (`.S` and `.D` forms) | Encoding (funct5, rs2, funct3) | Result / notes |
|---|---|---|---|
| Load/store | FLW, FLD, FSW, FSD | 0x07/0x27, funct3 2 (W) / 3 (D), I/S immediate | Alignment and access faults exactly as LW/LD/SW/SD (causes 4/5, 6/7) |
| FMA | FMADD, FMSUB, FNMSUB, FNMADD | opcodes 0x43, 0x47, 0x4b, 0x4f; rm | a*b+c, a*b-c, -(a*b)+c, -(a*b)-c, one rounding |
| Arithmetic | FADD, FSUB, FMUL, FDIV | 00000-00011, rm | |
| | FSQRT | 01011, rs2=0, rm | |
| Sign injection | FSGNJ, FSGNJN, FSGNJX | 00100, funct3 0/1/2 | bit copy; FMV/FNEG/FABS are aliases |
| Min/max | FMIN, FMAX | 00101, funct3 0/1 | IEEE 754-2019 minimumNumber/maximumNumber: -0 < +0; one NaN -> the other operand; two NaNs -> canonical NaN; NV if any operand is sNaN |
| Compare | FLE, FLT, FEQ -> x rd | 10100, funct3 0/1/2 | 1/0; any NaN -> 0. FEQ: NV only for sNaN. FLT/FLE: NV for any NaN |
| Classify | FCLASS -> x rd | 11100, rs2=0, funct3 1 | one-hot bits 0-9: -inf, -normal, -subnormal, -0, +0, +subnormal, +normal, +inf, sNaN, qNaN |
| FP to int | FCVT.W, .WU, .L, .LU (from S or D) | 11000, rs2 0/1/2/3, rm | see conversions |
| Int to FP | FCVT.S/D.W, .WU, .L, .LU | 11010, rs2 0/1/2/3, rm | rounds (NX); .D from 32-bit ints is exact |
| FP to FP | FCVT.S.D / FCVT.D.S | 01000 fmt S rs2 1 / fmt D rs2 0, rm | S.D rounds (OF, UF, NX); D.S exact. sNaN -> NV; NaN -> canonical |
| Moves | FMV.X.W, FMV.X.D -> x rd | 11100, rs2=0, funct3 0 | raw bits (W: sign-extended from bit 31) |
| | FMV.W.X, FMV.D.X | 11110, rs2=0, funct3 0 | raw bits (W: boxed) |
| CSR (Zicsr, FP CSRs only) | CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI, CSRRCI | SYSTEM 0x73, funct3 1/2/3/5/6/7, csr 0x001-0x003 | rd = old value zero-extended; CSRRS/C with rs1=x0 / uimm=0 do not write. Pseudos: frcsr, fscsr, frrm, fsrm, frflags, fsflags |

## 5. Rounding

* rm field: 000 RNE, 001 RTZ, 010 RDN, 011 RUP, 100 RMM (nearest, ties away from zero), 111 DYN (use frm).
  rm 101 or 110, or DYN with frm >= 5, is **illegal (cause 2)** for every instruction that has an rm field,
  including the exact FCVT.D.S, FCVT.D.W and FCVT.D.WU (as the Sail model and Spike do). The instruction
  then has no effect: no register write, no flags.
* Results are the infinitely precise result rounded once to the destination format. Subnormals are fully
  supported (no flush to zero).
* **Overflow:** RNE and RMM give ±inf; RTZ gives ±max finite; RDN gives +max / -inf; RUP gives +inf / -max.
  OF and NX are both set.
* **Underflow** (UF): the result is tiny **and** inexact. Tininess is detected **after rounding** (the
  result, rounded to the destination precision with unbounded exponent, has magnitude < 2^emin). UF always
  comes with NX. (AArch64 hardware detects tininess before rounding; rv_iss_fp corrects for it.)
* **Exact zero results:** x + (-x) and other exact zero sums give +0, except -0 in RDN; sums of zeros with
  equal signs keep that sign. FMA forms apply this to the operands (-(a*b)) and (-c) as negated before the
  single addition, as softfloat does: FNMADD(+0, +0, +0) = -0.
* **FMA invalid:** inf*0 (either order) raises NV and returns the canonical NaN even when c is a quiet NaN.
* **Other flags:** NV for sNaN inputs to arithmetic, inf-inf, 0*inf, 0/0, inf/inf, sqrt(negative, not -0);
  DZ for finite non-zero / ±0 (result ±inf). sqrt(-0) = -0.

## 6. Conversions to integers (FCVT.W/WU/L/LU)

The value is rounded to an integer with the rounding mode; NX if that changes it. If the rounded value is out
of range, or the input is NaN or ±inf, the result is the table entry and only NV is set (no NX):

| Input | W | WU | L | LU |
|---|---|---|---|---|
| NaN, +inf, > max | 2^31-1 | 2^32-1 | 2^63-1 | 2^64-1 |
| -inf, < min | -2^31 | 0 | -2^63 | 0 |

The range check is on the rounded value (FCVT.WU.S of -0.4 in RNE is 0 with NX; of -0.6 is 0 with NV).
32-bit results (W **and** WU) are sign-extended to 64 bits in x rd.

## 7. Trace format extension (reference.py / tb_core.sv)

Unchanged records: `R pc ins rd data next`, `W addr data mask`, `T pc cause tval`. Additions, all used only by
FP instructions, so integer-only programs produce byte-identical traces:

1. **FP register destination.** In an R record the 2-hex-digit destination field is `20`-`3f` for f0-f31
   (0x20 + n); data is the full 64-bit register value after the write (boxed for single). `00` still means no
   architectural write with data 0 (an integer-destination FP instruction with rd = x0). Integer
   destinations remain `01`-`1f`.
2. **`F ff`** — exception flags raised by this instruction (2 hex digits, NV=10 DZ=08 OF=04 UF=02 NX=01),
   emitted only when non-zero, whether or not they were already set in fflags. fflags |= ff at retirement.
3. **`C 003 vvvvvvvvvvvvvvvv`** — a CSR instruction that writes (CSRRW/CSRRWI always; CSRRS/CSRRC only with
   a non-zero rs1 field or uimm) reports the full new fcsr value (frm << 5 | fflags), whichever alias it named.
4. **FP store data (W):** FSW and FSD use the W format of SW and SD, but the data field holds only the bytes
   written: FSW logs bits 31:0 of the f register shifted into its lane, with zeros elsewhere (it does not log
   the NaN-box bits 63:32 the way SW logs the whole shifted x register). FSD logs all 64 bits.
5. **Order:** like W, the F and C records of an instruction come immediately before its own R record.
   A trapping instruction emits nothing but its T record.

Examples: `F 01` then `R 0000000000000040 18b57553 2a ffffffff3eaaaaab 0000000000000044` (fdiv.s fa0, fa0,
fa1 inexact); `C 003 0000000000000040` then `R ... 00215073 00 0000000000000000 ...` (fsrmi 2, that is csrrwi x0, frm, 2 →
frm = RDN).

## 8. Implementation notes for the RTL engineers

* A ROB entry needs a 5-bit flags field and a destination-class bit (x or f); rename an architectural space
  of 64 registers (x1-x31, f0-f31). fcsr is updated at retirement only; any instruction that reads frm
  (DYN) or fcsr must see all older retired accruals (simplest: serialize CSR accesses to fcsr, and treat
  a DYN-rounded instruction as reading frm, which only a CSR write changes).
* Single-precision results must be boxed in the register file; inputs are box-checked at the operand mux.
* A mode-5/6/7 trap must be raised at decode/rename for static rm, and once frm is known for DYN.

## 9. Out of scope (future gates)

Zfa (FLI, FMINM/FMAXM, FROUND, FCVTMOD.W.D, FLEQ/FLTQ — mandatory in RVA23, later step), Zfhmin/Zfh,
Zfinx, misaligned FP loads/stores, mstatus.FS state tracking, FP traps (RISC-V has none).
