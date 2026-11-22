/* SPDX-License-Identifier: MIT
 * Lab-environment linker script for riscv-tests: one 16 KiB RWX region at 0x0, the laboratory
 * RAM of tb_core.sv and the sample SoC (cpu/architecture.md section 3). */
OUTPUT_ARCH("riscv")
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x0, LENGTH = 16K }
SECTIONS
{
  . = 0x0;
  .text.init : { *(.text.init) } > RAM
  .text : { *(.text .text.*) } > RAM
  . = ALIGN(0x100);
  .data : { *(.rodata .rodata.* .sdata .sdata.* .data .data.*) } > RAM
  .bss : { *(.sbss .sbss.* .bss .bss.* COMMON) } > RAM
  _end = .;
}
