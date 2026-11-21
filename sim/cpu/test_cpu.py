"""Free CPU simulation suite: generated programs, sequential oracle, stalls/faults.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import shutil
import subprocess

from reference import MASK, execute

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/cpu'


def i_type(op, rd, f3, rs1, imm):
    return ((imm & 4095) << 20) | rs1 << 15 | f3 << 12 | rd << 7 | op


def r_type(op, rd, f3, rs1, rs2, f7=0):
    return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op


def store(f3, rs1, rs2, offset):
    offset &= 4095
    return (offset >> 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | (offset & 31) << 7 | 0x23


def branch(f3, rs1, rs2, offset):
    offset &= 8191
    return ((offset >> 12) << 31) | (((offset >> 5) & 63) << 25) | rs2 << 20 | rs1 << 15 | f3 << 12 | (((offset >> 1) & 15) << 8) | (((offset >> 11) & 1) << 7) | 0x63


def jal(rd, offset):
    offset &= (1 << 21) - 1
    return (offset >> 20) << 31 | ((offset >> 1) & 1023) << 21 | ((offset >> 11) & 1) << 20 | ((offset >> 12) & 255) << 12 | rd << 7 | 0x6f


CONSTANTS = [0, 1, MASK, 0x8000000000000000, 0x7fffffffffffffff,
             0x80000000, 0x1122334480000080, 31, 32, 63, 64, 0x8001ffff]


def prefix():
    return [(2 << 12) | (30 << 7) | 0x37] + [i_type(3, n+1, 3, 30, n*8) for n in range(len(CONSTANTS))]


def image_for(words):
    result = bytearray(16384)
    assert len(words)*4 < 8192
    for n, word in enumerate(words):
        result[4*n:4*n+4] = word.to_bytes(4, 'little')
    for n, value in enumerate(CONSTANTS):
        result[8192+8*n:8200+8*n] = value.to_bytes(8, 'little')
    return result


def cases():
    p = prefix()
    for op in (0x33, 0x3b):
        for f3 in (range(8) if op == 0x33 else (0, 1, 5)):
            for a, b in ((3, 2), (4, 5), (7, 8), (7, 9), (7, 10), (7, 11)):
                p.append(r_type(op, 20, f3, a, b))
                if f3 in (0, 5):
                    p.append(r_type(op, 21, f3, a, b, 32))
    for f3 in (0, 2, 3, 4, 6, 7):
        for imm in (-2048, -1, 0, 1, 2047):
            p.append(i_type(0x13, 20, f3, 7, imm))
    for op in (0x13, 0x1b):
        for sh in ((0, 1, 31, 32, 63) if op == 0x13 else (0, 1, 31)):
            for f3, high in ((1, 0), (5, 0), (5, 0x400)):
                p.append(i_type(op, 20, f3, 7, high | sh))
    for imm in (-2048, -1, 0, 1, 2047):
        p.append(i_type(0x1b, 20, 0, 6, imm))
    p += [0x80000ab7, 0xfffffb17, i_type(0x13, 0, 0, 0, 77), r_type(0x33, 22, 0, 0, 2), 0x0ff0000f, 0x0000100f, 0x100073]
    yield 'integer', p, 0, MASK

    p = prefix() + [(3 << 12) | (31 << 7) | 0x37]
    for f3 in range(4):
        size = 1 << f3
        for offset in range(0, 8, size):
            p += [store(f3, 31, 7, offset), i_type(3, 20, f3, 31, offset)]
            if f3 < 3:
                p += [i_type(3, 21, f3 + 4, 31, offset)]
    p += [i_type(3, 0, 3, 31, 0), i_type(0x13, 29, 0, 31, 8), store(3, 29, 4, -8), i_type(3, 22, 3, 29, -8), 0x100073]
    yield 'memory_lanes', p, 0, MASK

    p = prefix()
    for f3 in (0, 1, 4, 5, 6, 7):
        for a, b in ((2, 2), (3, 2), (2, 3)):
            p += [branch(f3, a, b, 8), i_type(0x13, 20, 0, 20, 1)]
    p += [i_type(0x13, 21, 0, 0, 5), i_type(0x13, 21, 0, 21, -1), branch(1, 21, 0, -4)]
    p += [jal(22, 8), 0xffffffff]
    target = (len(p) + 3) * 4
    p += [i_type(0x13, 23, 0, 0, target | 1), i_type(0x67, 24, 0, 23, 0), 0xffffffff]
    p += [branch(1, 0, 0, 2), 0x100073]  # misaligned target not taken
    yield 'control_flow', p, 0, MASK

    # Overwrite an initially illegal instruction, fence, then fetch the new word.
    p = [(0x02a01 << 12) | (5 << 7) | 0x37,
         i_type(0x13, 5, 0, 5, -1517), store(2, 0, 5, 512),
         0x0000100f, jal(0, 512 - 16)]
    p += [0] * (129 - len(p)) + [0x100073]
    yield 'self_modifying_fence_i', p, 0, MASK

    for seed in (101, 202, 303):
        rng = random.Random(seed)
        p = prefix()
        for _ in range(600):
            rd, a, b = rng.randrange(1, 29), rng.randrange(29), rng.randrange(29)
            op = rng.choice((0x13, 0x1b, 0x33, 0x3b))
            f3 = rng.choice((0, 1, 5) if op in (0x1b, 0x3b) else tuple(range(8)))
            if op in (0x13, 0x1b):
                imm = rng.randrange(-2048, 2048)
                if f3 in (1, 5):
                    imm = rng.randrange(32 if op == 0x1b else 64)
                    if f3 == 5 and rng.randrange(2): imm |= 0x400
                p.append(i_type(op, rd, f3, a, imm))
            else:
                f7 = 32 if f3 in (0, 5) and rng.randrange(2) else 0
                p.append(r_type(op, rd, f3, a, b, f7))
        yield f'random_{seed}', p + [0x100073], 0, MASK

    for name, words in (
        ('illegal_zero', [0]), ('illegal_mul', [r_type(0x33, 1, 0, 2, 3, 1)]),
        ('illegal_shift', [i_type(0x13, 1, 1, 0, 0x800)]),
        ('illegal_word_shift', [i_type(0x1b, 1, 1, 0, 32)]),
        ('illegal_load', [i_type(3, 1, 7, 0, 0)]),
        ('illegal_store', [store(4, 0, 1, 0)]),
        ('illegal_branch', [branch(2, 0, 0, 4)]),
        ('illegal_jalr', [i_type(0x67, 1, 1, 0, 0)]),
        ('illegal_csr', [0x300010f3]), ('ecall', [0x73]),
        ('misaligned_jal', [jal(1, 2)]), ('misaligned_taken_branch', [branch(0, 0, 0, 2)]),
        ('misaligned_jalr', [i_type(0x13, 1, 0, 0, 3), i_type(0x67, 2, 0, 1, 0)]),
        ('misaligned_lh', [i_type(3, 1, 1, 0, 1)]),
        ('misaligned_lw', [i_type(3, 1, 2, 0, 2)]),
        ('misaligned_ld', [i_type(3, 1, 3, 0, 4)]),
        ('misaligned_sh', [store(1, 0, 1, 1)]),
        ('misaligned_sw', [store(2, 0, 1, 2)]),
        ('misaligned_sd', [store(3, 0, 1, 4)]),
        ('unmapped_fetch', [(4 << 12) | (1 << 7) | 0x37, i_type(0x67, 0, 0, 1, 0)]),
        ('unmapped_load', [(4 << 12) | (1 << 7) | 0x37, i_type(3, 2, 3, 1, 0)]),
        ('unmapped_store', [(4 << 12) | (1 << 7) | 0x37, store(3, 1, 2, 0)]),
    ):
        yield name, words + [0x100073], 0, MASK
    yield 'fetch_bus_fault', [i_type(0x13, 1, 0, 0, 5), 0x100073], 1, 0
    yield 'load_bus_fault_x0', [(2 << 12) | (1 << 7) | 0x37, i_type(3, 0, 3, 1, 0), 0x100073], 2, 8192
    yield 'store_bus_fault', [(2 << 12) | (1 << 7) | 0x37, store(3, 1, 1, 0), 0x100073], 3, 8192


def command(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='Optional raw firmware binary for an additional differential test')
    parser.add_argument('--icache-beats', type=int, help='Override the core instruction-cache size (power of two >= 2)')
    parser.add_argument('--dcache-beats', type=int, help='Override the core data-cache size (power of two >= 2)')
    args = parser.parse_args()
    cache = [f'-Ptb_core.ICACHE_BEATS={args.icache_beats}'] if args.icache_beats else []
    cache += [f'-Ptb_core.DCACHE_BEATS={args.dcache_beats}'] if args.dcache_beats else []
    if not shutil.which('iverilog') or not shutil.which('vvp'):
        parser.error('iverilog and vvp are required; use the documented Ubuntu/WSL launcher')
    OUT.mkdir(parents=True, exist_ok=True)
    executable = OUT / 'cpu.vvp'
    command(['iverilog', '-g2012', '-Wall', '-s', 'tb_core', *cache, '-o', executable,
             ROOT / 'rtl/cpu/rv64_core.sv', ROOT / 'sim/cpu/tb_core.sv'])
    command(['iverilog', '-g2012', '-Wall', '-s', 'rv64_bram_soc', '-o', OUT/'soc.vvp',
             ROOT/'rtl/cpu/rv64_core.sv', ROOT/'rtl/cpu/rv64_bram_soc.sv'])
    command(['iverilog','-g2012','-Wall','-s','tb_reset','-o',OUT/'reset.vvp',
             ROOT/'rtl/cpu/rv64_core.sv',ROOT/'sim/cpu/tb_reset.sv'])
    reset_result=command(['vvp',OUT/'reset.vvp']).strip()
    command(['iverilog','-g2012','-Wall','-s','tb_soc','-o',OUT/'bram-soc.vvp',
             ROOT/'rtl/cpu/rv64_core.sv',ROOT/'rtl/cpu/rv64_bram_soc.sv',ROOT/'sim/cpu/tb_soc.sv'])
    smoke=image_for([0x00500093,0x00700113,0x002081b3,0x00003237,0x00323023,0x00100073])
    smoke_hex=OUT/'soc-smoke.hex'
    smoke_hex.write_text(''.join(f'{int.from_bytes(smoke[i:i+8],"little"):016x}\n' for i in range(0,len(smoke),8)),encoding='ascii')
    soc_results=[command(['vvp',OUT/'bram-soc.vvp',f'+image={smoke_hex}','+expected=c']).strip()]
    workloads = [(name,image_for(words),kind,addr) for name,words,kind,addr in cases()]
    if args.image:
        data = args.image.read_bytes()
        if len(data)>16384: raise ValueError('Firmware exceeds laboratory RAM')
        workloads.append(('compiled_firmware', data.ljust(16384,b'\0'), 0, MASK))
        bram=args.image.with_name('firmware-bram.hex')
        if not bram.is_file(): raise ValueError('Missing companion firmware-bram.hex')
        soc_results.append(command(['vvp',OUT/'bram-soc.vvp',f'+image={bram}','+expected=24','+second']).strip())
    records,coverage = [],set()
    for name, image, kind, address in workloads:
        expected, covered = execute(image,kind,address)
        if name == 'compiled_firmware':
            if 'W 0000000000003000 0000000000000024 ff' not in expected:
                raise AssertionError('Compiled firmware did not produce the known sum 36')
        coverage |= covered
        hexfile = OUT / (name+'.hex')
        hexfile.write_text(''.join(f'{b:02x}\n' for b in image),encoding='ascii')
        for stalls,seed in ((0,1),(7,42),(19,103)):
            trace = OUT / f'{name}-stall{stalls}.trace'
            output = command(['vvp',executable,f'+image={hexfile}',f'+trace={trace}',
                              f'+stall={stalls}',f'+seed={seed}',f'+fault_kind={kind}',f'+fault_addr={address:x}'])
            actual=trace.read_text().splitlines()
            if actual!=expected:
                for index in range(max(len(actual),len(expected))):
                    a=actual[index] if index<len(actual) else '<missing>'
                    e=expected[index] if index<len(expected) else '<missing>'
                    if a!=e: raise AssertionError(f'{name} stall={stalls} event {index}:\nactual {a}\nexpect {e}')
            records.append({'case':name,'max_wait_cycles':stalls,'events':len(actual),'result':'PASS','simulator_summary':output.strip()})
    required=set('lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw ld lbu lhu lwu sb sh sw sd addi slti sltiu xori ori andi slli srli srai add sub sll slt sltu xor srl sra or and addiw slliw srliw sraiw addw subw sllw srlw sraw fence fence.i ecall ebreak'.split())
    missing=required-coverage
    if missing: raise AssertionError('Missing instruction coverage: '+str(sorted(missing)))
    for branch_name in ('beq','bne','blt','bge','bltu','bgeu'):
        for outcome in ('taken','not_taken'):
            if branch_name+':'+outcome not in coverage: raise AssertionError('Missing branch outcome')
    report={'status':'PASS','cases':len(workloads),'runs':len(records),'instruction_names_covered':len(required),
            'icache_beats':args.icache_beats or 'RTL default','dcache_beats':args.dcache_beats or 'RTL default',
            'reset_test':reset_result,'bram_soc_tests':soc_results,
            'coverage':sorted(coverage),'validation_scope':'local directed/random differential simulation; no official ISA certification or synthesis',
            'rtl_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'rtl/cpu').glob('*.sv'))},
            'simulator':command(['iverilog','-V']).splitlines()[0],'results':records}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {len(workloads)} programs x 3 wait patterns = {len(records)} runs; {len(required)} instruction names covered.')
    print('Includes precise traps, invalid encodings, bus faults, x0, all memory lanes, branch outcomes and ordered retirement.')


if __name__=='__main__': main()
