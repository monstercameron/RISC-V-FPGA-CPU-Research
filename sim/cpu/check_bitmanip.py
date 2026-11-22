"""Check the B extension against the compiler's reading of C (architecture 0.6.0).

Builds sim/cpu/bitmanip_check.c twice with clang: for rv64im (base instructions
only) and for rv64im_zba_zbb_zbs (the compiler emits B instructions for the same
expressions). Runs both on the RTL with the trace testbench, requires each trace
to match the reference model, requires the B build to contain B instructions, and
requires both builds to produce identical results.

Needs Python 3.11+, clang, ld.lld, llvm-objcopy, llvm-objdump, Icarus (Linux/WSL).
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim/cpu'))
sys.path.insert(0, str(ROOT / 'sim/cpu/bench'))
from reference import execute  # noqa: E402
from build_bench import LINKER_SCRIPT, MAILBOX_BYTES, STACK_RESERVE  # noqa: E402

OUT = ROOT / 'build/cpu/bitmanip-check'
RAM = 64 * 1024
B_MNEMONICS = re.compile(r'\t(sh[123]add(\.uw)?|add\.uw|slli\.uw|andn|orn|xnor|clzw?|ctzw?|cpopw?|maxu?|minu?|'
                         r'sext\.[bh]|zext\.h|rolw?|rorw?|roriw?|orc\.b|rev8|bclri?|bexti?|binvi?|bseti?)\b')


def run(args):
    done = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=300)
    if done.returncode:
        raise SystemExit(f'Failed: {" ".join(map(str, args))}\n{done.stdout}{done.stderr}')
    return done.stdout


def build(isa, folder):
    folder.mkdir(parents=True, exist_ok=True)
    mailbox = RAM - MAILBOX_BYTES
    (folder / 'link.ld').write_text(LINKER_SCRIPT.format(ram_bytes=RAM, mailbox=mailbox,
                                                         program_limit=mailbox - STACK_RESERVE, extra=''),
                                    encoding='ascii')
    elf = folder / 'check.elf'
    run(['clang', '--target=riscv64-unknown-elf', f'-march={isa}', '-mabi=lp64', '-mcmodel=medany',
         '-msmall-data-limit=0', '-mno-relax', '-O2', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
         '-nostdlib', '-nostdlibinc', '-I', ROOT / 'sim/cpu/bench/include', '-fuse-ld=lld', '-Wl,--no-relax',
         f'-Wl,-T,{folder / "link.ld"}', ROOT / 'sim/cpu/bench/start.S', ROOT / 'sim/cpu/bitmanip_check.c',
         ROOT / 'sim/cpu/bench/runtime.c', '-o', elf])
    run(['llvm-objcopy', '-O', 'binary', elf, folder / 'check.bin'])
    disassembly = run(['llvm-objdump', '-d', '-M', 'no-aliases', elf])
    (folder / 'check.disasm.txt').write_text(disassembly, encoding='utf-8')
    image = (folder / 'check.bin').read_bytes().ljust(RAM, b'\0')
    (folder / 'check-bytes.hex').write_text(''.join(f'{b:02x}\n' for b in image), encoding='ascii')
    return image, mailbox, sorted({m[1] for m in B_MNEMONICS.finditer(disassembly)})


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', choices=('multicycle', 'pipe', 'ooo'), default='multicycle',
                        help='rtl/cpu/rv64_core.sv (multicycle) or rtl/cpu/rv64_pipe.sv (pipelined)')
    args = parser.parse_args()
    for tool in ('clang', 'ld.lld', 'llvm-objcopy', 'llvm-objdump', 'iverilog', 'vvp'):
        if not shutil.which(tool):
            raise SystemExit(f'{tool} is required')
    OUT.mkdir(parents=True, exist_ok=True)
    vvp = OUT / 'tb_core.vvp'
    run(['iverilog', '-g2012', '-Wall', *(['-DWIDE_TRACE'] if args.core == 'ooo' else []), '-s', 'tb_core',
         f'-Ptb_core.MEM_BYTES={RAM}', '-o', vvp,
         ROOT / {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}[args.core],
         ROOT / 'sim/cpu/tb_core.sv'])
    results = {}
    for isa in ('rv64im_zifencei', 'rv64im_zba_zbb_zbs_zifencei'):
        folder = OUT / isa
        image, mailbox, used = build(isa, folder)
        expected, _ = execute(image, max_steps=5_000_000)
        trace = folder / 'trace'
        run(['vvp', vvp, f'+image={folder / "check-bytes.hex"}', f'+trace={trace}', '+stall=3', '+seed=9',
             '+max_cycles=20000000'])
        actual = trace.read_text().splitlines()
        if actual != expected:
            index = next(i for i, (x, y) in enumerate(zip(actual + ['<end>'], expected + ['<end>'])) if x != y)
            raise SystemExit(f'{isa}: RTL trace differs from the reference at event {index}: '
                             f'{actual[index:index + 1]} vs {expected[index:index + 1]}')
        words = {}
        for line in actual:
            parts = line.split()
            if parts[0] == 'W' and mailbox + 16 <= int(parts[1], 16) < mailbox + 16 + 12 * 8:
                words[(int(parts[1], 16) - mailbox - 16) // 8] = parts[2]
        results[isa] = {'groups': [words.get(g) for g in range(12)], 'b_instructions': used,
                        'retired': sum(line.startswith('R ') for line in actual)}
    base, with_b = results['rv64im_zifencei'], results['rv64im_zba_zbb_zbs_zifencei']
    if None in base['groups'] or base['groups'] != with_b['groups']:
        raise SystemExit('B build results differ from the base build: '
                         + json.dumps({'base': base['groups'], 'b': with_b['groups']}))
    if base['b_instructions'] or len(with_b['b_instructions']) < 20:
        raise SystemExit(f'Unexpected B instruction use: base {base["b_instructions"]}, B {with_b["b_instructions"]}')
    report = {'status': 'PASS', 'results': results,
              'scope': 'Same C built without and with Zba/Zbb/Zbs; identical results on the RTL; traces match the reference.'}
    (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: identical results for all 12 groups; B build uses {len(with_b["b_instructions"])} B instructions '
          f'({", ".join(with_b["b_instructions"])}); retired {base["retired"]:,} (base) and {with_b["retired"]:,} (B).')


if __name__ == '__main__':
    main()
