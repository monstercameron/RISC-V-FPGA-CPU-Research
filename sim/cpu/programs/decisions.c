/* SPDX-License-Identifier: MIT */
typedef long long i64;
static volatile i64 inputs[2] = {-7, 4};

int main(void)
{
    volatile i64 *output = (volatile i64 *)0x3000;
    for (unsigned i = 0; i < 2; ++i) {
        i64 number = inputs[i];
        i64 answer;
        if (number < 0)
            answer = -number;
        else
            answer = number + 10;
        output[i] = answer;
    }
    return output[0] == 7 && output[1] == 14 ? 0 : 1;
}
