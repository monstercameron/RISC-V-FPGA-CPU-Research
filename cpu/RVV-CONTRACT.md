# RVV contract proposal: the ray-tracer subset (laboratory EEI)

Status: contract of the vector option, step 1, since architecture 0.18.0 (cpu/architecture.md section 1); written by the FP ISA engineer, 2026-11-22, and copied here from build/cpu/fp/ at the 0.18.0 release. In this repository the golden model is `sim/cpu/reference.py` (`vector=True`, `vlen=`) with `sim/cpu/vec_ref.py`; `rv_iss_fp.c --vector` and the two-model differential `vtest.py` are not in the repository yet (a later test-only step). Builds on FP-CONTRACT.md (F/D) and follows the RISC-V "V"
extension 1.0 specification; where this text is silent, the specification governs, and every choice the
specification leaves open is fixed here so that models and RTL produce identical traces. Golden models:
`reference_fp.py` (`vector=True`, `vlen=`) and `rv_iss_fp.c` (`--vector 1 --vlen N`). ISA option name: `RV64_V`
(the out-of-order core's define is `RV64_OOO_V`). Integrating this is a contract change (MINOR).

## 1. Profile, sizes and enablement

* Scope: **a subset of RVV 1.0**, exactly the instructions listed in sections 5 and 6 (integer SEW 8/16/32/64,
  FP32 vector arithmetic), ELEN = 64. It is not a complete Zve* extension and not V (missing, among others:
  widening and narrowing, vadc/vmadc, fixed point, segment loads and stores, FP64 vector arithmetic,
  vfrec7/vfrsqrt7, vrgatherei16), and must not be advertised as either. Section 9 lists what the out-of-order
  core implements so far.
* VLEN is a build parameter: 128, 256 (default) or 512. Traces depend on VLEN. VLENB = VLEN / 8.
* Vector instructions require the option; vector FP instructions also require F/D (`fp=True`). Disabled = every
  OP-V (0x57) instruction, every vector load/store encoding in LOAD-FP/STORE-FP (width 0, 5, 6, 7) and the vector
  CSRs are illegal (cause 2), so existing traces are unchanged.
* mstatus.VS is not modelled (no mstatus exists); enabled behaves as VS = Dirty, as FS does for F/D.

## 2. State

| State | CSR | Reset | Notes |
|---|---|---|---|
| v0-v31 | | 0 | VLEN bits each; element i of a group at bits [i*SEW, (i+1)*SEW) of the group, little-endian, register vd+k holding elements k*VLEN/SEW.. |
| vstart | 0x008 | 0 | read/write; writable bits: log2(VLEN) (values are masked to VLEN-1) |
| vxsat | 0x009 | 0 | read/write, 1 bit (no fixed-point instructions yet, storage only) |
| vxrm | 0x00a | 0 | read/write, 2 bits (storage only) |
| vcsr | 0x00f | 0 | vxrm << 1 \| vxsat |
| vl | 0xc20 | 0 | read-only; written by vsetvl* and fault-only-first |
| vtype | 0xc21 | vill = 1 (bit 63), rest 0 | read-only; written by vsetvl* |
| vlenb | 0xc22 | VLEN/8 | read-only |

Reset vtype has vill set, so a vector instruction before the first vsetvl* is illegal. Writes (any CSR instruction
that writes) to vl, vtype or vlenb are illegal. Other CSR numbers stay illegal (FP-CONTRACT.md section 1).

## 3. vsetvli / vsetivli / vsetvl

* vtype: vlmul[2:0], vsew[5:3], vta[6], vma[7], bits 62:8 reserved (must be 0), vill[63].
* vtype is **illegal** (vill = 1, vl = 0, other vtype bits 0) if: any reserved bit is set; vsew > 3; vlmul = 4;
  or a fractional LMUL with SEW > LMUL * ELEN (LMUL 1/8 allows SEW 8, 1/4 allows 8-16, 1/2 allows 8-32).
* VLMAX = LMUL * VLEN / SEW. AVL: x[rs1] if rs1 != x0; if rs1 = x0 and rd != x0, AVL = ~0 (VLMAX);
  vsetivli: AVL = uimm[4:0]. **vl = min(AVL, VLMAX)** (no other permitted value is used).
* rs1 = x0 and rd = x0 keeps vl; if the new VLMAX differs from the current one (or vtype was vill), the result
  is vill (vl = 0).
* rd receives the new vl. Like every vector instruction, vsetvl* ends with vstart = 0 (RVV 1.0 section 3.7).
* Trace: `C c20 <vl>` then `C c21 <vtype>` (both always), then `C 008 0000000000000000` if vstart was non-zero,
  then the R record (rd = new vl).

## 4. Common execution rules

* **vill or vstart.** Any vector instruction other than vsetvl*, the CSR instructions, whole-register loads and
  stores (vl<n>re, vs<n>r) and whole-register moves (vmv<n>r.v) is illegal while vtype.vill = 1. A vector arithmetic instruction (anything other than loads and stores) with vstart != 0 is
  illegal (the specification permits this). Loads and stores honour vstart (elements below it are not accessed
  and stay undisturbed) and every vector instruction that completes leaves vstart = 0.
* **Body, prestart, tail, inactive.** For vl and vstart: elements below vstart are prestart (undisturbed);
  elements in [vstart, vl) are the body; a body element is active unless the instruction is masked (vm = 0) and
  mask bit i of v0 is 0; elements from vl to the end of the destination register group (or of the register,
  for fractional LMUL) are tail.
* **Agnostic policy (backend's proposal, adopted).** A tail element with vta = 1, an inactive element with
  vma = 1, and every tail bit of a mask destination (always agnostic) is written **all ones**. With vta/vma = 0
  they are undisturbed. If vstart >= vl, nothing is written at all, tail included (no V record).
* **Mask layout.** Mask element i is bit i of the register, for every SEW and LMUL.
* **Illegal operand groups** (the specification's reserved cases, trapping here, cause 2):
  - every vector operand register number is a multiple of its group size (EMUL >= 1); EMUL > 8 or < 1/8 is
    illegal;
  - a masked instruction (vm = 0) whose destination is not a mask value and not a reduction scalar must not
    have v0 inside its destination group;
  - a destination group may overlap a source group only when the EEWs are equal; when the destination EEW is
    smaller (mask results, and indexed loads with a wider index), only in the lowest-numbered register of the
    source group; when the destination EEW is larger (vsext/vzext, indexed loads with a narrower index), only
    in the highest-numbered part of the destination group, with source EMUL >= 1;
  - vslideup, vslide1up, vfslide1up, vrgather, vcompress, viota.m, vmsbf/vmsif/vmsof: vd must not overlap any
    source vector group (vs2, vs1 where it is a vector, and v0 when masked).
* **Scalar operands.** `.vx`: x[rs1] truncated to SEW. `.vi`: simm5 sign-extended to SEW, except the shift,
  slide and vrgather forms, which use uimm5. `.vf`: f[rs1] NaN-box checked for SEW 32 (a non-boxed value is the
  canonical NaN), as scalar F.
* **Shifts** use the low log2(SEW) bits of the shift amount.
* **FP elements** (SEW = 32 only; other SEW are illegal for vector FP): exactly the scalar F semantics of
  FP-CONTRACT.md per element, rounding mode = frm (frm >= 5 is illegal), canonical NaN results; the flags of all
  active elements (and of every addition a reduction performs) are ORed into one `F` record and into fflags.

## 5. Instructions

OP-V = 0x57, funct3: OPIVV 0, OPFVV 1, OPMVV 2, OPIVI 3, OPIVX 4, OPFVF 5, OPMVX 6, OPCFG 7. Fields: funct6[31:26]
vm[25] vs2[24:20] vs1/rs1/imm[19:15] funct3 vd/rd[11:7]. Anything not listed is illegal.

| funct6 | OPIVV/IVX/IVI | OPMVV/MVX | OPFVV/FVF |
|---|---|---|---|
| 000000 | vadd (V X I) | vredsum.vs | vfadd (V F) |
| 000001 | | vredand.vs | vfredusum.vs |
| 000010 | vsub (V X) | vredor.vs | vfsub (V F) |
| 000011 | vrsub (X I) | vredxor.vs | vfredosum.vs |
| 000100 | vminu (V X) | vredminu.vs | vfmin (V F) |
| 000101 | vmin (V X) | vredmin.vs | vfredmin.vs |
| 000110 | vmaxu (V X) | vredmaxu.vs | vfmax (V F) |
| 000111 | vmax (V X) | vredmax.vs | vfredmax.vs |
| 001000 | | | vfsgnj (V F) |
| 001001 | vand (V X I) | | vfsgnjn (V F) |
| 001010 | vor (V X I) | | vfsgnjx (V F) |
| 001011 | vxor (V X I) | | |
| 001100 | vrgather (V X I) | | |
| 001110 | vslideup (X I) | vslide1up (X) | vfslide1up (F) |
| 001111 | vslidedown (X I) | vslide1down (X) | vfslide1down (F) |
| 010000 | | VWXUNARY0 (V): vmv.x.s vs1=0, vcpop.m 16, vfirst.m 17; RXUNARY0 (X): vmv.s.x vs2=0 | VWFUNARY0 (V): vfmv.f.s vs1=0; RFUNARY0 (F): vfmv.s.f vs2=0 |
| 010010 | | VXUNARY0 (V): vzext.vf8 2, vsext.vf8 3, vzext.vf4 4, vsext.vf4 5, vzext.vf2 6, vsext.vf2 7 | VFUNARY0 (V): vfcvt.xu.f.v 0, vfcvt.x.f.v 1, vfcvt.f.xu.v 2, vfcvt.f.x.v 3, vfcvt.rtz.xu.f.v 6, vfcvt.rtz.x.f.v 7 |
| 010011 | | | VFUNARY1 (V): vfsqrt.v 0, vfclass.v 16 |
| 010100 | | VMUNARY0 (V): vmsbf.m 1, vmsof.m 2, vmsif.m 3, viota.m 16, vid.v 17 | |
| 010111 | vmerge (vm=0) / vmv.v (vm=1, vs2=0) (V X I) | vcompress.vm (V, vm=1) | vfmerge.vfm (vm=0) / vfmv.v.f (vm=1, vs2=0) (F) |
| 011000 | vmseq (V X I) | vmandn.mm | vmfeq (V F) |
| 011001 | vmsne (V X I) | vmand.mm | vmfle (V F) |
| 011010 | vmsltu (V X) | vmor.mm | |
| 011011 | vmslt (V X) | vmxor.mm | vmflt (V F) |
| 011100 | vmsleu (V X I) | vmorn.mm | vmfne (V F) |
| 011101 | vmsle (V X I) | vmnand.mm | vmfgt (F) |
| 011110 | vmsgtu (X I) | vmnor.mm | |
| 011111 | vmsgt (X I) | vmxnor.mm | vmfge (F) |
| 100000 | | vdivu (V X) | vfdiv (V F) |
| 100001 | | vdiv (V X) | vfrdiv (F) |
| 100010 | | vremu (V X) | |
| 100011 | | vrem (V X) | |
| 100100 | | vmulhu (V X) | vfmul (V F) |
| 100101 | vsll (V X I) | vmul (V X) | |
| 100110 | | vmulhsu (V X) | |
| 100111 | vmv<n>r.v (I, vm=1, simm = n-1, n = 1/2/4/8) | vmulh (V X) | vfrsub (F) |
| 101000 | vsrl (V X I) | | vfmadd (V F) |
| 101001 | vsra (V X I) | vmadd (V X) | vfnmadd (V F) |
| 101010 | | | vfmsub (V F) |
| 101011 | | vnmsub (V X) | vfnmsub (V F) |
| 101100 | | | vfmacc (V F) |
| 101101 | | vmacc (V X) | vfnmacc (V F) |
| 101110 | | | vfmsac (V F) |
| 101111 | | vnmsac (V X) | vfnmsac (V F) |

Notes on semantics (all as the specification; the points that models must get right):
* Integer multiply-add: vmacc vd = vs1*vs2 + vd; vnmsac vd = -(vs1*vs2) + vd; vmadd vd = vs1*vd + vs2;
  vnmsub vd = -(vs1*vd) + vs2. FP: vfmacc +(vs1*vs2)+vd, vfnmacc -(vs1*vs2)-vd, vfmsac +(vs1*vs2)-vd,
  vfnmsac -(vs1*vs2)+vd, vfmadd +(vs1*vd)+vs2, vfnmadd -(vs1*vd)-vs2, vfmsub +(vs1*vd)-vs2, vfnmsub -(vs1*vd)+vs2,
  each one rounding with the operand negations of the scalar FMA forms (FP-CONTRACT.md section 5).
  For `.vx`/`.vf`, the scalar replaces vs1.
* Division by zero and overflow as the scalar M instructions, per SEW.
* vmerge / vfmerge write every body element (v0 selects the source), so the mask policy does not apply.
* vmv.x.s and vfmv.f.s read element 0 even if vl = 0 (vmv.x.s sign-extends SEW to 64 bits; vfmv.f.s needs SEW 32
  and NaN-boxes); they write no vector register. vmv.s.x / vfmv.s.f write element 0 when vl > 0; the remaining
  elements of vd (one register) are tail.
* vcpop.m, vfirst.m (-1 if none) count active bits below vl; they write x[rd] only.
* Slides: OFFSET = x[rs1] (unsigned, 64-bit) or uimm. vslideup: vd[i] = vs2[i - OFFSET] for OFFSET <= i < vl;
  vd[i] for i < max(vstart, OFFSET) is undisturbed (not agnostic). vslidedown: vd[i] = vs2[i + OFFSET] if
  i + OFFSET < VLMAX else 0. vslide1up: vd[0] = scalar, vd[i] = vs2[i-1]; vslide1down: vd[vl-1] = scalar.
* vrgather: vd[i] = index >= VLMAX ? 0 : vs2[index]; index = vs1[i] (vv), x[rs1] (vx, 64-bit), uimm (vi).
* vcompress.vm: active elements of vs2 (bits of vs1 below vl) packed from vd[0]; elements from the packed
  count to the end of the group are tail (vta).
* viota.m: vd[i] = number of set bits of vs2 below i among active elements; vid.v: vd[i] = i.
* vmsbf/vmsif/vmsof: set-before-first / including-first / only-first over active bits; mask destination.
* vfcvt: per element, the scalar FCVT.WU.S / W.S / S.WU / S.W at 32 bits; rtz forms use RTZ regardless of frm.
* vmv<n>r.v copies n whole registers: vl and vtype are ignored (legal with vill), no tail; vd and vs2 aligned
  to n; vstart != 0 is illegal as for other arithmetic.
* Mask logical (.mm) instructions are unmasked, act on bits below vl, and write tail bits as ones.

### Reductions

vd[0] = op(vs1[0], active elements of vs2). The other elements of vd (one register) are tail. If vl = 0 nothing is
written. If no element is active, vd[0] = vs1[0] (bits copied, no flags).
* Integer: exact, at SEW bits.
* **vfredosum:** strictly in element order: ((vs1[0] + e_a) + e_b) + ... over active elements a < b < ...
* **vfredusum:** a fixed pairwise tree, defined on element indices: T(lo, n) for a power of two n is the single
  active element lo (n = 1), and otherwise T(lo, n/2) (+) T(lo + n/2, n/2), where "empty (+) x = x" and
  "empty (+) empty = empty"; inactive and tail elements are empty. The tree is T(0, 2^ceil(log2(vl))) (the same
  result for any larger power of two). Then vd[0] = vs1[0] + T (one more addition) if T is not empty. Each
  addition rounds with frm and contributes flags; NaN results are canonical.
* vfredmin/vfredmax: the scalar FMIN/FMAX applied in element order starting from vs1[0] (the result is
  order-independent; NV if any operand is a signalling NaN).

## 6. Vector loads and stores

LOAD-FP 0x07 / STORE-FP 0x27 with width 0 (EEW 8), 5 (16), 6 (32), 7 (64): nf[31:29] mew[28] mop[27:26] vm[25]
lumop/sumop/rs2/vs2[24:20] rs1[19:15] width vd/vs3[11:7]. mew = 1, and nf != 0 except whole-register forms, are
illegal (no segments).

| mop | Form | EEW / EMUL |
|---|---|---|
| 00, lumop 00000 | vle<eew>.v / vse<eew>.v (unit stride) | data EEW = width, EMUL = EEW/SEW*LMUL |
| 00, lumop 10000 | vle<eew>ff.v (fault-only-first, loads only) | as unit stride |
| 00, lumop 01011 | vlm.v / vsm.v (mask), width 0 only | EEW 8, evl = ceil(vl/8) bytes, EMUL 1, unmasked; vlm writes bytes evl..VLENB-1 as 0xff (always tail agnostic); nothing if vl = 0 |
| 00, lumop 01000 | vl<n>re<eew>.v / vs<n>r.v (whole registers), nf = n-1 for n = 1, 2, 4, 8; vs<n>r needs width 0 | n*VLEN bits, vl and vtype ignored (legal even with vill), unmasked |
| 10 | vlse / vsse (strided, x[rs2] signed byte stride, stride 0 allowed: every element accesses the same address) | as unit stride |
| 01 / 11 | vluxei / vloxei / vsuxei / vsoxei (indexed; index EEW = width, data EEW = SEW) | index EMUL = width/SEW*LMUL, data EMUL = LMUL |

* Element address: unit stride x[rs1] + i*EEW/8; strided x[rs1] + i*stride; indexed x[rs1] + zero-extended vs2[i].
* Elements are accessed one at a time in increasing index order (ordered and unordered indexed forms alike).
  Every element must be naturally aligned to its EEW, else misaligned (cause 4 load / 6 store); an element beyond
  RAM or at an injected fault beat is an access fault (5 / 7), exactly as scalar accesses. Inactive and prestart
  elements are not accessed and cannot fault.
* **Element-precise traps.** If element i faults: the active elements before i have completed (stores wrote
  memory, loads wrote their destination elements); inactive elements before i, elements i and later, and the
  tail of the destination are unchanged (no agnostic writes on a trap); vstart = i; then the trap. Trace order: the W records of the completed store elements; for loads,
  V records of the destination registers if any element was written; `C 008 <i>` if i > 0; then the T record.
* **Fault-only-first.** A fault at element 0 traps as above. A fault at element i > 0 does not trap: vl becomes i,
  elements below i are written, elements from i to the end of the group are tail under the new vl (vta), and the
  instruction retires. Trace: `C c20 <new vl>`, V records, R. vl is never shortened without a fault.
* Whole-register and mask loads/stores ignore masking and vstart > 0 still applies to them.
* Stores: one W record per element, in element order, in the W format of scalar stores (aligned beat address,
  element bytes shifted into their lane, zeros elsewhere, byte mask).

## 7. Trace format extension

Additions only; integer and scalar FP traces are unchanged.
* **`V vv <VLEN/4 hex digits>`**: vector register vv (2 hex digits, 00-1f) after the instruction, the whole
  register, most significant digit first. An instruction emits one record for **every register of its
  destination group**, in ascending order, **whenever vstart < vl**. This holds whether or not any element is
  written or changes; a fully masked tu/mu instruction, for example, still emits them. Exceptions:
  - vlm.v emits them when vstart < ceil(vl/8);
  - whole-register loads (vl<n>re) and vmv<n>r.v always emit them, even when vstart >= their element count.

  Group sizes: LMUL or EMUL registers (at least 1) for vector results; 1 for mask results, reductions and
  vmv.s.x / vfmv.s.f; n for whole-register forms. Instructions that do not meet the condition emit none. A
  load that traps at element i emits the group's records if i > vstart, and none if i = vstart.
* **`C <csr> <16 hex digits>`** (as FP-CONTRACT.md): c20 (vl) and c21 (vtype) from vsetvl* (always both, vl
  first) and from fault-only-first truncation (c20 only); 008 when vstart becomes non-zero at a trap, or returns
  to 0 at the end of an instruction that started with vstart != 0 (a vector load or store, or vsetvl*, which
  prints it after its c20/c21 records); and any CSR instruction that writes a vector
  CSR (008, 009, 00a, 00f: reports that CSR's new value).
* **R record** of a vector instruction: destination 00 unless it writes an x register (vsetvl*, vmv.x.s,
  vcpop.m, vfirst.m: 01-1f) or an f register (vfmv.f.s: 20-3f).
* **Order per instruction:** W (element order), F, C, V (ascending), R; a trap ends with T.

## 8. Out of scope for this step

FP64 vector arithmetic (Zve64d / V), widening and narrowing (vfwmacc for mixed precision, vnsrl), fixed point
(vsadd, vxrm use), segment loads/stores, vfrec7/vfrsqrt7, vrgatherei16, vadc/vmadc, vfncvt/vfwcvt, Zvbb/Zvkt,
misaligned elements, vl choices other than min(AVL, VLMAX), and the full V profile claim.

## 9. Implementation status of the out-of-order core (step 1, simd hand-off v1)

A status record, not part of the contract: the contract defines all of sections 5 and 6, but step 1 of the core
executes only part of them, and raises cause 2 for the rest. Differential tests against the models must not use
the unimplemented instructions until a later step adds them.
* Executed: vsetvli / vsetivli / vsetvl; the vector CSRs; unit-stride, strided, whole-register and mask loads and
  stores (EEW 8-64, masked, vle*ff, element-precise faults with vstart); every FP32 instruction of section 5
  (the OPFVV / OPFVF column, vec_ref.vfp).
* Cause 2 in the core so far: all OPIVV / OPIVX / OPIVI / OPMVV / OPMVX integer, mask-logical, permute, vmv and
  reduction instructions, and indexed loads and stores (mop 01 / 11).

