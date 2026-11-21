# SPDX-License-Identifier: MIT
.section .text.start,"ax",@progbits
.globl _start
.option norvc
.option norelax
_start:
    lui sp, 4
    call main
    ebreak
1:  j 1b
