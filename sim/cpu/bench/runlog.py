"""Write benchmark runs to per-commit development logs.

Each run gets a detailed entry in devlog/devlog-<commit>.md, where <commit> is
the short hash of HEAD when the run started; the entry says whether the working
tree had uncommitted changes. DEVLOG.md keeps the daily summaries and one index
row per run, so detail can grow without making DEVLOG.md large.

Every entry ends with a one-line JSON record in an HTML comment. Later runs read
these records to report the change against the previous comparable run.
SPDX-License-Identifier: MIT
"""
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess

import rubric_score

LOG_DIR = 'devlog'
INDEX_HEADING = '## Run logs'
INDEX_INTRO = """
One row per benchmark run, oldest first. Each run's full record (result, rubric scorecard, profile, build commands and checks) is in its per-commit log under [devlog/](devlog/). Rows are added automatically by `sim/cpu/bench/run_bench.py --devlog`, which the Windows launcher passes on every run.

| Run time | Commit | Uncommitted changes | Architecture | Compiler | Clocks per run | DMIPS/MHz | Rubric | Log |
|---|---|---|---|---|---:|---:|---:|---|"""
RECORD = re.compile(r'^<!-- dhrystone-run (\{.*\}) -->$', re.MULTILINE)
TIME_FORMAT = '%Y-%m-%d %H:%M:%S %z'


def git(root, *args):
    try:
        # WSL sees Windows files as executable; ignore mode bits when checking for changes.
        done = subprocess.run(['git', '-c', 'safe.directory=*', '-c', 'core.fileMode=false', '-C', str(root), *args],
                              capture_output=True, text=True, timeout=30)
        # rstrip only: `git status --porcelain` lines start with a significant space.
        return done.stdout.rstrip() if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def previous_runs(root):
    records = []
    for path in sorted((Path(root) / LOG_DIR).glob('devlog-*.md')):
        records += [json.loads(m) for m in RECORD.findall(path.read_text(encoding='utf-8'))]
    return sorted(records, key=lambda r: datetime.strptime(r['time'], TIME_FORMAT))


def trend(report, compiler, previous):
    settings = (compiler, report['optimization'], report['scope']['isa'], report['ram_bytes'],
                report.get('runtime', 'reference'))
    same = [p for p in previous if (p['compiler'], p['optimization'], p['isa'], p['ram_bytes'],
                                    p.get('runtime', 'reference')) == settings]
    if not same:
        return 'first run with these build settings'
    last = same[-1]
    change = 100 * (report['cycles_per_run'] - last['cycles_per_run']) / last['cycles_per_run']
    text = (f'{change:+.2f}% clocks per run against the previous run with the same build settings '
            f'({last["time"]}, `{last["commit"]}`, architecture {last.get("architecture_version", "unrecorded")})')
    if abs(change) > 2:
        text += '. **Change over 2%: explain it in DEVLOG.md for this day.**'
    return text


def entry(report, card, prof, profile_markdown, when, commit, dirty, previous):
    compiler = report['compiler'].split(' (')[0]
    rtl = ', '.join(f'`{Path(k).name}` {v[:12]}' for k, v in report['scope']['rtl_sha256'].items())
    waits = ' and '.join(str(d['max_wait_cycles']) for d in report['differential'])
    passed = sum(c['pass'] for c in report['result_checks'])
    lines = [
        f'## Run {when}', '',
        f'- **Architecture:** version {card["architecture_version"]}',
        f'- **Commit:** `{commit}`, uncommitted changes: {dirty}',
        f'- **Build:** {compiler}, `-{report["optimization"]}`, `{report["scope"]["isa"]}`, {report["ram_bytes"] // 1024} KiB RAM, '
        f'{report.get("runtime", "reference")} runtime',
        f'- **RTL:** {rtl}',
        f'- **Result:** {report["cycles_per_run"]:,.1f} clocks per run, {report["instructions_per_run"]:,.1f} instructions per run, '
        f'CPI {report["clocks_per_instruction"]:.3f}, **{report["dmips_per_mhz"]:.4f} DMIPS/MHz** '
        f'({report["number_of_runs"]} runs; non-compliant simulation run, evidence class E1)',
        f'- **Checks:** {passed}/{len(report["result_checks"])} result values; traces match the reference model at {waits} wait cycles',
        f'- **Trend:** {trend(report, compiler, previous)}', '',
        '### Rubric scorecard', '',
        rubric_score.scorecard_markdown(card), '',
        profile_markdown, '',
        '### Result checks', '',
        '| Value | Expected | Actual | Pass |', '|---|---:|---:|---|',
    ]
    lines += [f'| {c["name"]} | {c["expected"]} | {c["actual"]} | {"yes" if c["pass"] else "**no**"} |'
              for c in report['result_checks']]
    lines += ['', '### Runs and tools', '',
              f'- Timed region: {report["timed_region"]["cycles"]:,} clocks, {report["timed_region"]["retired_instructions"]:,} '
              f'instructions ({report["timed_region"]["definition"]}).',
              f'- Whole program: {report["whole_program"]["cycles_after_reset"]:,} clocks, '
              f'{report["whole_program"]["retired_instructions"]:,} instructions.']
    lines += [f'- Differential run, up to {d["max_wait_cycles"]} wait cycles: {d["result"]}, {d["events"]:,} events, '
              f'`{d["simulator_summary"]}`.' for d in report['differential']]
    lines += [f'- Simulator: {report["simulator"]}. Host: {report["host"]["platform"]}, Python {report["host"]["python"]}.',
              f'- Wall time: timing run {report["wall_seconds"]["timing_run"]:.1f} s, reference model '
              f'{report["wall_seconds"]["reference_model"]:.1f} s.',
              f'- Instructions executed: {", ".join(f"`{n}`" for n in report["instruction_names_executed"])}.',
              '', 'Build commands:', '', '```text']
    lines += [' '.join(command) for command in report['build_commands']]
    lines += ['```', '']
    record = {'time': when, 'architecture_version': card['architecture_version'], 'commit': commit, 'dirty': dirty,
              'compiler': compiler, 'optimization': report['optimization'], 'isa': report['scope']['isa'],
              'ram_bytes': report['ram_bytes'], 'runtime': report.get('runtime', 'reference'),
              'cycles_per_run': report['cycles_per_run'],
              'cpi': report['clocks_per_instruction'], 'dmips_per_mhz': report['dmips_per_mhz'],
              'rubric_total': round(card['total'], 2), 'rtl_sha256': report['scope']['rtl_sha256']}
    lines += [f'<!-- dhrystone-run {json.dumps(record, separators=(",", ":"))} -->', '']
    return '\n'.join(lines), record


def add_index_row(root, record, log_name):
    path = Path(root) / 'DEVLOG.md'
    text = path.read_text(encoding='utf-8').rstrip('\n')
    if INDEX_HEADING not in text:
        text += '\n\n---\n\n' + INDEX_HEADING + '\n' + INDEX_INTRO
    dirty = record['dirty'].split(' (')[0]
    text += (f'\n| {record["time"]} | `{record["commit"]}` | {dirty} | '
             f'{record.get("architecture_version", "unrecorded")} | {record["compiler"]} `-{record["optimization"]}` `{record["isa"].split("_")[0] + ("b" if "_zbb" in record["isa"] else "")}`'
             f'{"" if record.get("runtime", "reference") == "reference" else " fast runtime"} | '
             f'{record["cycles_per_run"]:,.1f} | {record["dmips_per_mhz"]:.4f} | {record["rubric_total"]:.1f} | '
             f'[{log_name}]({LOG_DIR}/{log_name}) |\n')
    path.write_text(text, encoding='utf-8', newline='\n')


def write(root, report, card, prof, profile_markdown):
    root = Path(root)
    when = datetime.now().astimezone().strftime(TIME_FORMAT)
    commit = git(root, 'rev-parse', '--short', 'HEAD') or 'unknown'
    status = git(root, 'status', '--porcelain')
    if status is None:
        dirty = 'unknown'
    elif not status:
        dirty = 'no'
    else:
        changed = [line[3:] for line in status.splitlines()]
        dirty = 'yes (' + ', '.join(f'`{name}`' for name in changed[:8]) + (', ...' if len(changed) > 8 else '') + ')'
    log_name = f'devlog-{commit}.md'
    path = root / LOG_DIR / log_name
    path.parent.mkdir(exist_ok=True)
    text, record = entry(report, card, prof, profile_markdown, when, commit, dirty, previous_runs(root))
    if not path.is_file():
        subject = git(root, 'log', '-1', '--format=%s', commit) or 'unknown'
        header = (f'# Development log for commit `{commit}`\n\n'
                  f'Commit subject: {subject}\n\n'
                  'Detailed records of benchmark runs made while this commit was checked out. Each entry says whether '
                  'the working tree had uncommitted changes. Daily summaries and the index of all runs are in '
                  '[DEVLOG.md](../DEVLOG.md).\n')
        path.write_text(header, encoding='utf-8', newline='\n')
    with path.open('a', encoding='utf-8', newline='\n') as log:
        log.write('\n' + text)
    add_index_row(root, record, log_name)
    return path.relative_to(root).as_posix()
