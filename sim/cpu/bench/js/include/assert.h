/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_ASSERT_H
#define SHIM_ASSERT_H
_Noreturn void __shim_assert(const char *, const char *, int);
#ifdef NDEBUG
#define assert(x) ((void)0)
#else
#define assert(x) ((x) ? (void)0 : __shim_assert(#x, __FILE__, __LINE__))
#endif
#define static_assert _Static_assert
#endif
