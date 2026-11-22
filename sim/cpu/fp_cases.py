"""Directed F/D test programs for test_cpu-style differential runs (contract: cpu/architecture.md (RV64F and RV64D)).

fp_cases() yields (name, words, fault_kind, fault_address) like test_cpu.cases(): words is a program
for test_cpu.image_for (code from address 0, a constant table at 0x1000; results are stored from
0x3000, so the trace's W records carry them). Run with reference.execute(image, ..., fp=True).
test_cpu.py --fpu runs them on the out-of-order core.

FP_REQUIRED lists the instruction names the cases cover (as reference.py names them).
EXPECTED holds independently known results for some cases (stored words, by store index): the
Moller-Trumbore results come from the same arithmetic compiled natively for AArch64 (provenance at
MT_EXPECTED), the tininess results from the after-rounding rule worked by hand.
`python fp_cases.py` runs every case on reference.py and checks EXPECTED.
SPDX-License-Identifier: MIT
"""
import struct

MASK = (1 << 64) - 1
DATA, OUT = 0x1000, 0x3000          # constant table (x28) and result area (x29)
EBREAK = 0x100073
RNE, RTZ, RDN, RUP, RMM, DYN = 0, 1, 2, 3, 4, 7
S, D = 0, 1


# ---- encoders --------------------------------------------------------------------------------
def i_type(op, rd, f3, rs1, imm):
    return ((imm & 4095) << 20) | rs1 << 15 | f3 << 12 | rd << 7 | op


def s_type(op, f3, rs1, rs2, imm):
    imm &= 4095
    return (imm >> 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | (imm & 31) << 7 | op


def r_type(op, rd, f3, rs1, rs2, f7=0):
    return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op


def lui(rd, value):
    return (value & 0xfffff000) | rd << 7 | 0x37


def addi(rd, rs1, imm):
    return i_type(0x13, rd, 0, rs1, imm)


def ld(rd, rs1, imm):
    return i_type(0x03, rd, 3, rs1, imm)


def sd(rs2, rs1, imm):
    return s_type(0x23, 3, rs1, rs2, imm)


def branch(f3, rs1, rs2, offset):
    offset &= 8191
    return ((offset >> 12) << 31) | (((offset >> 5) & 63) << 25) | rs2 << 20 | rs1 << 15 | f3 << 12 | \
        (((offset >> 1) & 15) << 8) | (((offset >> 11) & 1) << 7) | 0x63


def fop(f5, fmt, rd, rs1, rs2=0, rm=0):
    return f5 << 27 | fmt << 25 | rs2 << 20 | rs1 << 15 | rm << 12 | rd << 7 | 0x53


def r4(op, fmt, rd, rs1, rs2, rs3, rm=RNE):
    return rs3 << 27 | fmt << 25 | rs2 << 20 | rs1 << 15 | rm << 12 | rd << 7 | op


FMADD, FMSUB, FNMSUB, FNMADD = 0x43, 0x47, 0x4b, 0x4f


def flw(fd, rs1, imm): return i_type(0x07, fd, 2, rs1, imm)
def fld(fd, rs1, imm): return i_type(0x07, fd, 3, rs1, imm)
def fsw(fs, rs1, imm): return s_type(0x27, 2, rs1, fs, imm)
def fsd(fs, rs1, imm): return s_type(0x27, 3, rs1, fs, imm)
def fadd(fmt, rd, a, b, rm=RNE): return fop(0, fmt, rd, a, b, rm)
def fsub(fmt, rd, a, b, rm=RNE): return fop(1, fmt, rd, a, b, rm)
def fmul(fmt, rd, a, b, rm=RNE): return fop(2, fmt, rd, a, b, rm)
def fdiv(fmt, rd, a, b, rm=RNE): return fop(3, fmt, rd, a, b, rm)
def fsqrt(fmt, rd, a, rm=RNE): return fop(0x0b, fmt, rd, a, 0, rm)
def fsgnj(fmt, rd, a, b, k=0): return fop(4, fmt, rd, a, b, k)        # k: 0 J, 1 JN, 2 JX
def fminmax(fmt, rd, a, b, mx): return fop(5, fmt, rd, a, b, mx)
def fcmp(fmt, rd, a, b, k): return fop(0x14, fmt, rd, a, b, k)        # k: 0 LE, 1 LT, 2 EQ
def fclass(fmt, rd, a): return fop(0x1c, fmt, rd, a, 0, 1)
def fmv_x(fmt, rd, a): return fop(0x1c, fmt, rd, a, 0, 0)
def fmv_f(fmt, rd, a): return fop(0x1e, fmt, rd, a, 0, 0)
def fcvt_to_int(fmt, rd, a, kind, rm=RNE): return fop(0x18, fmt, rd, a, kind, rm)   # kind 0 W 1 WU 2 L 3 LU
def fcvt_from_int(fmt, rd, a, kind, rm=RNE): return fop(0x1a, fmt, rd, a, kind, rm)
def fcvt_s_d(rd, a, rm=RNE): return fop(8, S, rd, a, 1, rm)
def fcvt_d_s(rd, a, rm=RNE): return fop(8, D, rd, a, 0, rm)
def csr(f3, rd, number, rs1): return i_type(0x73, rd, f3, rs1, number)   # f3 1 RW 2 RS 3 RC 5-7 immediate


FFLAGS, FRM, FCSR = 1, 2, 3


def f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def f64(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


# Named bit patterns.
S_ONE, S_QNAN, S_SNAN, S_INF, S_MAX, S_MINSUB, S_MINNORM = 0x3f800000, 0x7fc00000, 0x7f800001, 0x7f800000, 0x7f7fffff, 1, 0x00800000
D_ONE, D_QNAN, D_SNAN, D_INF, D_MAX, D_MINSUB, D_MINNORM = (0x3ff0000000000000, 0x7ff8000000000000, 0x7ff0000000000001,
                                                            0x7ff0000000000000, 0x7fefffffffffffff, 1, 0x0010000000000000)
NEG32, NEG64 = 0x80000000, 0x8000000000000000


class Prog:
    """Program builder: x28 -> constant table at DATA, x29 -> result area at OUT."""

    def __init__(self):
        self.code = [lui(28, DATA), lui(29, OUT)]
        self.data = []
        self.out = 0

    def const(self, value):
        if value & MASK in self.data:
            return 8 * self.data.index(value & MASK)
        self.data.append(value & MASK)
        assert len(self.data) <= 256, 'constant table full'
        return 8 * (len(self.data) - 1)

    def emit(self, *words):
        self.code.extend(words)

    def fs(self, fd, bits32):          # load a single (boxed by FLW)
        self.emit(flw(fd, 28, self.const(bits32)))

    def fd(self, fd, bits64):
        self.emit(fld(fd, 28, self.const(bits64)))

    def x(self, rd, value):
        self.emit(ld(rd, 28, self.const(value)))

    def _advance(self):
        self.out += 8
        if self.out >= 2040:            # move the result window on (it wraps inside 0x3000-0x3fff)
            self.emit(addi(29, 29, 2040))
            self.out = 0
            self.window = getattr(self, 'window', 0) + 1
            if self.window == 2:
                self.emit(lui(29, OUT))
                self.window = 0

    def save_f(self, fs):
        self.emit(fsd(fs, 29, self.out))
        self._advance()

    def save_x(self, xs):
        self.emit(sd(xs, 29, self.out))
        self._advance()

    def flags(self):
        """Read and clear fflags (csrrw x5, fflags, x0), store them."""
        self.emit(csr(1, 5, FFLAGS, 0))
        self.save_x(5)

    def words(self):
        code = self.code + [EBREAK]
        assert len(code) * 4 <= DATA, 'code overlaps the constant table'
        code += [0] * (DATA // 4 - len(code))
        for value in self.data:
            code += [value & 0xffffffff, value >> 32]
        return code


# ---- cases -----------------------------------------------------------------------------------
def case_move_box():
    p = Prog()
    p.x(5, S_ONE)                                    # 1.0f, not NaN-boxed in a 64-bit register
    p.emit(fmv_f(D, 1, 5))                           # f1 = 0x000000003f800000 (improperly boxed single)
    p.emit(fadd(S, 2, 1, 1)); p.save_f(2)            # reads as canonical NaN: result boxed 7fc00000, no NV
    p.emit(fmv_f(S, 3, 5)); p.save_f(3)              # fmv.w.x boxes
    p.emit(fadd(S, 4, 3, 3)); p.save_f(4)            # 2.0f
    p.emit(fsw(1, 29, p.out)); p._advance()          # FSW stores bits 31:0 without the box check
    p.emit(fmv_x(S, 6, 1)); p.save_x(6)              # FMV.X.W: bits 31:0 unchecked, sign-extended
    p.x(7, 0xbf800000)
    p.emit(fmv_f(S, 5, 7), fmv_x(S, 8, 5)); p.save_x(8)   # -1.0f -> 0xffffffffbf800000
    p.fs(6, 0xff800001)                              # sNaN single through FLW: boxed, no signal
    p.emit(fmv_x(D, 9, 6)); p.save_x(9); p.save_f(6)
    p.fd(7, D_SNAN)
    p.emit(fsgnj(D, 8, 7, 7, 1)); p.save_f(8)        # FSGNJN copies the sNaN payload, no NV
    p.emit(fsgnj(S, 9, 1, 3, 0)); p.save_f(9)        # unboxed operand -> canonical NaN with sign of f3
    p.emit(fclass(S, 10, 1)); p.save_x(10)           # unboxed reads as quiet NaN: class bit 9
    p.emit(fmv_x(S, 11, 7)); p.save_x(11)            # low word of a double
    p.emit(fcvt_d_s(12, 1)); p.save_f(12)            # canonical double NaN, no NV
    p.emit(fmv_f(S, 0, 5), fadd(S, 0, 0, 3)); p.save_f(0)   # f0 is a real register
    p.emit(fmv_f(D, 13, 0), fmv_x(D, 14, 13)); p.save_x(14)  # fmv.d.x of x0
    p.flags()
    return p.words()


def case_lanes():
    p = Prog()
    p.fs(1, f32(1.5)); p.fs(2, f32(-2.25)); p.fd(3, f64(3.125))
    for k in range(2):
        p.emit(fsw(1 + k, 29, 0x100 + 4 * k))            # both 4-byte lanes of one beat
    p.emit(fsd(3, 29, 0x108), flw(4, 29, 0x100), flw(5, 29, 0x104), fld(6, 29, 0x108),
           fld(7, 29, 0x100))                            # fld of the pair of singles
    for r in (4, 5, 6, 7):
        p.save_f(r)
    return p.words()


ARITH_PAIRS_S = [(S_ONE, f32(3.0)), (f32(0.1), f32(0.2)), (S_MAX, S_MAX), (S_MINSUB, f32(0.5)), (S_ONE, 0),
                 (0, 0), (S_INF, S_INF), (S_SNAN, S_ONE), (S_QNAN, S_ONE), (NEG32, 0), (0, NEG32),
                 (0x00c00000, f32(0.5)), (f32(-7.0), f32(2.0)), (S_MINNORM, f32(1.0 - 2 ** -24)),
                 (S_INF, 0), (f32(16777216.0), S_ONE), (S_ONE | NEG32, S_INF)]
ARITH_PAIRS_D = [(D_ONE, f64(3.0)), (f64(0.1), f64(0.2)), (D_MAX, D_MAX), (D_MINSUB, f64(0.5)), (D_ONE, 0),
                 (0, 0), (D_INF, D_INF), (D_SNAN, D_ONE), (D_QNAN, D_ONE), (NEG64, 0), (0, NEG64),
                 (0x0018000000000000, f64(0.5)), (f64(-7.0), f64(2.0)), (D_MINNORM, f64(1.0 - 2 ** -53)),
                 (D_INF, 0), (f64(2.0 ** 53), D_ONE), (D_ONE | NEG64, D_INF)]


def case_arith(fmt):
    p = Prog()
    for a, b in (ARITH_PAIRS_D if fmt else ARITH_PAIRS_S):
        if fmt:
            p.fd(1, a); p.fd(2, b)
        else:
            p.fs(1, a); p.fs(2, b)
        for op in (fadd, fsub, fmul, fdiv):
            p.emit(op(fmt, 3, 1, 2)); p.save_f(3)
        p.emit(fsqrt(fmt, 4, 1)); p.save_f(4)
        p.flags()
    return p.words()


def case_fma(fmt):
    p = Prog()
    one, inf, qnan, snan, neg = (D_ONE, D_INF, D_QNAN, D_SNAN, NEG64) if fmt else (S_ONE, S_INF, S_QNAN, S_SNAN, NEG32)
    v = f64 if fmt else f32
    eps = 2.0 ** (-52 if fmt else -23)
    triples = [(inf, 0, qnan), (0, inf, qnan), (inf, 0, snan), (v(2.0), v(3.0), v(-6.0)), (0, 0, 0),
               (neg, 0, 0), (v(1 + eps), v(1 - eps), v(-1.0)), (inf, one, inf | neg), (inf, one, inf),
               (v(1.5), v(1.0e30), v(-1.5e30)), (one, one, v(eps / 2)), (v(3.0), v(1 / 3), v(-1.0)),
               (snan, one, one), (qnan, one, one), (v(1.0e-30), v(1.0e-30), v(1.0e-45 if not fmt else 1e-310))]
    for a, b, c in triples:
        load = p.fd if fmt else p.fs
        load(1, a); load(2, b); load(3, c)
        for op in (FMADD, FMSUB, FNMSUB, FNMADD):
            for rm in (RNE, RDN):
                p.emit(r4(op, fmt, 4, 1, 2, 3, rm)); p.save_f(4)
        p.flags()
    return p.words()


def rounding_body(p, rm):
    p.fs(1, S_ONE); p.fs(2, f32(3.0)); p.fs(3, f32(2.0 ** -24)); p.fs(4, f32(3 * 2.0 ** -24))
    p.emit(fdiv(S, 5, 1, 2, rm)); p.save_f(5)                         # 1/3
    p.emit(fsgnj(S, 6, 1, 1, 1), fdiv(S, 7, 6, 2, rm)); p.save_f(7)   # -1/3
    p.emit(fadd(S, 8, 1, 3, rm)); p.save_f(8)                         # 1 + 2^-24: tie, even down
    p.emit(fadd(S, 9, 1, 4, rm)); p.save_f(9)                         # 1 + 3*2^-24: tie, even up
    p.emit(fsub(S, 10, 6, 3, rm)); p.save_f(10)                       # -1 - 2^-24
    for x in (2.5, -2.5, 3.5, -0.5, 0.5, -1.5):
        p.fs(11, f32(x))
        p.emit(fcvt_to_int(S, 12, 11, 0, rm)); p.save_x(12)
    p.x(13, (1 << 24) + 1)
    p.emit(fcvt_from_int(S, 14, 13, 2, rm)); p.save_f(14)             # 2^24 + 1 -> tie
    p.x(13, (1 << 53) + 3)
    p.emit(fcvt_from_int(D, 14, 13, 3, rm)); p.save_f(14)
    p.fd(15, f64(1.0 + 2.0 ** -24))
    p.emit(fcvt_s_d(16, 15, rm)); p.save_f(16)                        # double tie at single precision
    p.fd(15, f64(1.0) | NEG64); p.fd(17, f64(3.0))
    p.emit(fdiv(D, 18, 15, 17, rm)); p.save_f(18)
    p.emit(fsqrt(D, 19, 17, rm)); p.save_f(19)
    p.flags()


def case_rounding():
    p = Prog()
    for rm in (RNE, RTZ, RDN, RUP, RMM):
        rounding_body(p, rm)
    for rm in (RNE, RTZ, RDN, RUP, RMM):
        p.emit(csr(5, 0, FRM, rm))                                    # fsrmi rm
        rounding_body(p, DYN)
    return p.words()


def case_csr():
    p = Prog()
    p.emit(csr(5, 5, FRM, 3)); p.save_x(5)           # csrrwi frm, 3: old 0
    p.emit(csr(2, 6, FCSR, 0)); p.save_x(6)          # read fcsr (no write, no C record): 0x60
    p.emit(csr(5, 7, FFLAGS, 0x1f)); p.save_x(7)     # set all flags
    p.emit(csr(2, 8, FCSR, 0)); p.save_x(8)          # 0x7f
    p.emit(csr(7, 9, FFLAGS, 5)); p.save_x(9)        # csrrci: clear NX and OF
    p.emit(csr(3, 10, FCSR, 0)); p.save_x(10)        # csrrc with x0: no write
    p.x(11, 0xffffffffffffff81)
    p.emit(csr(1, 12, FCSR, 11)); p.save_x(12)       # csrrw fcsr: bits above 7 ignored -> 0x81
    p.emit(csr(2, 13, FRM, 0)); p.save_x(13)         # frm = 4
    p.emit(csr(6, 14, FFLAGS, 2)); p.save_x(14)      # csrrsi: old 1
    p.emit(csr(6, 15, FFLAGS, 0)); p.save_x(15)      # csrrsi with uimm 0: no write
    p.x(16, 0)
    p.emit(csr(3, 17, FCSR, 16)); p.save_x(17)       # csrrc with a zero value but rs1 != x0: writes
    p.emit(csr(1, 0, FCSR, 0))                       # csrrw x0, fcsr, x0: clear
    p.x(18, 0xe7)
    p.emit(csr(1, 19, FRM, 18)); p.save_x(19)        # frm = 7 (only low 3 bits)
    p.emit(csr(2, 20, FCSR, 0)); p.save_x(20)
    p.emit(csr(5, 0, FRM, 0))
    p.fs(1, S_ONE); p.fs(2, f32(3.0))
    p.emit(fdiv(S, 3, 1, 2, DYN), fdiv(S, 3, 1, 2, DYN))          # accrual: NX twice
    p.emit(csr(2, 21, FFLAGS, 0)); p.save_x(21)
    p.fs(4, 0)
    p.emit(fdiv(S, 5, 1, 4))                                      # DZ accrues onto NX
    p.emit(csr(2, 22, FCSR, 0)); p.save_x(22)
    p.emit(csr(1, 23, FFLAGS, 0)); p.save_x(23)                   # fsflags x0 (read and clear)
    p.emit(csr(5, 24, FCSR, 0x1f)); p.save_x(24)                  # csrrwi fcsr: uimm 5 bits
    p.emit(csr(2, 25, FCSR, 0)); p.save_x(25)
    p.emit(csr(5, 0, FCSR, 0))
    return p.words()


CMP_PAIRS = ['qnan,one', 'snan,one', 'one,qnan', 'nzero,zero', 'zero,nzero', 'one,two', 'two,one', 'ninf,inf',
             'snan,snan', 'qnan,qnan', 'none,none', 'minsub,zero', 'nminsub,nzero', 'snan,qnan']


def case_compare(fmt):
    p = Prog()
    if fmt:
        vals = dict(qnan=D_QNAN, snan=D_SNAN, one=D_ONE, two=f64(2.0), zero=0, nzero=NEG64, inf=D_INF,
                    ninf=D_INF | NEG64, none=D_ONE | NEG64, minsub=D_MINSUB, nminsub=D_MINSUB | NEG64)
        load = p.fd
    else:
        vals = dict(qnan=S_QNAN, snan=S_SNAN, one=S_ONE, two=f32(2.0), zero=0, nzero=NEG32, inf=S_INF,
                    ninf=S_INF | NEG32, none=S_ONE | NEG32, minsub=S_MINSUB, nminsub=S_MINSUB | NEG32)
        load = p.fs
    for pair in CMP_PAIRS:
        a, b = pair.split(',')
        load(1, vals[a]); load(2, vals[b])
        for k in (0, 1, 2):
            p.emit(fcmp(fmt, 5, 1, 2, k)); p.save_x(5)
        for mx in (0, 1):
            p.emit(fminmax(fmt, 3, 1, 2, mx)); p.save_f(3)
        for k in (0, 1, 2):
            p.emit(fsgnj(fmt, 4, 1, 2, k)); p.save_f(4)
        p.flags()
    if fmt:
        classes = [D_INF | NEG64, D_ONE | NEG64, D_MINSUB | NEG64, NEG64, 0, D_MINSUB, D_ONE, D_INF, D_SNAN, D_QNAN,
                   0x000fffffffffffff, D_MINNORM]
    else:
        classes = [S_INF | NEG32, S_ONE | NEG32, S_MINSUB | NEG32, NEG32, 0, S_MINSUB, S_ONE, S_INF, S_SNAN, S_QNAN,
                   0x007fffff, S_MINNORM]
    for c in classes:
        load(6, c)
        p.emit(fclass(fmt, 7, 6)); p.save_x(7)
    p.emit(fcmp(fmt, 0, 1, 2, 1))                    # flt with x0 destination: flags only
    p.flags()
    return p.words()


def case_convert(part):
    p = Prog()
    to_int = [D_QNAN, D_SNAN, D_INF, D_INF | NEG64, f64(2.0 ** 31), f64(2.0 ** 31 - 0.5), f64(-2.0 ** 31),
              f64(-2.0 ** 31 - 1), f64(-2.0 ** 31 - 0.5), f64(2.0 ** 32), f64(2.0 ** 32 - 0.25), f64(2.0 ** 63),
              f64(2.0 ** 64), f64(-2.0 ** 63), f64(-0.4), f64(-0.6), f64(-1.0), f64(0.5), f64(1.5), f64(2.5),
              f64(-2.5), f64(1e20), f64(-1e20), NEG64, D_MINSUB, f64(4294967295.5), f64(9.2233720368547748e18)]
    for bits in (to_int if part == 'to_int' else []):
        x = struct.unpack('<d', struct.pack('<Q', bits))[0]
        p.fd(1, bits)
        single = f32(x) if x == x else (S_SNAN if bits == D_SNAN else S_QNAN)
        p.fs(2, single)
        for kind in range(4):
            for rm in (RNE, RTZ, RMM):
                p.emit(fcvt_to_int(D, 5, 1, kind, rm)); p.save_x(5)
            p.emit(fcvt_to_int(S, 6, 2, kind, RNE)); p.save_x(6)
        p.flags()
    ints = [0, 1, MASK, (1 << 24) + 1, (1 << 53) + 1, 1 << 63, (1 << 64) - 1, 0xffffffff80000000, 0xffffffff,
            0x7fffffff, 0x0123456789abcdef, 0xffffffff00000001, 0x00000000ffffff7f]
    for value in (ints if part == 'from_int' else []):
        p.x(7, value)
        for kind in range(4):
            for fmt in (S, D):
                for rm in (RNE, RUP, RDN):
                    p.emit(fcvt_from_int(fmt, 8, 7, kind, rm)); p.save_f(8)
        p.flags()
    sd_vals = [f64(1 / 3), f64(1e39), f64(-1e39), f64(1e-46), f64(-1e-46), D_SNAN, D_QNAN | NEG64, D_INF | NEG64,
               NEG64, f64(3.4028235677973366e38), f64(1.401298464324817e-45 * 1.5), f64(2.0 ** -149 * 0.5)]
    for bits in (sd_vals if part == 'ff' else []):
        p.fd(1, bits)
        for rm in (RNE, RTZ, RUP, RMM):
            p.emit(fcvt_s_d(3, 1, rm)); p.save_f(3)
        p.flags()
    for bits in ((S_SNAN, S_QNAN, S_MINSUB, NEG32, S_MAX, S_INF | NEG32) if part == 'ff' else ()):
        p.fs(1, bits)
        p.emit(fcvt_d_s(3, 1)); p.save_f(3)
        p.flags()
    return p.words()


# Tininess after rounding (the AArch64 FPU detects it before rounding; see FP-CONTRACT.md section 5).
# Each entry: (description, instruction builder inputs, rm, expected result bits, expected fflags).
TININESS = [
    # 2^-126 * (1 - 2^-25): rounds to 2^-126 even with an unbounded exponent -> not tiny: NX only.
    ('cvt.s.d 2^-126(1-2^-25) RNE', 'sd', f64(2.0 ** -126 * (1 - 2.0 ** -25)), RNE, 0xffffffff00800000, 0x01),
    # 2^-126 * (1 - 2^-24): representable with 24 bits and an unbounded exponent -> tiny: UF NX.
    ('cvt.s.d 2^-126(1-2^-24) RNE', 'sd', f64(2.0 ** -126 * (1 - 2.0 ** -24)), RNE, 0xffffffff00800000, 0x03),
    ('cvt.s.d 2^-126(1-2^-25) RUP', 'sd', f64(2.0 ** -126 * (1 - 2.0 ** -25)), RUP, 0xffffffff00800000, 0x01),
    ('cvt.s.d 2^-126(1-2^-24) RUP', 'sd', f64(2.0 ** -126 * (1 - 2.0 ** -24)), RUP, 0xffffffff00800000, 0x03),
    ('cvt.s.d -2^-126(1-2^-25) RDN', 'sd', f64(-2.0 ** -126 * (1 - 2.0 ** -25)), RDN, 0xffffffff80800000, 0x01),
    ('cvt.s.d 2^-126(1-2^-25) RTZ', 'sd', f64(2.0 ** -126 * (1 - 2.0 ** -25)), RTZ, 0xffffffff007fffff, 0x03),
    # 2^-511(1+2^-27) * 2^-511(1-2^-27) = 2^-1022(1-2^-54): unbounded rounding ties to even 2^-1022 -> NX only.
    ('fmul.d 2^-1022(1-2^-54) RNE', 'mul', (f64(2.0 ** -511 * (1 + 2.0 ** -27)), f64(2.0 ** -511 * (1 - 2.0 ** -27))),
     RNE, 0x0010000000000000, 0x01),
    ('fmul.d 2^-1022(1-2^-54) RMM', 'mul', (f64(2.0 ** -511 * (1 + 2.0 ** -27)), f64(2.0 ** -511 * (1 - 2.0 ** -27))),
     RMM, 0x0010000000000000, 0x01),
    # 2^-511(1+2^-26) * 2^-511(1-2^-26) = 2^-1022(1-2^-52): exact as a subnormal -> no flags.
    ('fmul.d 2^-1022(1-2^-52) RNE', 'mul', (f64(2.0 ** -511 * (1 + 2.0 ** -26)), f64(2.0 ** -511 * (1 - 2.0 ** -26))),
     RNE, 0x000fffffffffffff, 0x00),
    ('fmadd.d 2^-1022(1-2^-54)+0 RNE', 'fma', (f64(2.0 ** -511 * (1 + 2.0 ** -27)), f64(2.0 ** -511 * (1 - 2.0 ** -27))),
     RNE, 0x0010000000000000, 0x01),
]


def case_tininess():
    p = Prog()
    for _, kind, value, rm, _, _ in TININESS:
        if kind == 'sd':
            p.fd(1, value)
            p.emit(fcvt_s_d(2, 1, rm))
        else:
            p.fd(1, value[0]); p.fd(3, value[1]); p.fd(4, 0)
            p.emit(fmul(D, 2, 1, 3, rm) if kind == 'mul' else r4(FMADD, D, 2, 1, 3, 4, rm))
        p.save_f(2)
        p.flags()
    return p.words()


def case_loop_dot():
    """Dependent FMA chain in a loop, with an FP compare steering a branch (rename/ROB exercise)."""
    p = Prog()
    p.emit(addi(27, 0, 24), addi(26, 28, 0))           # 24 iterations; x26 walks the constant table
    vals = [f32((k * 0.37) % 3.0 - 1.4) for k in range(48)]
    base = p.const(vals[0] | vals[1] << 32)
    for k in range(1, 24):
        p.const(vals[2 * k] | vals[2 * k + 1] << 32)
    assert base == 0
    p.fs(1, 0)                                         # f1 = acc (const offset 8*24 or reused zero)
    p.emit(fmv_f(S, 1, 0))
    p.fs(9, f32(0.5))
    loop = len(p.code)
    p.emit(flw(2, 26, 0), flw(3, 26, 4),
           r4(FMADD, S, 1, 2, 3, 1),                     # acc += a*b
           fcmp(S, 6, 9, 1, 1),                          # x6 = 0.5 < acc
           fcvt_to_int(S, 7, 1, 0, RTZ),
           r_type(0x33, 25, 0, 25, 6), r_type(0x33, 24, 0, 24, 7),
           addi(26, 26, 8), addi(27, 27, -1))
    p.emit(branch(1, 27, 0, 4 * (loop - len(p.code))))
    p.save_f(1); p.save_x(25); p.save_x(24)
    p.flags()
    return p.words()


# ---- Moller-Trumbore, single precision, same operation order as kernels/fpkern.c mt() ---------------
def mt_data():
    """16 ray/triangle pairs: o, d, a, b, c (15 floats each) as single-precision bit patterns."""
    tris = [((0, 0, 5), (1, 0, 5), (0, 1, 5)), ((-1, -1, 3), (2, -1, 4), (-1, 2, 3.5)),
            ((0.25, -2, 7), (3, 0.5, 6), (-0.75, 1.5, 8)), ((-3, -3, 10), (3, -3, 10), (0, 3, 10))]
    pairs, seed = [], 12345
    for r in range(4):
        vals = []
        for _ in range(6):
            seed = (seed * 1103515245 + 12345) & 0x7fffffff
            vals.append((seed / 2 ** 31 - 0.5) * 0.5)
        o, dd = (vals[0], vals[1], vals[2] * 0.5), (vals[3] * 0.25, vals[4] * 0.25, 1.0)
        for t in tris:
            pairs.append([f32(x) for x in (*o, *dd, *t[0], *t[1], *t[2])])
    pairs.append([f32(x) for x in (0, 0, 0, 1, 0, 0, 0, 0, 5, 1, 0, 5, 0, 1, 5)])   # parallel: det = 0
    pairs.append([f32(x) for x in (0.3, 0.3, 0, 0, 0, 1, 0, 0, 5, 1, 0, 5, 0, 1, 5)])
    return pairs


def case_ray_triangle():
    p = Prog()
    pairs = mt_data()
    # Data: 16 words (64 bytes) per pair from table offset 0.
    for pr in pairs:
        pr = pr + [0]
        for k in range(0, 16, 2):
            p.data.append(pr[k] | pr[k + 1] << 32)
    p.fs(30, f32(1e-8)); p.fs(31, f32(1e-6)); p.fs(29, S_ONE)
    p.emit(fmv_f(S, 28, 0))                               # f28 = +0.0
    p.emit(addi(27, 0, len(pairs)), addi(26, 28, 0), addi(25, 29, 0))
    loop = len(p.code)
    # f1-3 o, f4-6 d, f7-9 a, f10-12 b, f13-15 c
    p.emit(*[flw(1 + k, 26, 4 * k) for k in range(15)])
    sub = lambda rd, a, b: fsub(S, rd, a, b)
    mul = lambda rd, a, b: fmul(S, rd, a, b)
    add = lambda rd, a, b: fadd(S, rd, a, b)
    p.emit(sub(16, 10, 7), sub(17, 11, 8), sub(18, 12, 9),          # e1 = b - a
           sub(19, 13, 7), sub(20, 14, 8), sub(21, 15, 9))          # e2 = c - a
    # p = cross(d, e2) -> f22-24 (temporaries f25, f26)
    p.emit(mul(25, 5, 21), mul(26, 6, 20), sub(22, 25, 26),
           mul(25, 6, 19), mul(26, 4, 21), sub(23, 25, 26),
           mul(25, 4, 20), mul(26, 5, 19), sub(24, 25, 26))
    def dot(rd, ax, ay, az, bx, by, bz):
        return [mul(25, ax, bx), mul(26, ay, by), add(25, 25, 26), mul(26, az, bz), add(rd, 25, 26)]
    p.emit(*dot(27, 16, 17, 18, 22, 23, 24))                       # det -> f27
    p.emit(fdiv(S, 0, 29, 27))                                     # inv = 1 / det -> f0
    p.emit(sub(1, 1, 7), sub(2, 2, 8), sub(3, 3, 9))               # s = o - a (into f1-3)
    p.emit(*dot(7, 1, 2, 3, 22, 23, 24), mul(7, 7, 0))             # u -> f7
    # q = cross(s, e1) -> f10-12
    p.emit(mul(25, 2, 18), mul(26, 3, 17), sub(10, 25, 26),
           mul(25, 3, 16), mul(26, 1, 18), sub(11, 25, 26),
           mul(25, 1, 17), mul(26, 2, 16), sub(12, 25, 26))
    p.emit(*dot(8, 4, 5, 6, 10, 11, 12), mul(8, 8, 0))             # v -> f8
    p.emit(*dot(9, 19, 20, 21, 10, 11, 12), mul(9, 9, 0))          # t -> f9
    p.emit(fsgnj(S, 13, 27, 27, 2),                                # |det|
           fcmp(S, 5, 30, 13, 1), fcmp(S, 6, 28, 7, 0), r_type(0x33, 5, 7, 5, 6),
           fcmp(S, 6, 28, 8, 0), r_type(0x33, 5, 7, 5, 6),
           add(14, 7, 8), fcmp(S, 6, 14, 29, 0), r_type(0x33, 5, 7, 5, 6),
           fcmp(S, 6, 31, 9, 1), r_type(0x33, 5, 7, 5, 6))
    p.emit(fsw(9, 25, 0), fsw(7, 25, 4), fsw(8, 25, 8), sd(5, 25, 16))
    p.emit(addi(26, 26, 64), addi(25, 25, 24), addi(27, 27, -1))
    p.emit(branch(1, 27, 0, 4 * (loop - len(p.code))))
    p.flags()
    return p.words()


# Native AArch64 results for mt_data(): kernels/mt_native.c (fpkern.c's mt(), same operation order) built with
# Ubuntu clang 18.1.3 -O2 -ffp-contract=off -fno-math-errno, run on the WSL AArch64 host FPU on 2026-11-21
# (kernels/run_kernels.py). Per pair: t, u, v (single-precision bits) and the hit flag. The parallel-ray pair
# (det = 0) gives t = u = -inf and v = the canonical NaN, on the host as in the model.
MT_EXPECTED = [
    (0x409e99ae, 0xbe2a0716, 0xbdb2d727, 0),
    (0x405a5021, 0x3e9b4a66, 0x3e9b378b, 1),
    (0x40f006f0, 0x3b01e2b8, 0x3f0bebf9, 1),
    (0x411f4cd7, 0x3e4048f9, 0x3ef96eab, 1),
    (0x40a1f259, 0xbce84c70, 0x3e105392, 0),
    (0x4064a521, 0x3ea9d25e, 0x3eb86248, 1),
    (0x40f1539c, 0x3dbf0d45, 0x3f12ebba, 1),
    (0x4120f92d, 0x3e505922, 0x3f0eb224, 1),
    (0x409daec9, 0x3e4c284a, 0x3e838896, 1),
    (0x405fed91, 0x3ebdd327, 0x3ecd599a, 1),
    (0x40e71753, 0x3e6043ba, 0x3f035546, 1),
    (0x411ed765, 0x3e980dab, 0x3f12f9f2, 1),
    (0x40a20004, 0x3e18163a, 0x3e4c677c, 1),
    (0x40681a5f, 0x3ebdc4d6, 0x3ec61bd8, 1),
    (0x40ed1ca0, 0x3e32cfc8, 0x3f0598d0, 1),
    (0x41210002, 0x3e894376, 0x3f0e48cf, 1),
    (0xff800000, 0xff800000, 0x7fc00000, 0),
    (0x40a00000, 0x3e99999a, 0x3e99999a, 1),
]


def illegal_cases():
    one = [lui(28, DATA)]
    yield 'fp_illegal_rm5', one + [fadd(S, 1, 2, 3, 5), EBREAK]
    yield 'fp_illegal_rm6', one + [r4(FMADD, D, 1, 2, 3, 4, 6), EBREAK]
    yield 'fp_illegal_dyn_frm5', one + [csr(5, 0, FRM, 5), fop(0x18, S, 1, 2, 0, 0), fmul(D, 1, 2, 3, DYN), EBREAK]
    yield 'fp_illegal_dyn_frm7', one + [csr(5, 0, FRM, 7), fsgnj(S, 1, 2, 3), fcvt_d_s(1, 2, DYN), EBREAK]
    yield 'fp_illegal_fmt_h', one + [fadd(2, 1, 2, 3), EBREAK]
    yield 'fp_illegal_fmt_q', one + [r4(FMSUB, 3, 1, 2, 3, 4), EBREAK]
    yield 'fp_illegal_sqrt_rs2', one + [fop(0x0b, D, 1, 2, 1), EBREAK]
    yield 'fp_illegal_fcvt_rs2', one + [fcvt_to_int(S, 1, 2, 4), EBREAK]
    yield 'fp_illegal_fcvt_sd_rs2', one + [fop(8, S, 1, 2, 0), EBREAK]
    yield 'fp_illegal_fmv_f3', one + [fop(0x1c, S, 1, 2, 0, 2), EBREAK]
    yield 'fp_illegal_fmvwx_rs2', one + [fop(0x1e, D, 1, 2, 1, 0), EBREAK]
    yield 'fp_illegal_fmin_f3', one + [fop(5, D, 1, 2, 3, 2), EBREAK]
    yield 'fp_illegal_fcmp_f3', one + [fop(0x14, S, 1, 2, 3, 3), EBREAK]
    yield 'fp_illegal_funct5', one + [fop(0x07, S, 1, 2, 3, 0), EBREAK]
    yield 'fp_illegal_csr_mstatus', one + [csr(2, 5, 0x300, 0), EBREAK]
    yield 'fp_illegal_csr_cycle', one + [csr(2, 5, 0xc00, 0), EBREAK]
    yield 'fp_illegal_csr_f3_4', one + [i_type(0x73, 5, 4, 0, FCSR), EBREAK]
    yield 'fp_illegal_vector_load', one + [i_type(0x07, 1, 0, 28, 0), EBREAK]
    yield 'fp_illegal_fsh', one + [s_type(0x27, 1, 28, 1, 0), EBREAK]


def fault_cases():
    base = [lui(28, DATA), lui(29, OUT)]
    yield 'fp_fld_misaligned', base + [fld(1, 28, 4), EBREAK], 0, MASK
    yield 'fp_flw_misaligned', base + [flw(1, 28, 2), EBREAK], 0, MASK
    yield 'fp_fsd_misaligned', base + [fsd(1, 29, 4), EBREAK], 0, MASK
    yield 'fp_fsw_misaligned', base + [fsw(1, 29, 6), EBREAK], 0, MASK
    yield 'fp_fld_beyond_ram', base + [lui(27, 0x4000), fld(1, 27, 0), EBREAK], 0, MASK
    yield 'fp_flw_access_fault', base + [flw(1, 28, 0), flw(2, 28, 12), EBREAK], 2, DATA + 8
    yield 'fp_fsd_access_fault', base + [fsd(0, 29, 0), fsd(0, 29, 8), EBREAK], 3, OUT + 8
    yield 'fp_fsw_access_fault', base + [fsw(0, 29, 0), fsw(0, 29, 20), EBREAK], 3, OUT + 16


# ---- rounding-mode coverage (0.17.0 review, middle) -----------------------------------------------
# Every listed instruction under the five static modes and under DYN with frm = each of them, on inputs
# whose correct result depends on the mode: exact ties, values just above and below a tie, both signs,
# overflow and tiny results. Results come from the golden model (the trace comparison); fflags are read
# and stored after every mode.
RM_MODES = [(rm, None) for rm in (RNE, RTZ, RDN, RUP, RMM)] + [(DYN, frm) for frm in (RNE, RTZ, RDN, RUP, RMM)]


def _modes(p, body):
    for rm, frm in RM_MODES:
        if frm is not None:
            p.emit(csr(5, 0, FRM, frm))                               # fsrmi frm
        body(rm)
        p.flags()
    p.emit(csr(5, 0, FRM, RNE))


def _tie_inputs(fmt):
    """(a, b, small) with a*b exactly halfway between two representable values; small breaks the tie."""
    if fmt == S:
        return f32(1 + 2.0 ** -12), f32(1 + 2.0 ** -12), f32(2.0 ** -40)
    return f64(1 + 2.0 ** -26), f64(1 + 2.0 ** -27), f64(2.0 ** -80)


def case_rm_fma(fmt):
    p = Prog()
    a, b, t = _tie_inputs(fmt)
    neg, load = (NEG64, p.fd) if fmt == D else (NEG32, p.fs)
    load(1, a); load(2, b); load(10, a | neg)
    load(3, 0); load(4, t); load(5, t | neg)
    def body(rm):
        for fa in (1, 10):
            for fc in (3, 4, 5):
                for op in (FMADD, FMSUB, FNMSUB, FNMADD):
                    p.emit(r4(op, fmt, 6, fa, 2, fc, rm)); p.save_f(6)
    _modes(p, body)
    return p.words()


def case_rm_mul_div_sqrt():
    p = Prog()
    for fmt in (S, D):
        a, b, _ = _tie_inputs(fmt)
        v, load, big, neg = (f64, p.fd, D_MAX, NEG64) if fmt == D else (f32, p.fs, S_MAX, NEG32)
        base = 1 if fmt == S else 11
        load(base, a); load(base + 1, b); load(base + 2, a | neg); load(base + 3, big)
        load(base + 4, v(3.0)); load(base + 5, v(2.0)); load(base + 6, v(1.0)); load(base + 7, v(0.5))
        load(base + 8, v(2.0) | neg)
        def body(rm, fmt=fmt, r=base):
            p.emit(fmul(fmt, 21, r, r + 1, rm)); p.save_f(21)            # tie
            p.emit(fmul(fmt, 21, r + 2, r + 1, rm)); p.save_f(21)        # tie, negative
            p.emit(fmul(fmt, 21, r + 3, r + 5, rm)); p.save_f(21)        # overflow
            p.emit(fmul(fmt, 21, r + 3, r + 8, rm)); p.save_f(21)        # overflow, negative
            p.emit(fdiv(fmt, 21, r + 6, r + 4, rm)); p.save_f(21)        # 1/3
            p.emit(fdiv(fmt, 21, r + 5, r + 4, rm)); p.save_f(21)        # 2/3
            p.emit(fdiv(fmt, 21, r + 8, r + 4, rm)); p.save_f(21)        # -2/3
            p.emit(fdiv(fmt, 21, r + 3, r + 7, rm)); p.save_f(21)        # MAX / 0.5: overflow
            p.emit(fsqrt(fmt, 21, r + 5, rm)); p.save_f(21)              # sqrt 2
            p.emit(fsqrt(fmt, 21, r + 4, rm)); p.save_f(21)              # sqrt 3
            p.emit(fsqrt(fmt, 21, r, rm)); p.save_f(21)                  # sqrt of 1 + 2^-12 or 1 + 2^-26
        _modes(p, body)
    return p.words()


def case_rm_cvt_to_int(fmt):
    p = Prog()
    vals = [2.5, -2.5, -0.5, 1.5, 4294967295.5, -2147483648.5]
    for k, x in enumerate(vals):
        (p.fd if fmt == D else p.fs)(1 + k, f64(x) if fmt == D else f32(x))
    def body(rm):
        for k in range(len(vals)):
            for kind in range(4):
                p.emit(fcvt_to_int(fmt, 6, 1 + k, kind, rm)); p.save_x(6)
    _modes(p, body)
    return p.words()


RM_INTS = [(1 << 24) + 1, -((1 << 24) + 3), (1 << 53) + 1, 0x7fffffff, 0xffffffff, (1 << 63) + (1 << 39) + 1]


def case_rm_cvt_from_int(fmt):
    p = Prog()
    for k, value in enumerate(RM_INTS):
        p.x(14 + k, value & MASK)
    def body(rm):
        for k in range(len(RM_INTS)):
            for kind in range(4):
                p.emit(fcvt_from_int(fmt, 30, 14 + k, kind, rm)); p.save_f(30)
    _modes(p, body)
    return p.words()


def case_rm_cvt_ff():
    p = Prog()
    ds = [f64(1 + 2.0 ** -24), f64(1 + 2.0 ** -24 + 2.0 ** -40), f64(-(1 + 2.0 ** -24)), f64(1e300), f64(-1e300),
          f64(2.0 ** -150), f64(-(2.0 ** -150) * 1.5), f64(1 / 3)]
    for k, bits in enumerate(ds):
        p.fd(1 + k, bits)
    p.fs(20, f32(1 / 3)); p.fs(21, S_MINSUB | NEG32)
    def body(rm):
        for k in range(len(ds)):
            p.emit(fcvt_s_d(30, 1 + k, rm)); p.save_f(30)
        p.emit(fcvt_d_s(30, 20, rm)); p.save_f(30)
        p.emit(fcvt_d_s(30, 21, rm)); p.save_f(30)
    _modes(p, body)
    return p.words()


def rm_cases():
    yield 'fp_rm_fma_s', case_rm_fma(S), 0, MASK
    yield 'fp_rm_fma_d', case_rm_fma(D), 0, MASK
    yield 'fp_rm_mul_div_sqrt', case_rm_mul_div_sqrt(), 0, MASK
    yield 'fp_rm_cvt_to_int_s', case_rm_cvt_to_int(S), 0, MASK
    yield 'fp_rm_cvt_to_int_d', case_rm_cvt_to_int(D), 0, MASK
    yield 'fp_rm_cvt_from_int_s', case_rm_cvt_from_int(S), 0, MASK
    yield 'fp_rm_cvt_from_int_d', case_rm_cvt_from_int(D), 0, MASK
    yield 'fp_rm_cvt_ff', case_rm_cvt_ff(), 0, MASK


# ---- Codex review of 0.17.0, items 2-4 (FP ISA engineer) ------------------------------------------------
def case_rm_add_sub_d():
    """FADD.D / FSUB.D in all five static modes and DYN (each mode's first instruction directly after its
    fsrmi): ties, just above a tie, both signs, overflow and an exact zero."""
    p = Prog()
    p.fd(1, D_ONE); p.fd(2, f64(2.0 ** -53)); p.fd(3, f64(2.0 ** -53 + 2.0 ** -80)); p.fd(4, D_ONE | NEG64)
    p.fd(5, f64(2.0 ** -53) | NEG64); p.fd(6, f64(2.0 ** -54)); p.fd(7, D_MAX); p.fd(8, f64(3 * 2.0 ** -54))
    def body(rm):
        p.emit(fadd(D, 20, 1, 2, rm)); p.save_f(20)          # 1 + 2^-53: tie (RUP and RMM: 0x3ff0000000000001)
        p.emit(fadd(D, 20, 4, 5, rm)); p.save_f(20)          # -1 - 2^-53
        p.emit(fadd(D, 20, 1, 3, rm)); p.save_f(20)          # just above the tie
        p.emit(fsub(D, 20, 1, 5, rm)); p.save_f(20)          # 1 - (-2^-53)
        p.emit(fsub(D, 20, 1, 6, rm)); p.save_f(20)          # 1 - 2^-54: tie below 1
        p.emit(fsub(D, 20, 4, 8, rm)); p.save_f(20)          # -1 - 3*2^-54
        p.emit(fadd(D, 20, 7, 7, rm)); p.save_f(20)          # overflow
        p.emit(fsub(D, 20, 4, 7, rm)); p.save_f(20)          # -1 - MAX: -MAX or -inf by mode
        p.emit(fsub(D, 20, 1, 1, rm)); p.save_f(20)          # exact zero: -0 only in RDN
    _modes(p, body)
    return p.words()


# Expected first result of each mode of fp_rm_add_sub_d (static RNE RTZ RDN RUP RMM, then DYN with the same
# frm values): FADD.D(1, 2^-53), every one inexact. Ten stores (nine results, then fflags) per mode.
ADD_D_TIE = [0x3ff0000000000000, 0x3ff0000000000000, 0x3ff0000000000000, 0x3ff0000000000001,
             0x3ff0000000000001] * 2


def case_cvt_subnormal_first():
    """FLW of the smallest subnormal, then FCVT.W.S with RUP as the program's first FP arithmetic: 1 with NX.
    (rv_iss.c skipped its FPCR set-up on this path, so on a host left with flush-to-zero it returned 0
    without NX; test_cpu --fpu runs rv_iss with --host-fz 1 on AArch64 to keep that covered.)"""
    p = Prog()
    p.fs(1, S_MINSUB); p.fs(2, S_MINSUB | NEG32)
    p.emit(fcvt_to_int(S, 5, 1, 0, RUP)); p.save_x(5)
    p.flags()
    p.emit(fcvt_to_int(S, 6, 2, 2, RDN), fcvt_to_int(S, 7, 1, 3, RUP), fcvt_to_int(D, 8, 1, 0, RUP))
    p.save_x(6); p.save_x(7); p.save_x(8)
    p.flags()
    return p.words()


def _jal(rd, offset):
    offset &= (1 << 21) - 1
    return (offset >> 20) << 31 | ((offset >> 1) & 1023) << 21 | ((offset >> 11) & 1) << 20 | \
        ((offset >> 12) & 255) << 12 | rd << 7 | 0x6f


def _slow_zero(p, rd):
    """rd = 0, available only after four 63-step divides (a late branch condition or address)."""
    p.emit(r_type(0x33, rd, 4, 10, 11, 1), r_type(0x33, rd, 4, rd, 11, 1), r_type(0x33, rd, 4, rd, 11, 1),
           r_type(0x33, rd, 4, rd, 11, 1), i_type(0x13, rd, 7, rd, 0))


def _flag_setup(p):
    p.fd(1, D_ONE); p.fd(2, 0); p.fd(3, D_ONE | NEG64); p.fd(9, D_MAX)
    p.x(10, 0x7fffffffffffff00); p.x(11, 1)


def case_wrong_path_flags():
    """Wrong-path FP instructions must not leak flags. Eight cold forward branches resolve late (after slow
    divides) and are always taken; their fall-through holds FDIV.D 1/0 and FSQRT.D -1, which a not-taken
    prediction executes before the squash. Then a loop with a pseudo-random branch direction: one side divides
    by zero (DZ), the other takes the square root of -1 (NV); fflags is cleared before the branch and read after
    the join, so every stored value is exactly 0x08 or 0x10, and the first eight are 0."""
    p = Prog()
    _flag_setup(p)
    for _ in range(8):
        p.emit(csr(1, 0, FFLAGS, 0))                                   # fsflags x0
        _slow_zero(p, 6)
        p.emit(branch(0, 6, 0, 12), fdiv(D, 4, 1, 2), fsqrt(D, 5, 3))  # beq -> skip both (always taken)
        p.emit(csr(2, 7, FFLAGS, 0)); p.save_x(7)                      # frflags: must be 0
    p.x(12, 0x9e3779b97f4a7c15)
    p.emit(addi(20, 0, 24), addi(21, 29, 512))
    loop = len(p.code)
    p.emit(i_type(0x13, 13, 1, 12, 13), r_type(0x33, 12, 4, 12, 13),  # xorshift64 on x12
           i_type(0x13, 13, 5, 12, 7), r_type(0x33, 12, 4, 12, 13),
           i_type(0x13, 13, 1, 12, 17), r_type(0x33, 12, 4, 12, 13),
           csr(1, 0, FFLAGS, 0),
           r_type(0x33, 6, 4, 12, 11, 1), r_type(0x33, 6, 4, 6, 11, 1), r_type(0x33, 6, 4, 6, 11, 1),
           i_type(0x13, 6, 7, 6, 1),                                   # x6 = (x12 / 1 / 1 / 1) & 1, late
           branch(0, 6, 0, 12),                                         # beq -> B
           fdiv(D, 4, 1, 2), _jal(0, 8),                                # A: DZ, then j J
           fsqrt(D, 5, 3),                                              # B: NV
           csr(2, 7, FFLAGS, 0), sd(7, 21, 0), addi(21, 21, 8),         # J: frflags, store
           addi(20, 20, -1))
    p.emit(branch(1, 20, 0, 4 * (loop - len(p.code))))
    return p.words()


def case_trap_flag_order(kind):
    """A flagging divide retires before a faulting FP access whose address resolves late; an invalid square
    root and an overflowing multiply follow it and may execute first, but must not retire: at the halt
    fflags holds DZ only (test_cpu compares the core's final fcsr with the golden model's)."""
    p = Prog()
    _flag_setup(p)
    p.emit(csr(1, 0, FFLAGS, 0), fdiv(D, 4, 1, 2))                      # DZ: retires
    _slow_zero(p, 6)
    if kind == 'load':
        p.emit(lui(27, 0x4000), r_type(0x33, 6, 0, 6, 27), fld(5, 6, 0))       # beyond RAM: access fault (5)
    else:
        p.emit(addi(6, 6, 0x7fc), r_type(0x33, 6, 0, 6, 29), fsd(1, 6, 0))     # misaligned store (6)
    p.emit(fsqrt(D, 6, 3), fmul(D, 7, 9, 9), EBREAK)                    # NV, OF|NX: younger than the fault
    return p.words()


def review_cases():
    yield 'fp_rm_add_sub_d', case_rm_add_sub_d(), 0, MASK
    yield 'fp_cvt_subnormal_first', case_cvt_subnormal_first(), 0, MASK
    yield 'fp_wrong_path_flags', case_wrong_path_flags(), 0, MASK
    yield 'fp_trap_flag_order_load', case_trap_flag_order('load'), 0, MASK
    yield 'fp_trap_flag_order_store', case_trap_flag_order('store'), 0, MASK


def fp_cases():
    yield 'fp_move_box', case_move_box(), 0, MASK
    yield 'fp_lanes', case_lanes(), 0, MASK
    yield 'fp_arith_s', case_arith(S), 0, MASK
    yield 'fp_arith_d', case_arith(D), 0, MASK
    yield 'fp_fma_s', case_fma(S), 0, MASK
    yield 'fp_fma_d', case_fma(D), 0, MASK
    yield 'fp_rounding', case_rounding(), 0, MASK
    yield 'fp_csr', case_csr(), 0, MASK
    yield 'fp_compare_s', case_compare(S), 0, MASK
    yield 'fp_compare_d', case_compare(D), 0, MASK
    yield 'fp_convert_to_int', case_convert('to_int'), 0, MASK
    yield 'fp_convert_from_int', case_convert('from_int'), 0, MASK
    yield 'fp_convert_ff', case_convert('ff'), 0, MASK
    yield 'fp_tininess', case_tininess(), 0, MASK
    yield 'fp_loop_dot', case_loop_dot(), 0, MASK
    yield 'fp_ray_triangle', case_ray_triangle(), 0, MASK
    for name, words in illegal_cases():
        yield name, words, 0, MASK
    yield from fault_cases()
    yield from rm_cases()
    yield from review_cases()


FP_REQUIRED = set('''flw fld fsw fsd fadd.s fsub.s fmul.s fdiv.s fsqrt.s fadd.d fsub.d fmul.d fdiv.d fsqrt.d
fmadd.s fmsub.s fnmsub.s fnmadd.s fmadd.d fmsub.d fnmsub.d fnmadd.d fsgnj.s fsgnjn.s fsgnjx.s fsgnj.d fsgnjn.d
fsgnjx.d fmin.s fmax.s fmin.d fmax.d feq.s flt.s fle.s feq.d flt.d fle.d fclass.s fclass.d fmv.x.w fmv.w.x
fmv.x.d fmv.d.x fcvt.w.s fcvt.wu.s fcvt.l.s fcvt.lu.s fcvt.s.w fcvt.s.wu fcvt.s.l fcvt.s.lu fcvt.w.d fcvt.wu.d
fcvt.l.d fcvt.lu.d fcvt.d.w fcvt.d.wu fcvt.d.l fcvt.d.lu fcvt.s.d fcvt.d.s csrrw csrrs csrrc csrrwi csrrsi
csrrci'''.split())


def image_for(words):
    """test_cpu.image_for without its integer constants (which these programs do not use)."""
    image = bytearray(16384)
    assert len(words) * 4 < 8192
    for n, word in enumerate(words):
        image[4 * n:4 * n + 4] = word.to_bytes(4, 'little')
    return image


def stores(trace):
    """The W records' data words, in order."""
    return [int(line.split()[2], 16) for line in trace if line.startswith('W ')]


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from reference_fp import execute          # a separate candidate model, if present
    except ImportError:
        from reference import execute             # sim/cpu/reference.py
    covered, total = set(), 0
    for name, words, kind, address in fp_cases():
        state = {}
        trace, coverage = execute(image_for(words), kind, address, fp=True, state=state)
        covered |= coverage
        total += 1
        last = trace[-1]
        expect_trap = name.startswith(('fp_illegal', 'fp_trap')) or 'misaligned' in name or 'fault' in name \
            or 'beyond' in name
        cause = int(last.split()[2], 16) if last.startswith('T ') else None
        if expect_trap == (cause == 3):
            raise AssertionError(f'{name}: unexpected stop {last}')
        if name == 'fp_tininess':
            w = stores(trace)
            for k, (label, _, _, _, bits, flags) in enumerate(TININESS):
                if (w[2 * k], w[2 * k + 1]) != (bits, flags):
                    raise AssertionError(f'{label}: got {w[2 * k]:016x}/{w[2 * k + 1]:02x}, want {bits:016x}/{flags:02x}')
        if name == 'fp_ray_triangle' and MT_EXPECTED is not None:
            w = stores(trace)
            got = []
            for k in range(len(MT_EXPECTED)):     # four W records per pair: t, u (upper lane), v, hit
                t, u, v, hit = w[4 * k:4 * k + 4]
                got.append((t & 0xffffffff, u >> 32, v & 0xffffffff, hit))
            if got != [tuple(x) for x in MT_EXPECTED]:
                raise AssertionError('fp_ray_triangle differs from the native AArch64 results')
        if name == 'fp_rm_add_sub_d':
            w = stores(trace)
            got = [w[10 * k] for k in range(10)]
            if got != ADD_D_TIE or any(not w[10 * k + 9] & 1 for k in range(10)):
                raise AssertionError(f'fp_rm_add_sub_d: FADD.D(1, 2^-53) by mode {[hex(x) for x in got]}')
        if name == 'fp_cvt_subnormal_first' and stores(trace)[:2] != [1, 1]:
            raise AssertionError(f'fp_cvt_subnormal_first: {stores(trace)[:2]}, want 1 with NX')
        if name == 'fp_wrong_path_flags':
            w = stores(trace)
            if w[:8] != [0] * 8 or any(v not in (0x08, 0x10) for v in w[8:32]) or len(set(w[8:32])) != 2:
                raise AssertionError(f'fp_wrong_path_flags: {[hex(v) for v in w]}')
        if name.startswith('fp_trap_flag_order') and (state['fcsr'], cause) != (0x08, 5 if 'load' in name else 6):
            raise AssertionError(f'{name}: fcsr {state["fcsr"]:02x}, cause {cause}')
        print(f'{name}: {len(trace)} records, stop {last[:2]}{cause if cause is not None else ""}')
    missing = FP_REQUIRED - covered
    if missing:
        raise AssertionError(f'missing FP coverage: {sorted(missing)}')
    print(f'PASS: {total} FP cases on the golden model; {len(FP_REQUIRED)} FP instruction names covered'
          + ('' if MT_EXPECTED is not None else ' (MT_EXPECTED not yet filled)'))


if __name__ == '__main__':
    main()
