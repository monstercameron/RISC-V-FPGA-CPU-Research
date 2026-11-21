"""Profile a benchmark's retirement trace: where its clocks and instructions go.

Reads the zero-wait-cycle differential trace (one line per retired instruction
and memory write), the build's symbol map and disassembly, and attributes every
instruction in the timed region to a function, instruction class and address.

Clock costs come from a per-instruction model of the multicycle core with the
synchronous RAM wrapper: 2 clocks to fetch, 1 to execute, and 2 more for a load
or store. The model is checked against the measured timing-run clocks and
against the trace testbench's own cycle count; both checks are reported.

The "what if" estimates apply simple changes to the same counted trace. They
are model estimates, not measurements of changed RTL.
SPDX-License-Identifier: MIT
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
import re

FETCH, EXECUTE, MEMORY = 2, 1, 2           # rv64_bram_soc: synchronous RAM answers one clock later
TB_FETCH, TB_EXECUTE, TB_MEMORY = 1, 1, 1  # tb_core with no wait cycles answers in the same clock
DMIPS_DIVISOR = 1757
HELPERS = ('__muldi3', '__divdi3', '__moddi3', '__udivdi3', '__umoddi3')
LIBRARY = ('memcpy', 'memset', 'strcpy', 'strcmp', 'printf')

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
    if op == 0x13:
        name = OP_IMM[f3]
        return ('srai' if f3 == 5 and alt else name), 'alu'
    if op == 0x1b:
        return {0: 'addiw', 1: 'slliw', 5: 'sraiw' if alt else 'srliw'}.get(f3, '?'), 'alu'
    if op == 0x33:
        name = OP[f3]
        if f3 == 0 and alt: name = 'sub'
        if f3 == 5 and alt: name = 'sra'
        return name, 'alu'
    if op == 0x3b:
        return {0: 'subw' if alt else 'addw', 1: 'sllw', 5: 'sraw' if alt else 'srlw'}.get(f3, '?'), 'alu'
    if op == 0x0f: return ('fence.i' if f3 == 1 else 'fence'), 'fence'
    return '?', 'system'


def load_symbols(path):
    code = []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        address, kind, name = line.split()
        if kind in 'tT':
            code.append((int(address, 16), name))
    code.sort()
    return code


def load_disassembly(path):
    text = {}
    if Path(path).is_file():
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(.*)$', line)
            if match:
                text[int(match[1], 16)] = re.sub(r'\s+', ' ', match[2]).strip()
    return text


def clocks(kind, fetch=FETCH, execute=EXECUTE, memory=MEMORY):
    return fetch + execute + (memory if kind in ('load', 'store') else 0)


def dmips(runs, cycles):
    return runs * 1_000_000 / (cycles * DMIPS_DIVISOR)


def profile(trace_path, symbols_path, disassembly_path, mailbox, runs,
            measured_region_cycles, measured_total_cycles, tb_total_cycles):
    lines = Path(trace_path).read_text().splitlines()
    start = lines.index(f'W {mailbox:016x} {1:016x} ff')
    stop = lines.index(f'W {mailbox:016x} {2:016x} ff')
    code = load_symbols(symbols_path)
    starts = [address for address, _ in code]
    entry_of = {name: address for address, name in code}
    disassembly = load_disassembly(disassembly_path)

    def function(pc):
        index = bisect_right(starts, pc) - 1
        return code[index][1] if index >= 0 else '?'

    retired = []
    for index, line in enumerate(lines):
        if line.startswith('R '):
            _, pc, ins, rd, _, nxt = line.split()
            retired.append((index, int(pc, 16), int(ins, 16), int(rd, 16), int(nxt, 16)))

    soc_total = sum(clocks(decode(ins)[1]) for _, _, ins, _, _ in retired)
    tb_total = sum(clocks(decode(ins)[1], TB_FETCH, TB_EXECUTE, TB_MEMORY) for _, _, ins, _, _ in retired)
    region = [r for r in retired if start < r[0] < stop]

    classes, class_clocks = Counter(), Counter()
    mnemonics = Counter()
    per_function = defaultdict(lambda: {'instructions': 0, 'clocks': 0, 'calls': 0})
    per_pc = Counter()
    widths = Counter()
    taken = not_taken = calls = returns = reusable = reusable_outside_helpers = 0
    helper_calls = Counter()
    previous_pc = None
    for _, pc, ins, rd, nxt in region:
        name, kind = decode(ins)
        cost = clocks(kind)
        classes[kind] += 1
        class_clocks[kind] += cost
        mnemonics[name] += 1
        owner = function(pc)
        per_function[owner]['instructions'] += 1
        per_function[owner]['clocks'] += cost
        per_pc[pc] += 1
        if kind in ('load', 'store'):
            widths[name] += 1
        if kind == 'branch':
            if nxt != pc + 4: taken += 1
            else: not_taken += 1
        if kind == 'jump' and rd == 1:
            calls += 1
            callee = function(nxt)
            per_function[callee]['calls'] += 1
            if callee in HELPERS: helper_calls[callee] += 1
        if name == 'jalr' and rd == 0 and (ins >> 15) & 31 == 1:
            returns += 1
        # The 8-byte fetch beat that delivered the previous instruction also held this one.
        if previous_pc is not None and pc == previous_pc + 4 and pc >> 3 == previous_pc >> 3:
            reusable += 1
            if owner not in HELPERS:
                reusable_outside_helpers += 1
        previous_pc = pc

    instructions = len(region)
    region_clocks = sum(class_clocks.values())
    helper_instructions = sum(per_function[h]['instructions'] for h in HELPERS)
    helper_clock_total = sum(per_function[h]['clocks'] for h in HELPERS)
    library_instructions = sum(per_function[f]['instructions'] for f in LIBRARY)

    def estimate(name, new_instructions, new_clocks, assumption):
        return {'name': name, 'instructions_per_run': new_instructions / runs, 'clocks_per_run': new_clocks / runs,
                'cpi': new_clocks / new_instructions, 'dmips_per_mhz': dmips(runs, new_clocks),
                'speedup': region_clocks / new_clocks, 'assumption': assumption}

    m_instructions = instructions - helper_instructions
    m_clocks = region_clocks - helper_clock_total
    estimates = [
        estimate('Current core (model)', instructions, region_clocks,
                 'Per-instruction model of today\'s core; compare with the measured clocks above.'),
        estimate('Reuse the fetched beat, saving 1 clock', instructions, region_clocks - reusable,
                 'A one-entry fetch buffer serves the second instruction of each 8-byte beat with 1 clock of fetch instead of 2.'),
        estimate('Reuse the fetched beat, saving 2 clocks', instructions, region_clocks - 2 * reusable,
                 'The buffered instruction goes straight to execute with no fetch clock.'),
        estimate('Hardware multiply and divide (M)', m_instructions, m_clocks,
                 'Each helper call becomes one instruction costing the same as an add; the call instruction is replaced by it. '
                 'Best case: an iterative divider would take more clocks.'),
        estimate('M plus fetch reuse (1 clock)', m_instructions, m_clocks - reusable_outside_helpers,
                 'Both changes above; fetch reuse counted only for instructions outside the removed helpers.'),
        estimate('Ideal pipeline, today\'s instructions', instructions, instructions,
                 'Every instruction completes in 1 clock on average; no stalls. An upper bound, not a design.'),
        estimate('Ideal pipeline with M', m_instructions, m_instructions,
                 'Upper bound with hardware multiply and divide.'),
    ]

    functions = sorted(((name, data) for name, data in per_function.items() if data['instructions']),
                       key=lambda item: -item[1]['clocks'])
    hot = []
    for pc, count in per_pc.most_common(15):
        hot.append({'pc': pc, 'function': function(pc), 'count': count,
                    'clocks': count * clocks(decode(next(i for _, p, i, _, _ in region if p == pc))[1]),
                    'disassembly': disassembly.get(pc, '')})
    return {
        'model': {'fetch': FETCH, 'execute': EXECUTE, 'memory': MEMORY,
                  'region_model_clocks': region_clocks, 'region_measured_clocks': measured_region_cycles,
                  'whole_model_clocks': soc_total, 'whole_measured_clocks': measured_total_cycles,
                  'tb_model_clocks': tb_total, 'tb_measured_clocks': tb_total_cycles},
        'runs': runs, 'instructions': instructions, 'clocks': region_clocks,
        'classes': [(k, classes[k], class_clocks[k]) for k, _ in classes.most_common()],
        'mnemonics': mnemonics.most_common(),
        'functions': [(name, data['instructions'], data['clocks'], data['calls']) for name, data in functions],
        'branches': {'taken': taken, 'not_taken': not_taken}, 'calls': calls, 'returns': returns,
        'memory_widths': dict(widths),
        'fetch_reuse': {'reusable': reusable, 'share': reusable / instructions},
        'helpers': {'instructions': helper_instructions, 'clocks': helper_clock_total, 'calls': dict(helper_calls)},
        'library_instructions': library_instructions,
        'hot': hot, 'estimates': estimates,
        'entry_points': {name: entry_of.get(name) for name in HELPERS},
    }


def markdown(p):
    runs, n, c = p['runs'], p['instructions'], p['clocks']
    m = p['model']
    out = ['### Profile of the timed region', '',
           f'Source: the zero-wait differential trace, {n:,} retired instructions over {runs} runs. '
           f'Clock model: fetch {m["fetch"]}, execute {m["execute"]}, load or store +{m["memory"]}.', '',
           '| Model check | Model | Measured | Difference |', '|---|---:|---:|---:|']
    for label, model, measured in (
            ('Timed region, core + synchronous RAM', m['region_model_clocks'], m['region_measured_clocks']),
            ('Whole program, core + synchronous RAM', m['whole_model_clocks'], m['whole_measured_clocks']),
            ('Whole program, trace testbench (1-clock memory)', m['tb_model_clocks'], m['tb_measured_clocks'])):
        if measured is None:
            out.append(f'| {label} | {model:,} | not run | |')
        else:
            out.append(f'| {label} | {model:,} | {measured:,} | {measured - model:+,} |')
    out += ['', 'The whole-program differences are the final `ebreak`, which is fetched and executed but never retires.']
    out += ['', '**Where the clocks go, by instruction class** (per run):', '',
            '| Class | Instructions | Share | Clocks | Share |', '|---|---:|---:|---:|---:|']
    for kind, count, cost in p['classes']:
        out.append(f'| {kind} | {count / runs:,.1f} | {100 * count / n:.1f}% | {cost / runs:,.1f} | {100 * cost / c:.1f}% |')
    fetch_clocks = n * m['fetch']
    out += [f'| **total** | **{n / runs:,.1f}** | | **{c / runs:,.1f}** | |', '',
            f'Fetching instructions takes {fetch_clocks / runs:,.1f} clocks per run, '
            f'{100 * fetch_clocks / c:.1f}% of all clocks; executing takes {n * m["execute"] / runs:,.1f} '
            f'({100 * n * m["execute"] / c:.1f}%); the extra memory access of loads and stores takes '
            f'{(c - fetch_clocks - n * m["execute"]) / runs:,.1f} ({100 * (c - fetch_clocks - n * m["execute"]) / c:.1f}%).', '',
            '**Where the clocks go, by function** (per run; calls counted at the call instruction):', '',
            '| Function | Instructions | Share | Clocks | Share | Calls |', '|---|---:|---:|---:|---:|---:|']
    for name, count, cost, calls in p['functions']:
        out.append(f'| `{name}` | {count / runs:,.1f} | {100 * count / n:.1f}% | {cost / runs:,.1f} | '
                   f'{100 * cost / c:.1f}% | {calls / runs:,.1f} |')
    h = p['helpers']
    out += ['', f'Software multiply and divide (`{"`, `".join(HELPERS)}`): {h["instructions"] / runs:,.1f} instructions '
            f'and {h["clocks"] / runs:,.1f} clocks per run ({100 * h["clocks"] / c:.1f}% of clocks), from '
            f'{sum(h["calls"].values()) / runs:,.1f} calls per run '
            f'({", ".join(f"`{k}` {v / runs:,.1f}" for k, v in sorted(h["calls"].items())) or "none"}). '
            f'String and memory routines: {p["library_instructions"] / runs:,.1f} instructions per run.', '',
            f'Control flow per run: {p["branches"]["taken"] / runs:,.1f} branches taken, '
            f'{p["branches"]["not_taken"] / runs:,.1f} not taken, {p["calls"] / runs:,.1f} calls, '
            f'{p["returns"] / runs:,.1f} returns.', '',
            'Loads and stores per run by width: ' + ', '.join(
                f'`{k}` {v / runs:,.1f}' for k, v in sorted(p['memory_widths'].items())) + '.', '',
            f'Fetch reuse: {p["fetch_reuse"]["reusable"] / runs:,.1f} instructions per run '
            f'({100 * p["fetch_reuse"]["share"]:.1f}%) were in the same 8-byte fetch beat as the instruction '
            'just before them, so a one-entry fetch buffer could serve them without a new memory read.', '',
            '**Most-executed instructions** (whole region):', '',
            '| Address | Function | Instruction | Times | Clocks |', '|---|---|---|---:|---:|']
    for item in p['hot']:
        out.append(f'| `{item["pc"]:#06x}` | `{item["function"]}` | `{item["disassembly"]}` | '
                   f'{item["count"]:,} | {item["clocks"]:,} |')
    out += ['', '**Instruction mix** (per run): ' + ', '.join(
        f'`{name}` {count / runs:,.1f}' for name, count in p['mnemonics']) + '.', '',
        '**What-if estimates** from the same trace (model estimates, not measured RTL):', '',
        '| Change | Instructions per run | Clocks per run | CPI | DMIPS/MHz | Speed-up |',
        '|---|---:|---:|---:|---:|---:|']
    for e in p['estimates']:
        out.append(f'| {e["name"]} | {e["instructions_per_run"]:,.1f} | {e["clocks_per_run"]:,.1f} | '
                   f'{e["cpi"]:.3f} | {e["dmips_per_mhz"]:.4f} | {e["speedup"]:.2f}x |')
    out += [''] + [f'- *{e["name"]}:* {e["assumption"]}' for e in p['estimates']]
    return '\n'.join(out)
