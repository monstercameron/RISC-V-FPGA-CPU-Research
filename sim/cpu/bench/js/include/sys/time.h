/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_SYS_TIME_H
#define SHIM_SYS_TIME_H
#include <time.h>
struct timeval { time_t tv_sec; suseconds_t tv_usec; };
int gettimeofday(struct timeval *, void *);
#endif
