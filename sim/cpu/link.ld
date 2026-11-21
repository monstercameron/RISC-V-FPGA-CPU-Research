OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0, LENGTH = 16K }
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text .text.*) } > ram
  .rodata : { *(.rodata .rodata.*) *(.srodata .srodata.*) } > ram
  .data : { *(.data .data.*) *(.sdata .sdata.*) } > ram
  .bss (NOLOAD) : { *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON) } > ram
  ASSERT(SIZEOF(.bss) == 0, "Starter has no BSS clearing routine")
  ASSERT(. < 0x2000, "Keep firmware below test/signature/stack regions")
}
