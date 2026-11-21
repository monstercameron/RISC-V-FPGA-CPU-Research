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
