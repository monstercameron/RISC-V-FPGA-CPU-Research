"""Independent sequential RV64I laboratory interpreter, not a certified ISA oracle.

execute(..., fp=True) adds RV64F and RV64D with exact IEEE semantics from fp_ref_core.py, per
cpu/architecture.md (RV64F and RV64D); fp=False (the default) is the integer model, unchanged.

Uses byte-addressed memory and semantic integer operations. No cycle/RTL state.
SPDX-License-Identifier: MIT
"""
MASK = (1 << 64) - 1


def signed(value, bits=64):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def bitmanip_op(ins, a, b):
    """Zba, Zbb and Zbs per the RISC-V bit-manipulation specification.

    Returns (name, value) for a B instruction, or None for anything else.
    Encodings were checked against LLVM's assembler.
    """
    op, f3, f7 = ins & 127, (ins >> 12) & 7, ins >> 25
    f6, f12, rs2 = ins >> 26, ins >> 20, (ins >> 20) & 31
    shamt6, shamt5 = (ins >> 20) & 63, (ins >> 20) & 31
    a32 = a & 0xffffffff
    rot = lambda x, n, w: ((x << n) | (x >> (w - n))) & ((1 << w) - 1) if n else x
    if op == 0x33:
        if f7 == 0x10 and f3 in (2, 4, 6):
            n = f3 // 2
            return f'sh{n}add', (a << n) + b
        if f7 == 0x20 and f3 == 7: return 'andn', a & ~b
        if f7 == 0x20 and f3 == 6: return 'orn', a | (~b & MASK)
        if f7 == 0x20 and f3 == 4: return 'xnor', ~(a ^ b) & MASK
        if f7 == 0x05:
            sa, sb = signed(a), signed(b)
            return {4: ('min', min(sa, sb)), 5: ('minu', min(a, b)),
                    6: ('max', max(sa, sb)), 7: ('maxu', max(a, b))}.get(f3)
        if f7 == 0x30 and f3 == 1: return 'rol', rot(a, b & 63, 64)
        if f7 == 0x30 and f3 == 5: return 'ror', rot(a, (64 - (b & 63)) % 64, 64)
        if f7 == 0x24 and f3 == 1: return 'bclr', a & ~(1 << (b & 63))
        if f7 == 0x24 and f3 == 5: return 'bext', (a >> (b & 63)) & 1
        if f7 == 0x34 and f3 == 1: return 'binv', a ^ (1 << (b & 63))
        if f7 == 0x14 and f3 == 1: return 'bset', a | (1 << (b & 63))
        return None
    if op == 0x3b:
        if f7 == 0x04 and f3 == 0: return 'add.uw', a32 + b
        if f7 == 0x04 and f3 == 4 and rs2 == 0: return 'zext.h', a & 0xffff
        if f7 == 0x10 and f3 in (2, 4, 6):
            n = f3 // 2
            return f'sh{n}add.uw', (a32 << n) + b
        if f7 == 0x30 and f3 == 1: return 'rolw', signed(rot(a32, b & 31, 32), 32)
        if f7 == 0x30 and f3 == 5: return 'rorw', signed(rot(a32, (32 - (b & 31)) % 32, 32), 32)
        return None
    if op == 0x13:
        if f3 == 1 and f12 == 0x600: return 'clz', 64 - a.bit_length()
        if f3 == 1 and f12 == 0x601: return 'ctz', (a & -a).bit_length() - 1 if a else 64
        if f3 == 1 and f12 == 0x602: return 'cpop', bin(a).count('1')
        if f3 == 1 and f12 == 0x604: return 'sext.b', signed(a, 8)
        if f3 == 1 and f12 == 0x605: return 'sext.h', signed(a, 16)
        if f3 == 5 and f6 == 0x18: return 'rori', rot(a, (64 - shamt6) % 64, 64)
        if f3 == 5 and f12 == 0x287:
            return 'orc.b', sum((0xff << (8 * i)) for i in range(8) if (a >> (8 * i)) & 0xff)
        if f3 == 5 and f12 == 0x6b8: return 'rev8', int.from_bytes(a.to_bytes(8, 'little'), 'big')
        if f3 == 1 and f6 == 0x12: return 'bclri', a & ~(1 << shamt6)
        if f3 == 5 and f6 == 0x12: return 'bexti', (a >> shamt6) & 1
        if f3 == 1 and f6 == 0x1a: return 'binvi', a ^ (1 << shamt6)
        if f3 == 1 and f6 == 0x0a: return 'bseti', a | (1 << shamt6)
        return None
    if op == 0x1b:
        if f3 == 1 and f6 == 0x02: return 'slli.uw', a32 << shamt6
        if f3 == 1 and f12 == 0x600: return 'clzw', 32 - a32.bit_length()
        if f3 == 1 and f12 == 0x601: return 'ctzw', (a32 & -a32).bit_length() - 1 if a32 else 32
        if f3 == 1 and f12 == 0x602: return 'cpopw', bin(a32).count('1')
        if f3 == 5 and f7 == 0x30: return 'roriw', signed(rot(a32, (32 - shamt5) % 32, 32), 32)
        return None
    return None


def execute(image, fault_kind=0, fault_addr=MASK, max_steps=20000, bitmanip=True, fp=False, state=None,
            vector=False, vlen=256):
    """Run from PC 0 with zeroed state; returns (trace, coverage).

    fp: enable RV64FD (FP-CONTRACT.md). vector, vlen: enable the RVV subset of RVV-CONTRACT.md
    (vector FP also needs fp). state: optional dict that receives the final
    'x', 'f', 'fcsr', 'pc' and 'memory' when the run stops (used by the cross-checks)."""
    memory = bytearray(image)
    regs = [0] * 32
    if fp:
        from fp_ref_core import fp_compute, BOX
    fregs = [0] * 32
    fcsr = 0
    vst = None
    if vector:
        import vec_ref
        vst = vec_ref.VState(vlen)
    pc = 0
    trace = []
    coverage = set()

    def trap(cause, tval):
        trace.append(f'T {pc:016x} {cause:016x} {tval & MASK:016x}')
        if state is not None:
            state.update(x=list(regs), f=list(fregs), fcsr=fcsr, pc=pc, memory=bytes(memory), vector=vst)
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
        elif op in (0x33, 0x3b) and f7 == 1:
            # M extension (architecture 0.4.0), from the RISC-V unprivileged specification.
            word = op == 0x3b
            if not word or f3 in (0, 4, 5, 6, 7):
                if f3 < 4:
                    if word:
                        value = signed((a * b) & 0xffffffff, 32)
                    elif f3 == 0:
                        value = a * b
                    elif f3 == 1:
                        value = (signed(a) * signed(b)) >> 64
                    elif f3 == 2:
                        value = (signed(a) * b) >> 64
                    else:
                        value = (a * b) >> 64
                else:
                    sign = f3 in (4, 6)
                    width = 32 if word else 64
                    x = signed(a, width) if sign else a & ((1 << width) - 1)
                    y = signed(b, width) if sign else b & ((1 << width) - 1)
                    if y == 0:
                        quotient, remainder = -1, x
                    elif sign and x == -(1 << (width - 1)) and y == -1:
                        quotient, remainder = x, 0
                    else:
                        quotient = abs(x) // abs(y)
                        if (x < 0) != (y < 0):
                            quotient = -quotient
                        remainder = x - quotient * y
                    value = remainder if f3 in (6, 7) else quotient
                    if word:
                        value = signed(value, 32)
                name = ('mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu')[f3] + ('w' if word else '')
                destination = rd
        elif bitmanip and op in (0x13, 0x1b, 0x33, 0x3b) and bitmanip_op(ins, a, b) is not None:
            # B extension (Zba, Zbb, Zbs), when the run enables it (architecture 0.6.0).
            name, value = bitmanip_op(ins, a, b)
            destination = rd
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
        elif vector and (op == 0x57 or (op in (0x07, 0x27) and f3 in (0, 5, 6, 7))):
            result = vec_ref.vstep(ins, vst, regs, fregs, fcsr >> 5, memory, denied, fp)
            if result[0] == 'trap':
                trace.extend(result[3])
                return trap(result[1], result[2])
            if result[0] == 'ok':
                _, name, destination, value, flags, records = result
                fcsr |= flags
                trace.extend(records)
        elif fp and op in (0x07, 0x27) and f3 in (2, 3):
            # FLW/FLD/FSW/FSD: alignment and faults as the integer word/doubleword forms.
            load = op == 0x07
            size = 4 if f3 == 2 else 8
            offset = imm if load else signed(((ins >> 25) << 5) | ((ins >> 7) & 31), 12)
            address = (a + offset) & MASK
            if address % size:
                return trap(4 if load else 6, address)
            if denied(address, 2 if load else 3):
                return trap(5 if load else 7, address)
            if load:
                value = int.from_bytes(memory[address:address + size], 'little')
                if size == 4:
                    value |= BOX
                destination = 32 + rd
                name = 'flw' if size == 4 else 'fld'
            else:
                data = fregs[rs2] & ((1 << (8 * size)) - 1)
                memory[address:address + size] = data.to_bytes(size, 'little')
                lane = address & 7
                trace.append(f'W {address & ~7:016x} {(data << (8 * lane)) & MASK:016x} {((1 << size) - 1) << lane:02x}')
                name = 'fsw' if size == 4 else 'fsd'
        elif fp and (op in (0x43, 0x47, 0x4b, 0x4f) or op == 0x53):
            result = fp_compute(ins, a, fregs[rs1], fregs[rs2], fregs[ins >> 27], fcsr >> 5)
            if result is not None:
                name, to_float, value, flags = result
                destination = 32 + rd if to_float else rd
                if flags:
                    fcsr |= flags
                    trace.append(f'F {flags:02x}')
        elif vector and op == 0x73 and f3 in (1, 2, 3, 5, 6, 7) and (ins >> 20) in vec_ref.VECTOR_CSRS:
            csr = ins >> 20
            old = vst.csr_read(csr)
            source = rs1 if f3 >= 5 else a
            kind = f3 & 3
            new = source if kind == 1 else old | source if kind == 2 else old & ~source
            try:
                if kind == 1 or rs1 != 0:
                    trace.append(vst.csr_write(csr, new & MASK))
                value, destination = old, rd
                name = ('', 'csrrw', 'csrrs', 'csrrc', '', 'csrrwi', 'csrrsi', 'csrrci')[f3]
            except vec_ref.Illegal:
                name = None
        elif fp and op == 0x73 and f3 in (1, 2, 3, 5, 6, 7) and (ins >> 20) in (1, 2, 3):
            # Zicsr on the FP CSRs only (fflags 0x001, frm 0x002, fcsr 0x003).
            csr = ins >> 20
            old = fcsr & 0x1f if csr == 1 else fcsr >> 5 if csr == 2 else fcsr
            source = rs1 if f3 >= 5 else a
            kind = f3 & 3
            writes = kind == 1 or rs1 != 0
            new = source if kind == 1 else old | source if kind == 2 else old & ~source
            if writes:
                if csr == 1:
                    fcsr = (fcsr & 0xe0) | (new & 0x1f)
                elif csr == 2:
                    fcsr = (fcsr & 0x1f) | (new & 7) << 5
                else:
                    fcsr = new & 0xff
                trace.append(f'C 003 {fcsr:016x}')
            value, destination = old, rd
            name = ('', 'csrrw', 'csrrs', 'csrrc', '', 'csrrwi', 'csrrsi', 'csrrci')[f3]
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
        if destination >= 32:
            fregs[destination - 32] = value
        elif destination:
            regs[destination] = value
        else:
            value = 0
        trace.append(f'R {pc:016x} {ins:08x} {destination:02x} {value:016x} {nxt:016x}')
        coverage.add(name)
        pc = nxt
    raise RuntimeError('Reference instruction budget exceeded')
