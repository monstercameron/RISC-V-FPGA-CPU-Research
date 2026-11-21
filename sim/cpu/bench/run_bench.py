"""Run a built benchmark on the RTL, check its results and report cycle counts.

Needs Python 3.11+ and Icarus Verilog (Linux or Ubuntu/WSL). Build first with
build_bench.py. Two checks run:

1. Timing: the core with its synchronous RAM wrapper counts clocks and retired
   instructions between the program's start and stop markers.
2. Differential: the core runs under the trace testbench, with and without
   memory wait cycles, and every retirement, memory write and the final trap
   must match the project's sequential reference model.

Results are simulation evidence (rubric class E1), not a compliant benchmark run.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'sim/cpu'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import execute  # noqa: E402
import bench_profile  # noqa: E402
import rubric_score  # noqa: E402
import runlog  # noqa: E402

DHRYSTONE_MAGIC = 0x4e4f545359524844
DMIPS_DIVISOR = 1757  # Dhrystones per second of the VAX 11/780 reference

# Mailbox result words written by dhrystone_port.c, with the values upstream
# main() prints as "should be". Arr_2_Glob[8][7] depends on the run count.
DHRYSTONE_RESULTS = [
    ('magic', lambda runs: DHRYSTONE_MAGIC),
    ('number_of_runs', lambda runs: runs),
    ('Int_Glob', lambda runs: 5),
    ('Bool_Glob', lambda runs: 1),
    ('Ch_1_Glob', lambda runs: ord('A')),
    ('Ch_2_Glob', lambda runs: ord('B')),
    ('Arr_1_Glob[8]', lambda runs: 7),
    ('Arr_2_Glob[8][7]', lambda runs: runs + 10),
    ('Ptr_Glob->Discr', lambda runs: 0),
    ('Ptr_Glob->Enum_Comp', lambda runs: 2),
    ('Ptr_Glob->Int_Comp', lambda runs: 17),
    ('Ptr_Glob->Str_Comp matches', lambda runs: 1),
    ('Next_Ptr_Glob->Discr', lambda runs: 0),
    ('Next_Ptr_Glob->Enum_Comp', lambda runs: 1),
    ('Next_Ptr_Glob->Int_Comp', lambda runs: 18),
    ('Next_Ptr_Glob->Str_Comp matches', lambda runs: 1),
    ('Ptr_Comp equal in both records', lambda runs: 1),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, timeout=1800):
    completed = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(f'Command failed: {" ".join(map(str, args))}\n{completed.stdout}{completed.stderr}')
    return completed.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--benchmark', choices=['dhrystone'], default='dhrystone')
    parser.add_argument('--out-dir', help='Default: build/cpu/bench/<benchmark>')
    parser.add_argument('--stalls', type=int, nargs='+', default=[0, 7],
                        help='Maximum random memory wait cycles for each differential run')
    parser.add_argument('--max-cycles', type=int, default=50_000_000)
    parser.add_argument('--record', action='store_true',
                        help='Also write the result to cpu/<benchmark>-results.json')
    parser.add_argument('--devlog', action='store_true',
                        help='Write this run, its rubric scorecard and profile to devlog/devlog-<commit>.md '
                             'and add a row to the run index in DEVLOG.md')
    args = parser.parse_args()
    if not shutil.which('iverilog') or not shutil.which('vvp'):
        parser.error('iverilog and vvp are required; on Windows use run_dhrystone.ps1')
    out = (ROOT / (args.out_dir or f'build/cpu/bench/{args.benchmark}')).resolve()
    build = json.loads((out / 'build.json').read_bytes())
    for name, digest in build['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise SystemExit(f'Stale build: {name} changed since build_bench.py ran')
    for name, digest in build['artifact_sha256'].items():
        if sha(out / name) != digest:
            raise SystemExit(f'Stale or damaged build artifact: {name}')
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    rtl = [ROOT / 'rtl/cpu/rv64_core.sv', ROOT / 'rtl/cpu/rv64_bram_soc.sv']

    # 1. Timing on the core plus synchronous RAM wrapper.
    timing_vvp = out / 'tb_bench.vvp'
    command(['iverilog', '-g2012', '-Wall', '-s', 'tb_bench', f'-Ptb_bench.RAM_WORDS={ram_bytes // 8}',
             '-o', timing_vvp, *rtl, ROOT / 'sim/cpu/bench/tb_bench.sv'])
    started = time.perf_counter()
    output = command(['vvp', timing_vvp, f'+image={out / "bench-words.hex"}', f'+mailbox={mailbox:x}',
                      f'+max_cycles={args.max_cycles}'])
    timing_seconds = time.perf_counter() - started
    (out / 'timing-run.txt').write_text(output, encoding='utf-8')
    counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+) trap_pc=([0-9a-f]{16})', output)
    region = re.search(r'REGION cycles=(\d+) retirements=(\d+)', output)
    if not counters or not region:
        raise AssertionError('Timing run did not report its counters')
    total_cycles, total_retired = int(counters[1]), int(counters[2])
    region_cycles, region_retired = int(region[1]), int(region[2])
    words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.MULTILINE)}
    if words.get(1) != 0:
        raise AssertionError(f'main() returned {words.get(1)}, expected 0')
    runs = words.get(3)
    checks = []
    for offset, (name, expect) in enumerate(DHRYSTONE_RESULTS):
        expected, actual = expect(runs), words.get(2 + offset)
        checks.append({'name': name, 'expected': expected, 'actual': actual, 'pass': actual == expected})
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError('Wrong benchmark results: ' + '; '.join(
            f'{c["name"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))

    # 2. Differential trace against the sequential reference model.
    image = (out / 'bench.bin').read_bytes().ljust(ram_bytes, b'\0')
    started = time.perf_counter()
    expected_trace, coverage = execute(image, max_steps=20_000_000)
    reference_seconds = time.perf_counter() - started
    trace_vvp = out / 'tb_core.vvp'
    command(['iverilog', '-g2012', '-Wall', '-s', 'tb_core', f'-Ptb_core.MEM_BYTES={ram_bytes}',
             '-o', trace_vvp, rtl[0], ROOT / 'sim/cpu/tb_core.sv'])
    start_write = f'W {mailbox:016x} {1:016x} ff'
    stop_write = f'W {mailbox:016x} {2:016x} ff'
    differential = []
    for index, stalls in enumerate(args.stalls):
        trace_path = out / f'trace-stall{stalls}.trace'
        summary = command(['vvp', trace_vvp, f'+image={out / "bench-bytes.hex"}', f'+trace={trace_path}',
                           f'+stall={stalls}', f'+seed={index + 1}', f'+max_cycles={args.max_cycles}'])
        actual_trace = trace_path.read_text().splitlines()
        if actual_trace != expected_trace:
            for event, (a, e) in enumerate(zip(actual_trace + ['<missing>'] * len(expected_trace),
                                               expected_trace + ['<missing>'] * len(actual_trace))):
                if a != e:
                    raise AssertionError(f'Trace differs at event {event} (stall {stalls}):\nactual {a}\nexpect {e}')
        first, last = actual_trace.index(start_write), actual_trace.index(stop_write)
        traced_region = sum(line.startswith('R ') for line in actual_trace[first:last])
        traced_total = sum(line.startswith('R ') for line in actual_trace)
        if traced_region != region_retired or traced_total != total_retired:
            raise AssertionError('Timing and differential runs disagree on retired instruction counts')
        differential.append({'max_wait_cycles': stalls, 'events': len(actual_trace), 'result': 'PASS',
                             'simulator_summary': summary.strip().splitlines()[0], 'trace': trace_path})

    # Every traced run retires the same instructions; the zero-wait run also gives a cycle count to check.
    zero = next((d for d in differential if d['max_wait_cycles'] == 0), None)
    tb_cycles = int(re.search(r'cycles=(\d+)', zero['simulator_summary'])[1]) if zero else None
    profile = bench_profile.profile((zero or differential[0])['trace'], out / 'symbols.txt', out / 'bench.disasm.txt',
                                    mailbox, runs, region_cycles, total_cycles, tb_cycles)
    for d in differential:
        del d['trace']

    cycles_per_run = region_cycles / runs
    report = {
        'status': 'PASS',
        'benchmark': 'Dhrystone (riscv-tests edition, version string "C, Version 2.2")',
        'label': 'Non-compliant run, simulation (rubric evidence class E1)',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (ROOT / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'],
            'environment': 'bare metal, laboratory terminal trap', 'class': 'multicycle',
            'rtl_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': 'none (Icarus Verilog simulation)',
            'debug_trace': 'retirement trace ports present in the RTL',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'number_of_runs': runs,
        'timed_region': {'cycles': region_cycles, 'retired_instructions': region_retired,
                         'definition': 'from the start-marker store to the instruction before the stop-marker store'},
        'whole_program': {'cycles_after_reset': total_cycles, 'retired_instructions': total_retired},
        'cycles_per_run': cycles_per_run,
        'instructions_per_run': region_retired / runs,
        'clocks_per_instruction': region_cycles / region_retired,
        'dmips_per_mhz': runs * 1_000_000 / (region_cycles * DMIPS_DIVISOR),
        'result_checks': checks,
        'differential': differential,
        'profile': {
            'model_check': profile['model'],
            'fetch_share_of_clocks': profile['instructions'] * profile['model']['fetch'] / profile['clocks'],
            'classes_per_run': {k: {'instructions': n / runs, 'clocks': c / runs} for k, n, c in profile['classes']},
            'functions_per_run': {name: {'instructions': n / runs, 'clocks': c / runs, 'calls': calls / runs}
                                  for name, n, c, calls in profile['functions']},
            'fetch_reuse_share': profile['fetch_reuse']['share'],
            'estimates': profile['estimates'],
        },
        'instruction_names_executed': sorted(c for c in coverage if ':' not in c),
        'simulator': command(['iverilog', '-V']).splitlines()[0],
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'wall_seconds': {'timing_run': timing_seconds, 'reference_model': reference_seconds},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            'No M extension: multiply and divide use software routines in sim/cpu/bench/runtime.c.',
            'No cycle counter: timing comes from testbench markers; the program prints no time.',
            'Dhrystone local variables are not reachable from the port layer and are not checked.',
            'Per-MHz figures only; no clock frequency has been measured.',
            'Simulation run; not compliant with the benchmark\'s own reporting rules.',
        ],
    }
    card = rubric_score.score(ROOT, report)
    report['rubric'] = {'total': round(card['total'], 2), 'band': card['band'],
                        'evidence_assessed': card['evidence_assessed'], 'evidence_stale': card['evidence_stale'],
                        'dimensions': {d['id']: None if d['points'] is None else round(d['points'], 2)
                                       for d in card['dimensions']},
                        'gates_not_met': [g for g, v in card['gates'].items() if v['status'] != 'met'],
                        'claims_granted': [c['claim'] for c in card['claims'] if c['granted']],
                        'note': 'Automated self-assessment from cpu/rubric-evidence.json; not an independent review.'}
    (out / 'rubric.json').write_bytes((json.dumps(card, indent=2) + '\n').encode())
    (out / 'results.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    (out / 'profile.md').write_text(bench_profile.markdown(profile) + '\n', encoding='utf-8')
    log_path = runlog.write(ROOT, report, card, profile, bench_profile.markdown(profile)) if args.devlog else None
    if args.record:
        (ROOT / f'cpu/{args.benchmark}-results.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: Dhrystone, {runs} runs; all {len(checks)} result checks match.')
    print(f'PASS: differential traces match the reference model at wait cycles {args.stalls}.')
    print(f'Timed region: {region_cycles:,} cycles, {region_retired:,} instructions; '
          f'{cycles_per_run:,.1f} cycles per run, CPI {report["clocks_per_instruction"]:.3f}.')
    print(f'DMIPS/MHz: {report["dmips_per_mhz"]:.4f} (non-compliant run, simulation).')
    granted = report['rubric']['claims_granted']
    print(f'Rubric self-assessment: {card["total"]:.1f}/100 ({card["band"]}); claims granted: '
          f'{", ".join(granted) if granted else "none"}' + ('; evidence is stale' if card['evidence_stale'] else '') + '.')
    top = profile['functions'][0]
    print(f'Profile: fetch is {100 * report["profile"]["fetch_share_of_clocks"]:.1f}% of clocks; '
          f'busiest function `{top[0]}` takes {100 * top[2] / profile["clocks"]:.1f}% of clocks.')
    if log_path:
        print(f'Logged this run to {log_path} and indexed it in DEVLOG.md.')
    print(f'Results: {(out / "results.json").relative_to(ROOT).as_posix()}')


if __name__ == '__main__':
    main()
