/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_TIME_H
#define SHIM_TIME_H
#include "shimc.h"
struct timespec { time_t tv_sec; long tv_nsec; };
struct tm { int tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst; long tm_gmtoff; const char *tm_zone; };
#define CLOCK_MONOTONIC 1
#define CLOCK_REALTIME 0
int clock_gettime(int, struct timespec *); time_t time(time_t *);
struct tm *localtime_r(const time_t *, struct tm *); struct tm *gmtime_r(const time_t *, struct tm *);
#endif
