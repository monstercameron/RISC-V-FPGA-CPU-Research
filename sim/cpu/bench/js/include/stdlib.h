/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_STDLIB_H
#define SHIM_STDLIB_H
#include "shimc.h"
void *malloc(size_t); void free(void *); void *realloc(void *, size_t); void *calloc(size_t, size_t);
_Noreturn void abort(void); _Noreturn void exit(int);
void qsort(void *, size_t, size_t, int (*)(const void *, const void *));
double strtod(const char *, char **); long strtol(const char *, char **, int); unsigned long strtoul(const char*, char**, int);
long long strtoll(const char *, char **, int); unsigned long long strtoull(const char*, char**, int);
int abs(int); long labs(long); long long llabs(long long); int atoi(const char *); char *getenv(const char *);
#endif
