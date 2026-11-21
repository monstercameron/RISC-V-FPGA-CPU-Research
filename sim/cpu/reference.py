"""Independent sequential RV64I laboratory interpreter, not a certified ISA oracle.

Uses byte-addressed memory and semantic integer operations. No cycle/RTL state.
SPDX-License-Identifier: MIT
"""
MASK = (1 << 64) - 1


def signed(value, bits=64):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def execute(image, fault_kind=0, fault_addr=MASK, max_steps=20000):
    memory = bytearray(image)
    regs = [0] * 32
    pc = 0
    trace = []
    coverage = set()

    def trap(cause, tval):
        trace.append(f'T {pc:016x} {cause:016x} {tval & MASK:016x}')
        return trace, coverage

    def denied(address, kind):
        return (address & ~7) >= len(memory) or (kind == fault_kind and (address & ~7) == fault_addr)

    for _ in range(max_steps):
        if pc & 3:
            return trap(0, pc)
        if denied(pc, 1):
            return trap(1, pc)
        ins = int.from_bytes(memory[pc:pc + 4], 'little')
        op, rd, f3 = ins & 127, (ins >> 7) & 31, (ins >> 12) & 7
        rs1, rs2, f7 = (ins >> 15) & 31, (ins >> 20) & 31, ins >> 25
        a, b = regs[rs1], regs[rs2]
        imm = signed(ins >> 20, 12)
        nxt, value, destination = (pc + 4) & MASK, 0, 0
        name = None
        if op in (0x37, 0x17):
            value = signed(ins & 0xfffff000, 32) + (pc if op == 0x17 else 0)
            destination, name = rd, 'auipc' if op == 0x17 else 'lui'
        elif op == 0x6f:
            displacement = ((ins >> 31) << 20) | (((ins >> 12) & 255) << 12) | (((ins >> 20) & 1) << 11) | (((ins >> 21) & 1023) << 1)
            nxt = (pc + signed(displacement, 21)) & MASK
            destination, value, name = rd, pc + 4, 'jal'
        elif op == 0x67 and f3 == 0:
            nxt = ((a + imm) & MASK) & ~1
            destination, value, name = rd, pc + 4, 'jalr'
        elif op == 0x63 and f3 in (0, 1, 4, 5, 6, 7):
            displacement = ((ins >> 31) << 12) | (((ins >> 7) & 1) << 11) | (((ins >> 25) & 63) << 5) | (((ins >> 8) & 15) << 1)
            conditions = {0: a == b, 1: a != b, 4: signed(a) < signed(b), 5: signed(a) >= signed(b), 6: a < b, 7: a >= b}
            taken = conditions[f3]
            name = {0: 'beq', 1: 'bne', 4: 'blt', 5: 'bge', 6: 'bltu', 7: 'bgeu'}[f3]
            coverage.add(name + (':taken' if taken else ':not_taken'))
            if taken:
                nxt = (pc + signed(displacement, 13)) & MASK
        elif op in (0x13, 0x1b, 0x33, 0x3b):
            immediate = op in (0x13, 0x1b)
            word = op in (0x1b, 0x3b)
            width = 32 if word else 64
            rhs = imm & MASK if immediate else b
            shift = rhs & (width - 1)
            subtract = not immediate and f7 == 32
            arithmetic = (ins >> 30) & 1
            valid = True
            if immediate:
                if f3 in (1, 5):
                    top = ins >> (25 if word else 26)
                    valid = top == 0 or (f3 == 5 and top == (32 if word else 16))
            else:
                valid = f7 == 0 or (f7 == 32 and f3 in (0, 5))
            if word and f3 not in (0, 1, 5):
                valid = False
            if valid:
                if f3 == 0:
                    value, name = (a - rhs, 'sub') if subtract else (a + rhs, 'add')
                elif f3 == 1:
                    value, name = a << shift, 'sll'
                elif f3 == 2:
                    value, name = int(signed(a) < signed(rhs)), 'slt'
                elif f3 == 3:
                    value, name = int(a < rhs), 'sltu'
                elif f3 == 4:
                    value, name = a ^ rhs, 'xor'
                elif f3 == 5:
                    value, name = (signed(a, width) >> shift, 'sra') if arithmetic else ((a & ((1 << width) - 1)) >> shift, 'srl')
                elif f3 == 6:
                    value, name = a | rhs, 'or'
                else:
                    value, name = a & rhs, 'and'
                if immediate:
                    name = {'sltu': 'sltiu'}.get(name, name + 'i')
                if word:
                    value = signed(value, 32)
                    name += 'w'
                destination = rd
        elif op in (0x03, 0x23):
            load = op == 0x03
            if (load and f3 != 7) or (not load and f3 < 4):
                size = 1 << (f3 & 3)
                offset = imm if load else signed(((ins >> 25) << 5) | ((ins >> 7) & 31), 12)
                address = (a + offset) & MASK
                if address % size:
                    return trap(4 if load else 6, address)
                if denied(address, 2 if load else 3):
                    return trap(5 if load else 7, address)
                if load:
                    value = int.from_bytes(memory[address:address + size], 'little')
                    if f3 < 4:
                        value = signed(value, 8 * size)
                    destination = rd
                    name = ('lb', 'lh', 'lw', 'ld', 'lbu', 'lhu', 'lwu')[f3]
                else:
                    memory[address:address + size] = (b & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')
                    lane = address & 7
                    trace.append(f'W {address & ~7:016x} {(b << (8 * lane)) & MASK:016x} {((1 << size) - 1) << lane:02x}')
                    name = ('sb', 'sh', 'sw', 'sd')[f3]
        elif op == 0x0f and f3 in (0, 1):
            name = 'fence' if f3 == 0 else 'fence.i'
        elif ins == 0x73:
            coverage.add('ecall')
            return trap(11, 0)
        elif ins == 0x100073:
            coverage.add('ebreak')
            return trap(3, 0)
        if name is None:
            return trap(2, ins)
        if nxt & 3:
            return trap(0, nxt)
        value &= MASK
        if destination:
            regs[destination] = value
        else:
            value = 0
        trace.append(f'R {pc:016x} {ins:08x} {destination:02x} {value:016x} {nxt:016x}')
        coverage.add(name)
        pc = nxt
    raise RuntimeError('Reference instruction budget exceeded')
