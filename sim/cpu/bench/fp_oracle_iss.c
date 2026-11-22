/* SPDX-License-Identifier: MIT
 * rv_iss.c's F/D execution (fp_exec) on a file of instruction vectors, for sim/cpu/fp_oracle.py.
 *
 * Usage: fp_oracle_iss VECTORS RESULTS [--fp-soft] [--host-fz]
 *   VECTORS: records of u32 ins, u8 frm, 3 pad bytes, u64 xa, fa, fb, fc (little-endian, 40 bytes)
 *   RESULTS: records of i8 kind (-1 illegal, 0 x destination, 1 f destination), u8 flags, 6 pad, u64 value
 *   --fp-soft   the exact software arithmetic (rv_iss --fp-soft 1)
 *   --host-fz   AArch64: start from a host FPCR with flush-to-zero on (rv_iss --host-fz 1)
 */
#define RV_ISS_NO_MAIN
#include "rv_iss.c"

int main(int argc, char **argv) {
    if (argc < 3) die("usage: fp_oracle_iss VECTORS RESULTS [--fp-soft] [--host-fz]");
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "--fp-soft")) fp_soft = 1;
        else if (!strcmp(argv[i], "--host-fz")) host_fz = 1;
        else die("unknown option");
    }
#ifdef FP_HW
    if (host_fz) {
        u64 c;
        __asm__ volatile("mrs %0, fpcr" : "=r"(c));
        c = (c | (u64)1 << 24) & ~(u64)2;
        __asm__ volatile("msr fpcr, %0" :: "r"(c));
    }
#endif
    FILE *in = fopen(argv[1], "rb"), *out = fopen(argv[2], "wb");
    if (!in || !out) die("cannot open the vector files");
    setvbuf(in, NULL, _IOFBF, 1 << 20);
    setvbuf(out, NULL, _IOFBF, 1 << 20);
    uint8_t rec[40], res[16];
    while (fread(rec, 1, 40, in) == 40) {
        u32 ins;
        u64 xa, fa, fb, fc, val = 0;
        unsigned fl = 0;
        memcpy(&ins, rec, 4);
        memcpy(&xa, rec + 8, 8); memcpy(&fa, rec + 16, 8); memcpy(&fb, rec + 24, 8); memcpy(&fc, rec + 32, 8);
        int kind = fp_exec(ins, xa, fa, fb, fc, rec[4], &val, &fl);
        memset(res, 0, sizeof res);
        res[0] = (uint8_t)(int8_t)kind;
        res[1] = (uint8_t)fl;
        memcpy(res + 8, &val, 8);
        fwrite(res, 1, 16, out);
    }
    if (fclose(out)) die("write failed");
    fclose(in);
    return 0;
}
