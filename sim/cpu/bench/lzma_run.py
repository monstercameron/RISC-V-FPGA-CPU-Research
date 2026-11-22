"""Run the scaled-down 7-Zip LZMA kernel on the RTL (run_bench.py --benchmark lzma).

The program (lzma_bench.c) compresses and decompresses 7-Zip benchmark data once
and marks its phases in the mailbox (lzma_bench.h). This runner:

1. runs the image on the sequential reference model, finds each phase in program
   order, and checks the results independently: the packed stream must decode
   with Python's liblzma to the generated data, whose zlib CRC-32 must match;
2. times the phases on the chosen core, in one of two modes:
   full     the whole program from reset on the timing bench (laps split it);
   sampled  each phase cut into pieces; every piece starts from a checkpoint
            image (bench_checkpoint.py) a warm-up before the piece, and the
            timing bench counts clocks over the piece's retirement window.
            Phase clocks are the sum of the pieces. This keeps every simulation
            under the 5-minute step limit on slow models (the out-of-order core);
3. checks correctness against the reference model: in full mode the whole
   trace with and without memory wait cycles; in sampled mode every piece's
   trace (warm-up included) on tb_core, the wait-cycle settings alternating
   between pieces, and one checkpoint per phase replayed on the reference model
   to the program's end;
4. reports clocks, instructions, IPC and 7-Zip-style ratings per MHz from
   Bench.cpp's command counts (lzma_rating.py).

With --sim verilator (sim/cpu/simulator.py) the mode defaults to full for every
core: the whole out-of-order program then takes about 15 s.

Dictionaries above 4 KiB (build_bench.py --lzma-dict-log 13-22; 22 is the 7z b
-md22 shape) use the fast functional simulator rv_iss.c instead of reference.py
(--functional iss, the default there): phases, results, checkpoints and the
reference traces of the piece checks come from it, checkpoints are made a batch
at a time from its saved states, and images are loaded as binaries
(+image_bin). The out-of-order core then defaults to sampled mode, and
--sample-pieces K times K evenly spaced pieces per phase, scaled by instruction
count, with the spread of piece CPI reported.

Results are labelled "scaled-down 7-Zip LZMA kernel, simulation"; they are not
7-Zip benchmark scores.
SPDX-License-Identifier: MIT
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import json
import lzma
import platform
import re
import time
import zlib

import bench_checkpoint
import lzma_rating
from reference import execute

LZMA_MAGIC = 0x48434e42414d5a4c
MARK_START, MARK_STOP = 1, 2
MARK_ENC_CALL, MARK_ENC_DONE, MARK_DEC_CALL, MARK_DEC_KERNEL = 0x10, 0x11, 0x12, 0x13
LABEL = 'Scaled-down 7-Zip LZMA kernel, simulation (rubric evidence class E1); not a 7-Zip benchmark score'
RESULT_WORDS = ('magic', 'data_size', 'dict_size', 'packed_size', 'crc_data', 'crc_packed', 'crc_unpacked',
                'dec_result', 'dec_status', 'dec_in_used', 'compare_ok', 'enc_result', 'props_byte', 'arena_used')
LZMA_STATUS_MAYBE_FINISHED_WITHOUT_MARK = 4
# Default piece and warm-up sizes (instructions) per core for sampled mode.
# The out-of-order model simulates about 800 instructions per second under Icarus, so
# its pieces are sized to stay well inside the 5-minute step limit.
SAMPLING = {'multicycle': (1_200_000, 50_000), 'pipe': (1_200_000, 50_000), 'ooo': (150_000, 20_000)}


def align(value, to):
    return (value + to - 1) & ~(to - 1)


def scan(trace, mailbox):
    """Marker store indices (program order), mailbox words and all writes' final memory effect."""
    marks, words, count = [], {}, 0
    for line in trace:
        if line[0] == 'R':
            count += 1
        elif line[0] == 'W':
            _, address, data, mask = line.split()
            address = int(address, 16)
            if address == mailbox:
                marks.append((int(data, 16), count))
            elif mailbox < address < mailbox + 256 and mask == 'ff':
                words[(address - mailbox) // 8] = int(data, 16)
    return marks, words, count


def final_memory(image, trace):
    memory = bytearray(image)
    for line in trace:
        if line[0] == 'W':
            _, address, data, mask = line.split()
            address, data, mask = int(address, 16), int(data, 16), int(mask, 16)
            for lane in range(8):
                if mask >> lane & 1:
                    memory[address + lane] = data >> (8 * lane) & 0xff
    return memory


PHASES = {'compress_kernel': (MARK_START, MARK_ENC_DONE), 'compress_call': (MARK_ENC_CALL, MARK_ENC_DONE),
          'decompress_kernel': (MARK_DEC_KERNEL, MARK_STOP), 'decompress_call': (MARK_DEC_CALL, MARK_STOP)}


def phases_from(marks):
    index = {}
    for value, at in marks:
        if value in index:
            raise AssertionError(f'marker {value:#x} written twice')
        index[value] = at
    need = (MARK_ENC_CALL, MARK_START, MARK_ENC_DONE, MARK_DEC_CALL, MARK_DEC_KERNEL, MARK_STOP)
    if [v for v, _ in marks] != list(need):
        raise AssertionError(f'unexpected marker sequence {[hex(v) for v, _ in marks]}')
    # [first, last) in program order: from a marker store to the store that ends the phase.
    return {name: (index[a], index[b]) for name, (a, b) in PHASES.items()}


def independent_checks(build, symbols, memory, words):
    """Results computed without the RTL or the program's own CRC code."""
    lz = build['lzma']
    data_size, dict_size = lz['data_bytes'], lz['dict_bytes']
    capacity = data_size + data_size // 16 + 1024
    base = align(symbols['__bss_end'], 64)  # arena_alloc order in lzma_bench_pass()
    data_at = base
    packed_at = align(data_at + data_size, 64)
    output_at = align(packed_at + capacity, 64)
    data = bytes(memory[data_at:data_at + data_size])
    packed_size = words.get(5, 0)
    packed = bytes(memory[packed_at:packed_at + packed_size])
    output = bytes(memory[output_at:output_at + data_size])
    header = bytes([0x5d]) + dict_size.to_bytes(4, 'little') + data_size.to_bytes(8, 'little')
    decoded = lzma.decompress(header + packed, format=lzma.FORMAT_ALONE)
    expected = {
        'magic': LZMA_MAGIC, 'data_size': data_size, 'dict_size': dict_size, 'packed_size': packed_size,
        'crc_data': zlib.crc32(data), 'crc_packed': zlib.crc32(packed), 'crc_unpacked': zlib.crc32(data),
        'dec_result': 0, 'dec_status': LZMA_STATUS_MAYBE_FINISHED_WITHOUT_MARK, 'dec_in_used': packed_size,
        'compare_ok': 1, 'enc_result': 0, 'props_byte': 0x5d,
    }
    if decoded != data or output != data:
        raise AssertionError('liblzma does not decode the packed stream to the generated data')
    if not 0 < packed_size < data_size:
        raise AssertionError(f'implausible packed size {packed_size}')
    return expected, {'decoder': f'Python {platform.python_version()} lzma module (liblzma), FORMAT_ALONE',
                      'decode_matches_data': True, 'zlib_crc32_data': zlib.crc32(data)}


def check_words(words, expected, what):
    checks = []
    for offset, name in enumerate(RESULT_WORDS):
        actual = words.get(2 + offset)
        if name == 'arena_used':
            continue
        checks.append({'name': name, 'expected': expected[name], 'actual': actual, 'pass': actual == expected[name]})
    failed = [c for c in checks if not c['pass']]
    if failed:
        raise AssertionError(f'{what}: wrong results: ' + '; '.join(
            f'{c["name"]} = {c["actual"]}, expected {c["expected"]}' for c in failed))
    if words.get(1) != 0:
        raise AssertionError(f'{what}: main() returned {words.get(1)}')
    return checks


def run(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    if 'lzma' not in build:
        raise SystemExit('build.json is not an lzma build')
    functional = getattr(args, 'functional', None) or ('reference' if build['lzma']['dict_log'] == 12 else 'iss')
    if functional == 'iss':
        return run_iss(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches)
    if getattr(args, 'sample_pieces', None):
        raise SystemExit('--sample-pieces needs --functional iss')
    args.max_cycles = args.max_cycles or 50_000_000
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    mode = args.lzma_mode or ('sampled' if args.core == 'ooo' and sim.name == 'icarus' else 'full')
    piece, warmup = SAMPLING[args.core]
    piece = args.sample_instructions or piece
    warmup = args.warmup_instructions if args.warmup_instructions is not None else warmup
    symbols = {}
    for line in (out / 'symbols.txt').read_text(encoding='ascii').splitlines():
        value, _, name = line.split()
        symbols[name] = int(value, 16)
    image = (out / 'bench.bin').read_bytes().ljust(ram_bytes, b'\0')

    # 1. Reference model: phases in program order, independent result checks.
    started = time.perf_counter()
    reference_trace, coverage = execute(image, max_steps=40_000_000)
    reference_seconds = time.perf_counter() - started
    marks, words, total_instructions = scan(reference_trace, mailbox)
    phases = phases_from(marks)
    memory = final_memory(image, reference_trace)
    expected, independent = independent_checks(build, symbols, memory, words)
    check_words(words, expected, 'reference model')
    arena_used = words.get(15)

    timing_sim = sim.build('tb_bench', [*rtl, snap / 'sim/cpu/bench/tb_bench.sv'], out / 'tb_bench.vvp',
                           params={'RAM_WORDS': ram_bytes // 8, **caches}, defines=wide)
    trace_sim = sim.build('tb_core', [rtl[0], snap / 'sim/cpu/tb_core.sv'], out / 'tb_core.vvp',
                          params={'MEM_BYTES': ram_bytes, **({'N_MISS': caches['N_MISS']} if 'N_MISS' in caches else {})},
                          defines=wide)
    jobs = max(1, args.jobs)
    simulations = []

    def simulate(arguments, name):
        t0 = time.perf_counter()
        text = command(arguments)
        simulations.append({'run': name, 'wall_seconds': round(time.perf_counter() - t0, 1)})
        return text

    phase_clocks, differential, pieces_report, rtl_words = {}, [], [], None
    if mode == 'full':
        # 2a. Whole program from reset; laps give the phase edges.
        output = simulate([*timing_sim, f'+image={out / "bench-words.hex"}', f'+mailbox={mailbox:x}',
                           f'+max_cycles={args.max_cycles}'], 'timing, full program')
        (out / 'timing-run.txt').write_text(output, encoding='utf-8')
        laps = {int(v): int(c) for v, c, _ in re.findall(r'^LAP (\d+) cycles=(\d+) retirements=(\d+)$', output, re.M)}
        edges = re.search(r'EDGES start_cycle=(\d+) start_retired=\d+ stop_cycle=(\d+)', output)
        counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+)', output)
        if not edges or not counters or set(laps) != {MARK_ENC_CALL, MARK_ENC_DONE, MARK_DEC_CALL, MARK_DEC_KERNEL}:
            raise AssertionError('Timing run did not report its laps and region')
        at = {MARK_START: int(edges[1]), MARK_STOP: int(edges[2]), **laps}
        for name, (first_mark, last_mark) in PHASES.items():
            phase_clocks[name] = at[last_mark] - at[first_mark]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and reference model disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        checks = check_words(rtl_words, expected, 'RTL timing run')
        whole = {'cycles_after_reset': int(counters[1]), 'retired_instructions': total_instructions}
    else:
        whole = None
    # 2b. Pieces from checkpoints. Each phase kernel is cut into pieces of at most
    # `piece` instructions; each run starts `warmup` instructions earlier. Sampled
    # mode times them; both modes check every piece's trace against the reference.
    stub = mailbox - build['stack_reserve_bytes']
    plan = []
    for name in ('compress_kernel', 'decompress_kernel'):
        first, last = phases[name]
        for begin in range(first, last, piece):
            end = min(begin + piece, last)
            plan.append({'phase': name, 'begin': begin, 'end': end, 'checkpoint': max(0, begin - warmup)})
    r_lines = [i for i, line in enumerate(reference_trace) if line[0] == 'R']
    ckdir = out / 'checkpoints'
    ckdir.mkdir(exist_ok=True)
    for old in ckdir.glob('*'):
        old.unlink()
    for k, p in enumerate(plan):
        memory_k, info = bench_checkpoint.build(image, reference_trace, p['checkpoint'], stub,
                                                patches=[(mailbox, bytes(8))])
        p.update(info, index=k)
        p['words'], p['bytes'] = bench_checkpoint.write_images(memory_k, ckdir, f'piece{k:03d}')
        p['skip'] = p['begin'] - p['checkpoint']
        p['window'] = (bench_checkpoint.STUB_INSTRUCTIONS + p['skip'],
                       bench_checkpoint.STUB_INSTRUCTIONS + p['skip'] + p['end'] - p['begin'])
        if k == 0 or plan[k - 1]['phase'] != p['phase']:
            # Replay this checkpoint on the reference model to the end of the program:
            # after the stub it must retrace the original run exactly.
            replayed, _ = execute(memory_k, max_steps=40_000_000)
            stub_end = [i for i, line in enumerate(replayed) if line[0] == 'R'][bench_checkpoint.STUB_INSTRUCTIONS - 1]
            if replayed[stub_end + 1:] != reference_trace[r_lines[p['checkpoint'] - 1] + 1:]:
                raise AssertionError(f'checkpoint {k} does not reproduce the reference run')
            p['reference_replay'] = 'PASS'

    def time_piece(p):
        output = simulate([*timing_sim, f'+image={p["words"]}', f'+mailbox={mailbox:x}',
                           f'+max_cycles={args.max_cycles}', f'+sample_from={p["window"][0]}',
                           f'+sample_to={p["window"][1]}'], f'timing, piece {p["index"]}')
        m = re.search(r'^SAMPLE cycles=(\d+) retirements=(\d+) from_cycle=(\d+) from_retired=(\d+) '
                      r'to_cycle=(\d+) to_retired=(\d+) trapped=(\d+)$', output, re.M)
        if not m or int(m[7]):
            raise AssertionError(f'piece {p["index"]}: no sample window\n{output}')
        p['clocks'], p['window_retired'] = int(m[1]), int(m[2])
        p['window_overrun'] = (int(m[4]) - p['window'][0], int(m[6]) - p['window'][1])

    def check_piece(p):
        stalls = p['stalls']
        trace_path = out / f'piece{p["index"]:03d}-stall{stalls}.trace'
        limit = p['window'][1]
        summary = simulate([*trace_sim, f'+image={p["bytes"]}', f'+trace={trace_path}',
                            f'+stall={stalls}', f'+seed={p["index"] + 1}', f'+max_cycles={args.max_cycles}',
                            f'+max_retired={limit}'], f'differential, piece {p["index"]}, wait cycles {stalls}')
        actual = trace_path.read_text().splitlines()
        trace_path.unlink()
        rs = [i for i, line in enumerate(actual) if line[0] == 'R']
        if len(rs) < limit:
            raise AssertionError(f'piece {p["index"]}: trace ended after {len(rs)} retirements')
        # From just after the stub's last retirement, so a first store's write is included.
        got = actual[rs[bench_checkpoint.STUB_INSTRUCTIONS - 1] + 1:rs[limit - 1] + 1]
        n = limit - bench_checkpoint.STUB_INSTRUCTIONS
        want = reference_trace[r_lines[p['checkpoint'] - 1] + 1:r_lines[p['checkpoint'] + n - 1] + 1]
        if got != want:
            for event, (a, e) in enumerate(zip(got + ['<missing>'] * len(want), want + ['<missing>'] * len(got))):
                if a != e:
                    raise AssertionError(f'piece {p["index"]} trace differs at event {event} (stall {stalls}):\n'
                                         f'actual {a}\nexpect {e}')
        stub_pcs = [int(actual[i][2:18], 16) for i in rs[:bench_checkpoint.STUB_INSTRUCTIONS]]
        if stub_pcs[0] != 0 or stub_pcs[1] != p['stub_address']:
            raise AssertionError(f'piece {p["index"]}: restore stub did not run as built')
        differential.append({'scope': f'piece {p["index"]} ({p["phase"]})', 'max_wait_cycles': stalls,
                             'events': len(got), 'result': 'PASS',
                             'simulator_summary': summary.strip().splitlines()[0]})

    if mode == 'sampled':
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(time_piece, plan))
    if not args.no_differential:
        # Every piece, or with --differential-every K every K-th piece of each phase
        # (always its first).
        chosen = [p for p in plan if (p['begin'] - phases[p['phase']][0]) // piece % args.differential_every == 0]
        for k, p in enumerate(chosen):
            p['stalls'] = args.stalls[k % len(args.stalls)]
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(check_piece, chosen))
    if mode == 'sampled':
        for name in ('compress_kernel', 'decompress_kernel'):
            phase_clocks[name] = sum(p['clocks'] for p in plan if p['phase'] == name)
        checks = check_words(words, expected, 'reference model')
    for p in plan:
        pieces_report.append({k: p.get(k) for k in ('index', 'phase', 'begin', 'end', 'checkpoint', 'skip', 'window',
                                                    'clocks', 'window_retired', 'window_overrun', 'resume_pc')}
                             | ({'reference_replay': p['reference_replay']} if 'reference_replay' in p else {}))

    # 4. Ratings.
    lz = build['lzma']
    data_size, dict_size, packed_size = lz['data_bytes'], lz['dict_bytes'], expected['packed_size']
    commands = {'compress': lzma_rating.encode_commands(data_size, dict_size),
                'decompress': lzma_rating.decode_commands(packed_size, data_size)}
    report_phases = {}
    for name, clocks in phase_clocks.items():
        first, last = phases[name]
        instructions = last - first
        kind = name.split('_')[0]
        report_phases[name] = {
            'clocks': clocks, 'retired_instructions': instructions, 'ipc': instructions / clocks,
            'bytes_in': data_size if kind == 'compress' else packed_size,
            'bytes_out': packed_size if kind == 'compress' else data_size,
            'clocks_per_byte': clocks / data_size,
            'commands': commands[kind],
            'rating_mips_per_mhz': lzma_rating.rating_per_mhz(commands[kind], clocks),
        }
    report = {
        'status': 'PASS',
        'benchmark': 'Scaled-down 7-Zip LZMA benchmark kernel (7-Zip 26.06 LZMA SDK, Bench.cpp data and ratings)',
        'label': LABEL,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'],
            'environment': 'bare metal, laboratory terminal trap',
            'class': {'multicycle': 'multicycle', 'pipe': 'pipelined', 'ooo': 'out-of-order'}[args.core],
            'core': args.core,
            'core_source': args.core_source or core_file,
            'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
            'memory_model': {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64), ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))} |
                            {'ld_lat': getattr(args, 'ld_lat', None), 'l0_n': getattr(args, 'l0', None),
                             'l0_lat': getattr(args, 'l0_lat', None), 'fpu': getattr(args, 'fpu', False), 'dline': getattr(args, 'dline', 8),
                             'vector': getattr(args, 'vector', False),
                             'vlen': (getattr(args, 'vlen', None) or 256) if getattr(args, 'vector', False) else None},
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'kernel': {'dictionary_bytes': dict_size, 'data_bytes': data_size, 'packed_bytes': packed_size,
                   'encoder': 'LZMA level 5: lc 3, lp 0, pb 2, fb 32, BT4, mc 32, optimal parsing, 1 thread, no end marker',
                   'data': 'Bench.cpp GenerateLz(32 dictionary bits, salt 0)', 'arena_bytes_used': arena_used},
        'mode': mode,
        'pieces': {
            'piece_instructions': piece, 'warmup_instructions': warmup,
            'stub_instructions': bench_checkpoint.STUB_INSTRUCTIONS,
            'differential_every': None if args.no_differential else args.differential_every,
            'pieces': pieces_report,
            'note': 'Each piece starts from a checkpoint with cold caches and predictors and runs a warm-up of '
                    'the preceding instructions first. In sampled mode phase clocks are sums over the pieces; '
                    'in both modes every piece (warm-up included) is trace-checked against the reference model, '
                    'with the wait-cycle settings alternating between pieces.'},
        'phases': report_phases,
        'phase_definitions': {
            'compress_kernel': 'first input-stream read (after LzFind clears its hash) to LzmaEnc_Encode() return',
            'compress_call': 'LzmaEnc_Encode() call to return, including encoder and match-finder init',
            'decompress_kernel': 'after LzmaDec_Init() to the end of the output CRC',
            'decompress_call': 'LzmaDec_Init() to the end of the output CRC'},
        'rating_formula': 'Bench.cpp: compress commands = 870 x data bytes (dictionary below 2^18 counts as 2^18); '
                          'decompress commands = 190 x packed bytes + 4 x data bytes; MIPS/MHz = commands / clocks',
        'whole_program': whole or {'retired_instructions': total_instructions},
        'result_checks': checks,
        'result_checks_source': 'RTL timing run mailbox' if mode == 'full' else
            'reference model mailbox (pieces end before main returns; the RTL is tied to it by the piece traces)',
        'independent_checks': independent,
        'differential': differential,
        'instruction_names_executed': sorted(c for c in coverage if ':' not in c),
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'wall_seconds': {'reference_model': reference_seconds},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            'Scaled down: 4 KiB-class dictionary and data instead of 7z b -md22 (4 MiB + 64 KiB), so every table '
            'fits in small caches and the rating is not comparable to a 7-Zip score without calibration.',
            'One pass; 7-Zip repeats passes for several seconds and also counts the per-pass encoder init.',
            'CRC-32 is a byte-table loop, not 7-Zip\'s optimized or hardware CRC.',
            'No cycle counter: timing comes from testbench markers or retirement windows.',
            'Per-MHz figures only; no clock frequency has been measured.',
        ],
    }
    (out / 'results.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    if args.record:
        target = root / f'cpu/lzma-d{lz["dict_log"]}-{args.core}-results.json'
        target.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: LZMA kernel, {data_size} bytes, dictionary {dict_size}, packed {packed_size}; '
          f'results and liblzma decode match.')
    print(f'PASS: differential traces match the reference model ({len(differential)} runs, mode {mode}).'
          if differential else 'Differential check skipped (--no-differential).')
    for name, ph in report_phases.items():
        print(f'{name}: {ph["clocks"]:,} clocks, {ph["retired_instructions"]:,} instructions, IPC {ph["ipc"]:.3f}, '
              f'{ph["rating_mips_per_mhz"]:.4f} MIPS/MHz')
    print(f'({LABEL})')
    print(f'Results: {Path(os.path.relpath(out / "results.json", root)).as_posix()}')


# ---- Large dictionaries: the fast functional simulator rv_iss.c instead of reference.py ----
# reference.py runs about 0.5 M instructions per second, and the 2^22 kernel runs 4.0 G, so
# above the 4 KiB dictionary the runner takes phases, results, checkpoints and reference
# traces from rv_iss.c (same instruction subset and trace format; its whole 4 KiB-dictionary
# trace equals reference.py's, and the RTL piece traces are compared with its traces).
ISS_SOURCE = 'sim/cpu/bench/rv_iss.c'


def iss_binary(root, sha):
    """Compile rv_iss.c once per source hash into build/sim-cache/iss/; returns (path, compiler)."""
    import shutil
    import subprocess
    source = root / ISS_SOURCE
    exe = root / f'build/sim-cache/iss/rv_iss-{sha(source)[:16]}'
    cc = next((c for c in ('clang', 'gcc', 'cc') if shutil.which(c)), None)
    if cc is None:
        raise SystemExit('rv_iss.c needs a C compiler (clang, gcc or cc) on PATH')
    compiler = subprocess.run([cc, '--version'], capture_output=True, text=True, timeout=60).stdout.splitlines()[0]
    if not exe.is_file():
        exe.parent.mkdir(parents=True, exist_ok=True)
        temporary = exe.with_name(exe.name + f'.{time.time_ns()}.tmp')
        subprocess.run([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', str(temporary), str(source)],
                       check=True, capture_output=True, text=True, timeout=120)
        temporary.replace(exe)
    return exe, compiler


def iss_call(exe, ram_bytes, *options, timeout=300):
    import subprocess
    completed = subprocess.run([str(exe), '--ram', str(ram_bytes), *map(str, options)],
                               capture_output=True, text=True, timeout=timeout)
    if completed.returncode:
        raise RuntimeError(f'rv_iss failed: {completed.stderr}')
    return json.loads(completed.stdout)


def plan_pieces(phases, piece, warmup, sample_pieces):
    """Pieces of each phase kernel; with sample_pieces K, K evenly spaced ones per phase
    (the middle piece of each of K equal strata)."""
    plan = []
    for name in ('compress_kernel', 'decompress_kernel'):
        first, last = phases[name]
        cuts = list(range(first, last, piece))
        chosen = range(len(cuts))
        if sample_pieces and len(cuts) > sample_pieces:
            chosen = sorted({int((i + 0.5) * len(cuts) / sample_pieces) for i in range(sample_pieces)})
        for k in chosen:
            begin = cuts[k]
            plan.append({'phase': name, 'begin': begin, 'end': min(begin + piece, last), 'ordinal': k,
                         'phase_pieces': len(cuts), 'checkpoint': max(0, begin - warmup)})
    return plan


def phase_estimate(pieces, instructions):
    """Phase clocks from timed pieces: their sum when every piece ran, otherwise the timed
    clocks per instruction scaled to the phase, with the spread of piece CPI."""
    clocks = sum(p['clocks'] for p in pieces)
    timed = sum(p['end'] - p['begin'] for p in pieces)
    cpis = [p['clocks'] / (p['end'] - p['begin']) for p in pieces]
    mean = sum(cpis) / len(cpis)
    stdev = (sum((c - mean) ** 2 for c in cpis) / (len(cpis) - 1)) ** 0.5 if len(cpis) > 1 else 0.0
    complete = timed == instructions
    estimate = clocks if complete else round(clocks / timed * instructions)
    return estimate, {'pieces_timed': len(pieces), 'instructions_timed': timed, 'timed_clocks': clocks,
                      'fraction_timed': timed / instructions, 'complete': complete,
                      'piece_cpi_mean': mean, 'piece_cpi_stdev': stdev,
                      # Normal approximation for the mean over independent strata; 0 when complete.
                      'ci95_relative': 0.0 if complete else 1.96 * stdev / len(cpis) ** 0.5 / mean}


def run_iss(args, root, out, build, snap, rtl, core_file, command, sha, sim, caches):
    lz = build['lzma']
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    hex_images = build.get('hex_images', True)
    wide = ['WIDE_TRACE', *getattr(args, 'ooo_defines', [])] if args.core == 'ooo' else []
    mode = args.lzma_mode or ('sampled' if args.core == 'ooo' else 'full')
    piece, warmup = SAMPLING[args.core]
    piece = args.sample_instructions or piece
    warmup = args.warmup_instructions if args.warmup_instructions is not None else warmup
    symbols = {}
    for line in (out / 'symbols.txt').read_text(encoding='ascii').splitlines():
        value, _, name = line.split()
        symbols[name] = int(value, 16)
    exe, iss_compiler = iss_binary(root, sha)

    # 1. Functional run: phases in program order, independent result checks.
    final = out / 'iss-final-memory.bin'
    started = time.perf_counter()
    summary = iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}',
                       '--final-memory', final)
    functional_seconds = time.perf_counter() - started
    if summary['stop'] == 'budget' or summary['stop']['cause'] != 3 or summary['stop']['tval'] != 0:
        raise AssertionError(f'rv_iss: the program did not stop at its ebreak: {summary["stop"]}')
    marks = [tuple(m) for m in summary['marks']]
    words = {int(k): v for k, v in summary['mailbox'].items()}
    total_instructions = summary['instructions']
    phases = phases_from(marks)
    for attempt in range(2):
        memory = final.read_bytes()
        final.unlink()
        try:
            expected, independent = independent_checks(build, symbols, memory, words)
            break
        except AssertionError:
            # Once at d22 (2026-11-21 23:17) the 64 MiB final-memory file read back wrong through /mnt/c
            # (liblzma decode mismatch with a correct mailbox); write and check it once more before failing.
            if attempt:
                raise
            print('rv_iss final memory failed the liblzma check; rerunning rv_iss once', flush=True)
            iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--mailbox', f'{mailbox:x}', '--final-memory', final)
    del memory
    check_words(words, expected, 'rv_iss')
    arena_used = words.get(15)
    max_cycles = args.max_cycles or max(50_000_000, 40 * total_instructions)

    warm_l2 = getattr(args, 'warm_l2', False)
    if warm_l2 and not caches.get('L2_KIB'):
        raise SystemExit('--warm-l2 needs an L2 (L2_KIB)')
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
    simulations, differential, pieces_report, phase_clocks, sampling = [], [], [], {}, {}

    def simulate(arguments, name):
        t0 = time.perf_counter()
        text = command(arguments)
        simulations.append({'run': name, 'wall_seconds': round(time.perf_counter() - t0, 1)})
        return text

    checks = None
    whole = {'retired_instructions': total_instructions}
    if mode == 'full':
        image_arg = f'+image={out / "bench-words.hex"}' if hex_images else f'+image_bin={out / "bench-words-be.bin"}'
        output = simulate([*timing_sim, image_arg, f'+mailbox={mailbox:x}', f'+max_cycles={max_cycles}'],
                          'timing, full program')
        (out / 'timing-run.txt').write_text(output, encoding='utf-8')
        laps = {int(v): int(c) for v, c, _ in re.findall(r'^LAP (\d+) cycles=(\d+) retirements=(\d+)$', output, re.M)}
        edges = re.search(r'EDGES start_cycle=(\d+) start_retired=\d+ stop_cycle=(\d+)', output)
        counters = re.search(r'COUNTERS cycles=(\d+) retirements=(\d+)', output)
        if not edges or not counters or set(laps) != {MARK_ENC_CALL, MARK_ENC_DONE, MARK_DEC_CALL, MARK_DEC_KERNEL}:
            raise AssertionError('Timing run did not report its laps and region')
        at = {MARK_START: int(edges[1]), MARK_STOP: int(edges[2]), **laps}
        for name, (first_mark, last_mark) in PHASES.items():
            phase_clocks[name] = at[last_mark] - at[first_mark]
        if int(counters[2]) != total_instructions:
            raise AssertionError('Timing run and rv_iss disagree on the instruction count')
        rtl_words = {int(i): int(v, 16) for i, v in re.findall(r'^MAILBOX (\d+) ([0-9a-f]{16})$', output, re.M)}
        checks = check_words(rtl_words, expected, 'RTL timing run')
        whole = {'cycles_after_reset': int(counters[1]), 'retired_instructions': total_instructions}

    # 2. Pieces from rv_iss checkpoints, made a batch at a time (a 64 MiB image is 64 MiB on
    # disk per file), each batch continuing the functional run from the previous one.
    plan = plan_pieces(phases, piece, warmup, args.sample_pieces if mode == 'sampled' else None)
    for k, p in enumerate(plan):
        p['index'] = k
    if not args.no_differential:
        for p in plan:
            p['check'] = p['ordinal'] % args.differential_every == 0
        for k, p in enumerate([p for p in plan if p['check']]):
            p['stalls'] = args.stalls[k % len(args.stalls)]
    work = [p for p in plan if mode == 'sampled' or p.get('check')]
    # --pieces A:B runs only plan pieces A..B-1 and saves them to pieces/A-B.json, so a long
    # sampled run can be split into invocations of at most 5 minutes; --pieces merge then
    # reports from the saved files without simulating (every planned piece must be there).
    key = {'warm_l2': getattr(args, 'warm_l2', False), 'ooo_defines': getattr(args, 'ooo_defines', []),
           'core': args.core, 'core_sha256': sha(rtl[0]), 'soc_sha256': sha(rtl[1]), 'caches': caches, 'mode': mode,
           'piece': piece, 'warmup': warmup, 'sample_pieces': args.sample_pieces, 'phases': phases,
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
                p.update({k: v for k, v in saved[p['index']].items() if k in ('clocks', 'window_retired',
                          'window_overrun', 'window', 'skip', 'resume_pc', 'stub_instructions', 'functional_replay')})
        work = []
    elif subset:
        a, b = (int(x) for x in subset.split(':'))
        work = [p for p in work if a <= p['index'] < b]
        if not work:
            raise SystemExit(f'--pieces {subset}: no pieces in that range (plan has {len(plan)})')
    ckdir = out / 'checkpoints'
    ckdir.mkdir(exist_ok=True)
    for old in ckdir.glob('*'):
        old.unlink()
    stub = mailbox - build['stack_reserve_bytes']

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
        iss_call(exe, ram_bytes, '--state', p['state'], '--max', p['checkpoint'] + n, '--trace', want_path,
                 '--trace-from', p['checkpoint'], '--trace-to', p['checkpoint'] + n)
        summary_text = simulate([*trace_sim, f'+image_bin={p["le"]}', f'+trace={trace_path}', f'+stall={stalls}',
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
        stub_pcs = [int(actual[i][2:18], 16) for i in rs[:len(p['stub_pcs'])]]
        if stub_pcs != p['stub_pcs']:
            raise AssertionError(f'piece {p["index"]}: restore stub did not run as built')
        differential.append({'scope': f'piece {p["index"]} ({p["phase"]})', 'max_wait_cycles': stalls,
                             'events': len(got), 'result': 'PASS',
                             'simulator_summary': summary_text.strip().splitlines()[0]})

    def replay(p):
        # The checkpoint image, run from reset on rv_iss to the end of the program, must
        # retire the stub and then exactly the rest of the original run.
        r = iss_call(exe, ram_bytes, '--image', p['le'], '--mailbox', f'{mailbox:x}')
        shift = p['stub_instructions'] - p['checkpoint']
        want_marks = [[v, i + shift] for v, i in marks if i >= p['checkpoint']]
        if (r['instructions'] != total_instructions + shift or r['stop'] != summary['stop'] or
                r['marks'] != want_marks or {int(k): v for k, v in r['mailbox'].items()} != words):
            raise AssertionError(f'checkpoint {p["index"]} does not reproduce the rv_iss run')
        p['functional_replay'] = 'PASS'

    # The first planned piece of each phase is replayed on rv_iss (when this invocation runs it).
    first_of_phase = {min(p['index'] for p in plan if p['phase'] == name) for name in phases if
                      any(p['phase'] == name for p in plan)}
    fields = ('index', 'phase', 'begin', 'end', 'checkpoint', 'skip', 'window', 'clocks', 'window_retired',
              'window_overrun', 'resume_pc', 'stub_instructions', 'functional_replay')
    record_path = piece_dir / f'{subset.replace(":", "-")}.json' if subset and not merged else None

    def save_record(done):
        # After every batch, so a run stopped by its time limit keeps the pieces it finished.
        piece_dir.mkdir(exist_ok=True)
        record = {'key': key, 'pieces': [{k: q.get(k) for k in fields if k in q} for q in done],
                  'differential': differential, 'simulations': simulations}
        record_path.write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')

    def prepare(p):
        regs, memory, pc, index = bench_checkpoint.read_iss_state(p['state'])
        if index != p['checkpoint']:
            raise AssertionError('rv_iss state at the wrong instruction')
        if index == 0:  # a warm-up reaching back to reset: the program image itself, no stub
            image, info = bytes(memory), {'resume_pc': 0, 'resume_instruction': 0, 'stub_address': None,
                                          'stack_pointer': 0, 'stub_instructions': 0, 'stub_pcs': []}
        else:
            image, info = bench_checkpoint.build_from_state(regs, memory, pc, index, stub,
                                                            patches=[(mailbox, bytes(8))])
        del memory
        p.update(info)
        p['replay'] = p['index'] in first_of_phase
        # The byte image (tb_core, rv_iss replay) only when this piece is checked or replayed.
        p['be'], p['le'] = bench_checkpoint.write_binaries(image, ckdir, f'piece{p["index"]:04d}',
                                                           little=bool(p.get('check') or p['replay']))
        del image
        p['skip'] = p['begin'] - p['checkpoint']
        p['window'] = (p['stub_instructions'] + p['skip'], p['stub_instructions'] + p['skip'] + p['end'] - p['begin'])

    def piece_job(p):
        prepare(p)
        if mode == 'sampled':
            time_piece(p)
        if p.get('check'):
            check_piece(p)
        if p['replay']:
            replay(p)
        for name in ('be', 'le'):
            if p[name] is not None:
                p[name].unlink()
        p['be'] = p['le'] = None

    state, position, done = None, 0, []
    if warm_l2 and work:
        # The cache model is not in the state files, so one rv_iss pass from reset dumps every
        # checkpoint of this invocation with its L2 tags (64 MiB per state at d22: keep --pieces small).
        every = sorted({p['checkpoint'] for p in work})
        iss_call(exe, ram_bytes, '--image', out / 'bench.bin', '--warm-caches', warm_spec,
                 '--dump-at', ','.join(map(str, every)), '--max', every[-1], '--dump-prefix', ckdir / 'state-')
    for start in range(0, len(work), jobs):
        batch = work[start:start + jobs]
        targets = sorted({p['checkpoint'] for p in batch})
        if not warm_l2:
            source = ['--state', state] if state else ['--image', out / 'bench.bin']
            iss_call(exe, ram_bytes, *source, '--dump-at', ','.join(map(str, targets)), '--max', targets[-1],
                     '--dump-prefix', ckdir / 'state-')
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
        position = targets[-1]
        done += batch
        if record_path:
            save_record(done)
        print(f'  pieces {start + 1}-{start + len(batch)} of {len(work)} done (rv_iss at {position:,})', flush=True)
    if state and state.exists():
        state.unlink()
    if record_path:
        save_record(done)
        for p in work:
            print(f'piece {p["index"]} ({p["phase"]}, instructions {p["begin"]:,}-{p["end"]:,}): '
                  f'{p.get("clocks")} clocks')
        print(f'Saved {Path(os.path.relpath(record_path, root)).as_posix()}; plan has {len(plan)} pieces; '
              f'report with --pieces merge')
        return

    if mode == 'sampled':
        for name in ('compress_kernel', 'decompress_kernel'):
            first, last = phases[name]
            phase_clocks[name], sampling[name] = phase_estimate([p for p in plan if p['phase'] == name], last - first)
        checks = check_words(words, expected, 'rv_iss')
    for p in plan:
        pieces_report.append({k: p.get(k) for k in ('index', 'phase', 'ordinal', 'begin', 'end', 'checkpoint', 'skip',
                                                    'window', 'clocks', 'window_retired', 'window_overrun',
                                                    'resume_pc', 'stub_instructions')}
                             | ({'functional_replay': p['functional_replay']} if 'functional_replay' in p else {}))

    # 3. Ratings, with 7-Zip's command counts for this dictionary.
    data_size, dict_size, packed_size = lz['data_bytes'], lz['dict_bytes'], expected['packed_size']
    commands = {'compress': lzma_rating.encode_commands(data_size, dict_size),
                'decompress': lzma_rating.decode_commands(packed_size, data_size)}
    report_phases = {}
    for name, clocks in phase_clocks.items():
        first, last = phases[name]
        kind = name.split('_')[0]
        report_phases[name] = {
            'clocks': clocks, 'retired_instructions': last - first, 'ipc': (last - first) / clocks,
            'bytes_in': data_size if kind == 'compress' else packed_size,
            'bytes_out': packed_size if kind == 'compress' else data_size,
            'clocks_per_byte': clocks / data_size, 'commands': commands[kind],
            'rating_mips_per_mhz': lzma_rating.rating_per_mhz(commands[kind], clocks),
            **({'sampling': sampling[name]} if name in sampling else {}),
        }
    full_shape = lz['dict_log'] == 22
    label = (f'7-Zip LZMA benchmark kernel, 7z b -md22 shape (4 MiB dictionary, 4 MiB + 64 KiB data), one pass, '
             f'simulation (rubric evidence class E1); not a 7-Zip benchmark score' if full_shape else
             f'Scaled-down 7-Zip LZMA kernel, 2^{lz["dict_log"]} dictionary, simulation (rubric evidence class E1); '
             f'not a 7-Zip benchmark score')
    report = {
        'status': 'PASS',
        'benchmark': 'LZMA benchmark kernel (7-Zip 26.06 LZMA SDK, Bench.cpp data and ratings)',
        'label': label,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'architecture_version': (snap / 'cpu/VERSION').read_text(encoding='ascii').strip(),
            'isa': build['isa'], 'abi': build['abi'],
            'environment': 'bare metal, laboratory terminal trap',
            'class': {'multicycle': 'multicycle', 'pipe': 'pipelined', 'ooo': 'out-of-order'}[args.core],
            'core': args.core, 'core_source': args.core_source or core_file,
            'cache_beats': {'icache': caches['ICACHE_BEATS'], 'dcache': caches['DCACHE_BEATS']},
            'memory_model': {k.lower(): caches.get(k, d) for k, d in (('L2_KIB', 0), ('L2_WAYS', 8), ('L2_LINE', 64), ('L2_LAT', 12), ('MEM_LAT', 1), ('N_MISS', 1), ('MEM_GAP', 0), ('WRITE_FILL', 0))} |
                            {'ld_lat': getattr(args, 'ld_lat', None), 'l0_n': getattr(args, 'l0', None),
                             'l0_lat': getattr(args, 'l0_lat', None), 'fpu': getattr(args, 'fpu', False), 'dline': getattr(args, 'dline', 8),
                             'vector': getattr(args, 'vector', False),
                             'vlen': (getattr(args, 'vlen', None) or 256) if getattr(args, 'vector', False) else None},
            'rtl_sha256': {p.relative_to(snap).as_posix(): sha(p) for p in rtl},
            'platform': f'rv64_bram_soc, {ram_bytes // 1024} KiB synchronous RAM, no added wait cycles in the timing run',
            'hardware': f'none ({sim.label} simulation)',
        },
        'compiler': build['compiler'], 'optimization': build['optimization'], 'ram_bytes': ram_bytes,
        'build_commands': build['commands'],
        'kernel': {'dictionary_bytes': dict_size, 'data_bytes': data_size, 'packed_bytes': packed_size,
                   'encoder': 'LZMA level 5: lc 3, lp 0, pb 2, fb 32, BT4, mc 32, optimal parsing, 1 thread, no end marker',
                   'data': 'Bench.cpp GenerateLz(32 dictionary bits, salt 0)', 'arena_bytes_used': arena_used},
        'functional_model': {'name': 'rv_iss.c', 'source_sha256': sha(root / ISS_SOURCE), 'compiler': iss_compiler,
                             'seconds': round(functional_seconds, 2), 'mips': summary['mips']},
        'mode': mode,
        'pieces': {
            'piece_instructions': piece, 'warmup_instructions': warmup,
            'sample_pieces_per_phase': args.sample_pieces if mode == 'sampled' else None,
            'differential_every': None if args.no_differential else args.differential_every,
            'pieces': pieces_report,
            'note': 'Each piece starts from an rv_iss checkpoint with cold caches and predictors and runs a warm-up '
                    'of the preceding instructions first. In sampled mode phase clocks are the sum over the pieces, '
                    'or, when only some pieces are timed, their clocks per instruction times the phase\'s '
                    'instructions. Checked pieces (warm-up included) are compared with rv_iss traces on tb_core, the '
                    'wait-cycle settings alternating; the first checkpoint of each phase is replayed on rv_iss.'},
        'phases': report_phases,
        'phase_definitions': {
            'compress_kernel': 'first input-stream read (after LzFind clears its hash) to LzmaEnc_Encode() return',
            'compress_call': 'LzmaEnc_Encode() call to return, including encoder and match-finder init',
            'decompress_kernel': 'after LzmaDec_Init() to the end of the output CRC',
            'decompress_call': 'LzmaDec_Init() to the end of the output CRC'},
        'rating_formula': f'Bench.cpp: compress commands = {lzma_rating.encode_complexity(dict_size)} x data bytes '
                          f'(870 + (t*t*5 >> 16) for this dictionary; below 2^18 it counts as 2^18); decompress '
                          f'commands = 190 x packed bytes + 4 x data bytes; MIPS/MHz = commands / clocks',
        'whole_program': whole,
        'result_checks': checks,
        'result_checks_source': 'RTL timing run mailbox' if mode == 'full' else
            'rv_iss mailbox (pieces end before main returns; the RTL is tied to it by the piece traces)',
        'independent_checks': independent,
        'differential': differential,
        **sim.info(),
        'simulations': sorted(simulations, key=lambda s: s['run']),
        'host': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version()},
        'build_input_sha256': build['input_sha256'],
        'build_artifact_sha256': build['artifact_sha256'],
        'limitations': [
            ('The 7z b -md22 shape (4 MiB dictionary, 4 MiB + 64 KiB data)' if full_shape else
             f'Scaled down: 2^{lz["dict_log"]} dictionary, data = dictionary + 1/64'),
            'One pass; 7-Zip repeats passes for several seconds and also counts the per-pass encoder init.',
            'CRC-32 is a byte-table loop, not 7-Zip\'s optimized or hardware CRC.',
            'The memory behind the caches is the SoC model in this RTL revision (no DRAM latency unless it models one).',
            'No cycle counter: timing comes from testbench markers or retirement windows.',
            'Per-MHz figures only; no clock frequency has been measured.',
        ],
    }
    (out / 'results.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    if args.record:
        target = root / f'cpu/lzma-d{lz["dict_log"]}-{args.core}-results.json'
        target.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: LZMA kernel, {data_size} bytes, dictionary {dict_size}, packed {packed_size}; '
          f'results and liblzma decode match (functional model rv_iss, {total_instructions:,} instructions).')
    print(f'PASS: differential traces match rv_iss ({len(differential)} runs, mode {mode}).'
          if differential else 'Differential check skipped (--no-differential).')
    for name, ph in report_phases.items():
        extra = ''
        if 'sampling' in ph and not ph['sampling']['complete']:
            s = ph['sampling']
            extra = f' [sampled {s["pieces_timed"]} pieces, {100 * s["fraction_timed"]:.2f}% of instructions, ' \
                    f'95% CI +-{100 * s["ci95_relative"]:.1f}%]'
        print(f'{name}: {ph["clocks"]:,} clocks, {ph["retired_instructions"]:,} instructions, IPC {ph["ipc"]:.3f}, '
              f'{ph["rating_mips_per_mhz"]:.4f} MIPS/MHz{extra}')
    print(f'({label})')
    print(f'Results: {Path(os.path.relpath(out / "results.json", root)).as_posix()}')
