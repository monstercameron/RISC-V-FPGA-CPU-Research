"""Run the STREAM-like bandwidth probe on the RTL (run_bench.py --benchmark stream).

The program (stream/stream_bench.c) times read, write, copy, scale, add, triad and a dependent-load
chase at three footprints: first demand pass over DRAM (arrays in the loaded image, never touched by a
demand access before their one timed pass), L2-sized (128 KiB arrays after an untimed pass) and L1-sized (4 KiB arrays, 8 timed
passes after an untimed one). This runner:

1. runs the image on rv_iss.c: marker sequence, instruction count and the result mailbox (every check
   word must equal its closed form, mismatches 0);
2. times the whole program from reset on the timing bench (full mode only), laps at the markers, and
   checks the RTL mailbox against rv_iss's.
No differential trace check: this is a timing probe; core correctness is the test suites' job.
Bytes per call count the program's own element traffic (8 B per load or store of an element), not bus
beats: read n, write n, copy and scale 2n, add and triad 3n words. The chase reports clocks per load.
SPDX-License-Identifier: MIT
"""
from datetime import datetime, timezone
import json
import platform
import re
import time

from lzma_run import ISS_SOURCE, iss_binary, iss_call

LEVELS = ('dram', 'l2', 'l1')
KERNELS = ('read', 'write', 'copy', 'scale', 'add', 'triad', 'chase')
WORDS_MOVED = {'read': 1, 'write': 1, 'copy': 2, 'scale': 2, 'add': 3, 'triad': 3, 'chase': 0}
MAGIC = 0x48434e424d525453  # "STRMBNCH"
LABEL = 'STREAM-like bandwidth probe (original code, not STREAM), simulation (rubric evidence class E1)'


def calls_of(build):
    s = build['stream']
    calls = []
    for li, level in enumerate(LEVELS):
        if not s['levels'] >> li & 1:
            continue
        n = {'dram': s['dram_words'], 'l2': s['l2_words'], 'l1': s['l1_words']}[level]
        reps = s['l1_reps'] if level == 'l1' else 1
        for k, kernel in enumerate(KERNELS):
            if not s['kernels'] >> k & 1:
                continue
            words = s['chase_words'] if (kernel == 'chase' and level == 'dram') else n
            calls.append({'id': li * 8 + k, 'level': level, 'kernel': kernel, 'name': f'{level}_{kernel}',
                          'bytes': 8 * WORDS_MOVED[kernel] * words * reps,
                          'loads': (words // 8) * reps if kernel == 'chase' else None})
    return calls


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'stream' not in build:
        raise SystemExit('build.json is not a stream build')
    calls = calls_of(build)
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    exe, iss_compiler = iss_binary(root, sha)
    started = time.perf_counter()
    summary = iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}')
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    want_marks = [1] + [v for c in calls for v in (0x10 + 2 * c['id'], 0x11 + 2 * c['id'])] + [2]
    marks = [tuple(m) for m in summary['marks']]
    if [v for v, _ in marks] != want_marks:
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    at = dict(marks)
    words = {int(k): v for k, v in summary['mailbox'].items()}
    if words.get(2) != MAGIC or words.get(3) != 0 or words.get(1) != 0:
        raise AssertionError(f'rv_iss: magic/mismatch/return words wrong: {words.get(2)}, {words.get(3)}, {words.get(1)}')

    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches}, defines=wide)
    image_arg = f'+image_bin={out / "bench-words-be.bin"}'
    t0 = time.perf_counter()
    output = command([*timing_sim, image_arg, f'+mailbox={mailbox:x}',
                      f'+max_cycles={args.max_cycles or 400_000_000}'])
    timing_seconds = time.perf_counter() - t0
    (out / 'timing-run.txt').write_text(output, encoding='utf-8')
    laps = {int(v): (int(c), int(r)) for v, c, r in re.findall(r'^LAP (\d+) cycles=(\d+) retirements=(\d+)$', output, re.M)}
    counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+)', output)
    if not counters or set(laps) != set(want_marks[1:-1]):
        raise AssertionError('Timing run did not report its laps')
    rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
    if any(rtl_words.get(k) != v for k, v in words.items() if 1 <= k < 32):
        raise AssertionError('RTL mailbox differs from rv_iss')
    if int(counters[2]) != summary['instructions']:
        raise AssertionError('Timing run and rv_iss disagree on the instruction count')
    pf = re.search(r'^L2PF (.*)$', output, re.M)
    if caches.get('L2_PF', 0) and not pf:
        raise AssertionError('L2 prefetcher on, but the timing run printed no L2PF counters')
    pf_laps = {int(v): {k: int(x) for k, x in re.findall(r'(\w+)=(\d+)', rest)}
               for v, rest in re.findall(r'^L2PFLAP (\d+) (.*)$', output, re.M)}
    if pf and (any(m not in pf_laps for m in want_marks[1:-1]) or 'rd_miss' not in pf[1]):
        raise AssertionError('L2 prefetcher counters missing at some laps')
    report_calls = {}
    for c in calls:
        b, e = 0x10 + 2 * c['id'], 0x11 + 2 * c['id']
        clocks = laps[e][0] - laps[b][0]
        instructions = at[e] - at[b]
        entry = {'level': c['level'], 'kernel': c['kernel'], 'clocks': clocks, 'retired_instructions': instructions,
                 'ipc': instructions / clocks, 'bytes': c['bytes'], 'bytes_per_clock': c['bytes'] / clocks}
        if b in pf_laps and e in pf_laps:
            entry['l2_counters'] = {k: pf_laps[e][k] - pf_laps[b][k] for k in pf_laps[e]}
        if c['loads']:
            entry['loads'] = c['loads']
            entry['clocks_per_load'] = clocks / c['loads']
        report_calls[c['name']] = entry
    memory_model = {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64),
                    ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))}
    memory_model.update({k.lower(): v for k, v in caches.items() if k.startswith('L2_PF')})
    report = {
        'status': 'PASS', 'benchmark': 'STREAM-like bandwidth probe', 'label': LABEL,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
                  'isa': build['isa'], 'core': args.core, 'core_source': args.core_source or core_file,
                  'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
                  'memory_model': memory_model, 'core_defines': list(getattr(args, 'ooo_defines', [])),
                  'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
                  'hardware': f'none ({sim.label} simulation)'},
        'compiler': build['compiler'], 'optimization': build['optimization'], 'build_commands': build['commands'],
        'workload': build['stream'],
        'functional_model': {'name': 'rv_iss.c', 'source_sha256': sha(root / ISS_SOURCE), 'compiler': iss_compiler,
                             'seconds': round(functional_seconds, 2)},
        'mode': 'full', 'calls': report_calls, 'l2_prefetch_counters': pf[1] if pf else None,
        'whole_program': {'retired_instructions': summary['instructions'], 'cycles_after_reset': int(counters[1])},
        **sim.info(), 'timing_wall_seconds': round(timing_seconds, 1),
        'host': {'platform': platform.platform(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'], 'build_artifact_sha256': build['artifact_sha256'],
        'limitations': ['Bytes are element traffic (8 B per element load or store), not bus beats.',
                        'The dram level is one first demand pass per kernel over 32 KiB arrays, not a steady state.',
                        'With WRITE_FILL 0 a store that misses the L2 allocates its line with no DRAM traffic (optimistic).'],
    }
    result = out / f'results-{args.core}.json'
    result.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: stream check words equal their closed forms (rv_iss and RTL, {summary["instructions"]:,} instructions); '
          f'timing {timing_seconds:.1f} s.')
    for name, e in report_calls.items():
        extra = f', {e["clocks_per_load"]:.1f} dependent-load clk/load' if 'clocks_per_load' in e else f', {e["bytes_per_clock"]:.3f} B/clk'
        if 'l2_counters' in e:
            q = e['l2_counters']
            extra += f' [L2 rd miss {q["rd_miss"]}, pf issued {q["issued"]}, used {q["used"]}, late {q["late"]}]'
        print(f'{name}: {e["clocks"]:,} clocks, IPC {e["ipc"]:.3f}{extra}')
    print(f'(memory {memory_model}; defines {report["scope"]["core_defines"]})')
    if pf:
        print('L2PF', pf[1])
    print(f'Results: {result.relative_to(root).as_posix()}')
