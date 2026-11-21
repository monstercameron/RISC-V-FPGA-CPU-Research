"""Estimate logic depth and size of the core with a generic Yosys synthesis.

Maps rv64_core to 6-input LUTs with Yosys and ABC and reports the longest path
in LUT levels between registers, plus LUT and flip-flop counts. Small caches are
used by default: cache size barely changes depth and large caches become
flip-flops in a generic flow. This is a vendor-independent proxy for clock
frequency, not a timing report for any FPGA part (rubric evidence class E0/E1,
not E3). Needs Yosys on PATH (Linux or Ubuntu/WSL).
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--icache-beats', type=int, default=4)
    parser.add_argument('--dcache-beats', type=int, default=4)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/cpu/synth/depth.json')
    parser.add_argument('--rtl', type=Path, default=ROOT / 'rtl/cpu/rv64_core.sv',
                        help='Core source to measure, for example an older version from git')
    parser.add_argument('--label', help='Version label for the report (default: cpu/VERSION)')
    args = parser.parse_args()
    if not shutil.which('yosys'):
        parser.error('yosys is required (for example: apt install yosys)')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    script = '; '.join([
        f'read_verilog -sv {args.rtl}',
        f'chparam -set ICACHE_BEATS {args.icache_beats} -set DCACHE_BEATS {args.dcache_beats} rv64_core'
        if 'ICACHE_BEATS' in args.rtl.read_text(encoding='utf-8') else 'hierarchy -top rv64_core',
        'synth -top rv64_core -flatten',
        'abc -lut 6',
        'opt_clean',
        f'tee -q -o {args.out.with_suffix(".ltp.txt")} ltp -noff',
        f'tee -q -o {args.out.with_suffix(".stat.txt")} stat',
    ])
    started = time.perf_counter()
    done = subprocess.run(['yosys', '-q', '-p', script], capture_output=True, text=True, timeout=7200)
    seconds = time.perf_counter() - started
    log = done.stdout + done.stderr
    for suffix in ('.ltp.txt', '.stat.txt'):
        if args.out.with_suffix(suffix).is_file():
            log += args.out.with_suffix(suffix).read_text(encoding='utf-8')
    (args.out.parent / 'depth.log').write_text(log, encoding='utf-8')
    if done.returncode:
        raise SystemExit('Yosys failed; see ' + str(args.out.parent / 'depth.log'))
    depth = re.search(r'Longest topological path in .*?\(length=(\d+)\)', log)
    luts = re.search(r'\$lut\s+(\d+)', log)
    ffs = sum(int(n) for n in re.findall(r'\$_S?DFF\w*_\s+(\d+)', log))
    version = args.label or (ROOT / 'cpu/VERSION').read_text(encoding='ascii').strip()
    report = {'architecture_version': version, 'yosys': subprocess.run(['yosys', '-V'], capture_output=True,
              text=True).stdout.strip(), 'icache_beats': args.icache_beats, 'dcache_beats': args.dcache_beats,
              'lut6_levels_longest_path': int(depth[1]) if depth else None,
              'lut6_count': int(luts[1]) if luts else None, 'flip_flops': ffs,
              'rtl_sha256': __import__('hashlib').sha256(args.rtl.read_bytes()).hexdigest(),
              'wall_seconds': round(seconds, 1),
              'scope': 'Generic Yosys synth and ABC 6-input LUT mapping; logic levels, not nanoseconds; no FPGA part.'}
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
