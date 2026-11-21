/* SPDX-License-Identifier: MIT
 * Shared declarations of the scaled-down 7-Zip LZMA benchmark kernel
 * (lzma_bench.c), its data generator (lzma_bench_data.c) and the native
 * harness (lzma_native.c).
 */
#ifndef LZMA_BENCH_H
#define LZMA_BENCH_H

#include "7zTypes.h"

/* Sizes. 7-Zip's "7z b -mdN" compresses 2^N + 64 KiB bytes with a 2^N
 * dictionary; this kernel keeps the same shape at a small scale: the data is
 * the dictionary plus 1/64 of it (4 MiB + 64 KiB has the same ratio). */
#ifndef LZMA_BENCH_DICT_LOG
#define LZMA_BENCH_DICT_LOG 12
#endif
#ifndef LZMA_BENCH_DATA_SIZE
#define LZMA_BENCH_DATA_SIZE ((1u << LZMA_BENCH_DICT_LOG) + (1u << LZMA_BENCH_DICT_LOG) / 64)
#endif
/* Bench.cpp generates its data with GenerateLz(kOldLzmaDictBits = 32, salt);
 * the first (single-threaded) encoder has salt 0. */
#define LZMA_BENCH_GEN_DICT_BITS 32
#define LZMA_BENCH_SALT 0

/* Phase markers. Values 1 and 2 are the testbench's start and stop markers;
 * values 16 and above are lap markers that tb_bench.sv reports without
 * changing the region. */
enum {
    LZMA_MARK_ENC_CALL = 0x10,   /* LzmaEnc_Encode() called: encoder init begins */
    LZMA_MARK_ENC_DONE = 0x11,   /* LzmaEnc_Encode() returned */
    LZMA_MARK_DEC_CALL = 0x12,   /* decoder init begins */
    LZMA_MARK_DEC_KERNEL = 0x13  /* LzmaDec_Init() done; decoding begins */
};
/* The region start (1) is written by the first input-stream read, which LzFind
 * makes right after clearing its hash table; the stop (2) after the
 * decompressed data's CRC. */

typedef struct {
    UInt32 data_size, dict_size, packed_size, props_byte;
    UInt32 crc_data, crc_packed, crc_unpacked;
    UInt32 enc_result, dec_result, dec_status, dec_in_used, compare_ok;
    UInt64 arena_used;
} LzmaBenchResult;

void bench_generate_lz(Byte *buf, size_t buf_size, unsigned dict_bits, UInt32 salt);

/* Provided by the harness: record a phase marker (1, 2 or a lap value). */
void lzma_bench_mark(unsigned value);

/* Arena the kernel allocates from; reset before each pass. */
void lzma_arena_init(void *base, size_t size);

/* CRC-32 (IEEE, reflected 0xEDB88320), the CRC 7-Zip's benchmark checks. */
void lzma_crc_init(void);
UInt32 lzma_crc_update(UInt32 crc, const Byte *data, size_t size);

/* One benchmark pass: generate, compress, decompress, verify. */
void lzma_bench_prepare(void);
void lzma_bench_pass(LzmaBenchResult *result);

#endif
