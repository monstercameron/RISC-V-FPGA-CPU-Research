"""Directed RVV-subset test programs and encoders (contract: cpu/RVV-CONTRACT.md).

vec_cases() yields (name, words, fault_kind, fault_address) like fp_cases.fp_cases(); run them with
reference_fp.execute(image, ..., fp=True, vector=True, vlen=VLEN). Constant table at 0x1000 (x28),
results from 0x3000 (x29), vector data area at 0x2000-0x2fff (x27).
SPDX-License-Identifier: MIT
"""
import struct

import fp_cases as fc

MASK = (1 << 64) - 1
VDATA = 0x2000
OPIVV, OPFVV, OPMVV, OPIVI, OPIVX, OPFVF, OPMVX = 0, 1, 2, 3, 4, 5, 6
E8, E16, E32, E64 = 0, 1, 2, 3
M1, M2, M4, M8, MF8, MF4, MF2 = 0, 1, 2, 3, 5, 6, 7
W8, W16, W32, W64 = 0, 5, 6, 7


def vtypei(sew, lmul, ta=1, ma=1):
    return ma << 7 | ta << 6 | sew << 3 | lmul


def vsetvli(rd, rs1, vt):
    return (vt & 0x7ff) << 20 | rs1 << 15 | 7 << 12 | rd << 7 | 0x57


def vsetivli(rd, uimm, vt):
    return 3 << 30 | (vt & 0x3ff) << 20 | uimm << 15 | 7 << 12 | rd << 7 | 0x57


def vsetvl(rd, rs1, rs2):
    return 1 << 31 | rs2 << 20 | rs1 << 15 | 7 << 12 | rd << 7 | 0x57


def opv(funct6, f3, vd, vs2, vs1, vm=1):
    return funct6 << 26 | vm << 25 | vs2 << 20 | (vs1 & 31) << 15 | f3 << 12 | vd << 7 | 0x57


def vmem(load, width, vd, rs1, mop=0, lumop=0, vm=1, nf=0, mew=0):
    return nf << 29 | mew << 28 | mop << 26 | vm << 25 | lumop << 20 | rs1 << 15 | width << 12 | vd << 7 | \
        (0x07 if load else 0x27)


def vle(width, vd, rs1, vm=1): return vmem(True, width, vd, rs1, 0, 0, vm)
def vse(width, vs3, rs1, vm=1): return vmem(False, width, vs3, rs1, 0, 0, vm)
def vleff(width, vd, rs1, vm=1): return vmem(True, width, vd, rs1, 0, 16, vm)
def vlse(width, vd, rs1, rs2, vm=1): return vmem(True, width, vd, rs1, 2, rs2, vm)
def vsse(width, vs3, rs1, rs2, vm=1): return vmem(False, width, vs3, rs1, 2, rs2, vm)
def vluxei(width, vd, rs1, vs2, vm=1): return vmem(True, width, vd, rs1, 1, vs2, vm)
def vloxei(width, vd, rs1, vs2, vm=1): return vmem(True, width, vd, rs1, 3, vs2, vm)
def vsuxei(width, vs3, rs1, vs2, vm=1): return vmem(False, width, vs3, rs1, 1, vs2, vm)
def vsoxei(width, vs3, rs1, vs2, vm=1): return vmem(False, width, vs3, rs1, 3, vs2, vm)
def vlm(vd, rs1): return vmem(True, W8, vd, rs1, 0, 11)
def vsm(vs3, rs1): return vmem(False, W8, vs3, rs1, 0, 11)
def vlre(n, width, vd, rs1): return vmem(True, width, vd, rs1, 0, 8, 1, n - 1)
def vsr(n, vs3, rs1): return vmem(False, W8, vs3, rs1, 0, 8, 1, n - 1)


# funct6 values (RVV-CONTRACT.md section 5)
VADD, VSUB, VRSUB, VMINU, VMIN, VMAXU, VMAX, VAND, VOR, VXOR, VRGATHER = 0, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12
VSLIDEUP, VSLIDEDOWN, VMERGE, VMSEQ, VMSNE, VMSLTU, VMSLT, VMSLEU, VMSLE, VMSGTU, VMSGT = 14, 15, 23, 24, 25, 26, 27, 28, 29, 30, 31
VSLL, VSRL, VSRA, VMVNR = 0x25, 0x28, 0x29, 0x27
VREDSUM, VREDAND, VREDOR, VREDXOR, VREDMINU, VREDMIN, VREDMAXU, VREDMAX = range(8)
VWXUNARY0, VXUNARY0, VMUNARY0, VCOMPRESS = 0x10, 0x12, 0x14, 0x17
VMANDN, VMAND, VMOR, VMXOR, VMORN, VMNAND, VMNOR, VMXNOR = range(0x18, 0x20)
VDIVU, VDIV, VREMU, VREM, VMULHU, VMUL, VMULHSU, VMULH = range(0x20, 0x28)
VMADD, VNMSUB, VMACC, VNMSAC = 0x29, 0x2b, 0x2d, 0x2f
VFADD, VFREDUSUM, VFSUB, VFREDOSUM, VFMIN, VFREDMIN, VFMAX, VFREDMAX = range(8)
VFSGNJ, VFSGNJN, VFSGNJX, VFSLIDE1UP, VFSLIDE1DOWN = 8, 9, 10, 14, 15
VWFUNARY0, VFUNARY0, VFUNARY1, VFMERGE = 0x10, 0x12, 0x13, 0x17
VMFEQ, VMFLE, VMFLT, VMFNE, VMFGT, VMFGE = 0x18, 0x19, 0x1b, 0x1c, 0x1d, 0x1f
VFDIV, VFRDIV, VFMUL, VFRSUB = 0x20, 0x21, 0x24, 0x27
VFMADD, VFNMADD, VFMSUB, VFNMSUB, VFMACC, VFNMACC, VFMSAC, VFNMSAC = range(0x28, 0x30)
CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VL, CSR_VTYPE, CSR_VLENB = 0x008, 0x009, 0x00a, 0x00f, 0xc20, 0xc21, 0xc22


def vprog():
    p = fc.Prog()
    p.emit(fc.lui(27, VDATA))
    return p


def fill_data(p, words):
    """Vector data area contents: emitted as stores from the constant table at run start."""
    for k, w in enumerate(words):
        p.x(5, w)
        p.emit(fc.sd(5, 27, 8 * k))


def case_basic(vlen):
    """vsetvli forms, unit-stride load/add/store at every SEW, tail/mask policies."""
    p = vprog()
    fill_data(p, [0x0706050403020100 + 0x0808080808080808 * k for k in range(16)])
    for sew, width in ((E8, W8), (E16, W16), (E32, W32), (E64, W64)):
        for ta, ma in ((1, 1), (0, 0)):
            p.emit(fc.addi(6, 0, 5), vsetvli(7, 6, vtypei(sew, M1, ta, ma)))   # vl = 5
            p.save_x(7)
            p.emit(vle(width, 1, 27), vle(width, 2, 27))
            p.emit(opv(VADD, OPIVV, 3, 1, 2), opv(VADD, OPIVI, 4, 1, -3), opv(VSUB, OPIVX, 5, 1, 6))
            p.emit(opv(VMSLTU, OPIVX, 0, 1, 6), opv(VADD, OPIVV, 4, 1, 3, vm=0))       # masked add (v0 mask)
            p.emit(vse(width, 3, 29), vse(width, 4, 29, vm=0))
    p.emit(vsetvli(8, 0, vtypei(E32, M8)))                                          # vl = VLMAX
    p.save_x(8)
    p.emit(vsetvli(0, 0, vtypei(E16, M4)))                                          # keep vl: same VLMAX
    p.emit(fc.csr(2, 9, CSR_VL, 0), fc.csr(2, 10, CSR_VTYPE, 0), fc.csr(2, 11, CSR_VLENB, 0))
    p.save_x(9); p.save_x(10); p.save_x(11)
    p.emit(vsetvli(0, 0, vtypei(E16, M1)))                                          # VLMAX changes: vill
    p.emit(fc.csr(2, 9, CSR_VL, 0), fc.csr(2, 10, CSR_VTYPE, 0))
    p.save_x(9); p.save_x(10)
    p.emit(vsetivli(12, 3, vtypei(E64, MF2)))                                       # SEW 64 > LMUL*ELEN: vill
    p.save_x(12)
    p.emit(vsetivli(12, 17, vtypei(E8, MF8)), vsetivli(13, 31, vtypei(E8, M8)))
    p.save_x(12); p.save_x(13)
    p.x(14, 1 << 63)
    p.emit(vsetvl(15, 6, 14)); p.save_x(15)                                         # vsetvl with vill bit
    p.x(14, vtypei(E32, M2, 0, 1)); p.emit(vsetvl(15, 6, 14)); p.save_x(15)
    p.emit(fc.csr(1, 16, CSR_VSTART, 0), fc.csr(5, 17, CSR_VXRM, 3), fc.csr(6, 18, CSR_VXSAT, 1),
           fc.csr(2, 19, CSR_VCSR, 0))
    for r in (16, 17, 18, 19):
        p.save_x(r)
    return p.words()


def case_int_ops(vlen):
    p = vprog()
    vals = [0x80, 0x7f, 0xff, 0x01, 0x00, 0x8000, 0x7fff, 0xffff, 0x80000000, 0x7fffffff, 0xffffffff,
            0x8000000000000000, 0x7fffffffffffffff, MASK, 3, 0x123456789abcdef1]
    fill_data(p, vals + [v ^ 0x5a5a5a5a5a5a5a5a for v in vals])
    p.x(6, 0xfffffffffffffffd)                                                       # -3
    for sew, width in ((E8, W8), (E16, W16), (E32, W32), (E64, W64)):
        p.emit(fc.addi(7, 0, 31), vsetvli(0, 7, vtypei(sew, M2)))
        p.emit(vle(width, 2, 27), fc.addi(5, 27, 128), vle(width, 4, 5))
        for f6, forms in ((VADD, 'VXI'), (VSUB, 'VX'), (VRSUB, 'XI'), (VMINU, 'VX'), (VMIN, 'VX'), (VMAXU, 'VX'),
                          (VMAX, 'VX'), (VAND, 'VXI'), (VOR, 'VXI'), (VXOR, 'VXI'), (VSLL, 'VXI'), (VSRL, 'VXI'),
                          (VSRA, 'VXI')):
            for form in forms:
                f3, src = {'V': (OPIVV, 4), 'X': (OPIVX, 6), 'I': (OPIVI, 13)}[form]
                p.emit(opv(f6, f3, 8, 2, src))
                p.emit(vse(width, 8, 29))
        for f6 in (VDIVU, VDIV, VREMU, VREM, VMULHU, VMUL, VMULHSU, VMULH, VMADD, VNMSUB, VMACC, VNMSAC):
            p.emit(opv(VADD, OPIVI, 8, 2, 1))
            p.emit(opv(f6, OPMVV, 8, 2, 4), vse(width, 8, 29), opv(f6, OPMVX, 8, 4, 6), vse(width, 8, 29))
        for f6, forms in ((VMSEQ, 'VXI'), (VMSNE, 'VXI'), (VMSLTU, 'VX'), (VMSLT, 'VX'), (VMSLEU, 'VXI'),
                          (VMSLE, 'VXI'), (VMSGTU, 'XI'), (VMSGT, 'XI')):
            for form in forms:
                f3, src = {'V': (OPIVV, 4), 'X': (OPIVX, 6), 'I': (OPIVI, -3)}[form]
                p.emit(opv(f6, f3, 10, 2, src), vsm(10, 29))
        for f6 in range(8):                                                       # reductions
            p.emit(opv(f6, OPMVV, 12, 2, 4), vse(width, 12, 29))
        p.emit(opv(VMSLTU, OPIVX, 0, 2, 6))
        p.emit(opv(VREDSUM, OPMVV, 12, 2, 4, vm=0), vse(width, 12, 29))
    for ext in (2, 3, 4, 5, 6, 7):                                                # vzext / vsext
        sew = {2: E64, 3: E64, 4: E32, 5: E32, 6: E16, 7: E16}[ext]
        p.emit(fc.addi(7, 0, 9), vsetvli(0, 7, vtypei(sew, M2)), vle(W8, 1, 27))
        p.emit(opv(VXUNARY0, OPMVV, 4, 1, ext), vse({E64: W64, E32: W32, E16: W16}[sew], 4, 29))
    return p.words()


def case_mask_permute(vlen):
    p = vprog()
    fill_data(p, [0x0123456789abcdef * (k + 1) & MASK for k in range(32)])
    p.emit(fc.addi(6, 0, 13), vsetvli(0, 6, vtypei(E32, M1, 0, 0)))
    p.emit(vle(W32, 1, 27), vle(W32, 2, 27))
    p.emit(opv(VAND, OPIVI, 3, 1, 1), opv(VMSNE, OPIVI, 0, 3, 0))                # v0 = odd elements
    p.emit(opv(VMSLTU, OPIVX, 4, 1, 6), opv(VMSLEU, OPIVI, 5, 1, 15))
    for f6 in range(VMANDN, VMXNOR + 1):
        p.emit(opv(f6, OPMVV, 6, 4, 5), vsm(6, 29))
    p.emit(opv(VWXUNARY0, OPMVV, 7, 0, 16), opv(VWXUNARY0, OPMVV, 8, 0, 17))     # vcpop.m, vfirst.m
    p.emit(opv(VWXUNARY0, OPMVV, 9, 4, 16, vm=0), opv(VWXUNARY0, OPMVV, 10, 5, 17, vm=0))
    for r in (7, 8, 9, 10):
        p.save_x(r)
    for m in (1, 2, 3):
        p.emit(opv(VMUNARY0, OPMVV, 6, 4, m), vsm(6, 29), opv(VMUNARY0, OPMVV, 7, 4, m, vm=0), vsm(7, 29))
    p.emit(opv(VMUNARY0, OPMVV, 8, 4, 16), vse(W32, 8, 29))                      # viota.m
    p.emit(opv(VMUNARY0, OPMVV, 8, 0, 17), vse(W32, 8, 29))                      # vid.v
    p.emit(opv(VMUNARY0, OPMVV, 9, 0, 17, vm=0), vse(W32, 9, 29))
    p.emit(opv(VCOMPRESS, OPMVV, 10, 1, 4), vse(W32, 10, 29))
    p.emit(fc.addi(7, 0, 3))
    for f6, f3, s in ((VSLIDEUP, OPIVX, 7), (VSLIDEUP, OPIVI, 5), (VSLIDEDOWN, OPIVX, 7), (VSLIDEDOWN, OPIVI, 11),
                      (VRGATHER, OPIVX, 7), (VRGATHER, OPIVI, 30)):
        p.emit(opv(VMERGE, OPIVI, 11, 0, 9), opv(f6, f3, 11, 1, s), vse(W32, 11, 29))
    p.emit(opv(VREMU, OPMVX, 12, 1, 6), opv(VRGATHER, OPIVV, 13, 1, 12), vse(W32, 13, 29))
    p.x(14, 0xdeadbeef)
    p.emit(opv(14, OPMVX, 15, 1, 14), vse(W32, 15, 29), opv(15, OPMVX, 16, 1, 14), vse(W32, 16, 29))
    p.emit(opv(VMERGE, OPIVV, 17, 1, 2, vm=0), opv(VMERGE, OPIVX, 18, 1, 14, vm=0), opv(VMERGE, OPIVI, 19, 1, -1, vm=0))
    p.emit(opv(VMERGE, OPIVX, 20, 0, 14), vse(W32, 17, 29), vse(W32, 18, 29), vse(W32, 19, 29), vse(W32, 20, 29))
    p.emit(opv(VWXUNARY0, OPMVV, 21, 1, 0), opv(VWXUNARY0, OPMVX, 22, 0, 14))    # vmv.x.s, vmv.s.x
    p.save_x(21)
    p.emit(vsetivli(0, 0, vtypei(E32, M1)), opv(VWXUNARY0, OPMVV, 23, 1, 0), opv(VWXUNARY0, OPMVX, 22, 0, 6))
    p.save_x(23)                                                                  # vmv.x.s with vl = 0
    p.emit(opv(VMVNR, OPIVI, 24, 1, 0), opv(VMVNR, OPIVI, 26, 2, 1), opv(VMVNR, OPIVI, 28, 4, 3))
    return p.words()


def case_memory(vlen):
    p = vprog()
    fill_data(p, [(0x1111111111111111 * (k % 15 + 1)) ^ (k << 56) for k in range(64)])
    p.emit(fc.addi(6, 0, 7), vsetvli(0, 6, vtypei(E32, M2)))
    p.emit(fc.addi(7, 0, 12), vlse(W32, 2, 27, 7), vse(W32, 2, 29))                # stride 12 bytes
    p.emit(fc.addi(7, 0, -8), fc.addi(8, 27, 256), vlse(W32, 4, 8, 7), vse(W32, 4, 29))  # negative stride
    p.emit(vlse(W32, 6, 27, 0), vse(W32, 6, 29))                                  # stride 0
    p.emit(fc.addi(9, 29, 512), fc.addi(7, 0, 16), vsse(W32, 2, 9, 7))
    p.emit(vid_v(8), opv(VSLL, OPIVI, 8, 8, 3), opv(VXOR, OPIVI, 8, 8, 8))       # indices (i*8)^8
    p.emit(vluxei(W32, 10, 27, 8), vse(W32, 10, 29), vloxei(W32, 12, 27, 8), vse(W32, 12, 29))
    p.emit(vsetvli(0, 6, vtypei(E64, M4)), vluxei(W8, 4, 27, 1), vse(W64, 4, 29))   # 8-bit indices, 64-bit data
    p.emit(vsetvli(0, 6, vtypei(E32, M2)), vsuxei(W32, 12, 9, 8), vsoxei(W32, 10, 9, 8))
    p.emit(fc.addi(6, 0, 19), vsetvli(0, 6, vtypei(E8, M1)), vlm(0, 27), vsm(0, 29), vle(W8, 3, 27, vm=0),
           vse(W8, 3, 29, vm=0))
    for n in (1, 2, 4):
        p.emit(vlre(n, W64, 8, 27), vsr(n, 8, 29))
    p.emit(vlre(8, W8, 16, 27), vsr(8, 16, 29))
    p.emit(vsetvli(0, 6, vtypei(E16, M1)), vleff(W16, 5, 27), vse(W16, 5, 29))   # ff, no fault
    return p.words()


def vid_v(vd, vm=1):
    return opv(VMUNARY0, OPMVV, vd, 0, 17, vm)


def case_fault_only_first(vlen):
    """vle32ff.v that runs past the end of RAM: vl is truncated at the first faulting element."""
    p = vprog()
    p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -12))                                 # 3 elements before 16 KiB
    p.emit(fc.addi(6, 0, 8), vsetvli(0, 6, vtypei(E32, M1, 1, 1)), vleff(W32, 1, 8))
    p.emit(fc.csr(2, 9, CSR_VL, 0)); p.save_x(9)
    p.emit(vse(W32, 1, 29))
    return p.words()


def fault_cases():
    """Element-precise traps: (name, words, kind, address)."""
    base = vprog()
    base.emit(fc.addi(6, 0, 8), vsetvli(0, 6, vtypei(E32, M1, 0, 0)))
    pre = base.code[:]
    def prog(body):
        p = fc.Prog(); p.code = pre[:]; p.emit(*body); return p.words()
    yield 'v_load_beyond_ram', prog([fc.lui(8, 0x4000), fc.addi(8, 8, -8), vle(W32, 1, 8)]), 0, MASK
    yield 'v_load_fault_elem0', prog([fc.lui(8, 0x4000), vleff(W32, 1, 8)]), 0, MASK
    yield 'v_store_misaligned_elem', prog([fc.addi(7, 0, 6), vsse(W32, 1, 27, 7)]), 0, MASK
    yield 'v_store_access_fault', prog([vse(W32, 1, 27)]), 3, VDATA + 16
    yield 'v_load_access_fault_masked', prog([vid_v(2), opv(VMSNE, OPIVI, 0, 2, 4), vle(W32, 1, 27, vm=0)]), 2, VDATA + 16
    yield 'v_index_fault', prog([vid_v(2), opv(VSLL, OPIVI, 2, 2, 12), vluxei(W32, 4, 27, 2)]), 0, MASK


def illegal_cases():
    pre = [fc.lui(28, fc.DATA), fc.addi(6, 0, 4)]
    cfg = vsetvli(0, 6, vtypei(E32, M2))
    yield 'v_illegal_vill_reset', pre + [opv(VADD, OPIVV, 1, 2, 3), fc.EBREAK]
    yield 'v_illegal_misaligned_group', pre + [cfg, opv(VADD, OPIVV, 1, 2, 4), fc.EBREAK]
    yield 'v_illegal_masked_v0_dest', pre + [cfg, opv(VADD, OPIVV, 0, 2, 4, vm=0), fc.EBREAK]
    yield 'v_illegal_vstart', pre + [cfg, fc.csr(5, 0, CSR_VSTART, 1), opv(VADD, OPIVV, 2, 2, 4), fc.EBREAK]
    yield 'v_illegal_write_vl', pre + [cfg, fc.csr(1, 0, CSR_VL, 6), fc.EBREAK]
    yield 'v_illegal_fp_sew64', pre + [vsetvli(0, 6, vtypei(E64, M1)), opv(VFADD, OPFVV, 1, 2, 3), fc.EBREAK]
    yield 'v_illegal_frm', pre + [cfg, fc.csr(5, 0, fc.FRM, 6), opv(VFADD, OPFVV, 2, 2, 4), fc.EBREAK]
    yield 'v_illegal_slideup_overlap', pre + [cfg, opv(VSLIDEUP, OPIVI, 2, 2, 1), fc.EBREAK]
    yield 'v_illegal_compare_overlap', pre + [cfg, opv(VMSEQ, OPIVV, 3, 2, 4), fc.EBREAK]
    yield 'v_illegal_segment', pre + [cfg, vmem(True, W32, 2, 28, nf=1), fc.EBREAK]
    yield 'v_illegal_mew', pre + [cfg, vmem(True, W32, 2, 28, mew=1), fc.EBREAK]
    yield 'v_illegal_emul', pre + [vsetvli(0, 6, vtypei(E8, M4)), vle(W64, 0, 28), fc.EBREAK]
    yield 'v_illegal_widening', pre + [cfg, opv(0x30, OPIVV, 4, 2, 6), fc.EBREAK]
    yield 'v_illegal_vfrec7', pre + [cfg, opv(VFUNARY1, OPFVV, 2, 4, 5), fc.EBREAK]


def case_fp(vlen):
    p = vprog()
    vals = [fc.S_ONE, fc.f32(3.0), fc.f32(-0.5), fc.S_QNAN, fc.S_SNAN, fc.S_INF, fc.S_INF | fc.NEG32, 0, fc.NEG32,
            fc.S_MINSUB, fc.S_MINNORM, fc.S_MAX, fc.f32(1 / 3), fc.f32(2.5), fc.f32(-1e10), fc.f32(16777217.0)]
    other = [fc.f32(2.0), fc.f32(-3.0), fc.f32(0.5), fc.S_ONE, fc.S_ONE, fc.S_INF, fc.S_INF, fc.NEG32, 0,
             fc.f32(0.5), fc.f32(1.0 - 2 ** -24), fc.S_MAX, fc.f32(3.0), fc.f32(2.5), fc.f32(7.0), fc.f32(-1.0)]
    fill_data(p, [vals[2 * k] | vals[2 * k + 1] << 32 for k in range(8)] +
              [other[2 * k] | other[2 * k + 1] << 32 for k in range(8)])
    p.fs(1, fc.f32(1.5)); p.fd(2, fc.D_ONE)                                       # f2 not boxed: canonical NaN
    p.emit(fc.addi(6, 0, 16), vsetvli(0, 6, vtypei(E32, M2, 1, 0)))
    p.emit(vle(W32, 2, 27), fc.addi(5, 27, 64), vle(W32, 4, 5))
    p.emit(opv(VMFLT, OPFVF, 0, 2, 1))                                            # v0 = vals < 1.5
    for rm in (fc.RNE, fc.RDN, fc.RMM):
        p.emit(fc.csr(5, 0, fc.FRM, rm))
        for f6, forms in ((VFADD, 'VF'), (VFSUB, 'VF'), (VFRSUB, 'F'), (VFMUL, 'VF'), (VFDIV, 'VF'), (VFRDIV, 'F'),
                          (VFMIN, 'VF'), (VFMAX, 'VF'), (VFSGNJ, 'VF'), (VFSGNJN, 'VF'), (VFSGNJX, 'VF')):
            for form in forms:
                p.emit(opv(f6, OPFVV if form == 'V' else OPFVF, 6, 2, 4 if form == 'V' else 1), vse(W32, 6, 29))
            p.emit(opv(f6, OPFVF, 6, 2, 2, vm=0) if 'F' in forms else fc.addi(0, 0, 0), vse(W32, 6, 29))
            p.flags()
        for f6 in range(VFMADD, VFNMSAC + 1):
            p.emit(opv(VADD, OPIVI, 6, 4, 0), opv(f6, OPFVV, 6, 2, 4), vse(W32, 6, 29),
                   opv(f6, OPFVF, 6, 2, 1), vse(W32, 6, 29))
            p.flags()
        for f6, forms in ((VMFEQ, 'VF'), (VMFLE, 'VF'), (VMFLT, 'VF'), (VMFNE, 'VF'), (VMFGT, 'F'), (VMFGE, 'F')):
            for form in forms:
                p.emit(opv(f6, OPFVV if form == 'V' else OPFVF, 8, 2, 4 if form == 'V' else 1), vsm(8, 29))
            p.flags()
        for k in (0, 1, 2, 3, 6, 7):
            p.emit(opv(VFUNARY0, OPFVV, 6, 2, k), vse(W32, 6, 29))
        p.emit(opv(VFUNARY1, OPFVV, 6, 2, 0), vse(W32, 6, 29), opv(VFUNARY1, OPFVV, 6, 2, 16), vse(W32, 6, 29))
        p.flags()
        for f6 in (VFREDUSUM, VFREDOSUM, VFREDMIN, VFREDMAX):
            p.emit(opv(f6, OPFVV, 8, 2, 4), vse(W32, 8, 29), opv(f6, OPFVV, 8, 4, 2, vm=0), vse(W32, 8, 29))
        p.flags()
    p.emit(opv(VFMERGE, OPFVF, 10, 2, 1, vm=0), opv(VFMERGE, OPFVF, 12, 0, 1), vse(W32, 10, 29), vse(W32, 12, 29))
    p.emit(opv(VFSLIDE1UP, OPFVF, 14, 2, 1), opv(VFSLIDE1DOWN, OPFVF, 16, 2, 1), vse(W32, 14, 29), vse(W32, 16, 29))
    p.emit(opv(VWFUNARY0, OPFVV, 3, 4, 0), opv(VWFUNARY0, OPFVF, 18, 0, 1), vse(W32, 18, 29))
    p.save_f(3)
    return p.words()


def case_vstart_vset(vlen):
    """vsetvl* ends with vstart = 0: a load and an FP op after csrwi vstart + vsetvli see vstart 0."""
    p = vprog()
    fill_data(p, [0x0123456789abcdef * (k + 3) & MASK for k in range(8)])
    p.fs(1, fc.f32(1.5))
    p.emit(fc.addi(6, 0, 8), vsetvli(0, 6, vtypei(E32, M1, 0, 0)))
    p.emit(fc.csr(5, 0, CSR_VSTART, 2), vsetvli(7, 6, vtypei(E32, M1, 0, 0)), vle(W32, 1, 27), vse(W32, 1, 29))
    p.emit(fc.csr(5, 0, CSR_VSTART, 3), vsetivli(0, 5, vtypei(E32, M1, 1, 1)), opv(VFADD, OPFVF, 2, 1, 1))
    p.emit(fc.csr(5, 0, CSR_VSTART, 1), vsetvli(0, 0, vtypei(E32, M1, 1, 1)))      # keep-vl form
    p.emit(fc.csr(2, 9, CSR_VSTART, 0), vse(W32, 2, 29))
    p.save_x(7); p.save_x(9)
    return p.words()


def vec_cases(vlen=256):
    yield 'v_basic', case_basic(vlen), 0, MASK
    yield 'v_vstart_vset', case_vstart_vset(vlen), 0, MASK
    yield 'v_int_ops', case_int_ops(vlen), 0, MASK
    yield 'v_mask_permute', case_mask_permute(vlen), 0, MASK
    yield 'v_memory', case_memory(vlen), 0, MASK
    yield 'v_fault_only_first', case_fault_only_first(vlen), 0, MASK
    yield 'v_fp', case_fp(vlen), 0, MASK
    for name, words, kind, addr in fault_cases():
        yield name, words, kind, addr
    for name, words in illegal_cases():
        yield name, words, 0, MASK


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from reference_fp import execute
    vlens = [int(a) for a in sys.argv[1:]] or [128, 256, 512]
    for vlen in vlens:
        covered = set()
        for name, words, kind, address in vec_cases(vlen):
            trace, coverage = execute(fc.image_for(words), kind, address, fp=True, vector=True, vlen=vlen,
                                      max_steps=100000)
            covered |= coverage
            last = trace[-1]
            cause = int(last.split()[2], 16)
            expect_trap = not name.startswith(('v_basic', 'v_int', 'v_mask', 'v_memory', 'v_fault_only', 'v_fp',
                                                'v_vstart'))
            if expect_trap == (cause == 3):
                raise AssertionError(f'VLEN {vlen} {name}: unexpected stop {last}')
            print(f'VLEN {vlen} {name}: {len(trace)} records, stop {cause}')
        vnames = sorted(n for n in covered if n.startswith('v'))
        print(f'VLEN {vlen}: {len(vnames)} vector instruction names covered')


if __name__ == '__main__':
    main()
