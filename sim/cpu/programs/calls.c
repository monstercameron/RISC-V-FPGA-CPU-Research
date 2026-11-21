/* SPDX-License-Identifier: MIT */
typedef unsigned long long u64;
static volatile u64 input = 5;

/* A volatile local keeps a real stack value alive across each recursive call. */
__attribute__((noinline)) static u64 triangular(u64 n)
{
    volatile u64 saved = n;
    if (n == 0)
        return 0;
    u64 subtotal = triangular(n - 1);
    return saved + subtotal;
}

int main(void)
{
    u64 result = triangular(input);
    *(volatile u64 *)0x3000 = result;
    return result == 15 ? 0 : 1;
}
