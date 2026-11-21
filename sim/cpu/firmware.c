/* SPDX-License-Identifier: MIT
 * Small compiled bare-metal exercise, no libraries, floating point or multiply.
 * Result lives at 0x3000; EBREAK terminates through the laboratory EEI.
 */
typedef unsigned long long u64;
static volatile u64 input[8] = {1, 2, 3, 4, 5, 6, 7, 8};
int main(void) {
    u64 sum = 0;
    for (unsigned i = 0; i < 8; ++i) sum += input[i];
    *(volatile u64 *)0x3000 = sum;
    *(volatile u64 *)0x3008 = (sum << 32) | (sum ^ 0x5a);
    return sum == 36 ? 0 : 1;
}
