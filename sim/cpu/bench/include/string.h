/* SPDX-License-Identifier: MIT
 * Minimal freestanding string.h for bare-metal benchmarks.
 */
#ifndef BENCH_STRING_H
#define BENCH_STRING_H

typedef __SIZE_TYPE__ size_t;

void *memcpy(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);
char *strcpy(char *destination, const char *source);
int strcmp(const char *left, const char *right);

#endif
