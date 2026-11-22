# SPDX-License-Identifier: MIT
"""Check repository conventions and run existing planning checks in isolation.

Python 3.11+, standard library only. No network, downloads or hardware tools.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_DOCS = (
    'README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md', 'AGENTS.md',
    'THIRD_PARTY_NOTICES.md', 'licenses/README.md', 'rtl/README.md',
    'fpga/README.md', 'llm-accelerator/planning-evidence/README.md',
    'llm-accelerator/plan/llm-rva23-mapping.md', 'isa/README.md',
    'cpu/README.md', 'cpu/architecture.md', 'cpu/c-demo.md', 'cpu/visualizer.md', 'cpu/addition.md', 'cpu/programs.md', 'cpu/inputs.md',
    'cpu/review-rubric.md', 'cpu/TODO.md', 'cpu/dhrystone.md', 'DEVLOG.md', 'cpu/lzma-benchmark.md', 'cpu/raytracing-benchmark-targets.md',
    'cpu/js-benchmark-targets.md', 'cpu/mm-benchmark-targets.md', 'cpu/7zip-benchmark-targets.md',
    'cpu/ternary-benchmark-targets.md', 'sim/cpu/README.md', 'cpu/research/README.md',
)
REQUIRED = MAINTAINED_DOCS + (
    'LICENSE', '.gitignore', '.gitattributes', '.editorconfig',
    '.github/workflows/checks.yml', '.github/dependabot.yml',
    '.github/PULL_REQUEST_TEMPLATE.md', '.github/ISSUE_TEMPLATE/config.yml',
    '.github/ISSUE_TEMPLATE/bug_report.yml',
    '.github/ISSUE_TEMPLATE/research_proposal.yml', 'licenses/provenance.json',
    'isa/scalar_ops.S', 'isa/rvv_ops.S', 'isa/bf16_optional.S',
    'isa/transport.S', 'isa/opcode_examples.S', 'isa/verify_assembly.py',
    'cpu/core-explainer.html', 'cpu/verification.json',
    'rtl/cpu/rv64_core.sv', 'rtl/cpu/rv64_bram_soc.sv',
    'sim/cpu/test_cpu.py', 'sim/cpu/simulator.py', 'sim/cpu/reference.py', 'sim/cpu/tb_core.sv',
    'sim/cpu/tb_reset.sv', 'sim/cpu/tb_soc.sv', 'sim/cpu/run.sh', 'sim/cpu/run.ps1',
    'sim/cpu/build_firmware.py', 'sim/cpu/firmware.c', 'sim/cpu/start.S', 'sim/cpu/link.ld',
    'sim/cpu/c_demo.c', 'sim/cpu/tb_c_demo.sv', 'sim/cpu/run_c_demo.py',
    'sim/cpu/run_c_demo.ps1', 'cpu/c-demo-results.json',
    'sim/cpu/tb_visualizer.sv', 'sim/cpu/build_visualizer.py', 'sim/cpu/serve_visualizer.py',
    'sim/cpu/run_visualizer.ps1', 'cpu/visualizer.template.html', 'cpu/visualizer-verification.json',
    'sim/cpu/add_one.c', 'cpu/addition-verification.json',
    'sim/cpu/program_catalog.py', 'sim/cpu/program_inputs.py', 'sim/cpu/test_program_inputs.py', 'sim/cpu/build_programs.py', 'cpu/programs-verification.json',
    'sim/cpu/programs/decisions.c', 'sim/cpu/programs/counting.c', 'sim/cpu/programs/arrays.c',
    'sim/cpu/programs/calls.c', 'sim/cpu/programs/sorting.c',
    'sim/cpu/bench/build_bench.py', 'sim/cpu/bench/run_bench.py', 'sim/cpu/bench/tb_bench.sv',
    'sim/cpu/bench/run_dhrystone.ps1', 'sim/cpu/bench/start.S', 'sim/cpu/bench/runtime.c',
    'sim/cpu/bench/dhrystone_port.c', 'sim/cpu/bench/include/bench.h', 'sim/cpu/bench/include/util.h',
    'sim/cpu/bench/include/stdio.h', 'sim/cpu/bench/include/string.h', 'sim/cpu/bench/include/alloca.h',
    'sim/cpu/bench/vendor/dhrystone/SOURCE.txt', 'cpu/dhrystone-results.json',
    'sim/cpu/bench/rubric_score.py', 'cpu/rubric-evidence.json', 'cpu/VERSION',
    'sim/cpu/bench/bench_profile.py', 'sim/cpu/bench/runlog.py',
    'cpu/dhrystone-rv64im-results.json',
    'sim/cpu/bench/lzma_bench.c', 'sim/cpu/bench/lzma_bench_data.c', 'sim/cpu/bench/lzma_runtime.c',
    'sim/cpu/bench/lzma_native.c', 'sim/cpu/bench/lzma_run.py', 'sim/cpu/bench/lzma_rating.py',
    'sim/cpu/bench/bench_checkpoint.py', 'sim/cpu/bench/include-lzma/lzma_bench.h',
    'sim/cpu/bench/include-lzma/string.h', 'sim/cpu/bench/include-lzma/errno.h',
    'sim/cpu/bench/vendor/lzma/SOURCE.txt',
    'sim/cpu/bench/js_run.py', 'sim/cpu/bench/js/kernels.js', 'sim/cpu/bench/js/js_bench.c',
    'sim/cpu/bench/js/libc.c', 'sim/cpu/bench/js/gen_src.py', 'sim/cpu/bench/js/js_native.sh',
    'sim/cpu/bench/js/js_laptop.py', 'sim/cpu/bench/js/fetch_quickjs.sh', 'licenses/QUICKJS-NG-LICENSE.txt',
    'sim/cpu/fp_oracle.py', 'sim/cpu/fetch_softfloat.sh', 'sim/cpu/bench/fp_oracle_iss.c',
    'sim/cpu/bench/mm_run.py', 'sim/cpu/bench/mm_build.py', 'sim/cpu/bench/mm/mm_bench.h', 'sim/cpu/bench/mm/mm_bench.c',
    'sim/cpu/bench/mm/mm_kernels.c', 'sim/cpu/bench/mm/mm_runtime.c', 'sim/cpu/bench/mm/mm_native.c',
    'sim/cpu/bench/mm/mm_gen.c', 'sim/cpu/bench/mm/mm_export.sh', 'sim/cpu/bench/mm/mm_laptop.c',
    'sim/cpu/bench/mm/mm_laptop.sh', 'sim/cpu/bench/mm/mm_laptop_summary.py',
    'sim/cpu/suite.py', 'sim/cpu/suite_manifest.py', 'sim/cpu/baselines/0.17.2-release-patch.json',
    'sim/cpu/fetch_riscv_tests.sh', 'sim/cpu/riscv_tests/run_riscv_tests.py', 'sim/cpu/riscv_tests/riscv-tests.lock',
    'sim/cpu/riscv_tests/env/riscv_test.h', 'sim/cpu/riscv_tests/env/link.ld',
    'cpu/research/performance-targets.md', 'cpu/research/standards.md', 'cpu/research/isa-roadmap.md',
    'cpu/research/test-suite-inventory.md', 'cpu/research/rv64gc-linux.md', 'cpu/research/cpu-catalog.md',
    'cpu/research/bitnet-ternary.md', 'cpu/research/riscv-matrix.md', 'cpu/research/js-engines.md',
    'cpu/research/fp-contract-draft-0.17.0.md', 'llm-accelerator/plan/README.md',
)
PLANNING_INPUTS = (
    'memory_model.py', 'plan_audit_checks.py', 'refinement_checks.py', 'abi_v1.py',
    'reference-source-lock.json', 'qualification-fixtures.json',
    'abi-v1.md', 'adapter-v1.md', 'implementation-contract.md',
)
# The accelerator planning files live together in this folder (moved from the
# repository root on 2026-11-22, bytes unchanged). The checkers read their
# siblings and reference-sources/ by relative name, so check_planning() lays the
# inputs out flat in a scratch directory exactly as before.
PLANNING_DIR = 'llm-accelerator/plan'
# DEVLOG.md is append-only, so its old links keep the pre-2026-11-22 root paths.
# They are accepted for DEVLOG.md only, and only while the moved file exists.
MOVED_FROM_ROOT = {'TODO.md': 'cpu/TODO.md'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_metadata() -> dict:
    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file() or not path.read_bytes():
            raise ValueError(f'Missing or empty repository file: {name}')
        data = path.read_bytes()
        data.decode('utf-8')
        if not data.endswith(b'\n') or b'\r\n' in data:
            raise ValueError(f'Maintained file must use LF and a final newline: {name}')

    checked_links = 0
    for name in MAINTAINED_DOCS:
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = target.strip('<>')
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#', 1)[0])
            if not (path.parent / target).exists() and not (
                    name == 'DEVLOG.md' and (ROOT / MOVED_FROM_ROOT.get(target, '')).is_file()):
                raise ValueError(f'Broken local link in {name}: {target}')
            checked_links += 1

    manifest = json.loads((ROOT / 'licenses/provenance.json').read_bytes())
    for entry in manifest['files']:
        path = (ROOT / entry['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError(f'Invalid license path: {entry["path"]}')
        if sha(path) != entry['sha256']:
            raise ValueError(f'Upstream license bytes changed: {entry["path"]}')

    version = (ROOT / 'cpu/VERSION').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('cpu/VERSION must be a semantic version MAJOR.MINOR.PATCH')
    architecture = (ROOT / 'cpu/architecture.md').read_text(encoding='utf-8')
    if architecture.splitlines()[0] != f'# CPU architecture, version {version}':
        raise ValueError('cpu/architecture.md title must state the version in cpu/VERSION')
    if f'\n| {version} |' not in architecture:
        raise ValueError('cpu/architecture.md version history lacks a row for the current version')

    workflow = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    actions = re.findall(r'uses:\s+([^\s@]+)@([^\s#]+)', workflow)
    if not actions or any(not re.fullmatch(r'[0-9a-f]{40}', ref) for _, ref in actions):
        raise ValueError('Every external CI action must be pinned to a full commit SHA')
    return {'local_links_checked': checked_links, 'license_identities_checked': len(manifest['files']),
            'pinned_action_uses': len(actions), 'cpu_architecture_version': version}


def check_planning(report_dir: Path) -> dict:
    # Existing refinement checks emit a lifecycle fixture beside their script.
    # Run them on a disposable copy to avoid rewriting reviewed repository files.
    watched = [ROOT / PLANNING_DIR / name for name in PLANNING_INPUTS]
    watched += [p for p in (ROOT / 'reference-sources').iterdir() if p.is_file()]
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in watched}
    with tempfile.TemporaryDirectory(prefix='fpga-repository-check-') as temporary:
        scratch = Path(temporary)
        for name in PLANNING_INPUTS:
            shutil.copy2(ROOT / PLANNING_DIR / name, scratch / name)
        shutil.copytree(ROOT / 'reference-sources', scratch / 'reference-sources')
        for script, result in (
            ('plan_audit_checks.py', 'plan-audit-checks.json'),
            ('refinement_checks.py', 'refinement-checks.json'),
        ):
            completed = subprocess.run(
                [sys.executable, '-B', str(scratch / script), '--out', str(scratch / result)],
                cwd=scratch, text=True, encoding='utf-8', errors='replace',
                capture_output=True, timeout=180, check=False,
            )
            if completed.returncode:
                raise RuntimeError(f'{script} failed:\n{completed.stdout}\n{completed.stderr}')
            # Parse before copying so a malformed/empty result cannot appear successful.
            json.loads((scratch / result).read_bytes())
            shutil.copy2(scratch / result, report_dir / result)
            print(f'PASS {script}')
        # JSON writers use platform line endings; compare the actual fixture data.
        generated = json.loads((scratch / 'abi-lifecycle-example.json').read_bytes())
        if generated != json.loads((ROOT / PLANNING_DIR / 'abi-lifecycle-example.json').read_bytes()):
            raise ValueError('Lifecycle fixture differs from its checked-in codec result')

    if any(sha(ROOT / name) != digest for name, digest in before.items()):
        raise ValueError('Verification unexpectedly modified a planning input')
    return {'planning_programs_passed': 2, 'inputs_preserved': len(before),
            'lifecycle_fixture_reproduced': True}


def main() -> int:
    if sys.version_info < (3, 11):
        print('Python 3.11+ is required.', file=sys.stderr)
        return 1
    report_dir = ROOT / 'build' / 'repository-checks'
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'Repository/planning checks; no RTL, model-fidelity or hardware qualification',
              'python': platform.python_version()}
    try:
        report.update(check_metadata())
        report.update(check_planning(report_dir))
        report['status'] = 'PASS'
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        print(f'FAIL: {error}', file=sys.stderr)
    (report_dir / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"{report['status']}: reports in build/repository-checks/")
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
