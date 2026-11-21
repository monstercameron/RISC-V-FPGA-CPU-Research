/* SPDX-License-Identifier: MIT */
typedef long long i64;
static volatile i64 numbers[5] = {8, -3, 12, 5, -2};

int main(void)
{
    i64 sum = 0;
    i64 minimum = numbers[0];
    i64 maximum = minimum;
    for (unsigned i = 0; i < 5; ++i) {
        i64 value = numbers[i];
        sum += value;
        if (value < minimum)
            minimum = value;
        if (value > maximum)
            maximum = value;
    }
    volatile i64 *output = (volatile i64 *)0x3000;
    output[0] = sum;
    output[1] = minimum;
    output[2] = maximum;
    return sum == 20 && minimum == -3 && maximum == 12 ? 0 : 1;
}
