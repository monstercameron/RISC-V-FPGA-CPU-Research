/* SPDX-License-Identifier: MIT
 * Minimal freestanding string.h for the LZMA benchmark (lzma_runtime.c).
 */
#ifndef BENCH_LZMA_STRING_H
#define BENCH_LZMA_STRING_H

typedef __SIZE_TYPE__ size_t;

void *memcpy(void *destination, const void *source, size_t count);
void *memmove(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);
int memcmp(const void *left, const void *right, size_t count);

#endif
