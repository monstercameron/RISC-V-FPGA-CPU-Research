"""Run the JavaScript benchmark on the RTL (run_bench.py --benchmark js).

The program is QuickJS-ng v0.18.0 running nine original kernels (js/kernels.js: props, sched,
navier, sha256, json, regex, strings, dom, funcs). Each kernel runs twice in one process; the
second call is the timed one, so code, data and predictors are warm on both machines. The
markers are 0x10+k (warm call), 0x20+k (timed call) and 0x30+k (end). This runner:

1. runs the image on the fast functional simulator rv_iss.c (with --fp 1 for an F/D build):
   phases, instruction counts and the result mailbox, which must equal the native reference
   that js/js_native.sh recorded (expected.json): the output hash and length, and each
   kernel's own output line hash;
2. times each kernel's timed call on the chosen core:
   full     the whole program from reset on the timing bench, laps at the markers (only for
            small builds: the scale-1 program is about 600 M instructions);
   sampled  K evenly spaced pieces per timed call from rv_iss checkpoints, each after a
            detailed warm-up of the preceding instructions (the default 2 M instructions
            reaches back into the warm call for the first pieces); kernel clocks are the timed
            clocks per instruction times the call's instructions, with the spread of piece
            CPI (lzma_run.phase_estimate). --warm-l2 also preloads each piece's L2 tags from
            rv_iss's cache model (needs --l2-kib). --pieces A:B and --pieces merge split a long
            sampled run into invocations of at most 5 minutes, as for lzma;
3. trace-checks timed pieces (warm-up included) on tb_core against rv_iss, the memory
   wait-cycle settings alternating, unless --no-differential;
4. reports, per kernel and in total, clocks, instructions, IPC and the fraction of the goal:
   1.30 x the laptop's per-clock rate, the Apple M6 reference (cpu/js-benchmark-targets.md). The total is the geometric
   mean over the kernels of laptop cycles / our clocks.
SPDX-License-Identifier: MIT
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import functools
import json
import math
import platform
import re
import time

import bench_checkpoint
from lzma_run import ISS_SOURCE, iss_binary, iss_call, phase_estimate
from rt_run import plan_pieces

KERNELS = ('props', 'sched', 'navier', 'sha256', 'json', 'regex', 'strings', 'dom', 'funcs')
MAGIC = 0x48434e45424a5351  # "QJSBENCH"
# Apple M6 reference, set 2026-11-22 03:37 ("M6 everywhere"): 1.30 = Geekbench 6 single-core per GHz, M6 983 /
# Cortex-X925 755 (Notebookcheck; cpu/research/performance-targets.md). An estimate bridged from the laptop, not
# an M6 measurement. Previously 1.5 (laptop + 50%).
GOAL_FACTOR = 1.30
# Sampling defaults for the out-of-order core: 2 M-instruction warm-up, 250 K-instruction pieces,
# 4 pieces per kernel (js-benchmark-targets.md, "Sampling", for the warm-up study behind them).
SAMPLE_PIECE, SAMPLE_WARMUP, SAMPLE_PER_KERNEL = 250_000, 2_000_000, 4
LABEL = 'JavaScript benchmark (QuickJS-ng 0.18.0 interpreter, 9 kernels), simulation (rubric evidence class E1)'
# Laptop reference (cpu/js-benchmark-targets.md, measured 2026-11-22 01:58-01:59): Cortex-X925, vCPU 19,
# aarch64 WSL Ubuntu 24.04, clang 18.1.3 -O2, the same engine, harness and script, glibc. Per kernel: the
# median CPU cycles of the timed (second) call over 16 runs in two sessions (7 + 9, clock ramped), and the
# median AArch64 instructions of the first session (the second is within 0.1%).
LAPTOP = {
    'props': (4_224_946, 22_331_315), 'sched': (4_902_544, 20_932_234), 'navier': (3_869_884, 22_075_942),
    'sha256': (4_574_128, 23_602_824), 'json': (4_594_272, 26_289_559), 'regex': (3_879_336, 22_643_462),
    'strings': (6_366_042, 36_028_535), 'dom': (6_141_912, 26_336_185), 'funcs': (3_544_158, 17_552_382),
}


def check_words(words, expected, what):
    lines = expected['lines']
    want = {2: MAGIC, 3: expected['hash'], 4: expected['bytes'], 5: 0, 8: len(lines),
            **{9 + i: line['fnv1a64'] for i, line in enumerate(lines)}}
    names = {2: 'magic', 3: 'output hash', 4: 'output bytes', 5: 'exception', 8: 'lines',
             **{9 + i: f'{line["kernel"]} line hash' for i, line in enumerate(lines)}}
    checks = [{'word': k, 'name': names[k], 'expected': v, 'actual': words.get(k), 'pass': words.get(k) == v}
              for k, v in want.items()]
    if words.get(7):
        raise AssertionError(f'{what}: the shim stopped the run: '
                             f'{words[7].to_bytes(8, "little").rstrip(bytes(1)).decode(errors="replace")}')
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError(f'{what}: results differ from the native reference: ' + '; '.join(
            f'{c["name"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))
    if words.get(1) != 0:
        raise AssertionError(f'{what}: main() returned {words.get(1)}')
    return checks


def laptop_table():
    return {k: {'cycles': c, 'instructions': i} for k, (c, i) in LAPTOP.items()}


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'js' not in build:
        raise SystemExit('build.json is not a js build')
    js = build['js']
    fp = not js['soft_float']
    if fp and not (args.core == 'ooo' and getattr(args, 'fpu', False)):
        raise SystemExit('This build uses the F and D extensions: run it with --core ooo --fpu (RV64_OOO_FPU, '
                         'architecture 0.17.0); the multicycle and pipelined cores have no F or D')
    expected = js['expected']
    kernels = [line['kernel'] for line in expected['lines']]
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    mode = args.js_mode or 'sampled'
    piece = args.sample_instructions or SAMPLE_PIECE
    warmup = args.warmup_instructions if args.warmup_instructions is not None else SAMPLE_WARMUP
    per_phase = args.sample_pieces if args.sample_pieces is not None else SAMPLE_PER_KERNEL
    exe, iss_compiler = iss_binary(root, sha)
    iss = functools.partial(iss_call, exe, ram_bytes, *(('--fp', '1') if fp else ()))

    # 1. Functional run and result checks.
    started = time.perf_counter()
    summary = iss('--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}')
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    words = {int(k): v for k, v in summary['mailbox'].items()}
    checks = check_words(words, expected, 'rv_iss')
    marks = [tuple(m) for m in summary['marks']]
    want_marks = [1] + [m for k in range(len(kernels)) for m in (0x10 + k, 0x20 + k, 0x30 + k)] + [2]
    if [v for v, _ in marks] != want_marks or expected['marks'][1:] != want_marks:
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    at = dict(marks)
    phases = {name: (at[0x20 + k], at[0x30 + k]) for k, name in enumerate(kernels)}
    warm_calls = {name: at[0x20 + k] - at[0x10 + k] for k, name in enumerate(kernels)}
    total_instructions = summary['instructions']

    warm_l2 = getattr(args, 'warm_l2', False)
    if warm_l2 and not caches.get('L2_KIB'):
        raise SystemExit('--warm-l2 needs an L2 (L2_KIB)')
    if warm_l2 and mode == 'full':
        raise SystemExit('--warm-l2 applies to sampled mode only')
    warm_spec = ','.join(str(caches.get(k, d)) for k, d in (('ICACHE_BEATS', 0), ('DCACHE_BEATS', 0), ('L2_KIB', 0),
                                                             ('L2_WAYS', 8), ('L2_LINE', 64)))
    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches},
                           defines=wide + (['L2_PRELOAD'] if warm_l2 else []) +
                           (['L2_PRELOAD_READY'] if warm_l2 and 'l2_ready' in rtl[1].read_text(encoding='utf-8') else []))
    trace_sim = sim.build('tb_core', [rtl[0], snap / 'sim/cpu/tb_core.sv'], out / 'tb_core.vvp',
                          params={'MEM_BYTES': ram_bytes, **({'N_MISS': caches['N_MISS']} if 'N_MISS' in caches else {})},
                          defines=wide)
    jobs = max(1, args.jobs)
    simulations, differential, phase_clocks, sampling = [], [], {}, {}

    def simulate(arguments, name):
        t0 = time.perf_counter()
        text = command(arguments)
        simulations.append({'run': name, 'wall_seconds': round(time.perf_counter() - t0, 1)})
        return text

    whole = {'retired_instructions': total_instructions}
    rtl_checks = None
    if mode == 'full':
        max_cycles = args.max_cycles or max(50_000_000, 40 * total_instructions)
        output = simulate([*timing_sim, f'+image_bin={out / "bench-words-be.bin"}', f'+mailbox={mailbox:x}',
                           f'+max_cycles={max_cycles}'], 'timing, full program')
        (out / 'timing-run.txt').write_text(output, encoding='utf-8')
        laps = {int(v): int(c) for v, c, _ in re.findall(r'^LAP (\d+) cycles=(\d+) retirements=(\d+)$', output, re.M)}
        counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+)', output)
        if not counters or set(laps) != set(want_marks[1:-1]):
            raise AssertionError('Timing run did not report its laps')
        for k, name in enumerate(kernels):
            phase_clocks[name] = laps[0x30 + k] - laps[0x20 + k]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and rv_iss disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        rtl_checks = check_words(rtl_words, expected, 'RTL timing run')
        whole['cycles_after_reset'] = int(counters[1])

    # 2-3. Pieces from rv_iss checkpoints: timed in sampled mode, trace-checked in both modes.
    plan = plan_pieces(phases, piece, warmup, per_phase)
    for k, p in enumerate(plan):
        p['index'] = k
        p['check'] = not args.no_differential and p['ordinal'] % args.differential_every == 0 and \
            (mode == 'sampled' or p['ordinal'] == min(q['ordinal'] for q in plan if q['phase'] == p['phase']))
    for k, p in enumerate([p for p in plan if p['check']]):
        p['stalls'] = args.stalls[k % len(args.stalls)]
    work = [p for p in plan if mode == 'sampled' or p['check']]
    key = {'warm_l2': warm_l2, 'ooo_defines': getattr(args, 'ooo_defines', []), 'core': args.core,
           'core_sha256': sha(rtl[0]), 'soc_sha256': sha(rtl[1]), 'caches': caches, 'mode': mode, 'piece': piece,
           'warmup': warmup, 'per_phase': per_phase, 'phases': phases,
           'differential_every': None if args.no_differential else args.differential_every,
           'image_sha256': build['artifact_sha256']['bench.bin']}
    piece_dir = out / 'pieces'
    subset = getattr(args, 'pieces', None)
    merged = subset == 'merge'
    if merged:
        saved = {}
        for path in sorted(piece_dir.glob('*.json')):
            record = json.loads(path.read_text(encoding='utf-8'))
            if record['key'] == json.loads(json.dumps(key)):
                for q in record['pieces']:
                    saved[q['index']] = q
                differential += record['differential']
                simulations += record['simulations']
        missing = [p['index'] for p in work if p['index'] not in saved]
        if missing:
            raise SystemExit(f'--pieces merge: no saved result for pieces {missing[:10]} (of {len(missing)})')
        for p in plan:
            if p['index'] in saved:
                p.update({k: v for k, v in saved[p['index']].items() if k in (
                    'clocks', 'window_retired', 'window_overrun', 'window', 'resume_pc', 'stub_instructions')})
        work = []
    elif subset:
        a, b = (int(x) for x in subset.split(':'))
        work = [p for p in work if a <= p['index'] < b]
        if not work:
            raise SystemExit(f'--pieces {subset}: no pieces in that range (plan has {len(plan)})')
    record_path = piece_dir / f'{subset.replace(":", "-")}.json' if subset and not merged else None
    fields = ('index', 'phase', 'ordinal', 'begin', 'end', 'checkpoint', 'window', 'clocks', 'window_retired',
              'window_overrun', 'resume_pc', 'stub_instructions')
    ckdir = out / 'checkpoints'
    ckdir.mkdir(exist_ok=True)
    if work:
        for old in ckdir.glob('*'):
            old.unlink()
    stub = mailbox - build['stack_reserve_bytes']

    def prepare(p):
        regs, memory, pc, index = bench_checkpoint.read_iss_state(p['state'])
        fstate = bench_checkpoint.read_iss_fstate(p['state']) if fp else None
        if index != p['checkpoint']:
            raise AssertionError('rv_iss state at the wrong instruction')
        if index == 0:
            image, info = bytes(memory), {'resume_pc': 0, 'resume_instruction': 0, 'stub_address': None,
                                          'stack_pointer': 0, 'stub_instructions': 0, 'stub_pcs': []}
        else:
            image, info = bench_checkpoint.build_from_state(regs, memory, pc, index, stub,
                                                            patches=[(mailbox, bytes(8))], fstate=fstate)
        del memory
        p.update(info)
        p['be'], p['le'] = bench_checkpoint.write_binaries(image, ckdir, f'piece{p["index"]:04d}', little=p['check'])
        del image
        p['skip'] = p['begin'] - p['checkpoint']
        p['window'] = (p['stub_instructions'] + p['skip'], p['stub_instructions'] + p['skip'] + p['end'] - p['begin'])

    def time_piece(p):
        preload = [f'+l2_preload={p["l2"]}'] if warm_l2 else []
        output = simulate([*timing_sim, f'+image_bin={p["be"]}', *preload, f'+mailbox={mailbox:x}',
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

    def save_record(done):
        piece_dir.mkdir(exist_ok=True)
        record = {'key': key, 'pieces': [{k: q.get(k) for k in fields} for q in done],
                  'differential': differential, 'simulations': simulations}
        record_path.write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')

    state, done = None, []
    if warm_l2 and work:
        # The cache model is not in the state files: one rv_iss pass from reset dumps every checkpoint
        # of this invocation with its L2 tags.
        every = sorted({p['checkpoint'] for p in work})
        iss('--image', out / 'bench.bin', '--warm-caches', warm_spec, '--dump-at', ','.join(map(str, every)),
            '--max', every[-1], '--dump-prefix', ckdir / 'state-')
    for start in range(0, len(work), jobs):
        batch = work[start:start + jobs]
        targets = sorted({p['checkpoint'] for p in batch})
        if not warm_l2:
            source = ['--state', state] if state else ['--image', out / 'bench.bin']
            iss(*source, '--dump-at', ','.join(map(str, targets)), '--max', targets[-1], '--dump-prefix', ckdir / 'state-')
            if state and state.name not in {f'state-{t}.state' for t in targets}:
                state.unlink()
        for p in batch:
            p['state'] = ckdir / f'state-{p["checkpoint"]}.state'
            p['l2'] = ckdir / f'state-{p["checkpoint"]}.l2'
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(piece_job, batch))
        keep = ckdir / f'state-{targets[-1]}.state'
        for p in batch:
            if (warm_l2 or p['state'] != keep) and p['state'].exists():
                p['state'].unlink()
            if warm_l2 and p['l2'].exists():
                p['l2'].unlink()
        state = keep
        done += batch
        if record_path:
            save_record(done)
        print(f'  pieces {start + 1}-{start + len(batch)} of {len(work)} done', flush=True)
    if state and state.exists():
        state.unlink()
    if record_path:
        for p in work:
            print(f'piece {p["index"]} ({p["phase"]}, instructions {p["begin"]:,}-{p["end"]:,}): {p.get("clocks")} clocks')
        print(f'Saved {Path(os.path.relpath(record_path, root)).as_posix()}; plan has {len(plan)} pieces; report with --pieces merge')
        return
    if mode == 'sampled':
        for name, (first, last) in phases.items():
            phase_clocks[name], sampling[name] = phase_estimate([p for p in plan if p['phase'] == name], last - first)

    # 4. Metrics against the laptop reference and goal.
    report_kernels, ratios = {}, []
    for name in kernels:
        first, last = phases[name]
        clocks, instructions = phase_clocks[name], last - first
        lap_cycles, lap_instructions = LAPTOP.get(name, (None, None))
        entry = {'clocks': clocks, 'retired_instructions': instructions, 'ipc': instructions / clocks,
                 'warm_call_instructions': warm_calls[name]}
        if lap_cycles:
            goal_clocks = lap_cycles / GOAL_FACTOR
            ratios.append(lap_cycles / clocks)
            entry['against_goal'] = {
                'laptop_cycles': lap_cycles, 'laptop_instructions': lap_instructions,
                'laptop_ipc': lap_instructions / lap_cycles, 'rv_per_aarch64_instructions': instructions / lap_instructions,
                'goal_clocks': goal_clocks, 'goal_ipc': instructions / goal_clocks,
                'speed_vs_laptop_per_clock': lap_cycles / clocks, 'fraction_of_goal': goal_clocks / clocks}
        if name in sampling:
            entry['sampling'] = sampling[name]
        report_kernels[name] = entry
    clocks_sum = sum(phase_clocks.values())
    instr_sum = sum(e['retired_instructions'] for e in report_kernels.values())
    total = {'clocks': clocks_sum, 'retired_instructions': instr_sum, 'ipc': instr_sum / clocks_sum}
    if len(ratios) == len(kernels):
        geo = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
        total.update({'geomean_speed_vs_laptop_per_clock': geo, 'goal_geomean': GOAL_FACTOR,
                      'fraction_of_goal': geo / GOAL_FACTOR})
    report = {
        'status': 'PASS',
        'benchmark': 'JavaScript benchmark: QuickJS-ng 0.18.0 (bytecode interpreter), 9 original kernels, timed second call',
        'label': LABEL + ('; soft-float (compiler-rt) build' if js['soft_float'] else '; F/D build'),
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'], 'float': 'soft (compiler-rt builtins)' if js['soft_float'] else 'F/D',
            'environment': 'bare metal, laboratory terminal trap', 'core': args.core,
            'core_source': args.core_source or core_file,
            'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
            'memory_model': {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64),
                             ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))},
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'workload': {'scale': js['reference']['scale'], 'kernels': kernels, 'quickjs': js['quickjs'],
                     'native_reference': js['reference_dir'], 'output_hash': expected['hash_hex']},
        'functional_model': {'name': 'rv_iss.c', 'source_sha256': sha(root / ISS_SOURCE), 'compiler': iss_compiler,
                             'seconds': round(functional_seconds, 2), 'mips': summary['mips']},
        'mode': mode, 'fpu': fp, 'warm_l2': warm_l2, 'core_defines': list(getattr(args, 'ooo_defines', [])),
        'pieces': {'piece_instructions': piece, 'warmup_instructions': warmup, 'per_kernel': per_phase,
                   'differential_every': None if args.no_differential else args.differential_every,
                   'pieces': [{k: p.get(k) for k in fields} for p in plan]},
        'kernels': report_kernels,
        'total': total,
        'laptop_reference': laptop_table(),
        'kernel_definitions': 'marker 0x20+k to 0x30+k: the second (timed) call of kernel k; the first call '
                              '(0x10+k to 0x20+k) warms code, data and predictors',
        'whole_program': whole,
        'result_checks': checks,
        'result_checks_source': 'rv_iss mailbox against expected.json (native reference)',
        'rtl_result_checks': rtl_checks,
        'differential': differential,
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            'Soft-float build: every float and double operation is a compiler-rt call.' if js['soft_float'] else 'F/D build.',
            'QuickJS-ng is a bytecode interpreter; the laptop runs the same interpreter, not a JIT engine.',
            'The bare-metal build uses the shim libc (its allocator, memcpy and string routines); the laptop uses glibc.',
            'Sampled pieces start from rv_iss checkpoints with cold caches and predictors and a detailed warm-up; '
            'kernel clocks are estimates.' if mode == 'sampled' else 'Whole program from reset; exact.',
            'No cycle counter: timing comes from testbench markers or retirement windows. Per-clock figures only.',
        ],
    }
    name = f'results-{args.core}' + ('-fpu' if getattr(args, 'fpu', False) else '') + '.json'
    (out / name).write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: js results equal the native reference (rv_iss, {total_instructions:,} instructions; '
          f'{len(kernels)} kernel lines, output hash {expected["hash_hex"]}).')
    if rtl_checks:
        print('PASS: RTL timing-run mailbox equals the native reference.')
    print(f'PASS: differential traces match rv_iss ({len(differential)} pieces).' if differential else
          'Differential check skipped.')
    for kname, e in report_kernels.items():
        extra = ''
        if 'sampling' in e and not e['sampling']['complete']:
            s = e['sampling']
            extra = f' [{s["pieces_timed"]} pieces, {100 * s["fraction_timed"]:.1f}%, 95% CI +-{100 * s["ci95_relative"]:.1f}%]'
        g = e.get('against_goal')
        goal = f', {g["speed_vs_laptop_per_clock"]:.3f}x laptop/clk, {100 * g["fraction_of_goal"]:.1f}% of goal ' \
               f'(goal IPC {g["goal_ipc"]:.2f})' if g else ''
        print(f'{kname}: {e["clocks"]:,} clocks, {e["retired_instructions"]:,} instructions, IPC {e["ipc"]:.3f}{goal}{extra}')
    t = total
    print(f'total: {t["clocks"]:,} clocks, {t["retired_instructions"]:,} instructions, IPC {t["ipc"]:.3f}' +
          (f'; geomean {t["geomean_speed_vs_laptop_per_clock"]:.3f}x laptop per clock, '
           f'{100 * t["fraction_of_goal"]:.1f}% of the goal ({GOAL_FACTOR}x)' if 'fraction_of_goal' in t else ''))
    print(f'({report["label"]})')
    print(f'Results: {Path(os.path.relpath(out / name, root)).as_posix()}')
