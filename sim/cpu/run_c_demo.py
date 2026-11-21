"""Run the compiled C workload on our RTL and measure vvp, not WSL startup.

Use Linux/WSL with Python 3.11+, Icarus Verilog and GNU time.
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
import statistics
import subprocess
import time
import zlib

from reference import execute

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/cpu/c-demo'
MASK = (1 << 64) - 1


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args):
    completed = subprocess.run([str(x) for x in args], capture_output=True,
                               text=True, timeout=120)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return completed.stdout


def expected_results():
    values = sorted([-17, 42, 0, 99, -5, 42, 7, 1, 1024, -300, 18, 9, -1, 256, 3, 64])
    fingerprint = 0
    for value in values:
        fingerprint = (((fingerprint << 7) | (fingerprint >> 57)) ^ (value & MASK)) & MASK
    a, b = 0, 1
    for _ in range(40):
        a, b = b, a + b
    payload = b'Custom RV64 core: C -> ELF -> BRAM -> RTL.\n' * 8
    return [0x43505544454d4f31, 0, sum(values), values[0] & MASK, values[-1], a,
            zlib.crc32(payload), fingerprint]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be between 1 and 20')
    if not all(shutil.which(tool) for tool in ('iverilog', 'vvp')) or not Path('/usr/bin/time').is_file():
        parser.error('Use Linux/WSL with iverilog, vvp and /usr/bin/time installed')
    build = json.loads((OUT/'build.json').read_bytes())
    for name, digest in build['input_sha256'].items():
        if sha(ROOT/name) != digest:
            raise RuntimeError('Stale firmware source: ' + name)
    for name, digest in build['artifact_sha256'].items():
        if sha(OUT/name) != digest:
            raise RuntimeError('Stale or damaged build artifact: ' + name)

    executable = OUT/'c-demo.vvp'
    compile_start = time.perf_counter()
    command(['iverilog', '-g2012', '-Wall', '-s', 'tb_c_demo', '-o', executable,
             ROOT/'rtl/cpu/rv64_core.sv', ROOT/'rtl/cpu/rv64_bram_soc.sv',
             ROOT/'sim/cpu/tb_c_demo.sv'])
    rtl_compile_seconds = time.perf_counter() - compile_start
    expected = expected_results()
    measurements = []
    previous_counters = None
    for index in range(args.repetitions):
        metrics = OUT/f'timing-{index+1}.txt'
        started = time.perf_counter()
        output = command(['/usr/bin/time', '-f', '%e %U %S %M', '-o', metrics,
                          'vvp', executable, f'+image={OUT / "firmware-bram.hex"}'])
        wall = time.perf_counter() - started
        (OUT/f'run-{index+1}.txt').write_text(output, encoding='utf-8')
        rows = re.findall(r'^RESULT (\d+) ([0-9a-fA-F]{16})$', output, re.MULTILINE)
        if [int(row[0]) for row in rows] != list(range(8)):
            raise AssertionError('Missing, duplicate or unknown result values')
        actual = [int(row[1], 16) for row in rows]
        if actual != expected:
            raise AssertionError(f'Wrong result: {actual}, expected {expected}')
        counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+) trap_pc=([0-9a-f]{16})', output)
        if not counters:
            raise AssertionError('Missing retirement and cycle counts')
        current = tuple(int(x, 16 if i == 2 else 10) for i, x in enumerate(counters.groups()))
        if previous_counters is not None and current != previous_counters:
            raise AssertionError('Nondeterministic RTL execution')
        previous_counters = current
        wall_gnu, user, system, peak_kib = map(float, metrics.read_text().split())
        measurements.append({'wall_seconds_including_time_wrapper': wall,
            'vvp_wall_seconds_gnu_time': wall_gnu, 'vvp_user_seconds': user,
            'vvp_system_seconds': system, 'vvp_peak_rss_kib': int(peak_kib)})

    # Separately compare every retired instruction and memory write to the
    # project's sequential interpreter. These traced runs are not the benchmark.
    binary = (OUT/'firmware.bin').read_bytes()
    image = binary.ljust(16384, b'\0')
    trace_expected, coverage = execute(image, max_steps=100000)
    (OUT/'firmware-byte.hex').write_text(''.join(f'{byte:02x}\n' for byte in image), encoding='ascii')
    trace_executable = OUT/'c-demo-trace.vvp'
    command(['iverilog', '-g2012', '-Wall', '-s', 'tb_core', '-o', trace_executable,
             ROOT/'rtl/cpu/rv64_core.sv', ROOT/'sim/cpu/tb_core.sv'])
    trace_path = OUT/'retirement.trace'
    trace_summary = command(['vvp', trace_executable, f'+image={OUT / "firmware-byte.hex"}',
                             f'+trace={trace_path}', '+stall=0', '+seed=1'])
    actual_trace = trace_path.read_text().splitlines()
    if actual_trace != trace_expected:
        raise AssertionError('RTL retirement/memory/trap trace differs from the sequential reference')
    retired = sum(line.startswith('R ') for line in actual_trace)
    cycles, soc_retired, trap_pc = previous_counters
    if retired != soc_retired or actual_trace[-1] != f'T {trap_pc:016x} 0000000000000003 0000000000000000':
        raise AssertionError('SoC and differential execution disagree')
    for index, value in enumerate(expected):
        if f'W {0x3000 + index*8:016x} {value:016x} ff' not in actual_trace:
            raise AssertionError('Missing expected mailbox write in differential trace')

    names = ['completion_magic', 'status', 'sum', 'minimum_twos_complement', 'maximum',
             'fibonacci_40', 'crc32_344_bytes', 'sorted_fingerprint']
    median_wall = statistics.median(item['wall_seconds_including_time_wrapper'] for item in measurements)
    sources = ['rtl/cpu/rv64_core.sv', 'rtl/cpu/rv64_bram_soc.sv',
               'sim/cpu/c_demo.c', 'sim/cpu/start.S', 'sim/cpu/link.ld',
               'sim/cpu/build_firmware.py', 'sim/cpu/tb_c_demo.sv',
               'sim/cpu/run_c_demo.py', 'sim/cpu/reference.py', 'sim/cpu/tb_core.sv']
    report = {'status': 'PASS', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'simulator': command(['iverilog', '-V']).splitlines()[0],
        'build': build, 'rtl_compile_wall_seconds': rtl_compile_seconds,
        'expected': {name: f'{value:016x}' for name, value in zip(names, expected)},
        'actual': {name: f'{value:016x}' for name, value in zip(names, actual)},
        'soc_cycles_after_reset': cycles, 'retired_instructions': retired,
        'measurements': measurements,
        'median_simulation_wall_seconds': median_wall,
        'maximum_vvp_peak_rss_mib': max(item['vvp_peak_rss_kib'] for item in measurements)/1024,
        'simulated_cycles_per_wall_second': cycles/median_wall,
        'differential': {'status': 'PASS', 'events': len(actual_trace), 'max_wait_cycles': 0,
                         'summary': trace_summary.strip(), 'trace_bytes': trace_path.stat().st_size,
                         'instruction_names': sorted(coverage)},
        'source_sha256': {name: sha(ROOT/name) for name in sources},
        'scope': 'One small RV64I/FENCE.I core with 16 KiB RAM; no waveform dump in timing runs. '
                 'Wall time includes GNU time/process launch and image loading, excludes WSL startup, '
                 'C compilation, RTL compilation and the separate differential check. '
                 'Peak RSS is the vvp process, not the whole WSL VM or editor. '
                 'Local sequential reference is not official ISA certification. '
                 'Not a full RVA23 core, physical FPGA measurement or LLM simulation.'}
    (OUT/'results.json').write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(f'PASS: {retired:,} retired instructions, {cycles:,} SoC cycles, all 8 results correct.')
    print(f'PASS: all {len(actual_trace):,} differential trace events match.')
    print(f'Median vvp run ({args.repetitions} runs): {median_wall:.3f} s; '
          f'maximum peak RSS: {report["maximum_vvp_peak_rss_mib"]:.2f} MiB.')
    print('Results: build/cpu/c-demo/results.json')


if __name__ == '__main__':
    main()
