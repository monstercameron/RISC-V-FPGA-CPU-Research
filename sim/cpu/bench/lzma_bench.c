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
 *     (k_CheckCrcMode_Always) step by step as it is written, with a slicing-by-12 CRC;
 *   - the unmodified LZMA SDK decoder, run in 1 MiB output steps like 7-Zip's
 *     LzmaDecoder.cpp and asked to finish exactly at the end.
 * Known departures from Bench.cpp are listed in cpu/lzma-benchmark.md.
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

/* ---- CRC-32 (reflected polynomial 0xEDB88320). ----
 * lzma_crc_update: table-driven, one byte per step (data CRC and the packed stream).
 * lzma_crc_update12: slicing-by-12, the algorithm 7-Zip's CrcUpdate uses on a CPU without a
 * CRC instruction such as RISC-V (7-Zip 26.06 C/7zCrc.c line 29: 12 tables by default;
 * C/7zCrcOpt.c lines 46-100, CrcUpdateT12). Written here from the CRC definition, not copied:
 * table k maps a byte to its CRC contribution k byte positions further on, so
 * crc_slice[k][i] = (crc_slice[k-1][i] >> 8) ^ crc_slice[0][crc_slice[k-1][i] & 0xFF].
 * The twelve tables are built untimed (crc_slice_init(), after compression and before the
 * decoder's timed region), as 7-Zip builds them once at start-up (CrcGenerateTable, C/7zCrc.c
 * lines 307-327). They live in the arena and are built after compression so that everything up
 * to the end of compression executes the same instructions as before the change (2026-11-22),
 * which keeps the sampled compress pieces on the same windows. */
static UInt32 crc_table[256];
static UInt32 (*crc_slice)[256];

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

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "lzma_crc_update12 reads little-endian 32-bit words (RV64 and the aarch64/x86-64 native builds)"
#endif
/* One aligned 32-bit load (p is 4-byte aligned here), like 7-Zip's GetUi32a. */
static UInt32 load_le32(const Byte *p) {
    UInt32 w;
    __builtin_memcpy(&w, __builtin_assume_aligned(p, 4), 4);
    return w;
}

static int crc_slice_init(ISzAllocPtr alloc) {
    crc_slice = (UInt32 (*)[256])ISzAlloc_Alloc(alloc, 12 * 256 * sizeof(UInt32));
    if (!crc_slice) return 0;
    for (unsigned i = 0; i < 256; i++) crc_slice[0][i] = crc_table[i];
    for (unsigned k = 1; k < 12; k++)
        for (unsigned i = 0; i < 256; i++)
            crc_slice[k][i] = (crc_slice[k - 1][i] >> 8) ^ crc_table[crc_slice[k - 1][i] & 0xFF];
    return 1;
}

/* Bytes one at a time up to a 4-byte boundary, then 12 bytes (three 32-bit words) per step,
 * then the remaining bytes one at a time; the same split as CrcUpdateT12. */
static UInt32 lzma_crc_update12(UInt32 crc, const Byte *data, size_t size) {
    const Byte *p = data;
    for (; size && ((__UINTPTR_TYPE__)p & 3) != 0; size--, p++) crc = crc_table[(crc ^ *p) & 0xFF] ^ (crc >> 8);
    for (; size >= 12; size -= 12, p += 12) {
        const UInt32 a = load_le32(p) ^ crc, b = load_le32(p + 4), c = load_le32(p + 8);
        crc = crc_slice[11][a & 0xFF] ^ crc_slice[10][(a >> 8) & 0xFF] ^ crc_slice[9][(a >> 16) & 0xFF] ^ crc_slice[8][a >> 24] ^
              crc_slice[7][b & 0xFF] ^ crc_slice[6][(b >> 8) & 0xFF] ^ crc_slice[5][(b >> 16) & 0xFF] ^ crc_slice[4][b >> 24] ^
              crc_slice[3][c & 0xFF] ^ crc_slice[2][(c >> 8) & 0xFF] ^ crc_slice[1][(c >> 16) & 0xFF] ^ crc_slice[0][c >> 24];
    }
    for (; size; size--, p++) crc = crc_table[(crc ^ *p) & 0xFF] ^ (crc >> 8);
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
     * CEncoderInfo::Decode() iteration: init, then decode in output steps, each CRC'd as it
     * is written (below). */
    CLzmaDec dec;
    LzmaDec_CONSTRUCT(&dec)
    res = LzmaDec_AllocateProbs(&dec, header, LZMA_PROPS_SIZE, &arena);
    if (res == SZ_OK && !crc_slice_init(&arena)) res = SZ_ERROR_MEM;
    if (res != SZ_OK) {
        result->dec_result = (UInt32)res;
        return;
    }
    dec.dic = output_buf;
    dec.dicBufSize = LZMA_BENCH_DATA_SIZE;
    lzma_bench_mark(LZMA_MARK_DEC_CALL);
    LzmaDec_Init(&dec);
    lzma_bench_mark(LZMA_MARK_DEC_KERNEL);
    /* As 7-Zip's LZMA decoder (CPP/7zip/Compress/LzmaDecoder.cpp, CodeSpec, lines 119-182):
     * each LzmaDec_DecodeToDic call decodes at most _outStep = 1 MiB (line 32) past the last
     * write (lines 139-141), the last one with LZMA_FINISH_END; then the step is written
     * (WriteStream, line 178) to the benchmark's CCrcOutStream, which CRCs it as it arrives
     * (CPP/7zip/UI/Common/Bench.cpp lines 382-390, timed with the decode: lines 2105-2159). */
    SizeT in_left = out_pos;
    const Byte *in_next = packed_buf;
    ELzmaStatus status = LZMA_STATUS_NOT_SPECIFIED;
    UInt32 output_crc = 0xFFFFFFFFu;
    res = SZ_OK;
    for (SizeT wr = 0; wr < LZMA_BENCH_DATA_SIZE;) {
        const SizeT step = (SizeT)1 << 20;
        const SizeT limit = LZMA_BENCH_DATA_SIZE - wr > step ? wr + step : LZMA_BENCH_DATA_SIZE;
        SizeT in_now = in_left;
        res = LzmaDec_DecodeToDic(&dec, limit, in_next, &in_now,
                                  limit == LZMA_BENCH_DATA_SIZE ? LZMA_FINISH_END : LZMA_FINISH_ANY, &status);
        in_next += in_now;
        in_left -= in_now;
        output_crc = lzma_crc_update12(output_crc, output_buf + wr, dec.dicPos - wr);
        if (res != SZ_OK || dec.dicPos == wr) break;
        wr = dec.dicPos;
    }
    output_crc ^= 0xFFFFFFFFu;
    const SizeT in_used = out_pos - in_left;
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
