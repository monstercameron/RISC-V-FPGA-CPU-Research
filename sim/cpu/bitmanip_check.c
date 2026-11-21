/* SPDX-License-Identifier: MIT
 * Independent check of the B extension (architecture 0.6.0).
 *
 * Every operation is written as plain C. Built for rv64im, the compiler implements
 * it with base instructions; built with Zba/Zbb/Zbs, it emits B instructions for
 * the same expressions. check_bitmanip.py runs both builds on the core and requires
 * identical results, so the B hardware is checked against the compiler's reading of
 * C, not against the project's own reference model alone.
 *
 * Results: mailbox word 2 + k holds the checksum of operation group k.
 */
#include "bench.h"

typedef unsigned long long u64;
typedef long long i64;
typedef unsigned int u32;
typedef int i32;

static volatile u64 values[] = {
    0, 1, 0xffffffffffffffffull, 0x8000000000000000ull, 0x7fffffffffffffffull, 0x80000000ull,
    0x1122334480000080ull, 0x00ff00ff00ff0000ull, 0x0000000100000000ull, 0xdeadbeefcafebabeull,
    37, 0x8001ffffull, 0x0000ff0000000000ull, 0x8000000080000000ull,
};
static volatile unsigned shifts[] = {1, 5, 31, 32, 33, 63};
#define N_VALUES (sizeof values / sizeof values[0])
#define N_SHIFTS (sizeof shifts / sizeof shifts[0])

static u64 mix(u64 h, u64 v) { return ((h << 7) | (h >> 57)) ^ v ^ 0x9e3779b97f4a7c15ull; }

#ifdef __riscv_zbb
static u64 leading(u64 x) { return x ? (u64)__builtin_clzll(x) : 64; }
static u64 trailing(u64 x) { return x ? (u64)__builtin_ctzll(x) : 64; }
static u64 ones(u64 x) { return (u64)__builtin_popcountll(x); }
static u64 leading32(u32 x) { return x ? (u64)__builtin_clz(x) : 32; }
static u64 trailing32(u32 x) { return x ? (u64)__builtin_ctz(x) : 32; }
static u64 ones32(u32 x) { return (u64)__builtin_popcount(x); }
static u64 byteswap(u64 x) { return __builtin_bswap64(x); }
static u64 or_combine(u64 x) { return __builtin_riscv_orc_b_64(x); }
#else
static u64 leading(u64 x) { u64 n = 0; while (n < 64 && !((x << n) >> 63)) ++n; return n; }
static u64 trailing(u64 x) { u64 n = 0; while (n < 64 && !((x >> n) & 1)) ++n; return n; }
static u64 ones(u64 x) { u64 n = 0; while (x) { n += x & 1; x >>= 1; } return n; }
static u64 leading32(u32 x) { u64 n = 0; while (n < 32 && !((x << n) >> 31)) ++n; return n; }
static u64 trailing32(u32 x) { u64 n = 0; while (n < 32 && !((x >> n) & 1)) ++n; return n; }
static u64 ones32(u32 x) { u64 n = 0; while (x) { n += x & 1; x >>= 1; } return n; }
static u64 byteswap(u64 x) {
    u64 r = 0;
    for (int i = 0; i < 8; ++i) r |= ((x >> (8 * i)) & 0xff) << (8 * (7 - i));
    return r;
}
static u64 or_combine(u64 x) {
    u64 r = 0;
    for (int i = 0; i < 8; ++i) if ((x >> (8 * i)) & 0xff) r |= 0xffull << (8 * i);
    return r;
}
#endif

int main(void) {
    u64 group[16] = {0};
    for (unsigned i = 0; i < N_VALUES; ++i) {
        u64 x = values[i];
        u32 xw = (u32)x;
        group[0] = mix(group[0], leading(x) | trailing(x) << 8 | ones(x) << 16);
        group[1] = mix(group[1], leading32(xw) | trailing32(xw) << 8 | ones32(xw) << 16);
        group[2] = mix(group[2], (u64)(i64)(signed char)x ^ (u64)(i64)(short)x << 1 ^ (u64)(unsigned short)x << 2);
        group[3] = mix(group[3], byteswap(x) ^ or_combine(x));
        for (unsigned j = 0; j < N_VALUES; ++j) {
            u64 y = values[j];
            group[4] = mix(group[4], (x & ~y) ^ ((x | ~y) << 1) ^ ~(x ^ y));
            group[5] = mix(group[5], ((i64)x < (i64)y ? x : y) ^ ((i64)x > (i64)y ? x : y) << 1 ^
                                     (x < y ? x : y) << 2 ^ (x > y ? x : y) << 3);
            group[6] = mix(group[6], (y + (x << 1)) ^ (y + (x << 2)) << 1 ^ (y + (x << 3)) << 2);
            group[7] = mix(group[7], (y + (u64)xw) ^ (y + ((u64)xw << 1)) << 1 ^ (y + ((u64)xw << 3)) << 2);
            unsigned n = (unsigned)y & 63, nw = (unsigned)y & 31;
            group[8] = mix(group[8], ((x << n) | (x >> ((64 - n) & 63))) ^ ((x >> n) | (x << ((64 - n) & 63))) << 1);
            group[9] = mix(group[9], (u64)(i64)(i32)((xw << nw) | (xw >> ((32 - nw) & 31))) ^
                                     (u64)(i64)(i32)((xw >> nw) | (xw << ((32 - nw) & 31))) << 1);
            group[10] = mix(group[10], (x | (1ull << n)) ^ (x & ~(1ull << n)) << 1 ^ (x ^ (1ull << n)) << 2 ^
                                       ((x >> n) & 1) << 3);
        }
        for (unsigned k = 0; k < N_SHIFTS; ++k) {
            unsigned s = shifts[k];
            group[11] = mix(group[11], ((x << s) | (x >> (64 - s))) ^ ((u64)xw << s) ^ (x | (1ull << s)) ^
                                       (x & ~(1ull << s)) ^ (x ^ (1ull << s)) ^ ((x >> s) & 1));
        }
    }
    for (unsigned g = 0; g < 12; ++g) bench_result(g, group[g]);
    return 0;
}
