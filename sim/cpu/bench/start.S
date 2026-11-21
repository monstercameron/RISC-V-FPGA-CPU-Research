# SPDX-License-Identifier: MIT
# Benchmark startup: stack below the mailbox, clear .bss, run main, record its
# return value in mailbox word 1, then stop with EBREAK.
.section .text.start,"ax",@progbits
.globl _start
.option norvc
.option norelax
_start:
    la sp, __stack_top
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sd zero, 0(t0)
    addi t0, t0, 8
    j 1b
2:  call main
    la t0, __bench_mailbox
    sd a0, 8(t0)
    ebreak
3:  j 3b
