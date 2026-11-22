/* SPDX-License-Identifier: MIT */
/* Shim libc header for the bare-metal QuickJS-ng benchmark (sim/cpu/bench/js; original code). */
#ifndef SHIM_STDIO_H
#define SHIM_STDIO_H
#include "shimc.h"
typedef struct FILE FILE;
extern FILE *stdout, *stderr, *stdin;
#define EOF (-1)
int printf(const char *, ...); int fprintf(FILE *, const char *, ...);
int snprintf(char *, size_t, const char *, ...); int vsnprintf(char *, size_t, const char *, va_list);
int sprintf(char *, const char *, ...); int vfprintf(FILE *, const char *, va_list); int vprintf(const char*, va_list);
int putchar(int); int fputc(int, FILE *); int putc(int, FILE *); int fputs(const char *, FILE *); int puts(const char *);
size_t fwrite(const void *, size_t, size_t, FILE *); int fflush(FILE *);
#endif
