"""riscv-tests (p environment) on rv_iss --sys, optionally checked against Spike's commit log.

Builds each test of the listed suites from the fetched riscv-tests sources (build/third-party/riscv-tests-src,
BSD-3-Clause, never copied into the repository) with clang into build/sys/riscv-tests/, runs it on
rv_iss --sys 1 (pass: HTIF tohost = 1), and with --spike PATH also on Spike with --log-commits, comparing the
two commit logs instruction by instruction (commit_compare.py). Both models use Spike's time model here.

Usage (WSL): python3 -B sim/cpu/sys/riscv_tests.py [--suites rv64ui,rv64mi] [--spike PATH] [--only SUITE-NAME]
SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def third_party(root, name):
    """build/third-party/<name> of this checkout, or of an enclosing one (a worktree kept under build/)."""
    for d in (root, *root.parents):
        if (d / 'build/third-party' / name).is_dir():
            return d / 'build/third-party' / name
    return root / 'build/third-party' / name


SRC = third_party(ROOT, 'riscv-tests-src')
LINUX_LAB = third_party(ROOT, 'linux-lab')
OUT = ROOT / 'build/sys/riscv-tests'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import commit_compare  # noqa: E402

SUITES = ['rv64ui', 'rv64um', 'rv64ua', 'rv64uf', 'rv64ud', 'rv64uc', 'rv64mi', 'rv64si']
SPIKE_ISA = 'rv64imafdc_zicsr_zifencei_zicntr'
# Tests that need what the lab-virt contract leaves out (cpu/PRIV-CONTRACT.md): misaligned data in hardware
# (ma_data; the p environment has no M-mode emulation) and PMP entries (pmpaddr; the platform has 0).
# Each with its exact HTIF exit value: ma_data fails its test 668 ((668 << 1) | 1 = 1337), pmpaddr its test 1.
EXPECTED_FAIL = {'rv64ui-ma_data': 1337, 'rv64mi-pmpaddr': 3}
# Known commit-log differences from Spike, by contract choice (cpu/PRIV-CONTRACT.md section 9): the exact
# first differing record (index, Spike's x-register write, rv_iss's) that is excused, and nothing else.
KNOWN_SPIKE_DIFF = {'rv64mi-ma_fetch': (113, (('x7', 0x8000000000141129),), (('x7', 0x800000000014112d),),
                                        'Spike lets software clear misa.C; the contract makes misa read-only')}


def suite_tests(suite):
    """Test names from the suite's Makefrag (the <suite>_sc_tests list)."""
    names, grab = [], False
    for line in (SRC / 'riscv-tests/isa' / suite / 'Makefrag').read_text().splitlines():
        if line.startswith(f'{suite}_sc_tests'):
            grab = True
            continue
        if grab:
            word = line.strip().rstrip('\\').strip()
            names += word.split()
            if not line.rstrip().endswith('\\'):
                break
    return names


def build_iss():
    src = ROOT / 'sim/cpu/bench/rv_iss.c'
    exe = ROOT / f'build/sys/rv_iss-{hashlib.sha256(src.read_bytes()).hexdigest()[:16]}'
    if not exe.is_file():
        exe.parent.mkdir(parents=True, exist_ok=True)
        tmp = exe.with_name(f'{exe.name}.{os.getpid()}.tmp')     # concurrent cold starts each build their own
        subprocess.run(['clang', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', str(tmp), str(src)],
                       check=True, timeout=300)
        tmp.replace(exe)
    return exe


def build_test(suite, name):
    elf = OUT / f'{suite}-p-{name}.elf'
    source = SRC / 'riscv-tests/isa' / suite / f'{name}.S'
    if elf.is_file() and elf.stat().st_mtime > source.stat().st_mtime:
        return elf
    OUT.mkdir(parents=True, exist_ok=True)
    march = 'rv64gc' if suite == 'rv64uc' else 'rv64g'
    env = SRC / 'riscv-test-env'
    base = ['clang', '--target=riscv64-unknown-elf', f'-march={march}', '-mabi=lp64', '-mcmodel=medany']
    pre = subprocess.run(base + ['-E', '-P', f'-I{env}/p', f'-I{env}', f'-I{SRC}/riscv-tests/isa/macros/scalar',
                                 str(source)], check=True, timeout=300, capture_output=True, text=True).stdout
    # LLVM's assembler rejects `.weak X` followed by `.global X` (GNU as accepts it): the p environment
    # declares the optional handlers weak and some tests then define them globally. Drop the weak
    # declaration of a handler the test defines; the sources themselves are not changed.
    for handler in re.findall(r'\.glob(?:a)?l\s+(\w+_handler)', pre):
        pre = re.sub(r'\.weak\s+' + handler + r'\b', '', pre)
    pre = re.sub(r"(?<![A-Za-z0-9_])tcontrol(?![A-Za-z0-9_])", "0x7a5", pre)   # a CSR name LLVM 18 does not know
    asm = OUT / f'{suite}-p-{name}.s'
    asm.write_text(pre)
    cmd = base + ['-static', '-nostdlib', '-fuse-ld=lld', '-mno-relax', f'-T{env}/p/link.ld', str(asm), '-o', str(elf)]
    subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)
    return elf


def run_iss(exe, elf, clog=None, max_insns=2_000_000):
    cmd = [str(exe), '--sys', '1', '--ram', str(16 << 20), '--elf', str(elf), '--max', str(max_insns),
           '--marchid', '5', '--time', 'spike']
    if clog:
        cmd += ['--commit-log', str(clog)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


def run_spike(spike, elf, clog, max_insns=2_000_000):
    cmd = [spike, f'--isa={SPIKE_ISA}', '--priv=msu', '--pmpregions=0', '--triggers=0', '-m16',
           f'--instructions={max_insns}', '--log-commits', f'--log={clog}', str(elf)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suites', default=','.join(SUITES))
    ap.add_argument('--spike', help="Spike binary, or 'auto' for build/third-party/linux-lab/build/spike/spike")
    ap.add_argument('--only')
    args = ap.parse_args()
    exe = build_iss()
    if args.spike == 'auto':
        args.spike = str(LINUX_LAB / 'build/spike/spike')
    total = fails = mism = 0
    results = {}
    for suite in args.suites.split(','):
        for name in suite_tests(suite):
            key = f'{suite}-{name}'
            if args.only and args.only != key:
                continue
            total += 1
            try:
                elf = build_test(suite, name)
            except subprocess.CalledProcessError as e:
                results[key] = {'build_error': e.stderr[-400:]}
                fails += 1
                print(f'BUILD-FAIL {key}: {e.stderr[-300:]}')
                continue
            clog = OUT / f'{suite}-p-{name}.iss.log' if args.spike else None
            res = run_iss(exe, elf, clog)
            ok = res['stop'] == 'tohost' and res['exit_code'] == 1
            entry = {'iss': 'pass' if ok else f"fail {res['stop']} code {res['exit_code']} pc {res['pc']:#x}",
                     'instructions': res['instructions']}
            if args.spike:
                slog = OUT / f'{suite}-p-{name}.spike.log'
                entry['spike_rc'] = run_spike(args.spike, elf, slog)
                cmp = commit_compare.compare(slog, clog, iss_prefix=True)
                entry['compare'] = cmp['summary']
                known = KNOWN_SPIKE_DIFF.get(key)
                d = cmp.get('records')
                if not cmp['match']:
                    entry['first_difference'] = cmp['first_difference']
                    if known and d and cmp['compared'] == known[0] and d[0][3] == known[1] and d[1][3] == known[2] \
                            and d[0][:3] == d[1][:3]:
                        entry['known_spike_difference'] = known[3]
                    else:
                        mism += 1
                elif cmp['compared'] != res['instructions']:
                    # rv_iss's whole log must have been compared (it logs every retired instruction)
                    entry['compare'] += f"; but rv_iss retired {res['instructions']}"
                    mism += 1
                elif known:
                    entry['compare'] += '; the known difference did not occur'
                    mism += 1
            if not ok and res['stop'] == 'tohost' and res['exit_code'] == EXPECTED_FAIL.get(key):
                entry['expected_failure'] = True
            else:
                fails += not ok or key in EXPECTED_FAIL
            results[key] = entry
            print(f"{'PASS' if ok else 'FAIL'} {key} {json.dumps(entry)}", flush=True)
    print(json.dumps({'tests': total, 'iss_failures': fails, 'spike_mismatches': mism,
                      'expected_failures': sorted(k for k, e in results.items() if e.get('expected_failure'))}))
    if not fails and not mism:
        print(f'PASS: {total - len([e for e in results.values() if e.get("expected_failure")])} riscv-tests pass on '
              f'rv_iss --sys' + (' and match Spike' if args.spike else ''))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ('summary-spike.json' if args.spike else 'summary.json')).write_text(json.dumps(results, indent=1))
    return 1 if fails or mism else 0


if __name__ == '__main__':
    sys.exit(main())
