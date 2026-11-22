"""One front end for the CPU tests and benchmarks: named suites, one command, one report.

    python -B sim/cpu/suite.py --list                          # suites, presets, steps
    python -B sim/cpu/suite.py release-patch --core-source cand.sv --dry-run
    python -B sim/cpu/suite.py release-patch --core-source cand.sv --expect sim/cpu/baselines/0.19.4-release-patch.json
    python -B sim/cpu/suite.py isa fpu --cache-sizes default,2,8 --only 'isa-*'
    python -B sim/cpu/suite.py icarus-full --jobs 3 --devlog-row

It wraps the existing entry points and leaves their command lines unchanged:
test_cpu.py, bench/run_bench.py, check_bitmanip.py, check_soc_memory.py, fp_cases.py,
scripts/check_repo.py and others. suite_manifest.py says which steps make up which
suite (and how to add one). This script plans the steps, runs them, checks each
one's output and prints a summary table.

Pass rule: a step passes only if it exits 0 AND its parser finds a positive pass
count or result line (test_cpu: "N programs x 3 wait patterns = R runs" with N, R > 0
and a matching verification.json; benchmarks: their PASS lines plus clock counts).
Exit 0 with no such line is a failure. Negative controls pass only by failing in the
expected way.

Exit codes: 0 every selected step passed (at least one ran); 1 a step failed, timed
out, differed from --expect or was blocked by a failed step; 2 usage or setup error;
3 nothing ran (everything skipped or unavailable).

Time limit: every invocation stops after 300 s (AGENTS.md). Work that does not fit is
split, never given longer: Icarus test_cpu runs into --shard K/N steps and one
--merge-shards step, run_bench sampled runs into --pieces A:B steps and --pieces merge.

Platform: runs from Windows (Python 3.11+) or from WSL/Linux. Simulation steps run in
Linux: from Windows through `wsl -e bash -c 'cd <repo> && timeout -k 10 300 ...'`.
Benchmark builds use the Windows LLVM (C:\\Program Files\\LLVM, clang 23.1.5 for every
logged number) from either side, falling back to clang on PATH with a warning.
In a git worktree, the ignored folders it needs are taken from the main worktree:
vendored Verilator and TinyBVH as directory junctions (visible from Windows and WSL;
remove a junction with rmdir, not a recursive delete), and the benchmark inputs
(QuickJS-ng, compiler-rt, smallpt, rt/js/mm/ternary reference data) as copies, because
build_bench.py records them by their resolved path.

Results: --out-dir (default build/suite/<time>) holds one log per step, each
test_cpu step's folder, a copy of each benchmark's results.json, results.json for the
whole run (--json prints it) and devlog-row.md (--devlog-row prints it).
SPDX-License-Identifier: MIT
"""
from pathlib import Path, PurePosixPath, PureWindowsPath
import argparse
import concurrent.futures as futures
import fnmatch
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim/cpu'))
import suite_manifest as M  # noqa: E402

IS_WIN = os.name == 'nt'
LIMIT = M.STEP_LIMIT
WIN_LLVM = Path(r'C:\Program Files\LLVM\bin')
WSL_LLVM = Path('/mnt/c/Program Files/LLVM/bin')
PASSLIKE = ('PASS', 'REUSED')
# Folders a fresh worktree lacks (ignored build/ content) that main's checkout has. Tools are
# linked (directory junctions); inputs of benchmark builds are copied, because build_bench.py
# resolves them and records them relative to the repository (a junction resolves into main).
WORKTREE_LINKS = {'build/third-party/verilator': 'link', 'build/third-party/tinybvh': 'link',
                  'build/third-party/quickjs-ng': 'copy', 'build/third-party/compiler-rt-builtins': 'copy',
                  'build/third-party/smallpt': 'copy', 'build/cpu/bench/rt-data': 'copy',
                  'build/cpu/bench/js-ref': 'copy', 'build/cpu/bench/mm-data': 'copy',
                  'build/cpu/bench/ternary-data': 'copy', 'build/third-party/riscv-tests-src': 'link'}
# Knobs passed through to the runners: option -> (runners, argparse dest).
KNOBS = {'--fpu': (('test_cpu', 'run_bench'), 'fpu'), '--vector': (('test_cpu', 'run_bench'), 'vector'),
         '--dline': (('test_cpu', 'run_bench'), 'dline'), '--n-miss': (('test_cpu', 'run_bench'), 'n_miss'),
         '--ld-lat': (('test_cpu', 'run_bench'), 'ld_lat'), '--l0': (('test_cpu', 'run_bench'), 'l0'),
         '--l0-lat': (('test_cpu', 'run_bench'), 'l0_lat'), '--l2-kib': (('run_bench',), 'l2_kib'),
         '--l2-ways': (('run_bench',), 'l2_ways'), '--l2-line': (('run_bench',), 'l2_line'),
         '--l2-lat': (('run_bench',), 'l2_lat'), '--mem-lat': (('run_bench',), 'mem_lat'),
         '--mem-gap': (('run_bench',), 'mem_gap'), '--write-fill': (('run_bench',), 'write_fill')}
RUNNER_SCRIPT = {'test_cpu': 'sim/cpu/test_cpu.py', 'run_bench': 'sim/cpu/bench/run_bench.py'}
# Metrics that are reported but not compared by --expect (derived or host-dependent).
INFO_METRICS = {'dmips_per_mhz', 'seconds'}


# ---------------------------------------------------------------- paths and commands

class Loc:
    """A path argument, rendered for the side (linux/host) a command runs on."""
    def __init__(self, path):
        self.path = Path(path)

    def render(self, side):
        p = self.path if self.path.is_absolute() else ROOT / self.path
        try:
            rel = p.resolve().relative_to(ROOT)
            return rel.as_posix() if side == 'linux' else str(rel)
        except ValueError:
            return to_linux(p) if side == 'linux' else str(p)


def to_linux(path):
    """Windows path -> WSL path (C:\\x\\y -> /mnt/c/x/y); Linux paths unchanged."""
    s = str(path)
    m = re.match(r'^([A-Za-z]):[\\/](.*)$', s)
    return f'/mnt/{m[1].lower()}/{m[2].replace(chr(92), "/")}' if m else s


def to_windows(path):
    s = str(path)
    m = re.match(r'^/mnt/([a-z])/(.*)$', s)
    return f'{m[1].upper()}:\\{m[2].replace("/", chr(92))}' if m else s


def render(args, side):
    return [a.render(side) if isinstance(a, Loc) else str(a) for a in args]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    # WSL's git cannot read a worktree made by Windows git (its gitdir is a C:/ path), so try git.exe too.
    for exe, where in (('git', str(ROOT)), ('git.exe', to_windows(ROOT))):
        try:
            done = subprocess.run([exe, '-C', where, *args], capture_output=True, text=True, timeout=60)
            if done.returncode == 0:
                return done.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def main_worktree():
    """The main checkout's root when ROOT is a linked worktree, else None."""
    dot = ROOT / '.git'
    if not dot.is_file():
        return None
    m = re.match(r'gitdir:\s*(.+)', dot.read_text(encoding='utf-8').strip())
    if not m:
        return None
    gitdir = Path(to_windows(m[1]) if IS_WIN else to_linux(m[1]))
    parts = gitdir.parts
    if 'worktrees' not in parts:
        return None
    common = Path(*parts[:parts.index('worktrees')])
    return common.parent if common.name == '.git' else None


def link_worktree(dry, log):
    main = main_worktree()
    if main is None:
        return []
    made = []
    for rel, how in WORKTREE_LINKS.items():
        src, dst = main / rel, ROOT / rel
        if not src.exists() or dst.exists() or dst.is_symlink():
            continue
        made.append(rel)
        log(f'{"would " if dry else ""}{"copy" if how == "copy" else "link"} {rel} from main worktree {src}')
        if dry:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if how == 'copy':
            shutil.copytree(src, dst)
        elif IS_WIN:
            import _winapi
            _winapi.CreateJunction(str(src), str(dst))
        elif shutil.which('cmd.exe') and str(ROOT).startswith('/mnt/'):
            subprocess.run(['cmd.exe', '/c', 'mklink', '/J', to_windows(dst), to_windows(src)],
                           capture_output=True, timeout=60, cwd='/mnt/c', check=True)
        else:
            os.symlink(src, dst)
    return made


def llvm():
    """(python argv prefix, tool options, label) for benchmark builds."""
    if IS_WIN and (WIN_LLVM / 'clang.exe').is_file():
        tools = {n: str(WIN_LLVM / f) for n, f in (('clang', 'clang.exe'), ('objcopy', 'llvm-objcopy.exe'),
                                                   ('objdump', 'llvm-objdump.exe'), ('nm', 'llvm-nm.exe'))}
        return [sys.executable, '-B'], tools, 'windows-llvm', 'host'
    winpy = shutil.which('python.exe')
    if not IS_WIN and (WSL_LLVM / 'clang.exe').is_file() and winpy:
        tools = {n: str(PureWindowsPath(r'C:\Program Files\LLVM\bin') / f) for n, f in (
            ('clang', 'clang.exe'), ('objcopy', 'llvm-objcopy.exe'), ('objdump', 'llvm-objdump.exe'),
            ('nm', 'llvm-nm.exe'))}
        return [winpy, '-B'], tools, 'windows-llvm', 'winpath'
    return [sys.executable, '-B'], {}, 'path-clang', 'host'


# ---------------------------------------------------------------- parsers

def ints(text):
    return int(text.replace(',', ''))


def need(pattern, out, what):
    m = re.search(pattern, out, re.M)
    if not m:
        raise ValueError(f'no {what} line')
    return m


def p_count(pattern):
    def parse(out, step, ctx):
        m = need(pattern, out, 'pass')
        n = ints(m[1])
        if n <= 0:
            raise ValueError(f'pass count {n} is not positive')
        return {'count': n}, m[0].strip()
    return parse


def p_unittest(out, step, ctx):
    n = ints(need(r'^Ran (\d+) tests?', out, '"Ran N tests"')[1])
    need(r'^OK\b', out, 'unittest OK')
    if n <= 0:
        raise ValueError('ran 0 tests')
    return {'tests': n}, f'{n} tests OK'


def p_test_cpu(out, step, ctx):
    if step.shard:
        m = need(r'^PASS shard (\d+)/(\d+) \((\w+) core, ([^)]+)\): (\d+) of (\d+) programs, (\d+) runs', out,
                 'test_cpu shard PASS')
        part, total, runs = int(m[5]), int(m[6]), int(m[7])
        if part <= 0 or runs <= 0 or total <= 0:
            raise ValueError(f'shard ran {part} programs, {runs} runs')
        if ctx is not None:
            shard = json.loads((ctx / 'shard.json').read_bytes())
            if len(shard['records']) != runs or len(shard['cases']) != part:
                raise ValueError('shard.json does not match the PASS line')
        return {'programs': part, 'runs': runs}, f'shard {m[1]}/{m[2]}: {part} of {total} programs, {runs} runs'
    m = need(r'^PASS \((\w+) core, ([^)]+)\): (\d+) programs x 3 wait patterns = (\d+) runs; (\d+) instruction '
             r'names covered', out, 'test_cpu PASS')
    programs, runs, names = int(m[3]), int(m[4]), int(m[5])
    if programs <= 0 or runs <= 0 or names <= 0:
        raise ValueError(f'{programs} programs, {runs} runs: nothing was tested')
    if runs < 3 * programs:
        raise ValueError(f'{runs} runs for {programs} programs (expected 3 or more each)')
    if ctx is not None:
        report = json.loads((ctx / 'verification.json').read_bytes())
        if report.get('status') != 'PASS' or report.get('runs') != runs or len(report.get('results', ())) != runs:
            raise ValueError('verification.json does not match the PASS line')
    return {'programs': programs, 'runs': runs, 'instruction_names': names}, \
        f'{programs} programs, {runs} runs, {names} names'


def p_dhrystone(out, step, ctx):
    m = need(r'^PASS: Dhrystone, (\d+) runs; all (\d+) result checks match', out, 'Dhrystone PASS')
    need(r'^PASS: differential traces match', out, 'differential PASS')
    t = need(r'^Timed region: ([\d,]+) cycles, ([\d,]+) instructions', out, 'Timed region')
    cycles, instr = ints(t[1]), ints(t[2])
    if cycles <= 0 or instr <= 0 or int(m[1]) <= 0 or int(m[2]) <= 0:
        raise ValueError('zero cycles, instructions or runs')
    d = re.search(r'^DMIPS/MHz: ([\d.]+)', out, re.M)
    metrics = {'timed_cycles': cycles, 'timed_instructions': instr, 'dhrystone_runs': int(m[1])}
    if d:
        metrics['dmips_per_mhz'] = float(d[1])
    return metrics, f'{cycles:,} cycles, {instr:,} instructions' + (f', {d[1]} DMIPS/MHz' if d else '')


def phases(out, pattern, keys):
    found = {}
    for m in re.finditer(pattern, out, re.M):
        for key, group in keys:
            found[f'{m[1].strip()}.{key}'] = ints(m[group])
    if not found or any(v <= 0 for k, v in found.items() if k.endswith('clocks')):
        raise ValueError('no phase clock lines (or a zero count)')
    return found


def p_lzma(out, step, ctx):
    need(r'^PASS: LZMA kernel', out, 'LZMA PASS')
    if '--no-differential' not in step.args:
        need(r'^PASS: differential traces match', out, 'differential PASS')
    found = phases(out, r'^(\w+): ([\d,]+) clocks, ([\d,]+) instructions', (('clocks', 2), ('instructions', 3)))
    return found, ', '.join(f'{k.split(".")[0]} {v:,}' for k, v in found.items() if k.endswith('clocks'))


def p_rt(out, step, ctx):
    need(r'^PASS: rt results equal the native reference', out, 'rt PASS')
    found = phases(out, r'^([^:\n]+): ([\d,]+) clocks, IPC', (('clocks', 2),))
    return found, ', '.join(f'{k[:-7]} {v:,}' for k, v in found.items())


def p_js(out, step, ctx):
    need(r'^PASS: js results equal the native reference', out, 'js PASS')
    found = phases(out, r'^([\w.-]+): ([\d,]+) clocks, ([\d,]+) instructions', (('clocks', 2), ('instructions', 3)))
    total = found.get('total.clocks')
    return found, f'{len(found) // 2} lines' + (f', total {total:,} clocks' if total else '')


def p_pieces(out, step, ctx):
    need(r'^Saved .*plan has (\d+) pieces', out, '"Saved ... plan has N pieces"')
    clocks = [ints(m[2]) for m in re.finditer(r'^piece (\d+) .*?: ([\d,]+) clocks', out, re.M)]
    if not clocks or min(clocks) <= 0:
        raise ValueError('no timed pieces')
    return {'pieces': len(clocks), 'clocks': sum(clocks)}, f'{len(clocks)} pieces, {sum(clocks):,} clocks'


def p_bench(out, step, ctx):
    """Any benchmark runner: PASS lines and "<name>: N clocks" lines."""
    if not re.search(r'^PASS', out, re.M):
        raise ValueError('no PASS line')
    found = phases(out, r'^([^:\n]+): ([\d,]+) clocks', (('clocks', 2),))
    return found, ', '.join(f'{k[:-7]} {v:,}' for k, v in list(found.items())[:4])


def p_soc_memory(out, step, ctx):
    need(r'^PASS: SoC memory-model checks', out, 'PASS')
    n = len(re.findall(r'^ok ', out, re.M))
    if n <= 0 or re.search(r'^FAIL', out, re.M):
        raise ValueError('no passing checks listed')
    return {'checks': n}, f'{n} checks'


def p_btb(out, step, ctx):
    m = need(r'BTBTEST ok=(\d+) bad=(\d+) old_wrong=(\d+) of (\d+) pairs: PASS', out, 'BTBTEST PASS')
    if int(m[1]) <= 0 or int(m[2]):
        raise ValueError('no BTB pairs checked')
    return {'pairs': int(m[1])}, f'{m[1]} of {m[4]} pairs'


def p_check_repo(out, step, ctx):
    need(r'^PASS: reports in', out, 'PASS: reports')
    n = len(re.findall(r'^PASS \S+\.py', out, re.M))
    if n <= 0:
        raise ValueError('no planning programs passed')
    return {'programs': n}, f'{n} planning programs, metadata checks'


def p_build(out, step, ctx):
    if ctx is None or not (ctx / 'build.json').is_file():
        raise ValueError('no build.json')
    build = json.loads((ctx / 'build.json').read_bytes())
    if not build.get('artifact_sha256'):
        raise ValueError('build.json lists no artifacts')
    return {'payload_bytes': build.get('payload_bytes', 0)}, f'{build.get("compiler", "?")[:40]}'


PARSERS = {'unittest': p_unittest, 'test_cpu': p_test_cpu, 'dhrystone': p_dhrystone, 'lzma': p_lzma, 'rt': p_rt,
           'js': p_js, 'pieces': p_pieces, 'bench': p_bench, 'soc_memory': p_soc_memory, 'btb': p_btb,
           'check_repo': p_check_repo, 'build': p_build}


def parser_for(name):
    return p_count(name[6:]) if name.startswith('count:') else PARSERS[name]


def evaluate(step, rc, out, timed_out, folder):
    """(status, metrics, summary). A pass needs rc 0 and the parser's result line."""
    if timed_out or rc in (124, 137):
        return 'TIMEOUT', {}, f'stopped at the {LIMIT} s limit (split the step; never raise the limit)'
    errors = re.findall(r'^(?:\w+(?:Error|Exception|Exit)\b|FAIL\b|Command failed).*$', out, re.M)
    last = errors[-1] if errors else next((x for x in reversed(out.strip().splitlines()) if x.strip()), '')
    if step.expect_fail:
        m = re.search(step.expect_fail, out, re.M)
        if rc == 0:
            return 'FAIL', {}, 'negative control PASSED: the check cannot see this mutation'
        if not m:
            return 'FAIL', {}, f'negative control failed for another reason (rc {rc}): {last[:160]}'
        return 'PASS', {'rejected': 1}, f'mutant rejected as expected: {m[0][:120]}'
    try:
        metrics, summary = parser_for(step.parser)(out, step, folder)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
        if rc:
            return 'FAIL', {}, f'rc {rc}: {last[:200]}'
        return 'FAIL', {}, f'exit 0 but {e}: not counted as a pass'
    if rc:
        return 'FAIL', metrics, f'rc {rc} despite a pass line: {last[:160]}'
    if re.search(r'^Traceback \(most recent call last\)', out, re.M):
        return 'FAIL', metrics, 'exit 0 with a Python traceback in the output'
    return 'PASS', metrics, summary


def compare(results, baseline, fail):
    """--expect (fail=True) / --compare: identity of metrics against a previous results.json."""
    notes = []
    for name, r in results.items():
        b = baseline.get('steps', {}).get(name)
        if r['status'] != 'PASS' or not b or 'metrics' not in b:
            continue
        diffs = [f'{k} {v:,} -> {r["metrics"].get(k, "missing")}' for k, v in b['metrics'].items()
                 if k not in INFO_METRICS and r['metrics'].get(k) != v]
        if diffs:
            notes.append(f'{name}: ' + '; '.join(diffs))
            r['expect'] = 'DIFF: ' + '; '.join(diffs)
            if fail:
                r['status'] = 'DIFF'
        else:
            r['expect'] = 'same as baseline'
    return notes


# ---------------------------------------------------------------- planning

class Context:
    def __init__(self, args):
        self.cores = args.core
        self.sim = args.sim
        self.cache_sizes = args.cache_sizes
        self.fpu = args.fpu


def available(step, args, core_text):
    """None if the step can run, else the reason it cannot. Conditions joined by '&' must all hold."""
    for w in (step.when or '').split('&'):
        why = condition(w.strip(), args, core_text) if w.strip() else None
        if why:
            return why
    return None


def condition(w, args, core_text):
    if w.startswith('path-exists:'):
        rel = w.split(':', 1)[1]
        return None if (ROOT / rel).exists() else f'{rel} is missing (see the step note)'
    if w == 'core-has-fpu':
        return None if 'RV64_OOO_FPU' in core_text else 'the core under test has no RV64_OOO_FPU'
    if w.startswith('runner-has:'):
        _, script, flag = w.split(':')
        return None if f"'{flag}'" in (ROOT / script).read_text(encoding='utf-8') else f'{script} has no {flag} yet'
    if w.startswith('bench-exists:'):
        kind = w.split(':', 1)[1]
        for script in ('sim/cpu/bench/run_bench.py', 'sim/cpu/bench/build_bench.py'):
            if f"'{kind}'" not in (ROOT / script).read_text(encoding='utf-8'):
                return f'{script} has no --benchmark {kind} yet'
        return None
    raise ValueError(f'unknown condition {w}')


def selected(step, patterns):
    keys = [step.name, *step.suites, *step.tags]
    return any(fnmatch.fnmatch(k, p) for p in patterns for k in keys)


def plan(args, log=print):
    """Steps to run in order (with build, shard and merge steps added), plus skipped ones."""
    names = []
    for item in args.suites:
        names += M.PRESETS.get(item, [item])
    unknown = [n for n in names if n not in M.GENERATORS]
    if unknown:
        raise SystemExit(f'error: unknown suite or preset {unknown}; see --list')
    ctx = Context(args)
    core_file = Path(args.core_source) if args.core_source else ROOT / 'rtl/cpu/rv64_ooo.sv'
    core_text = core_file.read_text(encoding='utf-8', errors='replace')
    steps, skipped, seen = [], [], set()
    for gen_name, gen in M.GENERATORS.items():
        for step in gen(ctx):
            if step.name in seen or not set(step.suites) & set(names):
                continue
            seen.add(step.name)
            if args.only and not selected(step, args.only):
                continue
            if args.skip and selected(step, args.skip):
                skipped.append((step, 'skipped by --skip'))
                continue
            why = available(step, args, core_text)
            if why:
                skipped.append((step, f'unavailable: {why}'))
                continue
            steps.append(step)
    # Knobs: pass through to runners that have them, or stop with a clear error.
    for opt, (runners, dest) in KNOBS.items():
        value = getattr(args, dest)
        if value in (None, False):
            continue
        for runner in runners:
            if f"'{opt}'" not in (ROOT / RUNNER_SCRIPT[runner]).read_text(encoding='utf-8') and \
                    any(s.runner == runner for s in steps):
                raise SystemExit(f'error: {opt} was given but {RUNNER_SCRIPT[runner]} has no {opt} on this tree')
        for s in steps:
            if s.runner not in runners or (dest in M.OOO_ONLY and s.core != 'ooo') or opt in s.args:
                continue
            s.args += [opt] if value is True else [opt, str(value)]
    for s in steps:
        if s.runner == 'test_cpu' and args.test_args:
            s.args += shlex.split(args.test_args)
        if s.runner == 'run_bench' and args.bench_args:
            s.args += shlex.split(args.bench_args)
        s.args = [ctx_sim(s, args) if a is None else a for a in s.args]
        # The candidate: --core-source for runners that take it; check_btb_reach.py gets it as its
        # positional core (@core), the negative control as the file it mutates.
        if s.candidate and args.core_source and not s.mutate and '@core' not in s.args:
            s.args += ['--core-source', Loc(args.core_source)]
    return split_steps(steps, args), skipped


def ctx_sim(step, args):
    return step.sim or args.sim


def split_steps(steps, args):
    """Icarus test_cpu runs that cannot fit in 300 s become shards plus a merge step."""
    out = []
    for s in steps:
        size = 'default'
        if '--icache-beats' in s.args:
            size = s.args[s.args.index('--icache-beats') + 1]
        key = (s.core, 'small' if M.is_small(size) else 'default')
        sim = s.args[s.args.index('--sim') + 1] if '--sim' in s.args else None
        n = M.ICARUS_SHARDS.get(key) if s.runner == 'test_cpu' and sim == 'icarus' and not s.expect_fail else None
        if not n:
            out.append(s)
            continue
        parts = []
        for k in range(n):
            part = M.Step(f'{s.name}.s{k}of{n}', s.suites, s.script, [*s.args, '--shard', f'{k}/{n}'], s.parser,
                          tags=(*s.tags, 'shard'), core=s.core, candidate=s.candidate, sim=s.sim, runner=s.runner,
                          est=max(30, s.est // n), shard=(k, n), note=s.note)
            parts.append(part)
            out.append(part)
        merge = M.Step(s.name, s.suites, s.script, [*s.args, '--merge-shards', *[('@step', p.name) for p in parts]],
                       s.parser, tags=s.tags, core=s.core, candidate=s.candidate, sim=s.sim, runner=s.runner,
                       needs=[p.name for p in parts], est=60, note=f'merge of {n} shards')
        out.append(merge)
    # Benchmark builds the bench steps need, first.
    builds, final = {}, []
    for s in out:
        if s.bench and s.bench.name not in builds:
            b = s.bench
            builds[b.name] = M.Step(f'build:{b.name}', s.suites, 'sim/cpu/bench/build_bench.py', list(b.args),
                                    'build', tags=('build',), side='llvm', out_arg='--out-dir:bench', bench=b,
                                    lock=b.name, est=20)
            final.append(builds[b.name])
        if s.bench:
            s.needs = [*s.needs, f'build:{s.bench.name}']
    return final + out


# ---------------------------------------------------------------- running

class Runner:
    def __init__(self, args):
        self.args = args
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        self.out = Path(args.out_dir) if args.out_dir else ROOT / 'build/suite' / stamp
        if not self.out.is_absolute():
            self.out = ROOT / self.out
        self.bench_root = Path(args.bench_root) if args.bench_root else ROOT / 'build/suite/bench'
        if not self.bench_root.is_absolute():
            self.bench_root = ROOT / self.bench_root
        self.py, self.tools, self.llvm_label, self.llvm_paths = llvm()
        self.lock = threading.Lock()
        self.core_file = Path(args.core_source).resolve() if args.core_source else ROOT / 'rtl/cpu/rv64_ooo.sv'
        # Native scratch for Linux steps when the repository lives on a Windows drive (see native_wrap).
        self.native = not getattr(args, 'no_native_scratch', False) and (IS_WIN or str(ROOT).startswith('/mnt/'))

    def folder(self, step):
        if step.name.startswith('build:') or step.out_arg == '--out-dir:bench':
            return self.bench_root / step.bench.name
        return self.out / step.name.replace(':', '_')

    def argv(self, step):
        """(argv to run, display string, side)."""
        side = 'host' if step.side == 'llvm' else step.side
        args = []
        for a in step.args:
            if isinstance(a, tuple) and a[0] == '@step':
                args.append(Loc(self.out / a[1]))
            elif a == '@core':
                args.append(Loc(self.mutant(step) if step.mutate else self.core_file))
            elif a == '@out':
                args.append(Loc(self.folder(step)))
            else:
                args.append(a)
        if step.mutate:
            args += ['--core-source', Loc(self.mutant(step))]
        if step.out_arg:
            args += ['--out-dir', Loc(self.folder(step))]
        if step.side == 'llvm':
            for name, path in self.tools.items():
                args += [f'--{name}', path]
            if self.llvm_paths == 'winpath':
                script = to_windows(ROOT / step.script)
                rendered = [to_windows(a.path if a.path.is_absolute() else ROOT / a.path) if isinstance(a, Loc)
                            else str(a) for a in args]
                cmd = [*self.py, script, *rendered]
                return cmd, shlex.join(cmd), 'host'
        if side == 'linux':
            cmd = ['python3', '-B', step.script, *render(args, 'linux')]
            inner = f'timeout -k 10 {LIMIT} {shlex.join(cmd)}'
            if self.native:
                inner = self.native_wrap(step, args, cmd)
            run = inner if self.native else f'exec {inner}'   # the native wrapper is a command sequence
            if IS_WIN:
                full = ['wsl', '-e', 'bash', '-c', f'cd {shlex.quote(to_linux(ROOT))} && {{ {run}; }}']
                return full, inner, 'linux'
            return ['bash', '-c', f'cd {shlex.quote(str(ROOT))} && {{ {run}; }}'], inner, 'linux'
        cmd = [*([sys.executable, '-B'] if side == 'host' and step.side != 'llvm' else self.py), step.script,
               *render(args, 'host')]
        return cmd, shlex.join(str(c) for c in cmd), 'host'

    def native_wrap(self, step, args, cmd):
        """Linux steps on a repository on a Windows drive (/mnt/...): write every output folder in WSL's own
        file system, then copy the small result files back. Files written through /mnt/c under load lost
        characters (2026-11-21 NUL bytes; 2026-11-22 05:4x a trace line with characters missing), so traces
        and pieces never touch /mnt/c. Bench folders are copied in first (their images are inputs)."""
        own = Loc(self.folder(step)).render('linux')
        outs = [own] + [Loc(self.out / a[1]).render('linux') for a in step.args
                        if isinstance(a, tuple) and a[0] == '@step']
        bench = (step.out_arg == '--out-dir:bench' or step.name.startswith('build:'))
        mapped = list(dict.fromkeys(outs))
        q = shlex.quote
        # One native folder per tree and run (middle 06:59: a shared folder let concurrent suites in different
        # trees overwrite each other's bench folders and source snapshots). Run folders older than 12 h are pruned.
        run = hashlib.sha256(f'{ROOT}\n{self.out}'.encode()).hexdigest()[:16]
        parts = ['NB="$HOME/.cache/rv64-suite"',
                 'find "$NB" -mindepth 1 -maxdepth 1 -name "run-*" -mmin +720 -exec rm -rf {} + 2>/dev/null',
                 f'NS="$NB"/run-{run}']
        for d in mapped:
            parts.append(f'mkdir -p "$NS"/{q(d)}')
        if bench:   # refresh the native copy of the bench folder when its build changed
            parts.append(f'if ! cmp -s {q(own)}/build.json "$NS"/{q(own)}/build.json 2>/dev/null; then '
                         f'rm -rf "$NS"/{q(own)} && mkdir -p "$NS"/{q(own)} && cp -a {q(own)}/. "$NS"/{q(own)}/; fi')
        rendered = []
        for c in cmd:
            rendered.append(f'"$NS"/{q(c)}' if c in mapped else q(c))
        parts.append(f'timeout -k 10 {LIMIT} ' + ' '.join(rendered))
        parts.append('rc=$?')
        parts.append(f'mkdir -p {q(own)} && find "$NS"/{q(own)} -maxdepth 1 -type f '
                     r"\( -name '*.json' -o -name '*.log' -o -name '*.txt' -o -name '*.md' \) -size -8M "
                     f'-exec cp -p {{}} {q(own)}/ ' + '\\;')
        parts.append('exit $rc')
        return '; '.join(parts)

    def mutant(self, step):
        path = self.out / f'{step.name}-mutant.sv'
        if not path.is_file():
            text = self.core_file.read_text(encoding='utf-8')
            old, new = step.mutate
            if text.count(old) != 1:
                raise RuntimeError(f'mutation anchor {old!r} occurs {text.count(old)} times in {self.core_file}; '
                                   'update suite_manifest.negative')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
        return path

    def reusable(self, step):
        """A bench folder whose inputs, artifacts and compiler match is not rebuilt."""
        folder = self.folder(step)
        try:
            build = json.loads((folder / 'build.json').read_bytes())
            if any(sha256(ROOT / n) != d for n, d in build['input_sha256'].items()):
                return None
            if any(sha256(folder / n) != d for n, d in build['artifact_sha256'].items()):
                return None
            want = self.compiler()
            if want and build.get('compiler') != want:
                return None
            return build
        except (OSError, KeyError, json.JSONDecodeError):
            return None

    def compiler(self):
        if not hasattr(self, '_compiler'):
            clang = self.tools.get('clang') or shutil.which('clang') or 'clang'
            if self.llvm_paths == 'winpath':
                clang = str(WSL_LLVM / 'clang.exe')
            try:
                self._compiler = subprocess.run([clang, '--version'], capture_output=True, text=True,
                                                timeout=60).stdout.splitlines()[0]
            except (OSError, IndexError, subprocess.TimeoutExpired):
                self._compiler = None
        return self._compiler

    def run(self, step):
        start = time.time()
        folder = self.folder(step)
        log = self.out / f'{step.name.replace(":", "_")}.log'
        if step.name.startswith('build:') and not self.args.rebuild:
            build = self.reusable(step)
            if build:
                return self.result(step, 'REUSED', 0, {'payload_bytes': build.get('payload_bytes', 0)},
                                   f'valid build reused ({build.get("compiler", "?")[:32]})', '', start, log)
        try:
            argv, shown, side = self.argv(step)
        except RuntimeError as e:
            return self.result(step, 'ERROR', None, {}, str(e), '', start, log)
        if step.runner == 'test_cpu' or step.expect_fail:
            folder.mkdir(parents=True, exist_ok=True)
        timed_out = False
        try:
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=LIMIT + 30)
            rc, out = done.returncode, done.stdout + done.stderr
        except subprocess.TimeoutExpired as e:
            timed_out, rc = True, None
            out = (e.stdout or b'').decode('utf-8', 'replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f'$ {shown}\n{out}', encoding='utf-8')
        status, metrics, summary = evaluate(step, rc, out, timed_out, folder)
        if step.bench and not step.name.startswith('build:'):
            for name in ('results.json', f'results-{step.core}.json'):
                if (folder / name).is_file():   # bench folders are shared: keep this step's copy
                    shutil.copyfile(folder / name, self.out / f'{step.name}.{name}')
        return self.result(step, status, rc, metrics, summary, shown, start, log)

    def result(self, step, status, rc, metrics, summary, shown, start, log):
        core = None
        if step.core:
            core = (self.mutant(step).name if step.mutate else
                    self.core_file.name if step.candidate and self.args.core_source else
                    Path(CORES[step.core]).name)
        return {'status': status, 'rc': rc, 'seconds': round(time.time() - start, 1), 'command': shown,
                'side': step.side, 'suites': list(step.suites), 'core_file': core, 'metrics': metrics,
                'summary': summary, 'log': Loc(log).render('linux'), 'note': step.note}

    def execute(self, steps, emit):
        results, pending, running = {}, list(steps), {}
        jobs = self.args.jobs
        with futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            while pending or running:
                busy = sum(s.weight for s in running.values())
                locks = {s.lock for s in running.values() if s.lock}
                for s in list(pending):
                    if any(d not in results for d in s.needs):
                        continue
                    bad = [d for d in s.needs if results[d]['status'] not in PASSLIKE]
                    if bad:
                        pending.remove(s)
                        results[s.name] = {'status': 'BLOCKED', 'rc': None, 'seconds': 0, 'command': '',
                                           'side': s.side, 'suites': list(s.suites), 'core_file': None,
                                           'metrics': {}, 'summary': f'not run: {", ".join(bad)} did not pass',
                                           'log': '', 'note': s.note}
                        emit(s, results[s.name])
                        continue
                    if s.lock and s.lock in locks:
                        continue
                    if running and busy + s.weight > jobs:
                        continue
                    pending.remove(s)
                    running[pool.submit(self.run, s)] = s
                    busy += s.weight
                    if s.lock:
                        locks.add(s.lock)
                if not running:
                    if pending:   # only blocked-by-lock steps remain; cannot happen with nothing running
                        raise RuntimeError('scheduler stalled')
                    break
                done, _ = futures.wait(running, return_when=futures.FIRST_COMPLETED)
                for f in done:
                    s = running.pop(f)
                    try:
                        results[s.name] = f.result()
                    except Exception as e:  # noqa: BLE001 - a harness error is a failed step, never a pass
                        results[s.name] = {'status': 'ERROR', 'rc': None, 'seconds': 0, 'command': '',
                                           'side': s.side, 'suites': list(s.suites), 'core_file': None,
                                           'metrics': {}, 'summary': f'harness error: {e!r}', 'log': '',
                                           'note': s.note}
                    emit(s, results[s.name])
        return results


# test_cpu.CORES (not imported: test_cpu.py needs a simulator on import paths)
CORES = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}
SHARD_NAME = re.compile(r'\.s\d+of\d+$')


# ---------------------------------------------------------------- tools, report, devlog row

def probe_tools():
    """--probe-tools: versions on this side, as JSON (run on the Linux side by the front end)."""
    import simulator
    info = {'python3': platform.python_version(), 'machine': platform.machine()}
    for name in ('verilator', 'icarus'):
        try:
            sim = simulator.get(name)
            info[name] = sim.version()
            if name == 'verilator':
                info['verilator_cxx'] = sim.cxx_version()
        except BaseException as e:  # noqa: BLE001 - SimulatorMissing is a SystemExit
            info[name] = f'missing ({e})'
    print(json.dumps(info))


def tools_info(runner, need_linux):
    info = {'python_host': f'{platform.python_version()} ({platform.system()} {platform.machine()})',
            'bench_compiler': runner.compiler(), 'bench_compiler_source': runner.llvm_label}
    if need_linux:
        inner = 'python3 -B sim/cpu/suite.py --probe-tools'
        argv = (['wsl', '-e', 'bash', '-c', f'cd {shlex.quote(to_linux(ROOT))} && {inner}'] if IS_WIN
                else ['bash', '-c', inner])
        try:
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
            info.update(json.loads(done.stdout.strip().splitlines()[-1]))
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            info['linux'] = f'probe failed: {e}'
    return info


def commit_info():
    head = git('rev-parse', '--short', 'HEAD') or 'unknown'
    dirty = git('status', '--porcelain', '--untracked-files=no')
    return {'commit': head, 'uncommitted': bool(dirty), 'changed_files': (dirty or '').count('\n') + bool(dirty)}


def table(steps, results):
    rows = [('step', 'status', 'secs', 'core', 'result')]
    for s in steps:
        r = results.get(s.name)
        if r:
            rows.append((s.name, r['status'], f'{r["seconds"]:.0f}', r['core_file'] or '-',
                         r['summary'] + (f' [{r["expect"]}]' if r.get('expect') else '')))
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    return '\n'.join(f'{a:<{w[0]}}  {b:<{w[1]}}  {c:>{w[2]}}  {d:<{w[3]}}  {e}' for a, b, c, d, e in rows)


def devlog_row(report):
    t0, t1 = report['started'][11:16], report['finished'][11:16]
    c = report['commit']
    commit = f'`{c["commit"]}`' + (' with uncommitted changes' if c['uncommitted'] else '')
    tools = report['tools']
    tv = '; '.join(f'{k} {v}' for k, v in tools.items() if v)
    core = report.get('core_source') or 'rtl/cpu/rv64_ooo.sv'
    steps = report['steps']
    passed = sum(r['status'] in PASSLIKE for r in steps.values())
    bad = [n for n, r in steps.items() if r['status'] not in PASSLIKE]
    res = '; '.join(f'{n} {r["status"]}' + (f' ({r["summary"]})' if r['summary'] else '')
                    for n, r in steps.items() if not n.startswith('build:') and not SHARD_NAME.search(n))
    def short(cmd):   # the LLVM tool options and interpreter paths are the same for every build
        cmd = re.sub(r"\s--(clang|objcopy|objdump|nm) '?[^ ']*(?: [^ ']*)*'?(?=\s--|$)", '', cmd)
        return re.sub(r"^'?[^ ']*python(?:\.exe)?'? ", 'python ', cmd)
    cmds = '; '.join(f'`{short(r["command"])}`' for n, r in steps.items()
                     if r['command'] and not SHARD_NAME.search(n))
    shards = [r['command'] for n, r in steps.items() if SHARD_NAME.search(n) and r['command']]
    shard_note = (f' Shard steps: {len(shards)}, each the merge command with `--shard K/N` and its own --out-dir '
                  f'(commands in results.json).' if shards else '')
    if any(n.startswith('build:') and r['command'] for n, r in steps.items()):
        shard_note += f' Builds use {tools.get("bench_compiler_source")} tools (--clang/--objcopy/--objdump/--nm).'
    exp = report.get('expect') and Loc(report['expect']).render('linux')
    expect = f' Expect `{exp}`: ' + ('all identity metrics equal.' if not report['expect_notes'] else
                                               'DIFF ' + '; '.join(report['expect_notes']) + '.') \
        if report.get('expect') else ''
    verdict = 'PASS' if not bad else f'FAIL ({", ".join(bad)})'
    return (f'| {t0} to {t1} | **suite.py {" ".join(report["selection"])}: {verdict}** ({report["who"]}; '
            f'commit {commit}; core `{core}` sha256 {report["core_sha256"][:8]}; {tv}). '
            f'Command: `{report["argv"]}`. Steps: {cmds}.{shard_note} Results: {res}. '
            f'{passed} of {len(steps)} steps passed, {len(report["skipped"])} skipped, '
            f'{report["wall_seconds"]:.0f} s wall, --jobs {report["jobs"]}.{expect} '
            f'(source: suite.py output, `{report["results_file"]}`) |')


# ---------------------------------------------------------------- self-test

def self_test():
    """Negative controls of the harness itself: nothing here may pass by accident."""
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    S = M.Step
    tc = S('t', ('isa',), 'sim/cpu/test_cpu.py', [], 'test_cpu')
    good = ('PASS (ooo core, Verilator): 131 programs x 3 wait patterns = 393 runs; 106 instruction names '
            'covered.\n')
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / 'verification.json').write_text(json.dumps({'status': 'PASS', 'runs': 393, 'results': [0] * 393}))
        check('test_cpu pass', evaluate(tc, 0, good, False, d)[0] == 'PASS')
        check('test_cpu rc 1 with PASS line', evaluate(tc, 1, good, False, d)[0] == 'FAIL')
        check('test_cpu exit 0, no PASS line', evaluate(tc, 0, 'done\n', False, d)[0] == 'FAIL')
        zero = good.replace('131 programs', '0 programs').replace('393 runs', '0 runs')
        check('test_cpu zero programs', evaluate(tc, 0, zero, False, d)[0] == 'FAIL')
        check('test_cpu traceback after PASS', evaluate(tc, 0, good + 'Traceback (most recent call last):\n',
                                                        False, d)[0] == 'FAIL')
        check('timeout is not a pass', evaluate(tc, 124, good, False, d)[0] == 'TIMEOUT')
        check('python-side timeout', evaluate(tc, None, good, True, d)[0] == 'TIMEOUT')
        (d / 'verification.json').write_text(json.dumps({'status': 'PASS', 'runs': 3, 'results': [0] * 3}))
        check('verification.json mismatch', evaluate(tc, 0, good, False, d)[0] == 'FAIL')
        empty = Path(tmp) / 'none'
        check('missing verification.json', evaluate(tc, 0, good, False, empty)[0] == 'FAIL')
        sh = S('t.s0of4', ('isa',), 'sim/cpu/test_cpu.py', [], 'test_cpu', shard=(0, 4))
        line = 'PASS shard 0/4 (ooo core, Icarus Verilog): 0 of 131 programs, 0 runs; x\n'
        check('empty shard', evaluate(sh, 0, line, False, None)[0] == 'FAIL')
    dh = S('d', ('bench',), 'run_bench.py', [], 'dhrystone')
    dgood = ('PASS: Dhrystone, 500 runs; all 17 result checks match.\nPASS: differential traces match the reference '
             'model at wait cycles [0, 7].\nTimed region: 15,706 cycles, 275,030 instructions; x\nDMIPS/MHz: 18.1189\n')
    st, met, _ = evaluate(dh, 0, dgood, False, None)
    check('dhrystone pass and clocks', st == 'PASS' and met['timed_cycles'] == 15706)
    check('dhrystone without differential', evaluate(dh, 0, dgood.replace('PASS: differential', 'x'), False,
                                                     None)[0] == 'FAIL')
    check('dhrystone zero cycles', evaluate(dh, 0, dgood.replace('15,706', '0'), False, None)[0] == 'FAIL')
    lz = S('l', ('bench',), 'run_bench.py', [], 'lzma')
    lgood = ('PASS: LZMA kernel, 4160 bytes\nPASS: differential traces match the reference model (24 runs)\n'
             'compress_kernel: 384,788 clocks, 3,065,962 instructions, IPC 7.968\n')
    check('lzma pass', evaluate(lz, 0, lgood, False, None)[0] == 'PASS')
    check('lzma without phase lines', evaluate(lz, 0, lgood.splitlines()[0] + '\n', False, None)[0] == 'FAIL')
    neg = S('n', ('negative',), 'test_cpu.py', [], 'test_cpu', expect_fail=r'AssertionError: \S+ stall=\d+ event \d+')
    check('mutant that passes fails the control', evaluate(neg, 0, good, False, None)[0] == 'FAIL')
    check('mutant build error fails the control', evaluate(neg, 1, 'RuntimeError: Command failed: verilator',
                                                           False, None)[0] == 'FAIL')
    check('mutant trace mismatch passes the control', evaluate(
        neg, 1, 'AssertionError: xor_case stall=0 event 3:\nactual x\nexpect y', False, None)[0] == 'PASS')
    res = {'d': {'status': 'PASS', 'metrics': {'timed_cycles': 15707, 'dmips_per_mhz': 1.0}}}
    compare(res, {'steps': {'d': {'metrics': {'timed_cycles': 15706, 'dmips_per_mhz': 2.0}}}}, True)
    check('--expect catches a clock change', res['d']['status'] == 'DIFF')
    res = {'d': {'status': 'PASS', 'metrics': {'timed_cycles': 15706, 'dmips_per_mhz': 1.0}}}
    compare(res, {'steps': {'d': {'metrics': {'timed_cycles': 15706, 'dmips_per_mhz': 2.0}}}}, True)
    check('--expect ignores derived metrics', res['d']['status'] == 'PASS')
    check('unittest zero tests', evaluate(S('u', ('unit',), 'x', [], 'unittest'), 0, 'Ran 0 tests\nOK\n', False,
                                          None)[0] == 'FAIL')
    # The manifest: unique names, known parsers, no step planned above the limit.
    ns = argparse.Namespace(core=['ooo'], sim='verilator', cache_sizes=list(M.DEFAULT_CACHE_SIZES), fpu=False)
    ctx = Context(ns)
    allsteps = [s for g in M.GENERATORS.values() for s in g(ctx)]
    check('manifest step names unique', len({s.name for s in allsteps}) == len(allsteps))
    check('manifest parsers known', all(s.parser.startswith('count:') or s.parser in PARSERS for s in allsteps))
    check('every suite has a step', all(any(n in s.suites for s in allsteps) for n in M.SUITES))
    check('presets name suites', all(n in M.GENERATORS for p in M.PRESETS.values() for n in p))
    check('limit is 300 s', LIMIT == 300)
    cond = S('c', ('unit',), 'x', [], 'unittest', when='path-exists:sim/cpu/suite.py & path-exists:no/such/dir')
    check('every joined condition must hold', available(cond, None, '') is not None)
    cond.when = 'path-exists:sim/cpu/suite.py & core-has-fpu'
    check('joined conditions that hold', available(cond, None, 'RV64_OOO_FPU') is None)
    failed = [n for n, ok in checks if not ok]
    if failed:
        print(f'FAIL: suite self-test: {failed}')
        return 1
    print(f'PASS: suite self-test, {len(checks)} checks')
    return 0


# ---------------------------------------------------------------- command line

EPILOG = """suites:
{suites}

presets:
{presets}

selection: positional names are suites or presets; --only / --skip take comma-separated
glob patterns matched against step names, suite names and tags (test_cpu, run_bench,
icarus, verilator, fpu, shard, build, piece, python, writes-docs, the core name).

examples:
  python -B sim/cpu/suite.py --list
  python -B sim/cpu/suite.py release-patch --core-source build/x/cand.sv --dry-run
  python -B sim/cpu/suite.py release-patch --core-source build/x/cand.sv --expect sim/cpu/baselines/0.19.4-release-patch.json
  python -B sim/cpu/suite.py icarus-full --only 'full-pipe,full-multicycle' --jobs 2
  python -B sim/cpu/suite.py isa --core ooo,pipe --cache-sizes default,2,64 --sim icarus
  python -B sim/cpu/suite.py bench --fpu --only 'bench-js*' --devlog-row
  python -B sim/cpu/suite.py bench-smoke --n-miss 4 --l2-kib 4096 --mem-lat 350 --compare old/results.json
"""


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ['--probe-tools']:
        return probe_tools()
    if argv[:1] == ['--self-test']:
        return self_test()
    epilog = EPILOG.format(suites='\n'.join(f'  {k:<12} {v}' for k, v in M.SUITES.items()),
                           presets='\n'.join(f'  {k:<14} = {" + ".join(v)}' for k, v in M.PRESETS.items()))
    ap = argparse.ArgumentParser(prog='suite.py', description=__doc__.rsplit('SPDX', 1)[0], epilog=epilog,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('suites', nargs='*', metavar='SUITE', help='suites and presets to run (see below)')
    g = ap.add_argument_group('selection')
    g.add_argument('--list', action='store_true', help='list suites, presets and the planned steps, then exit')
    g.add_argument('--dry-run', action='store_true', help='print the exact commands in order; run nothing')
    g.add_argument('--only', type=lambda s: s.split(','), help='run only steps matching these patterns')
    g.add_argument('--skip', type=lambda s: s.split(','), help='skip steps matching these patterns')
    g = ap.add_argument_group('core and simulator')
    g.add_argument('--core', type=lambda s: s.split(','), default=['ooo'],
                   help='cores for per-core suites (isa, bitmanip): ooo, multicycle, pipe; comma-separated '
                        '(default ooo). Benchmarks, fpu, vector and negative use ooo')
    g.add_argument('--sim', choices=('verilator', 'icarus'), default='verilator',
                   help='simulator for steps without a fixed one (default verilator; icarus-full, bitmanip and '
                        'soc-memory always use Icarus, the reference). Icarus test_cpu runs are sharded')
    g.add_argument('--core-source', help='candidate core file used instead of rtl/cpu/rv64_ooo.sv by every ooo '
                   'step whose runner takes --core-source (bitmanip and the multicycle/pipe steps test rtl/cpu)')
    g.add_argument('--cache-sizes', type=lambda s: s.split(','), default=list(M.DEFAULT_CACHE_SIZES),
                   help='L1 sizes for isa/fpu/vector in 8-byte beats, "default" = tb_core default (512); '
                        'comma-separated (default default,2)')
    g = ap.add_argument_group('knobs passed through (to the runners that have them; ooo steps only for core knobs)')
    g.add_argument('--fpu', action='store_true', help='RV64F/D build (RV64_OOO_FPU); bench uses F/D images')
    g.add_argument('--vector', action='store_true', help='vector unit (needs a runner with --vector)')
    g.add_argument('--dline', type=int, help='D-cache line in beats (needs a runner with --dline)')
    for opt in ('--n-miss', '--ld-lat', '--l0', '--l0-lat'):
        g.add_argument(opt, type=int, help=f'test_cpu and run_bench {opt}')
    for opt in ('--l2-kib', '--l2-ways', '--l2-line', '--l2-lat', '--mem-lat', '--mem-gap'):
        g.add_argument(opt, type=int, help=f'run_bench {opt} (SoC memory model)')
    g.add_argument('--write-fill', type=int, choices=(0, 1), help='run_bench --write-fill')
    g.add_argument('--test-args', help='extra arguments appended to every test_cpu.py step (quoted string)')
    g.add_argument('--bench-args', help='extra arguments appended to every run_bench.py step (quoted string)')
    g = ap.add_argument_group('running')
    g.add_argument('--jobs', type=int, default=2,
                   help='steps (simulations) at once (default 2; WSL memory is shared, keep it at 2-3)')
    g.add_argument('--out-dir', help='results folder (default build/suite/<date-time>)')
    g.add_argument('--bench-root', help='benchmark build folders (default build/suite/bench); valid builds '
                   'are reused, for example --bench-root build/cpu/ooo-debug/coord/bench')
    g.add_argument('--rebuild', action='store_true', help='rebuild benchmark images even if valid')
    g.add_argument('--no-native-scratch', action='store_true',
                   help='write Linux steps\' traces and pieces straight to the repository folder (default on a '
                        'Windows drive: WSL-native ~/.cache/rv64-suite, small results copied back)')
    g = ap.add_argument_group('results')
    g.add_argument('--expect', help='results.json of an earlier run: FAIL (status DIFF) any step whose identity '
                   'metrics (programs, runs, clocks, instructions) differ')
    g.add_argument('--compare', help='like --expect but only reports the differences')
    g.add_argument('--json', action='store_true', help='print results.json to stdout at the end')
    g.add_argument('--devlog-row', action='store_true', help='print a DEVLOG.md row for this run (also written to '
                   'devlog-row.md in --out-dir)')
    g.add_argument('--who', default='suite', help='who ran it, for the DEVLOG row (default "suite")')
    args = ap.parse_args(argv)
    for c in args.core:
        if c not in ('ooo', 'multicycle', 'pipe'):
            ap.error(f'unknown core {c}')
    for c in args.cache_sizes:
        if c != 'default' and (not c.isdigit() or int(c) < 2 or int(c) & (int(c) - 1)):
            ap.error(f'cache size {c} is not "default" or a power of two >= 2')
    if args.core_source and not Path(args.core_source).is_file():
        ap.error(f'--core-source {args.core_source} does not exist')
    for name in ('core_source', 'expect', 'compare', 'out_dir', 'bench_root'):   # relative to the caller's folder
        if getattr(args, name):
            setattr(args, name, str(Path(getattr(args, name)).resolve()))
    if not 1 <= args.jobs <= 8:
        ap.error('--jobs must be 1 to 8')
    if args.list and not args.suites:
        args.suites = list(M.SUITES)
    if not args.suites:
        ap.error('name at least one suite or preset (or --list); see --help')
    steps, skipped = plan(args)
    runner = Runner(args)
    if args.list:
        print('suites:')
        for k, v in M.SUITES.items():
            print(f'  {k:<12} {v}')
        print('presets:')
        for k, v in M.PRESETS.items():
            print(f'  {k:<14} = {" + ".join(v)}')
        print(f'\nsteps for {" ".join(args.suites)} ({len(steps)}; ~{sum(s.est for s in steps) // 60} min serial):')
        for s in steps:
            print(f'  {s.name:<34} {",".join(s.suites):<22} ~{s.est:>4} s  {s.side:<5} '
                  f'{" ".join(s.tags)}' + (f'  ({s.note})' if s.note else ''))
        for s, why in skipped:
            print(f'  {s.name:<34} {",".join(s.suites):<22} {why}')
        return 0
    if args.dry_run:
        link_worktree(True, print)
        for s in steps:
            if s.name.startswith('build:'):
                build = runner.reusable(s)
                if build and not args.rebuild:
                    print(f'# {s.name}: reuse {runner.folder(s)}')
                    continue
            try:
                shown = runner.argv(s)[1]
            except RuntimeError as e:
                shown = f'ERROR {e}'
            dep = f'   # after {", ".join(s.needs)}' if s.needs else ''
            where = 'wsl: ' if s.side == 'linux' and IS_WIN else ''
            print(f'# {s.name}{dep}\n{where}{shown}')
        for s, why in skipped:
            print(f'# {s.name}: {why}')
        return 0
    if not steps:
        print('nothing to run: ' + '; '.join(f'{s.name} {why}' for s, why in skipped))
        return 3
    runner.out.mkdir(parents=True, exist_ok=True)
    try:
        link_worktree(False, print)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f'error: could not link the main worktree\'s build folders: {e}')
        return 2
    started = datetime.now().astimezone()
    print(f'[{started:%H:%M:%S}] suite.py {" ".join(args.suites)}: {len(steps)} steps, --jobs {args.jobs}, '
          f'out {Loc(runner.out).render("linux")}' + (f', core {args.core_source}' if args.core_source else ''))
    tools = tools_info(runner, any(s.side == 'linux' for s in steps))
    if runner.llvm_label != 'windows-llvm' and any(s.side == 'llvm' for s in steps):
        print('warning: no Windows LLVM; benchmark images are built with clang on PATH '
              f'({tools.get("bench_compiler")}), so clocks are not comparable to logged numbers')

    def emit(step, r):
        print(f'[{datetime.now():%H:%M:%S}] {r["status"]:<7} {step.name} ({r["seconds"]:.0f} s): {r["summary"]}',
              flush=True)

    t0 = time.time()
    results = runner.execute(steps, emit)
    results = {s.name: results[s.name] for s in steps if s.name in results}   # plan order
    notes, expect = [], args.expect or args.compare
    if expect:
        notes = compare(results, json.loads(Path(expect).read_bytes()), bool(args.expect))
    finished = datetime.now().astimezone()
    core_file = runner.core_file
    report = {'tool': 'sim/cpu/suite.py', 'selection': args.suites, 'argv': 'python -B sim/cpu/suite.py ' +
              ' '.join(shlex.quote(a) for a in (argv)), 'who': args.who,
              'started': started.isoformat(timespec='seconds'), 'finished': finished.isoformat(timespec='seconds'),
              'wall_seconds': round(time.time() - t0, 1), 'jobs': args.jobs, 'commit': commit_info(),
              'core_source': args.core_source, 'core_sha256': sha256(core_file), 'tools': tools,
              'expect': expect, 'expect_notes': notes,
              'skipped': {s.name: why for s, why in skipped}, 'steps': results,
              'results_file': Loc(runner.out / 'results.json').render('linux')}
    (runner.out / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    row = devlog_row(report)
    (runner.out / 'devlog-row.md').write_text(row + '\n', encoding='utf-8')
    print('\n' + table(steps, results))
    for s, why in skipped:
        print(f'  ({s.name}: {why})')
    bad = [n for n, r in results.items() if r['status'] not in PASSLIKE]
    print(f'\n{"SUITE FAILED" if bad else "SUITE PASSED"}: {len(results) - len(bad)} of {len(results)} steps passed'
          + (f'; failed: {", ".join(bad)}' if bad else '') + f'; results {report["results_file"]}')
    if args.devlog_row:
        print('\n' + row)
    if args.json:
        print(json.dumps(report, indent=2))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
