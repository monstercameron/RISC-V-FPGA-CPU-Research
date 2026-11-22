#!/usr/bin/env python3
"""Write a lab trace (tb_core.sv, reference.py or rv_iss) as a commit log in Spike's --log-commits format.

The RTL cores' commit-log writer (P0): the trace records an RTL core already emits (R, W, F, C, E/I, T) carry
everything Spike's log has for these programs except load addresses and the privilege mode, so the log is
derived here instead of being formatted in tb_core.sv. Each R record becomes one line, its stores (from the W
records before it) appended as `mem ADDR VALUE` with Spike's width (the digit count), and the accumulated
fflags as `c1_fflags` when the instruction raised flags. The privilege field is --priv (default 3, M-mode: the
lab environment and riscv-tests' p environment) until the RTL traces carry mode records. A terminal T record
ends the log (Spike does not log a trapping instruction). The result reads back with
sim/cpu/sys/commit_compare.py.

Usage: python3 -B sim/cpu/trace_to_commitlog.py TRACE [--priv N] [-o LOG]
SPDX-License-Identifier: MIT
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from spike_lockstep import rtl_records   # noqa: E402


def write(trace_lines, out, priv=3):
    n = 0
    for r in rtl_records(trace_lines):
        if r[0] == 'T':
            break
        _, pc, insn, regs, stores, fl = r
        width = 4 if (insn & 3) != 3 else 8
        line = f'core   0: {priv} 0x{pc:016x} (0x{insn:0{width}x})'
        for name, v in regs:
            line += f' {name[0]}{int(name[1:]):<2d} 0x{v:016x}'
        if fl is not None:
            line += f' c1_fflags 0x{fl:016x}'
        for a, v, w in stores:
            line += f' mem 0x{a:016x} 0x{v:0{2 * w}x}'
        out.write(line + '\n')
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace', type=Path)
    ap.add_argument('--priv', type=int, default=3)
    ap.add_argument('-o', '--output', type=Path)
    a = ap.parse_args()
    with open(a.trace) as f, (open(a.output, 'w') if a.output else sys.stdout) as out:
        n = write(f, out, a.priv)
    print(f'{n} records', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
