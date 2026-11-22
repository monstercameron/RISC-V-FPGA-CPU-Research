"""Run the mm benchmark on the RTL (run_bench.py --benchmark mm).

The program (mm/mm_bench.c, mm/mm_kernels.c; shapes and layouts in mm/mm_bench.h) runs the matrix
kernels one after the other and marks the phases: G1 int8 GEMM, G2 BF16 GEMM, G3 FP32 GEMM (64x64x64),
V1 int8 GEMV, V3 Q4_0-style int4 GEMV, V4 FP32 GEMV and, in the full profile only, V1b int8 GEMV larger
than the 4 MiB L2. This runner:

1. runs the image on the fast functional simulator rv_iss.c: phases, instruction counts and the result
   mailbox (an FNV-1a 64 checksum per kernel output), which must equal the native reference that
   mm/mm_export.sh computed from the same kernel sources with -ffp-contract=off, word for word. Integer
   kernels are exact; the FP kernels are ordered (ascending k, one rounding per addition, no FMA), so
   the checksums are bit-exact too;
2. times the phases on the chosen core:
   full     the whole program from reset on the timing bench, laps at the markers (the default when the
            functional run retires at most FULL_LIMIT instructions: the small profile with hard float);
   sampled  K evenly spaced pieces per phase from rv_iss checkpoints, each after a warm-up of the
            preceding instructions (rt_run.plan_pieces, lzma_run.phase_estimate). Pieces start with cold
            caches and predictors (the 2026-11-22 01:11 artifact: it understated RT-T 2.1-2.3x), so a
            full run is preferred wherever one fits; the 8 MiB V1b is sampled-only;
3. trace-checks every timed piece on tb_core against rv_iss unless --no-differential;
4. reports per kernel clocks, instructions, IPC, MACs per clock and, for the GEMVs, weight bytes per
   clock, against the laptop reference (cpu/mm-benchmark-targets.md). No goal is set.

The RAM holds the generated inputs (mm_data.S, .incbin), so the simulator spends no instructions
making them. Hard float needs --core ooo --fpu; the soft-float build (rv64imb) runs on every core.
SPDX-License-Identifier: MIT
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import platform
import re
import time

import bench_checkpoint
from lzma_run import ISS_SOURCE, SAMPLING, iss_binary, iss_call, phase_estimate
from rt_run import plan_pieces

FULL_LIMIT = 15_000_000
LABEL = 'mm benchmark (matrix multiplication and LLM-style kernels, scalar C), simulation (rubric evidence class E1)'
COLS = {'G1': 64, 'G2': 64, 'G3': 64, 'V1': 2048, 'V3': 2048, 'V4': 1024, 'V1b': 2048}
# Laptop reference per clock (cpu/mm-benchmark-targets.md): MACs per clock of the same scalar C, clang 18 -O2
# without the auto-vectoriser, one Cortex-X925 core. No goal is set (the user decides goals).
LAPTOP = {}


def kernel_id(name):
    return name.split('_')[0]


def kernel_shapes(rows):
    """Per kernel: MACs, weight bytes (GEMVs only) and the shape text."""
    q4_row = 2048 // 32 * 18
    shapes = {'G1': (64 ** 3, None, '64x64x64 int8 -> int32'), 'G2': (64 ** 3, None, '64x64x64 BF16 -> FP32'),
              'G3': (64 ** 3, None, '64x64x64 FP32')}
    shapes['V1'] = (rows['v1'] * 2048, rows['v1'] * 2048, f'int8 GEMV {rows["v1"]} rows x 2048 -> int32')
    shapes['V3'] = (rows['v3'] * 2048, rows['v3'] * q4_row, f'Q4_0 int4 GEMV {rows["v3"]} rows x 2048 -> FP32')
    shapes['V4'] = (rows['v4'] * 1024, rows['v4'] * 4096, f'FP32 GEMV {rows["v4"]} rows x 1024')
    if rows['v1b']:
        shapes['V1b'] = (rows['v1b'] * 2048, rows['v1b'] * 2048, f'int8 GEMV {rows["v1b"]} rows x 2048, 8 MiB')
    return shapes


def check_words(words, expected, what):
    checks = []
    for key, want in sorted(expected['mailbox'].items(), key=lambda kv: int(kv[0])):
        got = words.get(int(key))
        index = int(key) - 2
        name = 'magic' if index == 0 else 'rows' if index == 1 else f'checksum {expected["kernels"][index - 2]}'
        checks.append({'word': int(key), 'name': name, 'expected': want, 'actual': got, 'pass': got == want})
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError(f'{what}: results differ from the native reference: ' + '; '.join(
            f'{c["name"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))
    if words.get(1) != 0:
        raise AssertionError(f'{what}: main() returned {words.get(1)}')
    return checks


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'mm' not in build:
        raise SystemExit('build.json is not an mm build')
    mm = build['mm']
    fp = not mm['soft_float']
    if fp and not (args.core == 'ooo' and getattr(args, 'fpu', False)):
        raise SystemExit('This build uses the F and D extensions: run it with --core ooo --fpu (RV64_OOO_FPU, '
                         'architecture 0.17.0); the multicycle and pipelined cores have no F or D')
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    hex_images = build.get('hex_images', True)
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    kernels = [kernel_id(k) for k in mm['kernels']]
    shapes = kernel_shapes(mm['rows'])
    marks_expected = [1, *range(0x20, 0x20 + len(kernels) - 1), 2]
    phases_of = {k: (marks_expected[i], marks_expected[i + 1]) for i, k in enumerate(kernels)}
    piece, warmup = SAMPLING[args.core]
    piece = args.sample_instructions or piece
    warmup = args.warmup_instructions if args.warmup_instructions is not None else warmup
    per_phase = args.sample_pieces if args.sample_pieces is not None else 6
    exe, iss_compiler = iss_binary(root, sha)

    def iss(*options, **kw):
        return iss_call(exe, ram_bytes, *(['--fp', '1'] if fp else []), *options, **kw)

    # 1. Functional run and result checks.
    started = time.perf_counter()
    summary = iss('--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}')
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    marks = [tuple(m) for m in summary['marks']]
    if [v for v, _ in marks] != marks_expected:
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    at = dict(marks)
    phases = {k: (at[a], at[b]) for k, (a, b) in phases_of.items()}
    words = {int(k): v for k, v in summary['mailbox'].items()}
    total_instructions = summary['instructions']
    checks = check_words(words, mm['expected'], 'rv_iss')
    selected = [k for k in kernels if not args.mm_kernels or k in args.mm_kernels.split(',')]
    if not selected:
        raise SystemExit(f'--mm-kernels names none of {kernels}')

    mode_default = args.mm_mode is None
    mode = args.mm_mode or ('full' if total_instructions <= FULL_LIMIT else 'sampled')
    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches}, defines=wide)
    trace_sim = sim.build('tb_core', [rtl[0], snap / 'sim/cpu/tb_core.sv'], out / 'tb_core.vvp',
                          params={'MEM_BYTES': ram_bytes, **({'N_MISS': caches['N_MISS']} if 'N_MISS' in caches else {})},
                          defines=wide)
    jobs = max(1, min(args.jobs, 3))
    simulations, differential, phase_clocks, sampling = [], [], {}, {}

    def simulate(arguments, name):
        t0 = time.perf_counter()
        text = command(arguments)
        simulations.append({'run': name, 'wall_seconds': round(time.perf_counter() - t0, 1)})
        return text

    whole = {'retired_instructions': total_instructions}
    rtl_checks = None
    if mode == 'full':
        image_arg = f'+image={out / "bench-words.hex"}' if hex_images else f'+image_bin={out / "bench-words-be.bin"}'
        max_cycles = args.max_cycles or max(50_000_000, 40 * total_instructions)
        output = simulate([*timing_sim, image_arg, f'+mailbox={mailbox:x}', f'+max_cycles={max_cycles}'],
                          'timing, full program')
        (out / 'timing-run.txt').write_text(output, encoding='utf-8')
        laps = {int(v): int(c) for v, c, _ in re.findall(r'^LAP (\d+) cycles=(\d+) retirements=(\d+)$', output, re.M)}
        edges = re.search(r'EDGES start_cycle=(\d+) start_retired=\d+ stop_cycle=(\d+)', output)
        counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+)', output)
        if not edges or not counters or set(laps) != set(marks_expected[1:-1]):
            raise AssertionError('Timing run did not report its laps and region')
        clock_at = {1: int(edges[1]), 2: int(edges[2]), **laps}
        for k, (a, b) in phases_of.items():
            phase_clocks[k] = clock_at[b] - clock_at[a]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and rv_iss disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        rtl_checks = check_words(rtl_words, mm['expected'], 'RTL timing run')
        whole['cycles_after_reset'] = int(counters[1])

    # 2-3. Pieces from rv_iss checkpoints: timed in sampled mode, trace-checked in both modes.
    plan = plan_pieces({k: phases[k] for k in selected}, piece, warmup, per_phase)
    for k, p in enumerate(plan):
        p['index'] = k
        p['check'] = not args.no_differential and p['ordinal'] % args.differential_every == 0
    for k, p in enumerate([p for p in plan if p['check']]):
        p['stalls'] = args.stalls[k % len(args.stalls)]
    work = [p for p in plan if mode == 'sampled' or p['check']]
    ckdir = out / 'checkpoints'
    ckdir.mkdir(exist_ok=True)
    for old in ckdir.glob('*'):
        old.unlink()
    stub = mailbox - build['stack_reserve_bytes']

    def prepare(p):
        regs, memory, pc, index = bench_checkpoint.read_iss_state(p['state'])
        fstate = bench_checkpoint.read_iss_fstate(p['state'])
        if index != p['checkpoint']:
            raise AssertionError('rv_iss state at the wrong instruction')
        if index == 0:
            image, info = bytes(memory), {'resume_pc': 0, 'resume_instruction': 0, 'stub_address': None,
                                          'stack_pointer': 0, 'stub_instructions': 0, 'stub_pcs': []}
        else:
            image, info = bench_checkpoint.build_from_state(regs, memory, pc, index, stub,
                                                            patches=[(mailbox, bytes(8))], fstate=fstate)
        p.update(info)
        p['be'], p['le'] = bench_checkpoint.write_binaries(image, ckdir, f'piece{p["index"]:04d}', little=p['check'])
        p['skip'] = p['begin'] - p['checkpoint']
        p['window'] = (p['stub_instructions'] + p['skip'], p['stub_instructions'] + p['skip'] + p['end'] - p['begin'])

    def time_piece(p):
        output = simulate([*timing_sim, f'+image_bin={p["be"]}', f'+mailbox={mailbox:x}',
                           f'+max_cycles={max(50_000_000, 40 * p["window"][1])}', f'+sample_from={p["window"][0]}',
                           f'+sample_to={p["window"][1]}'], f'timing, piece {p["index"]}')
        m = re.search(r'^SAMPLE cycles=(\d+) retirements=(\d+) from_cycle=(\d+) from_retired=(\d+) '
                      r'to_cycle=(\d+) to_retired=(\d+) trapped=(\d+)$', output, re.M)
        if not m or int(m[7]):
            raise AssertionError(f'piece {p["index"]}: no sample window\n{output}')
        p['clocks'], p['window_retired'] = int(m[1]), int(m[2])
        p['window_overrun'] = (int(m[4]) - p['window'][0], int(m[6]) - p['window'][1])

    def check_piece(p):
        stalls, n_stub = p['stalls'], p['stub_instructions']
        trace_path = ckdir / f'piece{p["index"]:04d}-stall{stalls}.trace'
        want_path = ckdir / f'piece{p["index"]:04d}-iss.trace'
        limit = p['window'][1]
        n = limit - n_stub
        iss('--state', p['state'], '--max', p['checkpoint'] + n, '--trace', want_path,
            '--trace-from', p['checkpoint'], '--trace-to', p['checkpoint'] + n)
        text = simulate([*trace_sim, f'+image_bin={p["le"]}', f'+trace={trace_path}', f'+stall={stalls}',
                         f'+seed={p["index"] + 1}', f'+max_cycles={max(50_000_000, 100 * limit)}',
                         f'+max_retired={limit}'], f'differential, piece {p["index"]}, wait cycles {stalls}')
        actual = trace_path.read_text().splitlines()
        want = want_path.read_text().splitlines()
        trace_path.unlink()
        want_path.unlink()
        rs = [i for i, line in enumerate(actual) if line[0] == 'R']
        if len(rs) < limit:
            raise AssertionError(f'piece {p["index"]}: trace ended after {len(rs)} retirements')
        got = actual[(rs[n_stub - 1] + 1 if n_stub else 0):rs[limit - 1] + 1]
        if got != want:
            for event, (a, e) in enumerate(zip(got + ['<missing>'] * len(want), want + ['<missing>'] * len(got))):
                if a != e:
                    raise AssertionError(f'piece {p["index"]} trace differs at event {event} (stall {stalls}):\n'
                                         f'actual {a}\nexpect {e}')
        if [int(actual[i][2:18], 16) for i in rs[:len(p['stub_pcs'])]] != p['stub_pcs']:
            raise AssertionError(f'piece {p["index"]}: restore stub did not run as built')
        differential.append({'scope': f'piece {p["index"]} ({p["phase"]})', 'max_wait_cycles': stalls,
                             'events': len(got), 'result': 'PASS', 'simulator_summary': text.strip().splitlines()[0]})

    def piece_job(p):
        prepare(p)
        if mode == 'sampled':
            time_piece(p)
        if p['check']:
            check_piece(p)
        for name in ('be', 'le'):
            if p[name] is not None:
                p[name].unlink()
        p['be'] = p['le'] = None

    state = None
    for start in range(0, len(work), jobs):
        batch = work[start:start + jobs]
        targets = sorted({p['checkpoint'] for p in batch})
        source = ['--state', state] if state else ['--image', out / 'bench.bin']
        iss(*source, '--dump-at', ','.join(map(str, targets)), '--max', targets[-1], '--dump-prefix', ckdir / 'state-')
        if state and state.name not in {f'state-{t}.state' for t in targets}:
            state.unlink()
        for p in batch:
            p['state'] = ckdir / f'state-{p["checkpoint"]}.state'
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(piece_job, batch))
        keep = ckdir / f'state-{targets[-1]}.state'
        for p in batch:
            if p['state'] != keep and p['state'].exists():
                p['state'].unlink()
        state = keep
        print(f'  pieces {start + 1}-{start + len(batch)} of {len(work)} done', flush=True)
    if state and state.exists():
        state.unlink()
    if mode == 'sampled':
        for k in selected:
            first, last = phases[k]
            phase_clocks[k], sampling[k] = phase_estimate([p for p in plan if p['phase'] == k], last - first)

    # 4. Per kernel metrics against the laptop reference.
    report_phases = {}
    for k, clocks in phase_clocks.items():
        if k not in selected:
            continue
        first, last = phases[k]
        instructions = last - first
        macs, weight_bytes, shape = shapes[k]
        entry = {'shape': shape, 'clocks': clocks, 'retired_instructions': instructions, 'ipc': instructions / clocks,
                 'macs': macs, 'macs_per_clock': macs / clocks, 'instructions_per_mac': instructions / macs}
        if weight_bytes:
            entry['weight_bytes'] = weight_bytes
            entry['weight_bytes_per_clock'] = weight_bytes / clocks
        if k in LAPTOP:
            entry['laptop_scalar_macs_per_clock'] = LAPTOP[k]
            entry['fraction_of_laptop_scalar'] = entry['macs_per_clock'] / LAPTOP[k]
        if k in sampling:
            entry['sampling'] = sampling[k]
        report_phases[k] = entry
    report = {
        'status': 'PASS',
        'benchmark': 'mm: matrix multiplication and LLM-style kernels (G1-G3 GEMM, V1/V3/V4/V1b GEMV), scalar C',
        'label': LABEL + ('; soft-float baseline: the core has no F, D or V' if mm['soft_float'] else ''),
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'goal': 'not set (user to decide)',
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'], 'float': 'soft (compiler-rt addsf3/mulsf3)' if mm['soft_float'] else 'F/D',
            'environment': 'bare metal, laboratory terminal trap',
            'core': args.core, 'core_source': args.core_source or core_file,
            'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
            'memory_model': {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64),
                             ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))},
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'workload': {'profile': mm['profile'], 'rows': mm['rows'], 'variant': mm['variant'], 'data_dir': mm['data_dir'],
                     'data_bytes': mm['data_bytes'], 'kernels': mm['kernels']},
        'functional_model': {'name': 'rv_iss.c', 'source_sha256': sha(root / ISS_SOURCE), 'compiler': iss_compiler,
                             'seconds': round(functional_seconds, 2), 'mips': summary['mips']},
        'mode': mode, 'mode_default': mode_default, 'fpu': fp,
        'core_defines': list(getattr(args, 'ooo_defines', [])),
        'pieces': {'piece_instructions': piece, 'warmup_instructions': warmup, 'per_phase': per_phase,
                   'differential_every': None if args.no_differential else args.differential_every,
                   'pieces': [{k: p.get(k) for k in ('index', 'phase', 'ordinal', 'phase_pieces', 'begin', 'end',
                                                     'checkpoint', 'window', 'clocks', 'window_retired',
                                                     'window_overrun', 'resume_pc')} for p in plan]},
        'phases': report_phases,
        'phase_definitions': {k: f'marker {hex(a)} to {hex(b)}: {shapes[k][2]}' for k, (a, b) in phases_of.items()},
        'whole_program': whole,
        'result_checks': checks,
        'result_checks_source': 'rv_iss mailbox against expected.json (native reference, mm_native.c)',
        'rtl_result_checks': rtl_checks,
        'differential': differential,
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            'Soft-float baseline: every FP32 operation is a compiler-rt call; not a measure of an FP pipeline.'
            if mm['soft_float'] else 'F/D build, scalar kernels (no vector unit).',
            'The small profile runs 128-256 rows of each GEMV (cold weights, streamed once); the full profile is sampled.',
            'Each kernel runs once from cold caches and predictors (no warm-up pass); the laptop figures are warm medians.',
            'Sampled pieces start with cold caches and predictors after a warm-up; phase clocks are estimates.',
            'No cycle counter: timing comes from testbench markers or retirement windows. Per-clock figures only.',
        ],
    }
    (out / f'results-{args.core}.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: mm results equal the native reference (rv_iss, {total_instructions:,} instructions, '
          f'{len(kernels)} kernel checksums).')
    if rtl_checks:
        print('PASS: RTL timing-run mailbox equals the native reference.')
    print(f'PASS: differential traces match rv_iss ({len(differential)} pieces).' if differential else
          'Differential check skipped.')
    for k, ph in report_phases.items():
        extra = ''
        if 'sampling' in ph and not ph['sampling']['complete']:
            s = ph['sampling']
            extra = f' [sampled {s["pieces_timed"]} pieces, {100 * s["fraction_timed"]:.2f}%, 95% CI +-{100 * s["ci95_relative"]:.1f}%]'
        bw = f', {ph["weight_bytes_per_clock"]:.3f} B/clk' if 'weight_bytes_per_clock' in ph else ''
        print(f'{k} ({ph["shape"]}): {ph["clocks"]:,} clocks, {ph["retired_instructions"]:,} instr, IPC {ph["ipc"]:.3f}, '
              f'{ph["macs_per_clock"]:.4f} MAC/clk{bw}{extra}')
    print(f'({report["label"]}; goal: not set)')
    print(f'Results: {(out / f"results-{args.core}.json").relative_to(root).as_posix()}')
