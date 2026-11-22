"""RVV 1.0 subset golden model (cpu/RVV-CONTRACT.md): a subset of the integer and FP32 vector instructions.

Vector state is a bytearray of 32 * VLENB bytes (element i of the group at register r with EEW e lives at byte
r*VLENB + i*e/8, little-endian), so groups run on into the following registers as the specification lays
them out. FP elements use fp_ref_core (the scalar F golden model) per element.
vstep() executes one instruction and returns ('na',) when it is not a vector instruction, ('illegal',),
('trap', cause, tval, records) or ('ok', name, destination, value, flags, records); records are the W, F, C
and V trace lines in contract order (the caller adds the R or T line).
SPDX-License-Identifier: MIT
"""
from fp_ref_core import (S, RTZ, f_add, f_mul, f_div, f_sqrt, f_fma, f_minmax, f_compare, f_class, f_to_int,
                         int_to_f, read_s, BOX)

MASK64 = (1 << 64) - 1
CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VL, CSR_VTYPE, CSR_VLENB = 0x008, 0x009, 0x00a, 0x00f, 0xc20, 0xc21, 0xc22
VECTOR_CSRS = (CSR_VSTART, CSR_VXSAT, CSR_VXRM, CSR_VCSR, CSR_VL, CSR_VTYPE, CSR_VLENB)


class Illegal(Exception):
    pass


class Fault(Exception):
    def __init__(self, cause, tval, index):
        super().__init__(cause)
        self.cause, self.tval, self.index = cause, tval, index


def sx(v, e):
    v &= (1 << e) - 1
    return v - (1 << e) if v >> (e - 1) else v


class VState:
    def __init__(self, vlen=256):
        assert vlen in (128, 256, 512)
        self.vlen, self.vlenb = vlen, vlen // 8
        self.v = bytearray(32 * self.vlenb)
        self.vl, self.vtype, self.vstart, self.vxsat, self.vxrm = 0, 1 << 63, 0, 0, 0

    # ---- vtype ----
    def config(self, vtype=None):
        """(sew, lmul_num, lmul_den, vlmax) or None for vill."""
        vt = self.vtype if vtype is None else vtype
        if vt >> 63 or vt >> 8 & ((1 << 55) - 1):
            return None
        vsew, vlmul = vt >> 3 & 7, vt & 7
        if vsew > 3 or vlmul == 4:
            return None
        sew = 8 << vsew
        num, den = (1 << vlmul, 1) if vlmul < 4 else (1, 1 << (8 - vlmul))
        if den > 1 and sew > 64 // den:
            return None
        return sew, num, den, num * self.vlen // (den * sew)

    # ---- CSRs ----
    def csr_read(self, n):
        return {CSR_VSTART: self.vstart, CSR_VXSAT: self.vxsat, CSR_VXRM: self.vxrm,
                CSR_VCSR: self.vxrm << 1 | self.vxsat, CSR_VL: self.vl, CSR_VTYPE: self.vtype,
                CSR_VLENB: self.vlenb}[n]

    def csr_write(self, n, value):
        """Returns the record, or raises Illegal for the read-only CSRs."""
        if n in (CSR_VL, CSR_VTYPE, CSR_VLENB):
            raise Illegal
        if n == CSR_VSTART:
            self.vstart = value & (self.vlen - 1)
        elif n == CSR_VXSAT:
            self.vxsat = value & 1
        elif n == CSR_VXRM:
            self.vxrm = value & 3
        else:
            self.vxsat, self.vxrm = value & 1, value >> 1 & 3
        return f'C {n:03x} {self.csr_read(n):016x}'

    # ---- elements ----
    def get(self, reg, i, eew):
        o = reg * self.vlenb + i * (eew // 8)
        return int.from_bytes(self.v[o:o + eew // 8], 'little')

    def put(self, reg, i, eew, value):
        o = reg * self.vlenb + i * (eew // 8)
        self.v[o:o + eew // 8] = (value & ((1 << eew) - 1)).to_bytes(eew // 8, 'little')

    def bit(self, reg, i):
        return self.v[reg * self.vlenb + i // 8] >> (i % 8) & 1

    def put_bit(self, reg, i, b):
        o = reg * self.vlenb + i // 8
        self.v[o] = (self.v[o] & ~(1 << (i % 8))) | (b & 1) << (i % 8)

    def record(self, reg):
        return f'V {reg:02x} ' + self.v[reg * self.vlenb:(reg + 1) * self.vlenb][::-1].hex()


def emul_regs(eew, sew, num, den):
    """Register count of a group with element width eew (at least 1), or Illegal if EMUL is out of range."""
    n, d = eew * num, sew * den              # EMUL = n / d
    if n * 8 < d or n > 8 * d:
        raise Illegal
    return max(1, n // d)


def check_group(base, regs):
    if base % regs or base + regs > 32:
        raise Illegal


def overlaps(a, b):
    return a[0] < b[0] + b[1] and b[0] < a[0] + a[1]


def check_overlap(dest, src, dest_eew, src_eew, src_frac=False):
    """Specification section 5.2 rules for one destination/source pair (groups are (base, regs))."""
    if not overlaps(dest, src):
        return
    if dest_eew == src_eew:
        return
    if dest_eew < src_eew:
        if dest[0] == src[0]:
            return
        raise Illegal
    if not src_frac and src[0] + src[1] == dest[0] + dest[1]:
        return
    raise Illegal


def vstep(ins, st, x, f, frm, memory, denied, fp_on):
    try:
        return _vstep(ins, st, x, f, frm, memory, denied, fp_on)
    except Illegal:
        return ('illegal',)


def _vstep(ins, st, x, f, frm, memory, denied, fp_on):
    op = ins & 127
    f3 = ins >> 12 & 7
    if op in (0x07, 0x27) and f3 in (0, 5, 6, 7):
        return vmem(ins, st, x, memory, denied)
    if op != 0x57:
        return ('na',)
    rd, rs1, vs2, vm = ins >> 7 & 31, ins >> 15 & 31, ins >> 20 & 31, ins >> 25 & 1
    funct6 = ins >> 26
    if f3 == 7:
        return vset(ins, st, x)
    cfg = st.config()
    if cfg is None and not (f3 == 3 and funct6 == 0x27):
        raise Illegal
    if st.vstart:
        raise Illegal
    if f3 == 3 and funct6 == 0x27:                       # vmv<n>r.v
        n = rs1 + 1
        if vm != 1 or n not in (1, 2, 4, 8):
            raise Illegal
        check_group(rd, n); check_group(vs2, n)
        b = st.vlenb
        st.v[rd * b:(rd + n) * b] = st.v[vs2 * b:(vs2 + n) * b]
        return ('ok', f'vmv{n}r.v', 0, 0, 0, [st.record(rd + k) for k in range(n)])
    sew, num, den, vlmax = cfg
    vl = st.vl
    e = sew
    em = (1 << e) - 1
    lm = max(1, num // den)                             # registers per LMUL group
    frac = den > 1
    if f3 in (1, 5):
        return vfp(ins, st, x, f, frm, cfg, fp_on)
    imm5 = rs1
    simm = sx(imm5, 5) & em
    if f3 == 0:
        scalar = None
    elif f3 == 3:
        scalar = simm
    elif f3 in (4, 6):
        scalar = x[rs1] & em
    else:
        scalar = None
    sel = 'I' if f3 in (0, 3, 4) else 'M'
    records = []

    def active(i):
        return vm or st.bit(0, i)

    def v_dest(compute, name, dest_eew=None, sources=(), no_overlap=False, keep_prefix=0, end=None, all_body=False):
        """Write a vector destination (EEW dest_eew, LMUL scaled) with policy; compute(i) gives element i."""
        de = dest_eew or e
        dregs = emul_regs(de, e, num, den)
        check_group(rd, dregs)
        if not vm and overlaps((rd, dregs), (0, 1)):
            raise Illegal
        for base, regs, seew, sfrac in sources:
            check_group(base, regs)
            if no_overlap and overlaps((rd, dregs), (base, regs)):
                raise Illegal
            check_overlap((rd, dregs), (base, regs), de, seew, sfrac)
        if no_overlap and not vm and overlaps((rd, dregs), (0, 1)):
            raise Illegal
        if st.vstart >= vl:
            return ('ok', name, 0, 0, 0, [])
        values = {}
        body_end = vl if end is None else end
        for i in range(max(st.vstart, keep_prefix), vl):
            if i < body_end and (all_body or active(i)):
                values[i] = compute(i)
        ones = (1 << de) - 1
        vma, vta = st.vtype >> 7 & 1, st.vtype >> 6 & 1
        for i in range(max(st.vstart, keep_prefix), vl):
            if i in values:
                st.put(rd, i, de, values[i])
            elif i >= body_end:
                if vta:
                    st.put(rd, i, de, ones)
            elif vma:
                st.put(rd, i, de, ones)
        tail_end = dregs * st.vlen // de
        if vta:
            for i in range(vl, tail_end):
                st.put(rd, i, de, ones)
        return ('ok', name, 0, 0, 0, [st.record(rd + k) for k in range(dregs)])

    def m_dest(compute, name, sources=(), no_overlap=False):
        """Mask destination: bits below vl from compute(i) (active) or policy; tail bits ones."""
        check_group(rd, 1)
        for base, regs, seew in sources:
            check_group(base, regs)
            if no_overlap and overlaps((rd, 1), (base, regs)):
                raise Illegal
            if regs > 1 and overlaps((rd, 1), (base, regs)) and rd != base:
                raise Illegal
        if no_overlap and not vm and rd == 0:
            raise Illegal
        if st.vstart >= vl:
            return ('ok', name, 0, 0, 0, [])
        vals = {i: compute(i) for i in range(st.vstart, vl) if active(i)}
        vma = st.vtype >> 7 & 1
        for i in range(st.vstart, vl):
            if i in vals:
                st.put_bit(rd, i, vals[i])
            elif vma:
                st.put_bit(rd, i, 1)
        for i in range(vl, st.vlen):
            st.put_bit(rd, i, 1)
        return ('ok', name, 0, 0, 0, [st.record(rd)])

    src2 = (vs2, lm, e, False)
    src1 = (rs1, lm, e, False)
    a = lambda i: st.get(vs2, i, e)
    if f3 in (0, 3, 4):
        if f3 == 0:
            b = lambda i: st.get(rs1, i, e)
            srcs = (src2, src1)
        else:
            b = lambda i: scalar
            srcs = (src2,)
        uimm_ok = f3 == 3
        sh = lambda i: (b(i) if f3 != 3 else imm5) & (e - 1)
        ops = {
            0x00: ('vadd', lambda i: a(i) + b(i), 'VXI'), 0x02: ('vsub', lambda i: a(i) - b(i), 'VX'),
            0x03: ('vrsub', lambda i: b(i) - a(i), 'XI'), 0x04: ('vminu', lambda i: min(a(i), b(i)), 'VX'),
            0x05: ('vmin', lambda i: min(sx(a(i), e), sx(b(i), e)), 'VX'),
            0x06: ('vmaxu', lambda i: max(a(i), b(i)), 'VX'),
            0x07: ('vmax', lambda i: max(sx(a(i), e), sx(b(i), e)), 'VX'),
            0x09: ('vand', lambda i: a(i) & b(i), 'VXI'), 0x0a: ('vor', lambda i: a(i) | b(i), 'VXI'),
            0x0b: ('vxor', lambda i: a(i) ^ b(i), 'VXI'),
            0x25: ('vsll', lambda i: a(i) << sh(i), 'VXI'), 0x28: ('vsrl', lambda i: a(i) >> sh(i), 'VXI'),
            0x29: ('vsra', lambda i: sx(a(i), e) >> sh(i), 'VXI'),
        }
        form = {0: 'V', 3: 'I', 4: 'X'}[f3]
        if funct6 in ops:
            name, fn, forms = ops[funct6]
            if form not in forms:
                raise Illegal
            return v_dest(lambda i: fn(i) & em, f'{name}.v{form.lower()}', sources=srcs)
        cmps = {0x18: ('vmseq', lambda p, q: p == q, False, 'VXI'), 0x19: ('vmsne', lambda p, q: p != q, False, 'VXI'),
                0x1a: ('vmsltu', lambda p, q: p < q, False, 'VX'), 0x1b: ('vmslt', lambda p, q: p < q, True, 'VX'),
                0x1c: ('vmsleu', lambda p, q: p <= q, False, 'VXI'), 0x1d: ('vmsle', lambda p, q: p <= q, True, 'VXI'),
                0x1e: ('vmsgtu', lambda p, q: p > q, False, 'XI'), 0x1f: ('vmsgt', lambda p, q: p > q, True, 'XI')}
        if funct6 in cmps:
            name, rel, signed, forms = cmps[funct6]
            if form not in forms:
                raise Illegal
            cv = (lambda v: sx(v, e)) if signed else (lambda v: v)
            return m_dest(lambda i: int(rel(cv(a(i)), cv(b(i)))), f'{name}.v{form.lower()}',
                          sources=[(s[0], s[1], s[2]) for s in srcs] + ([] if vm else [(0, 1, 1)]))
        if funct6 == 0x17:                               # vmerge / vmv.v
            if vm:
                if vs2 != 0:
                    raise Illegal
                srcs_m = (src1,) if f3 == 0 else ()
                return v_dest(lambda i: b(i), f'vmv.v.{form.lower()}', sources=srcs_m)
            return v_dest(lambda i: b(i) if st.bit(0, i) else a(i), f'vmerge.v{form.lower()}m', sources=srcs,
                          all_body=True)
        if funct6 == 0x0c:                               # vrgather
            idx = (lambda i: st.get(rs1, i, e)) if f3 == 0 else (lambda i: x[rs1] if f3 == 4 else imm5)
            return v_dest(lambda i: a(idx(i)) if idx(i) < vlmax else 0, f'vrgather.v{form.lower()}',
                          sources=srcs, no_overlap=True)
        if funct6 in (0x0e, 0x0f) and f3 != 0:           # slides
            off = x[rs1] if f3 == 4 else imm5
            if funct6 == 0x0e:
                return v_dest(lambda i: a(i - off), f'vslideup.v{form.lower()}', sources=(src2,), no_overlap=True,
                              keep_prefix=min(off, vl))
            return v_dest(lambda i: a(i + off) if i + off < vlmax else 0, f'vslidedown.v{form.lower()}',
                          sources=(src2,))
        raise Illegal
    # OPMVV (2) / OPMVX (6)
    if f3 == 2:
        b = lambda i: st.get(rs1, i, e)
        srcs = (src2, src1)
    else:
        b = lambda i: scalar
        srcs = (src2,)
    form = 'v' if f3 == 2 else 'x'
    if f3 == 2 and funct6 <= 0x07:                       # integer reductions
        name = ('vredsum', 'vredand', 'vredor', 'vredxor', 'vredminu', 'vredmin', 'vredmaxu', 'vredmax')[funct6]
        check_group(vs2, lm)
        if vl == 0:
            return ('ok', name + '.vs', 0, 0, 0, [])
        acc = st.get(rs1, 0, e)
        for i in range(vl):
            if active(i):
                v = a(i)
                acc = [lambda p, q: (p + q) & em, lambda p, q: p & q, lambda p, q: p | q, lambda p, q: p ^ q,
                       min, lambda p, q: min(sx(p, e), sx(q, e)) & em, max,
                       lambda p, q: max(sx(p, e), sx(q, e)) & em][funct6](acc, v)
        return reduction_write(st, rd, e, acc, name + '.vs')
    if funct6 == 0x10:
        if f3 == 2:
            if rs1 == 0:                                 # vmv.x.s
                if not vm:
                    raise Illegal
                return ('ok', 'vmv.x.s', rd, sx(st.get(vs2, 0, e), e) & MASK64, 0, [])
            if rs1 in (16, 17):                          # vcpop.m / vfirst.m
                bits = [i for i in range(vl) if active(i) and st.bit(vs2, i)]
                if rs1 == 16:
                    return ('ok', 'vcpop.m', rd, len(bits), 0, [])
                return ('ok', 'vfirst.m', rd, (bits[0] if bits else -1) & MASK64, 0, [])
            raise Illegal
        if vs2 != 0 or not vm:                           # vmv.s.x
            raise Illegal
        return scalar_move(st, rd, e, x[rs1], 'vmv.s.x')
    if funct6 == 0x12 and f3 == 2:                       # vzext / vsext
        if rs1 not in (2, 3, 4, 5, 6, 7):
            raise Illegal
        fac = {2: 8, 3: 8, 4: 4, 5: 4, 6: 2, 7: 2}[rs1]
        se = e // fac
        if se < 8:
            raise Illegal
        sregs = emul_regs(se, e, num, den)
        sfrac = se * num < e * den
        signed = rs1 & 1
        return v_dest(lambda i: (sx(st.get(vs2, i, se), se) if signed else st.get(vs2, i, se)) & em,
                      ('vsext' if signed else 'vzext') + f'.vf{fac}', sources=((vs2, sregs, se, sfrac),))
    if funct6 == 0x14 and f3 == 2:                       # VMUNARY0
        if rs1 == 17:                                    # vid.v
            if vs2 != 0:
                raise Illegal
            return v_dest(lambda i: i & em, 'vid.v')
        if rs1 == 16:                                    # viota.m
            def iota(i):
                return sum(1 for j in range(i) if active(j) and st.bit(vs2, j)) & em
            return v_dest(iota, 'viota.m', sources=((vs2, 1, 1, False),), no_overlap=True)
        if rs1 in (1, 2, 3):
            first = next((i for i in range(vl) if active(i) and st.bit(vs2, i)), None)
            fn = {1: lambda i: int(first is None or i < first), 2: lambda i: int(i == first),
                  3: lambda i: int(first is None or i <= first)}[rs1]
            return m_dest(fn, ('', 'vmsbf.m', 'vmsof.m', 'vmsif.m')[rs1], sources=[(vs2, 1, 1)], no_overlap=True)
        raise Illegal
    if funct6 == 0x17 and f3 == 2:                       # vcompress.vm
        if not vm:
            raise Illegal
        check_group(vs2, lm); check_group(rd, lm)
        if overlaps((rd, lm), (vs2, lm)) or overlaps((rd, lm), (rs1, 1)):
            raise Illegal
        if vl == 0:
            return ('ok', 'vcompress.vm', 0, 0, 0, [])
        picked = [a(i) for i in range(vl) if st.bit(rs1, i)]
        for k, v in enumerate(picked):
            st.put(rd, k, e, v)
        if st.vtype >> 6 & 1:
            for k in range(len(picked), lm * st.vlen // e):
                st.put(rd, k, e, em)
        return ('ok', 'vcompress.vm', 0, 0, 0, [st.record(rd + k) for k in range(lm)])
    if 0x18 <= funct6 <= 0x1f and f3 == 2:               # mask logical
        if not vm:
            raise Illegal
        fn = {0x18: lambda p, q: p & (q ^ 1), 0x19: lambda p, q: p & q, 0x1a: lambda p, q: p | q,
              0x1b: lambda p, q: p ^ q, 0x1c: lambda p, q: p | (q ^ 1), 0x1d: lambda p, q: (p & q) ^ 1,
              0x1e: lambda p, q: (p | q) ^ 1, 0x1f: lambda p, q: (p ^ q) ^ 1}[funct6]
        name = {0x18: 'vmandn', 0x19: 'vmand', 0x1a: 'vmor', 0x1b: 'vmxor', 0x1c: 'vmorn', 0x1d: 'vmnand',
                0x1e: 'vmnor', 0x1f: 'vmxnor'}[funct6]
        return m_dest(lambda i: fn(st.bit(vs2, i), st.bit(rs1, i)), name + '.mm')
    if funct6 in (0x0e, 0x0f) and f3 == 6:               # vslide1up / vslide1down
        s = x[rs1] & em
        if funct6 == 0x0e:
            return v_dest(lambda i: s if i == 0 else a(i - 1), 'vslide1up.vx', sources=(src2,), no_overlap=True)
        return v_dest(lambda i: s if i == vl - 1 else a(i + 1), 'vslide1down.vx', sources=(src2,))
    mul = {0x20: 'vdivu', 0x21: 'vdiv', 0x22: 'vremu', 0x23: 'vrem', 0x24: 'vmulhu', 0x25: 'vmul', 0x26: 'vmulhsu',
           0x27: 'vmulh'}
    if funct6 in mul:
        def mop(i):
            p, q = a(i), b(i)
            if funct6 == 0x25:
                return p * q
            if funct6 == 0x24:
                return (p * q) >> e
            if funct6 == 0x27:
                return (sx(p, e) * sx(q, e)) >> e
            if funct6 == 0x26:
                return (sx(p, e) * q) >> e
            signed = funct6 in (0x21, 0x23)
            pp, qq = (sx(p, e), sx(q, e)) if signed else (p, q)
            if qq == 0:
                quo, rem = -1, pp
            elif signed and pp == -(1 << (e - 1)) and qq == -1:
                quo, rem = pp, 0
            else:
                quo = abs(pp) // abs(qq)
                if (pp < 0) != (qq < 0):
                    quo = -quo
                rem = pp - quo * qq
            return quo if funct6 in (0x20, 0x21) else rem
        return v_dest(lambda i: mop(i) & em, mul[funct6] + f'.v{form}', sources=srcs)
    if funct6 in (0x29, 0x2b, 0x2d, 0x2f):               # vmadd vnmsub vmacc vnmsac
        d = lambda i: st.get(rd, i, e)
        fn = {0x29: lambda i: b(i) * d(i) + a(i), 0x2b: lambda i: -(b(i) * d(i)) + a(i),
              0x2d: lambda i: b(i) * a(i) + d(i), 0x2f: lambda i: -(b(i) * a(i)) + d(i)}[funct6]
        name = {0x29: 'vmadd', 0x2b: 'vnmsub', 0x2d: 'vmacc', 0x2f: 'vnmsac'}[funct6]
        return v_dest(lambda i: fn(i) & em, f'{name}.v{form}', sources=srcs)
    raise Illegal


def reduction_write(st, rd, e, value, name, flags=0):
    """vd[0] = value; elements 1.. of the one register are tail."""
    st.put(rd, 0, e, value)
    if st.vtype >> 6 & 1:
        for i in range(1, st.vlen // e):
            st.put(rd, i, e, (1 << e) - 1)
    return ('ok', name, 0, 0, flags, [st.record(rd)])


def scalar_move(st, rd, e, value, name):
    if st.vstart >= st.vl:
        return ('ok', name, 0, 0, 0, [])
    return reduction_write(st, rd, e, value & ((1 << e) - 1), name)


def vfp(ins, st, x, f, frm, cfg, fp_on):
    sew, num, den, vlmax = cfg
    f3, rd, rs1, vs2, vm, funct6 = ins >> 12 & 7, ins >> 7 & 31, ins >> 15 & 31, ins >> 20 & 31, ins >> 25 & 1, ins >> 26
    if not fp_on or sew != 32 or frm > 4:
        raise Illegal
    e, vl = 32, st.vl
    lm = max(1, num // den)
    flags = [0]
    vf = f3 == 5
    fs = read_s(f[rs1]) if vf else None
    a = lambda i: st.get(vs2, i, 32)
    b = (lambda i: fs) if vf else (lambda i: st.get(rs1, i, 32))
    srcs = ((vs2, lm),) if vf else ((vs2, lm), (rs1, lm))
    form = 'f' if vf else 'v'

    def active(i):
        return vm or st.bit(0, i)

    def fl(res):
        value, flg = res
        flags[0] |= flg
        return value

    def done(result):
        if result[0] == 'ok' and flags[0]:
            r = list(result)
            r[4] = flags[0]
            r[5] = [f'F {flags[0]:02x}'] + r[5]
            return tuple(r)
        return result

    def v_dest(compute, name, sources=srcs, no_overlap=False, keep_prefix=0, all_body=False):
        check_group(rd, lm)
        if not vm and rd == 0:
            raise Illegal
        for base, regs in sources:
            check_group(base, regs)
            if no_overlap and overlaps((rd, lm), (base, regs)):
                raise Illegal
        if st.vstart >= vl:
            return ('ok', name, 0, 0, 0, [])
        vals = {}
        for i in range(max(st.vstart, keep_prefix), vl):
            if all_body or active(i):
                vals[i] = compute(i)
        vma, vta = st.vtype >> 7 & 1, st.vtype >> 6 & 1
        for i in range(max(st.vstart, keep_prefix), vl):
            if i in vals:
                st.put(rd, i, 32, vals[i])
            elif vma:
                st.put(rd, i, 32, 0xffffffff)
        if vta:
            for i in range(vl, lm * st.vlen // 32):
                st.put(rd, i, 32, 0xffffffff)
        return done(('ok', name, 0, 0, 0, [st.record(rd + k) for k in range(lm)]))

    def m_dest(compute, name):
        check_group(rd, 1)
        for base, regs in srcs:
            check_group(base, regs)
            if regs > 1 and overlaps((rd, 1), (base, regs)) and rd != base:
                raise Illegal
        if st.vstart >= vl:
            return ('ok', name, 0, 0, 0, [])
        vals = {i: compute(i) for i in range(st.vstart, vl) if active(i)}
        vma = st.vtype >> 7 & 1
        for i in range(st.vstart, vl):
            if i in vals:
                st.put_bit(rd, i, vals[i])
            elif vma:
                st.put_bit(rd, i, 1)
        for i in range(vl, st.vlen):
            st.put_bit(rd, i, 1)
        return done(('ok', name, 0, 0, 0, [st.record(rd)]))

    arith = {0x00: ('vfadd', lambda i: fl(f_add(a(i), b(i), S, frm)), 'VF'),
             0x02: ('vfsub', lambda i: fl(f_add(a(i), b(i), S, frm, sub=True)), 'VF'),
             0x27: ('vfrsub', lambda i: fl(f_add(b(i), a(i), S, frm, sub=True)), 'F'),
             0x24: ('vfmul', lambda i: fl(f_mul(a(i), b(i), S, frm)), 'VF'),
             0x20: ('vfdiv', lambda i: fl(f_div(a(i), b(i), S, frm)), 'VF'),
             0x21: ('vfrdiv', lambda i: fl(f_div(b(i), a(i), S, frm)), 'F'),
             0x04: ('vfmin', lambda i: fl(f_minmax(a(i), b(i), S, False)), 'VF'),
             0x06: ('vfmax', lambda i: fl(f_minmax(a(i), b(i), S, True)), 'VF'),
             0x08: ('vfsgnj', lambda i: (a(i) & 0x7fffffff) | (b(i) & 0x80000000), 'VF'),
             0x09: ('vfsgnjn', lambda i: (a(i) & 0x7fffffff) | (~b(i) & 0x80000000), 'VF'),
             0x0a: ('vfsgnjx', lambda i: a(i) ^ (b(i) & 0x80000000), 'VF')}
    if funct6 in arith:
        name, fn, forms = arith[funct6]
        if form.upper() not in forms:
            raise Illegal
        return v_dest(fn, f'{name}.v{form}')
    if 0x28 <= funct6 <= 0x2f:                            # FMA
        d = lambda i: st.get(rd, i, 32)
        np_, nc = {0x28: (0, 0), 0x29: (1, 1), 0x2a: (0, 1), 0x2b: (1, 0),
                   0x2c: (0, 0), 0x2d: (1, 1), 0x2e: (0, 1), 0x2f: (1, 0)}[funct6]
        if funct6 < 0x2c:                                 # vfmadd family: vs1 * vd + vs2
            fn = lambda i: fl(f_fma(b(i), d(i), a(i), S, frm, np_, nc))
        else:                                             # vfmacc family: vs1 * vs2 + vd
            fn = lambda i: fl(f_fma(b(i), a(i), d(i), S, frm, np_, nc))
        name = ('vfmadd', 'vfnmadd', 'vfmsub', 'vfnmsub', 'vfmacc', 'vfnmacc', 'vfmsac', 'vfnmsac')[funct6 - 0x28]
        return v_dest(fn, f'{name}.v{form}')
    cmps = {0x18: ('vmfeq', lambda p, q: f_compare(p, q, S, 'eq'), 'VF'),
            0x19: ('vmfle', lambda p, q: f_compare(p, q, S, 'le'), 'VF'),
            0x1b: ('vmflt', lambda p, q: f_compare(p, q, S, 'lt'), 'VF'),
            0x1c: ('vmfne', lambda p, q: (1 - f_compare(p, q, S, 'eq')[0], f_compare(p, q, S, 'eq')[1]), 'VF'),
            0x1d: ('vmfgt', lambda p, q: f_compare(q, p, S, 'lt'), 'F'),
            0x1f: ('vmfge', lambda p, q: f_compare(q, p, S, 'le'), 'F')}
    if funct6 in cmps:
        name, fn, forms = cmps[funct6]
        if form.upper() not in forms:
            raise Illegal
        return m_dest(lambda i: fl(fn(a(i), b(i))), f'{name}.v{form}')
    if funct6 == 0x17:                                    # vfmerge.vfm / vfmv.v.f
        if not vf:
            raise Illegal
        if vm:
            if vs2 != 0:
                raise Illegal
            return v_dest(lambda i: fs, 'vfmv.v.f', sources=())
        return v_dest(lambda i: fs if st.bit(0, i) else a(i), 'vfmerge.vfm', sources=((vs2, lm),), all_body=True)
    if funct6 == 0x10:
        if not vf:                                        # vfmv.f.s
            if rs1 != 0 or not vm:
                raise Illegal
            return ('ok', 'vfmv.f.s', 32 + rd, st.get(vs2, 0, 32) | BOX, 0, [])
        if vs2 != 0 or not vm:                            # vfmv.s.f
            raise Illegal
        return scalar_move(st, rd, 32, fs, 'vfmv.s.f')
    if funct6 == 0x12 and not vf:                         # VFUNARY0 conversions
        kinds = {0: ('vfcvt.xu.f.v', lambda i: fl(f_to_int(a(i), S, frm, 32, 1))),
                 1: ('vfcvt.x.f.v', lambda i: fl(f_to_int(a(i), S, frm, 32, 0)) & 0xffffffff),
                 2: ('vfcvt.f.xu.v', lambda i: fl(int_to_f(a(i), S, frm))),
                 3: ('vfcvt.f.x.v', lambda i: fl(int_to_f(sx(a(i), 32), S, frm))),
                 6: ('vfcvt.rtz.xu.f.v', lambda i: fl(f_to_int(a(i), S, RTZ, 32, 1))),
                 7: ('vfcvt.rtz.x.f.v', lambda i: fl(f_to_int(a(i), S, RTZ, 32, 0)) & 0xffffffff)}
        if rs1 not in kinds:
            raise Illegal
        name, fn = kinds[rs1]
        return v_dest(fn, name, sources=((vs2, lm),))
    if funct6 == 0x13 and not vf:                         # VFUNARY1
        if rs1 == 0:
            return v_dest(lambda i: fl(f_sqrt(a(i), S, frm)), 'vfsqrt.v', sources=((vs2, lm),))
        if rs1 == 16:
            return v_dest(lambda i: f_class(a(i), S), 'vfclass.v', sources=((vs2, lm),))
        raise Illegal
    if funct6 in (0x0e, 0x0f) and vf:                     # vfslide1up / vfslide1down
        if funct6 == 0x0e:
            return v_dest(lambda i: fs if i == 0 else a(i - 1), 'vfslide1up.vf', sources=((vs2, lm),),
                          no_overlap=True)
        return v_dest(lambda i: fs if i == vl - 1 else a(i + 1), 'vfslide1down.vf', sources=((vs2, lm),))
    if funct6 in (0x01, 0x03, 0x05, 0x07) and not vf:     # FP reductions
        name = {0x01: 'vfredusum', 0x03: 'vfredosum', 0x05: 'vfredmin', 0x07: 'vfredmax'}[funct6] + '.vs'
        check_group(vs2, lm)
        if vl == 0:
            return ('ok', name, 0, 0, 0, [])
        acc = st.get(rs1, 0, 32)
        act = [i for i in range(vl) if active(i)]
        if not act:
            return reduction_write(st, rd, 32, acc, name)
        if funct6 == 0x03:
            for i in act:
                acc = fl(f_add(acc, a(i), S, frm))
        elif funct6 == 0x01:
            def tree(lo, n):
                if n == 1:
                    return a(lo) if lo < vl and active(lo) else None
                left, right = tree(lo, n // 2), tree(lo + n // 2, n // 2)
                if left is None:
                    return right
                if right is None:
                    return left
                return fl(f_add(left, right, S, frm))
            n = 1
            while n < vl:
                n *= 2
            acc = fl(f_add(acc, tree(0, n), S, frm))
        else:
            for i in act:
                acc = fl(f_minmax(acc, a(i), S, funct6 == 0x07))
        return done(reduction_write(st, rd, 32, acc, name))
    raise Illegal


def vset(ins, st, x):
    rd, rs1 = ins >> 7 & 31, ins >> 15 & 31
    if ins >> 31 == 0:
        vtype, avl_src, name = ins >> 20 & 0x7ff, 'rs1', 'vsetvli'
    elif ins >> 30 == 3:
        vtype, avl_src, name = ins >> 20 & 0x3ff, 'imm', 'vsetivli'
    elif (ins >> 25) & 0x3f == 0:
        vtype, avl_src, name = x[ins >> 20 & 31], 'rs1', 'vsetvl'
    else:
        raise Illegal
    old = st.config()
    cfg = st.config(vtype)
    keep = avl_src == 'rs1' and rs1 == 0 and rd == 0
    if cfg is None or (keep and (old is None or old[3] != cfg[3])):
        st.vtype, st.vl = 1 << 63, 0
    else:
        vlmax = cfg[3]
        if avl_src == 'imm':
            avl = rs1
        elif rs1 != 0:
            avl = x[rs1]
        elif rd != 0:
            avl = MASK64
        else:
            avl = st.vl
        st.vtype, st.vl = vtype & MASK64, min(avl, vlmax)
    records = [f'C c20 {st.vl:016x}', f'C c21 {st.vtype:016x}']
    if st.vstart:                                    # every vector instruction ends with vstart = 0 (RVV 1.0 3.7)
        st.vstart = 0
        records.append('C 008 0000000000000000')
    return ('ok', name, rd, st.vl, 0, records)


def vmem(ins, st, x, memory, denied):
    load = (ins & 127) == 0x07
    width = ins >> 12 & 7
    eew = {0: 8, 5: 16, 6: 32, 7: 64}[width]
    nf, mew, mop, vm = ins >> 29, ins >> 28 & 1, ins >> 26 & 3, ins >> 25 & 1
    lumop, rs1, vd = ins >> 20 & 31, ins >> 15 & 31, ins >> 7 & 31
    if mew:
        raise Illegal
    base = x[rs1]
    records = []
    whole = mop == 0 and lumop == 8
    if whole:
        n = nf + 1
        if n not in (1, 2, 4, 8) or not vm or (not load and width != 0):
            raise Illegal
        check_group(vd, n)
        evl = n * st.vlen // eew
        regs, data_eew, name = n, eew, (f'vl{n}re{eew}.v' if load else f'vs{n}r.v')
        addr = lambda i: base + i * (eew // 8)
        act = lambda i: True
        tail = False
    else:
        if nf:
            raise Illegal
        cfg = st.config()
        if cfg is None:
            raise Illegal
        sew, num, den, vlmax = cfg
        if mop == 0 and lumop == 11:                     # vlm / vsm
            if width != 0 or not vm:
                raise Illegal
            evl, regs, data_eew = (st.vl + 7) // 8, 1, 8
            name = 'vlm.v' if load else 'vsm.v'
            addr = lambda i: base + i
            act = lambda i: True
            tail = 'mask'
        else:
            if mop == 0 and lumop not in (0, 16) or (mop == 0 and lumop == 16 and not load):
                raise Illegal
            if mop in (1, 3):
                data_eew = sew
                regs = emul_regs(sew, sew, num, den)
                iregs = emul_regs(eew, sew, num, den)
                ifrac = eew * num < sew * den
                vs2 = lumop
                check_group(vs2, iregs)
                if load:
                    check_group(vd, regs)
                    check_overlap((vd, regs), (vs2, iregs), sew, eew, ifrac)
                addr = lambda i: base + st.get(vs2, i, eew)
                name = ('vluxei' if mop == 1 else 'vloxei') if load else ('vsuxei' if mop == 1 else 'vsoxei')
                name += f'{eew}.v'
            else:
                data_eew = eew
                regs = emul_regs(eew, sew, num, den)
                if mop == 2:
                    stride = x[lumop]
                    stride = stride - (1 << 64) if stride >> 63 else stride
                    addr = lambda i: base + i * stride
                    name = f'vlse{eew}.v' if load else f'vsse{eew}.v'
                else:
                    addr = lambda i: base + i * (eew // 8)
                    name = (f'vle{eew}ff.v' if lumop == 16 else f'vle{eew}.v') if load else f'vse{eew}.v'
            check_group(vd, regs)
            if load and not vm and vd == 0:
                raise Illegal
            evl = st.vl
            act = (lambda i: True) if vm else (lambda i: st.bit(0, i))
            tail = True
    ff = load and not whole and mop == 0 and lumop == 16
    size = data_eew // 8
    start = st.vstart
    loaded = {}
    fault = None
    for i in range(start, evl):
        if not act(i):
            continue
        a = addr(i) & MASK64
        if a % size:
            fault = (4 if load else 6, a, i)
        elif denied(a, 2 if load else 3):
            fault = (5 if load else 7, a, i)
        if fault:
            break
        if load:
            loaded[i] = int.from_bytes(memory[a:a + size], 'little')
        else:
            v = st.get(vd, i, data_eew)
            memory[a:a + size] = v.to_bytes(size, 'little')
            lane = a & 7
            records.append(f'W {a & ~7:016x} {(v << (8 * lane)) & MASK64:016x} {((1 << size) - 1) << lane:02x}')
    if fault and not (ff and fault[2] > 0):
        cause, tval, i = fault
        for k, v in loaded.items():
            st.put(vd, k, data_eew, v)
        if load and i > start:
            records += [st.record(vd + r) for r in range(regs)]
        if i:
            st.vstart = i
            records.append(f'C 008 {i:016x}')
        return ('trap', cause, tval, records)
    if fault:                                            # fault-only-first truncation
        st.vl = evl = fault[2]
        records.append(f'C c20 {st.vl:016x}')
    if start:
        records.append('C 008 0000000000000000')
    st.vstart = 0
    if not load:
        return ('ok', name, 0, 0, 0, records)
    if start >= evl and not whole:
        return ('ok', name, 0, 0, 0, records)
    vma = st.vtype >> 7 & 1
    vta = st.vtype >> 6 & 1
    ones = (1 << data_eew) - 1
    for i in range(start, evl):
        if i in loaded:
            st.put(vd, i, data_eew, loaded[i])
        elif vma and not whole:
            st.put(vd, i, data_eew, ones)
    if tail == 'mask':
        for i in range(evl, st.vlenb):
            st.put(vd, i, 8, 0xff)
    elif tail and vta:
        for i in range(evl, regs * st.vlen // data_eew):
            st.put(vd, i, data_eew, ones)
    return ('ok', name, 0, 0, 0, records + [st.record(vd + r) for r in range(regs)])
