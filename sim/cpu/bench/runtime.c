/* SPDX-License-Identifier: MIT
 * Freestanding runtime for bare-metal benchmarks on rv64i.
 *
 * The core has no M extension and this LLVM installation ships no RISC-V
 * compiler-rt, so the compiler's multiply/divide helper calls are provided
 * here. Their cost is part of every benchmark result and must be reported
 * with it. They are written without '*', '/' or '%' so they never call
 * themselves.
 */
typedef unsigned long long u64;
typedef long long i64;
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

#ifndef BENCH_FAST_STRINGS
/* Reference runtime: one byte per iteration. Results built with it are the ones
 * compared across core versions. */
char *strcpy(char *destination, const char *source) {
    char *out = destination;
    while ((*out++ = *source++) != '\0') {
    }
    return destination;
}

int strcmp(const char *left, const char *right) {
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    while (*a != '\0' && *a == *b) {
        ++a;
        ++b;
    }
    return (int)*a - (int)*b;
}
#else
/* Fast runtime (build option --runtime fast), the technique C libraries use:
 * align the destination (strcpy) or the first string (strcmp) a byte at a time,
 * then move 8 bytes per step. When the other string is not aligned the same way,
 * read its aligned words and shift neighbouring words together. Stop at the first
 * word holding a zero byte (or a difference) and finish a byte at a time. Every
 * word read is aligned, so no read crosses the end of memory. Results built with
 * this runtime are labelled and are not compared with the reference runtime. */
typedef unsigned long long __attribute__((may_alias)) word64;
typedef __UINTPTR_TYPE__ uptr;

#define ONES64 0x0101010101010101ull
#define HIGHS64 0x8080808080808080ull
#ifdef __riscv_zbb
/* With Zbb, orc.b turns every non-zero byte into 0xff: a zero byte leaves a hole. */
#define HAS_ZERO64(w) (__builtin_riscv_orc_b_64(w) != ~0ull)
#else
#define HAS_ZERO64(w) ((((w) - ONES64) & ~(w) & HIGHS64) != 0)
#endif

char *strcpy(char *destination, const char *source) {
    char *out = destination;
    while (((uptr)out & 7) != 0)
        if ((*out++ = *source++) == '\0') return destination;
    unsigned shift = (unsigned)((uptr)source & 7) * 8;
    word64 *to = (word64 *)out;
    if (shift == 0) {
        const word64 *in = (const word64 *)source;
        while (!HAS_ZERO64(*in)) *to++ = *in++;
        source = (const char *)in;
    } else {
        const word64 *in = (const word64 *)((uptr)source & ~(uptr)7);
        u64 low = *in++;
        for (;;) {
            u64 high = *in;
            u64 word = (low >> shift) | (high << (64 - shift));
            if (HAS_ZERO64(word)) break;
            *to++ = word;
            source += 8;
            low = high;
            ++in;
        }
    }
    out = (char *)to;
    while ((*out++ = *source++) != '\0') {
    }
    return destination;
}

int strcmp(const char *left, const char *right) {
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    while (((uptr)a & 7) != 0) {
        if (*a == '\0' || *a != *b) return (int)*a - (int)*b;
        ++a;
        ++b;
    }
    unsigned shift = (unsigned)((uptr)b & 7) * 8;
    const word64 *wa = (const word64 *)a;
    if (shift == 0) {
        const word64 *wb = (const word64 *)b;
        while (*wa == *wb && !HAS_ZERO64(*wa)) {
            ++wa;
            ++wb;
        }
        b = (const unsigned char *)wb;
    } else {
        const word64 *in = (const word64 *)((uptr)b & ~(uptr)7);
        u64 low = *in++;
        for (;;) {
            u64 high = *in;
            u64 word = (low >> shift) | (high << (64 - shift));
            u64 mine = *wa;
            if (mine != word || HAS_ZERO64(mine)) break;
            ++wa;
            b += 8;
            low = high;
            ++in;
        }
    }
    a = (const unsigned char *)wa;
    while (*a != '\0' && *a == *b) {
        ++a;
        ++b;
    }
    return (int)*a - (int)*b;
}
#endif

/* There is no console. Arguments are accepted and ignored. */
int printf(const char *format, ...) {
    (void)format;
    return 0;
}

/* Shift-and-add multiply; the loop runs once per bit of the smaller operand. */
i64 __muldi3(i64 left, i64 right) {
    u64 a = (u64)left, b = (u64)right, product = 0;
    if (a < b) {
        u64 swap = a;
        a = b;
        b = swap;
    }
    while (b != 0) {
        if (b & 1) product += a;
        a <<= 1;
        b >>= 1;
    }
    return (i64)product;
}

/* Shift-subtract division, starting from the divisor's aligned position.
 * Division by zero follows the RISC-V M convention: all-ones quotient,
 * remainder equal to the dividend. */
static u64 udivmod(u64 dividend, u64 divisor, u64 *remainder) {
    u64 quotient = 0, bit = 1;
    if (divisor == 0) {
        *remainder = dividend;
        return ~0ull;
    }
    while (divisor < dividend && (divisor >> 63) == 0) {
        divisor <<= 1;
        bit <<= 1;
    }
    while (bit != 0) {
        if (dividend >= divisor) {
            dividend -= divisor;
            quotient |= bit;
        }
        divisor >>= 1;
        bit >>= 1;
    }
    *remainder = dividend;
    return quotient;
}

static u64 magnitude(i64 value) { return value < 0 ? 0 - (u64)value : (u64)value; }

u64 __udivdi3(u64 dividend, u64 divisor) {
    u64 remainder;
    return udivmod(dividend, divisor, &remainder);
}

u64 __umoddi3(u64 dividend, u64 divisor) {
    u64 remainder;
    udivmod(dividend, divisor, &remainder);
    return remainder;
}

i64 __divdi3(i64 dividend, i64 divisor) {
    u64 remainder;
    u64 quotient = udivmod(magnitude(dividend), magnitude(divisor), &remainder);
    return ((dividend < 0) != (divisor < 0)) ? (i64)(0 - quotient) : (i64)quotient;
}

i64 __moddi3(i64 dividend, i64 divisor) {
    u64 remainder;
    udivmod(magnitude(dividend), magnitude(divisor), &remainder);
    return dividend < 0 ? (i64)(0 - remainder) : (i64)remainder;
}
