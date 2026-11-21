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

    # M extension (architecture 0.4.0): every operation over operand pairs that
    # include zero divisors, signed overflow, -1, extremes, small dividends and
    # long quotients. Registers x1..x12 hold CONSTANTS.
    p = prefix()
    operands = (2, 3, 4, 5, 6, 7, 8, 12)
    divisors = (1, 2, 3, 4, 5, 6, 7, 8, 12)
    for op, functions in ((0x33, range(8)), (0x3b, (0, 4, 5, 6, 7))):
        for f3 in functions:
            for a in operands:
                for b in divisors:
                    p.append(r_type(op, 20, f3, a, b, 1))
    p += [r_type(0x33, 0, 4, 5, 2, 1), 0x100073]  # divide into x0: no write
    yield 'm_extension', p, 0, MASK

    # B extension (architecture 0.6.0): every Zba/Zbb/Zbs instruction over the same
    # operand pairs. Encodings: (opcode, funct3, funct7 or None for unary/immediate).
    p = prefix()
    register_ops = [(0x33, 2, 0x10), (0x33, 4, 0x10), (0x33, 6, 0x10), (0x33, 7, 0x20), (0x33, 6, 0x20),
                    (0x33, 4, 0x20), (0x33, 4, 0x05), (0x33, 5, 0x05), (0x33, 6, 0x05), (0x33, 7, 0x05),
                    (0x33, 1, 0x30), (0x33, 5, 0x30), (0x33, 1, 0x24), (0x33, 5, 0x24), (0x33, 1, 0x34),
                    (0x33, 1, 0x14), (0x3b, 0, 0x04), (0x3b, 2, 0x10), (0x3b, 4, 0x10), (0x3b, 6, 0x10),
                    (0x3b, 1, 0x30), (0x3b, 5, 0x30)]
    for op, f3, f7 in register_ops:
        for a in operands:
            for b in (1, 2, 3, 4, 8, 9, 10, 12):
                p.append(r_type(op, 20, f3, a, b, f7))
    unary = [(0x13, 1, 0x600), (0x13, 1, 0x601), (0x13, 1, 0x602), (0x13, 1, 0x604), (0x13, 1, 0x605),
             (0x13, 5, 0x287), (0x13, 5, 0x6b8), (0x1b, 1, 0x600), (0x1b, 1, 0x601), (0x1b, 1, 0x602),
             (0x3b, 4, 0x080)]
    for op, f3, f12 in unary:
        for a in operands + (1, 9, 10, 11):
            p.append(i_type(op, 20, f3, a, f12))
    for op, f3, top in ((0x13, 5, 0x18), (0x13, 1, 0x12), (0x13, 5, 0x12), (0x13, 1, 0x1a), (0x13, 1, 0x0a),
                        (0x1b, 1, 0x02)):
        for shamt in (0, 1, 31, 32, 63):
            for a in (3, 4, 7, 12):
                p.append(i_type(op, 20, f3, a, (top << 6) | shamt))
    for shamt in (0, 1, 31):
        for a in (3, 4, 7, 12):
            p.append(r_type(0x1b, 20, 5, a, shamt, 0x30))       # roriw
    yield 'b_extension', p + [0x100073], 0, MASK

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

    # Dual issue (0.5.0): a store that rewrites the next instruction in its own beat
    # must not pair with it, and the new instruction must execute; a store to another
    # beat followed by an independent ALU instruction pairs.
    new_word = i_type(0x13, 20, 0, 0, 42)
    low = new_word & 0xfff
    low = low - 4096 if low & 0x800 else low
    high = ((new_word - low) >> 12) & 0xfffff
    p = [(high << 12) | (5 << 7) | 0x37, i_type(0x13, 5, 0, 5, low),
         store(2, 0, 5, 12), i_type(0x13, 20, 0, 0, 1),        # 8: sw x5,12(x0); 12: replaced
         store(3, 0, 20, 256), i_type(0x13, 22, 0, 20, 1),      # 16: sd x20,256(x0); 20: addi x22,x20,1
         0x100073]
    yield 'dual_issue_store_pairs', p, 0, MASK

    # Second-slot loads (0.5.2). The prefix loads have filled the data cache for
    # 0x2000..0x205f (x30 = 0x2000). Two hits pair; a load whose address depends on
    # the first slot waits; a load from an address just stored must see the store.
    p = prefix() + [
        i_type(3, 20, 3, 30, 0), i_type(3, 21, 3, 30, 8),       # ld x20,0(x30); ld x21,8(x30)
        i_type(3, 22, 3, 30, 16), i_type(0x13, 23, 0, 22, 1),   # ld x22; addi x23,x22,1
        store(3, 30, 21, 24), i_type(3, 24, 3, 30, 24),         # sd x21,24(x30); ld x24,24(x30)
        i_type(0x13, 25, 0, 30, 32), i_type(3, 26, 2, 25, 4),   # addi x25,x30,32; lw x26,4(x25)
        i_type(3, 27, 0, 30, 3), i_type(3, 28, 4, 30, 5),       # lb x27,3(x30); lbu x28,5(x30)
        0x100073]
    yield 'dual_issue_loads', p, 0, MASK

    # 0.5.3: ALU + JALR and ALU + JAL pairs, and a not-taken branch first.
    p = [i_type(0x13, 1, 0, 0, 32), i_type(0x13, 5, 0, 0, 1),     # 0, 4
         i_type(0x13, 9, 0, 0, 2), i_type(0x67, 6, 0, 1, 0),      # 8: addi; 12: jalr x6,0(x1) -> 32
         0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,          # 16..28 skipped
         i_type(0x13, 7, 0, 0, 3), jal(8, 8),                     # 32: addi; 36: jal x8,+8 -> 44
         0xffffffff,                                              # 40 skipped
         branch(1, 0, 0, 8), i_type(0x13, 10, 0, 0, 4),          # 44: bne not taken; 48: addi
         i_type(0x13, 11, 0, 10, 6), 0x100073]                    # 52: depends on 48; 56: ebreak
    yield 'dual_issue_jumps', p, 0, MASK

    # 0.5.4: second-slot stores (data forwarded from the first slot) and ALU results
    # forwarded to ALU, branch and store operands in the same clock.
    p = [(2 << 12) | (1 << 7) | 0x37, i_type(0x13, 9, 0, 0, 1),    # lui x1,2; addi x9
         i_type(0x13, 2, 0, 0, 5), store(3, 1, 2, 0),               # addi x2,x0,5; sd x2,0(x1)
         i_type(0x13, 3, 0, 2, 1), i_type(0x13, 4, 0, 3, 1),        # x3 = x2+1; x4 = x3+1
         i_type(0x13, 5, 0, 4, 1), branch(0, 5, 0, 8),              # x5 = x4+1; beq x5,x0 (not taken)
         i_type(0x13, 6, 0, 5, 2), store(3, 1, 6, 8),               # x6 = x5+2; sd x6,8(x1)
         i_type(0x13, 7, 0, 0, 3), i_type(0x13, 7, 0, 7, 4),        # same destination twice
         i_type(3, 8, 3, 1, 8), 0x100073]                           # ld x8,8(x1)
    yield 'dual_issue_store_second', p, 0, MASK

    # 0.5.5 branch folding: on the second pass the targets are cached, so the jump
    # pairs with a target that reads its link (forwarded), and the taken backward
    # branch pairs with the jump at its target.
    p = [i_type(0x13, 10, 0, 0, 2), jal(1, 12),                    # 0: x10 = 2; 4: jal x1,+12 -> 16
         0xffffffff, 0xffffffff,                                  # 8, 12 skipped
         i_type(0x13, 2, 0, 1, 0), i_type(0x13, 10, 0, 10, -1),     # 16: x2 = x1; 20: x10 -= 1
         branch(1, 10, 0, -20), 0x100073]                          # 24: bne x10,x0 -> 4; 28: ebreak
    yield 'dual_issue_fold', p, 0, MASK

    # Regression for a 0.5.5 bug found by the visualizer: while 0x2c is fetched after
    # the jump at 0x40, that stale jump's target (0x2c - 0x14 = 0x18) is cached; the
    # instruction captured for the second slot must be the one at 0x30, not 0x18.
    p = [0xffffffff] * 14
    p[0x00 // 4] = jal(0, 0x18)
    p[0x18 // 4] = i_type(0x13, 5, 0, 0, 7)
    p[0x1c // 4] = jal(0, 0x24)
    p[0x2c // 4] = i_type(0x13, 6, 0, 0, 1)
    p[0x30 // 4] = i_type(0x13, 7, 0, 0, 2)
    p[0x34 // 4] = 0x100073
    p += [0xffffffff, jal(0, -0x14)]                              # 0x38; 0x40 after padding
    p.insert(14, 0xffffffff)
    yield 'fetch_after_stale_jump', p, 0, MASK

    # Overwrite an initially illegal instruction, fence, then fetch the new word.
    p = [(0x02a01 << 12) | (5 << 7) | 0x37,
         i_type(0x13, 5, 0, 5, -1517), store(2, 0, 5, 512),
         0x0000100f, jal(0, 512 - 16)]
    p += [0] * (129 - len(p)) + [0x100073]
    yield 'self_modifying_fence_i', p, 0, MASK

    for seed in (606, 707):
        rng = random.Random(seed)
        p = prefix()
        bops = [(0x33, 2, 0x10), (0x33, 7, 0x20), (0x33, 4, 0x05), (0x33, 7, 0x05), (0x33, 1, 0x30),
                (0x33, 5, 0x30), (0x33, 5, 0x24), (0x33, 1, 0x14), (0x3b, 0, 0x04), (0x3b, 4, 0x10),
                (0x3b, 5, 0x30)]
        for _ in range(600):
            rd, a, b = rng.randrange(1, 29), rng.randrange(29), rng.randrange(29)
            pick = rng.randrange(4)
            if pick == 0:
                op, f3, f7 = rng.choice(bops)
                p.append(r_type(op, rd, f3, a, b, f7))
            elif pick == 1:
                p.append(i_type(0x13, rd, rng.choice((1, 1, 5)), a,
                                rng.choice((0x600, 0x601, 0x602, 0x604, 0x605)) if rng.randrange(2) else
                                rng.choice((0x287, 0x6b8, (0x18 << 6) | rng.randrange(64)))))
            else:
                op = rng.choice((0x33, 0x3b))
                f3 = rng.choice((0, 1, 5) if op == 0x3b else tuple(range(8)))
                p.append(r_type(op, rd, f3, a, b, 32 if f3 in (0, 5) and rng.randrange(2) else 0))
        yield f'random_b_{seed}', p + [0x100073], 0, MASK

    for seed in (404, 505):
        rng = random.Random(seed)
        p = prefix()
        for _ in range(600):
            rd, a, b = rng.randrange(1, 29), rng.randrange(29), rng.randrange(29)
            if rng.randrange(3) == 0:
                op = rng.choice((0x33, 0x3b))
                f3 = rng.choice(tuple(range(8)) if op == 0x33 else (0, 4, 5, 6, 7))
                p.append(r_type(op, rd, f3, a, b, 1))
            else:
                op = rng.choice((0x33, 0x3b))
                f3 = rng.choice((0, 1, 5) if op == 0x3b else tuple(range(8)))
                p.append(r_type(op, rd, f3, a, b, 32 if f3 in (0, 5) and rng.randrange(2) else 0))
        yield f'random_m_{seed}', p + [0x100073], 0, MASK

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
        ('illegal_zero', [0]), ('illegal_funct7', [r_type(0x33, 1, 0, 2, 3, 2)]),
        ('illegal_mulhw', [r_type(0x3b, 1, 1, 2, 3, 1)]),
        ('illegal_shift', [i_type(0x13, 1, 1, 0, 0x800)]),
        ('illegal_word_shift', [i_type(0x1b, 1, 1, 0, 32)]),
        ('illegal_load', [i_type(3, 1, 7, 0, 0)]),
        ('illegal_store', [store(4, 0, 1, 0)]),
        ('illegal_branch', [branch(2, 0, 0, 4)]),
        ('illegal_jalr', [i_type(0x67, 1, 1, 0, 0)]),
        ('illegal_csr', [0x300010f3]), ('ecall', [0x73]),
        ('misaligned_jal', [jal(1, 2)]), ('misaligned_taken_branch', [branch(0, 0, 0, 2)]),
        # Dual issue (0.5.1): a branch that would trap must not pair with the ALU
        # instruction before it; one that depends on it must wait for it.
        ('misaligned_branch_after_alu', [i_type(0x13, 1, 0, 0, 5), branch(0, 0, 0, 2)]),
        ('misaligned_jalr_after_alu', [i_type(0x13, 1, 0, 0, 6), i_type(0x67, 0, 0, 1, 0)]),
        ('branch_depends_on_alu', [i_type(0x13, 1, 0, 0, 0), i_type(0x13, 1, 0, 0, 1),
                                   branch(1, 1, 0, 8), 0xffffffff]),
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
    # 0.5.4: a second-slot store that faults; the first slot retires, the store traps.
    yield 'store2_bus_fault', [(2 << 12) | (1 << 7) | 0x37, i_type(0x13, 9, 0, 0, 1),
                               i_type(0x13, 2, 0, 0, 7), store(3, 1, 2, 0), 0x100073], 3, 8192


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
    required=set('lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw ld lbu lhu lwu sb sh sw sd addi slti sltiu xori ori andi slli srli srai add sub sll slt sltu xor srl sra or and addiw slliw srliw sraiw addw subw sllw srlw sraw fence fence.i ecall ebreak mul mulh mulhsu mulhu div divu rem remu mulw divw divuw remw remuw sh1add sh2add sh3add add.uw sh1add.uw sh2add.uw sh3add.uw slli.uw andn orn xnor clz ctz cpop clzw ctzw cpopw max maxu min minu sext.b sext.h zext.h rol ror rolw rorw rori roriw orc.b rev8 bclr bclri bext bexti binv binvi bset bseti'.split())
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
