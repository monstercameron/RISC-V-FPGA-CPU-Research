/* SPDX-License-Identifier: MIT
 * Replaces riscv-tests' benchmarks/common/util.h for this core.
 * The core has no CSRs yet, so read_csr() cannot read mcycle. Timing comes
 * from start/stop marker writes that the testbench counts instead.
 */
#ifndef BENCH_UTIL_H
#define BENCH_UTIL_H

void setStats(int enable);
long bench_timer(void);

/* Dhrystone's Start_Timer()/Stop_Timer() expand to read_csr(mcycle). */
#define read_csr(reg) bench_timer()

#endif
