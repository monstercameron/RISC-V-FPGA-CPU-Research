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

Results are labelled "scaled-down 7-Zip LZMA kernel, simulation"; they are not
7-Zip benchmark scores.
SPDX-License-Identifier: MIT
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
    ram_bytes, mailbox = build['ram_bytes'], build['mailbox_address']
    wide = ['WIDE_TRACE'] if args.core == 'ooo' else []
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
                          params={'MEM_BYTES': ram_bytes}, defines=wide)
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
    print(f'Results: {(out / "results.json").relative_to(root).as_posix()}')
