/* SPDX-License-Identifier: LGPL-2.1-or-later
 *
 * 7-Zip benchmark data generator, translated from C++ to C.
 *
 * Derived from 7-Zip 26.06, CPP/7zip/UI/Common/Bench.cpp
 * (https://github.com/ip7z/7zip, commit d3296e39e1f1f92c7b41c0c3848e65640428d42d):
 * class CBaseRandomGenerator and CBenchRandomGenerator::GenerateLz().
 * 7-Zip Copyright (C) 1999-2026 Igor Pavlov. Bench.cpp carries no licence
 * statement of its own, so by 7-Zip's DOC/License.txt it is under the GNU LGPL
 * (version 2.1 or any later version). This file keeps those terms; see
 * licenses/7ZIP-License.txt and licenses/7ZIP-LGPL-2.1.txt. The rest of the
 * benchmark port is MIT; the LZMA SDK files in vendor/lzma/ are public domain.
 *
 * Changes from upstream: C instead of C++ (the class members became a struct
 * and static functions, the buffer is passed in), comments and debug lines
 * dropped. The arithmetic, the types (UInt32, size_t) and the order of random
 * draws are unchanged, so the bytes produced are the same for the same size,
 * dictionary bits and salt.
 */
#include "lzma_bench.h"

typedef struct {
    UInt32 a1, a2, salt;
} BenchRandom;

static void random_init(BenchRandom *g, UInt32 salt) {
    g->salt = salt;
    g->a1 = 362436069;
    g->a2 = 521288629;
}

static UInt32 random_next(BenchRandom *g) {
    return g->salt ^
        (((g->a1 = 36969 * (g->a1 & 0xffff) + (g->a1 >> 16)) << 16) +
         ((g->a2 = 18000 * (g->a2 & 0xffff) + (g->a2 >> 16))));
}

static UInt32 get_val(UInt32 *res, unsigned num_bits) {
    const UInt32 val = *res & (((UInt32)1 << num_bits) - 1);
    *res >>= num_bits;
    return val;
}

static UInt32 get_len(UInt32 *r) {
    const unsigned len = (unsigned)get_val(r, 2);
    return get_val(r, 1 + len);
}

void bench_generate_lz(Byte *buf, size_t buf_size, unsigned dict_bits, UInt32 salt) {
    BenchRandom rg;
    size_t pos = 0;
    size_t rep0 = 1;
    unsigned pos_bits = 1;
    random_init(&rg, salt);

    while (pos < buf_size) {
        UInt32 r = random_next(&rg);
        if (get_val(&r, 1) == 0 || pos < 1024)
            buf[pos++] = (Byte)(r & 0xFF);
        else {
            UInt32 len;
            len = 1 + get_len(&r);

            if (get_val(&r, 3) != 0) {
                len += get_len(&r);

                while (((size_t)1 << pos_bits) < pos)
                    pos_bits++;

                unsigned num_bits_max = dict_bits;
                if (num_bits_max > pos_bits)
                    num_bits_max = pos_bits;

                const unsigned k_add_bits = 6;
                unsigned num_log_bits = 5;
                if (num_bits_max <= (1 << 4) - 1 + k_add_bits)
                    num_log_bits = 4;

                for (;;) {
                    const UInt32 ppp = get_val(&r, num_log_bits) + k_add_bits;
                    r = random_next(&rg);
                    if (ppp > num_bits_max)
                        continue;
                    rep0 = r & (((size_t)1 << ppp) - 1);
                    if (rep0 < pos)
                        break;
                    r = random_next(&rg);
                }
                rep0++;
            }

            {
                const size_t rem = buf_size - pos;
                if (len > rem)
                    len = (UInt32)rem;
            }
            Byte *dest = buf + pos;
            const Byte *src = dest - rep0;
            pos += len;
            for (UInt32 i = 0; i < len; i++)
                *dest++ = *src++;
        }
    }
}
