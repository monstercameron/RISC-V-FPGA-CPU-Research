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
    'llm-rva23-mapping.md', 'isa/README.md',
    'cpu/README.md', 'cpu/architecture.md', 'cpu/c-demo.md', 'cpu/visualizer.md', 'cpu/addition.md', 'cpu/programs.md', 'cpu/inputs.md',
    'cpu/review-rubric.md', 'TODO.md',
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
    'sim/cpu/test_cpu.py', 'sim/cpu/reference.py', 'sim/cpu/tb_core.sv',
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
)
PLANNING_INPUTS = (
    'memory_model.py', 'plan_audit_checks.py', 'refinement_checks.py', 'abi_v1.py',
    'reference-source-lock.json', 'qualification-fixtures.json',
    'abi-v1.md', 'adapter-v1.md', 'implementation-contract.md',
)


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
            if not (path.parent / target).exists():
                raise ValueError(f'Broken local link in {name}: {target}')
            checked_links += 1

    manifest = json.loads((ROOT / 'licenses/provenance.json').read_bytes())
    for entry in manifest['files']:
        path = (ROOT / entry['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError(f'Invalid license path: {entry["path"]}')
        if sha(path) != entry['sha256']:
            raise ValueError(f'Upstream license bytes changed: {entry["path"]}')

    workflow = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    actions = re.findall(r'uses:\s+([^\s@]+)@([^\s#]+)', workflow)
    if not actions or any(not re.fullmatch(r'[0-9a-f]{40}', ref) for _, ref in actions):
        raise ValueError('Every external CI action must be pinned to a full commit SHA')
    return {'local_links_checked': checked_links, 'license_identities_checked': len(manifest['files']),
            'pinned_action_uses': len(actions)}


def check_planning(report_dir: Path) -> dict:
    # Existing refinement checks emit a lifecycle fixture beside their script.
    # Run them on a disposable copy to avoid rewriting reviewed repository files.
    watched = [ROOT / name for name in PLANNING_INPUTS]
    watched += [p for p in (ROOT / 'reference-sources').iterdir() if p.is_file()]
    before = {str(p.relative_to(ROOT)): sha(p) for p in watched}
    with tempfile.TemporaryDirectory(prefix='fpga-repository-check-') as temporary:
        scratch = Path(temporary)
        for name in PLANNING_INPUTS:
            shutil.copy2(ROOT / name, scratch / name)
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
        if generated != json.loads((ROOT / 'abi-lifecycle-example.json').read_bytes()):
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
