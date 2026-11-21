/* SPDX-License-Identifier: MIT */
typedef unsigned long long u64;

/* Volatile makes the CPU load both ones and really execute an addition. */
static volatile u64 left = 1;
static volatile u64 right = 1;

int main(void)
{
    u64 sum = left + right;
    *(volatile u64 *)0x3000 = sum;
    return sum == 2 ? 0 : 1;
}
