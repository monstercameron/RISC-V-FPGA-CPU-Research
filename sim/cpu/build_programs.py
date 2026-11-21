"""Compile, simulate and verify every built-in lesson; leave addition open.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from program_catalog import PROGRAMS
from program_inputs import validate_inputs, render_source, expected_output

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-library', action='store_true', help='Exit 0 only if all saved lessons and the viewer match current sources')
    for option in ('clang', 'objcopy', 'objdump', 'distribution'):
        parser.add_argument('--' + option)
    args = parser.parse_args()
    if args.check_library:
        try:
            for program in PROGRAMS:
                folder = ROOT / 'build/cpu/programs' / program
                report = json.loads((folder / 'verification.json').read_bytes())
                data = json.loads((folder / 'viewer-data.json').read_bytes())
                assert data['programId'] == report['program'] == program
                assert data['meta']['status'] == report['status'] == 'PASS'
                assert data['meta']['source_sha256'] == report['source_sha256']
                inputs=validate_inputs(program,data['inputs'])
                assert inputs==report['inputs']
                assert expected_output(program,inputs)==report['observed_output']
                generated=render_source(program,(ROOT/PROGRAMS[program]['source']).read_text(encoding='utf-8'),inputs)
                assert hashlib.sha256(generated.encode()).hexdigest()==report['generated_source_sha256']
                assert (folder/'program.c').read_bytes()==generated.encode()
                for name, digest in report['source_sha256'].items():
                    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
            active = json.loads((ROOT / 'cpu/visualizer-verification.json').read_bytes())
            assert hashlib.sha256((ROOT / 'cpu/visualizer.template.html').read_bytes()).hexdigest() == active['template_sha256']
            assert hashlib.sha256((ROOT / 'cpu/cpu-visualizer.html').read_bytes()).hexdigest() == active['viewer_sha256']
        except (OSError, KeyError, ValueError, AssertionError):
            raise SystemExit(1)
        print('Saved lesson library is current.')
        return
    forwarded = [item for name, value in vars(args).items() if value for item in ('--' + name, value)]
    for program in [p for p in PROGRAMS if p != 'add'] + ['add']:
        print('Verifying lesson: ' + program, flush=True)
        command = [sys.executable, '-B', 'sim/cpu/build_visualizer.py', '--program', program] + forwarded
        if program != 'add':
            command.append('--capture-only')
        subprocess.run(command, cwd=ROOT, check=True, timeout=240)
    records = {}
    for program in PROGRAMS:
        folder = ROOT / 'build/cpu/programs' / program
        report = json.loads((folder / 'verification.json').read_bytes())
        assert report['status'] == 'PASS' and report['program'] == program
        records[program] = report
        records[program]['saved_capture_sha256'] = hashlib.sha256((folder / 'viewer-data.json').read_bytes()).hexdigest()
    summary = {'status': 'PASS', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
               'scope': 'Seven C programs compiled and run on the RTL simulator; no physical FPGA claim.',
               'programs': records}
    (ROOT / 'cpu/programs-verification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('PASS: all seven lessons verified; addition is the initial viewer.', flush=True)


if __name__ == '__main__':
    main()
