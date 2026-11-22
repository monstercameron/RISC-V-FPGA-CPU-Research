/* Linker script for the S1 directed programs: code and data at 0x8000_0000 (riscv-tests' p layout).
   Our own text. SPDX-License-Identifier: MIT */
OUTPUT_ARCH("riscv")
ENTRY(_start)
SECTIONS
{
  . = 0x80000000;
  .text.init : { *(.text.init) }
  .text : { *(.text) }
  . = ALIGN(0x1000);
  .tohost : { *(.tohost) }
  .data : { *(.data) }
  .bss : { *(.bss) }
}
