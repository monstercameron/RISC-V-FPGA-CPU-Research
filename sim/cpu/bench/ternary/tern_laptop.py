#!/usr/bin/env python3
"""Laptop reference of the ternary benchmark (SPDX-License-Identifier: MIT). aarch64 Linux or WSL.

Builds tern_laptop.c for T-small and T-2B4T (clang -O2, auto-vectoriser off, NEON SDOT enabled for the
context kernel), runs each binary RUNS times pinned with taskset to one core, and writes the median,
minimum and maximum over the runs of cycles per call (CPU_CYCLES from the user-space PMU), retired
instructions, weights per clock, bytes per clock and instructions per weight. Each process ramps the
clock for 2 s first. No goal is set.

Usage: python3 -B sim/cpu/bench/ternary/tern_laptop.py [--runs 7] [--cpu 19] [--out DIR]
"""
from pathlib import Path
import argparse
import json
import platform
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FLAGS = ['-O2', '-std=gnu11', '-fno-vectorize', '-fno-slp-vectorize', '-march=armv8.2-a+dotprod', '-Wall', '-Wextra',
         '-Wno-unused-function', '-Wno-unused-parameter']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', type=int, default=7)
    ap.add_argument('--cpu', type=int, default=19)
    ap.add_argument('--cold-reps', type=int, default=3)
    ap.add_argument('--out', default=str(ROOT / 'build/cpu/bench/ternary-laptop'))
    ap.add_argument('--shapes', default='small,2b4t')
    args = ap.parse_args()
    if platform.machine() not in ('aarch64', 'arm64'):
        sys.exit('this reference needs an aarch64 host (PMUv3 counters)')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cc = 'clang'
    version = subprocess.run([cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    raw = []
    for shape in args.shapes.split(','):
        exe = out / f'tern_laptop_{shape}'
        subprocess.run([cc, *FLAGS, f'-DTERN_SHAPE={1 if shape == "small" else 0}', f'-I{HERE}', str(HERE / 'tern_laptop.c'),
                        '-o', str(exe)], check=True)
        for run in range(args.runs):
            t0 = time.time()
            p = subprocess.run(['taskset', '-c', str(args.cpu), str(exe), str(args.cold_reps)], capture_output=True, text=True)
            if p.returncode:
                sys.exit(f'{shape} run {run} failed: {p.stdout[-400:]} {p.stderr[-400:]}')
            for line in p.stdout.splitlines():
                f = line.split()
                if f[0] == 'R':
                    raw.append({'run': run, 'shape': f[1], 'layer': int(f[2]), 'kernel': f[3], 'mode': f[4], 'm': int(f[5]),
                                'k': int(f[6]), 'weights': float(f[7]), 'bytes': int(f[8]), 'cycles': int(f[9]),
                                'insns': int(f[10]), 'seconds': float(f[11])})
                elif f[0] == 'C' and f[2] == 'clock_ramp_ghz':
                    raw.append({'run': run, 'shape': f[1], 'clock_ramp_ghz': float(f[3])})
            print(f'{shape} run {run}: {time.time() - t0:.1f} s', flush=True)
    rows = [r for r in raw if 'kernel' in r]
    summary = {}
    for shape in sorted({r['shape'] for r in rows}):
        for mode in ('resident', 'cold'):
            for kernel in ('i2', 'lut5w', 'bs8', 'ndot', 'stream'):
                sel = [r for r in rows if r['shape'] == shape and r['mode'] == mode and r['kernel'] == kernel]
                if not sel:
                    continue
                # per run (and per cold repetition index): totals over the layers
                groups = {}
                for r in sel:
                    groups.setdefault(r['run'], {}).setdefault(r['layer'], []).append(r)
                totals = []
                for run, layers in groups.items():
                    reps = min(len(v) for v in layers.values())
                    for i in range(reps):
                        totals.append({'cycles': sum(layers[li][i]['cycles'] for li in layers),
                                       'insns': sum(layers[li][i]['insns'] for li in layers),
                                       'weights': sum(layers[li][i]['weights'] for li in layers),
                                       'bytes': sum(layers[li][i]['bytes'] for li in layers),
                                       'seconds': sum(layers[li][i]['seconds'] for li in layers)})
                def stat(key, fn):
                    v = [fn(t) for t in totals]
                    return {'median': statistics.median(v), 'min': min(v), 'max': max(v)}
                entry = {'samples': len(totals), 'cycles': stat('c', lambda t: t['cycles']),
                         'insns': stat('i', lambda t: t['insns']),
                         'bytes_per_clock': stat('b', lambda t: t['bytes'] / t['cycles']),
                         'clock_ghz': stat('g', lambda t: t['cycles'] / t['seconds'] / 1e9)}
                if totals[0]['weights']:
                    entry['weights_per_clock'] = stat('w', lambda t: t['weights'] / t['cycles'])
                    entry['insns_per_weight'] = stat('p', lambda t: t['insns'] / t['weights'])
                    entry['ipc'] = stat('ipc', lambda t: t['insns'] / t['cycles'])
                summary[f'{shape}/{mode}/{kernel}'] = entry
    ramps = [r['clock_ramp_ghz'] for r in raw if 'clock_ramp_ghz' in r]
    doc = {'host': {'platform': platform.platform(), 'machine': platform.machine(), 'compiler': version,
                    'flags': FLAGS, 'cpu': args.cpu, 'runs': args.runs,
                    'clock_ramp_ghz': {'median': statistics.median(ramps), 'min': min(ramps), 'max': max(ramps)}},
           'summary': summary, 'raw': raw}
    (out / 'laptop.json').write_bytes((json.dumps(doc, indent=1) + '\n').encode())
    print(f'{"shape/mode/kernel":24} {"weights/clk":>26} {"B/clk":>22} {"instr/weight":>20} {"GHz":>6}')
    for key, e in summary.items():
        w = e.get('weights_per_clock')
        ws = f'{w["median"]:.3f} [{w["min"]:.3f}-{w["max"]:.3f}]' if w else '-'
        b = e['bytes_per_clock']
        ip = e.get('insns_per_weight')
        print(f'{key:24} {ws:>26} {b["median"]:.3f} [{b["min"]:.3f}-{b["max"]:.3f}] '
              f'{(f"{ip["median"]:.3f}" if ip else "-"):>10} {e["clock_ghz"]["median"]:6.2f}')
    print(f'Output: {out / "laptop.json"}')


if __name__ == '__main__':
    main()
