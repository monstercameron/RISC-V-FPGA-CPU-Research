"""Build-side helpers of the ternary benchmark (build_bench.py --benchmark ternary).

SPDX-License-Identifier: MIT
Reads the data directory that tern_export.py wrote (packed weights, activations, reference
outputs, descriptor table), checks it against its recorded hashes, and returns what
build_bench.py needs: the extra source, compiler flags, the sizes for the RAM choice, the files
whose hashes lock the build, and the record for build.json.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
DATA_DEFAULT = 'build/cpu/bench/ternary-data/small-i2+lut5w+bs8'  # tern_export.py small i2,lut5w,bs8
SLOTS = ('i2', 'lut5w', 'bs8', 'stream', 'streamall')
SHAPE_DEFINE = {'small': 1, '2b4t': 0}
SCRATCH_BYTES = 128 << 10  # lut table tile, bit planes, outputs, stack slack


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(args, parser, root, stack_reserve, mailbox_bytes, ram_kibs):
    data = (root / (args.tern_data or DATA_DEFAULT)).resolve()
    for name in ('ternary_data.S', 'expected.json', 'export.json', 'act.bin', 'yref.bin', 'w_i2.bin'):
        if not (data / name).is_file():
            parser.error(f'{data / name} is missing: run sim/cpu/bench/ternary/tern_export.py first')
    export = json.loads((data / 'export.json').read_bytes())
    expected = json.loads((data / 'expected.json').read_bytes())
    for name, digest in export['files_sha256'].items():
        if sha(data / name) != digest:
            parser.error(f'{data / name} differs from the one tern_export.py recorded')
    if expected['native_checks']['kernel_mismatches'] or expected['native_checks']['qidx_bad']:
        parser.error('the data directory was generated with failing native checks')
    in_data = export['kernels']
    wanted = [k for k in (args.tern_kernels.split(',') if args.tern_kernels else [*in_data, 'stream', 'streamall']) if k]
    for k in wanted:
        if k not in SLOTS:
            parser.error(f'--tern-kernels: unknown kernel {k} (i2, lut5w, bs8, stream, streamall)')
        if k not in ('stream', 'streamall') and k not in in_data:
            parser.error(f'--tern-kernels: {k} is not packed in {data} (it holds {", ".join(in_data)})')
    mask = sum(1 << SLOTS.index(k) for k in wanted)
    blobs = sum(export['bytes'][n] for n in export['bytes'] if n.endswith('.bin'))
    need = blobs + (192 << 10) + SCRATCH_BYTES + stack_reserve + mailbox_bytes
    ram_kib = next(k for k in ram_kibs if k >= 256 and k * 1024 >= need)
    inputs = [data / n for n in export['files_sha256']] + [data / 'export.json'] + \
        [HERE / n for n in ('tern_bench.c', 'tern_kernels.h', 'tern_shapes.h', 'tern_build.py')]
    return {
        'data_dir': data, 'export': export, 'expected': expected, 'kernels': wanted, 'mask': mask,
        'ram_kib': ram_kib,
        'flags': [f'-DTERN_SHAPE={SHAPE_DEFINE[export["shape"]]}', f'-DTERN_KERNELS={mask}'],
        'include_dirs': [HERE, data], 'source': data / 'ternary_data.S', 'inputs': inputs,
    }
