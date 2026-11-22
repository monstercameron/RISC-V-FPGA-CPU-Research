/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_ERRNO_H
#define SHIM_ERRNO_H
extern int errno;
#define ENOMEM 12
#define EINVAL 22
#define ERANGE 34
#define EINTR 4
#define ENOENT 2
#define EAGAIN 11
#define ETIMEDOUT 110
#endif
