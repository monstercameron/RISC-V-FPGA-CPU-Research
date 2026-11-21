/* SPDX-License-Identifier: MIT */
typedef unsigned long long u64;
static volatile u64 numbers[6] = {9, 3, 7, 1, 5, 2};

int main(void)
{
    for (unsigned i = 1; i < 6; ++i) {
        u64 value = numbers[i];
        unsigned j = i;
        while (j > 0 && numbers[j - 1] > value) {
            numbers[j] = numbers[j - 1];
            --j;
        }
        numbers[j] = value;
    }
    volatile u64 *output = (volatile u64 *)0x3000;
    for (unsigned i = 0; i < 6; ++i)
        output[i] = numbers[i];
    return output[0] == 1 && output[1] == 2 && output[2] == 3 &&
           output[3] == 5 && output[4] == 7 && output[5] == 9 ? 0 : 1;
}
