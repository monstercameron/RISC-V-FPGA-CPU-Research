"""Run a built benchmark on the RTL, check its results and report cycle counts.

Needs Python 3.11+ and Icarus Verilog (Linux or Ubuntu/WSL). Build first with
build_bench.py. --sim verilator uses Verilator instead (much faster, 2-state:
registers start at 0, not X); Icarus stays the default and the cross-check for
logged results. See sim/cpu/simulator.py. Two checks run:

1. Timing: the core with its synchronous RAM wrapper counts clocks and retired
   instructions between the program's start and stop markers.
2. Differential: the core runs under the trace testbench, with and without
   memory wait cycles, and every retirement, memory write and the final trap
   must match the project's sequential reference model.

Results are simulation evidence (rubric class E1), not a compliant benchmark run.

--benchmark lzma runs the scaled-down 7-Zip LZMA kernel instead; lzma_run.py
describes its phases, checkpoint sampling and checks. --benchmark rt runs the
ray-tracing benchmark (RT-T traversal, RT-P smallpt); rt_run.py describes it.
--benchmark js runs the JavaScript benchmark (QuickJS-ng, nine kernels, timed second
call); js_run.py describes it. The sampled-mode options in the lzma group
(--sample-pieces, --sample-instructions, --warmup-instructions, --jobs, --no-differential,
--differential-every) apply to rt and js too, and --pieces and --warm-l2 to js.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import os
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
import simulator  # noqa: E402
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


# Every step (a compile or one simulation) is stopped after 5 minutes, so a hung core
# fails quickly instead of holding the machine.
def command(args, timeout=300):
    completed = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(f'Command failed: {" ".join(map(str, args))}\n{completed.stdout}{completed.stderr}')
    return completed.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--benchmark', choices=['dhrystone', 'lzma', 'rt', 'js', 'mm', 'ternary', 'stream'], default='dhrystone')
    parser.add_argument('--out-dir', help='Default: build/cpu/bench/<benchmark>')
    parser.add_argument('--stalls', type=int, nargs='+', default=[0, 7],
                        help='Maximum random memory wait cycles for each differential run')
    parser.add_argument('--max-cycles', type=int,
                        help='Clock limit per simulation (default 50,000,000; for lzma 40 clocks per instruction run)')
    parser.add_argument('--core', choices=('multicycle', 'pipe', 'ooo'), default='multicycle',
                        help='Core implementation: rtl/cpu/rv64_core.sv (multicycle) or rv64_pipe.sv (pipelined)')
    parser.add_argument('--record', action='store_true',
                        help='Also write the result to cpu/<benchmark>-results.json')
    parser.add_argument('--devlog', action='store_true',
                        help='Write this run, its rubric scorecard and profile to devlog/devlog-<commit>.md '
                             'and add a row to the run index in DEVLOG.md')
    parser.add_argument('--core-source', help='Time and check this core file instead of the released one '
                        '(a candidate; it is snapshotted and hashed under the released name)')
    parser.add_argument('--icache-beats', type=int,
                        help='Instruction-cache size in 8-byte beats (default 512 = 4 KiB for dhrystone, '
                             '8192 = 64 KiB for lzma)')
    parser.add_argument('--dcache-beats', type=int, help='Data-cache size in 8-byte beats (defaults as --icache-beats)')
    memory = parser.add_argument_group('SoC memory model (architecture 0.15.0; defaults keep the flat 1-clock memory)')
    memory.add_argument('--l2-kib', type=int, default=0, help='Shared L2 size in KiB (0 = no L2)')
    memory.add_argument('--l2-ways', type=int, default=8)
    memory.add_argument('--l2-line', type=int, default=64, help='L2 line in bytes')
    memory.add_argument('--l2-lat', type=int, default=12, help='Clocks for a read that hits the L2')
    memory.add_argument('--mem-lat', type=int, default=1, help='Clocks for a read from memory (an L2 miss, or every read without an L2)')
    memory.add_argument('--mem-gap', type=int, default=0, help='Clocks between DRAM line starts (SoC MEM_GAP, 0.16.0; 0 = unlimited bandwidth)')
    memory.add_argument('--l2-pf', type=int, default=0, help='L2 stream prefetcher trackers (SoC L2_PF; 0 = off)')
    memory.add_argument('--l2-pf-dist', type=int, default=16, help='Lines a confirmed stream prefetches ahead (SoC L2_PF_DIST)')
    memory.add_argument('--l2-pf-deg', type=int, default=4, help='Candidate tag lookups per advancing read (SoC L2_PF_DEG)')
    memory.add_argument('--l2-pf-n', type=int, default=16, help='Most prefetch fills in flight (SoC L2_PF_N)')
    memory.add_argument('--write-fill', type=int, choices=(0, 1), default=0,
                        help='1: a write that misses the L2 starts a fill of its line (SoC WRITE_FILL, 0.16.0)')
    knobs = parser.add_argument_group('out-of-order core knobs (compile-time defines; defaults keep the released core)')
    knobs.add_argument('--ld-lat', type=int, help='Load-to-use latency in clocks: define RV64_OOO_LD_LAT (0.14.10)')
    knobs.add_argument('--l0', type=int, help='L0 recent-beat buffer entries: define RV64_OOO_L0_N (0.15.4)')
    knobs.add_argument('--l0-lat', type=int, help='L0 hit latency in clocks: define RV64_OOO_L0_LAT (0.15.4)')
    knobs.add_argument('--dline', type=int, choices=(8, 16, 32, 64), default=8,
                       help='Data-cache line bytes: define RV64_OOO_DLINE (above 8 needs --n-miss >= 2)')
    knobs.add_argument('--fpu', action='store_true',
                       help='Build with RISC-V F and D: define RV64_OOO_FPU (0.17.0); integer programs run unchanged')
    knobs.add_argument('--vector', action='store_true',
                       help='Build with the RVV subset: define RV64_OOO_V (implies --fpu); programs without vector instructions run unchanged')
    knobs.add_argument('--vlen', type=int, choices=(128, 256, 512), help='With --vector: define RV64_OOO_VLEN (default 256)')
    knobs.add_argument('--n-miss', type=int, default=1,
                       help='Data misses in flight: core and SoC parameter N_MISS (0.16.0; above 1, split data reads)')
    simulator.add_argument(parser)
    lzma_options = parser.add_argument_group('lzma only')
    lzma_options.add_argument('--lzma-mode', choices=('full', 'sampled'),
                              help='full: whole program from reset; sampled: checkpointed pieces '
                                   '(default full, sampled for ooo under Icarus)')
    lzma_options.add_argument('--lzma-dict-log', type=int,
                              help='Dictionary 2^N (12-22): default --out-dir build/cpu/bench/lzma-dN-rv64imb; '
                                   'with --out-dir, the build must have this dictionary')
    lzma_options.add_argument('--functional', choices=('reference', 'iss'),
                              help='Functional model for phases, results and trace checks: reference.py '
                                   '(default for the 4 KiB dictionary) or the fast rv_iss.c (default above it)')
    lzma_options.add_argument('--sample-pieces', type=int,
                              help='Sampled mode: time at most this many evenly spaced pieces per phase and '
                                   'scale by instruction count (default: every piece)')
    lzma_options.add_argument('--pieces', help='rv_iss path, sampled mode: A:B times only plan pieces A..B-1 and '
                              'saves them (to split a long run into 5-minute invocations); merge reports from the '
                              'saved pieces')
    lzma_options.add_argument('--warm-l2', action='store_true',
                              help='Experimental: preload each piece\'s L2 tags from rv_iss\'s functional cache model')
    lzma_options.add_argument('--sample-instructions', type=int, help='Instructions per piece (sampled mode)')
    lzma_options.add_argument('--warmup-instructions', type=int, help='Warm-up before each piece (sampled mode)')
    lzma_options.add_argument('--jobs', type=int, default=3, help='Simulations run at once (sampled mode)')
    lzma_options.add_argument('--no-differential', action='store_true', help='Skip the piece trace checks')
    lzma_options.add_argument('--differential-every', type=int, default=1,
                              help='Trace-check every K-th piece of each phase (always the first)')
    rt_options = parser.add_argument_group('rt only')
    rt_options.add_argument('--rt-mode', choices=('full', 'sampled'),
                            help='full: whole program on the timing bench (small builds only); sampled (default): '
                                 '--sample-pieces pieces per phase (default 6) from rv_iss checkpoints')
    js_options = parser.add_argument_group('js only')
    js_options.add_argument('--js-mode', choices=('full', 'sampled'),
                            help='full: whole program on the timing bench (small builds only); sampled (default): '
                                 '--sample-pieces pieces per kernel (default 4) from rv_iss checkpoints')
    mm_options = parser.add_argument_group('mm only (mm_run.py)')
    mm_options.add_argument('--mm-mode', choices=('full', 'sampled'), help='full: whole program (default when it retires at most 15 M instructions); sampled: pieces per phase')
    mm_options.add_argument('--mm-kernels', help='sampled mode: time only these kernels, for example G1,V1b')
    tern_options = parser.add_argument_group('ternary only')
    tern_options.add_argument('--tern-mode', choices=('full', 'sampled'),
                              help='full: whole program on the timing bench (default up to 12 M instructions); '
                                   'sampled: --sample-pieces pieces per call (default 4) from rv_iss checkpoints')
    args = parser.parse_args()
    # Core knobs as Verilog defines for the out-of-order builds (timing and trace benches alike).
    if args.vlen and not args.vector: parser.error('--vlen needs --vector')
    if args.vector: args.fpu = True   # vector FP uses the F state
    args.ooo_knobs = {'RV64_OOO_LD_LAT': args.ld_lat, 'RV64_OOO_L0_N': args.l0, 'RV64_OOO_L0_LAT': args.l0_lat}
    args.ooo_defines = [f'{k}={v}' for k, v in args.ooo_knobs.items() if v is not None] + (['RV64_OOO_FPU'] if args.fpu else []) + ([f'RV64_OOO_DLINE={args.dline}'] if args.dline != 8 else [])
    args.ooo_defines += (['RV64_OOO_V'] + ([f'RV64_OOO_VLEN={args.vlen}'] if args.vlen else [])) if args.vector else []
    if args.ooo_defines and args.core != 'ooo':
        parser.error('--ld-lat, --l0, --l0-lat and --fpu apply to --core ooo only')
    if args.n_miss != 1 and (args.core != 'ooo' or not 1 <= args.n_miss <= 8):
        parser.error('--n-miss above 1 needs --core ooo, and must be 1 to 8')
    if args.devlog and (args.core_source or args.icache_beats or args.dcache_beats or args.l2_kib or args.mem_lat != 1 or args.mem_gap or args.write_fill
                        or args.ooo_defines or args.n_miss != 1):
        parser.error('--devlog records the released core in its standard configuration only')
    if (args.mm_mode or args.mm_kernels) and args.benchmark != 'mm':
        parser.error('--mm-mode and --mm-kernels apply to --benchmark mm only')
    if args.rt_mode and args.benchmark != 'rt':
        parser.error('--rt-mode applies to --benchmark rt only')
    if args.js_mode and args.benchmark != 'js':
        parser.error('--js-mode applies to --benchmark js only')
    if (args.pieces or args.warm_l2) and args.benchmark not in ('lzma', 'js'):
        parser.error('--pieces and --warm-l2 apply to --benchmark lzma and js only')
    if args.tern_mode and args.benchmark != 'ternary':
        parser.error('--tern-mode applies to --benchmark ternary only')
    if args.benchmark == 'stream' and args.devlog:
        parser.error('--devlog records Dhrystone runs only; log stream runs in DEVLOG.md by hand')
    if args.benchmark == 'ternary' and args.devlog:
        parser.error('--devlog records Dhrystone runs only; log ternary runs in DEVLOG.md by hand')
    if args.benchmark in ('lzma', 'rt', 'js', 'mm') and args.devlog:
        parser.error('--devlog records Dhrystone runs only; log LZMA runs in DEVLOG.md by hand')
    try:
        sim = simulator.get(args.sim)
    except simulator.SimulatorMissing as missing:
        parser.error(f'{missing}; on Windows use run_dhrystone.ps1')
    if args.lzma_dict_log is not None and args.benchmark != 'lzma':
        parser.error('--lzma-dict-log applies to --benchmark lzma only')
    default_dir = f'build/cpu/bench/{args.benchmark}'
    if args.benchmark == 'lzma' and args.lzma_dict_log is not None:
        default_dir = f'build/cpu/bench/lzma-d{args.lzma_dict_log}-rv64imb'
    if args.benchmark == 'rt':
        default_dir = 'build/cpu/bench/rt-g16s2i32-pt16x12x4-rv64imb'  # build_bench.py --benchmark rt
    if args.benchmark == 'js':  # build_bench.py --benchmark js [--isa rv64imfd_zba_zbb_zbs_zifencei]
        default_dir = 'build/cpu/bench/js-s1-' + ('rv64imfdb' if args.fpu else 'rv64imb')
    if args.benchmark == 'mm':
        default_dir = 'build/cpu/bench/mm-small-rv64imb'  # build_bench.py --benchmark mm
    if args.benchmark == 'ternary':
        default_dir = 'build/cpu/bench/ternary-small-i2+lut5w+bs8-rv64imb'  # build_bench.py --benchmark ternary
    if args.benchmark == 'stream':
        default_dir = 'build/cpu/bench/stream-rv64imb'  # build_bench.py --benchmark stream
    out = (ROOT / (args.out_dir or default_dir)).resolve()
    build = json.loads((out / 'build.json').read_bytes())
    if args.lzma_dict_log is not None and build.get('lzma', {}).get('dict_log') != args.lzma_dict_log:
        parser.error(f'{out} is not a 2^{args.lzma_dict_log}-dictionary lzma build')
    if args.benchmark not in ('lzma', 'rt', 'js', 'mm', 'ternary', 'stream') and args.max_cycles is None:
        args.max_cycles = 50_000_000
    for name, digest in build['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise SystemExit(f'Stale build: {name} changed since build_bench.py ran')
    for name, digest in build['artifact_sha256'].items():
        if sha(out / name) != digest:
            raise SystemExit(f'Stale or damaged build artifact: {name}')
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    core_file = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}[args.core]
    # Snapshot the sources at the start, so a run whose files change on disk midway
    # still compiles, times and hashes one revision (found by a Codex review, 2026-11-21).
    snap = out / 'source-snapshot'
    sources = [core_file, 'rtl/cpu/rv64_bram_soc.sv', 'sim/cpu/bench/tb_bench.sv', 'sim/cpu/tb_core.sv', 'cpu/VERSION']
    for name in sources:
        (snap / name).parent.mkdir(parents=True, exist_ok=True)
        source = Path(args.core_source).resolve() if (args.core_source and name == core_file) else ROOT / name
        shutil.copyfile(source, snap / name)
    # Cache sizes of the measured configuration (8-byte beats). 7-Zip runs default to 64 KiB each,
    # the L1 sizes of the Cortex-X925 they are compared with; Dhrystone keeps the SoC's 4 KiB.
    default_beats = 8192 if args.benchmark in ('lzma', 'rt', 'js', 'mm', 'ternary', 'stream') else 512
    args.icache_beats = args.icache_beats or default_beats
    args.dcache_beats = args.dcache_beats or default_beats
    caches = {'ICACHE_BEATS': args.icache_beats, 'DCACHE_BEATS': args.dcache_beats}
    # SoC memory-model parameters are passed only when they differ from the SoC defaults, so a
    # default run builds exactly the same simulator as before they existed.
    memory_defaults = {'L2_KIB': 0, 'L2_WAYS': 8, 'L2_LINE': 64, 'L2_LAT': 12, 'MEM_LAT': 1, 'N_MISS': 1,
                       'MEM_GAP': 0, 'WRITE_FILL': 0, 'L2_PF': 0, 'L2_PF_DIST': 16, 'L2_PF_DEG': 4, 'L2_PF_N': 16}
    memory_model = {'L2_KIB': args.l2_kib, 'L2_WAYS': args.l2_ways, 'L2_LINE': args.l2_line,
                    'L2_LAT': args.l2_lat, 'MEM_LAT': args.mem_lat, 'N_MISS': args.n_miss,
                    'MEM_GAP': args.mem_gap, 'WRITE_FILL': args.write_fill,
                    'L2_PF': args.l2_pf, 'L2_PF_DIST': args.l2_pf_dist, 'L2_PF_DEG': args.l2_pf_deg, 'L2_PF_N': args.l2_pf_n}
    caches.update({k: v for k, v in memory_model.items() if v != memory_defaults[k]})
    rtl = [snap / core_file, snap / 'rtl/cpu/rv64_bram_soc.sv']
    if args.benchmark == 'lzma':
        import lzma_run
        lzma_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return
    if args.benchmark == 'mm':
        import mm_run
        mm_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return
    if args.benchmark == 'rt':
        import rt_run
        rt_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return
    if args.benchmark == 'js':
        import js_run
        js_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return

    if args.benchmark == 'stream':
        import stream_run
        stream_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return

    if args.benchmark == 'ternary':
        import ternary_run
        ternary_run.run(args, ROOT, out, build, snap, rtl, core_file, command, sha, sim, caches)
        return

    # 1. Timing on the core plus synchronous RAM wrapper.
    wide = ['WIDE_TRACE', *args.ooo_defines] if args.core == 'ooo' else []
    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches}, defines=wide)
    started = time.perf_counter()
    output = command([*timing_sim, f'+image={out / "bench-words.hex"}', f'+mailbox={mailbox:x}',
                      f'+max_cycles={args.max_cycles}', f'+profile={out / "profile.trace"}'])
    timing_seconds = time.perf_counter() - started
    (out / 'timing-run.txt').write_text(output, encoding='utf-8')
    counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+) trap_pc=([0-9a-f]{16})', output)
    region = re.search(r'REGION cycles=(\d+) retirements=(\d+)', output)
    if not counters or not region:
        raise AssertionError('Timing run did not report its counters')
    total_cycles, total_retired = int(counters[1]), int(counters[2])
    region_cycles, soc_region_retired = int(region[1]), int(region[2])
    region_retired = None  # counted from the trace in program order, below
    words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.MULTILINE)}
    if words.get(1) != 0:
        raise AssertionError(f'main() returned {words.get(1)}, expected 0')
    runs = words.get(3)
    # The run count must be the build's fixed NUMBER_OF_RUNS, not only self-consistent
    # (found by a Codex review, 2026-11-21: a wrong count would pass its own check).
    header = (ROOT / 'sim/cpu/bench/vendor/dhrystone/dhrystone.h').read_text(encoding='latin-1')
    fixed = re.search(r'#define\s+NUMBER_OF_RUNS\s+(\d+)', header)
    if fixed is None or runs != int(fixed[1]):
        raise AssertionError(f'Dhrystone reported {runs} runs; the build fixes {fixed[1] if fixed else "?"}')
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
    trace_sim = sim.build('tb_core', [rtl[0], snap / 'sim/cpu/tb_core.sv'], out / 'tb_core.vvp',
                          params={'MEM_BYTES': ram_bytes, **({'N_MISS': args.n_miss} if args.n_miss != 1 else {})},
                          defines=wide)
    start_write = f'W {mailbox:016x} {1:016x} ff'
    stop_write = f'W {mailbox:016x} {2:016x} ff'
    differential = []
    for index, stalls in enumerate(args.stalls):
        trace_path = out / f'trace-stall{stalls}.trace'
        summary = command([*trace_sim, f'+image={out / "bench-bytes.hex"}', f'+trace={trace_path}',
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
        # Totals must match exactly. The timed region's edges may differ by up to two
        # instructions: with dual issue (0.5.0 and later) a marker store can retire in
        # the same clock as the next instruction, and the timing testbench snapshots
        # after both. The region's instruction count comes from the trace, in program order.
        if traced_total != total_retired or abs(traced_region - soc_region_retired) > 2:
            raise AssertionError('Timing and differential runs disagree on retired instruction counts')
        if region_retired is not None and traced_region != region_retired:
            raise AssertionError('Differential runs disagree with each other')
        region_retired = traced_region
        differential.append({'max_wait_cycles': stalls, 'events': len(actual_trace), 'result': 'PASS',
                             'simulator_summary': summary.strip().splitlines()[0]})

    profile = bench_profile.profile(out / 'profile.trace', out / 'symbols.txt', out / 'bench.disasm.txt',
                                    runs, region_cycles)
    if profile['instructions'] != soc_region_retired:
        raise AssertionError('Profile and timing run disagree on the timed instruction count')

    cycles_per_run = region_cycles / runs
    report = {
        'status': 'PASS',
        'benchmark': 'Dhrystone (riscv-tests edition, version string "C, Version 2.2")',
        'label': 'Non-compliant run, simulation (rubric evidence class E1)',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'],
            'environment': 'bare metal, laboratory terminal trap',
            'class': {'multicycle': 'multicycle', 'pipe': 'pipelined', 'ooo': 'out-of-order'}[args.core], 'core': args.core,
            'core_source': args.core_source or core_file,
            'cache_beats': {'icache': args.icache_beats, 'dcache': args.dcache_beats},
            'memory_model': {k.lower(): v for k, v in memory_model.items()} |
                            {'ld_lat': args.ld_lat, 'l0_n': args.l0, 'l0_lat': args.l0_lat, 'fpu': args.fpu, 'dline': args.dline,
                             'vector': args.vector, 'vlen': (args.vlen or 256) if args.vector else None},
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
            'debug_trace': 'retirement trace ports present in the RTL',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'runtime': build.get('runtime', 'reference'),
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
            'per_instruction_clock_sum': profile['clocks'],
            'state_clocks_per_run': {k: profile['totals'][k] / runs for k in ('fetch', 'execute', 'memory')},
            'fetch_share_of_clocks': profile['totals']['fetch'] / profile['clocks'],
            'bus_fetches_per_run': profile['totals']['fetch_misses'] / runs,
            'classes_per_run': {k: {f: v / runs for f, v in d.items()} for k, d in profile['classes'].items()},
            'functions_per_run': {name: {f: v / runs for f, v in d.items()} for name, d in profile['functions']},
            'instruction_cache_estimates': profile['cache'],
            'estimates': profile['estimates'],
        },
        'instruction_names_executed': sorted(c for c in coverage if ':' not in c),
        **sim.info(),
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
        label = build['isa'].split('_')[0] + ('b' if '_zbb' in build['isa'] else '')
        suffix = ('' if build['isa'] == 'rv64i_zifencei' else '-' + label) + \
            ('' if build.get('runtime', 'reference') == 'reference' else '-fastrt') +             ('' if args.core == 'multicycle' else '-' + args.core)
        (ROOT / f'cpu/{args.benchmark}{suffix}-results.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
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
          f'busiest function `{top[0]}` takes {100 * top[1]["clocks"] / profile["clocks"]:.1f}% of clocks.')
    if log_path:
        print(f'Logged this run to {log_path} and indexed it in DEVLOG.md.')
    print(f'Results: {Path(os.path.relpath(out / "results.json", ROOT)).as_posix()}')


if __name__ == '__main__':
    main()
