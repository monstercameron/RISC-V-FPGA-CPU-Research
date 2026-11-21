"""Profile a benchmark run from measured per-instruction clocks.

tb_bench.sv (+profile) writes one line per instruction retired in the timed
region: PC, instruction, destination, next PC and the clocks the core spent in
its FETCH, EXECUTE and MEMORY states for that instruction. Because the clocks
are measured on the actual core and RAM wrapper, the profile stays exact as the
microarchitecture changes.

The profile attributes clocks to instruction classes, functions and addresses,
splits them into fetch, execute and memory time, and gives "what if" estimates.
Estimates are computed from the same measured instruction stream; they are
model estimates, not measurements of changed RTL.
SPDX-License-Identifier: MIT
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
import re

DMIPS_DIVISOR = 1757
HELPERS = ('__muldi3', '__divdi3', '__moddi3', '__udivdi3', '__umoddi3')
LIBRARY = ('memcpy', 'memset', 'strcpy', 'strcmp', 'printf')
CACHE_BEATS = (1, 2, 4, 8, 16, 32, 64)

BRANCHES = {0: 'beq', 1: 'bne', 4: 'blt', 5: 'bge', 6: 'bltu', 7: 'bgeu'}
LOADS = {0: 'lb', 1: 'lh', 2: 'lw', 3: 'ld', 4: 'lbu', 5: 'lhu', 6: 'lwu'}
STORES = {0: 'sb', 1: 'sh', 2: 'sw', 3: 'sd'}
OP_IMM = {0: 'addi', 1: 'slli', 2: 'slti', 3: 'sltiu', 4: 'xori', 5: 'srli', 6: 'ori', 7: 'andi'}
OP = {0: 'add', 1: 'sll', 2: 'slt', 3: 'sltu', 4: 'xor', 5: 'srl', 6: 'or', 7: 'and'}


def decode(ins):
    """Return (mnemonic, class) for an RV64I/Zifencei instruction word."""
    op, f3, alt = ins & 0x7f, (ins >> 12) & 7, (ins >> 30) & 1
    if op == 0x37: return 'lui', 'alu'
    if op == 0x17: return 'auipc', 'alu'
    if op == 0x6f: return 'jal', 'jump'
    if op == 0x67: return 'jalr', 'jump'
    if op == 0x63: return BRANCHES.get(f3, '?'), 'branch'
    if op == 0x03: return LOADS.get(f3, '?'), 'load'
    if op == 0x23: return STORES.get(f3, '?'), 'store'
    if op == 0x13: return ('srai' if f3 == 5 and alt else OP_IMM[f3]), 'alu'
    if op == 0x1b: return {0: 'addiw', 1: 'slliw', 5: 'sraiw' if alt else 'srliw'}.get(f3, '?'), 'alu'
    if op == 0x33:
        name = OP[f3]
        if f3 == 0 and alt: name = 'sub'
        if f3 == 5 and alt: name = 'sra'
        return name, 'alu'
    if op == 0x3b: return {0: 'subw' if alt else 'addw', 1: 'sllw', 5: 'sraw' if alt else 'srlw'}.get(f3, '?'), 'alu'
    if op == 0x0f: return ('fence.i' if f3 == 1 else 'fence'), 'fence'
    return '?', 'system'


def load_symbols(path):
    code = []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        address, kind, name = line.split()
        if kind in 'tT':
            code.append((int(address, 16), name))
    return sorted(code)


def load_disassembly(path):
    text = {}
    if Path(path).is_file():
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(.*)$', line)
            if match:
                text[int(match[1], 16)] = re.sub(r'\s+', ' ', match[2]).strip()
    return text


def dmips(runs, cycles):
    return runs * 1_000_000 / (cycles * DMIPS_DIVISOR)


def cache_hits(beats_sequence, lines):
    """Which accesses would hit a direct-mapped instruction cache of `lines` 8-byte beats."""
    tags, hits = [None] * lines, []
    for beat in beats_sequence:
        slot = beat % lines
        hits.append(tags[slot] == beat)
        tags[slot] = beat
    return hits


def profile(profile_path, symbols_path, disassembly_path, runs, measured_region_cycles):
    rows = []
    for line in Path(profile_path).read_text().splitlines():
        _, pc, ins, rd, nxt, f, e, m = line.split()
        rows.append((int(pc, 16), int(ins, 16), int(rd, 16), int(nxt, 16), int(f), int(e), int(m)))
    code = load_symbols(symbols_path)
    starts = [address for address, _ in code]
    disassembly = load_disassembly(disassembly_path)

    def function(pc):
        index = bisect_right(starts, pc) - 1
        return code[index][1] if index >= 0 else '?'

    n = len(rows)
    totals = Counter()
    classes = defaultdict(Counter)
    mnemonics = Counter()
    per_function = defaultdict(Counter)
    per_pc = defaultdict(Counter)
    taken = not_taken = calls = 0
    helper_calls = Counter()
    for pc, ins, rd, nxt, f, e, m in rows:
        name, kind = decode(ins)
        cost = f + e + m
        owner = function(pc)
        for bucket in (totals, classes[kind], per_function[owner], per_pc[pc]):
            bucket['instructions'] += 1
            bucket['clocks'] += cost
            bucket['fetch'] += f
            bucket['execute'] += e
            bucket['memory'] += m
            bucket['fetch_misses'] += f > 0
        mnemonics[name] += 1
        if kind == 'branch':
            if nxt != pc + 4: taken += 1
            else: not_taken += 1
        if kind == 'jump' and rd == 1:
            calls += 1
            callee = function(nxt)
            per_function[callee]['calls'] += 1
            if callee in HELPERS:
                helper_calls[callee] += 1
    clocks = totals['clocks']
    memory_ops = classes['load']['instructions'] + classes['store']['instructions']

    def estimate(name, new_clocks, new_instructions, assumption):
        return {'name': name, 'instructions_per_run': new_instructions / runs, 'clocks_per_run': new_clocks / runs,
                'cpi': new_clocks / new_instructions, 'dmips_per_mhz': dmips(runs, new_clocks),
                'speedup': clocks / new_clocks, 'assumption': assumption}

    # Instruction-cache estimates: replay every instruction's beat through a
    # direct-mapped cache; a real fetch miss that would hit saves its fetch clocks.
    beats = [pc >> 3 for pc, *_ in rows]
    cache = []
    for lines in CACHE_BEATS:
        hits = cache_hits(beats, lines)
        saved = sum(r[4] for r, hit in zip(rows, hits) if hit and r[4] > 0)
        misses = sum(1 for r, hit in zip(rows, hits) if not hit)
        cache.append({'beats': lines, 'bytes': lines * 8, 'misses': misses, 'saved_clocks': saved})
    best_cache = cache[-1]

    helper = Counter()
    for h in HELPERS:
        helper.update(per_function[h])
    estimates = [estimate('Measured', clocks, n, 'Clocks measured on the core and synchronous RAM.')]
    for entry in cache[1:]:
        estimates.append(estimate(f'Instruction cache, {entry["beats"]} beats ({entry["bytes"]} bytes)',
                                  clocks - entry['saved_clocks'], n,
                                  'Direct-mapped, filled on every fetch; a hit costs no fetch clocks. Stores to '
                                  'cached code are ignored by this estimate.'))
    estimates += [
        estimate('Issue loads and stores in EXECUTE', clocks - memory_ops, n,
                 'The data request starts in EXECUTE, so each load or store spends one fewer clock waiting in MEMORY.'),
        estimate('Issue the next fetch in EXECUTE', clocks - totals['fetch_misses'], n,
                 'A fetch that misses starts one clock earlier, during the previous instruction\'s EXECUTE. '
                 'Upper bound: not possible after a load or store, which uses the bus.'),
        estimate('Hardware multiply and divide (M)', clocks - helper['clocks'] + sum(helper_calls.values()),
                 n - helper['instructions'],
                 'Each helper call becomes one 1-clock instruction. Best case: an iterative divider takes longer.'),
        estimate('No fetch clocks at all', clocks - totals['fetch'], n, 'Perfect instruction supply: a lower bound for fetch work.'),
        estimate('One clock per instruction', n, n, 'The floor for a core that executes one instruction per clock.'),
    ]
    functions = sorted(((name, data) for name, data in per_function.items() if data['instructions']),
                       key=lambda item: -item[1]['clocks'])
    hot = [{'pc': pc, 'function': function(pc), 'disassembly': disassembly.get(pc, ''), **per_pc[pc]}
           for pc in sorted(per_pc, key=lambda p: -per_pc[p]['clocks'])[:15]]
    return {
        'runs': runs, 'instructions': n, 'clocks': clocks, 'measured_region_cycles': measured_region_cycles,
        'totals': dict(totals), 'classes': {k: dict(v) for k, v in classes.items()},
        'mnemonics': mnemonics.most_common(),
        'functions': [(name, dict(data)) for name, data in functions],
        'branches': {'taken': taken, 'not_taken': not_taken}, 'calls': calls,
        'helpers': {'instructions': helper['instructions'], 'clocks': helper['clocks'], 'calls': dict(helper_calls)},
        'library_instructions': sum(per_function[f]['instructions'] for f in LIBRARY),
        'cache': cache, 'best_cache': best_cache, 'hot': hot, 'estimates': estimates,
    }


def markdown(p):
    runs, n, c, t = p['runs'], p['instructions'], p['clocks'], p['totals']
    pct = lambda x: f'{100 * x / c:.1f}%'
    out = ['### Profile of the timed region', '',
           f'Measured on the core and synchronous RAM: {n:,} retired instructions over {runs} runs, with the clocks each '
           f'spent in FETCH, EXECUTE and MEMORY. Per-instruction clocks sum to {c:,}; the timed region measured '
           f'{p["measured_region_cycles"]:,} (difference {p["measured_region_cycles"] - c:+,}, from where the region '
           'starts and stops inside the marker stores).', '',
           '| Core state | Clocks per run | Share |', '|---|---:|---:|',
           f'| FETCH (waiting for instructions) | {t["fetch"] / runs:,.1f} | {pct(t["fetch"])} |',
           f'| EXECUTE | {t["execute"] / runs:,.1f} | {pct(t["execute"])} |',
           f'| MEMORY (loads and stores) | {t["memory"] / runs:,.1f} | {pct(t["memory"])} |',
           f'| **Total** | **{c / runs:,.1f}** | |', '',
           f'Instructions that needed a bus fetch: {t["fetch_misses"] / runs:,.1f} of {n / runs:,.1f} per run '
           f'({100 * t["fetch_misses"] / n:.1f}%).', '',
           '**By instruction class** (per run):', '',
           '| Class | Instructions | Clocks | Share | Fetch | Execute | Memory |', '|---|---:|---:|---:|---:|---:|---:|']
    for kind, d in sorted(p['classes'].items(), key=lambda kv: -kv[1]['clocks']):
        out.append(f'| {kind} | {d["instructions"] / runs:,.1f} | {d["clocks"] / runs:,.1f} | {pct(d["clocks"])} | '
                   f'{d["fetch"] / runs:,.1f} | {d["execute"] / runs:,.1f} | {d["memory"] / runs:,.1f} |')
    out += ['', '**By function** (per run; calls counted at the call instruction):', '',
            '| Function | Instructions | Clocks | Share | Fetch | Memory | Calls |', '|---|---:|---:|---:|---:|---:|---:|']
    for name, d in p['functions']:
        out.append(f'| `{name}` | {d["instructions"] / runs:,.1f} | {d["clocks"] / runs:,.1f} | {pct(d["clocks"])} | '
                   f'{d["fetch"] / runs:,.1f} | {d["memory"] / runs:,.1f} | {d.get("calls", 0) / runs:,.1f} |')
    h = p['helpers']
    out += ['', f'Software multiply and divide: {h["instructions"] / runs:,.1f} instructions and {h["clocks"] / runs:,.1f} '
            f'clocks per run ({pct(h["clocks"])}), from ' + (', '.join(
                f'`{k}` {v / runs:,.1f}' for k, v in sorted(h['calls'].items())) or 'no') + ' calls per run. '
            f'String and memory routines: {p["library_instructions"] / runs:,.1f} instructions per run.', '',
            f'Control flow per run: {p["branches"]["taken"] / runs:,.1f} branches taken, '
            f'{p["branches"]["not_taken"] / runs:,.1f} not taken, {p["calls"] / runs:,.1f} calls.', '',
            '**Direct-mapped instruction cache, replayed on this instruction stream:**', '',
            '| Size | Misses per run | Fetch clocks saved per run |', '|---|---:|---:|']
    for e in p['cache']:
        out.append(f'| {e["beats"]} beats ({e["bytes"]} bytes) | {e["misses"] / runs:,.1f} | {e["saved_clocks"] / runs:,.1f} |')
    out += ['', '**Most expensive instructions** (whole region):', '',
            '| Address | Function | Instruction | Times | Clocks | Fetch | Memory |', '|---|---|---|---:|---:|---:|---:|']
    for item in p['hot']:
        out.append(f'| `{item["pc"]:#06x}` | `{item["function"]}` | `{item["disassembly"]}` | {item["instructions"]:,} | '
                   f'{item["clocks"]:,} | {item["fetch"]:,} | {item["memory"]:,} |')
    out += ['', '**Instruction mix** (per run): ' + ', '.join(f'`{k}` {v / runs:,.1f}' for k, v in p['mnemonics']) + '.', '',
            '**What-if estimates** from the measured stream (model estimates, not measured RTL):', '',
            '| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |', '|---|---:|---:|---:|---:|---:|']
    for e in p['estimates']:
        out.append(f'| {e["name"]} | {e["instructions_per_run"]:,.1f} | {e["clocks_per_run"]:,.1f} | {e["cpi"]:.3f} | '
                   f'{e["dmips_per_mhz"]:.4f} | {e["speedup"]:.2f}x |')
    out += [''] + [f'- *{e["name"]}:* {e["assumption"]}' for e in p['estimates'] if not e['name'].startswith('Instruction cache, ')
                   or e['name'].endswith('(16 bytes)')]
    return '\n'.join(out)
