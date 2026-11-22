"""RISC-V F and D semantics with exact integer significand arithmetic (golden model core).

Every finite value is sign, integer significand m and exponent e (value = (-1)^s * m * 2^e). Operations
form the exact result (Python integers are unbounded; division and square root keep an exact
sticky remainder), and round_pack rounds it once, with the five RISC-V rounding modes, subnormals,
tininess after rounding, and the RISC-V canonical NaN. No host floating point is used anywhere.
Contract: cpu/architecture.md (RV64F and RV64D). reference.py imports it only when a run enables FP.
SPDX-License-Identifier: MIT
"""
from math import isqrt

NV, DZ, OF, UF, NX = 0x10, 0x08, 0x04, 0x02, 0x01
RNE, RTZ, RDN, RUP, RMM, DYN = 0, 1, 2, 3, 4, 7
BOX = 0xffffffff00000000


class Fmt:
    def __init__(self, name, p, ebits):
        self.name, self.p, self.ebits = name, p, ebits
        self.bias = (1 << (ebits - 1)) - 1
        self.emin, self.emax = 1 - self.bias, self.bias
        self.fbits = p - 1
        self.width = ebits + p
        self.mask = (1 << self.width) - 1
        self.qnan = ((1 << ebits) - 1) << self.fbits | 1 << (self.fbits - 1)   # canonical NaN
        self.inf = ((1 << ebits) - 1) << self.fbits
        self.maxfin = self.inf - 1


S = Fmt('s', 24, 8)
D = Fmt('d', 53, 11)


def unpack(bits, f):
    """('nan', signalling) | ('inf', sign) | ('zero', sign) | ('fin', sign, m, e)."""
    sign = bits >> (f.width - 1) & 1
    exp = bits >> f.fbits & ((1 << f.ebits) - 1)
    frac = bits & ((1 << f.fbits) - 1)
    if exp == (1 << f.ebits) - 1:
        if frac:
            return ('nan', not frac >> (f.fbits - 1) & 1)
        return ('inf', sign)
    if exp == 0:
        if frac == 0:
            return ('zero', sign)
        return ('fin', sign, frac, f.emin - f.fbits)
    return ('fin', sign, frac | 1 << f.fbits, exp - f.bias - f.fbits)


def pack(sign, biased, frac, f):
    return sign << (f.width - 1) | biased << f.fbits | frac


def zero(sign, f):
    return sign << (f.width - 1)


def inf(sign, f):
    return sign << (f.width - 1) | f.inf


def round_int(m, s, sticky, sign, rm):
    """Drop s >= 0 low bits of m (plus a sticky fraction below them) with mode rm.

    Returns (rounded integer, inexact). With sticky set, s must be >= 1."""
    if s <= 0:
        assert not sticky
        return m << -s, False
    q = m >> s
    rem = m & ((1 << s) - 1)
    half = 1 << (s - 1)
    inexact = bool(rem) or sticky
    if not inexact:
        return q, False
    above = rem > half or (rem == half and sticky)
    tie = rem == half and not sticky
    if rm == RNE:
        up = above or (tie and q & 1)
    elif rm == RTZ:
        up = False
    elif rm == RDN:
        up = bool(sign)
    elif rm == RUP:
        up = not sign
    elif rm == RMM:
        up = above or tie
    else:
        raise ValueError(rm)
    return q + up, True


def round_pack(sign, m, e, f, rm, sticky=False):
    """Round (-1)^sign * (m + sticky fraction) * 2^e, m > 0, to format f. Returns (bits, flags)."""
    nb = m.bit_length()
    assert m > 0 and (not sticky or nb >= f.p + 2)
    # Final grid: p significant bits, and never below the subnormal LSB 2^(emin - p + 1).
    s = max(nb - f.p, f.emin - f.fbits - e)
    q, inexact = round_int(m, s, sticky, sign, rm)
    if q.bit_length() > f.p:          # carry out of the significand: q == 2^p
        q >>= 1
        s += 1
    flags = NX if inexact else 0
    if q == 0:
        return zero(sign, f), flags | UF | NX
    E = q.bit_length() - 1 + e + s
    if E > f.emax:
        flags |= OF | NX
        if rm == RNE or rm == RMM or (rm == RUP and not sign) or (rm == RDN and sign):
            return inf(sign, f), flags
        return sign << (f.width - 1) | f.maxfin, flags
    if inexact:
        # Tininess after rounding: round to p bits with an unbounded exponent range.
        q1, _ = round_int(m, nb - f.p, sticky, sign, rm) if nb > f.p else (m, False)
        E1 = q1.bit_length() - 1 + e + max(nb - f.p, 0)
        if E1 < f.emin:
            flags |= UF
    if q.bit_length() == f.p:
        return pack(sign, E + f.bias, q - (1 << f.fbits), f), flags
    return pack(sign, 0, q, f), flags                  # subnormal


def is_snan(u):
    return u[0] == 'nan' and u[1]


def exact_zero_sign(rm):
    return 1 if rm == RDN else 0


def add_exact(sa, ma, ea, sb, mb, eb, f, rm):
    e = min(ea, eb)
    v = (-ma if sa else ma) << (ea - e)
    v += (-mb if sb else mb) << (eb - e)
    if v == 0:
        return zero(exact_zero_sign(rm), f), 0
    return round_pack(int(v < 0), abs(v), e, f, rm)


def f_add(a, b, f, rm, sub=False):
    ua, ub = unpack(a, f), unpack(b, f)
    if ua[0] == 'nan' or ub[0] == 'nan':
        return f.qnan, NV if is_snan(ua) or is_snan(ub) else 0
    sb_flip = 1 if sub else 0
    if ua[0] == 'inf' or ub[0] == 'inf':
        if ua[0] == 'inf' and ub[0] == 'inf':
            if ua[1] != ub[1] ^ sb_flip:
                return f.qnan, NV
            return inf(ua[1], f), 0
        return (inf(ua[1], f) if ua[0] == 'inf' else inf(ub[1] ^ sb_flip, f)), 0
    if ua[0] == 'zero' and ub[0] == 'zero':
        sa, sb = ua[1], ub[1] ^ sb_flip
        return zero(sa if sa == sb else exact_zero_sign(rm), f), 0
    if ub[0] == 'zero':
        return a, 0
    if ua[0] == 'zero':
        return b ^ (sb_flip << (f.width - 1)), 0
    return add_exact(ua[1], ua[2], ua[3], ub[1] ^ sb_flip, ub[2], ub[3], f, rm)


def f_mul(a, b, f, rm):
    ua, ub = unpack(a, f), unpack(b, f)
    if ua[0] == 'nan' or ub[0] == 'nan':
        return f.qnan, NV if is_snan(ua) or is_snan(ub) else 0
    sign = ua[1] ^ ub[1]
    if (ua[0] == 'inf' and ub[0] == 'zero') or (ua[0] == 'zero' and ub[0] == 'inf'):
        return f.qnan, NV
    if ua[0] == 'inf' or ub[0] == 'inf':
        return inf(sign, f), 0
    if ua[0] == 'zero' or ub[0] == 'zero':
        return zero(sign, f), 0
    return round_pack(sign, ua[2] * ub[2], ua[3] + ub[3], f, rm)


def f_div(a, b, f, rm):
    ua, ub = unpack(a, f), unpack(b, f)
    if ua[0] == 'nan' or ub[0] == 'nan':
        return f.qnan, NV if is_snan(ua) or is_snan(ub) else 0
    sign = ua[1] ^ ub[1]
    if ua[0] == 'inf':
        return (f.qnan, NV) if ub[0] == 'inf' else (inf(sign, f), 0)
    if ub[0] == 'inf':
        return zero(sign, f), 0
    if ub[0] == 'zero':
        return (f.qnan, NV) if ua[0] == 'zero' else (inf(sign, f), DZ)
    if ua[0] == 'zero':
        return zero(sign, f), 0
    ma, mb = ua[2], ub[2]
    k = max(0, f.p + 3 + mb.bit_length() - ma.bit_length())
    q, r = divmod(ma << k, mb)
    return round_pack(sign, q, ua[3] - ub[3] - k, f, rm, sticky=r != 0)


def f_sqrt(a, f, rm):
    ua = unpack(a, f)
    if ua[0] == 'nan':
        return f.qnan, NV if is_snan(ua) else 0
    if ua[0] == 'zero':
        return a, 0
    if ua[1]:
        return f.qnan, NV
    if ua[0] == 'inf':
        return a, 0
    m, e = ua[2], ua[3]
    if e & 1:
        m, e = m << 1, e - 1
    k = max(0, f.p + 3 - m.bit_length() // 2)
    m <<= 2 * k
    root = isqrt(m)
    return round_pack(0, root, (e - 2 * k) // 2, f, rm, sticky=root * root != m)


def f_fma(a, b, c, f, rm, neg_prod, neg_add):
    """(-1)^neg_prod * a * b + (-1)^neg_add * c, one rounding (FMADD/FMSUB/FNMSUB/FNMADD)."""
    ua, ub, uc = unpack(a, f), unpack(b, f), unpack(c, f)
    inf_zero = (ua[0] == 'inf' and ub[0] == 'zero') or (ua[0] == 'zero' and ub[0] == 'inf')
    if ua[0] == 'nan' or ub[0] == 'nan' or uc[0] == 'nan' or inf_zero:
        nv = is_snan(ua) or is_snan(ub) or is_snan(uc) or inf_zero
        return f.qnan, NV if nv else 0
    sp = ua[1] ^ ub[1] ^ neg_prod
    sc = uc[1] ^ neg_add
    if ua[0] == 'inf' or ub[0] == 'inf':
        if uc[0] == 'inf' and sc != sp:
            return f.qnan, NV
        return inf(sp, f), 0
    if uc[0] == 'inf':
        return inf(sc, f), 0
    prod_zero = ua[0] == 'zero' or ub[0] == 'zero'
    if prod_zero and uc[0] == 'zero':
        return zero(sp if sp == sc else exact_zero_sign(rm), f), 0
    if prod_zero:
        return zero(0, f) | (c & ((1 << (f.width - 1)) - 1)) | sc << (f.width - 1), 0
    mp, ep = ua[2] * ub[2], ua[3] + ub[3]
    if uc[0] == 'zero':
        return round_pack(sp, mp, ep, f, rm)
    return add_exact(sp, mp, ep, sc, uc[2], uc[3], f, rm)


def f_minmax(a, b, f, is_max):
    ua, ub = unpack(a, f), unpack(b, f)
    flags = NV if is_snan(ua) or is_snan(ub) else 0
    if ua[0] == 'nan' and ub[0] == 'nan':
        return f.qnan, flags
    if ua[0] == 'nan':
        return b, flags
    if ub[0] == 'nan':
        return a, flags
    lt = f_less(ua, ub) or (ua[0] == 'zero' and ub[0] == 'zero' and ua[1] > ub[1])
    if is_max:
        return (b if lt else a), flags
    return (a if lt else b), flags


def key(u):
    """Exact order key for a non-NaN unpacked value (a pair compared lexicographically)."""
    if u[0] == 'zero':
        return (0, 0)
    if u[0] == 'inf':
        return (-2 if u[1] else 2, 0)
    # Compare m * 2^e exactly: magnitude as a big integer at scale 2^-1200 (below every LSB).
    mag = u[2] << (u[3] + 1200)
    return (-1, -mag) if u[1] else (1, mag)


def f_less(ua, ub):
    return key(ua) < key(ub)


def f_compare(a, b, f, op):
    """op: 'eq', 'lt', 'le'. Returns (0/1, flags)."""
    ua, ub = unpack(a, f), unpack(b, f)
    if ua[0] == 'nan' or ub[0] == 'nan':
        if op == 'eq':
            return 0, NV if is_snan(ua) or is_snan(ub) else 0
        return 0, NV
    ka, kb = key(ua), key(ub)
    return int({'eq': ka == kb, 'lt': ka < kb, 'le': ka <= kb}[op]), 0


def f_class(a, f):
    u = unpack(a, f)
    if u[0] == 'nan':
        return 1 << 8 if u[1] else 1 << 9
    if u[0] == 'inf':
        return 1 << 0 if u[1] else 1 << 7
    if u[0] == 'zero':
        return 1 << 3 if u[1] else 1 << 4
    normal = a >> f.fbits & ((1 << f.ebits) - 1) != 0
    if u[1]:
        return 1 << 1 if normal else 1 << 2
    return 1 << 6 if normal else 1 << 5


def f_to_int(a, f, rm, bits, unsigned):
    """FCVT.W/WU/L/LU: returns (integer value in range, flags); caller sign-extends 32-bit results."""
    lo, hi = (0, (1 << bits) - 1) if unsigned else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)
    u = unpack(a, f)
    if u[0] == 'nan':
        return hi, NV
    if u[0] == 'inf':
        return (lo if u[1] else hi), NV
    if u[0] == 'zero':
        return 0, 0
    sign, m, e = u[1], u[2], u[3]
    q, inexact = round_int(m, -e, False, sign, rm) if e < 0 else (m << e, False)
    v = -q if sign else q
    if v < lo or v > hi:
        return (lo if sign else hi), NV
    return v, NX if inexact else 0


def int_to_f(v, f, rm):
    if v == 0:
        return 0, 0
    return round_pack(int(v < 0), abs(v), 0, f, rm)


def f_convert(a, src, dst, rm):
    """FCVT.S.D / FCVT.D.S."""
    u = unpack(a, src)
    if u[0] == 'nan':
        return dst.qnan, NV if u[1] else 0
    if u[0] == 'inf':
        return inf(u[1], dst), 0
    if u[0] == 'zero':
        return zero(u[1], dst), 0
    return round_pack(u[1], u[2], u[3], dst, rm)


# ---- Instruction level -------------------------------------------------------------------------

def read_s(reg):
    """Single-precision operand of a 64-bit f register: NaN-boxing check."""
    return reg & 0xffffffff if reg >> 32 == 0xffffffff else S.qnan


def fp_compute(ins, xa, fa, fb, fc, frm):
    """Execute one non-memory F/D instruction (OP-FP or an FMA opcode).

    xa is x[rs1]; fa, fb, fc are f[rs1], f[rs2], f[rs3] (64-bit raw); frm the current frm.
    Returns None for an illegal encoding (or an invalid rounding mode), else
    (name, is_float_destination, value64, flags)."""
    op, rd, f3 = ins & 127, (ins >> 7) & 31, (ins >> 12) & 7
    rs2, f7 = (ins >> 20) & 31, ins >> 25
    fmt = (ins >> 25) & 3
    if fmt > 1:
        return None
    f = D if fmt else S
    sfx = '.' + f.name
    rm = frm if f3 == DYN else f3
    rm_ok = rm <= 4
    if f is S:
        a, b, c = read_s(fa), read_s(fb), read_s(fc)
    else:
        a, b, c = fa, fb, fc

    def fres(value, flags, name):
        if f is S:
            value |= BOX
        return name, True, value, flags

    if op in (0x43, 0x47, 0x4b, 0x4f):
        if not rm_ok:
            return None
        neg_prod = op in (0x4b, 0x4f)
        neg_add = op in (0x47, 0x4f)
        value, flags = f_fma(a, b, c, f, rm, neg_prod, neg_add)
        name = {0x43: 'fmadd', 0x47: 'fmsub', 0x4b: 'fnmsub', 0x4f: 'fnmadd'}[op]
        return fres(value, flags, name + sfx)
    if op != 0x53:
        return None
    f5 = f7 >> 2
    if f5 in (0, 1, 2, 3):
        if not rm_ok:
            return None
        if f5 == 0:
            value, flags = f_add(a, b, f, rm)
        elif f5 == 1:
            value, flags = f_add(a, b, f, rm, sub=True)
        elif f5 == 2:
            value, flags = f_mul(a, b, f, rm)
        else:
            value, flags = f_div(a, b, f, rm)
        return fres(value, flags, ('fadd', 'fsub', 'fmul', 'fdiv')[f5] + sfx)
    if f5 == 0x0b:
        if rs2 != 0 or not rm_ok:
            return None
        value, flags = f_sqrt(a, f, rm)
        return fres(value, flags, 'fsqrt' + sfx)
    if f5 == 0x04:
        if f3 > 2:
            return None
        top = f.width - 1
        sb = b >> top & 1
        sa = a >> top & 1
        sign = (sb, sb ^ 1, sa ^ sb)[f3]
        value = (a & ~(1 << top)) | sign << top
        return fres(value, 0, ('fsgnj', 'fsgnjn', 'fsgnjx')[f3] + sfx)
    if f5 == 0x05:
        if f3 > 1:
            return None
        value, flags = f_minmax(a, b, f, f3 == 1)
        return fres(value, flags, ('fmin', 'fmax')[f3] + sfx)
    if f5 == 0x08:
        if not rm_ok:
            return None
        if f is S and rs2 == 1:
            value, flags = f_convert(fa, D, S, rm)
            return fres(value, flags, 'fcvt.s.d')
        if f is D and rs2 == 0:
            value, flags = f_convert(read_s(fa), S, D, rm)
            return fres(value, flags, 'fcvt.d.s')
        return None
    if f5 == 0x14:
        if f3 > 2:
            return None
        value, flags = f_compare(a, b, f, ('le', 'lt', 'eq')[f3])
        return ('fle', 'flt', 'feq')[f3] + sfx, False, value, flags
    if f5 == 0x1c:
        if rs2 != 0:
            return None
        if f3 == 1:
            return 'fclass' + sfx, False, f_class(a, f), 0
        if f3 == 0:
            if f is S:
                v = fa & 0xffffffff
                return 'fmv.x.w', False, (v | 0xffffffff00000000) if v >> 31 else v, 0
            return 'fmv.x.d', False, fa, 0
        return None
    if f5 == 0x1e:
        if rs2 != 0 or f3 != 0:
            return None
        if f is S:
            return 'fmv.w.x', True, (xa & 0xffffffff) | BOX, 0
        return 'fmv.d.x', True, xa & ((1 << 64) - 1), 0
    if f5 == 0x18:
        if rs2 > 3 or not rm_ok:
            return None
        bits = 32 if rs2 < 2 else 64
        v, flags = f_to_int(a, f, rm, bits, rs2 & 1)
        v &= (1 << bits) - 1
        if bits == 32 and v >> 31:
            v |= 0xffffffff00000000           # W and WU results sign-extend
        return 'fcvt.' + ('w', 'wu', 'l', 'lu')[rs2] + sfx, False, v, flags
    if f5 == 0x1a:
        if rs2 > 3 or not rm_ok:
            return None
        if rs2 == 0:
            v = xa & 0xffffffff
            v = v - (1 << 32) if v >> 31 else v
        elif rs2 == 1:
            v = xa & 0xffffffff
        elif rs2 == 2:
            v = xa - (1 << 64) if xa >> 63 else xa
        else:
            v = xa
        value, flags = int_to_f(v, f, rm)
        return fres(value, flags, 'fcvt' + sfx + '.' + ('w', 'wu', 'l', 'lu')[rs2])
    return None
