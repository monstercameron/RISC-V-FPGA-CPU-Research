"""Front-end directed cases (frontend engineer, 2026-11-22): instruction-cache ways and the
indirect-target predictor. Plain RV64I programs (traces checked against the golden model as
usual); with the matching knob, timing checks on the stall-0 'cycles=' (test_cpu.py layout).
Usage inside test_cpu.py:
    import fe_cases as FE
    cases():  yield from FE.cases(globals())
    after the run loop:  FE.check(records, args)
SPDX-License-Identifier: MIT
"""
import re


def ind_path(g, seq, iters, stores=False):
    """One dispatch JALR whose targets repeat seq (handlers A, B, C, D). With A, B, A, C every
    target differs from the previous one (last-target prediction always misses) and the two
    previous targets decide the next; with A, A, A, B, A, A, A, C four previous targets are
    needed. stores: each handler also stores, so stores retire right behind dispatch JALRs."""
    i_type, branch, jal, store = g['i_type'], g['branch'], g['jal'], g['store']
    add = lambda rd, a, b: g['r_type'](0x33, rd, 0, a, b)
    ld = lambda rd, rs, off: i_type(3, rd, 3, rs, off)
    p = [i_type(0x13, 10, 0, 0, iters), (3 << 12) | (29 << 7) | 0x37]    # 0: x10 = iterations; 4: x29 = 0x3000
    H = 3 if stores else 2                                                # words per handler
    A = 0x100
    hs = [A + 4 * H * k for k in range(4)]
    N = A + 4 * H * 4
    for k, c in enumerate(seq):
        p += [i_type(0x13, 5, 0, 0, hs['ABCD'.index(c)]), store(3, 29, 5, 8 * k)]   # sd target, 8k(x29)
    p += [i_type(0x13, 7, 0, 0, 0)]                                       # x7 = 0 (byte index)
    L = 4 * len(p)
    p += [add(8, 29, 7), ld(6, 8, 0),                                     # L: x6 = seq[x7 / 8]
          i_type(0x13, 7, 0, 7, 8), i_type(0x13, 7, 7, 7, 8 * len(seq) - 1),   # x7 = (x7 + 8) mod 8 len
          i_type(0x67, 0, 0, 6, 0)]                                       # D: jalr x0, 0(x6)
    assert len(seq) in (4, 8) and 4 * len(p) <= A
    p += [0x00000013] * (A // 4 - len(p))
    for k, h in enumerate(hs):
        assert 4 * len(p) == h
        p += [i_type(0x13, 20 + k, 0, 20 + k, 1)]                         # x20+k += 1
        if stores:
            p += [store(3, 29, 20 + k, 0x100 + 8 * k)]                    # sd x20+k, 0x100+8k(x29)
        p += [jal(0, N - (h + 4 * (H - 1)))]                              # j N
    assert 4 * len(p) == N
    p += [i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, L - (N + 4)),   # N: x10 -= 1; bne -> L
          0x100073, jal(0, 0)]
    return p


def iw_alias(g):
    """A loop at 0x100 calls three functions at 0x900, 0x1100 and 0x1900: with 2 KiB of
    instruction cache the four beats share a set; with 4 KiB they share two sets in pairs."""
    i_type, branch, jal = g['i_type'], g['branch'], g['jal']
    p = [i_type(0x13, 10, 0, 0, 100)]                                     # 0: x10 = 100
    p += [jal(0, 0x100 - 4)]                                              # 4: j 0x100
    p += [0x00000013] * (0x100 // 4 - len(p))
    L = 0x100
    p += [jal(1, 0x900 - L), jal(1, 0x1100 - (L + 4)), jal(1, 0x1900 - (L + 8)),   # call F1, F2, F3
          i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, L - (L + 16)),   # x10 -= 1; bne -> L
          0x100073, jal(0, 0)]
    for k, f in enumerate((0x900, 0x1100, 0x1900)):
        p += [0x00000013] * (f // 4 - len(p))
        p += [i_type(0x13, 20 + k, 0, 20 + k, 1), i_type(0x67, 0, 0, 1, 0)]   # x20+k += 1; ret
    return p


def cases(g):
    mask = g['MASK']
    yield 'fe_ind_path', ind_path(g, 'ABAC', 300), 0, mask
    yield 'fe_ind_path4', ind_path(g, 'AAABAAAC', 400, stores=True), 0, mask
    yield 'fe_iw_alias', iw_alias(g), 0, mask


# Limits (stall 0), measured 2026-11-22 on 0.17.4 + the knob (frontend/NOTES.md). fe_ind_path: 1,527
# clocks with the BTB's last target, 294 with RV64_OOO_ITTAGE. fe_ind_path4: 1,245 with the BTB, 399
# with ITTAGE, 865 when only the two shortest tables can provide (a mutant). fe_iw_alias: 410-510
# clocks while its aliasing beats thrash, 187 when they fit the ways.
IND_PATH_MAX = 600
IND_PATH4_MAX = 600
IW_ALIAS_MAX = 250


def cycles(records, name):
    for r in records:
        if r['case'] == name and r['max_wait_cycles'] == 0:
            m = re.search(r'^DONE retirements=\d+ cycles=(\d+)', r['simulator_summary'], re.M)   # the DONE line only
            return int(m[1]) if m else None
    return None


def check(records, args):
    if args.core != 'ooo' or getattr(args, 'ld_lat', None) is not None or getattr(args, 'l0', None) or             getattr(args, 'n_miss', 1) != 1:
        return    # limits of the out-of-order core at its default knobs only (Codex review 2, finding 11)
    if getattr(args, 'ittage', False) and args.icache_beats in (None, 512) and args.dcache_beats in (None, 512):
        for name, limit in (('fe_ind_path', IND_PATH_MAX), ('fe_ind_path4', IND_PATH4_MAX)):
            c = cycles(records, name)
            if c is None or c > limit:
                raise AssertionError(f'{name} took {c} clocks with RV64_OOO_ITTAGE, expected <= {limit} '
                                     '(the path history must predict the dispatch sequence)')
    # fe_iw_alias: four beats 2 KiB apart. A way of at most 2 KiB holds all four in one set, of
    # 4 KiB two per set, of 8 KiB or more one: they fit when the set has that many ways.
    w = getattr(args, 'iways', None) or 1
    beats = args.icache_beats or 512                  # tb_core's default
    way_bytes = 8 * beats // w
    alias = 4 if way_bytes <= 2048 else 2 if way_bytes == 4096 else 1
    if beats >= 256 and w >= alias and args.dcache_beats in (None, 512):
        c = cycles(records, 'fe_iw_alias')
        if c is None or c > IW_ALIAS_MAX:
            raise AssertionError(f'fe_iw_alias took {c} clocks with {w} ways of {way_bytes} bytes, expected <= '
                                 f'{IW_ALIAS_MAX} (its {alias} aliasing beats per set fit the ways)')
