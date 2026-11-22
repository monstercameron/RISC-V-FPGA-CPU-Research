// SPDX-License-Identifier: MIT
// Project-owned "lab" test environment for riscv-tests (riscv-software-src/riscv-tests).
// It replaces riscv-test-env's p/riscv_test.h for this project's terminal laboratory EEI
// (cpu/architecture.md sections 3 and 4): 16 KiB RAM at 0x0, start at PC 0 with all registers 0,
// no machine-mode CSRs, and every trap halts the core with a sticky (cause, pc, tval) record.
// Original work, not derived from riscv-test-env's code: only the macro names and the TESTNUM
// convention (gp) are the interface that the riscv-tests sources expect.
//
// Pass/fail protocol, read from the golden model's final trap record and registers:
//   PASS: gp = 1, a7 = 93, a0 = 0, then ECALL                -> trap cause 11
//   FAIL: gp = (testnum << 1) | 1, a7 = 93, a0 = gp, EBREAK  -> trap cause 3
// Any other trap (illegal instruction, misaligned, access fault) ends the run early; the runner
// treats it as a failure unless sim/cpu/riscv_tests/run_riscv_tests.py lists it as expected.
// There is no tohost/fromhost: the halt is the core's own terminal trap.
#ifndef LAB_RISCV_TEST_H
#define LAB_RISCV_TEST_H

#define TESTNUM gp

// U: nothing to set up. UF: there is no mstatus (with the F and D option the environment behaves
// as if mstatus.FS were permanently Dirty, architecture section 1), so only fcsr (0x003) is cleared.
#define RVTEST_RV64U  .macro init; .endm
#define RVTEST_RV32U  .macro init; .endm
#define RVTEST_RV64UF .macro init; csrwi fcsr, 0; .endm
#define RVTEST_RV32UF .macro init; csrwi fcsr, 0; .endm
// The lab EEI has no vector, machine-mode or supervisor environment: such tests refuse to build.
#define RVTEST_RV64UV  .error "lab env: no vector environment"
#define RVTEST_RV64UVX .error "lab env: no vector environment"
#define RVTEST_RV64M   .error "lab env: no M-mode (needs the C1 privilege stage)"
#define RVTEST_RV64S   .error "lab env: no S-mode"
#define RVTEST_RV32M   .error "lab env: no M-mode (needs the C1 privilege stage)"
#define RVTEST_RV32S   .error "lab env: no S-mode"

#define RVTEST_CODE_BEGIN        \
        .section .text.init;     \
        .align 6;                \
        .globl _start;           \
_start:                          \
        li TESTNUM, 0;           \
        init;                    \
        j 1f;                    \
        .align 2;                \
1:

#define RVTEST_CODE_END          \
        unimp

#define RVTEST_PASS              \
        fence;                   \
        li TESTNUM, 1;           \
        li a7, 93;               \
        li a0, 0;                \
        ecall

#define RVTEST_FAIL              \
        fence;                   \
        sll TESTNUM, TESTNUM, 1; \
        or TESTNUM, TESTNUM, 1;  \
        li a7, 93;               \
        addi a0, TESTNUM, 0;     \
        ebreak

#define EXTRA_DATA

#define RVTEST_DATA_BEGIN        \
        EXTRA_DATA               \
        .align 4; .global begin_signature; begin_signature:

#define RVTEST_DATA_END          \
        .align 4; .global end_signature; end_signature:

#endif
