"""Run the ray-tracing benchmark on the RTL (run_bench.py --benchmark rt).

The program (rt_bench.c, smallpt_rt.cpp) traces the RT-T primary and secondary
rays (closest hit), the secondary rays again (any hit), then renders the RT-P
smallpt image, and marks the four phases (include-rt/rt_bench.h). This runner:

1. runs the image on the fast functional simulator rv_iss.c: phases, instruction
   counts and the result mailbox, which must equal the native reference that
   rt_export.sh computed from the same sources (expected.json) word for word.
   The RT-T checksums are also compared with TinyBVH's own kernels on the same
   data (tinybvh.json): hits, primitive sums and per-ray primitive hashes must
   agree; the distance sums may differ in the last bits (TinyBVH fused its
   multiply-adds on the laptop; the port does not);
2. times the phases on the chosen core:
   full     the whole program from reset on the timing bench, laps at the
            markers (practical only for small builds: the scaled rv64imb
            soft-float program runs about 390 M instructions);
   sampled  K evenly spaced pieces per phase from rv_iss checkpoints, each after
            a warm-up of the preceding instructions; phase clocks are the timed
            clocks per instruction times the phase's instructions, with the
            spread of piece CPI (lzma_run.phase_estimate);
3. trace-checks every timed piece (warm-up included) on tb_core against rv_iss,
   the memory wait-cycle settings alternating, unless --no-differential;
4. reports clocks per ray and per path, rays per 1,000 clocks and paths per
   million clocks, and sets them against the laptop reference and its goal
   (cpu/raytracing-benchmark-targets.md, Apple M6 reference: 1.44 x the laptop per clock, an estimate).

The goal is defined on the full workload (4,096 triangles, 65,536 rays per set,
128 x 96 at 16 spp); a scaled build has a smaller tree (fewer node visits per
ray), so clocks per node visit and per path segment are reported as well. A
soft-float (rv64imb) build is a baseline only: the cores have no F, D or V.
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

MARKS = (1, 0x20, 0x21, 0x22, 2)
PHASES = {'rtt_primary_closest': (1, 0x20), 'rtt_secondary_closest': (0x20, 0x21),
          'rtt_secondary_anyhit': (0x21, 0x22), 'rtp_smallpt': (0x22, 2)}
LABEL = ('Ray-tracing benchmark (RT-T TinyBVH-derived traversal, RT-P smallpt), simulation (rubric evidence '
         'class E1)')
# Laptop reference and goal, per clock (cpu/raytracing-benchmark-targets.md, 2026-11-21): rays per 1,000
# clocks or paths per million clocks, scalar build and best SIMD build; laptop work per ray and per path.
# Goals since 2026-11-22 03:37 (user: "M6 everywhere"): 1.44 x the laptop per clock, the Cinebench 2024
# single-core per-clock ratio Apple M6 / Cortex-X925 (221 / 4.78 GHz vs 131 / 4.1 GHz, Notebookcheck;
# cpu/research/performance-targets.md). An ESTIMATE bridged from the laptop, not an M6 measurement (Apple
# publishes no M6 microarchitecture); about +-6% from the two clocks plus workload mismatch. Previous goals
# were 1.5 x the laptop (6.17 / 2.24 / 2.70 / 563 scalar; SIMD 18.2 / 9.0 / 4.63). SIMD laptop figures are
# the laptop's best kernels (16-ray NEON packets 12.1, SVE2 ray streams 6.00 rays/kclk).
TARGETS = {
    'rtt_primary_closest': {'unit': 'rays/kclk', 'laptop_scalar': 4.110, 'laptop_simd': 12.1,
                            'goal_scalar': 5.92, 'goal_simd': 17.4, 'laptop_node_visits_per_ray': 11.5734},
    'rtt_secondary_closest': {'unit': 'rays/kclk', 'laptop_scalar': 1.493, 'laptop_simd': 6.00,
                              'goal_scalar': 2.15, 'goal_simd': 8.64, 'laptop_node_visits_per_ray': 16.2159},
    'rtt_secondary_anyhit': {'unit': 'rays/kclk', 'laptop_scalar': 1.802, 'laptop_simd': 3.085,
                             'goal_scalar': 2.59, 'goal_simd': 4.44},
    'rtp_smallpt': {'unit': 'paths/Mclk', 'laptop_scalar': 375.5, 'laptop_simd': 375.8,
                    'goal_scalar': 541.0, 'goal_simd': 541.0, 'laptop_segments_per_path': 9.4614},
}
MAILBOX_NAMES = {2: 'magic', 3: 'tris|nodes<<32', 4: 'rays', 5: 'P hits', 6: 'P prim sum', 7: 'P hash',
                 8: 'P distance sum', 9: 'S hits', 10: 'S prim sum', 11: 'S hash', 12: 'S distance sum',
                 13: 'any-hit occluded', 14: 'any-hit hash', 15: 'paths', 16: 'segments', 17: 'image hash',
                 18: 'input data hash', 19: 'RT-P w|h<<16|spp<<32'}


def _iss_fp(exe, ram_bytes, *options, exe_fp=None, **kw):
    from lzma_run import iss_call as call
    return call(exe, ram_bytes, '--fp', '1', *options, **kw)


def check_words(words, expected, what):
    checks = []
    for key, want in sorted(expected['mailbox'].items(), key=lambda kv: int(kv[0])):
        got = words.get(int(key))
        checks.append({'word': int(key), 'name': MAILBOX_NAMES.get(int(key)), 'expected': want, 'actual': got,
                       'pass': got == want})
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError(f'{what}: results differ from the native reference: ' + '; '.join(
            f'{c["name"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))
    if words.get(1) != 0:
        raise AssertionError(f'{what}: main() returned {words.get(1)}')
    return checks


def tinybvh_crosscheck(words, tb):
    """The port against TinyBVH's own kernels on the same data (the laptop build's arithmetic)."""
    rows = []
    for name, base in (('P_closest', 5), ('S_closest', 9)):
        ref = tb[f'tinybvh_{name}']
        for field, offset in (('hits', 0), ('primsum', 1), ('hash', 2)):
            rows.append({'check': f'{name} {field}', 'tinybvh': ref[field], 'port': words[base + offset],
                         'pass': ref[field] == words[base + offset]})
    ref = tb['tinybvh_S_anyhit']
    rows.append({'check': 'S_anyhit hits', 'tinybvh': ref['hits'], 'port': words[13], 'pass': ref['hits'] == words[13]})
    rows.append({'check': 'S_anyhit hash', 'tinybvh': ref['hash'], 'port': words[14], 'pass': ref['hash'] == words[14]})
    failed = [r for r in rows if not r['pass']]
    if failed:
        raise AssertionError('port differs from TinyBVH: ' + '; '.join(f'{r["check"]} {r["port"]} vs {r["tinybvh"]}'
                                                                     for r in failed))
    return rows


def plan_pieces(phases, piece, warmup, per_phase):
    plan = []
    for name, (first, last) in phases.items():
        cuts = list(range(first, last, piece))
        chosen = range(len(cuts))
        if per_phase and len(cuts) > per_phase:
            chosen = sorted({int((i + 0.5) * len(cuts) / per_phase) for i in range(per_phase)})
        for k in chosen:
            begin = cuts[k]
            plan.append({'phase': name, 'begin': begin, 'end': min(begin + piece, last), 'ordinal': k,
                         'phase_pieces': len(cuts), 'checkpoint': max(0, begin - warmup)})
    return plan


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'rt' not in build:
        raise SystemExit('build.json is not an rt build')
    rt = build['rt']
    fp = not rt['soft_float']
    if fp and not (args.core == 'ooo' and getattr(args, 'fpu', False)):
        raise SystemExit('This build uses the F and D extensions: run it with --core ooo --fpu (RV64_OOO_FPU, '
                         'architecture 0.17.0); the multicycle and pipelined cores have no F or D')
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    hex_images = build.get('hex_images', True)
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    # Scaled hard-float builds on the out-of-order core run whole (exact, inside one 5-minute step);
    # the sampled default (20 K warm-up, cold caches per piece) understated RT-T 2.1-2.3x there.
    # Soft-float and full-size builds stay sampled.
    mode_default = args.rt_mode is None
    mode = args.rt_mode or ('full' if args.core == 'ooo' and fp and rt['tinybvh']['rays'] <= 4096 else 'sampled')
    piece, warmup = SAMPLING[args.core]
    piece = args.sample_instructions or piece
    warmup = args.warmup_instructions if args.warmup_instructions is not None else warmup
    per_phase = args.sample_pieces if args.sample_pieces is not None else 6
    exe, iss_compiler = iss_binary(root, sha)
    if fp:
        import functools
        global iss_call
        iss_call = functools.partial(_iss_fp, exe_fp=exe)

    # 1. Functional run and result checks.
    started = time.perf_counter()
    summary = iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}')
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    marks = [tuple(m) for m in summary['marks']]
    if [v for v, _ in marks] != list(MARKS):
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    at = dict(marks)
    phases = {name: (at[a], at[b]) for name, (a, b) in PHASES.items()}
    words = {int(k): v for k, v in summary['mailbox'].items()}
    total_instructions = summary['instructions']
    checks = check_words(words, rt['expected'], 'rv_iss')
    crosscheck = tinybvh_crosscheck(words, rt['tinybvh'])

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
        if not edges or not counters or set(laps) != {0x20, 0x21, 0x22}:
            raise AssertionError('Timing run did not report its laps and region')
        clock_at = {1: int(edges[1]), 2: int(edges[2]), **laps}
        for name, (a, b) in PHASES.items():
            phase_clocks[name] = clock_at[b] - clock_at[a]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and rv_iss disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        rtl_checks = check_words(rtl_words, rt['expected'], 'RTL timing run')
        whole['cycles_after_reset'] = int(counters[1])

    # 2-3. Pieces from rv_iss checkpoints: timed in sampled mode, trace-checked in both modes.
    plan = plan_pieces(phases, piece, warmup, per_phase)
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
        for name, (first, last) in phases.items():
            phase_clocks[name], sampling[name] = phase_estimate([p for p in plan if p['phase'] == name], last - first)

    # 4. Metrics against the laptop reference and goal.
    rays = rt['expected']['mailbox']['4']
    paths, segments = words[15], words[16]
    tb = rt['tinybvh']
    visits = {'rtt_primary_closest': tb['tinybvh_P_closest']['node_visits_per_ray'],
              'rtt_secondary_closest': tb['tinybvh_S_closest']['node_visits_per_ray']}
    report_phases = {}
    for name, clocks in phase_clocks.items():
        first, last = phases[name]
        instructions = last - first
        target = TARGETS[name]
        entry = {'clocks': clocks, 'retired_instructions': instructions, 'ipc': instructions / clocks}
        if name.startswith('rtt'):
            per_kclk = rays / clocks * 1e3
            entry.update({'rays': rays, 'clocks_per_ray': clocks / rays, 'instructions_per_ray': instructions / rays,
                          'rays_per_kclk': per_kclk})
            if name in visits:
                entry['node_visits_per_ray'] = visits[name]
                entry['clocks_per_node_visit'] = clocks / rays / visits[name]
                entry['laptop_scalar_clocks_per_node_visit'] = 1e3 / target['laptop_scalar'] / \
                    target['laptop_node_visits_per_ray']
        else:
            per_kclk = paths / clocks * 1e6
            entry.update({'paths': paths, 'segments': segments, 'clocks_per_path': clocks / paths,
                          'instructions_per_path': instructions / paths, 'instructions_per_segment': instructions / segments,
                          'clocks_per_segment': clocks / segments, 'paths_per_mclk': per_kclk,
                          'laptop_scalar_clocks_per_segment': 1e6 / target['laptop_scalar'] / target['laptop_segments_per_path']})
        entry['against_targets'] = {
            'unit': target['unit'], 'measured': per_kclk,
            **{k: target[k] for k in ('laptop_scalar', 'laptop_simd', 'goal_scalar', 'goal_simd')},
            'fraction_of_goal_scalar': per_kclk / target['goal_scalar'],
            'fraction_of_goal_simd': per_kclk / target['goal_simd']}
        if name in sampling:
            entry['sampling'] = sampling[name]
        report_phases[name] = entry
    export = rt['export']['args']
    report = {
        'status': 'PASS',
        'benchmark': 'Ray-tracing benchmark: RT-T (TinyBVH 1.9.2 binary-BVH traversal, C port) and RT-P (smallpt)',
        'label': LABEL + ('; soft-float (compiler-rt) baseline: the core has no F, D or V' if rt['soft_float'] else ''),
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'], 'float': 'soft (compiler-rt builtins)' if rt['soft_float'] else 'F/D',
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
        'workload': {'triangles': words[3] & 0xffffffff, 'bvh_nodes': words[3] >> 32, 'rays_per_set': rays,
                     'pt': {'w': export['pt_w'], 'h': export['pt_h'], 'spp': export['pt_spp'], 'paths': paths,
                            'segments': segments},
                     'export_args': export, 'data_dir': rt['data_dir']},
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
        'phase_definitions': {
            'rtt_primary_closest': 'marker 1 to 0x20: closest hit for every primary ray (Ray set-up, traversal, checksum)',
            'rtt_secondary_closest': 'marker 0x20 to 0x21: closest hit for every secondary ray',
            'rtt_secondary_anyhit': 'marker 0x21 to 0x22: any hit (t = far) for every secondary ray',
            'rtp_smallpt': 'marker 0x22 to 2: smallpt render (image clear, all paths); the image hash is after 2'},
        'whole_program': whole,
        'result_checks': checks,
        'result_checks_source': 'rv_iss mailbox against expected.json (native reference)',
        'rtl_result_checks': rtl_checks,
        'tinybvh_crosscheck': crosscheck,
        'differential': differential,
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            'Soft-float baseline: every float and double operation is a compiler-rt call; not a measure of an '
            'FP pipeline.' if rt['soft_float'] else 'F/D build.',
            'Scaled workload unless export_args are 32 8 256 128 96 16; the goal is defined on the full workload.',
            'RT-T traversal is a C port of TinyBVH\'s binary-BVH kernel (the laptop SIMD figures use BVH4_CPU with NEON).',
            'smallpt uses rt_math.c sine and cosine (not glibc), so its image differs in the last bits from the laptop build.',
            'Sampled pieces start with cold caches and predictors after a warm-up; phase clocks are estimates.',
            'No cycle counter: timing comes from testbench markers or retirement windows. Per-clock figures only.',
        ],
    }
    (out / f'results-{args.core}.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: rt results equal the native reference (rv_iss, {total_instructions:,} instructions); '
          f'RT-T checksums equal TinyBVH\'s on the same data.')
    if rtl_checks:
        print('PASS: RTL timing-run mailbox equals the native reference.')
    print(f'PASS: differential traces match rv_iss ({len(differential)} pieces).' if differential else
          'Differential check skipped.')
    for name, ph in report_phases.items():
        t = ph['against_targets']
        extra = ''
        if 'sampling' in ph and not ph['sampling']['complete']:
            s = ph['sampling']
            extra = f' [sampled {s["pieces_timed"]} pieces, {100 * s["fraction_timed"]:.2f}%, 95% CI +-{100 * s["ci95_relative"]:.1f}%]'
        per = (f'{ph["clocks_per_ray"]:,.0f} clk/ray, {ph["instructions_per_ray"]:,.0f} instr/ray' if 'rays' in ph else
               f'{ph["clocks_per_path"]:,.0f} clk/path, {ph["instructions_per_path"]:,.0f} instr/path')
        print(f'{name}: {ph["clocks"]:,} clocks, IPC {ph["ipc"]:.3f}, {per}, {t["measured"]:.4g} {t["unit"]} '
              f'(goal {t["goal_scalar"]} scalar / {t["goal_simd"]} SIMD: {100 * t["fraction_of_goal_scalar"]:.2f}% / '
              f'{100 * t["fraction_of_goal_simd"]:.2f}%){extra}')
    print(f'({report["label"]})')
    print(f'Results: {(out / f"results-{args.core}.json").relative_to(root).as_posix()}')
