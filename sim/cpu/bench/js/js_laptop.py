# SPDX-License-Identifier: MIT
"""Laptop reference of the JavaScript benchmark: per-clock figures for cpu/js-benchmark-targets.md.

Runs the native binary from js_native.sh (same QuickJS-ng, harness and script) RUNS times pinned to
one CPU with taskset, after a clock ramp (JS_BENCH_RAMP_MS of dependent adds inside the process,
which also reports the clock from the cycle counter and from a 64-add chain). The harness reads the
CPU's own user-space PMUv3 counters (0x08 INST_RETIRED, 0x11 CPU_CYCLES) at every marker. For each
kernel it reports the timed (second) call, marker 0x20+k to 0x30+k: median CPU cycles with the
min-max over runs, median instructions and IPC, and the effective clock (cycles / wall time).
The warm (first) call is reported too. Usage (Linux or WSL):
    python3 -B js_laptop.py [--ref build/cpu/bench/js-ref/s1] [--cpu 19] [--runs 7] [--ramp-ms 1500]
Writes <ref>/laptop.json and prints a table.
"""
import argparse
import json
import math
import os
import platform
import re
import statistics
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def run_once(binary, cpu, ramp_ms):
    env = dict(os.environ, JS_BENCH_RAMP_MS=str(ramp_ms))
    done = subprocess.run(['taskset', '-c', str(cpu), str(binary)], capture_output=True, text=True,
                          timeout=120, env=env)
    if done.returncode:
        raise SystemExit(f'native run failed: {done.stderr[-2000:]}')
    marks = {int(m, 16): (float(t), int(i), int(c)) for m, t, i, c in
             re.findall(r'^mark 0x([0-9a-f]+) t ([0-9.]+) s ins (-?\d+) cyc (-?\d+)$', done.stderr, re.M)}
    clock = re.search(r'^clock ramp_ms ([0-9.]+) pmu_ghz ([0-9.]+) add_chain_ghz ([-0-9.]+) cpu (\d+)$', done.stderr, re.M)
    out_hash = re.search(r'^hash ([0-9a-f]{16})', done.stderr, re.M)[1]
    return marks, clock, out_hash, done.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ref', default='build/cpu/bench/js-ref/s1')
    ap.add_argument('--cpu', type=int, default=19)
    ap.add_argument('--runs', type=int, default=7)
    ap.add_argument('--ramp-ms', type=float, default=1500)
    args = ap.parse_args()
    ref = (ROOT / args.ref).resolve()
    expected = json.loads((ref / 'expected.json').read_text())
    kernels = [line['kernel'] for line in expected['lines']]
    part = None
    for block in Path('/proc/cpuinfo').read_text().split('\n\n'):
        if re.search(rf'^processor\s*:\s*{args.cpu}$', block, re.M):
            m = re.search(r'^CPU part\s*:\s*(\S+)', block, re.M)
            part = m[1] if m else None
    load_before = Path('/proc/loadavg').read_text().split()[:3]
    runs = []
    for r in range(args.runs):
        marks, clock, out_hash, stdout = run_once(ref / 'qjs_bench', args.cpu, args.ramp_ms)
        if out_hash != expected['hash_hex']:
            raise SystemExit(f'run {r}: output hash {out_hash}, expected {expected["hash_hex"]}')
        runs.append({'marks': marks, 'clock': {'ramp_ms': float(clock[1]), 'pmu_ghz': float(clock[2]),
                                               'add_chain_ghz': float(clock[3]), 'cpu': int(clock[4])}})
        if int(clock[4]) != args.cpu:
            raise SystemExit(f'run {r} ran on CPU {clock[4]}, not {args.cpu}')
    load_after = Path('/proc/loadavg').read_text().split()[:3]
    table = {}
    for k, name in enumerate(kernels):
        def span(a, b):
            cyc = [r['marks'][b][2] - r['marks'][a][2] for r in runs]
            ins = [r['marks'][b][1] - r['marks'][a][1] for r in runs]
            sec = [r['marks'][b][0] - r['marks'][a][0] for r in runs]
            return cyc, ins, sec
        cyc, ins, sec = span(0x20 + k, 0x30 + k)
        wcyc, wins, _ = span(0x10 + k, 0x20 + k)
        mc, mi = statistics.median(cyc), statistics.median(ins)
        table[name] = {'cycles_median': mc, 'cycles_min': min(cyc), 'cycles_max': max(cyc), 'cycles': cyc,
                       'instructions_median': mi, 'instructions_min': min(ins), 'instructions_max': max(ins),
                       'ipc': mi / mc, 'effective_ghz': mc / statistics.median(sec) / 1e9,
                       'warm_call_cycles_median': statistics.median(wcyc),
                       'warm_call_instructions_median': statistics.median(wins),
                       'goal_clocks': mc / 1.5}
    run_totals = [sum(r['marks'][0x30 + k][2] - r['marks'][0x20 + k][2] for k in range(len(kernels))) for r in runs]
    total_cycles = sum(t['cycles_median'] for t in table.values())
    total_ins = sum(t['instructions_median'] for t in table.values())
    ver = subprocess.run(['clang', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    result = {
        'date': datetime.now().astimezone().isoformat(timespec='seconds'),
        'host': ' '.join(platform.uname()[i] for i in (0, 2, 4)), 'cpu': args.cpu, 'cpu_part': part,
        'runs': args.runs, 'ramp_ms': args.ramp_ms, 'loadavg_before': load_before, 'loadavg_after': load_after,
        'binary': str((ref / 'qjs_bench').relative_to(ROOT)), 'reference': json.loads((ref / 'reference.json').read_text()),
        'compiler_now': ver, 'clock': [r['clock'] for r in runs], 'kernels': table,
        'total': {'cycles_sum_of_medians': total_cycles, 'instructions_sum_of_medians': total_ins,
                  'ipc': total_ins / total_cycles, 'run_totals_cycles': run_totals,
                  'run_total_median': statistics.median(run_totals)},
        'counters': 'user-space PMUv3 0x08 INST_RETIRED and 0x11 CPU_CYCLES, read at each marker',
    }
    (ref / 'laptop.json').write_text(json.dumps(result, indent=1) + '\n')
    ghz = [c['pmu_ghz'] for c in result['clock']]
    chain = [c['add_chain_ghz'] for c in result['clock']]
    print(f'{args.runs} runs on CPU {args.cpu} (part {part}); ramp clock by cycle counter {min(ghz):.3f}-{max(ghz):.3f} GHz, '
          f'add chain {min(chain):.3f}-{max(chain):.3f} GHz; load {load_before} -> {load_after}')
    print('| Kernel | Cycles median [min-max] | Instructions | IPC | GHz | Goal clocks (laptop / 1.5) |')
    for name, t in table.items():
        print(f'| {name} | {t["cycles_median"]:,.0f} [{t["cycles_min"]:,}-{t["cycles_max"]:,}] | '
              f'{t["instructions_median"]:,.0f} | {t["ipc"]:.2f} | {t["effective_ghz"]:.2f} | {t["goal_clocks"]:,.0f} |')
    print(f'| total | {total_cycles:,.0f} | {total_ins:,.0f} | {total_ins / total_cycles:.2f} | | {total_cycles / 1.5:,.0f} |')
    print(f'Wrote {(ref / "laptop.json").relative_to(ROOT)}')


if __name__ == '__main__':
    main()
