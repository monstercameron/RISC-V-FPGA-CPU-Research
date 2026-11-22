#!/usr/bin/env python3
"""Make the data object and the native reference of the ternary benchmark (SPDX-License-Identifier: MIT).

Builds tern_gen.c for the host, runs it (it packs the synthetic weights for each kernel layout, computes
the exact int32 outputs with a plain int8 multiply-accumulate and checks that the three scalar kernels
reproduce them natively), and records the tools and the SHA-256 of every generated file.

Usage: python3 -B sim/cpu/bench/ternary/tern_export.py SHAPE KERNELS [OUT]
  SHAPE    small (T-small, 1,179,648 weights) or 2b4t (one BitNet b1.58 2B4T layer, 69,468,160 weights)
  KERNELS  comma list of the packings to include: i2,lut5w,bs8 (the i2 blob is always written)
  OUT      default build/cpu/bench/ternary-data/<shape>-<kernels with + between>/
"""
from pathlib import Path
import hashlib
import json
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CC_FLAGS = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ('small', '2b4t'):
        sys.exit(__doc__)
    shape, kernels = sys.argv[1], sys.argv[2]
    names = [k for k in kernels.split(',') if k]
    if not names or any(k not in ('i2', 'lut5w', 'bs8') for k in names):
        sys.exit('KERNELS must be a comma list of i2, lut5w, bs8')
    out = Path(sys.argv[3]).resolve() if len(sys.argv) == 4 else \
        ROOT / f'build/cpu/bench/ternary-data/{shape}-{"+".join(names)}'
    out.mkdir(parents=True, exist_ok=True)
    cc = shutil.which('clang') or shutil.which('gcc')
    if cc is None:
        sys.exit('a host C compiler is needed')
    exe = out / ('tern_gen.exe' if platform.system() == 'Windows' else 'tern_gen')
    subprocess.run([cc, *CC_FLAGS, f'-DTERN_SHAPE={1 if shape == "small" else 0}', f'-I{HERE}',
                    str(HERE / 'tern_gen.c'), '-o', str(exe)], check=True)
    run = subprocess.run([str(exe), shape, ','.join(names), str(out)], capture_output=True, text=True)
    print(run.stdout.strip())
    if run.returncode:
        sys.exit(f'tern_gen failed ({run.returncode}): {run.stderr}')
    files = ['ternary_data.S', 'w_i2.bin', 'act.bin', 'yref.bin', 'expected.json'] + \
        [f'w_{k}.bin' for k in names if k != 'i2']
    export = {
        'shape': shape, 'kernels': names,
        'compiler': subprocess.run([cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
        'flags': CC_FLAGS, 'host': {'platform': platform.platform(), 'machine': platform.machine()},
        'generator_sha256': {n: sha(HERE / n) for n in ('tern_gen.c', 'tern_data.h', 'tern_kernels.h', 'tern_shapes.h')},
        'files_sha256': {n: sha(out / n) for n in files},
        'bytes': {n: (out / n).stat().st_size for n in files},
    }
    (out / 'export.json').write_bytes((json.dumps(export, indent=2) + '\n').encode())
    exe.unlink()
    print(f'Output: {out}')


if __name__ == '__main__':
    main()
