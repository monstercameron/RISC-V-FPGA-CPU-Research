#!/usr/bin/env python3
"""Run the official riscv-tests ISA tests on the golden models and the RTL cores.

The test sources come from riscv-software-src/riscv-tests at a pinned commit, fetched by
sim/cpu/fetch_riscv_tests.sh into the ignored build/third-party/riscv-tests-src and checked
against sim/cpu/riscv_tests/riscv-tests.lock before every build. They are assembled with
the project's MIT lab environment (env/riscv_test.h, env/link.ld; no CSRs, 16 KiB RAM at 0)
instead of riscv-test-env's M-mode `p` environment.

Each test runs on reference.py (the golden model), on rv_iss.c, and with --core on one RTL
core through tb_core.sv at each --stalls pattern. A test passes when the golden model ends
with the lab environment's PASS (ECALL with a0 = 0 and gp = 1) and every other trace,
stores and trap record included, is identical to the golden trace. With the F and D suites
the final fcsr of the RTL must also equal the golden model's.

Tests listed in EXPECTED_TRAPS must instead end with that trap cause in the golden model
(with all traces identical). They are reported as expected traps, never counted as passes,
and a listed test that passes is an error, so the list is updated when the contract changes.

Usage (WSL or Linux; clang with the RISC-V target and ld.lld, llvm-objcopy):
  python3 -B sim/cpu/riscv_tests/run_riscv_tests.py rv64ui rv64um              # golden models only
  python3 -B sim/cpu/riscv_tests/run_riscv_tests.py --core ooo --sim verilator --stalls 0,7 rv64ui
  python3 -B sim/cpu/riscv_tests/run_riscv_tests.py --core ooo --sim verilator rv64uf rv64ud   # F/D option
  python3 -B sim/cpu/riscv_tests/run_riscv_tests.py --self-test --core pipe --sim icarus
Last line: "PASS: N riscv-tests (...)" or "FAIL: ...". Results go to --out-dir/results.json.
SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'sim/cpu'))
import reference   # noqa: E402  the golden model
import simulator   # noqa: E402  Icarus and Verilator back ends

SRC = Path(os.environ.get('RISCV_TESTS_DIR') or ROOT / 'build/third-party/riscv-tests-src')
TESTS = SRC / 'riscv-tests'
ENV = HERE / 'env'
LOCK = HERE / 'riscv-tests.lock'
COMMIT = '3df703cd52d5f0d8224e3c50bf03c6cb70efff98'
RAM = 16384
MARCH = {'rv64ui': 'rv64i', 'rv64um': 'rv64im', 'rv64uzba': 'rv64i_zba', 'rv64uzbb': 'rv64i_zbb',
         'rv64uzbs': 'rv64i_zbs', 'rv64uf': 'rv64imfd', 'rv64ud': 'rv64imfd'}
FP_SUITES = ('rv64uf', 'rv64ud')
CORES = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}
SEEDS = {0: 1, 7: 42, 19: 103}          # test_cpu.py's wait-pattern seeds
# Tests whose golden run must end in a trap under the current contract, with the reason.
EXPECTED_TRAPS = {
    ('rv64ui', 'ma_data'): (4, 'misaligned loads and stores trap (architecture section 1, Data alignment; '
                               'the RVA23 Zicclsm item, C3/C6)'),
}


def run(args, timeout=120):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} rc={r.returncode}: {(r.stdout + r.stderr).strip()[-400:]}')
    return r.stdout


def check_lock():
    """Every locked file must exist with its recorded SHA-256 (refuse to build otherwise)."""
    if not TESTS.is_dir():
        raise SystemExit(f'error: {TESTS} is missing; run sim/cpu/fetch_riscv_tests.sh first')
    entries = {}
    for line in LOCK.read_text(encoding='ascii').splitlines():
        if line and not line.startswith('#'):
            digest, name = line.split(maxsplit=1)
            entries[name.lstrip('*')] = digest
    bad = [n for n, d in entries.items() if not (SRC / n).is_file() or
           hashlib.sha256((SRC / n).read_bytes()).hexdigest() != d]
    if bad:
        raise SystemExit(f'error: {len(bad)} riscv-tests files differ from {LOCK.name}, e.g. {bad[:3]}; '
                         'refetch with sim/cpu/fetch_riscv_tests.sh (never regenerate the lock to silence this)')
    return entries


def tests_of(suite):
    frag = (TESTS / 'isa' / suite / 'Makefrag').read_text(encoding='utf-8')
    m = re.search(rf'^{suite}_sc_tests\s*=\s*\\\n(.*?)\n\s*\n', frag, re.S | re.M)
    if not m:
        raise SystemExit(f'error: no {suite}_sc_tests list in {suite}/Makefrag')
    return m[1].replace('\\', ' ').split()


def tool_version(cmd):
    try:
        return run([*cmd, '--version']).splitlines()[0].strip()
    except (OSError, RuntimeError):
        return None


def build(src, march, fp, out, tag, clang, objcopy):
    """Assemble and link one test with the lab environment; returns the 16 KiB image."""
    elf, binf = out / f'{tag}.elf', out / f'{tag}.bin'
    run([clang, '--target=riscv64-unknown-elf', f'-march={march}', '-mabi=' + ('lp64d' if fp else 'lp64'),
         '-mcmodel=medany', '-mno-relax', '-nostdlib', '-static', '-fuse-ld=lld', f'-I{ENV}',
         f'-I{TESTS}/isa/macros/scalar', f'-T{ENV}/link.ld', '-o', elf, src])
    run([objcopy, '-O', 'binary', elf, binf])
    data = binf.read_bytes()
    if len(data) > RAM:
        raise RuntimeError(f'image of {len(data)} bytes exceeds the {RAM}-byte lab RAM')
    return data.ljust(RAM, b'\0')


def verdict(trace, final):
    """The golden model's outcome: PASS, FAIL(test n), TRAP(cause c, ...) or NO-HALT."""
    last = trace[-1].split() if trace else []
    if not last or last[0] != 'T':
        return 'NO-HALT'
    cause = int(last[2], 16)
    if cause == 11 and final['x'][10] == 0 and final['x'][3] == 1:
        return 'PASS'
    if cause == 3 and final['x'][3] & 1:
        return f'FAIL(test {final["x"][3] >> 1})'
    return f'TRAP(cause {cause}, pc {int(last[1], 16):#x}, tval {int(last[3], 16):#x})'


def classify(suite, name, golden):
    """(result, note) from the golden verdict and the expected-trap list."""
    want = EXPECTED_TRAPS.get((suite, name))
    if want is None:
        return ('PASS', '') if golden == 'PASS' else ('FAIL', golden)
    if golden.startswith(f'TRAP(cause {want[0]},'):
        return 'XTRAP', f'{golden}: expected, {want[1]}'
    if golden == 'PASS':
        return 'FAIL', f'listed as an expected cause-{want[0]} trap but passed: update EXPECTED_TRAPS'
    return 'FAIL', f'{golden}, expected cause {want[0]}'


def first_diff(actual, expected):
    for i in range(max(len(actual), len(expected))):
        a = actual[i] if i < len(actual) else '<missing>'
        e = expected[i] if i < len(expected) else '<missing>'
        if a != e:
            return f'event {i}: actual {a} expect {e}'
    return None


class Models:
    """rv_iss and (optionally) one RTL core, built once per invocation."""

    def __init__(self, a, out, fp):
        self.a, self.out, self.fp = a, out, fp
        cc = a.cc or next((c for c in ('clang', 'gcc', 'cc') if shutil.which(c)), None)
        if not cc:
            raise SystemExit('error: rv_iss.c needs a C compiler (clang, gcc or cc)')
        self.iss = out / 'rv_iss'
        run([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', self.iss, ROOT / 'sim/cpu/bench/rv_iss.c'])
        self.cc = tool_version([cc])
        self.exe = None
        if a.core:
            core = Path(a.core_source).resolve() if a.core_source else ROOT / CORES[a.core]
            if fp and a.core != 'ooo':
                raise SystemExit('error: rv64uf/rv64ud need --core ooo (the F and D option exists only there)')
            if fp and 'RV64_OOO_FPU' not in core.read_text(encoding='utf-8'):
                raise SystemExit(f'error: {core.name} has no RV64_OOO_FPU option')
            sim = simulator.get(a.sim)
            params = {k: v for k, v in (('ICACHE_BEATS', a.icache_beats), ('DCACHE_BEATS', a.dcache_beats)) if v}
            defines = (['WIDE_TRACE'] if a.core == 'ooo' else []) + (['RV64_OOO_FPU'] if fp else [])
            self.exe = sim.build('tb_core', [core, ROOT / 'sim/cpu/tb_core.sv'], out / f'cpu-{a.core}.vvp',
                                 params=params, defines=defines, timeout=simulator.STEP_TIMEOUT)
            self.core_file = core
            self.sim = sim

    def run_all(self, tag, image, gold, final):
        """{model: 'MATCH' or 'DIFF ...'} for rv_iss and each RTL wait pattern."""
        got = {}
        img = self.out / f'{tag}.img'
        img.write_bytes(image)
        trc = self.out / f'{tag}.iss.trace'
        run([self.iss, '--ram', RAM, '--image', img, '--trace', trc, '--max', 2_000_000] + (['--fp', 1] if self.fp else []))
        d = first_diff(trc.read_text().splitlines(), gold)
        got['rv_iss'] = 'MATCH' if d is None else f'DIFF {d}'
        if self.exe:
            hexf = self.out / f'{tag}.hex'
            hexf.write_text(''.join(f'{b:02x}\n' for b in image), encoding='ascii')
            for stall in self.a.stalls:
                rtrc = self.out / f'{tag}.{self.a.core}-stall{stall}.trace'
                output = run([*self.exe, f'+image={hexf}', f'+trace={rtrc}', f'+stall={stall}',
                              f'+seed={SEEDS.get(stall, 7)}', '+fault_kind=0', '+fault_addr=ffffffffffffffff'])
                d = first_diff(rtrc.read_text().splitlines(), gold)
                if d is None and self.fp:
                    m = re.search(r'fcsr=([0-9a-f]{2})', output)
                    if not m or int(m[1], 16) != final['fcsr']:
                        d = f'final fcsr {m[1] if m else None}, expect {final["fcsr"]:02x}'
                got[f'{self.a.core}-stall{stall}'] = 'MATCH' if d is None else f'DIFF {d}'
        return got


def run_test(models, suite, name, src, out, a, tag=None):
    tag = tag or f'{suite}-{name}'
    rec = {'suite': suite, 'test': name}
    try:
        image = build(src, MARCH[suite], suite in FP_SUITES, out, tag, a.clang, a.objcopy)
        final = {}
        gold, _ = reference.execute(image, max_steps=500_000, fp=suite in FP_SUITES, state=final)
        rec['golden'] = verdict(gold, final)
        rec['events'] = len(gold)
        rec['models'] = models.run_all(tag, image, gold, final)
        rec['result'], rec['note'] = classify(suite, name, rec['golden'])
        diffs = {k: v for k, v in rec['models'].items() if v != 'MATCH'}
        if diffs:
            rec['result'], rec['note'] = 'FAIL', '; '.join(f'{k}: {v}' for k, v in diffs.items())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        rec['result'], rec['note'] = 'FAIL', f'error: {e}'
    return rec


def self_test(a, out):
    """Negative controls: the harness must report failures it is meant to catch. out: scratch folder."""
    checks = []
    t = ['R 0000000000000000 00000193 03 0000000000000000 0000000000000004',
         'T 0000000000000004 000000000000000b 0000000000000000']
    ok_final = {'x': [0] * 3 + [1] + [0] * 28}
    checks.append(('pass verdict', verdict(t, ok_final) == 'PASS'))
    checks.append(('a0 != 0 at ecall is not a pass', verdict(t, {'x': [0] * 3 + [1] + [0] * 6 + [5] + [0] * 21}) != 'PASS'))
    checks.append(('missing trap is NO-HALT', verdict(t[:1], ok_final) == 'NO-HALT'))
    checks.append(('unexpected trap fails', classify('rv64ui', 'add', 'TRAP(cause 2, pc 0x10, tval 0x0)')[0] == 'FAIL'))
    checks.append(('expected trap is not a pass', classify('rv64ui', 'ma_data', 'TRAP(cause 4, pc 0x18, tval 0x1)')[0] == 'XTRAP'))
    checks.append(('expected trap that passes fails', classify('rv64ui', 'ma_data', 'PASS')[0] == 'FAIL'))
    checks.append(('wrong expected cause fails', classify('rv64ui', 'ma_data', 'TRAP(cause 6, pc 0x18, tval 0x1)')[0] == 'FAIL'))
    checks.append(('trace difference found', first_diff(t, [t[0], t[1].replace('0b', '03')]) is not None))
    checks.append(('short trace found', first_diff(t[:1], t) is not None))
    # A mutated copy of add.S (test 3 expects 3 instead of 2) must fail as test 3 on every model,
    # with identical traces: the FAIL path of the environment, end to end.
    text = (TESTS / 'isa/rv64ui/add.S').read_text(encoding='utf-8')
    anchor = 'TEST_RR_OP( 3,  add, 0x00000002, 0x00000001, 0x00000001 );'
    checks.append(('mutation anchor unique', text.count(anchor) == 1))
    mutant = out / 'add_mutant.S'
    mutant.write_text(text.replace(anchor, anchor.replace('0x00000002', '0x00000003', 1)), encoding='utf-8')
    models = Models(a, out, fp=False)
    rec = run_test(models, 'rv64ui', 'add_mutant', mutant, out, a)
    checks.append(('mutated add fails as test 3', rec.get('golden') == 'FAIL(test 3)' and rec['result'] == 'FAIL'))
    checks.append(('mutated add: all models agree', bool(rec.get('models')) and
                   all(v == 'MATCH' for v in rec['models'].values())))
    print(json.dumps(rec))
    failed = [n for n, ok in checks if not ok]
    if failed:
        print(f'FAIL: riscv-tests self-test: {failed}')
        return 1
    print(f'PASS: riscv-tests self-test, {len(checks)} checks (models: {", ".join(rec["models"])})')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('suites', nargs='*', metavar='SUITE', help=f'riscv-tests directories: {", ".join(MARCH)}')
    p.add_argument('--only', help='comma-separated test names to keep')
    p.add_argument('--core', choices=sorted(CORES), help='also run this RTL core (default: golden models only)')
    p.add_argument('--core-source', help='candidate core file instead of the rtl/cpu one')
    p.add_argument('--sim', choices=simulator.CHOICES, default='icarus')
    p.add_argument('--stalls', default='0', help='comma-separated tb_core wait patterns (default 0)')
    p.add_argument('--icache-beats', type=int)
    p.add_argument('--dcache-beats', type=int)
    p.add_argument('--clang', default='clang')
    p.add_argument('--objcopy', default='llvm-objcopy')
    p.add_argument('--cc', help='C compiler for rv_iss.c (default: clang, gcc or cc)')
    p.add_argument('--out-dir', type=Path, default=ROOT / 'build/riscv-tests')
    p.add_argument('--self-test', action='store_true', help='run the harness negative controls')
    a = p.parse_args()
    a.stalls = [int(s) for s in a.stalls.split(',')]
    if a.core_source and not a.core:
        p.error('--core-source needs --core')
    if not a.suites and not a.self_test:
        p.error('name at least one suite, or --self-test')
    for s in a.suites:
        if s not in MARCH:
            p.error(f'unknown suite {s}')
    out = a.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    locked = check_lock()
    # Scratch files (ELFs, images, traces, the simulator build) go to a Linux temporary folder: on a
    # Windows drive mounted in WSL the many small files dominated the run time. Failing tests are copied
    # to --out-dir/failed/, so the evidence for a failure is kept.
    work = Path(tempfile.mkdtemp(prefix='riscv-tests-'))
    try:
        if a.self_test:
            return self_test(a, work)
        return run_suites(a, p, out, work, locked)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_suites(a, p, out, work, locked):
    fp = any(s in FP_SUITES for s in a.suites)
    if fp and not all(s in FP_SUITES for s in a.suites) and a.core and a.core != 'ooo':
        p.error('rv64uf/rv64ud need --core ooo; run them as a separate invocation')
    t0 = time.time()
    models = Models(a, work, fp)
    only = set(a.only.split(',')) if a.only else None
    results = []
    for suite in a.suites:
        for name in tests_of(suite):
            if only and name not in only:
                continue
            rec = run_test(models, suite, name, TESTS / 'isa' / suite / f'{name}.S', work, a)
            if rec['result'] == 'FAIL':
                (out / 'failed').mkdir(exist_ok=True)
                for f in work.glob(f'{suite}-{name}.*'):
                    shutil.copy2(f, out / 'failed' / f.name)
            rec['source_sha256'] = locked.get(f'riscv-tests/isa/{suite}/{name}.S')
            results.append(rec)
            label = {'PASS': 'ok', 'XTRAP': 'xtrap', 'FAIL': 'FAIL'}[rec['result']]
            print(f'{label:5} {suite}/{name}' + (f': {rec["note"]}' if rec['note'] else ''), flush=True)
    passed = sum(r['result'] == 'PASS' for r in results)
    xtrap = [f'{r["suite"]}/{r["test"]}' for r in results if r['result'] == 'XTRAP']
    failed = [r for r in results if r['result'] == 'FAIL']
    summary = {
        'riscv_tests_commit': COMMIT, 'suites': a.suites, 'core': a.core,
        'core_source': str(models.core_file) if a.core else None,
        'core_sha256': hashlib.sha256(models.core_file.read_bytes()).hexdigest() if a.core else None,
        'sim': a.sim if a.core else None, 'sim_version': models.sim.version() if a.core else None,
        'stalls': a.stalls if a.core else [], 'icache_beats': a.icache_beats, 'dcache_beats': a.dcache_beats,
        'clang': tool_version([a.clang]), 'rv_iss_cc': models.cc,
        'sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in
                   ('sim/cpu/reference.py', 'sim/cpu/bench/rv_iss.c', 'sim/cpu/tb_core.sv',
                    'sim/cpu/riscv_tests/env/riscv_test.h', 'sim/cpu/riscv_tests/env/link.ld',
                    'sim/cpu/riscv_tests/run_riscv_tests.py', 'sim/cpu/riscv_tests/riscv-tests.lock')},
        'passed': passed, 'expected_traps': xtrap, 'failed': len(failed), 'total': len(results),
        'seconds': round(time.time() - t0, 1), 'results': results}
    (out / 'results.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    where = f'{a.core} {a.sim} stalls {",".join(map(str, a.stalls))}' if a.core else 'golden models only'
    if failed or not results:
        print(f'FAIL: {len(failed)} of {len(results)} riscv-tests failed ({where})')
        return 1
    print(f'PASS: {passed} riscv-tests ({where}; {len(xtrap)} expected traps: {", ".join(xtrap) or "none"}; '
          f'reference.py and rv_iss traces identical; {summary["seconds"]} s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
