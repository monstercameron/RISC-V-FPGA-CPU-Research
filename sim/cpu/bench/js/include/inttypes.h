/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_INTTYPES_H
#define SHIM_INTTYPES_H
#include <stdint.h>
#define PRId64 "ld"
#define PRIu64 "lu"
#define PRIx64 "lx"
#define PRIX64 "lX"
#define PRId32 "d"
#define PRIu32 "u"
#define PRIx32 "x"
#define PRIu16 "u"
#define PRIdPTR "ld"
#define PRIuPTR "lu"
#define PRIxPTR "lx"
#endif
