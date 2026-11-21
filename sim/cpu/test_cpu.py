"""Free CPU simulation suite: generated programs, sequential oracle, stalls/faults.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess

from reference import MASK, execute

ROOT = Path(__file__).resolve().parents[2]
# Programs written to exercise an issue slot, and the testbench counter that must be
# non-zero for them (checked with the default caches and no bus wait cycles).
# Implementations of the same architecture: the multicycle multi-issue core, the
# pipelined single-issue core (0.8.0) and the out-of-order core (0.9.0). All define
# module rv64_core.
CORES = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}
# Programs written to exercise an issue slot of the multicycle core, and the testbench
# counter that must be non-zero for them (default caches, no bus wait cycles).
SLOT_USE = {'multicycle': {'dual_issue_fold': 'slot2', 'triple_issue': 'slot3'}, 'pipe': {}, 'ooo': {}}
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

    # 0.7.0 third slot, exercised on the second pass when the lines are cached:
    # forwarding from the first slot, a third that depends on the second (must wait),
    # and three writes to one register in one clock (the last must win).
    p = [i_type(0x13, 10, 0, 0, 2),                                   # 0
         i_type(0x13, 1, 0, 0, 1), i_type(0x13, 2, 0, 1, 2), i_type(0x13, 3, 0, 1, 3),   # 4, 8, 12
         i_type(0x13, 4, 0, 0, 4), i_type(0x13, 5, 0, 4, 1), i_type(0x13, 6, 0, 5, 1),   # 16, 20, 24
         i_type(0x13, 7, 0, 0, 7), i_type(0x13, 7, 0, 0, 8), i_type(0x13, 7, 0, 0, 9),   # 28, 32, 36
         i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -40), 0x100073]  # 40, 44 -> 4, 48
    yield 'triple_issue', p, 0, MASK

    # Branches right after a pair, where a third slot would see them (a third-slot
    # branch was tried and dropped on 2026-11-21): taken backward using the first
    # slot's result, finally not taken; one that depends on the second slot.
    p = [i_type(0x13, 10, 0, 0, 3),                                   # 0: x10 = 3
         i_type(0x13, 10, 0, 10, -1), i_type(0x13, 2, 0, 2, 1),       # 4: x10 -= 1; 8: x2 += 1
         branch(1, 10, 0, -8),                                        # 12: bne x10,x0 -> 4
         i_type(0x13, 5, 0, 0, 2),                                    # 16: x5 = 2
         i_type(0x13, 8, 0, 8, 1), i_type(0x13, 6, 0, 6, 1),          # 20: x8 += 1; 24: x6 += 1
         branch(0, 6, 0, 8),                                          # 28: beq x6,x0 -> 36 (never)
         i_type(0x13, 5, 0, 5, -1), i_type(0x13, 9, 0, 9, 1),         # 32: x5 -= 1; 36: x9 += 1
         branch(1, 5, 0, -20), 0x100073]                              # 40: bne x5,x0 -> 20; 44
    yield 'triple_branch', p, 0, MASK

    # A taken branch with a misaligned target right after a pair, reached on the
    # second pass with the lines cached: it must trap precisely.
    p = [i_type(0x13, 10, 0, 0, 2),                                   # 0: x10 = 2
         i_type(0x13, 10, 0, 10, -1), i_type(0x13, 2, 0, 0, 1),       # 4: x10 -= 1; 8: x2 = 1
         branch(0, 10, 0, 6),                                         # 12: beq x10,x0 -> 18
         jal(0, -12)]                                                 # 16: j 4
    yield 'triple_branch_misaligned', p, 0, MASK

    # 0.7.1: a multiply never pairs, so a store after it must not reach the bus before
    # the multiply retires (found by mutation during the 0.7.1 review: with multiplies
    # allowed to pair, the store went out early and again after MULTIPLY).
    muls = [(0x33, 0), (0x33, 1), (0x33, 2), (0x33, 3), (0x3b, 0)]
    for pad in (0, 1):
        p = prefix() + [i_type(0x13, 0, 0, 0, 0)] * pad
        for op, f3 in muls:
            p += [r_type(op, 20, f3, 3, 7, 1), store(3, 30, 7, 96),
                  r_type(op, 21, f3, 4, 7, 1), store(2, 30, 8, 100)]
        yield f'mul_then_store_pad{pad}', p + [i_type(3, 22, 3, 30, 96), 0x100073], 0, MASK

    # 0.9.1 store-to-load forwarding in the out-of-order core: a load right after
    # stores to its beat, with full cover, partial cover, narrower and wider loads,
    # two stores where the younger wins, and a dependent store-load chain; run twice
    # so the second pass hits in the caches.
    body = [store(3, 30, 5, 0x300), i_type(3, 10, 3, 30, 0x300),                    # full
            store(0, 30, 6, 0x301), i_type(3, 11, 3, 30, 0x300),                    # byte into dword
            store(3, 30, 7, 0x308), i_type(3, 12, 2, 30, 0x30c),                    # word of a dword
            store(2, 30, 8, 0x310), i_type(3, 13, 6, 30, 0x310), i_type(3, 14, 0, 30, 0x313),
            store(1, 30, 9, 0x318), store(1, 30, 4, 0x31a), i_type(3, 15, 2, 30, 0x318),  # two halves
            store(3, 30, 3, 0x320), store(3, 30, 2, 0x320), i_type(3, 16, 3, 30, 0x320),  # younger wins
            i_type(3, 17, 3, 30, 0x300), r_type(0x33, 18, 0, 17, 17), store(3, 30, 18, 0x328),
            i_type(3, 19, 3, 30, 0x328), i_type(0x13, 20, 0, 20, -1)]
    p = prefix() + [i_type(0x13, 20, 0, 0, 2)] + body
    p += [branch(1, 20, 0, -4 * len(body)), 0x100073]
    yield 'store_load_forwarding', p, 0, MASK

    # Every multiply into x0 (no write, trace data 0), then a use of x0.
    p = prefix() + [r_type(op, 0, f3, 3, 4, 1) for op, f3 in muls] + [i_type(0x13, 5, 0, 0, 1), 0x100073]
    yield 'mul_into_x0', p, 0, MASK

    # Value prediction (out-of-order core): a load, a multiply and a divide repeat one
    # result 40 times, so a predictor becomes confident, then a store changes the
    # loaded value; the consumers must see the new results.
    body = [i_type(3, 10, 3, 30, 0x380),                 # ld x10
            r_type(0x33, 11, 0, 10, 7, 1),               # mul x11 = x10 * x7
            r_type(0x33, 14, 4, 11, 4, 1),               # div x14 = x11 / x4
            r_type(0x33, 12, 0, 11, 14),                 # add x12 = x11 + x14
            r_type(0x33, 13, 0, 13, 12),                 # add x13 += x12
            i_type(0x13, 20, 0, 20, -1),                 # x20 -= 1
            branch(1, 20, 21, 8),                        # bne x20, x21: skip the store
            store(3, 30, 13, 0x380),                     # the loaded value changes once
            branch(1, 20, 0, -32)]                       # bne x20, x0: loop
    p = prefix() + [store(3, 30, 3, 0x380), i_type(0x13, 20, 0, 0, 44), i_type(0x13, 21, 0, 0, 3)] + body
    yield 'value_change_after_repeats', p + [0x100073], 0, MASK

    # 0.11.2 fusion: a producer that overwrites its own source (addi x10, x10, 5) is fused
    # with the next instruction, which also waits for a divide; the producer retires
    # and frees its old register first, and new results reuse it before the consumer
    # executes. Loads, stores and a branch consume fused producers as well.
    body = [r_type(0x33, 6, 4, 6, 5, 1), r_type(0x33, 6, 4, 6, 5, 1),          # x6 = x6 / x5 (slow)
            i_type(0x13, 10, 0, 10, 5), r_type(0x33, 11, 0, 10, 6),            # fused: x11 = (x10 + 5) + x6
            i_type(0x13, 12, 0, 30, 0x40), store(3, 12, 11, 0),                # fused store address
            i_type(0x13, 13, 0, 30, 0x40), i_type(3, 14, 3, 13, 0),            # fused load address
            r_type(0x33, 15, 0, 15, 14)] +            [i_type(0x13, r, 0, r, 1) for r in list(range(16, 20)) + list(range(21, 29))] +            [i_type(0x13, 20, 0, 20, -1), branch(1, 20, 0, -4 * 22)]            # fused branch operand
    p = prefix() + [i_type(0x13, 5, 0, 0, 1), i_type(0x13, 6, 0, 0, 1000), i_type(0x13, 20, 0, 0, 6)] + body
    yield 'fused_pairs', p + [0x100073], 0, MASK

    # 0.11.1 memory-dependence speculation (memory agent): a store's address arrives
    # late (a fill and two divides), so a younger load to its bytes can issue first
    # and must be flushed and replayed; disjoint bytes and other beats must not be.
    def late(rd, warm=0x1f8):
        return [i_type(0x13, 27, 0, 0, 1), i_type(3, 26, 3, 30, warm), r_type(0x33, rd, 0, 30, 26),
                r_type(0x33, rd, 4, rd, 27, 1), r_type(0x33, rd, 4, rd, 27, 1)]
    add_ = lambda rd, a, b: r_type(0x33, rd, 0, a, b)
    yield 'mdp_full', prefix() + late(21, 0x100) + [store(3, 21, 7, 0x100), i_type(3, 22, 3, 30, 0x100),
                                                     add_(23, 22, 22), store(3, 30, 23, 0x108), 0x100073], 0, MASK
    yield 'mdp_partial', prefix() + late(21, 0x110) + [store(2, 21, 7, 0x114), i_type(3, 22, 3, 30, 0x110),
                                                        add_(23, 22, 22), store(3, 30, 23, 0x118), 0x100073], 0, MASK
    yield 'mdp_same_beat_disjoint', prefix() + late(21, 0x120) + [store(2, 21, 7, 0x124), i_type(3, 22, 2, 30, 0x120),
                                                                   add_(23, 22, 22), store(3, 30, 23, 0x128), 0x100073], 0, MASK
    body = late(21, 0x130) + [add_(25, 25, 8), store(3, 21, 25, 0x130), i_type(3, 22, 3, 30, 0x130), add_(23, 23, 22)]
    yield 'mdp_loop', prefix() + [i_type(0x13, 24, 0, 0, 4), i_type(0x13, 25, 0, 0, 0), i_type(0x13, 23, 0, 0, 0)] + body +         [i_type(0x13, 24, 0, 24, -1), branch(1, 24, 0, -4 * (len(body) + 1)), store(3, 30, 23, 0x138), 0x100073], 0, MASK
    yield 'mdp_early_forward', prefix() + [store(3, 30, 8, 0x140)] + late(21) + [store(3, 21, 9, 0x140), i_type(3, 22, 3, 30, 0x140),
                                                                              add_(23, 22, 22), store(3, 30, 23, 0x148), 0x100073], 0, MASK
    yield 'mdp_other_beat', prefix() + late(21, 0x158) + [store(3, 21, 7, 0x150), i_type(3, 22, 3, 30, 0x158),
                                                           add_(23, 22, 22), store(3, 30, 23, 0x160), 0x100073], 0, MASK

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
    # 0.11.1 (from the second Codex review): two stores held behind a divide chain, so
    # the out-of-order core pairs them on the bus; a fault on the first half retires
    # neither, a fault on the second retires the first and the ALU between them.
    held = [(2 << 12) | (1 << 7) | 0x37, i_type(0x13, 5, 0, 0, 7),
            r_type(0x33, 6, 4, 5, 5, 1), r_type(0x33, 6, 4, 6, 5, 1), r_type(0x33, 6, 4, 6, 5, 1)]
    pair = [i_type(0x13, 2, 0, 0, 0x55), store(3, 1, 2, 0), i_type(0x13, 3, 0, 0, 0x66), store(3, 1, 3, 8)]
    yield 'paired_store_fault_first', held + pair + [0x100073], 3, 8192
    yield 'paired_store_fault_second', held + pair + [0x100073], 3, 8200
    yield 'paired_store_overlap', held + [i_type(0x13, 2, 0, 0, 0x55), store(2, 1, 2, 16), i_type(0x13, 3, 0, 0, 0x66),
                                          store(0, 1, 3, 17), i_type(3, 4, 3, 1, 16), 0x100073], 0, MASK
    # A load fully covered by an older store still needs its beat to be readable.
    yield 'forwarded_load_read_fault', held + [i_type(0x13, 2, 0, 0, 0x55), store(3, 1, 2, 0),
                                               i_type(3, 4, 3, 1, 0), 0x100073], 2, 8192

    # Memory hand-off 6 (paste into cases() of sim/cpu/test_cpu.py; uses its prefix/i_type/store/
    # branch/r_type helpers). x30 = 0x2000, x2 = 1 after the prefix.
    #
    # A store before a load and a store behind it, in a byte loop whose load value is trained
    # by value prediction (zero) and then changes. With small caches the store-write scan used
    # to choose the store behind the value-mispredicted load, which retirement then discarded
    # ("store write without its store retiring" / "unstable stalled request" with bus waits,
    # 0.12.0 with 2-line caches; also middle's fold_byte_loop).
    for n, chg in ((12, 10), (16, 12)):
        loop = [store(0, 22, 23, 0x40), i_type(3, 24, 4, 21, 0), store(0, 22, 24, 0), i_type(0x13, 21, 0, 21, 1),
                i_type(0x13, 22, 0, 22, 1), i_type(0x13, 23, 0, 23, -1), branch(1, 23, 0, -24)]
        p = prefix() + [store(0, 30, 2, 0x100 + chg), i_type(0x13, 21, 0, 30, 0x100),
                        i_type(0x13, 22, 0, 30, 0x200), i_type(0x13, 23, 0, 0, n)] + loop
        p += [i_type(3, 25, 3, 30, 0x208), 0x100073]
        yield f'vp_store_scan_{n}', p, 0, MASK
    # An older store with a late address and a younger store with an early address write the
    # same bytes; the load forwards from the younger one and must give its value (correctness;
    # 0.12.0 also flushed it needlessly and set its load-wait bit).
    late = [i_type(0x13, 27, 0, 0, 1), i_type(3, 26, 3, 30, 0x178), r_type(0x33, 21, 0, 30, 26),
            r_type(0x33, 21, 4, 21, 27, 1), r_type(0x33, 21, 4, 21, 27, 1)]
    p = prefix() + [i_type(3, 25, 3, 30, 0x170)] + late + [
        store(3, 21, 7, 0x170), store(3, 30, 8, 0x170), i_type(3, 22, 3, 30, 0x170),
        r_type(0x33, 23, 0, 22, 22), store(3, 30, 23, 0x180), 0x100073]
    yield 'mdp_forward_from_younger', p, 0, MASK
    # Frontend (council, after 0.12.0): several calls and returns and up to 4 taken
    # transfers in one fetch group, on later passes with the lines cached. Nested calls
    # through ra and t0 (x5); a return to an address pushed earlier in the same group;
    # a chain of jumps; a taken branch back.
    p = [i_type(0x13, 10, 0, 0, 4),                                   # 0: x10 = 4
         jal(1, 36),                                                  # 4: call f (40)
         jal(1, 40),                                                  # 8: call g (48)
         jal(1, 28),                                                  # 12: call f (40)
         jal(5, 52),                                                  # 16: call h via t0 (68)
         jal(0, 60),                                                  # 20: j 80
         i_type(0x13, 10, 0, 10, -1),                                 # 24: x10 -= 1
         branch(1, 10, 0, -24),                                       # 28: bne x10,x0 -> 4
         0x100073, 0xffffffff,                                        # 32: ebreak; 36
         i_type(0x13, 20, 0, 20, 1), i_type(0x67, 0, 0, 1, 0),        # 40: f: x20 += 1; 44: ret
         i_type(0x13, 5, 0, 1, 0), jal(1, -12),                       # 48: g: x5 = ra; 52: call f
         i_type(0x13, 21, 0, 21, 1), i_type(0x67, 0, 0, 5, 0),        # 56: x21 += 1; 60: jr t0 -> 12
         0xffffffff,                                                  # 64
         i_type(0x13, 22, 0, 22, 1), i_type(0x67, 0, 0, 5, 0),        # 68: h: x22 += 1; 72: jr t0 -> 20
         0xffffffff,                                                  # 76
         jal(0, 8), 0xffffffff, jal(0, 8), 0xffffffff,                # 80: j 88; 88: j 96
         i_type(0x13, 23, 0, 23, 1), branch(0, 0, 0, -76)]            # 96: x23 += 1; 100: beq -> 24
    yield 'fetch_many_calls', p, 0, MASK

    # Recursion 20 deep (deeper than the 16-entry return stack, so it wraps), three
    # times: several calls, or several returns, per fetch group.
    p = [(3 << 12) | (2 << 7) | 0x37, i_type(0x13, 12, 0, 0, 3),     # 0: sp = 0x3000; 4: x12 = 3
         i_type(0x13, 11, 0, 0, 20), jal(1, 20),                      # 8: x11 = 20; 12: call r (32)
         i_type(0x13, 12, 0, 12, -1), branch(1, 12, 0, -12),          # 16: x12 -= 1; 20: bne -> 8
         0x100073, 0xffffffff,                                        # 24: ebreak; 28
         i_type(0x13, 11, 0, 11, -1), branch(0, 11, 0, 24),           # 32: r: x11 -= 1; 36: beq x11,x0 -> 60
         i_type(0x13, 2, 0, 2, -8), store(3, 2, 1, 0),                # 40: sp -= 8; 44: sd ra,0(sp)
         jal(1, -16), i_type(3, 1, 3, 2, 0),                          # 48: call r; 52: ld ra,0(sp)
         i_type(0x13, 2, 0, 2, 8),                                    # 56: sp += 8
         i_type(0x13, 20, 0, 20, 1), i_type(0x67, 0, 0, 1, 0)]        # 60: x20 += 1; 64: ret
    yield 'fetch_deep_recursion', p, 0, MASK
    # Folding at rename (council middle, after 0.12.0): addi/mv/li, lui, auipc, jal and
    # constant-base jalr finish at rename; rd maps to a (physical register, offset) pair.
    # An eliminated mv/addi shares its source's physical register, which must stay
    # allocated after the source architectural register is overwritten and retired.
    slow = [i_type(0x13, 5, 0, 0, 1), r_type(0x33, 6, 4, 7, 5, 1), r_type(0x33, 6, 4, 6, 5, 1)]   # x6 = x7 / 1 / 1 (late)
    body = ([i_type(0x13, 11, 0, 6, 0), i_type(0x13, 12, 0, 11, 7), i_type(0x13, 13, 0, 12, -3),   # x11 = x6; x12 = x11+7; x13 = x12-3
            r_type(0x33, 6, 0, 6, 6)] +                                                         # overwrite the shared source
           [r_type(0x33, 14, 0, 14, 8) for _ in range(40)] +                                    # reuse freed registers
           [r_type(0x33, 15, 0, 11, 12), r_type(0x33, 16, 0, 13, 6),
            store(3, 30, 11, 0x300), store(3, 30, 13, 0x308), i_type(3, 17, 3, 30, 0x308),       # store data with an offset
            store(0, 30, 12, 0x311), i_type(3, 18, 3, 30, 0x310),                                # forwarded byte with an offset
            i_type(0x13, 6, 0, 13, 0), i_type(0x13, 11, 0, 11, 1), r_type(0x33, 19, 0, 6, 11),
            0x100073])
    yield 'fold_shared_register', prefix() + slow + body, 0, MASK

    # A strcpy-like byte loop: pointer and counter chains folded over many iterations,
    # a data-dependent branch inside (mispredicts restore folded map entries), then the
    # copy is read back.
    loop = [i_type(3, 24, 4, 21, 0), i_type(0x13, 21, 0, 21, 1), store(0, 22, 24, 0),
            i_type(0x13, 22, 0, 22, 1), branch(0, 24, 0, 8), i_type(0x13, 28, 0, 28, 1),
            i_type(0x13, 23, 0, 23, -1), branch(1, 23, 0, -28)]
    p = prefix() + [i_type(0x13, 21, 0, 30, 0), i_type(0x13, 22, 0, 30, 0x400), i_type(0x13, 23, 0, 0, 90)] + loop
    p += [i_type(3, 25, 3, 30, 0x400), i_type(3, 26, 3, 30, 0x408), i_type(3, 27, 3, 30, 0x450),
          r_type(0x33, 29, 0, 21, 22), 0x100073]
    yield 'fold_byte_loop', p, 0, MASK

    # Calls through auipc+jalr (constant base, finished at rename), returns through a
    # folded link, an absolute jalr from x0, and the links used as data.
    base = len(prefix()) * 4
    p = prefix() + [0x00000097, i_type(0x67, 1, 0, 1, 28),          # +0: auipc ra,0; +4: jalr ra,28(ra) -> +28
                    0x00000297, i_type(0x67, 5, 0, 5, 28),          # +8: auipc t0,0; +12: jalr t0,28(t0) -> +36
                    i_type(0x67, 0, 0, 0, base + 44),               # +16: jalr x0, abs(+44)
                    0xffffffff, 0xffffffff,                         # +20, +24
                    i_type(0x13, 20, 0, 20, 1), i_type(0x67, 0, 0, 1, 0),   # +28: f: x20 += 1; ret -> +8
                    i_type(0x13, 21, 0, 21, 1), i_type(0x67, 0, 0, 5, 0),   # +36: h: x21 += 1; jr t0 -> +16
                    r_type(0x33, 22, 0, 1, 5), store(3, 30, 1, 0x320),      # +44: links as data
                    (0x80000 << 12) | (23 << 7) | 0x37, i_type(0x13, 23, 0, 23, -1),   # lui (negative), addi
                    i_type(0x13, 24, 0, 0, -1), i_type(0x13, 24, 0, 24, 1),            # -1 + 1 wraps to 0
                    branch(1, 24, 0, 8), r_type(0x33, 25, 0, 23, 24), 0x100073]
    yield 'fold_calls_constants', p, 0, MASK

    # Branch and ALU operands with offsets on a late register.
    p = prefix() + slow + [i_type(0x13, 9, 0, 6, 1), i_type(0x13, 10, 0, 6, 1), branch(0, 9, 10, 8), 0xffffffff,
                           i_type(0x13, 9, 0, 9, -1), branch(4, 9, 10, 8), 0xffffffff,
                           r_type(0x33, 11, 0, 9, 10), r_type(0x33, 12, 1, 10, 5), i_type(0x13, 13, 1, 10, 3),
                           0x100073]
    yield 'fold_branch_operands', p, 0, MASK
    # Memory hand-off 4 (paste into cases() of sim/cpu/test_cpu.py; uses its prefix/i_type/store
    # helpers). Four stores in a row go out on one write request (third and fourth on mem_x*).
    # x30 = 0x2000 and x3..x6 hold constants after the prefix.
    four = [store(3, 30, 3, 0x100), store(3, 30, 4, 0x108), store(3, 30, 5, 0x110), store(3, 30, 6, 0x118)]
    check = [i_type(3, 20, 3, 30, 0x100), i_type(3, 21, 3, 30, 0x118), 0x100073]
    yield 'x4_four_beats', prefix() + four + check, 0, MASK
    # A store bus fault on the second, third or fourth store of the group: the earlier stores
    # are written and retire, the faulting one traps precisely, the later ones are not written.
    yield 'x4_fault_second', prefix() + four + check, 3, 0x2108
    yield 'x4_fault_third', prefix() + four + check, 3, 0x2110
    yield 'x4_fault_fourth', prefix() + four + check, 3, 0x2118
    # Four byte stores to one beat and two words to the next, read back.
    p = prefix() + [store(0, 30, 3, 0x120), store(0, 30, 4, 0x121), store(0, 30, 5, 0x122), store(0, 30, 7, 0x127),
                    store(2, 30, 8, 0x128), store(2, 30, 9, 0x12c), i_type(3, 20, 3, 30, 0x120),
                    i_type(3, 21, 3, 30, 0x128), 0x100073]
    yield 'x4_same_beat', p, 0, MASK
    # The fourth store of a group rewrites an instruction two slots after the group
    # (addi x22,x0,1 becomes addi x22,x0,7); the new instruction must execute.
    patch = [(0x701 << 12) | (21 << 7) | 0x37, i_type(0x13, 21, 0, 21, -0x4ed)]   # x21 = 0x00700b13
    n0 = len(prefix()) + len(patch)
    body = [(19 << 7) | 0x17, store(3, 30, 3, 0x140), store(3, 30, 4, 0x148), store(3, 30, 5, 0x150)]
    body.append(store(2, 19, 21, 4 * (len(body) + 2)))
    body += [i_type(0x13, 23, 0, 0, 3), i_type(0x13, 22, 0, 0, 1), store(3, 30, 22, 0x158), 0x100073]
    yield 'x4_store_patches_code', prefix() + patch + body, 0, MASK
    add_ = lambda rd, a, b: r_type(0x33, rd, 0, a, b)
    # More load and store-address ports (N_LD / N_ST): a block of independent loads and
    # stores to the same and neighbouring beats, so several store addresses and loads
    # execute in one clock; loads after stores to their bytes must see the stores.
    body = []
    for n in range(6):
        body += [store(3, 30, 10 + n, 0x240 + 8 * n), i_type(3, 16 + n, 3, 30, 0x240 + 8 * n),
                 store(0, 30, 3, 0x241 + 8 * n), i_type(3, 22, 4, 30, 0x240 + 8 * n), add_(28, 28, 22)]
    body += [add_(27, 16, 17), add_(27, 27, 21), i_type(0x13, 29, 0, 29, -1)]
    body.append(branch(1, 29, 0, -4 * len(body)))
    p = prefix() + [i_type(0x13, 29, 0, 0, 3)] + body + [store(3, 30, 27, 0x280), store(3, 30, 28, 0x288), 0x100073]
    yield 'many_memory_ports', p, 0, MASK

    # Bus faults inside a full group of memory operations (4 load ports, 3 store-address
    # ports): four independent loads where the third or fourth faults, three stores where
    # the second faults, and loads and stores mixed with the last load faulting.
    lui1 = (2 << 12) | (1 << 7) | 0x37                                   # x1 = 0x2000
    loads4 = [i_type(3, 2, 3, 1, 0), i_type(3, 3, 3, 1, 8), i_type(3, 4, 3, 1, 16), i_type(3, 5, 3, 1, 24)]
    yield 'ports_load_fault_third', [lui1, i_type(0x13, 9, 0, 0, 1)] + loads4 + [0x100073], 2, 8208
    yield 'ports_load_fault_fourth', [lui1, i_type(0x13, 9, 0, 0, 1)] + loads4 + [0x100073], 2, 8216
    stores3 = [i_type(0x13, 6, 0, 0, 0x11), store(3, 1, 6, 0), store(3, 1, 6, 8), store(3, 1, 6, 16)]
    yield 'ports_store_fault_second', [lui1] + stores3 + [0x100073], 3, 8200
    mixed = [i_type(0x13, 6, 0, 0, 0x22), store(3, 1, 6, 32), i_type(3, 2, 3, 1, 40), store(3, 1, 6, 48),
             i_type(3, 3, 3, 1, 32), store(2, 1, 6, 56), i_type(3, 4, 3, 1, 48), i_type(3, 5, 3, 1, 64)]
    yield 'ports_mixed_fault_last_load', [lui1] + mixed + [0x100073], 2, 8256

def command(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='Optional raw firmware binary for an additional differential test')
    parser.add_argument('--icache-beats', type=int, help='Override the core instruction-cache size (power of two >= 2)')
    parser.add_argument('--dcache-beats', type=int, help='Override the core data-cache size (power of two >= 2)')
    parser.add_argument('--core', choices=sorted(CORES), default='multicycle', help='Core implementation to test')
    parser.add_argument('--core-source', type=Path,
                        help="Test this file instead of the core's file in rtl/cpu (a candidate kept elsewhere)")
    parser.add_argument('--out-dir', type=Path,
                        help='Build and report folder (default build/cpu), so candidates can be tested side by side')
    args = parser.parse_args()
    if args.out_dir: OUT = args.out_dir.resolve()
    cache = [f'-Ptb_core.ICACHE_BEATS={args.icache_beats}'] if args.icache_beats else []
    cache += [f'-Ptb_core.DCACHE_BEATS={args.dcache_beats}'] if args.dcache_beats else []
    if not shutil.which('iverilog') or not shutil.which('vvp'):
        parser.error('iverilog and vvp are required; use the documented Ubuntu/WSL launcher')
    OUT.mkdir(parents=True, exist_ok=True)
    executable = OUT / 'cpu.vvp'
    core_src = args.core_source.resolve() if args.core_source else ROOT / CORES[args.core]
    wide = ['-DWIDE_TRACE'] if args.core == 'ooo' else []  # 0.10.0: up to 8 retirements per clock
    command(['iverilog', '-g2012', '-Wall', *wide, '-s', 'tb_core', *cache, '-o', executable,
             core_src, ROOT / 'sim/cpu/tb_core.sv'])
    command(['iverilog', '-g2012', '-Wall', *wide, '-s', 'rv64_bram_soc', '-o', OUT/'soc.vvp',
             core_src, ROOT/'rtl/cpu/rv64_bram_soc.sv'])
    command(['iverilog','-g2012','-Wall','-s','tb_reset','-o',OUT/'reset.vvp',
             core_src,ROOT/'sim/cpu/tb_reset.sv'])
    reset_result=command(['vvp',OUT/'reset.vvp']).strip()
    command(['iverilog','-g2012','-Wall',*wide,'-s','tb_soc','-o',OUT/'bram-soc.vvp',
             core_src,ROOT/'rtl/cpu/rv64_bram_soc.sv',ROOT/'sim/cpu/tb_soc.sv'])
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
            # Structural coverage: these programs exist to exercise an issue slot, so
            # check that the slot was used (default caches, where the lines stay cached).
            if args.icache_beats is None and stalls == 0 and name in SLOT_USE[args.core]:
                field = SLOT_USE[args.core][name]
                used = re.search(field + r'=(\d+)', output)
                if not used or int(used[1]) == 0:
                    raise AssertionError(f'{name}: expected {field} > 0, simulator said {output.strip()}')
            records.append({'case':name,'max_wait_cycles':stalls,'events':len(actual),'result':'PASS','simulator_summary':output.strip()})
    required=set('lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw ld lbu lhu lwu sb sh sw sd addi slti sltiu xori ori andi slli srli srai add sub sll slt sltu xor srl sra or and addiw slliw srliw sraiw addw subw sllw srlw sraw fence fence.i ecall ebreak mul mulh mulhsu mulhu div divu rem remu mulw divw divuw remw remuw sh1add sh2add sh3add add.uw sh1add.uw sh2add.uw sh3add.uw slli.uw andn orn xnor clz ctz cpop clzw ctzw cpopw max maxu min minu sext.b sext.h zext.h rol ror rolw rorw rori roriw orc.b rev8 bclr bclri bext bexti binv binvi bset bseti'.split())
    missing=required-coverage
    if missing: raise AssertionError('Missing instruction coverage: '+str(sorted(missing)))
    for branch_name in ('beq','bne','blt','bge','bltu','bgeu'):
        for outcome in ('taken','not_taken'):
            if branch_name+':'+outcome not in coverage: raise AssertionError('Missing branch outcome')
    report={'status':'PASS','cases':len(workloads),'runs':len(records),'instruction_names_covered':len(required),
            'core':args.core,'core_source':str(args.core_source) if args.core_source else CORES[args.core],
            'icache_beats':args.icache_beats or 'tb_core default (512)','dcache_beats':args.dcache_beats or 'tb_core default (512)',
            'reset_test':reset_result,'bram_soc_tests':soc_results,
            'coverage':sorted(coverage),'validation_scope':'local directed/random differential simulation; no official ISA certification or synthesis',
            'rtl_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'rtl/cpu').glob('*.sv'))},
            'simulated_core_sha256':hashlib.sha256(core_src.read_bytes()).hexdigest(),
            'simulator':command(['iverilog','-V']).splitlines()[0],'results':records}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS ({args.core} core): {len(workloads)} programs x 3 wait patterns = {len(records)} runs; {len(required)} instruction names covered.')
    print('Includes precise traps, invalid encodings, bus faults, x0, all memory lanes, branch outcomes and ordered retirement.')


if __name__=='__main__': main()
