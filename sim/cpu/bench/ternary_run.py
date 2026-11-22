"""Run the ternary-weight GEMV benchmark on the RTL (run_bench.py --benchmark ternary).

The program (ternary/tern_bench.c) runs scalar kernels over packed ternary weights (BitNet
b1.58-style, synthetic values): i2 (2-bit codes and multiplies, the I2_S idea), lut5w (5 trits per
byte, 256-entry sum tables per 5 activations, the TQ1_0 byte order) and bs8 (bit-serial: two weight
bit planes against eight activation bit planes with Zbb cpop), plus a read-bandwidth probe (stream:
sum of 64-bit words). Activations are int8, outputs exact int32. Weights, activations and the
reference outputs are generated natively (ternary/tern_export.py); the core never packs.
Each call (kernel x layer) is preceded by one load per 64-byte line of its weights (untimed), so with
an L2 large enough the weights are L2-resident, and with a smaller L2 (or a layer larger than it)
they stream from memory. Each call is bracketed by lap markers. This runner:

1. runs the image on the fast functional simulator rv_iss.c: calls, instruction counts and the
   result mailbox, which must equal the native reference (expected.json) word for word;
2. times each call on the chosen core:
   full     the whole program from reset on the timing bench, laps at the markers (T-small);
   sampled  K evenly spaced pieces per call from rv_iss checkpoints, each after a warm-up of the
            preceding instructions; call clocks are the timed clocks per instruction times the
            call's instructions, with the spread of piece CPI (lzma_run.phase_estimate);
3. trace-checks pieces (warm-up included) on tb_core against rv_iss, the memory wait-cycle
   settings alternating, unless --no-differential;
4. reports per call and per kernel: clocks, instructions, IPC, weights per clock, packed bytes
   read per clock and instructions per weight. Goals (Apple M6 reference estimates, 2026-11-22) are in GOAL_*.
Memory regimes are the SoC options of run_bench.py: flat (default), --l2-kib N with --l2-lat,
--mem-lat, --n-miss, --mem-gap. In sampled mode every piece starts with a cold L2 (the touch pass
is in the warm-up when the warm-up reaches back to it).
SPDX-License-Identifier: MIT
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import json
import platform
import re
import time

import bench_checkpoint
from lzma_run import ISS_SOURCE, SAMPLING, iss_binary, iss_call, phase_estimate
from rt_run import plan_pieces

SLOTS = ('i2', 'lut5w', 'bs8', 'stream', 'streamall')
MAGIC = 0x48434e424e524554  # "TERNBNCH"
FULL_LIMIT_INSTRUCTIONS = 12_000_000  # default mode: full at or below this many instructions
LABEL = 'Ternary-weight GEMV benchmark (scalar i2, lut5w, bs8 and a stream probe), simulation (rubric evidence class E1)'


# Goals, set 2026-11-22 03:37 ("M6 everywhere"); estimates, not M6 measurements (Apple publishes no M6 data).
# Scalar kernels: 1.30 x the laptop's weights per clock (Geekbench 6 single-core per GHz, M6 983 / X925 755;
# cpu/research/performance-targets.md; no FP/integer-specific bridge exists), laptop rows of
# cpu/ternary-benchmark-targets.md: T-small resident, T-2B4T cold (DRAM). Streaming bandwidth: Apple
# single-core DRAM 20-32 B/clk (M4 Max ~92 GB/s forum, unverified; M1 Max 102 GB/s AnandTech), not M6.
GOAL_WEIGHTS_PER_CLOCK = {'small': {'i2': 1.28, 'lut5w': 4.03, 'bs8': 4.04},
                          '2b4t': {'i2': 1.25, 'lut5w': 5.88, 'bs8': 4.50}}
GOAL_DRAM_B_PER_CLK_MIN, GOAL_DRAM_B_PER_CLK_MAX = 20.0, 32.0
GOAL_TEXT = ('Apple M6 reference (estimate, 2026-11-22): scalar kernels 1.30 x laptop weights/clk; DRAM streaming '
             '20-32 B/clk (M4/M1 Max figures, M6 unpublished)')


def calls_of(build):
    """The timed calls in program order: (id, kernel, layer, name)."""
    t = build['ternary']
    layers = len(t['expected']['layers'])
    calls = []
    for slot, kernel in enumerate(SLOTS):
        if not t['kernel_mask'] >> slot & 1:
            continue
        for li in range(1 if kernel == 'streamall' else layers):
            calls.append({'id': slot * (layers + 1) + li, 'kernel': kernel, 'layer': li,
                          'name': 'streamall' if kernel == 'streamall' else f'{kernel}_L{li}'})
    calls.sort(key=lambda c: (c['kernel'] != 'streamall', c['id']))  # streamall runs first
    return calls


def expected_words(build):
    t = build['ternary']
    ex = t['expected']
    layers = ex['layers']
    # bench_result(index) is word 2 + index: 2 magic, 3 mismatches, 4 weights, 5 mask | layers << 8, 6 + id outputs
    words = {2: MAGIC, 3: 0, 4: ex['weights'], 5: t['kernel_mask'] | len(layers) << 8}
    for c in calls_of(build):
        li = c['layer']
        if c['kernel'] == 'streamall':
            words[6 + c['id']] = ex['stream_all_sum']
        elif c['kernel'] == 'stream':
            words[6 + c['id']] = layers[li]['stream_sum']
        else:
            words[6 + c['id']] = layers[li]['y_fnv']
    return words


def check_words(words, build, what):
    want = expected_words(build)
    checks = []
    for key, value in sorted(want.items()):
        got = words.get(key)
        checks.append({'word': key, 'expected': value, 'actual': got, 'pass': got == value})
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError(f'{what}: results differ from the native reference: ' + '; '.join(
            f'word {c["word"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))
    if words.get(1) != 0:
        raise AssertionError(f'{what}: main() returned {words.get(1)}')
    return checks


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'ternary' not in build:
        raise SystemExit('build.json is not a ternary build')
    t = build['ternary']
    ex = t['expected']
    layers = ex['layers']
    calls = calls_of(build)
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    hex_images = build.get('hex_images', True)
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    piece, warmup = SAMPLING[args.core]
    piece = args.sample_instructions or piece
    warmup = args.warmup_instructions if args.warmup_instructions is not None else warmup
    exe, iss_compiler = iss_binary(root, sha)

    # 1. Functional run and result checks.
    started = time.perf_counter()
    summary = iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}')
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    marks = [tuple(m) for m in summary['marks']]
    want_marks = [1] + [v for c in calls for v in (0x10 + 2 * c['id'], 0x11 + 2 * c['id'])] + [2]
    if [v for v, _ in marks] != want_marks:
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    at = dict(marks)
    phases = {c['name']: (at[0x10 + 2 * c['id']], at[0x11 + 2 * c['id']]) for c in calls}
    words = {int(k): v for k, v in summary['mailbox'].items()}
    total_instructions = summary['instructions']
    checks = check_words(words, build, 'rv_iss')

    mode_default = args.tern_mode is None
    mode = args.tern_mode or ('full' if args.core == 'ooo' and total_instructions <= FULL_LIMIT_INSTRUCTIONS else 'sampled')
    per_phase = args.sample_pieces if args.sample_pieces is not None else (2 if mode == 'full' else 4)

    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches}, defines=wide)
    trace_sim = sim.build('tb_core', [rtl[0], snap / 'sim/cpu/tb_core.sv'], out / 'tb_core.vvp',
                          params={'MEM_BYTES': ram_bytes, **({'N_MISS': caches['N_MISS']} if 'N_MISS' in caches else {})},
                          defines=wide)
    jobs = max(1, min(args.jobs, 3))
    simulations, differential, call_clocks, sampling = [], [], {}, {}

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
        if not edges or not counters or set(laps) != set(want_marks[1:-1]):
            raise AssertionError('Timing run did not report its laps and region')
        for c in calls:
            call_clocks[c['name']] = laps[0x11 + 2 * c['id']] - laps[0x10 + 2 * c['id']]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and rv_iss disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        rtl_checks = check_words(rtl_words, build, 'RTL timing run')
        whole['cycles_after_reset'] = int(counters[1])
        whole['region_cycles'] = int(edges[2]) - int(edges[1])

    # 2-3. Pieces from rv_iss checkpoints: timed in sampled mode, trace-checked in both modes.
    plan = plan_pieces(phases, piece, warmup, per_phase)
    for k, p in enumerate(plan):
        if p['checkpoint'] < at[1]:  # inside the startup code: images above 1 MiB cannot restore there, so start from reset
            p['checkpoint'] = 0
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
        if index != p['checkpoint']:
            raise AssertionError('rv_iss state at the wrong instruction')
        if index == 0:
            image, info = bytes(memory), {'resume_pc': 0, 'resume_instruction': 0, 'stub_address': None,
                                          'stack_pointer': 0, 'stub_instructions': 0, 'stub_pcs': []}
        else:
            image, info = bench_checkpoint.build_from_state(regs, memory, pc, index, stub,
                                                            patches=[(mailbox, bytes(8))])
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
        iss_call(exe, ram_bytes, '--state', p['state'], '--max', p['checkpoint'] + n, '--trace', want_path,
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
        iss_call(exe, ram_bytes, *source, '--dump-at', ','.join(map(str, targets)), '--max', targets[-1],
                 '--dump-prefix', ckdir / 'state-')
        if state and state.name not in {f'state-{x}.state' for x in targets}:
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
        for name, (first, last) in phases.items():
            call_clocks[name], sampling[name] = phase_estimate([p for p in plan if p['phase'] == name], last - first)

    # 4. Metrics. Every figure is a measurement on this configuration; goals are estimates (see GOAL_*).
    report_calls, per_kernel = {}, {}
    for c in calls:
        first, last = phases[c['name']]
        instructions, clocks = last - first, call_clocks[c['name']]
        li, kernel = c['layer'], c['kernel']
        if kernel in ('stream', 'streamall'):
            weights, nbytes = 0, ex['stream_all_bytes'] if kernel == 'streamall' else layers[li]['bytes_i2']
        else:
            weights, nbytes = layers[li]['m'] * layers[li]['k'], layers[li][f'bytes_{kernel}']
        entry = {'kernel': kernel, 'layer': 'all' if kernel == 'streamall' else li, 'clocks': clocks,
                 'retired_instructions': instructions, 'ipc': instructions / clocks, 'weights': weights,
                 'packed_bytes': nbytes, 'bytes_per_clock': nbytes / clocks}
        if weights:
            entry.update({'weights_per_clock': weights / clocks, 'instructions_per_weight': instructions / weights,
                          'clocks_per_weight': clocks / weights})
        if c['name'] in sampling:
            entry['sampling'] = sampling[c['name']]
        report_calls[c['name']] = entry
        k = per_kernel.setdefault(kernel, {'clocks': 0, 'retired_instructions': 0, 'weights': 0, 'packed_bytes': 0})
        k['clocks'] += clocks
        k['retired_instructions'] += instructions
        k['weights'] += weights
        k['packed_bytes'] += nbytes
    for kernel, k in per_kernel.items():
        k['ipc'] = k['retired_instructions'] / k['clocks']
        k['bytes_per_clock'] = k['packed_bytes'] / k['clocks']
        if k['weights']:
            k['weights_per_clock'] = k['weights'] / k['clocks']
            k['instructions_per_weight'] = k['retired_instructions'] / k['weights']
    memory_model = {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64),
                    ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))}
    report = {
        'status': 'PASS',
        'benchmark': f'Ternary-weight GEMV, shape {ex["shape"]}: {ex["weights"]:,} weights in {len(layers)} layers',
        'label': LABEL, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'], 'float': 'none (integer kernels)',
            'environment': 'bare metal, laboratory terminal trap',
            'core': args.core, 'core_source': args.core_source or core_file,
            'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
            'memory_model': memory_model,
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'workload': {'shape': ex['shape'], 'layers': [{'m': l['m'], 'k': l['k']} for l in layers],
                     'weights': ex['weights'], 'kernels': t['kernels'], 'data_dir': t['data_dir'],
                     'touch_pass': 'one load per 64-byte line of the call\'s weights, untimed, before each call'},
        'functional_model': {'name': 'rv_iss.c', 'source_sha256': sha(root / ISS_SOURCE), 'compiler': iss_compiler,
                             'seconds': round(functional_seconds, 2), 'mips': summary['mips']},
        'mode': mode, 'mode_default': mode_default,
        'core_defines': list(getattr(args, 'ooo_defines', [])),
        'pieces': {'piece_instructions': piece, 'warmup_instructions': warmup, 'per_phase': per_phase,
                   'differential_every': None if args.no_differential else args.differential_every,
                   'pieces': [{k: p.get(k) for k in ('index', 'phase', 'ordinal', 'phase_pieces', 'begin', 'end',
                                                     'checkpoint', 'window', 'clocks', 'window_retired',
                                                     'window_overrun', 'resume_pc')} for p in plan]},
        'calls': report_calls, 'kernels': per_kernel,
        'whole_program': whole,
        'result_checks': checks, 'result_checks_source': 'rv_iss mailbox against the native reference (expected.json)',
        'rtl_result_checks': rtl_checks,
        'differential': differential,
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'], 'build_artifact_sha256': build['artifact_sha256'],
        'goal': GOAL_TEXT,
        'goal_reference': {'scalar_weights_per_clock': GOAL_WEIGHTS_PER_CLOCK, 'bytes_per_clock_dram_min': GOAL_DRAM_B_PER_CLK_MIN,
                           'bytes_per_clock_dram_max': GOAL_DRAM_B_PER_CLK_MAX},
        'limitations': [
            'Synthetic ternary weights (kernel speed does not depend on the values); no model is run.',
            'Each call is preceded by an untimed touch of its weights: with an L2 that holds them they are '
            'L2-resident, otherwise they stream from memory. A real decode streams a layer once per token.',
            'Sampled pieces start with cold caches and predictors after a warm-up; call clocks are estimates.' if mode == 'sampled'
            else 'Full mode: exact clocks of the whole program from reset.',
            'No cycle counter: timing comes from testbench markers or retirement windows. Per-clock figures only.',
        ],
    }
    result = out / f'results-{args.core}.json'
    result.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: ternary results equal the native reference (rv_iss, {total_instructions:,} instructions).')
    if rtl_checks:
        print('PASS: RTL timing-run mailbox equals the native reference.')
    print(f'PASS: differential traces match rv_iss ({len(differential)} pieces).' if differential else
          'Differential check skipped.')
    for name, e in report_calls.items():
        w = f'{e["weights_per_clock"]:.3f} weights/clk, {e["instructions_per_weight"]:.3f} instr/weight, ' if e['weights'] else ''
        print(f'{name}: {e["clocks"]:,} clocks, {e["retired_instructions"]:,} instr, IPC {e["ipc"]:.3f}, {w}'
              f'{e["bytes_per_clock"]:.4f} B/clk')
    for kernel, k in per_kernel.items():
        w = f'{k["weights_per_clock"]:.3f} weights/clk, ' if k['weights'] else ''
        print(f'TOTAL {kernel}: {k["clocks"]:,} clocks, IPC {k["ipc"]:.3f}, {w}{k["bytes_per_clock"]:.4f} B/clk')
    print(f'({report["label"]}; mode {mode}; memory {memory_model})')
    print(f'Results: {Path(os.path.relpath(result, root)).as_posix()}')
