# S1 directed program (M-mode, linked at 0x8000_0000, ends through HTIF tohost). Our own text (MIT).
# It does not check itself: every CSR value and every trap's mcause/mepc/mtval goes into registers, and the
# run is compared record by record with Spike and rv_iss configured the same
# (sim/cpu/spike_lockstep.py penv --asm). Covers the WARL fields of the S1 CSR set, read-only and absent CSRs,
# every exception cause the M-only hart can raise, MRET, minstret across issue groups and around ECALL,
# EBREAK and writes, mcycle reads (N records), and a faulting store in the second issue slot.
# SPDX-License-Identifier: MIT
    .section .text.init, "ax"
    .globl _start
_start:
    csrw    minstret, zero              # Spike's boot ROM (0x1000) retired 5 instructions; the core starts here
    la      t0, handler
    csrw    mtvec, t0
    la      s11, resume0                # where a fetch fault resumes
    # ---- WARL walks
    li      t1, -1
    csrw    mtvec, t1
    csrr    a0, mtvec                   # bit 1 reads 0, mode bit 0 kept
    csrw    mtvec, zero
    csrr    a0, mtvec
    li      t1, 0x80000003
    csrw    mtvec, t1
    csrr    a0, mtvec
    la      t0, handler
    csrw    mtvec, t0
    li      t1, -1
    csrw    mstatus, t1
    csrr    a1, mstatus                 # MIE, MPIE, MPP 3
    csrw    mstatus, zero
    csrr    a2, mstatus
    csrrs   a3, mstatus, t1
    csrrc   a3, mstatus, t1
    csrrsi  a3, mstatus, 8
    csrrci  a3, mstatus, 8
    csrr    a4, misa
    csrw    misa, a4                    # its own value (Spike lets software clear bits: a known difference)
    csrr    a4, misa
    csrw    mie, t1
    csrr    a5, mie                     # MSIE, MTIE, MEIE
    csrw    mie, zero
    csrw    mepc, t1
    csrr    a6, mepc                    # bits 1:0 read 0
    csrw    mscratch, t1
    csrr    a7, mscratch
    csrw    mcause, t1
    csrr    s2, mcause
    csrw    mtval, t1
    csrr    s3, mtval
    csrw    mip, t1                     # no writable field (mip is not read: its MTIP is platform state, the
                                        # CLINT's reset mtimecmp, which differs between Spike and the core)
    csrr    s5, mcountinhibit
    csrw    mcountinhibit, t1
    csrr    s5, mcountinhibit
    csrr    s6, mhartid
    csrrs   s6, mhartid, x0             # read-only CSR, no write: legal
    csrrc   s6, mvendorid, x0
    csrrsi  s6, mimpid, 0
    csrr    s6, 0xf15                   # mconfigptr
    csrr    s6, tselect
    csrw    tselect, t1
    csrr    s6, tselect
    csrr    s6, tdata1
    csrr    s6, 0x7a4                   # tinfo
    csrr    s6, 0xb03                   # mhpmcounter3
    csrw    0xb03, t1
    csrr    s6, 0xb03
    csrr    s6, 0x323                   # mhpmevent3
    csrw    0x7a8, t1                   # mcontext: Spike has a writable 13-bit one even with 0 triggers (check)
    csrr    s6, 0x7a8
    # ---- illegal: absent CSRs, writes to read-only ones, SYSTEM encodings
    csrw    mhartid, t1
    csrrs   s7, misa, x0
    csrrsi  s7, mhartid, 1
    csrr    s7, medeleg
    csrr    s7, mideleg
    csrr    s7, satp
    csrr    s7, sstatus
    csrr    s7, mcounteren
    csrr    s7, menvcfg
    csrr    s7, cycle
    csrr    s7, instret
    csrr    s7, time
    csrr    s7, 0x3a0                   # pmpcfg0 (0 PMP entries)
    csrr    s7, 0x3b0                   # pmpaddr0
    csrr    s7, fflags
    csrr    s7, 0x7c0                   # custom
    csrr    s7, 0x5a8                   # scontext (S only)
    csrr    s7, 0x747                   # mseccfg (absent without Smepmp, Zkr, ...)
    .word   0x10200073                  # SRET without S
    .word   0x12000073                  # SFENCE.VMA without S
    .word   0x00000000                  # all-zero word
    .word   0xdead0001                  # low parcel is not a 32-bit encoding: mtval is the 16-bit parcel
    # (no WFI: the core treats it as a no-op, a legal implementation, while Spike waits for an interrupt)
    # ---- the other exceptions
    ebreak
    ecall
    la      t3, data
    lw      t2, 1(t3)                   # misaligned load
    sd      t2, 2(t3)                   # misaligned store
    li      t3, 0x100
    ld      t2, 0(t3)                   # load access fault (no memory there)
    sd      t2, 0(t3)                   # store access fault
    la      t3, mis + 2
    jr      t3                          # misaligned target: cause 0 on the jump
mis:
    nop
    la      s11, resume0
    li      t3, 0x200
    jr      t3                          # fetch access fault, resumes at s11
resume0:
    # ---- MRET: MIE := MPIE, MPIE := 1, MPP stays M
    li      t1, 0x80
    csrw    mstatus, t1                 # MPIE 1, MIE 0
    la      t1, 1f
    csrw    mepc, t1
    mret
1:  csrr    a1, mstatus
    csrw    mstatus, zero
    la      t1, 2f
    csrw    mepc, t1
    mret
2:  csrr    a1, mstatus
    # ---- minstret around issue groups, writes, ECALL and EBREAK
    csrr    s4, minstret
    addi    x8, x8, 1
    addi    x9, x9, 2
    addi    x18, x18, 3
    addi    x19, x19, 4
    addi    x20, x20, 5
    addi    x21, x21, 6
    csrr    s5, minstret
    li      t1, 1000
    csrw    minstret, t1
    csrr    s5, minstret                # 1000: the write wins over its own count
    csrrw   s5, minstret, t1
    csrr    s5, minstret
    csrr    s4, minstret
    ebreak
    csrr    s5, minstret                # the handler's instructions count, the EBREAK does not
    csrr    s4, minstret
    ecall
    csrr    s5, minstret
    # ---- mcycle: reads are the RTL's own values (N records); writes
    csrr    s6, mcycle
    csrw    mcycle, zero
    csrr    s6, mcycle
    # ---- a faulting store in the second slot of a pair (the second pass runs from the instruction cache)
    li      s8, 2
    li      t3, 0x100
    .balign 16
3:  addi    s9, s9, 1
    sd      s9, 0(t3)                   # store access fault, mepc = this store
    addi    s8, s8, -1
    bnez    s8, 3b
    # ---- end
    la      t0, tohost
    li      t1, 1
    sd      t1, 0(t0)
4:  j       4b

    .balign 4
handler:                                # record the trap, return after it (a fetch fault: to s11)
    csrr    t5, mcause
    csrr    t6, mepc
    csrr    s10, mtval
    li      t4, 1
    beq     t5, t4, 5f
    addi    t6, t6, 4
    csrw    mepc, t6
    mret
5:  csrw    mepc, s11
    mret

    .section .data
    .balign 8
data:
    .dword  0x0123456789abcdef, 0xfedcba9876543210
    .section .tohost, "aw"
    .balign 64
    .globl tohost
tohost: .dword 0
    .globl fromhost
fromhost: .dword 0
