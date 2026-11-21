"""Checkpoint images: start a benchmark part-way through, from reference-model state.

The reference model's trace (sim/cpu/reference.py) lists every retirement with
its destination register value and every memory write, so the architectural
state (32 registers, all of memory, the PC) before any instruction can be
rebuilt by replaying the trace. A checkpoint image is that memory with a short
restore stub: the reset vector jumps to the stub, the stub loads x1-x31 from a
table and jumps to the saved PC. The cores have no other architectural state
the benchmark uses (no CSRs, no reservations).

The stub sits at the bottom of the stack reserve, below any live stack frame
(checked), and runs once before the program continues; caches and predictors
start cold at the checkpoint, which differs from a run from reset.
SPDX-License-Identifier: MIT
"""
from pathlib import Path

STUB_INSTRUCTIONS = 34  # jal at the reset vector, auipc, 31 loads, jal to the saved PC


def _ld(rd, rs1, offset):
    return (offset & 0xfff) << 20 | rs1 << 15 | 3 << 12 | rd << 7 | 0x03


def _jal(rd, offset):
    if offset & 1 or not -(1 << 20) <= offset < (1 << 20):
        raise ValueError('jal offset out of range')
    o = offset & 0x1fffff
    return ((o >> 20) & 1) << 31 | ((o >> 1) & 0x3ff) << 21 | ((o >> 11) & 1) << 20 | \
        ((o >> 12) & 0xff) << 12 | rd << 7 | 0x6f


def replay(image, trace, stop_index):
    """State before instruction number stop_index (0-based, program order).

    Returns (registers, memory, pc). Memory writes listed in the trace before the
    instruction's own writes are applied; its own are not.
    """
    memory = bytearray(image)
    regs = [0] * 32
    count = 0
    for line in trace:
        kind = line[0]
        if kind == 'R':
            if count == stop_index:
                return regs, memory, int(line[2:18], 16)
            rd, value = int(line[28:30], 16), int(line[31:47], 16)
            if rd:
                regs[rd] = value
            count += 1
        elif kind == 'W':
            if count == stop_index:
                continue  # the instruction's own write
            _, address, data, mask = line.split()
            address, data, mask = int(address, 16), int(data, 16), int(mask, 16)
            for lane in range(8):
                if mask >> lane & 1:
                    memory[address + lane] = data >> (8 * lane) & 0xff
        else:
            break
    raise ValueError(f'trace ends before instruction {stop_index}')


def instruction_index_of_write(trace, address, value):
    """Program-order index of the instruction whose store wrote value to address."""
    count = 0
    want = f'W {address:016x} {value:016x} '
    for line in trace:
        if line[0] == 'R':
            count += 1
        elif line.startswith(want):
            return count
    raise ValueError(f'no write of {value:#x} to {address:#x} in the trace')


def build(image, trace, stop_index, stub_address, patches=()):
    """Checkpoint image (bytes) that resumes before instruction stop_index.

    patches: (address, little-endian bytes) applied to the captured memory, for
    example to reset the marker word or select a benchmark phase.
    """
    regs, memory, pc = replay(image, trace, stop_index)
    table = stub_address + 4 * 33
    table = (table + 7) & ~7
    stub_end = table + 8 * 32
    if stub_address & 7 or regs[2] < stub_end + 64:
        raise ValueError('restore stub would overlap the live stack')
    words = [0x17 | 31 << 7]  # auipc x31, 0
    for rd in range(1, 32):
        words.append(_ld(rd, 31, table - stub_address + 8 * rd))
    words.append(_jal(0, pc - (stub_address + 4 * len(words))))
    if len(words) != STUB_INSTRUCTIONS - 1 or stub_address + 4 * len(words) > table:
        raise AssertionError('restore stub layout')
    for address, data in patches:
        memory[address:address + len(data)] = data
    for i, word in enumerate(words):
        memory[stub_address + 4 * i:stub_address + 4 * i + 4] = word.to_bytes(4, 'little')
    for rd in range(32):
        memory[table + 8 * rd:table + 8 * rd + 8] = regs[rd].to_bytes(8, 'little')
    memory[0:4] = _jal(0, stub_address).to_bytes(4, 'little')
    return bytes(memory), {'resume_pc': pc, 'resume_instruction': stop_index, 'stub_address': stub_address,
                           'stack_pointer': regs[2]}


def write_images(memory, directory, stem):
    """bench-words.hex style (tb_bench) and bench-bytes.hex style (tb_core) files."""
    directory = Path(directory)
    words = directory / f'{stem}-words.hex'
    data = directory / f'{stem}-bytes.hex'
    texts = {words: ''.join(f'{int.from_bytes(memory[i:i + 8], "little"):016x}\n' for i in range(0, len(memory), 8)),
             data: ''.join(f'{b:02x}\n' for b in memory)}
    # Read each file back: a write through WSL's /mnt/c once left NUL bytes in an image
    # (2026-11-21), which the simulator then loaded as a broken program.
    for path, text in texts.items():
        for _ in range(3):
            path.write_bytes(text.encode('ascii'))
            if path.read_bytes() == text.encode('ascii'):
                break
        else:
            raise OSError(f'{path} does not read back as written')
    return words, data
