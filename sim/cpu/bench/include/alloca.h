/* SPDX-License-Identifier: MIT
 * Minimal freestanding alloca.h for bare-metal benchmarks.
 */
#ifndef BENCH_ALLOCA_H
#define BENCH_ALLOCA_H

#define alloca(size) __builtin_alloca(size)

#endif
