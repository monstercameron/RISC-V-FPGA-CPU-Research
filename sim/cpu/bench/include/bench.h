/* SPDX-License-Identifier: MIT
 * Benchmark mailbox shared by the port layer, startup code and testbench.
 *
 * The linker script places the mailbox in the top 256 bytes of RAM:
 *   word 0   marker: 1 when the timed region starts, 2 when it stops
 *   word 1   main()'s return value, written by start.S
 *   word 2+  benchmark-specific results, read by the Python runner
 */
#ifndef BENCH_H
#define BENCH_H

typedef unsigned long long bench_u64;

extern volatile bench_u64 __bench_mailbox[32];

#define BENCH_MARKER_START 1u
#define BENCH_MARKER_STOP 2u

static inline void bench_marker(bench_u64 value) { __bench_mailbox[0] = value; }
static inline void bench_result(unsigned index, bench_u64 value) { __bench_mailbox[2 + index] = value; }

#endif
