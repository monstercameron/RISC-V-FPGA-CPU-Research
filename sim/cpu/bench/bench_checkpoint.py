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
import sys

STUB_INSTRUCTIONS = 34  # jal at the reset vector, auipc, 31 loads, jal to the saved PC
# (the near layout; images above 1 MiB use FAR_STUB_INSTRUCTIONS, see build_from_state)


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
    return build_from_state(regs, memory, pc, stop_index, stub_address, patches)


def _reaches(source, target):
    return -(1 << 20) <= target - source < (1 << 20)


def _lui(rd, value):
    return (value & 0xfffff) << 12 | rd << 7 | 0x37


def _jalr(rd, rs1, offset):
    return (offset & 0xfff) << 20 | rs1 << 15 | rd << 7 | 0x67


# Far layout, for images where a jal cannot reach the stub from the reset vector or
# the saved PC from the stub (RAM above 1 MiB): the reset vector is lui x31 + jalr to
# the stub; the stub ends with jalr x0, 8(x0) to a trampoline jal at address 8, which
# reaches any PC in the first MiB. Addresses 0-0x2f hold start.S code before
# `call main`, which runs once after reset and never again (checked: the saved PC
# must not lie there).
FAR_STUB_INSTRUCTIONS = 36  # lui, jalr, auipc, 31 loads, jalr to 8, trampoline jal
FAR_DEAD_END = 0x30


def build_from_state(regs, memory, pc, stop_index, stub_address, patches=()):
    """Checkpoint image from architectural state (registers, memory bytes, PC), for
    example a state saved by the fast functional simulator rv_iss.c. Same layout as
    build() when jal reaches (always for images of up to 1 MiB); otherwise the far
    layout above. The info dict gives the layout's instruction count
    ('stub_instructions') and the PCs the stub retires first ('stub_pcs')."""
    memory = memory if isinstance(memory, bytearray) else bytearray(memory)
    table = stub_address + 4 * 33
    table = (table + 7) & ~7
    stub_end = table + 8 * 32
    if stub_address & 7 or regs[2] < stub_end + 64:
        raise ValueError('restore stub would overlap the live stack')
    near = _reaches(0, stub_address) and _reaches(stub_address + 4 * 32, pc)
    words = [0x17 | 31 << 7]  # auipc x31, 0
    for rd in range(1, 32):
        words.append(_ld(rd, 31, table - stub_address + 8 * rd))
    if near:
        words.append(_jal(0, pc - (stub_address + 4 * len(words))))
    else:
        if not 0 <= stub_address < (1 << 31) or pc < FAR_DEAD_END or not _reaches(8, pc):
            raise ValueError(f'far restore stub cannot reach PC {pc:#x} from address 8')
        words.append(_jalr(0, 0, 8))
    if len(words) != STUB_INSTRUCTIONS - 1 or stub_address + 4 * len(words) > table:
        raise AssertionError('restore stub layout')
    for address, data in patches:
        memory[address:address + len(data)] = data
    for i, word in enumerate(words):
        memory[stub_address + 4 * i:stub_address + 4 * i + 4] = word.to_bytes(4, 'little')
    for rd in range(32):
        memory[table + 8 * rd:table + 8 * rd + 8] = regs[rd].to_bytes(8, 'little')
    if near:
        memory[0:4] = _jal(0, stub_address).to_bytes(4, 'little')
        count, pcs = STUB_INSTRUCTIONS, [0, stub_address]
    else:
        hi = (stub_address + 0x800) >> 12
        lo = stub_address - (hi << 12)
        memory[0:4] = _lui(31, hi).to_bytes(4, 'little')
        memory[4:8] = _jalr(0, 31, lo).to_bytes(4, 'little')
        memory[8:12] = _jal(0, pc - 8).to_bytes(4, 'little')
        count, pcs = FAR_STUB_INSTRUCTIONS, [0, 4, stub_address]
    return bytes(memory), {'resume_pc': pc, 'resume_instruction': stop_index, 'stub_address': stub_address,
                           'stack_pointer': regs[2], 'stub_instructions': count, 'stub_pcs': pcs}


def read_iss_state(path):
    """(registers, memory bytearray, pc, instruction index) from an rv_iss.c state file."""
    data = Path(path).read_bytes()
    if data[:8] != b'RVISSST1':
        raise ValueError(f'{path} is not an rv_iss state file')
    index, pc = int.from_bytes(data[8:16], 'little'), int.from_bytes(data[16:24], 'little')
    regs = [int.from_bytes(data[24 + 8 * i:32 + 8 * i], 'little') for i in range(32)]
    size = int.from_bytes(data[280:288], 'little')
    memory = bytearray(data[288:288 + size])
    if len(memory) != size:
        raise ValueError(f'{path} is truncated')
    return regs, memory, pc, index


def write_binaries(memory, directory, stem, little=True):
    """Binary images for +image_bin: <stem>-be.bin (tb_bench, big-endian 64-bit words) and,
    with little, <stem>-le.bin (tb_core, bytes; otherwise None is returned for it). Each file
    is read back like write_images()."""
    import array
    directory = Path(directory)
    words = array.array('Q')
    if words.itemsize != 8:
        raise OSError('array type Q is not 64-bit on this host')
    words.frombytes(bytes(memory))
    if sys.byteorder == 'little':
        words.byteswap()
    paths = {directory / f'{stem}-be.bin': words.tobytes()}
    if little:
        paths[directory / f'{stem}-le.bin'] = bytes(memory)
    for path, blob in paths.items():
        for _ in range(3):
            path.write_bytes(blob)
            if path.stat().st_size == len(blob) and path.read_bytes() == blob:
                break
        else:
            raise OSError(f'{path} does not read back as written')
    return tuple(paths) if little else (next(iter(paths)), None)


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
