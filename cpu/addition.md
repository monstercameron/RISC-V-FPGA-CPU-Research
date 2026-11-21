# 1 + 1 on our CPU

**Observed result: 2.** LLVM compiled the C below for RV64I, and the custom RTL core executed it with synchronous RAM. The run completed in **32 clocks** on architecture 0.4.0 (48 on the first 0.1.0 core), with **13 retired instructions**, one RAM write and 15 events matching the independent sequential reference. EBREAK ends the program without retiring.

## C source

This is the actual [source file](../sim/cpu/add_one.c). Volatile inputs force runtime loads and an actual ADD; the compiler cannot replace the calculation with a precomputed 2.

```c
/* SPDX-License-Identifier: MIT */
typedef unsigned long long u64;

/* Volatile makes the CPU load both ones and really execute an addition. */
static volatile u64 left = 1;
static volatile u64 right = 1;

int main(void)
{
    u64 sum = left + right;
    *(volatile u64 *)0x3000 = sum;
    return sum == 2 ? 0 : 1;
}
```

The result goes to RAM address `0x3000`. Returning 0 reports success to the testbench; that return status is separate from the arithmetic answer 2.

## Actual compiled assembly

The executable includes the startup routine that sets the stack and calls `main`. This listing is from `llvm-objdump`, with the 32-bit instruction words beside their addresses. `snez` and `ret` are assembly aliases for base instructions.

```text
Disassembly of section .text:
0000000000000000 <_start>:
       0: 00004137     	lui	sp, 0x4
       4: 00000097     	auipc	ra, 0x0
       8: 010080e7     	jalr	0x10(ra) <main>
       c: 00100073     	ebreak
      10: 0000006f     	j	0x10 <_start+0x10>
0000000000000014 <main>:
      14: 00000517     	auipc	a0, 0x0
      18: 02c50513     	addi	a0, a0, 0x2c
      1c: 00053583     	ld	a1, 0x0(a0)
      20: 00853503     	ld	a0, 0x8(a0)
      24: 00b505b3     	add	a1, a0, a1
      28: ffe58513     	addi	a0, a1, -0x2
      2c: 00a03533     	snez	a0, a0
      30: 00003637     	lui	a2, 0x3
      34: 00b63023     	sd	a1, 0x0(a2)
      38: 00008067     	ret
```

## Binary instruction words

Each row below is an actual instruction in the executable, with bit 31 on the left and bit 0 on the right. The word at `0x0010` is an unexecuted fallback loop after EBREAK.

```text
Address   Instruction bits (31..0)           Hex       Assembly
0x0000    00000000000000000100000100110111  00004137  lui sp, 0x4
0x0004    00000000000000000000000010010111  00000097  auipc ra, 0x0
0x0008    00000001000000001000000011100111  010080e7  jalr 0x10(ra) <main>
0x000c    00000000000100000000000001110011  00100073  ebreak
0x0010    00000000000000000000000001101111  0000006f  j 0x10 <_start+0x10>
0x0014    00000000000000000000010100010111  00000517  auipc a0, 0x0
0x0018    00000010110001010000010100010011  02c50513  addi a0, a0, 0x2c
0x001c    00000000000001010011010110000011  00053583  ld a1, 0x0(a0)
0x0020    00000000100001010011010100000011  00853503  ld a0, 0x8(a0)
0x0024    00000000101101010000010110110011  00b505b3  add a1, a0, a1
0x0028    11111111111001011000010100010011  ffe58513  addi a0, a1, -0x2
0x002c    00000000101000000011010100110011  00a03533  snez a0, a0
0x0030    00000000000000000011011000110111  00003637  lui a2, 0x3
0x0034    00000000101101100011000000100011  00b63023  sd a1, 0x0(a2)
0x0038    00000000000000001000000001100111  00008067  ret
```

The addition itself is at **PC `0x0024`**:

```text
Assembly:  add a1, a0, a1       # x11 = x10 + x11
Hex word:  0x00b505b3
Bits:      0000000 01011 01010 000 01011 0110011
Fields:    funct7  rs2   rs1   f3  rd    opcode
```

The instruction is stored in RAM as bytes **`b3 05 b5 00`**, because this core uses little-endian byte order. The 32-bit instruction encoding is distinct from the 64-bit operand/result values.

## What the hardware actually did

| Clock | Observed action |
|---:|---|
| 28 | ADD reads x10=1 and x11=1; x11 becomes 2 |
| 41 | RAM accepts the store and writes 2 at `0x3000` |
| 42 | The CPU receives acknowledgement and retires the store |
| 48 | EBREAK stops the core after `main` returned 0 |

The two initialized inputs live at `0x0040` and `0x0048`. The firmware image is 80 bytes, including instructions, alignment padding and input data. The [verification record](addition-verification.json) includes the firmware/source hashes and the observed ADD operands, destination and result.

## Watch or rerun it

Run `.\sim\cpu\run_visualizer.ps1` from the project, select **1 + 1**, and click **Run simulation**. The C, Assembly and Binary tabs follow the captured program counter. The hardware pane shows instruction bits beside the circuit. Choose **The ADD instruction** to stop on clock 28; **Jump to output** reveals the finished answer.

For a direct rebuild and checked RTL run:

```powershell
python -B sim/cpu/build_visualizer.py --program add
```

The standalone viewer is generated at `cpu/cpu-visualizer.html`. Compiled ELF, raw binary, disassembly, bit listing and clock trace are generated under ignored `build/cpu/visualizer/`. A preserved copy of this addition run is under `build/cpu/addition/`; rebuilding another program replaces only the active visualizer capture. This is RTL simulation of our current core, not physical FPGA execution or full RVA23 certification.
