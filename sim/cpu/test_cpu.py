"""Free CPU simulation suite: generated programs, sequential oracle, stalls/faults.

--sim verilator builds and runs the same testbenches with Verilator instead of
Icarus Verilog (the default and the cross-check); see simulator.py.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import re
import subprocess

from reference import MASK, execute
import simulator

ROOT = Path(__file__).resolve().parents[2]
# Programs written to exercise an issue slot, and the testbench counter that must be
# non-zero for them (checked with the default caches and no bus wait cycles).
# Implementations of the same architecture: the multicycle multi-issue core, the
# pipelined single-issue core (0.8.0) and the out-of-order core (0.9.0). All define
# module rv64_core.
CORES = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}
# Programs written to exercise an issue slot of the multicycle core, and the testbench
# counter that must be non-zero for them (default caches, no bus wait cycles).
SLOT_USE = {'multicycle': {'dual_issue_fold': 'slot2', 'triple_issue': 'slot3'}, 'pipe': {},
            # Out-of-order core: multi-store writes really use lanes 2-4 (lane cover, 0.14.x).
            'ooo': {'x4_four_beats': 'lane4', 'x4_fault_second': 'fault_lane2', 'x4_fault_third': 'fault_lane3',
                    'x4_fault_fourth': 'fault_lane4'}}
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


def ras_wrong_path_call_program():
    """Frontend hand-off 8 (Codex 1739-3): wrong-path return then call; see the case."""
    def slli(rd, rs, sh): return i_type(0x13, rd, 1, rs, sh)
    def srli(rd, rs, sh): return i_type(0x13, rd, 5, rs, sh)
    def xor(rd, a, b): return r_type(0x33, rd, 4, a, b)
    def div(rd, a, b): return r_type(0x33, rd, 4, a, b, 1)
    def sd(rs2, base, off): return ((off >> 5) << 25) | rs2 << 20 | base << 15 | 3 << 12 | (off & 31) << 7 | 0x23
    PAD = 640    # more than ROB + fetch queue: the wrong path cannot reach the next call of f
    f = 48 + 4 * PAD + 16                                              # address of f
    g = f + 48
    p = [i_type(0x13, 10, 0, 0, 12),                                   # 0: x10 = 12 iterations (24 until 2026-11-21: too slow under Icarus)
         i_type(0x13, 11, 0, 0, 0x5a5),                                # 4: x11 = seed
         (3 << 12) | (2 << 7) | 0x37,                                  # 8: x2 = 0x3000 (lui; was x12 = 1)
         slli(13, 11, 13), xor(11, 11, 13),                            # 12: xorshift64
         srli(13, 11, 7), xor(11, 11, 13),                             # 20
         slli(13, 11, 17), xor(11, 11, 13),                            # 28
         jal(1, f - 36),                                               # 36: call f
         jal(1, g - 40),                                               # 40: call g
         i_type(0x13, 10, 0, 10, -1)]                                  # 44: x10 -= 1
    p += [0x00000013] * PAD                                            # 48: nops
    p += [branch(1, 10, 0, 12 - (48 + 4 * PAD)),                       # bne x10 -> 12
          0x100073, 0x00000013, 0x00000013]                            # ebreak; pad
    assert 4 * len(p) == f
    # f keeps ra in memory, so its returns read ra from a load (as compiled code does) and
    # are predicted and checked at execute, not resolved at rename from a constant ra.
    p += [sd(1, 2, 0), i_type(0x13, 12, 0, 0, 1),                      # f: sd ra,0(x2); x12 = 1
          div(6, 11, 12), div(6, 6, 12), i_type(0x13, 6, 7, 6, 1),     # x6 = x11 / 1 / 1; x6 &= 1
          branch(0, 6, 0, 16),                                         # f+20: beq x6, x0 -> f+36
          i_type(0x13, 20, 0, 20, 1), i_type(3, 1, 3, 2, 0),           # x20 += 1; ld ra,0(x2)
          i_type(0x67, 0, 0, 1, 0),                                    # f+32: ret
          i_type(0x13, 21, 0, 21, 1), i_type(3, 1, 3, 2, 0),           # f+36: x21 += 1; ld ra,0(x2)
          i_type(0x67, 0, 0, 1, 0)]                                    # f+44: ret
    assert 4 * len(p) == g
    p += [i_type(0x13, 22, 0, 22, 1), i_type(0x67, 0, 0, 1, 0)]        # g: x22 += 1; ret
    return p


def ret_displacement_program():
    """Frontend hand-off 9 (Codex 1624-3): returns with a non-zero displacement."""
    def sd(rs2, base, off): return ((off >> 5) << 25) | rs2 << 20 | base << 15 | 3 << 12 | (off & 31) << 7 | 0x23
    p = [i_type(0x13, 10, 0, 0, 30),                                   # 0: x10 = 30 iterations
         (3 << 12) | (2 << 7) | 0x37,                                  # 4: x2 = 0x3000
         jal(1, 24),                                                   # 8: call f (32)
         0x00000000,                                                   # 12: data word skipped by the return
         i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -12),           # 16: x10 -= 1; 20: bne -> 8
         0x100073, jal(0, 0)]                                          # 24: ebreak; 28: j 28 (fetch past
                                                                       # the ebreak must not fall into f)
    p += [sd(1, 2, 0), i_type(0x13, 20, 0, 20, 1),                     # 32: f: sd ra,0(x2); x20 += 1
          i_type(3, 1, 3, 2, 0), i_type(0x67, 0, 0, 1, 4)]             # 40: ld ra,0(x2); 44: jalr x0, 4(ra)
    return p


# Frontend hand-off 11 (fetch in the branch-recovery clock): programs that mispredict often.
def rc_fetch_cases(i_type, r_type, store, branch, jal, MASK):
    slli = lambda rd, rs, sh: i_type(0x13, rd, 1, rs, sh)
    srli = lambda rd, rs, sh: i_type(0x13, rd, 5, rs, sh)
    xor = lambda rd, a, b: r_type(0x33, rd, 4, a, b)
    div = lambda rd, a, b: r_type(0x33, rd, 4, a, b, 1)
    xs = [slli(13, 11, 13), xor(11, 11, 13), srli(13, 11, 7), xor(11, 11, 13), slli(13, 11, 17), xor(11, 11, 13)]
    # The mispredicted branch's taken target beat starts with a call (pushes the return stack
    # in the recovery clock) whose callee returns; the not-taken side is ordinary code.
    p = [i_type(0x13, 10, 0, 0, 30), i_type(0x13, 11, 0, 0, 0x2b7), i_type(0x13, 12, 0, 0, 1)]   # 0..8
    p += xs                                                                     # 12..32: xorshift
    p += [div(6, 11, 12), i_type(0x13, 6, 7, 6, 1),                             # 36: x6 = x11 & 1 (late)
          branch(1, 6, 0, 16),                                                  # 44: bne x6, x0 -> 60
          i_type(0x13, 20, 0, 20, 1), jal(0, 16), 0x00000013,                   # 48: x20 += 1; 52: j 68; 56
          jal(1, 32), i_type(0x13, 21, 0, 21, 1),                               # 60: call g (92); 64: x21 += 1
          i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -60),                   # 68: x10 -= 1; 72: bne -> 12
          0x100073, jal(0, 0), 0x00000013, 0x00000013,                          # 76: ebreak; 80: j .; 84, 88
          i_type(0x13, 22, 0, 22, 3), i_type(0x67, 0, 0, 1, 0)]                 # 92: g: x22 += 3; 96: ret
    assert 4 * p.index(jal(1, 32)) == 60 and len(p) == 25
    yield 'rc_fetch_call_target', p, 0, MASK
    # The mispredicted branch's target is the second word of a beat, which holds a taken
    # backward branch: the recovery-clock fetch takes one instruction and must stop at the beat
    # boundary; the target of that branch is fetched the next clock.
    p = [i_type(0x13, 10, 0, 0, 30), i_type(0x13, 11, 0, 0, 0x1d3), i_type(0x13, 12, 0, 0, 1)]   # 0..8
    p += xs                                                                     # 12..32
    p += [div(6, 11, 12), i_type(0x13, 6, 7, 6, 2),                             # 36: x6 = x11 & 2 (late)
          branch(0, 6, 0, 24),                                                  # 44: beq x6, x0 -> 68
          i_type(0x13, 20, 0, 20, 1), i_type(0x13, 20, 0, 20, 1),               # 48, 52
          i_type(0x13, 20, 0, 20, 1), i_type(0x13, 20, 0, 20, 1),               # 56, 60
          0x00000013,                                                           # 64
          i_type(0x13, 10, 0, 10, -1),                                          # 68: x10 -= 1 (odd word)
          branch(1, 10, 0, -60),                                                # 72: bne -> 12
          0x100073, jal(0, 0)]                                                  # 76: ebreak; 80: j .
    yield 'rc_fetch_odd_word_target', p, 0, MASK


# Frontend hand-off 12 (global-history predictor): correlated and PC+4 branches, a full training queue before a store.
def gh_predictor_cases(i_type, r_type, store, branch, jal, MASK):
    slli = lambda rd, rs, sh: i_type(0x13, rd, 1, rs, sh)
    srli = lambda rd, rs, sh: i_type(0x13, rd, 5, rs, sh)
    xor = lambda rd, a, b: r_type(0x33, rd, 4, a, b)
    div = lambda rd, a, b: r_type(0x33, rd, 4, a, b, 1)
    head = [i_type(0x13, 10, 0, 0, 200), i_type(0x13, 11, 0, 0, 0x5a5), i_type(0x13, 12, 0, 0, 1),   # 0..8
            slli(13, 11, 13), xor(11, 11, 13), srli(13, 11, 7), xor(11, 11, 13),                     # 12: xorshift64
            slli(13, 11, 17), xor(11, 11, 13)]
    # C is always at 52; the loop branch at 64 goes back to 12.
    p = head + [div(6, 11, 12), i_type(0x13, 6, 7, 6, 1),               # 36: x6 = (x11 / 1) & 1
                branch(0, 6, 0, 8), i_type(0x13, 20, 0, 20, 1),         # 44: R: beq x6,x0 -> 52
                branch(0, 6, 0, 8), i_type(0x13, 21, 0, 21, 1),         # 52: C: beq x6,x0 -> 60
                i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -52),     # 60, 64
                0x100073, jal(0, 0)]                                    # 68: ebreak; 72: j .
    yield 'gh_correlated', p, 0, MASK
    p = head + [div(6, 11, 12), i_type(0x13, 6, 7, 6, 1),               # 36: x6 = (x11 / 1) & 1
                branch(0, 6, 0, 4), i_type(0x13, 20, 0, 20, 1),         # 44: B4: beq x6,x0 -> 48 (= PC+4)
                branch(0, 6, 0, 8), i_type(0x13, 21, 0, 21, 1),         # 52: C: beq x6,x0 -> 60
                i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -52),     # 60, 64
                0x100073, jal(0, 0)]
    yield 'gh_plus4_exec', p, 0, MASK
    p = head + [i_type(0x13, 7, 7, 10, 1), div(6, 10, 12),             # 36: x7 = x10 & 1 (rename constant); x6 = x10 / 1
                branch(0, 7, 0, 4), i_type(0x13, 6, 7, 6, 1),           # 44: B4: beq x7,x0 -> 48 (resolved at rename); x6 &= 1
                branch(0, 6, 0, 8), i_type(0x13, 21, 0, 21, 1),         # 52: C: beq x6,x0 -> 60
                i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -52),     # 60, 64
                0x100073, jal(0, 0)]
    yield 'gh_plus4_rename', p, 0, MASK
    # Training queue full (rev. 3, Codex review 2): three divides hold the ROB head while many
    # conditional branches decided at rename (bne x0,x0: never taken) and stores pile up
    # behind it. When the head retires, 32 instructions retire at once and fill the 32-entry
    # queue; the next clock only 4 entries drain, so retirement stops at the fifth branch. The
    # store-write scan must stop there too: a store written but not retired is a contract
    # violation (tb_core: "store write without its store retiring on the same clock").
    # Two passes: the first brings the code into the instruction cache, so in the second fetch
    # runs far ahead of the divides at the head.
    p = [i_type(0x13, 5, 0, 0, 7), i_type(0x13, 6, 0, 0, 1), (3 << 12) | (29 << 7) | 0x37,   # x5 = 7; x6 = 1; x29 = 0x3000
         i_type(0x13, 10, 0, 0, 2)]                                    # 12: x10 = 2 passes
    top = len(p)
    p += [div(7, 5, 6)] * 6                                           # 16: six divides at the head
    for k in range(6):
        p += [branch(1, 0, 0, 4)] * 40 + [store(3, 29, 5, 8 * k)]     # 40 never-taken branches, then sd x5, 8k(x29)
    p += [store(3, 29, 7, 0x100), i_type(0x13, 10, 0, 10, -1)]        # sd x7; x10 -= 1
    p += [branch(1, 10, 0, 4 * (top - len(p))), 0x100073]             # bne x10 -> top; ebreak
    yield 'tq_full_store', p, 0, MASK


# Frontend hand-off 14 (Codex 1724-2): a stale BTB entry after FENCE.I must not redirect a non-branch.
def btb_stale_cases(i_type, r_type, store, branch, jal, MASK):
    p = [i_type(0x13, 10, 0, 0, 3), i_type(0x13, 11, 0, 0, 0),         # 0: x10 = 3; 4: x11 = 0 (pass)
         branch(0, 0, 0, 8), 0x00000013,                                # 8: L: beq x0,x0 -> 16; 12: nop
         i_type(0x13, 10, 0, 10, -1), branch(1, 10, 0, -12),            # 16: x10 -= 1; 20: bne -> 8
         branch(1, 11, 0, 28),                                          # 24: bne x11,x0 -> 52 (done)
         i_type(0x13, 5, 0, 0, 0x13), store(2, 0, 5, 8),                # 28: x5 = nop; 32: sw x5, 8(x0)
         0x0000100f,                                                    # 36: fence.i
         i_type(0x13, 10, 0, 0, 20), i_type(0x13, 11, 0, 0, 1),         # 40: x10 = 20; 44: x11 = 1
         jal(0, -40),                                                   # 48: j 8
         0x100073, jal(0, 0)]                                           # 52: ebreak; 56: j .
    yield 'btb_stale_after_fencei', p, 0, MASK

COUNT_DECL = "    integer max_retired=0,image_bin=0;\n"
COUNT_ADD = """    integer max_retired=0,image_bin=0;
    // hand-off 14 test: redirects and mispredicts of the instruction at 8 while it is a nop
    integer s_mp=0;
    always @(negedge clk) if (!reset && dut.d_redirect && dut.rb_pc[dut.rb_tail-1]==64'd8 && dut.rb_insn[dut.rb_tail-1]==32'h13) s_mp=s_mp+1;
    always @(negedge clk) if (!reset && dut.mp_any && dut.rb_pc[dut.b_rob]==64'd8 && dut.rb_insn[dut.b_rob]==32'h13) s_mp=s_mp+1;
"""
DONE = 'fault_lane4=%0d",\n'
DONE_NEW = 'fault_lane4=%0d s_mp=%0d",\n'
DONE_ARGS = 'fault_lane2,fault_lane3,fault_lane4);'
DONE_ARGS_NEW = 'fault_lane2,fault_lane3,fault_lane4,s_mp);'


def cases():
    # Memory hand-off 2 (several misses in flight, split data reads). These run with any N_MISS;
    # they matter with N_MISS > 1 and tb_core's split reads (beats sampled at acceptance, answers
    # out of order). x29 = 0x3000 holds cold lines; loads from 0x0-0x7f read program words.
    lui29 = (3 << 12) | (29 << 7) | 0x37
    add_ = lambda rd, a, b: r_type(0x33, rd, 0, a, b)
    # The deadlock found with "any load may start a miss" (Codex 1739-1): the oldest load A misses;
    # a store S between A and a younger load B writes B's beat with A's value; B misses too and then
    # waits for S's data. If B could hold the fill buffer, A could never start its miss.
    yield 'miss_store_dep_deadlock', prefix() + [lui29,
        i_type(3, 21, 3, 0, 0x10),            # A: ld x21, 0x10(x0)   cold beat (program words)
        store(3, 29, 21, 0x100),              # S: sd x21, 0x100(x29) address known, data from A
        i_type(3, 22, 3, 29, 0x100),          # B: ld x22, 0x100(x29) cold, forwarded from S
        i_type(3, 23, 3, 0, 0x20),            # C: ld x23, 0x20(x0)   another cold younger miss
        add_(24, 22, 23), store(3, 29, 24, 0x108), 0x100073], 0, MASK
    # The timing that deadlocked: B misses while S's address is still unknown, S resolves while B's
    # fill is in flight or just arrived (B then waits for S's data with the fill buffer), and A's
    # address comes late. S's address delay sweeps 0..15 multiplies, so some variant hits the window
    # at every wait pattern; each variant uses its own cold beats.
    p = prefix() + [lui29, i_type(0x13, 27, 0, 0, 1)]
    for j in range(16):
        p += [i_type(3, 26, 3, 30, 0),                        # x26 = 0 (cached constant)
              add_(20, 29, 26)] + [r_type(0x33, 20, 4, 20, 27, 1)] * 6 + [   # x20 = 0x3000 after 6 divides
              add_(21, 30, 26)] + [r_type(0x33, 21, 0, 21, 27, 1)] * j + [    # x21 = 0x2000 after j multiplies
              i_type(3, 22, 3, 20, 0x40 * j),                 # A: ld x22, 0x3000+64j   late address, cold
              store(3, 21, 22, 0x800 + 0x40 * j),             # S: sd x22 -> 0x2800+64j  data from A
              i_type(3, 23, 3, 30, 0x800 + 0x40 * j),         # B: ld 0x2800+64j  address at once, cold
              add_(24, 23, 22), add_(25, 25, 24)]
    yield 'miss_store_dep_window', p + [store(3, 29, 25, 0x3f8), 0x100073], 0, MASK
    # Same, with B only partly covered by S (sw), so B needs the beat itself.
    yield 'miss_store_dep_partial', prefix() + [lui29,
        i_type(3, 21, 3, 0, 0x18),
        store(2, 29, 21, 0x104),              # sw: upper half of 0x3100
        i_type(3, 22, 3, 29, 0x100),          # ld: needs the lower half from memory
        i_type(3, 23, 3, 0, 0x28),
        add_(24, 22, 23), store(3, 29, 24, 0x110), 0x100073], 0, MASK
    # A younger miss is in flight when an older store to its beat retires: the answer may hold
    # the beat from before the store and must be dropped (stale), then read again.
    yield 'miss_stale_after_store', prefix() + [lui29,
        store(3, 29, 7, 0x200),               # make 0x3200 non-zero first (no allocation on stores)
        i_type(3, 21, 3, 0, 0x30),            # cold load: the store below waits for it
        add_(25, 21, 21),
        store(2, 29, 25, 0x300),              # sw x25 -> 0x3300 (data late)
        i_type(3, 22, 3, 29, 0x300),          # ld 0x3300: half from the store, half from memory
        i_type(3, 26, 3, 29, 0x300),          # again, after the store retires, from the cache
        i_type(3, 23, 3, 29, 0x200),
        add_(24, 22, 26), add_(24, 24, 23), store(3, 29, 24, 0x118), 0x100073], 0, MASK
    # Many independent cold misses (more than N_MISS), then a dependent chain through them.
    p = prefix() + [lui29]
    for n in range(12):
        p.append(i_type(3, 5 + n, 3, 0, 8 * n))          # 12 cold beats of program words
    for n in range(11):
        p.append(add_(5, 5, 6 + n))
    yield 'miss_many_in_flight', p + [store(3, 29, 5, 0x120), 0x100073], 0, MASK
    # A read fault on a younger miss is dropped; the load faults precisely once it is the oldest.
    yield 'miss_younger_fault', prefix() + [lui29,
        i_type(3, 21, 3, 0, 0x38),            # cold, older
        (4 << 12) | (28 << 7) | 0x37,         # lui x28, 4 -> 0x4000, outside memory
        i_type(3, 22, 3, 28, 0),              # faults (younger miss while x21 misses)
        store(3, 29, 21, 0x128), 0x100073], 0, MASK
    # Codex review of hand-off 2, item 1: two loads to the same faulting beat. The younger one's
    # address comes first, so it takes a younger entry; its error is dropped and it misses again;
    # the oldest load must still read the beat itself (entry 0) and fault precisely.
    # Variants j add j identity ORs to A's address chain, so A and B replay in either phase.
    for j in range(8):
        yield f'miss_two_loads_faulting_beat{j}', prefix() + [lui29, i_type(0x13, 27, 0, 0, 1),
            (4 << 12) | (28 << 7) | 0x37,         # lui x28, 4 -> 0x4000, outside memory
            i_type(3, 26, 3, 30, 0), add_(20, 28, 26)] + [r_type(0x33, 20, 4, 20, 27, 1)] * 2 + [  # x20 = 0x4000, late
            r_type(0x33, 20, 6, 20, 20)] * j + [  # or x20, x20, x20
            i_type(3, 21, 3, 20, 0),              # A: oldest, late address, faults
            i_type(3, 22, 3, 28, 0),              # B: younger, same beat, address at once
            store(3, 29, 22, 0x130), 0x100073], 0, MASK
    # Item 4: a store write faults while younger split reads are outstanding; the core retries the
    # write until they have returned, then traps (cause 7). tb_core checks none is outstanding.
    yield 'miss_store_fault_drain', prefix() + [lui29, (4 << 12) | (28 << 7) | 0x37,
        store(3, 28, 7, 0),                   # sd -> 0x4000: access fault at its write
        i_type(3, 21, 3, 0, 0x40), i_type(3, 22, 3, 0, 0x48), i_type(3, 23, 3, 0, 0x50),
        add_(24, 21, 22), store(3, 29, 24, 0x138), 0x100073], 0, MASK
    # Codex follow-up review, item 1: the store's first write faults while split reads are
    # outstanding, and a second write would succeed (fault_kind 4 faults once). The core must not
    # retry the write: it traps with cause 7 at the store once the reads have returned.
    yield 'miss_store_fault_transient', prefix() + [lui29,
        store(3, 29, 7, 0x100),               # sd -> 0x3100: faults (once)
        i_type(3, 21, 3, 0, 0x40), i_type(3, 22, 3, 0, 0x48), i_type(3, 23, 3, 0, 0x50),
        add_(24, 21, 22), store(3, 29, 24, 0x140), 0x100073], 4, 0x3100
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
    # Wider retirement (council middle, after 0.13.0): long runs of instructions finished
    # at rename (li/mv/addi/lui/auipc) retire up to RW per clock, around a trap, stores
    # and a store bus fault in the same retirement window.
    folded = lambda n, r0=10: [i_type(0x13, r0 + (k % 8), 0, (r0 + ((k + 7) % 8)) if k % 3 else 0, k + 1) for k in range(n)]
    yield 'retire_wide_trap', prefix() + folded(40) + [i_type(3, 1, 3, 0, 4)] + folded(8, 20), 0, MASK
    body = folded(14) + [store(3, 30, 10, 0x500), i_type(0x13, 30, 0, 30, 8)] + folded(14, 18) + \
           [store(3, 30, 11, 0x500), i_type(3, 26, 3, 30, 0x4f8), r_type(0x33, 27, 0, 27, 26),
            i_type(0x13, 28, 0, 28, -1), branch(1, 28, 0, -4 * 34)]
    yield 'retire_wide_stores', prefix() + [i_type(0x13, 28, 0, 0, 3)] + body + [0x100073], 0, MASK
    yield 'retire_wide_store_fault', [(2 << 12) | (1 << 7) | 0x37] + folded(24) + [store(3, 1, 10, 0)] + folded(10, 18) + [0x100073], 3, 8192
    # Rename-stage constant ALU and branch resolution (council middle, after 0.14.1).
    # Constants from li/lui/auipc feed simple and B ops (chains in one rename group),
    # mixed with a late non-constant register; results go to stores, a load and branches.
    li = lambda rd, v: i_type(0x13, rd, 0, 0, v)
    slow = [i_type(0x13, 5, 0, 0, 1), r_type(0x33, 6, 4, 7, 5, 1), r_type(0x33, 6, 4, 6, 5, 1)]   # x6 late
    p = prefix() + slow + [li(10, 5), li(11, -7), r_type(0x33, 12, 0, 10, 11), i_type(0x13, 13, 1, 12, 3),
         r_type(0x33, 14, 4, 13, 10), r_type(0x33, 15, 0, 14, 11, 0x20), r_type(0x33, 16, 3, 11, 10),
         r_type(0x33, 17, 2, 11, 10), i_type(0x13, 18, 7, 11, 0xff), r_type(0x33, 19, 4, 10, 12, 0x10),
         i_type(0x13, 20, 1, 11, 0x604), (0x12345 << 12) | (21 << 7) | 0x37, i_type(0x1b, 21, 0, 21, 0x678),
         r_type(0x3b, 22, 0, 21, 21), r_type(0x33, 23, 0, 6, 10), r_type(0x33, 24, 7, 12, 6),
         store(3, 30, 15, 0x600), store(2, 30, 19, 0x608), i_type(3, 25, 3, 30, 0x600), r_type(0x33, 26, 0, 25, 22),
         0x100073]
    yield 'rename_const_alu', p, 0, MASK
    # Branches decided at rename: constants (every condition, signed and unsigned), the same
    # register with offsets (equality), a counted loop whose counter is a folded constant
    # (fetch mispredicts the exit: rename redirects), and a register compared with itself.
    p = prefix() + slow + [li(10, -1), li(11, 1),
         branch(4, 10, 11, 8), 0xffffffff,                 # blt -1,1: taken
         branch(6, 10, 11, 8), i_type(0x13, 20, 0, 20, 1), # bltu: not taken
         branch(5, 11, 10, 8), 0xffffffff,                 # bge 1,-1: taken
         i_type(0x13, 9, 0, 6, 1), i_type(0x13, 12, 0, 6, 1),
         branch(0, 9, 12, 8), 0xffffffff,                  # beq same reg, same offset: taken
         branch(1, 9, 6, 8), 0xffffffff,                   # bne x6+1, x6: taken
         branch(0, 9, 6, 8), i_type(0x13, 21, 0, 21, 1),   # beq x6+1, x6: not taken
         branch(5, 6, 6, 8), 0xffffffff,                   # bge x6, x6: taken (execute)
         li(13, 6), i_type(0x13, 22, 0, 22, 3), i_type(0x13, 13, 0, 13, -1), branch(1, 13, 0, -8),   # loop 6
         li(14, 2), r_type(0x33, 15, 0, 14, 14), branch(0, 15, 14, 8), i_type(0x13, 23, 0, 23, 1),
         0x100073]
    yield 'rename_branches', p, 0, MASK
    # More branch-capable ports (N_BR): six independent conditional branches per iteration
    # on bits of a counter, so several resolve in one clock and some mispredict together
    # (the oldest must win), a branch-class multiply among them, and an indirect jump.
    body = [i_type(0x13, 20, 0, 20, 1)]                                   # x20 = iteration
    for n in range(6):
        body += [i_type(0x13, 21 + n % 3, 7, 20, 1 << n),                 # andi x21.., x20, bit n
                 branch(0, 21 + n % 3, 0, 8), i_type(0x13, 13 + n, 0, 13 + n, 1)]   # count when set
    body += [r_type(0x33, 24, 0, 20, 20, 1), add_(25, 25, 24),           # mul on a full port
             (0 << 12) | (26 << 7) | 0x17,                                 # auipc x26, 0
             i_type(0x67, 0, 0, 26, 12),                                   # jalr x0, 12(x26): skip one
             i_type(0x13, 27, 0, 27, 1),                                   # skipped
             i_type(0x13, 28, 0, 20, -40)]
    body.append(branch(1, 28, 0, -4 * len(body)))                         # 40 iterations
    # x20 from a loaded register (x1 = 0), not a rename-time constant, so the bit tests and
    # branches reach the ports instead of being decided at rename (Codex 1539-2).
    p = prefix() + [i_type(0x13, 20, 0, 1, 0)] + body + [add_(29, 13, 14), add_(29, 29, 18), 0x100073]
    yield 'branch_ports_many', p, 0, MASK
    # Load-to-use latency knob (backend hand-off 5; run with --ld-lat N on the ooo core).
    ld = lambda rd, rs, off: i_type(3, rd, 3, rs, off)
    def ld_chain(n):   # x31 = 0x2700 holds its own address: n dependent loads in a row
        return prefix() + [i_type(0x13, 31, 0, 30, 0x700), store(3, 30, 31, 0x700), ld(31, 31, 0)] + \
            [ld(31, 31, 0) for _ in range(n)] + [add_(29, 31, 1), 0x100073]
    yield 'ld_lat_chain8', ld_chain(8), 0, MASK
    yield 'ld_lat_chain40', ld_chain(40), 0, MASK
    # Early full forward to an uncached beat; a load feeding a cold mispredicted branch with
    # younger loads (one misaligned) squashed; every load size into ALU, mul and store; a
    # store forwarded to a narrower load; a load into x0; a loop so value prediction engages.
    p = prefix() + [i_type(0x13, 31, 0, 30, 0x700), store(3, 30, 31, 0x700),
                    store(3, 30, 7, 0x7f8), ld(8, 30, 0x7f8), add_(9, 8, 2),
                    i_type(3, 10, 4, 30, 8), branch(1, 10, 0, 16),
                    ld(17, 30, 16), add_(18, 17, 17), ld(19, 18, 0),
                    i_type(0x13, 20, 0, 0, 10)]
    body = [ld(11, 31, 0), add_(12, 12, 11),
            i_type(3, 13, 2, 30, 8 * 7), r_type(0x33, 14, 0, 13, 11, 1),
            store(2, 30, 14, 0x710), i_type(3, 15, 1, 30, 0x710), add_(16, 16, 15),
            i_type(3, 21, 0, 30, 8 * 6 + 3), add_(22, 22, 21),
            i_type(3, 23, 6, 30, 8 * 5 + 4), add_(24, 24, 23),
            i_type(3, 0, 3, 30, 8 * 2), i_type(0x13, 20, 0, 20, -1)]
    body.append(branch(1, 20, 0, -4 * len(body)))
    p += body + [add_(29, 12, 16), add_(29, 29, 22), add_(29, 29, 24), add_(29, 29, 9), 0x100073]
    yield 'ld_lat_mix', p, 0, MASK
    # Offset consumer of a load (hand-off 6): load -> folded addi -> add -> next load address.
    def ld_off_chain(n):
        body = []
        for _ in range(n):
            body += [ld(5, 10, 0), i_type(0x13, 6, 0, 5, 1), r_type(0x33, 10, 0, 6, 3)]
        return prefix() + [i_type(0x13, 10, 0, 30, 0x700), store(3, 30, 10, 0x700)] + body + [store(3, 30, 10, 0x708), 0x100073]
    yield 'ld_off_chain8', ld_off_chain(8), 0, MASK
    yield 'ld_off_chain40', ld_off_chain(40), 0, MASK
    # A walk over distinct beats (hand-off 7): a ring of 48 nodes in consecutive beats (node i
    # at 0x2400 + 8i points to node i + 1 mod 48), one lap to fill the L1, then n more steps.
    def ld_far_chain(n):
        nodes = []
        for i in range(48):
            nodes += [i_type(0x13, 12, 0, 30, 0x400 + 8 * ((i + 1) % 48)), store(3, 30, 12, 0x400 + 8 * i)]
        return prefix() + nodes + [i_type(0x13, 10, 0, 30, 0x400)] + [ld(10, 10, 0) for _ in range(48 + n)] + \
            [store(3, 30, 10, 0x708), 0x100073]
    yield 'ld_far_chain8', ld_far_chain(8), 0, MASK
    yield 'ld_far_chain40', ld_far_chain(40), 0, MASK
    # Offset consumers of late-written registers (hand-off 8, Codex 1609-2): a multiply,
    # a divide and a value-predicted load each feed a folded addi, whose result is used by
    # an ALU op, a branch, a store (data and address), a load address and another multiply.
    lp = [i_type(3, 14, 3, 30, 0x310),                                   # ld x14 (same value every time: predicted)
          i_type(0x13, 15, 0, 14, 5), r_type(0x33, 16, 0, 16, 15),       # x15 = x14+5 (folded); x16 += x15
          r_type(0x33, 17, 0, 15, 2, 1),                                 # mul x17, x15, x2
          i_type(0x13, 18, 0, 18, -1), branch(1, 18, 0, -20)]            # 12 iterations
    p = prefix() + [store(3, 30, 8, 0x310), i_type(0x13, 18, 0, 0, 12)] + lp + [
         r_type(0x33, 5, 0, 7, 9, 1), i_type(0x13, 6, 0, 5, 7),          # mul x5, x7, x9; x6 = x5+7 (folded)
         r_type(0x33, 19, 0, 6, 2), branch(0, 6, 5, 8),                  # add x19, x6, x2; beq x6,x5 (not taken)
         r_type(0x33, 20, 0, 6, 9, 1),                                   # mul x20, x6, x9
         store(3, 30, 6, 0x318), i_type(0x13, 21, 0, 30, 0x2f8),         # sd x6; x21 = x30+0x2f8
         r_type(0x33, 22, 0, 5, 9, 1), i_type(0x13, 23, 0, 22, -0x2e0),  # x23 = x5*x9 - 0x2e0
         r_type(0x33, 24, 4, 8, 2, 1), i_type(0x13, 25, 0, 24, 1),       # div x24, x8, x2; x25 = x24+1 (folded)
         r_type(0x33, 26, 0, 25, 25), store(3, 21, 25, 0x28),            # add x26 = 2*x25; sd x25 via x21
         i_type(3, 27, 3, 21, 0x20), r_type(0x33, 28, 0, 27, 26), 0x100073]
    yield 'fold_offset_late_producers', p, 0, MASK
    # Frontend hand-off 8: a mispredicted branch inside f sends fetch down a wrong path that
    # returns from f (pops the return stack) and then calls g (writes the entry the restored
    # pointer names). The correct path's return from f must still be predicted (performance;
    # values are checked here). The branch depends on two divides, so it resolves late, and
    # its direction comes from an xorshift sequence, so it keeps mispredicting.
    p = ras_wrong_path_call_program()
    yield 'ras_wrong_path_call', p, 0, MASK
    yield 'ret_displacement', ret_displacement_program(), 0, MASK
    yield from rc_fetch_cases(i_type, r_type, store, branch, jal, MASK)
    yield from gh_predictor_cases(i_type, r_type, store, branch, jal, MASK)
    yield from btb_stale_cases(i_type, r_type, store, branch, jal, MASK)
    # Load-wait table (middle hand-off 13): load L conflicts with store A, whose address
    # arrives late (a fill and two divides), and is marked with A; a different store B, older
    # than the next L and later still (thirty multiplies), writes that L's word every 4th
    # iteration, so a load marked only with A may run past B and must be caught and refetched.
    # Addresses move every iteration, so value prediction cannot supply them early.
    def late(rd, src):     # rd = (src + mem[0x1f8]) / 1 / 1
        return [i_type(0x13, 27, 0, 0, 1), i_type(3, 26, 3, 30, 0x1f8), r_type(0x33, rd, 0, src, 26),
                r_type(0x33, rd, 4, rd, 27, 1), r_type(0x33, rd, 4, rd, 27, 1)]
    def slow(rd, src):     # rd = (src + mem[0x1f0]) * 1, thirty times
        return [i_type(0x13, 27, 0, 0, 1), i_type(3, 26, 3, 30, 0x1f0), r_type(0x33, rd, 0, src, 26)] + \
               [r_type(0x33, rd, 0, rd, 27, 1)] * 30
    loop = ([r_type(0x33, 31, 0, 30, 25)] +                               # x31 = x30 + x25 (early)
            late(20, 31) + [r_type(0x33, 20, 0, 20, 23), store(3, 20, 16, 0x400)] +   # A: sd x16, 0x400(late x31 + x23)
            [i_type(3, 17, 3, 31, 0x400), r_type(0x33, 18, 0, 18, 17)] +   # L: ld x17, 0x400(x31); x18 += x17
            [r_type(0x33, 28, 0, 31, 24)] + slow(22, 28) +                 # B: sd x16, 0x400(slow(x31 + x24))
            [store(3, 22, 16, 0x400),
             i_type(0x13, 16, 0, 16, 3), i_type(0x13, 25, 0, 25, 8),       # data += 3; x25 += 8
             i_type(0x13, 19, 0, 19, 1), i_type(0x13, 29, 7, 19, 3),
             i_type(0x13, 24, 0, 0, 72), branch(1, 29, 0, 8), i_type(0x13, 24, 0, 0, 8),   # x24 = 8 every 4th
             i_type(0x13, 23, 0, 0, 64), i_type(0x13, 21, 0, 21, -1)])   # A writes elsewhere after iteration 1
    loop += [branch(1, 21, 0, -4 * len(loop))]
    p = prefix() + [i_type(0x13, 21, 0, 0, 40), i_type(0x13, 24, 0, 0, 72), i_type(0x13, 25, 0, 0, 0), i_type(0x13, 23, 0, 0, 0)] + loop
    p += [store(3, 30, 18, 0x3f8), 0x100073]
    yield 'mdp_learnt_store_only', p, 0, MASK
    # Value-prediction confidence (middle hand-off 11): one load PC sees runs of 11 equal
    # values (an 8-result confidence predicts and then misses at every change); then a load
    # that returns the same value 450 times becomes predicted, its value changes under it
    # (a store in the loop), and it keeps running with a raised requirement.
    vals = [2, 1, 3, 4]                                                       # x2=1, x1=0, x3=MASK, x4=2^63
    p = prefix() + [i_type(0x13, 20, 0, 30, 0x400)]
    p += [store(3, 20, vals[n // 11], 8 * n) for n in range(44)]
    p += [i_type(0x13, 26, 0, 0, 44),                                        # x26 = 44
          i_type(3, 21, 3, 20, 0), r_type(0x33, 22, 0, 22, 21),              # loop A: ld x21; x22 += x21
          r_type(0x33, 23, 0, 21, 21, 1), r_type(0x33, 24, 0, 24, 23),       # x24 += x21*x21
          i_type(0x13, 20, 0, 20, 8), i_type(0x13, 26, 0, 26, -1), branch(1, 26, 0, -24)]
    p += [i_type(0x13, 26, 0, 0, 600), store(3, 30, 0, 0x3f0),               # loop B: 600 iterations, word = 0
          i_type(3, 25, 3, 30, 0x3f0), r_type(0x33, 27, 0, 27, 25),          # ld x25 (predicted after 32)
          i_type(0x13, 28, 0, 0, 150), branch(1, 26, 28, 8),                 # at x26 == 150:
          store(3, 30, 3, 0x3f0),                                            #   the word becomes MASK
          i_type(0x13, 26, 0, 26, -1), branch(1, 26, 0, -24),
          r_type(0x33, 29, 0, 22, 27), store(3, 30, 29, 0x3f8), store(3, 30, 24, 0x3e8), 0x100073]
    yield 'vp_confidence_runs', p, 0, MASK

# Wall-clock guard per simulation. Real hangs end at tb_core's cycle limit; this only backs it
# up, so Icarus (100-400x slower than Verilator) gets more time: under Icarus with 2-line caches
# and heavy bus waits ras_wrong_path_call took 192 s (2026-11-21).
HANG_SECONDS = 60


def command(args, timeout=None):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                            timeout=HANG_SECONDS if timeout is None else timeout)
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
    parser.add_argument('--n-miss', type=int, default=1,
                        help='Out-of-order core: data misses in flight (N_MISS; above 1, split reads in tb_core)')
    parser.add_argument('--core-source', type=Path,
                        help="Test this file instead of the core's file in rtl/cpu (a candidate kept elsewhere)")
    parser.add_argument('--out-dir', type=Path,
                        help='Build and report folder (default build/cpu), so candidates can be tested side by side')
    parser.add_argument('--ld-lat', type=int,
                        help='ooo core: build with load-to-use latency N (define RV64_OOO_LD_LAT; default 1)')
    parser.add_argument('--l0', type=int, help='ooo core with --ld-lat >= 3: an L0 beat buffer of N beats (RV64_OOO_L0_N)')
    parser.add_argument('--l0-lat', type=int, default=2, help='load-to-use latency of an L0 hit (RV64_OOO_L0_LAT, default 2)')
    simulator.add_argument(parser)
    args = parser.parse_args()
    if args.out_dir: OUT = args.out_dir.resolve()
    cache = {'ICACHE_BEATS': args.icache_beats} if args.icache_beats else {}
    cache |= {'DCACHE_BEATS': args.dcache_beats} if args.dcache_beats else {}
    if args.n_miss > 1 and args.core != 'ooo':
        parser.error('--n-miss above 1 needs --core ooo (split reads exist only in the out-of-order core)')
    cache |= {'N_MISS': args.n_miss} if args.n_miss > 1 else {}  # memory hand-off 2: split data reads
    try:
        sim = simulator.get(args.sim)
        global HANG_SECONDS
        HANG_SECONDS = 60 if args.sim == 'verilator' else 300
    except simulator.SimulatorMissing as missing:
        parser.error(str(missing))
    # Icarus compiles in seconds; a Verilator build gets the 5-minute step limit.
    limit = 60 if sim.name == 'icarus' else simulator.STEP_TIMEOUT
    OUT.mkdir(parents=True, exist_ok=True)
    core_src = args.core_source.resolve() if args.core_source else ROOT / CORES[args.core]
    wide = ['WIDE_TRACE'] if args.core == 'ooo' else []  # 0.10.0: up to 8 retirements per clock
    if args.ld_lat is not None and args.core != 'ooo': parser.error('--ld-lat applies to the ooo core')
    lat = [f'RV64_OOO_LD_LAT={args.ld_lat}'] if args.ld_lat is not None else []
    if args.l0:
        if args.core != 'ooo' or args.ld_lat is None or args.ld_lat < 3: parser.error('--l0 needs the ooo core and --ld-lat >= 3')
        lat += [f'RV64_OOO_L0_N={args.l0}', f'RV64_OOO_L0_LAT={args.l0_lat}']
    wide += lat
    executable = sim.build('tb_core', [core_src, ROOT / 'sim/cpu/tb_core.sv'], OUT / 'cpu.vvp',
                           params=cache, defines=wide, timeout=limit)
    sim.elaborate('rv64_bram_soc', [core_src, ROOT/'rtl/cpu/rv64_bram_soc.sv'], OUT/'soc.vvp',
                  defines=wide, timeout=limit)
    reset_sim = sim.build('tb_reset', [core_src, ROOT/'sim/cpu/tb_reset.sv'], OUT/'reset.vvp', defines=lat, timeout=limit)
    reset_result=command(reset_sim).strip()
    soc_sim = sim.build('tb_soc', [core_src, ROOT/'rtl/cpu/rv64_bram_soc.sv', ROOT/'sim/cpu/tb_soc.sv'],
                        OUT/'bram-soc.vvp', defines=wide, timeout=limit)
    smoke=image_for([0x00500093,0x00700113,0x002081b3,0x00003237,0x00323023,0x00100073])
    smoke_hex=OUT/'soc-smoke.hex'
    smoke_hex.write_text(''.join(f'{int.from_bytes(smoke[i:i+8],"little"):016x}\n' for i in range(0,len(smoke),8)),encoding='ascii')
    soc_results=[command([*soc_sim,f'+image={smoke_hex}','+expected=c']).strip()]
    workloads = [(name,image_for(words),kind,addr) for name,words,kind,addr in cases()]
    if args.image:
        data = args.image.read_bytes()
        if len(data)>16384: raise ValueError('Firmware exceeds laboratory RAM')
        workloads.append(('compiled_firmware', data.ljust(16384,b'\0'), 0, MASK))
        bram=args.image.with_name('firmware-bram.hex')
        if not bram.is_file(): raise ValueError('Missing companion firmware-bram.hex')
        soc_results.append(command([*soc_sim,f'+image={bram}','+expected=24','+second']).strip())
    records,coverage = [],set()
    for name, image, kind, address in workloads:
        expected, covered = execute(image, 3 if kind == 4 else kind, address)  # kind 4: store faults once
        if name == 'compiled_firmware':
            if 'W 0000000000003000 0000000000000024 ff' not in expected:
                raise AssertionError('Compiled firmware did not produce the known sum 36')
        coverage |= covered
        hexfile = OUT / (name+'.hex')
        hexfile.write_text(''.join(f'{b:02x}\n' for b in image),encoding='ascii')
        # N_MISS > 1: also fixed split-read latencies 2-4 (random answer timing can hide livelocks).
        patterns = [(0,1,0),(7,42,0),(19,103,0)] + ([(0,1,2),(0,1,3),(0,1,4)] if args.n_miss > 1 else [])
        for stalls,seed,slat in patterns:
            trace = OUT / (f'{name}-stall{stalls}' + (f'-lat{slat}' if slat else '') + '.trace')
            output = command([*executable,f'+image={hexfile}',f'+trace={trace}',
                              f'+stall={stalls}',f'+seed={seed}',f'+fault_kind={kind}',f'+fault_addr={address:x}']
                             + ([f'+split_lat={slat}'] if args.n_miss > 1 else []))
            actual=trace.read_text().splitlines()
            if actual!=expected:
                for index in range(max(len(actual),len(expected))):
                    a=actual[index] if index<len(actual) else '<missing>'
                    e=expected[index] if index<len(expected) else '<missing>'
                    if a!=e: raise AssertionError(f'{name} stall={stalls} event {index}:\nactual {a}\nexpect {e}')
            # Structural coverage: these programs exist to exercise an issue slot, so
            # check that the slot was used (default caches, where the lines stay cached).
            if args.icache_beats is None and stalls == 0 and slat == 0 and name in SLOT_USE[args.core]:
                field = SLOT_USE[args.core][name]
                used = re.search(field + r'=(\d+)', output)
                if not used or int(used[1]) == 0:
                    raise AssertionError(f'{name}: expected {field} > 0, simulator said {output.strip()}')
            records.append({'case':name,'max_wait_cycles':stalls,'events':len(actual),'result':'PASS','simulator_summary':output.strip()})
    required=set('lui auipc jal jalr beq bne blt bge bltu bgeu lb lh lw ld lbu lhu lwu sb sh sw sd addi slti sltiu xori ori andi slli srli srai add sub sll slt sltu xor srl sra or and addiw slliw srliw sraiw addw subw sllw srlw sraw fence fence.i ecall ebreak mul mulh mulhsu mulhu div divu rem remu mulw divw divuw remw remuw sh1add sh2add sh3add add.uw sh1add.uw sh2add.uw sh3add.uw slli.uw andn orn xnor clz ctz cpop clzw ctzw cpopw max maxu min minu sext.b sext.h zext.h rol ror rolw rorw rori roriw orc.b rev8 bclr bclri bext bexti binv binvi bset bseti'.split())
    # LD_LAT N >= 2: the 32 extra chained loads cost N clocks each (stall 0, default caches).
    if args.ld_lat is not None and args.ld_lat >= 2 and args.icache_beats is None and args.dcache_beats is None:
        clk = {r['case']: int(re.search(r'cycles=(\d+)', r['simulator_summary'])[1]) for r in records
               if r['max_wait_cycles'] == 0 and r['case'] in ('ld_lat_chain8', 'ld_lat_chain40')}
        # With an L0 the same-beat chains hit it after their first load (hand-off 7).
        hit = args.l0_lat if args.l0 else args.ld_lat
        extra = clk['ld_lat_chain40'] - clk['ld_lat_chain8']
        if not 32 * hit <= extra <= 32 * hit + 8:
            raise AssertionError(f'LD_LAT {args.ld_lat}: 32 chained loads took {extra} clocks, expected {32 * hit}')
        clk = {r['case']: int(re.search(r'cycles=(\d+)', r['simulator_summary'])[1]) for r in records
               if r['max_wait_cycles'] == 0 and r['case'] in ('ld_far_chain8', 'ld_far_chain40')}
        extra = clk['ld_far_chain40'] - clk['ld_far_chain8']
        far = args.l0_lat if args.l0 and args.l0 >= 48 else args.ld_lat   # the ring's 48 beats fit an L0 of 48+
        if not 32 * far <= extra <= 32 * far + 8:
            raise AssertionError(f'LD_LAT {args.ld_lat}: 32 loads over distinct beats took {extra} clocks, expected {32 * far}')
        # A consumer with a folded offset pays its clock: load, offset clock, add.
        clk = {r['case']: int(re.search(r'cycles=(\d+)', r['simulator_summary'])[1]) for r in records
               if r['max_wait_cycles'] == 0 and r['case'] in ('ld_off_chain8', 'ld_off_chain40')}
        extra = clk['ld_off_chain40'] - clk['ld_off_chain8']
        if not 32 * (hit + 2) <= extra <= 32 * (hit + 2) + 8:
            raise AssertionError(f'LD_LAT {args.ld_lat}: 32 load-offset-add steps took {extra} clocks, expected {32 * (hit + 2)}')
    missing=required-coverage
    if missing: raise AssertionError('Missing instruction coverage: '+str(sorted(missing)))
    for branch_name in ('beq','bne','blt','bge','bltu','bgeu'):
        for outcome in ('taken','not_taken'):
            if branch_name+':'+outcome not in coverage: raise AssertionError('Missing branch outcome')
    report={'status':'PASS','cases':len(workloads),'runs':len(records),'instruction_names_covered':len(required),
            'core':args.core,'ld_lat':args.ld_lat or 1,'l0_n':args.l0 or 0,'l0_lat':args.l0_lat if args.l0 else None,'core_source':str(args.core_source) if args.core_source else CORES[args.core],
            'icache_beats':args.icache_beats or 'tb_core default (512)','dcache_beats':args.dcache_beats or 'tb_core default (512)',
            'reset_test':reset_result,'bram_soc_tests':soc_results,
            'coverage':sorted(coverage),'validation_scope':'local directed/random differential simulation; no official ISA certification or synthesis',
            'rtl_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'rtl/cpu').glob('*.sv'))},
            'simulated_core_sha256':hashlib.sha256(core_src.read_bytes()).hexdigest(),
            **sim.info(),'results':records}
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS ({args.core} core, {sim.label}): {len(workloads)} programs x 3 wait patterns = {len(records)} runs; {len(required)} instruction names covered.')
    print('Includes precise traps, invalid encodings, bus faults, x0, all memory lanes, branch outcomes and ordered retirement.')


if __name__=='__main__': main()
