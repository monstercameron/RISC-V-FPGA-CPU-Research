"""Compare two commit logs in Spike's --log-commits format (Spike's own and rv_iss --commit-log).

Each instruction line is reduced to (privilege, pc, instruction bits, x/f register writes, memory reads,
memory writes). CSR write records (cNNN_name) are ignored, because the two models log implicit CSR writes
differently; every CSR value read into a register is still compared through that register write.

Usage: python3 -B sim/cpu/sys/commit_compare.py SPIKE_LOG ISS_LOG [--limit N]
SPDX-License-Identifier: MIT
"""
import argparse
import itertools
import json
import re
import sys

LINE = re.compile(r'^core\s+\d+: (\d) (0x[0-9a-f]+) \((0x[0-9a-f]+)\)(.*)$')
CSR = re.compile(r'^c\d+_')
REG = re.compile(r'^[xf]\d+$')


def parse(line):
    m = LINE.match(line.rstrip('\n'))
    if not m:
        return None
    prv, pc, insn, rest = m.groups()
    toks = rest.split()
    regs, loads, stores = [], [], []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == 'mem':
            if i + 2 < len(toks) and toks[i + 2].startswith('0x'):
                # (address, value, bytes): Spike prints a store's width as the value's hex digit count
                stores.append((int(toks[i + 1], 16), int(toks[i + 2], 16), (len(toks[i + 2]) - 2) // 2))
                i += 3
            else:
                loads.append(int(toks[i + 1], 16))
                i += 2
        elif CSR.match(t) or REG.match(t):
            if REG.match(t) and t != 'x0':
                regs.append((t, int(toks[i + 1], 16)))
            i += 2
        else:
            i += 1
    return (int(prv), int(pc, 16), int(insn, 16), tuple(sorted(regs)), tuple(loads), tuple(stores))


def records(path):
    """Instruction records; a line that is not a commit record (for example a truncated last line) is an error,
    except Spike's own non-record lines, which do not start with "core"."""
    with open(path, errors='replace') as f:
        for line in f:
            r = parse(line)
            if r:
                yield r
            elif line.startswith('core'):
                raise ValueError(f'{path}: unparsable commit record {line.rstrip()!r}')


def fmt(r):
    if r is None:
        return 'end of log'
    prv, pc, insn, regs, loads, stores = r
    return (f'{prv} {pc:#018x} ({insn:#x}) ' + ' '.join(f'{n}={v:#x}' for n, v in regs) +
            ''.join(f' ld {a:#x}' for a in loads) + ''.join(f' st{w} {a:#x}={v:#x}' for a, v, w in stores))


def compare(spike_log, iss_log, limit=None, iss_prefix=False, ignore_loads=False):
    """First difference between the logs (over the first `limit` instructions, if given). With iss_prefix,
    rv_iss's log may end first: it stops at the HTIF tohost store, while Spike runs on to its next poll."""
    n = 0
    def strip(it):    # a log written from a lab trace (sim/cpu/trace_to_commitlog.py) has no load addresses
        return (r if r is None or not ignore_loads else (*r[:4], (), r[5]) for r in it)
    for x, y in itertools.zip_longest(strip(records(spike_log)), strip(records(iss_log))):
        if limit is not None and n >= limit:
            break
        if x is None or y is None:
            ok = (x is None and y is None) or (iss_prefix and y is None)
            return {'match': ok, 'compared': n,
                    'summary': f'{n} instructions equal; {"spike" if x is None else "rv_iss"} log ends first',
                    'first_difference': None if ok else {'index': n, 'spike': fmt(x), 'rv_iss': fmt(y)}}
        if x != y:
            return {'match': False, 'compared': n, 'summary': f'differ at instruction {n}', 'records': (x, y),
                    'first_difference': {'index': n, 'spike': fmt(x), 'rv_iss': fmt(y)}}
        n += 1
    return {'match': True, 'compared': n, 'summary': f'{n} instructions equal'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spike_log')
    ap.add_argument('iss_log')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--ignore-loads', action='store_true', help='for logs written from lab traces (no load addresses)')
    ap.add_argument('--iss-prefix', action='store_true', help='the second log may end first')
    args = ap.parse_args()
    r = compare(args.spike_log, args.iss_log, args.limit, args.iss_prefix, args.ignore_loads)
    print(json.dumps(r, indent=1))
    return 0 if r['match'] else 1


if __name__ == '__main__':
    sys.exit(main())
