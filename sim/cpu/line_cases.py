"""Data-cache line cases (council middle, line step 1): test_cpu.py adds them with --n-miss > 1, where data reads
are split reads and, with --dline > 8, whole-line reads (critical beat first, wrapping). They are ordinary
programs, checked against the golden model like every case, and each also has an expected end (END: the
terminal cause and tval of the golden trace), so a program that stops early by mistake is caught. Offsets follow
the line size (LINE bytes, set by test_cpu.py from --dline; 64 when lines are off, so the programs keep their
shape). The lines used are first written by stores (stores do not allocate), so their reads are cold and not zero.
SPDX-License-Identifier: MIT
"""
from test_cpu import i_type, r_type, store, prefix, MASK

LINE = 64
LUI29 = (3 << 12) | (29 << 7) | 0x37            # x29 = 0x3000
END = {}                                         # case -> (cause, tval) of the golden trace's T record


def _add(rd, a, b):
    return r_type(0x33, rd, 0, a, b)


def _fill(base, beats):
    """sd distinct values to the beats at 0x3000 + base (x29)."""
    p = []
    for n in range(beats):
        p += [i_type(0x13, 5, 0, 0, (n * 37 + 11) & 0x7ff), store(3, 29, 5, base + 8 * n)]
    return p


def _late_base(rd):
    """rd = x29 after 6 divides by one (x27 = 1): an address that comes late."""
    return [i_type(3, 26, 3, 30, 0), _add(rd, 29, 26)] + [r_type(0x33, rd, 4, rd, 27, 1)] * 6


def cases():
    lb = max(2, LINE // 8)                       # beats per line (at least 2, so "another beat" exists)
    lb = min(lb, 8)
    ln = 8 * lb
    END.clear()
    # Stores to other beats of a line whose fill is in flight: their bytes survive the fill (merge), and later
    # loads of those beats (from the store queue, then from the line) see them. Variants move the critical beat
    # round the line (wrapping order); one variant stores a byte (a partial merge) and one stores two beats.
    p = prefix() + [LUI29, i_type(0x13, 27, 0, 0, 1)] + _fill(0x400, 64) + _late_base(20)
    for j in range(8):
        line = 0x400 + ln * j
        crit, other, third = 8 * (j % lb), 8 * ((j + 1) % lb), 8 * ((j + lb - 1) % lb)
        f3 = 0 if j == 3 else 3                  # j == 3: sb (part of a beat)
        p += [i_type(3, 21, 3, 20, line + crit),          # A: cold, the line's read starts here
              i_type(0x13, 22, 0, 21, 0x55),               # A + 0x55
              store(f3, 20, 22, line + other + (5 if f3 == 0 else 0)),   # S: same line, another beat
              i_type(3, 23, 3, 20, line + other),          # B: S's beat (forwarded, then the line)
              i_type(3, 24, 3, 20, line + third),          # C: another beat of the line
              _add(25, 25, 23), _add(25, 25, 24)]
        if j == 5:
            p += [store(3, 20, 25, line + third), i_type(3, 24, 3, 20, line + third), _add(25, 25, 24)]   # two stores
    for j in range(8):                                     # read the stored beats again (from the lines)
        p += [i_type(3, 23, 3, 29, 0x400 + ln * j + 8 * ((j + 1) % lb)), _add(25, 25, 23)]
    yield 'line_store_merge', p + [store(3, 29, 25, 0x3f8), 0x100073], 0, MASK
    END['line_store_merge'] = (3, 0)
    # A read fault on a beat of the line that is not the critical one: the line is not installed and the
    # older load completes; the load of the faulting beat then faults precisely (cause 5) as the oldest.
    fb = 0x3600 + 8 * (lb - 1)
    p = prefix() + [LUI29, i_type(0x13, 27, 0, 0, 1)] + _fill(0x600, lb) + _late_base(20)
    p += [i_type(3, 21, 3, 20, 0x600), store(3, 29, 21, 0x3f0)]           # the line's read, critical beat 0x3600
    if lb > 2:
        p += [i_type(3, 22, 3, 20, 0x608), store(3, 29, 22, 0x3e8)]       # another good beat of the line
    p += [i_type(3, 23, 3, 20, fb - 0x3000), store(3, 29, 23, 0x3e0), 0x100073]   # the faulting beat
    yield 'line_fault_other_beat', p, 2, fb
    END['line_fault_other_beat'] = (5, fb)
    # A younger load of the faulting (last) beat while an older load reads the line: it waits on the line, the
    # line is not installed, and it faults once it is the oldest load (entry 0's own read).
    fy = 0x3700 + 8 * (lb - 1)
    p = prefix() + [LUI29, i_type(0x13, 27, 0, 0, 1)] + _fill(0x700, lb) + _late_base(20)
    p += [i_type(3, 21, 3, 20, 0x700),                             # older, late address: reads the line
          i_type(3, 22, 3, 29, fy - 0x3000),                       # younger, early address: the faulting beat
          store(3, 29, 21, 0x3d8), store(3, 29, 22, 0x3c8), 0x100073]
    yield 'line_fault_younger_sleeps', p, 2, fy
    END['line_fault_younger_sleeps'] = (5, fy)
    # Many loads to few lines: the first of each line misses, the rest find the line in flight and wait.
    # Destinations x5-x18 (the base x20 is never overwritten: Codex review, item 3).
    p = prefix() + [LUI29, i_type(0x13, 27, 0, 0, 1)] + _fill(0x780, 16) + _late_base(20)
    for n in range(32):
        p += [i_type(3, 5 + n % 14, 3, 20, 0x780 + 8 * ((n * 5) % 16))]
    for n in range(13):
        p.append(_add(5, 5, 6 + n))
    yield 'line_many_same_line', p + [store(3, 29, 5, 0x3d0), 0x100073], 0, MASK
    END['line_many_same_line'] = (3, 0)


FAULT_ONCE_ADDR = 0x3100


def fault_once_program():
    """Codex review of line step 1, item 1. The load L is the oldest load and reads its beat through entry 0
    (its value is forwarded from the older store S, but the beat must still be read); S retires only after a
    divide chain, so it writes L's beat while L's line read is out. tb_core (+fault_kind=5) answers that critical
    beat once with an error. Since a store wrote the beat after the read was accepted, the error is not L's:
    L reads the beat again and retires, as in the golden model (which has no fault). Run with stall 0 and a
    fixed split latency longer than the divide chain (test_cpu uses 80)."""
    return [LUI29, i_type(0x13, 27, 0, 0, 1), i_type(0x13, 24, 0, 0, 77)] + \
        [r_type(0x33, 24, 4, 24, 27, 1)] * 6 + [                 # older divide chain (about 42 clocks)
        i_type(0x13, 7, 0, 0, 0x5a5),
        store(3, 29, 7, FAULT_ONCE_ADDR - 0x3000),              # S: sd x7, its data at once, retires late
        i_type(3, 23, 3, 29, FAULT_ONCE_ADDR - 0x3000),         # L: forwarded from S, reads its beat (entry 0)
        _add(25, 23, 24), store(3, 29, 25, 0x108), 0x100073]
