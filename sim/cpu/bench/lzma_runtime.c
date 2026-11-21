/* SPDX-License-Identifier: MIT
 * Freestanding memory routines for the LZMA benchmark (lzma_bench.c).
 *
 * The LZMA SDK uses memcpy, memmove and memset, and the compiler emits calls
 * to them for large copies and clears. When source and destination share
 * their alignment modulo 8 these move 8 bytes per step after aligning; other
 * cases go a byte at a time. Every access is naturally aligned, so no access
 * is misaligned. The cost of these routines is part of the benchmark result.
 * Dhrystone keeps its own runtime.c; this file is linked only into the LZMA
 * benchmark.
 */
typedef __SIZE_TYPE__ size_t;
typedef __UINTPTR_TYPE__ uptr;
typedef unsigned long long __attribute__((may_alias)) word64;

void *memcpy(void *destination, const void *source, size_t count) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    if ((((uptr)out ^ (uptr)in) & 7) == 0) {
        while (count && ((uptr)out & 7)) {
            *out++ = *in++;
            --count;
        }
        word64 *wo = (word64 *)out;
        const word64 *wi = (const word64 *)in;
        while (count >= 8) {
            *wo++ = *wi++;
            count -= 8;
        }
        out = (unsigned char *)wo;
        in = (const unsigned char *)wi;
    }
    while (count--) *out++ = *in++;
    return destination;
}

void *memmove(void *destination, const void *source, size_t count) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    if (out <= in || out >= in + count) return memcpy(destination, source, count);
    out += count;
    in += count;
    while (count--) *--out = *--in;
    return destination;
}

void *memset(void *destination, int value, size_t count) {
    unsigned char *out = destination;
    const unsigned char byte = (unsigned char)value;
    while (count && ((uptr)out & 7)) {
        *out++ = byte;
        --count;
    }
    unsigned long long word = 0x0101010101010101ull * byte;
    word64 *wo = (word64 *)out;
    while (count >= 8) {
        *wo++ = word;
        count -= 8;
    }
    out = (unsigned char *)wo;
    while (count--) *out++ = byte;
    return destination;
}

int memcmp(const void *left, const void *right, size_t count) {
    const unsigned char *a = left, *b = right;
    for (; count; --count, ++a, ++b)
        if (*a != *b) return (int)*a - (int)*b;
    return 0;
}
