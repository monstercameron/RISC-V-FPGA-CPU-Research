"""Compute the CPU review-rubric scorecard for a benchmark run.

Hand-assessed criteria and gates come from cpu/rubric-evidence.json. Entries
marked "auto" are computed here from the run and from local records:

- R4.1 from the run's clocks per instruction and the core class bars in
  cpu/review-rubric.md section 6, capped at 2 while CoreMark is missing;
- HG2 from build/cpu/verification.json, which must be PASS on the current RTL;
- PG1 from HG1-HG8.

If the RTL has changed since the evidence was assessed, the hand-assessed R1-R6
scores are void (rubric section 10) and count as 0 until reassessed.

This is an automated self-assessment. It is not an independent review and
grants only what rubric section 8 allows.
SPDX-License-Identifier: MIT
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

DIMENSIONS = [
    ('R1', 'Architectural correctness', 25),
    ('R2', 'Traps, interrupts, privilege and reset', 10),
    ('R3', 'Verification depth and independence', 15),
    ('R4', 'Performance', 20),
    ('R5', 'FPGA implementation quality', 12),
    ('R6', 'Interfaces and integration', 8),
    ('R7', 'Observability and debug', 4),
    ('R8', 'Design quality and maintainability', 3),
    ('R9', 'Reproducibility and claim hygiene', 3),
]
CRITERIA_PER_DIMENSION = {'R1': 6, 'R2': 6, 'R3': 7, 'R4': 8, 'R5': 7, 'R6': 6, 'R7': 4, 'R8': 4, 'R9': 4}
HARD_GATES = [f'HG{i}' for i in range(1, 9)]
PERFORMANCE_GATES = [f'PG{i}' for i in range(1, 6)]
# Clocks per instruction: (meets, exceeds), rubric section 6, R4.1.
CPI_BARS = {'multicycle': (4.0, 3.0), 'in-order pipelined': (1.6, 1.3), 'out-of-order': (1.0, 0.7)}
BANDS = [(90, 'excellent'), (75, 'good'), (60, 'solid'), (40, 'developing'), (0, 'foundation')]
RUN_LOG_HEADING = '## Dhrystone run log'
RUN_LOG_INTRO = """
Appended automatically by `sim/cpu/bench/run_bench.py --devlog`; the Windows launcher `run_dhrystone.ps1` does this on every run. Each entry records the run and a rubric scorecard computed from [cpu/rubric-evidence.json](cpu/rubric-evidence.json) plus the run's own measurements. A scorecard is an automated self-assessment, not an independent review, and grants only the claims rubric section 8 allows. Oldest run first.
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_rtl(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted((root / 'rtl/cpu').glob('*.sv'))}


def git(root, *args):
    try:
        # WSL sees Windows files as executable; ignore mode bits when checking for changes.
        done = subprocess.run(['git', '-c', 'safe.directory=*', '-c', 'core.fileMode=false', '-C', str(root), *args],
                              capture_output=True, text=True, timeout=30)
        return done.stdout.strip() if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def regression_gate(root, rtl):
    record = root / 'build/cpu/verification.json'
    if not record.is_file():
        return 'not met', 'No local regression record; run sim/cpu/run.sh.'
    data = json.loads(record.read_bytes())
    if data.get('status') != 'PASS':
        return 'not met', 'Latest local regression did not pass.'
    if data.get('rtl_sha256') != rtl:
        return 'not met', 'Latest local regression ran on different RTL; rerun sim/cpu/run.sh.'
    return 'met', f'Regression PASS on the current RTL: {data.get("runs")} runs, {data.get("instruction_names_covered")} instruction names.'


def cpi_score(cpi, core_class, complete):
    meets, exceeds = CPI_BARS[core_class]
    raw = 4 if cpi <= exceeds else 3 if cpi <= meets else 2 if cpi <= 2 * meets else 1
    score = min(raw, 2) if not complete else raw
    note = (f'CPI {cpi:.3f} against the {core_class} bars of {meets} (meets) and {exceeds} (exceeds) gives {raw}'
            + ('' if complete else '; capped at 2 because the benchmark set lacks CoreMark'))
    return score, note


def score(root, report):
    root = Path(root)
    evidence = json.loads((root / 'cpu/rubric-evidence.json').read_bytes())
    criteria = evidence['criteria']
    for dimension, count in CRITERIA_PER_DIMENSION.items():
        for n in range(1, count + 1):
            if f'{dimension}.{n}' not in criteria:
                raise ValueError(f'cpu/rubric-evidence.json lacks {dimension}.{n}')
    rtl = current_rtl(root)
    version = (root / 'cpu/VERSION').read_text(encoding='ascii').strip()
    stale = evidence['rtl_sha256'] != rtl or evidence['architecture_version'] != version
    scope = evidence['scope']
    auto = {}

    scores = {}
    for key, item in criteria.items():
        value = item['score']
        if value == 'auto':
            continue
        if stale and value is not None and key[:2] in ('R1', 'R2', 'R3', 'R4', 'R5', 'R6'):
            value = 0
        scores[key] = value
    cpi = report['clocks_per_instruction']
    scores['R4.1'], auto['R4.1'] = cpi_score(cpi, scope['class'], evidence['benchmark_set_complete'])

    gates = {key: dict(value) for key, value in evidence['gates'].items()}
    gates['HG2']['status'], gates['HG2']['evidence'] = regression_gate(root, rtl)
    auto['HG2'] = gates['HG2']['evidence']
    all_hard = all(gates[g]['status'] == 'met' for g in HARD_GATES)
    gates['PG1']['status'] = 'met' if all_hard else 'not met'

    dimensions, total = [], 0.0
    for key, name, weight in DIMENSIONS:
        values = [scores[f'{key}.{n}'] for n in range(1, CRITERIA_PER_DIMENSION[key] + 1)]
        scored = [v for v in values if v is not None]
        points = weight * sum(scored) / (4 * len(scored)) if scored else None
        percent = 100 * sum(scored) / (4 * len(scored)) if scored else None
        dimensions.append({'id': key, 'name': name, 'weight': weight, 'points': points, 'percent': percent,
                           'scores': values, 'not_applicable': len(values) - len(scored)})
        total += points or 0
    pct = {d['id']: d['percent'] or 0 for d in dimensions}
    band = next(name for floor, name in BANDS if total >= floor)

    def met(*names):
        return [n for n in names if gates[n]['status'] != 'met']

    claims = []
    missing = met('HG1', 'HG2', 'HG4', 'HG5', 'HG6')
    if pct['R1'] < 60: missing.append(f'R1 {pct["R1"]:.0f}% < 60%')
    if pct['R3'] < 50: missing.append(f'R3 {pct["R3"]:.0f}% < 50%')
    claims.append(('Verified in simulation', missing))
    missing = met(*HARD_GATES)
    if total < 75: missing.append(f'total {total:.1f} < 75')
    if pct['R1'] < 80: missing.append(f'R1 {pct["R1"]:.0f}% < 80%')
    if any(v is not None and v < 3 for v in [scores[f'R1.{n}'] for n in range(1, 7)]): missing.append('an R1 criterion under 3')
    for d in ('R2', 'R3', 'R6'):
        if pct[d] < 70: missing.append(f'{d} {pct[d]:.0f}% < 70%')
    if any(d['percent'] is not None and d['percent'] < 50 for d in dimensions): missing.append('a dimension under 50%')
    good_missing = missing
    claims.append(('Good', missing))
    missing = (['"Good" not granted'] if good_missing else []) + met(*PERFORMANCE_GATES)
    if pct['R4'] < 75: missing.append(f'R4 {pct["R4"]:.0f}% < 75%')
    for c in ('R4.1', 'R4.2', 'R4.3'):
        if (scores[c] or 0) < 3: missing.append(f'{c} = {scores[c]} < 3')
    if pct['R5'] < 60: missing.append(f'R5 {pct["R5"]:.0f}% < 60%')
    claims.append((f'Performant for a {scope["class"]} FPGA core', missing))

    return {
        'architecture_version': version, 'evidence_architecture_version': evidence['architecture_version'],
        'rubric_revision': evidence['rubric_revision'], 'evidence_assessed': evidence['assessed'],
        'evidence_commit': evidence['assessed_at_commit'], 'assessed_by': evidence['assessed_by'],
        'evidence_stale': stale, 'scope': scope, 'scores': scores, 'auto': auto, 'gates': gates,
        'dimensions': dimensions, 'total': total, 'band': band,
        'claims': [{'claim': c, 'granted': not m, 'missing': m} for c, m in claims],
    }


def previous_runs(text):
    return [json.loads(m) for m in re.findall(r'^<!-- dhrystone-run (\{.*\}) -->$', text, re.MULTILINE)]


def entry(root, report, card, previous):
    root = Path(root)
    now = datetime.now().astimezone()
    commit = git(root, 'rev-parse', '--short', 'HEAD') or 'unknown'
    status = git(root, 'status', '--porcelain')
    dirty = 'unknown' if status is None else ('yes' if status else 'no')
    compiler = report['compiler'].split(' (')[0]
    build = (compiler, report['optimization'], report['scope']['isa'], report['ram_bytes'])
    same = [p for p in previous if (p['compiler'], p['optimization'], p['isa'], p['ram_bytes']) == build]
    if same:
        change = 100 * (report['cycles_per_run'] - same[-1]['cycles_per_run']) / same[-1]['cycles_per_run']
        comparison = (f'{change:+.2f}% clocks per run against the previous run with the same build settings '
                      f'({same[-1]["time"]}, `{same[-1]["commit"]}`, '
                      f'architecture {same[-1].get("architecture_version", "unrecorded")})')
        if abs(change) > 2:
            comparison += '. **Change over 2%: explain it in this day\'s entry.**'
    else:
        comparison = 'first run with these build settings'
    rtl = ', '.join(f'`{Path(k).name}` {v[:12]}' for k, v in report['scope']['rtl_sha256'].items())
    waits = ' and '.join(str(d['max_wait_cycles']) for d in report['differential'])
    passed = sum(c['pass'] for c in report['result_checks'])
    lines = [
        f'### Run {now.strftime("%Y-%m-%d %H:%M:%S %z")}', '',
        f'- **Architecture:** version {card["architecture_version"]}',
        f'- **Commit:** `{commit}`, uncommitted changes: {dirty}',
        f'- **Build:** {compiler}, `-{report["optimization"]}`, `{report["scope"]["isa"]}`, {report["ram_bytes"] // 1024} KiB RAM',
        f'- **RTL:** {rtl}',
        f'- **Result:** {report["cycles_per_run"]:,.1f} clocks per run, {report["instructions_per_run"]:,.1f} instructions per run, '
        f'CPI {report["clocks_per_instruction"]:.3f}, **{report["dmips_per_mhz"]:.4f} DMIPS/MHz** '
        f'({report["number_of_runs"]} runs; non-compliant simulation run, evidence class E1)',
        f'- **Checks:** {passed}/{len(report["result_checks"])} result values; traces match the reference model at {waits} wait cycles',
        f'- **Trend:** {comparison}', '',
        f'Rubric scorecard (revision {card["rubric_revision"]}; evidence assessed {card["evidence_assessed"]} at '
        f'`{card["evidence_commit"]}`; automated self-assessment, not a review):', '',
    ]
    if card['evidence_stale']:
        lines += [f'**RTL or architecture version changed since the evidence was assessed (assessed at version '
                  f'{card["evidence_architecture_version"]}): hand-scored R1-R6 criteria count as 0 until '
                  '`cpu/rubric-evidence.json` is reassessed.**', '']
    lines += ['| Dimension | Points | Of | Score |', '|---|---:|---:|---:|']
    for d in card['dimensions']:
        points = '-' if d['points'] is None else f'{d["points"]:.1f}'
        percent = 'N/A' if d['percent'] is None else f'{d["percent"]:.0f}%'
        lines.append(f'| {d["id"]} {d["name"]} | {points} | {d["weight"]} | {percent} |')
    lines += [f'| **Total** | **{card["total"]:.1f}** | **100** | **{card["band"]}** |', '']
    met = [g for g, v in card['gates'].items() if v['status'] == 'met']
    unmet = [g for g, v in card['gates'].items() if v['status'] != 'met']
    lines.append(f'- **Gates met:** {", ".join(met) or "none"}. **Not met:** {", ".join(unmet) or "none"}.')
    for claim in card['claims']:
        state = 'granted' if claim['granted'] else 'not granted: ' + '; '.join(claim['missing'])
        lines.append(f'- **"{claim["claim"]}":** {state}.')
    lines.append(f'- **Computed this run:** R4.1 = {card["scores"]["R4.1"]} ({card["auto"]["R4.1"]}); '
                 f'HG2 {card["gates"]["HG2"]["status"]} ({card["auto"]["HG2"]})')
    record = {'time': now.strftime('%Y-%m-%d %H:%M:%S %z'), 'architecture_version': card['architecture_version'],
              'commit': commit, 'dirty': dirty, 'compiler': compiler,
              'optimization': report['optimization'], 'isa': report['scope']['isa'], 'ram_bytes': report['ram_bytes'],
              'cycles_per_run': report['cycles_per_run'], 'cpi': report['clocks_per_instruction'],
              'dmips_per_mhz': report['dmips_per_mhz'], 'rubric_total': round(card['total'], 2),
              'rtl_sha256': report['scope']['rtl_sha256']}
    lines += ['', f'<!-- dhrystone-run {json.dumps(record, separators=(",", ":"))} -->', '']
    return '\n'.join(lines)


def append_devlog(root, report, card):
    path = Path(root) / 'DEVLOG.md'
    text = path.read_text(encoding='utf-8')
    if RUN_LOG_HEADING not in text:
        text = text.rstrip('\n') + '\n\n---\n\n' + RUN_LOG_HEADING + '\n' + RUN_LOG_INTRO
    text = text.rstrip('\n') + '\n\n' + entry(root, report, card, previous_runs(text))
    path.write_text(text, encoding='utf-8', newline='\n')
