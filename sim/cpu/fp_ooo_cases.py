"""F/D cases for the out-of-order core's rename and retirement (council middle, 0.17.0): the unified
register file, f0, FLW boxing, forwarding into an f register, the FP CSRs serialised at rename, fflags
accrual, dynamic rounding, recovery with FP writers on both sides of a branch. test_cpu.py --fpu adds
them; the trace is checked against reference.execute(..., fp=True).
SPDX-License-Identifier: MIT
"""
from test_cpu import i_type, r_type, store, branch, jal, prefix, MASK


def cases():
    # FP state (middle, FPU): FLW/FLD/FSW/FSD through the unified register file, f0 as an
    # ordinary register, FLW NaN-boxing, store-to-load forwarding into an f register, and the
    # FP CSRs (fsrmi, frcsr, fsflags, csrrs/csrrc, a read-only csrrsi) serialised at rename.
    fl = lambda f3, rd, rs1, imm: i_type(0x07, rd, f3, rs1, imm)
    fs = lambda f3, rs1, rs2, imm: (store(f3, rs1, rs2, imm) & ~0x7f) | 0x27
    csr = lambda f3, rd, src, c: (c << 20) | (src << 15) | (f3 << 12) | (rd << 7) | 0x73
    p = prefix() + [store(3, 30, 8, 0x300), store(3, 30, 3, 0x308),               # memory: x8, MASK
                    fl(2, 1, 30, 0x300), fl(3, 2, 30, 0x308), fl(3, 0, 30, 0x300),  # flw f1; fld f2; fld f0
                    fs(3, 30, 1, 0x310), fs(2, 30, 2, 0x318), fs(3, 30, 0, 0x320),  # fsd f1 (boxed); fsw f2; fsd f0
                    store(3, 30, 7, 0x328), fl(3, 3, 30, 0x328), fs(3, 30, 3, 0x330),   # forwarded into f3, stored
                    i_type(3, 20, 3, 30, 0x310), i_type(3, 21, 3, 30, 0x318), i_type(3, 22, 3, 30, 0x330),
                    csr(5, 6, 2, 0x002), csr(2, 7, 0, 0x003),                       # fsrmi 2 -> x6 old frm; frcsr x7
                    csr(1, 8, 9, 0x001), csr(3, 10, 2, 0x003),                      # fsflags x9; csrrc fcsr, x2
                    csr(6, 11, 0, 0x001), csr(2, 12, 0, 0x003),                     # csrrsi fflags, 0 (no write); frcsr
                    csr(1, 0, 5, 0x003), csr(2, 13, 0, 0x002),                      # fscsr x5 (x0 dest); frrm x13
                    fl(2, 31, 30, 0x308), fs(3, 30, 31, 0x338), i_type(3, 23, 3, 30, 0x338), 0x100073]
    yield 'fp_regs_loads_stores_csrs', p, 0, MASK
    # Any other CSR is still an illegal instruction with FP enabled.
    yield 'fp_csr_other_illegal', prefix() + [fl(3, 4, 30, 0), (0x300 << 20) | (2 << 12) | (5 << 7) | 0x73, 0x100073], 0, MASK
    # FP rename/retire with FP execution (middle FP state + backend FP execute): integer->FP
    # and FP->integer dependencies, a 3-source FMA, fflags accrued in order and read by frflags
    # (serialised), dynamic rounding after fsrmi, NaN-boxed singles, f0, and a data-dependent
    # branch with FP writers on both sides (recovery restores the f registers' mappings).
    fop = lambda f5, fmt, rd, rs1, rs2, rm: (((f5 << 2) | fmt) << 25) | (rs2 << 20) | (rs1 << 15) | (rm << 12) | (rd << 7) | 0x53
    fma = lambda rd, rs1, rs2, rs3, rm: (rs3 << 27) | (1 << 25) | (rs2 << 20) | (rs1 << 15) | (rm << 12) | (rd << 7) | 0x43
    csr = lambda f3, rd, src, c: (c << 20) | (src << 15) | (f3 << 12) | (rd << 7) | 0x73
    fs = lambda f3, rs1, rs2, imm: (store(f3, rs1, rs2, imm) & ~0x7f) | 0x27
    p = prefix() + [fop(0b11010, 1, 1, 2, 2, 7), fop(0b11010, 1, 2, 9, 2, 7),       # f1 = 1.0, f2 = 31.0 (fcvt.d.l)
                    fop(0b00011, 1, 3, 1, 2, 7),                                     # f3 = f1 / f2 (inexact)
                    fma(4, 3, 2, 1, 7),                                              # f4 = f3*f2 + f1
                    fop(0b10100, 1, 5, 4, 1, 2), fop(0b11100, 1, 6, 3, 0, 0),        # x5 = feq(f4, f1); x6 = fmv.x.d f3
                    fs(3, 30, 4, 0x300), csr(2, 7, 0, 0x001),                        # fsd f4; frflags x7
                    csr(5, 0, 1, 0x002), fop(0b00011, 1, 0, 1, 2, 7),                # fsrmi 1 (RTZ); f0 = 1/31 (dyn)
                    fop(0b11100, 1, 8, 0, 0, 0), csr(1, 0, 0, 0x001),                # x8 = f0 bits; fsflags x0
                    fop(0b11010, 0, 10, 2, 2, 0), fop(0b11100, 0, 11, 10, 0, 0),     # f10 = 1.0f (boxed); x11 = fmv.x.w
                    fop(0b10100, 1, 12, 3, 1, 1), fop(0b11100, 1, 13, 3, 0, 1),      # x12 = flt(f3, f1); x13 = fclass(f3)
                    fop(0b00000, 0, 14, 10, 3, 0), fop(0b11100, 0, 15, 14, 0, 1),    # f14 = f10 + f3 (f3 not boxed: NaN); fclass.s
                    csr(2, 16, 0, 0x003)]                                            # frcsr x16
    loop = [i_type(0x13, 17, 0, 17, 1), fop(0b11010, 1, 5, 17, 2, 0),               # i += 1; f5 = (double)i
            i_type(0x13, 18, 5, 17, 2), r_type(0x33, 19, 4, 17, 18), i_type(0x13, 19, 7, 19, 1),   # x19 = (i ^ i>>2) & 1
            branch(0, 19, 0, 12), fop(0b00000, 1, 6, 6, 5, 0), jal(0, 8),            # odd-ish: f6 += f5
            fop(0b00001, 1, 6, 6, 5, 0),                                             # else  f6 -= f5
            i_type(0x13, 20, 0, 20, -1), branch(1, 20, 0, -40)]
    p += [i_type(0x13, 20, 0, 0, 24), i_type(0x13, 17, 0, 0, 0)] + loop
    p += [fop(0b11100, 1, 21, 6, 0, 0), fs(3, 30, 6, 0x308), 0x100073]               # x21 = f6 bits; fsd f6
    yield 'fp_rename_flags_recovery', p, 0, MASK
    # FMA whose destination is one of its own sources (rd == rs3 accumulator, rd == rs1, rd == rs2):
    # every source is read from the map before the destination's new mapping is written.
    p = prefix() + [fop(0b11010, 1, 2, 2, 2, 7), fop(0b11010, 1, 3, 9, 2, 7),       # f2 = 1.0, f3 = 31.0
                    fop(0b11010, 1, 1, 0, 2, 7), fop(0b11010, 1, 4, 5, 2, 7),       # f1 = 0.0, f4 = (double)x5
                    i_type(0x13, 20, 0, 0, 6)]
    p += [fma(1, 2, 3, 1, 7), fma(1, 1, 2, 1, 7), i_type(0x13, 20, 0, 20, -1), branch(1, 20, 0, -12)]   # acc
    p += [fma(2, 2, 3, 4, 7), fma(3, 2, 3, 4, 7), fma(4, 4, 4, 4, 7),                # rd == rs1, rd == rs2, all four
          fs(3, 30, 1, 0x300), fs(3, 30, 2, 0x308), fs(3, 30, 3, 0x310), fs(3, 30, 4, 0x318),
          fop(0b11100, 1, 21, 1, 0, 0), 0x100073]
    yield 'fp_fma_rd_is_source', p, 0, MASK
