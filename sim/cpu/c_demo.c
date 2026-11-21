/* SPDX-License-Identifier: MIT
 * Bare-metal workload for our RV64I core. No libc, OS, multiply or divide.
 * Volatile inputs make the CPU do the work instead of constant-folding it.
 */
typedef unsigned long long u64;
typedef long long i64;
typedef unsigned int u32;

static volatile i64 input[16] = {
    -17, 42, 0, 99, -5, 42, 7, 1, 1024, -300, 18, 9, -1, 256, 3, 64
};
static volatile unsigned char message[] =
    "Custom RV64 core: C -> ELF -> BRAM -> RTL.\n";
static volatile unsigned fibonacci_iterations = 40;

int main(void)
{
    i64 sorted[16];
    for (unsigned i = 0; i < 16; ++i)
        sorted[i] = input[i];

    /* Insertion sort exercises signed comparisons, loops and stack memory. */
    for (unsigned i = 1; i < 16; ++i) {
        i64 value = sorted[i];
        unsigned j = i;
        while (j && sorted[j - 1] > value) {
            sorted[j] = sorted[j - 1];
            --j;
        }
        sorted[j] = value;
    }

    i64 sum = 0;
    u64 fingerprint = 0;
    u64 status = 0;
    for (unsigned i = 0; i < 16; ++i) {
        sum += sorted[i];
        fingerprint = ((fingerprint << 7) | (fingerprint >> 57)) ^ (u64)sorted[i];
        if (i && sorted[i - 1] > sorted[i])
            status |= 1;
    }

    u64 a = 0, b = 1;
    unsigned iterations = fibonacci_iterations;
    for (unsigned i = 0; i < iterations; ++i) {
        u64 next = a + b;
        a = b;
        b = next;
    }

    /* CRC-32/ISO-HDLC, the same result as zlib.crc32(message repeated 8x). */
    u32 crc = ~0u;
    for (unsigned repeat = 0; repeat < 8; ++repeat) {
        for (unsigned i = 0; i < sizeof(message) - 1; ++i) {
            crc ^= message[i];
            for (unsigned bit = 0; bit < 8; ++bit)
                crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
        }
    }
    crc = ~crc;
    if (sum != 1242 || sorted[0] != -300 || sorted[15] != 1024)
        status |= 2;
    if (a != 102334155ull || crc != 0x97f65c54u || fingerprint != 0x87101f1288184441ull)
        status |= 4;

    /* The testbench reads this mailbox after _start executes EBREAK. */
    volatile u64 *result = (volatile u64 *)0x3000;
    result[1] = status;
    result[2] = (u64)sum;
    result[3] = (u64)sorted[0];
    result[4] = (u64)sorted[15];
    result[5] = a;
    result[6] = crc;
    result[7] = fingerprint;
    result[0] = 0x43505544454d4f31ull; /* "CPUDEMO1", written last */
    return status ? 1 : 0;
}
