/* SPDX-License-Identifier: MIT */
typedef unsigned long long u64;
static volatile u64 limit = 10;

int main(void)
{
    u64 sum = 0;
    u64 count = 0;
    /* Reread the volatile limit so this remains a loop, not a formula. */
    for (u64 number = 1; number <= limit; ++number) {
        sum += number;
        ++count;
    }
    volatile u64 *output = (volatile u64 *)0x3000;
    output[0] = sum;
    output[1] = count;
    return sum == 55 && count == 10 ? 0 : 1;
}
