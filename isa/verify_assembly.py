"""Assemble examples and check instruction encodings; does NOT execute kernels.

Python 3.11+, clang and llvm-objdump. No downloads. Output: build/rva23-assembly/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = 'rva23u64'
BF16 = BASE + '_zfbfmin_zvfbfmin_zvfbfwma'
UNITS = {'scalar_ops.S': BASE, 'rvv_ops.S': BASE, 'transport.S': BASE,
         'bf16_optional.S': BF16, 'opcode_examples.S': BF16}


def run(args: list[str], *, success: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if success and result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def r(op: int, rd: int, f3: int, rs1: int, rs2: int, f7: int) -> int:
    return op | rd << 7 | f3 << 12 | rs1 << 15 | rs2 << 20 | f7 << 25


def expected_words() -> list[int]:
    # Field construction from the cited ISA/opcode definitions, not disassembly.
    # x5=t0, x10=a0; f10=fa0, f11=fa1, f12=fa2; vm=1 (unmasked).
    fp = lambda f7: r(0x53, 10, 0, 11, 12, f7)
    vec = lambda f6, vd, f3, s1, s2: r(0x57, vd, f3, s1, s2, (f6 << 1) | 1)
    return [
        0x03 | 5 << 7 | 5 << 12 | 10 << 15,  # lhu
        0x13 | 5 << 7 | 1 << 12 | 5 << 15 | 16 << 20,
        0x07 | 2 << 12 | 10 << 15,
        0x27 | 2 << 12 | 10 << 15,
        fp(0), fp(8), r(0x43, 10, 0, 11, 12, 10 << 2),
        fp(12), r(0x53, 10, 0, 11, 0, 44),
        0x57 | 5 << 7 | 7 << 12 | 10 << 15 | 0xd1 << 20,
        r(0x07, 8, 5, 10, 0, 1), r(0x27, 12, 6, 10, 0, 1),
        vec(0x2c, 12, 5, 0, 10), vec(0x03, 8, 1, 12, 10),
        r(0x53, 10, 0, 11, 8, 0x22), r(0x53, 10, 0, 11, 6, 0x20),
        vec(0x12, 10, 1, 0x0d, 8), vec(0x12, 8, 1, 0x1d, 10),
        vec(0x3b, 12, 5, 0, 8),
        0x0f | 0xff << 20,
        0x23 | 2 << 12 | 10 << 15 | 5 << 20 | 0x30 << 25,
        0x13 | 6 << 12 | 10 << 15 | 1 << 20,
        0x0f | 2 << 12 | 10 << 15 | 1 << 20,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clang', default=shutil.which('clang'))
    parser.add_argument('--objdump', default=shutil.which('llvm-objdump'))
    args = parser.parse_args()
    if not args.clang or not args.objdump:
        parser.error('clang and llvm-objdump required; provide their executable paths')
    out = ROOT / 'build/rva23-assembly'
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for name, arch in UNITS.items():
        source = ROOT / 'isa' / name
        obj = out / (source.stem + '.o')
        command = [args.clang, '--target=riscv64-unknown-elf', '-march=' + arch,
                   '-mabi=lp64d', '-c', str(source), '-o', str(obj)]
        run(command)
        dis = run([args.objdump, '-d', '--mattr=+zfbfmin,+zvfbfmin,+zvfbfwma', str(obj)]).stdout
        if '<unknown>' in dis:
            raise RuntimeError('Unknown instruction in ' + name)
        (out / (source.stem + '.dis.txt')).write_bytes(dis.encode('utf-8'))
        records.append({'source': 'isa/' + name, 'march': arch,
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})

    negative = run([args.clang, '--target=riscv64-unknown-elf', '-march=' + BASE,
                    '-mabi=lp64d', '-c', str(ROOT / 'isa/bf16_optional.S'),
                    '-o', str(out / 'must-not-build.o')], success=False)
    if not negative.returncode or not re.search('requires.*(Zfbfmin|Zvfbfwma)', negative.stderr, re.I):
        raise RuntimeError('BF16 instructions were not rejected for the base profile as expected')
    (out / 'optional-extension-negative.txt').write_bytes(negative.stderr.encode('utf-8'))

    dis = (out / 'opcode_examples.dis.txt').read_text(encoding='utf-8')
    rows = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$', dis, re.M)
    actual = [int(word, 16) for _, word, _ in rows]
    if actual != expected_words():
        raise RuntimeError('Encoding specimens do not match the ISA field definitions')
    encoded = [{'offset': int(offset, 16), 'word': '0x' + word,
                'major_opcode': f'0x{int(word, 16) & 0x7f:02x}',
                'little_endian_bytes': int(word, 16).to_bytes(4, 'little').hex(' '),
                'assembly': ' '.join(asm.split())} for offset, word, asm in rows]
    report = {'status': 'PASS (assembly and encoding only)',
              'compiler': run([args.clang, '--version']).stdout.splitlines()[0],
              'units': records, 'encoding_checks': len(encoded),
              'base_profile_rejects_optional_bf16': True,
              'runtime_execution': 'NOT RUN; no RISC-V simulator used',
              'hardware_or_full_model_validation': 'NOT RUN', 'encodings': encoded}
    (out / 'verification.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'PASS: {len(records)} units assembled; {len(encoded)} encodings matched; optional BF16 rejected under base RVA23.')
    print('Runtime execution and full-model/hardware validation: NOT RUN.')


if __name__ == '__main__':
    main()
