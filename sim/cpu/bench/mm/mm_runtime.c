/* SPDX-License-Identifier: MIT
 * Bare-metal harness of the mm benchmark: main(), phase markers and the result
 * mailbox words (mm_bench.h: mm_words). memcpy and memset are here for the
 * compiler's block copies and clears.
 */
#include "bench.h"
#include "mm_bench.h"

typedef __SIZE_TYPE__ size_t;

void *memcpy(void *destination, const void *source, size_t count) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    while (count--) *out++ = *in++;
    return destination;
}

void *memset(void *destination, int value, size_t count) {
    unsigned char *out = destination;
    while (count--) *out++ = (unsigned char)value;
    return destination;
}

void mm_mark(unsigned value) { bench_marker(value); }

int main(void) {
    mm_results r;
    mm_u64 w[16];
    mm_bench_run(&r);
    unsigned n = mm_words(&r, w);
    for (unsigned i = 0; i < n; i++) bench_result(i, w[i]);
    return 0;
}
