# SPDX-License-Identifier: MIT
# Teaching example for a kernel/firmware port with equivalent MMIO semantics.
# This is not a driver: see README.md and the existing ABI/adapter contracts.
.text
.option norvc
.option norelax

# unsigned try_submit_command(volatile void *bar, const uint32_t *command)
# Preconditions: driver lock held, session ready, registered/sealed inputs,
# validated 256-byte ABI1 command, OS DMA visibility already established.
# Returns 0 after ringing (NOT completion), 1 busy, 2 offline.
# a0=board-mapped BAR, a1=256-byte command; no guessed physical address.
.globl try_submit_command
.type try_submit_command,@function
try_submit_command:
    lw t0, 0x604(a0)
    andi t1, t0, 64
    bnez t1, .Loffline
    andi t1, t0, 1
    beqz t1, .Lbusy
    fence iorw, iorw
    addi t0, a0, 0x100
    li t1, 64
.Lcopy_command:
    lw t2, 0(a1)
    sw t2, 0(t0)
    addi a1, a1, 4
    addi t0, t0, 4
    addi t1, t1, -1
    bnez t1, .Lcopy_command
    fence iorw, iorw
    li t0, 1
    sw t0, 0x600(a0)
    li a0, 0
    ret
.Lbusy:
    li a0, 1
    ret
.Loffline:
    li a0, 2
    ret
.size try_submit_command, .-try_submit_command
