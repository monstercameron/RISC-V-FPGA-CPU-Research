/* SPDX-License-Identifier: MIT
 * Minimal freestanding stdio.h for bare-metal benchmarks. There is no
 * console: printf() accepts its arguments and prints nothing.
 */
#ifndef BENCH_STDIO_H
#define BENCH_STDIO_H

int printf(const char *format, ...);

#endif
