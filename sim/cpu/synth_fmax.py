"""Estimate the core's clock frequency on a real FPGA family with an open flow.

Synthesizes rv64_core for Lattice ECP5 with Yosys (synth_ecp5), then places and
routes it out of context with nextpnr-ecp5 and reports nextpnr's achieved maximum
frequency and resource use. Out of context means no I/O buffers or pins: the
core's ports are left as internal nets, so paths from and to the ports are not a
board-level constraint. Small caches are used by default, as in synth_depth.py.

This is a post-route timing estimate from an open-source timing model for one
part and one placement seed, not a measurement on hardware and not a vendor
sign-off (rubric evidence class E1, not E3/E4). Needs yosys and nextpnr-ecp5 on
PATH (Linux or Ubuntu/WSL).
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def tool_version(cmd):
    done = subprocess.run(cmd, capture_output=True, text=True)
    return (done.stdout + done.stderr).strip().splitlines()[0]


def critical_path(log):
    """Logic and routing split of the final (post-route) critical path, plus its ends."""
    report = log.rsplit('Critical path report for clock', 1)
    if len(report) < 2:
        return None
    split = re.search(r'([\d.]+) ns logic, ([\d.]+) ns routing', report[1])
    source = re.search(r'Source (\S+)', report[1])
    sinks = re.findall(r'Setup (\S+)', report[1])
    return {'logic': float(split[1]), 'routing': float(split[2]),
            'from': source[1] if source else None, 'to': sinks[0] if sinks else None} if split else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--icache-beats', type=int, default=4)
    parser.add_argument('--dcache-beats', type=int, default=4)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/cpu/synth/fmax.json')
    parser.add_argument('--rtl', type=Path, default=ROOT / 'rtl/cpu/rv64_core.sv',
                        help='Core source to measure, for example an older version from git')
    parser.add_argument('--label', help='Version label for the report (default: cpu/VERSION)')
    parser.add_argument('--device', default='85k', choices=['25k', '45k', '85k', 'um-85k', 'um5g-85k'])
    parser.add_argument('--package', default='CABGA381')
    parser.add_argument('--speed', default='6', choices=['6', '7', '8'])
    parser.add_argument('--freq', type=float, default=50.0, help='Target clock for the router, MHz')
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    for tool in ('yosys', 'nextpnr-ecp5'):
        if not shutil.which(tool):
            parser.error(f'{tool} is required (for example: apt install yosys nextpnr-ecp5)')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Snapshot the source first so the report describes exactly what was built.
    source = args.out.with_suffix('.sv')
    source.write_bytes(args.rtl.read_bytes())
    netlist = args.out.with_suffix('.netlist.json')
    route_report = args.out.with_suffix('.nextpnr.json')
    log_path = args.out.with_suffix('.log')
    version = args.label or (ROOT / 'cpu/VERSION').read_text(encoding='ascii').strip()
    text = source.read_text(encoding='utf-8')
    script = '; '.join([
        f'read_verilog -sv {source}',
        f'chparam -set ICACHE_BEATS {args.icache_beats} -set DCACHE_BEATS {args.dcache_beats} rv64_core'
        if 'ICACHE_BEATS' in text else 'hierarchy -top rv64_core',
        f'synth_ecp5 -top rv64_core -json {netlist}',
        f'tee -q -o {args.out.with_suffix(".stat.txt")} stat',
    ])
    started = time.perf_counter()
    synth = subprocess.run(['yosys', '-q', '-p', script], capture_output=True, text=True, timeout=7200)
    synth_seconds = time.perf_counter() - started
    log = synth.stdout + synth.stderr
    if synth.returncode:
        log_path.write_text(log, encoding='utf-8')
        raise SystemExit('Yosys failed; see ' + str(log_path))
    route = subprocess.run(['nextpnr-ecp5', f'--{args.device}', '--package', args.package, '--speed', args.speed,
                            '--out-of-context', '--json', str(netlist), '--freq', str(args.freq),
                            '--seed', str(args.seed), '--report', str(route_report), '--timing-allow-fail'],
                           capture_output=True, text=True, timeout=14400)
    seconds = time.perf_counter() - started
    log += route.stdout + route.stderr
    log_path.write_text(log, encoding='utf-8')
    fmax = utilization = None
    if route_report.is_file():
        data = json.loads(route_report.read_text(encoding='utf-8'))
        fmax = {clock: {'achieved_mhz': round(v['achieved'], 2), 'target_mhz': v['constraint']}
                for clock, v in data.get('fmax', {}).items()}
        utilization = {k: v for k, v in data.get('utilization', {}).items() if v.get('used')}
    if fmax is None:
        # Fall back to the log line if the report is missing.
        found = re.findall(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz", log)
        fmax = {clock: {'achieved_mhz': float(mhz)} for clock, mhz in found[-1:]} or None
    report = {
        'architecture_version': version,
        'yosys': tool_version(['yosys', '-V']),
        'nextpnr': tool_version(['nextpnr-ecp5', '--version']),
        'device': f'LFE5U-{args.device.upper()}' if args.device[0].isdigit() else args.device,
        'package': args.package, 'speed_grade': args.speed, 'seed': args.seed,
        'icache_beats': args.icache_beats, 'dcache_beats': args.dcache_beats,
        'route_status': 'routed' if route.returncode == 0 or 'Routing complete' in log
                        else f'nextpnr exit {route.returncode}',
        'fmax': fmax, 'utilization': utilization,
        'critical_path_ns': critical_path(log),
        'rtl_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'synth_seconds': round(synth_seconds, 1), 'wall_seconds': round(seconds, 1),
        'scope': 'Yosys synth_ecp5 and nextpnr-ecp5 out-of-context place and route; post-route timing '
                 'estimate for one part and seed; not a hardware measurement or vendor sign-off.',
    }
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if route.returncode:
        raise SystemExit(f'nextpnr failed (exit {route.returncode}); see {log_path}')


if __name__ == '__main__':
    main()
