/* SPDX-License-Identifier: MIT
 * Scaled-down 7-Zip LZMA benchmark kernel for the bare-metal RV64 cores.
 *
 * Reproduces one pass of what "7z b" times for LZMA (7-Zip 26.06,
 * CPP/7zip/UI/Common/Bench.cpp), at a size the simulator can run:
 *   - the benchmark's own pseudo-random LZ data (lzma_bench_data.c);
 *   - the unmodified LZMA SDK encoder (vendor/lzma) with the benchmark's
 *     settings: level 5 defaults (lc 3, lp 0, pb 2, 32 fast bytes, BT4 match
 *     finder, cut value 32, optimal parsing), one thread, reduceSize = data
 *     size, a 2^LZMA_BENCH_DICT_LOG dictionary and no end marker;
 *   - stream callbacks that behave like Bench.cpp's: the input stream copies
 *     from the data buffer, the output stream copies the packed bytes and
 *     updates their CRC (CheckCrc_Enc), and the decoder's output is CRC-checked
 *     (k_CheckCrcMode_Always);
 *   - the unmodified LZMA SDK decoder, asked to finish exactly at the end.
 * Phase markers (lzma_bench.h) let the testbench time compression and
 * decompression separately. Results go to the benchmark mailbox:
 *   word 2   magic "LZMABNCH"      word 9   decoder result (SRes)
 *   word 3   data size             word 10  decoder status
 *   word 4   dictionary size       word 11  packed bytes the decoder used
 *   word 5   packed size           word 12  1 if the output equals the input
 *   word 6   CRC of the data       word 13  encoder result (SRes)
 *   word 7   CRC of packed data    word 14  LZMA properties byte (lc/lp/pb)
 *   word 8   CRC of output         word 15  arena bytes used
 * Built with -DLZMA_BENCH_NATIVE, main() and the marker hook come from
 * lzma_native.c instead.
 */
#include "lzma_bench.h"
#include "LzmaEnc.h"
#include "LzmaDec.h"

#include <string.h>

#define PACKED_CAPACITY (LZMA_BENCH_DATA_SIZE + LZMA_BENCH_DATA_SIZE / 16 + 1024) /* GetBenchCompressedSize() */

/* ---- Static arena: the kernel's only memory allocator. ---- */
static Byte *arena_base, *arena_next, *arena_end;

void lzma_arena_init(void *base, size_t size) {
    Byte *start = (Byte *)(((__UINTPTR_TYPE__)base + 63) & ~(__UINTPTR_TYPE__)63);
    arena_end = (Byte *)base + size;
    arena_base = arena_next = start;
}

static void *arena_alloc(ISzAllocPtr p, size_t size) {
    (void)p;
    size_t offset = ((size_t)(arena_next - arena_base) + 63) & ~(size_t)63; /* 64-byte aligned like g_AlignedAlloc */
    if (size > (size_t)(arena_end - arena_base) - offset) return NULL;
    arena_next = arena_base + offset + size;
    return arena_base + offset;
}

static void arena_free(ISzAllocPtr p, void *address) {
    (void)p;
    (void)address; /* released all at once by lzma_arena_init() before the next pass */
}

static const ISzAlloc arena = {arena_alloc, arena_free};

/* ---- CRC-32, table-driven, one byte per step. ---- */
static UInt32 crc_table[256];

void lzma_crc_init(void) {
    for (UInt32 i = 0; i < 256; i++) {
        UInt32 r = i;
        for (unsigned j = 0; j < 8; j++) r = (r >> 1) ^ (0xEDB88320u & ((UInt32)0 - (r & 1)));
        crc_table[i] = r;
    }
}

UInt32 lzma_crc_update(UInt32 crc, const Byte *data, size_t size) {
    for (size_t i = 0; i < size; i++) crc = crc_table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    return crc;
}

/* ---- Buffers. ---- */
static Byte *data_buf, *packed_buf, *output_buf;
static UInt32 data_crc;

/* Input stream, like CBenchmarkInStream: at most 1 MiB per read. The first
 * read comes from MatchFinder_Init() after it has cleared the hash table, so
 * it starts the timed region (marker 1). */
static size_t in_pos;
static int in_started;

static SRes in_read(ISeqInStreamPtr p, void *buf, size_t *size) {
    (void)p;
    if (!in_started) {
        in_started = 1;
        lzma_bench_mark(1);
    }
    size_t n = *size;
    if (n > ((size_t)1 << 20)) n = (size_t)1 << 20;
    if (n > LZMA_BENCH_DATA_SIZE - in_pos) n = LZMA_BENCH_DATA_SIZE - in_pos;
    if (n) memcpy(buf, data_buf + in_pos, n);
    in_pos += n;
    *size = n;
    return SZ_OK;
}

/* Output stream, like CBenchmarkOutStream with RealCopy and CalcCrc. */
static size_t out_pos;
static UInt32 out_crc;

static size_t out_write(ISeqOutStreamPtr p, const void *buf, size_t size) {
    (void)p;
    if (size > PACKED_CAPACITY - out_pos) size = PACKED_CAPACITY - out_pos;
    memcpy(packed_buf + out_pos, buf, size);
    out_crc = lzma_crc_update(out_crc, packed_buf + out_pos, size);
    out_pos += size;
    return size;
}

static const ISeqInStream in_stream = {in_read};
static const ISeqOutStream out_stream = {out_write};

void lzma_bench_prepare(void) {
    lzma_crc_init();
}

void lzma_bench_pass(LzmaBenchResult *result) {
    memset(result, 0, sizeof(*result));
    result->data_size = LZMA_BENCH_DATA_SIZE;

    /* CEncoderInfo::Generate(): data, its CRC, encoder properties. Not timed. */
    data_buf = (Byte *)arena_alloc(&arena, LZMA_BENCH_DATA_SIZE);
    packed_buf = (Byte *)arena_alloc(&arena, PACKED_CAPACITY);
    output_buf = (Byte *)arena_alloc(&arena, LZMA_BENCH_DATA_SIZE);
    if (!data_buf || !packed_buf || !output_buf) {
        result->enc_result = SZ_ERROR_MEM;
        return;
    }
    bench_generate_lz(data_buf, LZMA_BENCH_DATA_SIZE, LZMA_BENCH_GEN_DICT_BITS, LZMA_BENCH_SALT);
    data_crc = lzma_crc_update(0xFFFFFFFFu, data_buf, LZMA_BENCH_DATA_SIZE) ^ 0xFFFFFFFFu;
    result->crc_data = data_crc;

    CLzmaEncHandle enc = LzmaEnc_Create(&arena);
    if (!enc) {
        result->enc_result = SZ_ERROR_MEM;
        return;
    }
    CLzmaEncProps props;
    LzmaEncProps_Init(&props); /* level 5 defaults */
    props.dictSize = (UInt32)1 << LZMA_BENCH_DICT_LOG;
    props.reduceSize = LZMA_BENCH_DATA_SIZE; /* SetCoderProps_DSReduce_Aff(&reduceSize) */
    props.numThreads = 1;                    /* 7z b -mmt1 */
    SRes res = LzmaEnc_SetProps(enc, &props);
    Byte header[LZMA_PROPS_SIZE];
    SizeT header_size = LZMA_PROPS_SIZE;
    if (res == SZ_OK) res = LzmaEnc_WriteProperties(enc, header, &header_size);
    if (res != SZ_OK) {
        result->enc_result = (UInt32)res;
        return;
    }
    result->props_byte = header[0];
    result->dict_size = (UInt32)header[1] | (UInt32)header[2] << 8 | (UInt32)header[3] << 16 | (UInt32)header[4] << 24;

    /* Compression: one CEncoderInfo::Encode() iteration. */
    in_pos = 0;
    in_started = 0;
    out_pos = 0;
    out_crc = 0xFFFFFFFFu;
    lzma_bench_mark(LZMA_MARK_ENC_CALL);
    res = LzmaEnc_Encode(enc, &out_stream, &in_stream, NULL, &arena, &arena);
    lzma_bench_mark(LZMA_MARK_ENC_DONE);
    result->enc_result = (UInt32)res;
    result->packed_size = (UInt32)out_pos;
    result->crc_packed = out_crc ^ 0xFFFFFFFFu;
    if (res != SZ_OK || in_pos != LZMA_BENCH_DATA_SIZE) {
        if (res == SZ_OK) result->enc_result = SZ_ERROR_FAIL;
        return;
    }

    /* Decompression: SetDecoderProperties2() allocates (not timed), then one
     * CEncoderInfo::Decode() iteration: init, decode to the end, CRC. */
    CLzmaDec dec;
    LzmaDec_CONSTRUCT(&dec)
    res = LzmaDec_AllocateProbs(&dec, header, LZMA_PROPS_SIZE, &arena);
    if (res != SZ_OK) {
        result->dec_result = (UInt32)res;
        return;
    }
    dec.dic = output_buf;
    dec.dicBufSize = LZMA_BENCH_DATA_SIZE;
    lzma_bench_mark(LZMA_MARK_DEC_CALL);
    LzmaDec_Init(&dec);
    lzma_bench_mark(LZMA_MARK_DEC_KERNEL);
    SizeT in_used = out_pos;
    ELzmaStatus status;
    res = LzmaDec_DecodeToDic(&dec, LZMA_BENCH_DATA_SIZE, packed_buf, &in_used, LZMA_FINISH_END, &status);
    UInt32 output_crc = lzma_crc_update(0xFFFFFFFFu, output_buf, dec.dicPos) ^ 0xFFFFFFFFu;
    lzma_bench_mark(2);

    result->dec_result = (UInt32)res;
    result->dec_status = (UInt32)status;
    result->dec_in_used = (UInt32)in_used;
    result->crc_unpacked = output_crc;
    result->compare_ok = dec.dicPos == LZMA_BENCH_DATA_SIZE && in_used == out_pos && output_crc == data_crc &&
                         memcmp(output_buf, data_buf, LZMA_BENCH_DATA_SIZE) == 0;
    result->arena_used = (UInt64)(arena_next - arena_base);
}

#ifndef LZMA_BENCH_NATIVE
#include "bench.h"

/* Free memory between the program's end and the reserved stack below the
 * mailbox; the linker script asserts that 8 KiB of stack remain. */
extern char __bss_end[], __stack_top[];
#define STACK_RESERVE 8192

void lzma_bench_mark(unsigned value) { bench_marker(value); }

#define LZMA_MAGIC 0x48434e42414d5a4cull /* "LZMABNCH" in little-endian ASCII */

int main(void) {
    LzmaBenchResult r;
    lzma_arena_init(__bss_end, (size_t)(__stack_top - STACK_RESERVE - __bss_end));
    lzma_bench_prepare();
    lzma_bench_pass(&r);
    bench_result(0, LZMA_MAGIC);
    bench_result(1, r.data_size);
    bench_result(2, r.dict_size);
    bench_result(3, r.packed_size);
    bench_result(4, r.crc_data);
    bench_result(5, r.crc_packed);
    bench_result(6, r.crc_unpacked);
    bench_result(7, r.dec_result);
    bench_result(8, r.dec_status);
    bench_result(9, r.dec_in_used);
    bench_result(10, r.compare_ok);
    bench_result(11, r.enc_result);
    bench_result(12, r.props_byte);
    bench_result(13, r.arena_used);
    return r.compare_ok ? 0 : 1;
}
#endif
