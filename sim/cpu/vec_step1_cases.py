"""RVV step 1 (simd, RV64_OOO_V): directed and random vector programs for test_cpu.py --vector.

Step 1 implements vsetvli/vsetivli/vsetvl, the vector CSRs, unit-stride and strided loads and stores (EEW 8-64,
masked, whole-register, mask, fault-only-first, element-precise faults) and the FP32 vector instructions of
RVV-CONTRACT.md; the integer, mask-logical, permute and indexed instructions are illegal in this step. So these
cases use only that subset: the contract's case_fp (vec_cases.py, its one integer copy replaced by vfsgnj.vv), the
contract's fault and illegal cases that need nothing else, directed memory/vstart/ff/element-fault cases, and
random programs whose chunks the golden model rejects (illegal, faulting) are dropped before use.
cases(vlen, n_random, seed) yields (name, words, fault_kind, fault_address); images use fp_cases.image_for.
SPDX-License-Identifier: MIT
"""
import random

import fp_cases as fc
import vec_cases as vc
import reference

MASK = (1 << 64) - 1
VLEN = 256
F6 = {k: getattr(vc, k) for k in dir(vc) if k.isupper() and isinstance(getattr(vc, k), int)}


def step1_case_fp():
    words = vc.case_fp(VLEN)
    copy = vc.opv(vc.VADD, vc.OPIVI, 6, 4, 0)
    return [vc.opv(vc.VFSGNJ, vc.OPFVV, 6, 4, 4) if w == copy else w for w in words]


def directed():
    yield 'v_fp_step1', step1_case_fp(), 0, MASK
    for name, words, kind, addr in vc.fault_cases():
        if name in ('v_load_beyond_ram', 'v_load_fault_elem0', 'v_store_misaligned_elem', 'v_store_access_fault'):
            yield name, words, kind, addr
    for name, words in vc.illegal_cases():
        yield name, words, 0, MASK
    # memory forms over the policies, LMUL and vstart
    p = vc.vprog()
    vc.fill_data(p, [0x0706050403020100 + 0x0808080808080808 * k for k in range(32)])
    for sew, width in ((vc.E8, vc.W8), (vc.E16, vc.W16), (vc.E32, vc.W32), (vc.E64, vc.W64)):
        for lmul in ((vc.M1, vc.M2, vc.MF2) if sew != vc.E64 else (vc.M1, vc.M2)):
            for ta, ma in ((1, 1), (0, 0)):
                p.emit(fc.addi(6, 0, 7), vc.vsetvli(7, 6, vc.vtypei(sew, lmul, ta, ma)))
                p.save_x(7)
                p.emit(vc.vlm(0, 27), vc.vle(width, 2, 27), vc.vle(width, 4, 27, vm=0), vc.vse(width, 4, 29))
                p.emit(fc.addi(5, 0, 3 * (1 << width if width else 1)), vc.vlse(width, 6, 27, 5), vc.vsse(width, 6, 29, 5, vm=0))
                p.emit(fc.addi(9, 29, 512))
    p.emit(vc.vlre(2, vc.W32, 8, 27), vc.vsr(2, 8, 29), vc.vsm(8, 29))
    p.emit(fc.addi(6, 0, 9), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)))
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 3), vc.vle(vc.W32, 10, 27), vc.vse(vc.W32, 10, 29))     # vstart 3
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 2), vc.vse(vc.W32, 10, 29))
    p.emit(fc.csr(2, 11, vc.CSR_VL, 0), fc.csr(2, 12, vc.CSR_VTYPE, 0), fc.csr(2, 13, vc.CSR_VLENB, 0), fc.csr(2, 14, vc.CSR_VSTART, 0))
    for r in (11, 12, 13, 14):
        p.save_x(r)
    yield 'v_mem_step1', p.words(), 0, MASK
    # fault-only-first truncation at a page-less boundary: the end of RAM
    p = vc.vprog()
    p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -12), fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)))
    p.emit(vc.vleff(vc.W32, 1, 8), fc.csr(2, 9, vc.CSR_VL, 0)); p.save_x(9)
    p.emit(vc.vse(vc.W32, 1, 29))
    yield 'v_ff_truncate', p.words(), 0, MASK
    # a load fault after some elements: completed elements, vstart, then the trap
    p = vc.vprog()
    p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -12), fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)))
    p.emit(vc.vle(vc.W32, 1, 8))
    yield 'v_load_fault_elem3', p.words(), 0, MASK
    p = vc.vprog()
    p.emit(fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)), vc.vle(vc.W32, 1, 27))
    p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -8), vc.vse(vc.W32, 1, 8))
    yield 'v_store_fault_elem2', p.words(), 0, MASK
    # --- review additions (coordinator, 01:4x) ---
    # vset* resets vstart; an FP op after vstart then vsetvli is legal
    p = vc.vprog()
    p.emit(fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)))
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 2), vc.vsetvli(7, 6, vc.vtypei(vc.E32, vc.M1)), vc.vle(vc.W32, 1, 27), vc.vse(vc.W32, 1, 29))
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 3), vc.vsetivli(0, 5, vc.vtypei(vc.E32, vc.M1)), vc.opv(vc.VFADD, vc.OPFVV, 2, 1, 1), vc.vse(vc.W32, 2, 29))
    p.emit(fc.csr(2, 9, vc.CSR_VSTART, 0)); p.save_x(9)
    yield 'v_vset_clears_vstart', p.words(), 0, MASK
    # masked-off elements at faulting addresses are not accessed
    p = vc.vprog()
    vc.fill_data(p, [0x3])                                           # mask bits: elements 0 and 1 active
    p.emit(fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)), vc.vlm(0, 27))
    p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -8), vc.vle(vc.W32, 1, 8, vm=0), vc.vse(vc.W32, 1, 29))   # elements 2..7 beyond RAM
    p.emit(fc.addi(5, 0, 6), vc.vsse(vc.W32, 1, 29, 5, vm=0))                                     # element 1 misaligned: active
    yield 'v_masked_off_faulting', p.words(), 0, MASK
    p = vc.vprog()
    vc.fill_data(p, [0x5])                                           # elements 0 and 2: element 1 (misaligned) inactive
    p.emit(fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)), vc.vlm(0, 27), vc.vle(vc.W32, 1, 27))
    p.emit(fc.addi(5, 0, 6), vc.vsse(vc.W32, 1, 29, 5, vm=0), fc.addi(7, 29, 64), vc.vlse(vc.W32, 2, 7, 5, vm=0))
    yield 'v_masked_off_misaligned', p.words(), 0, MASK
    # fault-only-first with vstart > 0: a fault above vstart truncates, also at vstart itself (index > 0)
    for vs, back in ((2, 16), (2, 8)):
        p = vc.vprog()
        p.emit(fc.addi(6, 0, 8), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)), vc.vle(vc.W32, 1, 27))
        p.emit(fc.lui(8, 0x4000), fc.addi(8, 8, -back), fc.csr(5, 0, vc.CSR_VSTART, vs), vc.vleff(vc.W32, 1, 8))
        p.emit(fc.csr(2, 9, vc.CSR_VL, 0)); p.save_x(9); p.emit(vc.vse(vc.W32, 1, 29))
        yield f'v_ff_vstart{vs}_back{back}', p.words(), 0, MASK
    # stores and loads with vstart >= vl: nothing accessed, vstart returns to 0
    p = vc.vprog()
    p.emit(fc.addi(6, 0, 4), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1)), vc.vle(vc.W32, 1, 27))
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 5), vc.vse(vc.W32, 1, 29), fc.csr(5, 0, vc.CSR_VSTART, 4), vc.vle(vc.W32, 1, 29))
    p.emit(fc.csr(5, 0, vc.CSR_VSTART, 6), vc.vsse(vc.W32, 1, 29, 6), vc.vse(vc.W32, 1, 29))
    yield 'v_vstart_ge_vl', p.words(), 0, MASK
    # FP at LMUL 4 and 8
    p = vc.vprog()
    vc.fill_data(p, [0x3f8000003f800000 + 0x0000100000001000 * k for k in range(64)])
    p.fs(1, fc.f32(1.5))
    for lm in (vc.M4, vc.M8):
        p.emit(vc.vsetvli(7, 0, vc.vtypei(vc.E32, lm, 1, 1))); p.save_x(7)
        p.emit(vc.vle(vc.W32, 8, 27), vc.vle(vc.W32, 16, 27), vc.opv(vc.VMFLT, vc.OPFVF, 0, 8, 1))
        p.emit(vc.opv(vc.VFADD, vc.OPFVV, 24, 8, 16), vc.opv(vc.VFMACC, vc.OPFVF, 24, 8, 1, vm=0),
               vc.opv(vc.VFREDUSUM, vc.OPFVV, 1, 24, 16), vc.opv(vc.VFREDOSUM, vc.OPFVV, 2, 24, 16, vm=0),
               vc.opv(vc.VFSLIDE1UP, vc.OPFVF, 16, 8, 1), vc.opv(vc.VMFLE, vc.OPFVV, 3, 16, 24))
        p.emit(vc.vse(vc.W32, 24, 29), vc.vse(vc.W32, 16, 29), vc.vsm(3, 29), vc.opv(vc.VWFUNARY0, vc.OPFVV, 9, 1, 0), fc.fsw(9, 29, 0),
               vc.opv(vc.VWFUNARY0, vc.OPFVV, 10, 2, 0), fc.fsw(10, 29, 8))   # reductions read out as scalars (v1, v2 misaligned for EMUL 4/8)
        p.flags()
    yield 'v_fp_lmul48', p.words(), 0, MASK


FP_OPS = [('VFADD', 'VF'), ('VFSUB', 'VF'), ('VFRSUB', 'F'), ('VFMUL', 'VF'), ('VFDIV', 'VF'), ('VFRDIV', 'F'),
          ('VFMIN', 'VF'), ('VFMAX', 'VF'), ('VFSGNJ', 'VF'), ('VFSGNJN', 'VF'), ('VFSGNJX', 'VF'),
          ('VFMADD', 'VF'), ('VFNMADD', 'VF'), ('VFMSUB', 'VF'), ('VFNMSUB', 'VF'),
          ('VFMACC', 'VF'), ('VFNMACC', 'VF'), ('VFMSAC', 'VF'), ('VFNMSAC', 'VF')]
CMP_OPS = [('VMFEQ', 'VF'), ('VMFLE', 'VF'), ('VMFLT', 'VF'), ('VMFNE', 'VF'), ('VMFGT', 'F'), ('VMFGE', 'F')]
SPECIAL = [fc.S_ONE, fc.f32(3.0), fc.f32(-0.5), fc.S_QNAN, fc.S_SNAN, fc.S_INF, fc.S_INF | fc.NEG32, 0, fc.NEG32,
           fc.S_MINSUB, fc.S_MINNORM, fc.S_MAX, fc.f32(1 / 3), fc.f32(2.5), fc.f32(-1e10), fc.f32(16777217.0)]


def rand_prog(rng):
    """Random step-1 program as chunks; chunks the golden model rejects (illegal, faults) are dropped."""
    p = vc.vprog()
    words = []
    for k in range(64):
        a = rng.choice(SPECIAL) if rng.random() < 0.3 else rng.getrandbits(32) & 0xbfffffff
        b = rng.choice(SPECIAL) if rng.random() < 0.3 else (0x3f800000 + rng.getrandbits(23)) ^ (rng.getrandbits(1) << 31)
        words.append(a | b << 32)
    vc.fill_data(p, words)
    for r in range(1, 8):
        p.fs(r, rng.choice(SPECIAL + [fc.f32(rng.uniform(-4, 4))]))
    p.fd(8, fc.D_ONE)                                   # f8 not boxed: canonical NaN in .vf
    p.emit(fc.addi(6, 0, rng.randint(1, 64)), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1, 1, 0)))   # M1: every register aligned
    for vd in (2, 4, 8, 16, 24):
        p.emit(vc.vle(vc.W32, vd, 27))
    p.emit(fc.addi(6, 0, rng.randint(1, 64)), vc.vsetvli(0, 6, vc.vtypei(vc.E32, rng.choice([vc.M1, vc.M2, vc.M4, vc.M8]), 1, 0)))
    chunks = []
    for _ in range(rng.randint(30, 60)):
        c0 = len(p.code)
        kind = rng.random()
        if kind < 0.10:
            lm = rng.choice([vc.M1, vc.M1, vc.M2, vc.M4, vc.M8, vc.MF2])
            sew = vc.E32 if rng.random() < 0.9 else rng.choice([vc.E8, vc.E16, vc.E64])
            p.emit(fc.addi(6, 0, rng.randint(0, 70)), vc.vsetvli(rng.choice([0, 7]), rng.choice([6, 6, 6, 0]),
                                                                  vc.vtypei(sew, lm, rng.getrandbits(1), rng.getrandbits(1))))
        elif kind < 0.25:
            vd = rng.choice([0, 2, 4, 8, 12, 16, 24])
            if rng.random() < 0.5:
                p.emit(fc.addi(5, 27, 4 * rng.randint(0, 40)), vc.vle(vc.W32, vd, 5, vm=rng.choice([1, 1, 0])))
            else:
                p.emit(fc.addi(5, 0, 4 * rng.randint(-2, 6)), vc.vlse(vc.W32, vd, 27, 5, vm=rng.choice([1, 1, 0])))
        elif kind < 0.32:
            p.emit(vc.vlm(0, 27) if rng.random() < 0.4 else vc.opv(vc.VMFLT, vc.OPFVF, 0, rng.choice([2, 4, 8]), rng.randint(1, 7)))
        elif kind < 0.52:
            name, forms = rng.choice(FP_OPS)
            form = rng.choice(forms)
            vd = rng.choice([2, 4, 6, 8, 10, 12, 16, 20, 24]); vs2 = rng.choice([2, 4, 8, 12, 16, 24])
            vs1 = rng.choice([2, 4, 8, 16]) if form == 'V' else rng.randint(1, 8)
            p.emit(vc.opv(F6[name], vc.OPFVV if form == 'V' else vc.OPFVF, vd, vs2, vs1, vm=rng.choice([1, 1, 0])))
        elif kind < 0.60:
            name, forms = rng.choice(CMP_OPS); form = rng.choice(forms)
            p.emit(vc.opv(F6[name], vc.OPFVV if form == 'V' else vc.OPFVF, rng.choice([0, 1, 3, 5, 9, 2, 4]), rng.choice([2, 4, 8]),
                          rng.choice([2, 4, 8]) if form == 'V' else rng.randint(1, 8), vm=rng.choice([1, 0])))
        elif kind < 0.67:
            f6 = rng.choice([vc.VFREDUSUM, vc.VFREDOSUM, vc.VFREDMIN, vc.VFREDMAX])
            p.emit(vc.opv(f6, vc.OPFVV, rng.choice([1, 3, 6]), rng.choice([2, 4, 8, 16]), rng.choice([2, 4]), vm=rng.choice([1, 0])))
        elif kind < 0.73:
            k = rng.choice([0, 1, 2, 3, 6, 7])
            p.emit(vc.opv(vc.VFUNARY0, vc.OPFVV, rng.choice([2, 4, 6, 8]), rng.choice([2, 4, 8]), k, vm=rng.choice([1, 0])))
            if rng.random() < 0.5:
                p.emit(vc.opv(vc.VFUNARY1, vc.OPFVV, rng.choice([2, 4, 6]), rng.choice([2, 4, 8]), rng.choice([0, 16]), vm=rng.choice([1, 0])))
        elif kind < 0.80:
            c = rng.random()
            if c < 0.3: p.emit(vc.opv(vc.VFMERGE, vc.OPFVF, rng.choice([2, 4, 6]), rng.choice([2, 4, 8]) if rng.random() < 0.7 else 0, rng.randint(1, 8), vm=rng.choice([0, 1])))
            elif c < 0.5: p.emit(vc.opv(vc.VFSLIDE1UP, vc.OPFVF, rng.choice([2, 6, 10, 12]), rng.choice([4, 8]), rng.randint(1, 8), vm=rng.choice([1, 0])))
            elif c < 0.7: p.emit(vc.opv(vc.VFSLIDE1DOWN, vc.OPFVF, rng.choice([2, 6, 10]), rng.choice([2, 4, 8]), rng.randint(1, 8), vm=rng.choice([1, 0])))
            elif c < 0.85: p.emit(vc.opv(vc.VWFUNARY0, vc.OPFVV, rng.randint(9, 15), rng.choice([2, 4, 8]), 0), fc.fsw(rng.randint(9, 15), 29, 8 * rng.randint(0, 100)))
            else: p.emit(vc.opv(vc.VWFUNARY0, vc.OPFVF, rng.choice([2, 4]), 0, rng.randint(1, 8)))
        elif kind < 0.90:
            vs = rng.choice([2, 4, 6, 8, 12, 16]); off = 4 * rng.randint(0, 300)
            if rng.random() < 0.7: p.emit(fc.addi(5, 29, off), vc.vse(vc.W32, vs, 5, vm=rng.choice([1, 1, 0])))
            else: p.emit(fc.addi(5, 0, 4 * rng.randint(-3, 5)), fc.addi(7, 29, 1024), vc.vsse(vc.W32, vs, 7, 5, vm=rng.choice([1, 0])))
        elif kind < 0.94:
            p.emit(fc.csr(5, 0, fc.FRM, rng.choice([0, 1, 2, 3, 4, 4, 0, 5])))
        elif kind < 0.97:
            p.emit(fc.csr(5, 0, vc.CSR_VSTART, rng.randint(1, 6)), rng.choice([vc.vle(vc.W32, rng.choice([2, 4, 8]), 27), vc.vse(vc.W32, rng.choice([2, 4, 8]), 29)]))
        else:
            p.flags()
            p.emit(fc.csr(2, 9, rng.choice([vc.CSR_VL, vc.CSR_VTYPE, vc.CSR_VLENB]), 0)); p.save_x(9)
        chunks.append((c0, len(p.code)))
    p.emit(fc.addi(6, 0, 64), vc.vsetvli(0, 6, vc.vtypei(vc.E32, vc.M1, 1, 0)))   # M1 for the final stores (aligned)
    for vs in (2, 4, 8, 16):
        p.emit(vc.vse(vc.W32, vs, 29), fc.addi(29, 29, 64))
    p.flags()
    code = list(p.code)
    drop = set()
    for _ in range(80):
        kept = [w for i, w in enumerate(code) if not any(a <= i < b for (a, b), k in zip(chunks, range(len(chunks))) if k in drop)]
        p.code = kept
        words = p.words()
        trace, _ = reference.execute(fc.image_for(words), 0, MASK, fp=True, vector=True, vlen=VLEN)
        t = trace[-1].split()
        if t[0] == 'T' and int(t[2], 16) == 3:
            break
        # map the trapping pc back to its chunk in the original code
        pc = int(t[1], 16) // 4
        orig = [i for i in range(len(code)) if not any(a <= i < b for (a, b), k in zip(chunks, range(len(chunks))) if k in drop)]
        if pc >= len(orig):
            break
        oi = orig[pc]
        hit = [k for k, (a, b) in enumerate(chunks) if a <= oi < b]
        if not hit:
            break
        drop.add(hit[0])
    return words


def rand_cases(n, seed):
    rng = random.Random(seed)
    for k in range(n):
        yield f'v_rand_{seed}_{k}', rand_prog(rng), 0, MASK


def cases(vlen=256, n_random=40, seed=1):
    global VLEN
    VLEN = vlen
    yield from directed()
    yield from rand_cases(n_random, seed)
