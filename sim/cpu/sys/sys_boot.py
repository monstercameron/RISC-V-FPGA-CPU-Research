"""Boot OpenSBI + Linux + busybox on rv_iss --sys (lab time model) to the shell, then power off.

Uses the images that sim/cpu/sys/build_all.sh leaves in build/third-party/linux-lab/out/ (fw_payload.elf
with the kernel and its built-in initramfs, lab-virt.dtb). Checks: the run ends through the SiFive test
finisher with exit 0; the console shows the init marker, the shell's answer to the scripted input and the
power-down message. Then a full-system checkpoint (RVISSST3) taken at the init marker is restored and run to
the end; its final state must equal the uninterrupted run's byte for byte.

Usage (WSL): python3 -B sim/cpu/sys/sys_boot.py [--out-dir DIR] [--no-checkpoint]
SPDX-License-Identifier: MIT
"""
import argparse
import filecmp
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import riscv_tests  # noqa: E402  (build_iss, third_party)

ROOT = riscv_tests.ROOT
INPUT = b'echo SHELL-OK\nuname -m\nexit\n'
MARKER = 'LAB-VIRT-MARKER: busybox init reached'
RAM = 64 << 20
MAX = 400_000_000


def run(exe, args, timeout=280):
    r = subprocess.run([str(exe), '--sys', '1', '--ram', str(RAM), *map(str, args)], capture_output=True,
                       text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'rv_iss failed: {r.stderr}')
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', type=Path, default=ROOT / 'build/sys/boot')
    ap.add_argument('--no-checkpoint', action='store_true')
    args = ap.parse_args()
    images = riscv_tests.LINUX_LAB / 'out'
    elf, dtb = images / 'fw_payload.elf', images / 'lab-virt.dtb'
    if not elf.is_file() or not dtb.is_file():
        print(f'FAIL: no images in {images}; build them with sim/cpu/sys/build_all.sh')
        return 2
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / 'uart-in.txt').write_bytes(INPUT)
    exe = riscv_tests.build_iss()
    common = ['--uart-in', out / 'uart-in.txt', '--max', MAX]
    res = run(exe, ['--elf', elf, '--dtb', dtb, *common, '--uart-out', out / 'console.txt',
                    '--dump-on-output', MARKER, '--dump-prefix', out / 'boot-', '--final-state', out / 'final.state'])
    console = (out / 'console.txt').read_text(errors='replace')
    (out / 'result.json').write_text(json.dumps(res, indent=1))
    problems = []
    if res['stop'] != 'finisher' or res['exit_code'] != 0:
        problems.append(f"run ended with {res['stop']} code {res['exit_code']}")
    lines = console.splitlines()
    for text in (MARKER, 'LAB-VIRT-MARKER: shell ran a command on riscv64', 'reboot: Power down'):
        if text not in console:
            problems.append(f'console lacks {text!r}')
    if 'SHELL-OK' not in lines or not any(x.endswith('riscv64') and x.startswith('#') for x in lines):
        problems.append('the shell did not answer the scripted console input')
    if problems:
        print('FAIL: sys-boot: ' + '; '.join(problems))
        return 1
    print(f"PASS: sys-boot reached the busybox shell and powered off: {res['instructions']:,} instructions, "
          f"{res['seconds']:.2f} s, {res['mips']:.1f} MIPS, mtime {res['mtime']:,}")
    if not args.no_checkpoint:
        state = out / 'boot-marker.state'
        res2 = run(exe, ['--state', state, *common, '--uart-out', out / 'console-restored.txt',
                         '--final-state', out / 'final-restored.state'])
        if not filecmp.cmp(out / 'final.state', out / 'final-restored.state', shallow=False):
            print('FAIL: sys-boot checkpoint: the restored run ends in a different state')
            return 1
        tail = (out / 'console-restored.txt').read_bytes()
        if (res2['stop'], res2['exit_code'], res2['instructions']) != (res['stop'], res['exit_code'], res['instructions']) \
                or not tail or not (out / 'console.txt').read_bytes().endswith(tail):
            print(f"FAIL: sys-boot checkpoint: the restored run ended {res2['stop']}/{res2['exit_code']} after "
                  f"{res2['instructions']} instructions, or its console output is not the original's tail")
            return 1
        print(f"PASS: sys-boot checkpoint at instruction {res['marker_state_index']:,} (RVISSST3, "
              f"{state.stat().st_size:,} bytes) restores to an identical final state")
    print(f"PASS: {res['instructions']} sys-boot instructions")
    return 0


if __name__ == '__main__':
    sys.exit(main())
