/* SPDX-License-Identifier: MIT
 * Fast sequential RV64 functional simulator for the benchmark runners.
 *
 * Executes the same subset as sim/cpu/reference.py (RV64I, M, Zba, Zbb, Zbs,
 * fence, fence.i; ecall/ebreak and every fault stop the run) with the same
 * byte-addressed memory, starting at PC 0 with all registers 0, or from a
 * saved state. It is a laboratory interpreter like reference.py, not an ISA
 * oracle; lzma_run.py compares its trace with reference.py's before relying
 * on it. It exists because reference.py runs about 50 k instructions per
 * second, and the large-dictionary LZMA kernels run billions.
 *
 * Usage: rv_iss --ram BYTES (--image FILE | --state FILE) [options]
 *   --image FILE         raw memory image (bench.bin), zero-padded to --ram
 *   --state FILE         saved state (format below) instead of an image
 *   --mailbox HEX        report marker stores and mailbox words (as lzma_run.scan)
 *   --max N              stop with an error after N instructions (default 2^62)
 *   --dump-at LIST       comma-separated instruction indices: before each one
 *                        executes, write <dump-prefix><index>.state
 *   --dump-prefix PATH   prefix for --dump-at files
 *   --trace FILE         write reference.py-format trace lines for the
 *   --trace-from A       instructions with program-order index in [A, B),
 *   --trace-to B         their memory writes included (default: all)
 *   --final-memory FILE  write the memory at the end
 *   --final-state FILE   write the state at the end (the stopping instruction
 *                        not executed)
 * Prints one JSON object on stdout: instructions retired, the stop (trap
 * cause, tval and PC, as reference.py's T line), the marker stores with the
 * program-order index of the storing instruction, the mailbox words written
 * with full 8-byte stores, and the wall time.
 *
 * State file: "RVISSST1", u64 instruction index, u64 pc, u64 x0..x31,
 * u64 memory bytes, then the memory; all little-endian.
 */
#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef uint64_t u64;
typedef int64_t i64;
typedef uint32_t u32;

static uint8_t *mem;
static u64 ram;
static u64 regs[32];
static u64 pc, count;
static u64 mailbox = ~(u64)0;
static FILE *trace_fd;
static u64 trace_from = 0, trace_to = ~(u64)0;
static u64 *dumps;
static size_t ndumps, next_dump;
static const char *dump_prefix = "state-";

#define MAX_MARKS 64
static u64 mark_value[MAX_MARKS], mark_index[MAX_MARKS];
static int nmarks;
static u64 mbox_words[32];
static u32 mbox_seen;

static void die(const char *msg) {
    fprintf(stderr, "rv_iss: %s\n", msg);
    exit(2);
}

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + 1e-9 * (double)t.tv_nsec;
}

static void write_state(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot write state");
    u64 head[3] = {0, count, pc};
    memcpy(&head[0], "RVISSST1", 8);
    fwrite(head, 8, 3, f);
    fwrite(regs, 8, 32, f);
    fwrite(&ram, 8, 1, f);
    if (fwrite(mem, 1, ram, f) != ram || fclose(f)) die("state write failed");
}

static void read_state(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot read state");
    u64 head[3], bytes = 0;
    if (fread(head, 8, 3, f) != 3 || memcmp(&head[0], "RVISSST1", 8)) die("not a state file");
    count = head[1];
    pc = head[2];
    if (fread(regs, 8, 32, f) != 32 || fread(&bytes, 8, 1, f) != 1) die("short state file");
    if (bytes != ram) die("state memory size differs from --ram");
    if (fread(mem, 1, ram, f) != ram) die("short state file");
    fclose(f);
    regs[0] = 0;
}

static inline int tracing(void) { return trace_fd && count >= trace_from && count < trace_to; }

static inline i64 sx(u64 v, int bits) { return (i64)(v << (64 - bits)) >> (64 - bits); }

static int stop_cause = -1;
static u64 stop_tval;

#define TRAP(c, t) do { stop_cause = (c); stop_tval = (t); return 0; } while (0)

static inline u64 rot64(u64 x, unsigned n) { n &= 63; return n ? (x << n) | (x >> (64 - n)) : x; }
static inline u32 rot32(u32 x, unsigned n) { n &= 31; return n ? (x << n) | (x >> (32 - n)) : x; }

static u64 mulhu64(u64 a, u64 b) { return (u64)(((unsigned __int128)a * b) >> 64); }
static u64 mulh64(u64 a, u64 b) { return (u64)(((__int128)(i64)a * (__int128)(i64)b) >> 64); }
static u64 mulhsu64(u64 a, u64 b) { return (u64)(((__int128)(i64)a * (__int128)(unsigned __int128)b) >> 64); }

/* M-extension division, per the unprivileged specification. */
static u64 divide(int f3, int word, u64 a, u64 b) {
    int sign = f3 == 4 || f3 == 6, rem = f3 >= 6;
    if (word) {
        if (sign) {
            int32_t x = (int32_t)a, y = (int32_t)b, q, r;
            if (y == 0) { q = -1; r = x; }
            else if (x == INT32_MIN && y == -1) { q = x; r = 0; }
            else { q = x / y; r = x % y; }
            return (u64)(i64)(rem ? r : q);
        }
        u32 x = (u32)a, y = (u32)b, q, r;
        if (y == 0) { q = 0xffffffffu; r = x; } else { q = x / y; r = x % y; }
        return (u64)(i64)(int32_t)(rem ? r : q);
    }
    if (sign) {
        i64 x = (i64)a, y = (i64)b, q, r;
        if (y == 0) { q = -1; r = x; }
        else if (x == INT64_MIN && y == -1) { q = x; r = 0; }
        else { q = x / y; r = x % y; }
        return (u64)(rem ? r : q);
    }
    u64 q, r;
    if (b == 0) { q = ~(u64)0; r = a; } else { q = a / b; r = a % b; }
    return rem ? r : q;
}

/* Zba/Zbb/Zbs: returns 1 and sets *v when ins is one of them (as reference.bitmanip_op). */
static int bitmanip(u32 ins, u64 a, u64 b, u64 *v) {
    u32 op = ins & 127, f3 = (ins >> 12) & 7, f7 = ins >> 25, f6 = ins >> 26, f12 = ins >> 20;
    u32 rs2 = (ins >> 20) & 31, sh6 = (ins >> 20) & 63, sh5 = (ins >> 20) & 31;
    u64 a32 = a & 0xffffffffu;
    if (op == 0x33) {
        if (f7 == 0x10 && (f3 == 2 || f3 == 4 || f3 == 6)) { *v = (a << (f3 / 2)) + b; return 1; }
        if (f7 == 0x20 && f3 == 7) { *v = a & ~b; return 1; }
        if (f7 == 0x20 && f3 == 6) { *v = a | ~b; return 1; }
        if (f7 == 0x20 && f3 == 4) { *v = ~(a ^ b); return 1; }
        if (f7 == 0x05) {
            switch (f3) {
            case 4: *v = (i64)a < (i64)b ? a : b; return 1;
            case 5: *v = a < b ? a : b; return 1;
            case 6: *v = (i64)a > (i64)b ? a : b; return 1;
            case 7: *v = a > b ? a : b; return 1;
            default: return 0;
            }
        }
        if (f7 == 0x30 && f3 == 1) { *v = rot64(a, b & 63); return 1; }
        if (f7 == 0x30 && f3 == 5) { *v = rot64(a, (64 - (b & 63)) & 63); return 1; }
        if (f7 == 0x24 && f3 == 1) { *v = a & ~((u64)1 << (b & 63)); return 1; }
        if (f7 == 0x24 && f3 == 5) { *v = (a >> (b & 63)) & 1; return 1; }
        if (f7 == 0x34 && f3 == 1) { *v = a ^ ((u64)1 << (b & 63)); return 1; }
        if (f7 == 0x14 && f3 == 1) { *v = a | ((u64)1 << (b & 63)); return 1; }
        return 0;
    }
    if (op == 0x3b) {
        if (f7 == 0x04 && f3 == 0) { *v = a32 + b; return 1; }
        if (f7 == 0x04 && f3 == 4 && rs2 == 0) { *v = a & 0xffff; return 1; }
        if (f7 == 0x10 && (f3 == 2 || f3 == 4 || f3 == 6)) { *v = (a32 << (f3 / 2)) + b; return 1; }
        if (f7 == 0x30 && f3 == 1) { *v = (u64)sx(rot32((u32)a32, b & 31), 32); return 1; }
        if (f7 == 0x30 && f3 == 5) { *v = (u64)sx(rot32((u32)a32, (32 - (b & 31)) & 31), 32); return 1; }
        return 0;
    }
    if (op == 0x13) {
        if (f3 == 1 && f12 == 0x600) { *v = a ? (u64)__builtin_clzll(a) : 64; return 1; }
        if (f3 == 1 && f12 == 0x601) { *v = a ? (u64)__builtin_ctzll(a) : 64; return 1; }
        if (f3 == 1 && f12 == 0x602) { *v = (u64)__builtin_popcountll(a); return 1; }
        if (f3 == 1 && f12 == 0x604) { *v = (u64)sx(a, 8); return 1; }
        if (f3 == 1 && f12 == 0x605) { *v = (u64)sx(a, 16); return 1; }
        if (f3 == 5 && f6 == 0x18) { *v = rot64(a, (64 - sh6) & 63); return 1; }
        if (f3 == 5 && f12 == 0x287) {
            u64 r = 0;
            for (int i = 0; i < 8; i++) if ((a >> (8 * i)) & 0xff) r |= (u64)0xff << (8 * i);
            *v = r;
            return 1;
        }
        if (f3 == 5 && f12 == 0x6b8) { *v = __builtin_bswap64(a); return 1; }
        if (f3 == 1 && f6 == 0x12) { *v = a & ~((u64)1 << sh6); return 1; }
        if (f3 == 5 && f6 == 0x12) { *v = (a >> sh6) & 1; return 1; }
        if (f3 == 1 && f6 == 0x1a) { *v = a ^ ((u64)1 << sh6); return 1; }
        if (f3 == 1 && f6 == 0x0a) { *v = a | ((u64)1 << sh6); return 1; }
        return 0;
    }
    if (op == 0x1b) {
        if (f3 == 1 && f6 == 0x02) { *v = a32 << sh6; return 1; }
        if (f3 == 1 && f12 == 0x600) { *v = a32 ? (u64)__builtin_clz((u32)a32) : 32; return 1; }
        if (f3 == 1 && f12 == 0x601) { *v = a32 ? (u64)__builtin_ctz((u32)a32) : 32; return 1; }
        if (f3 == 1 && f12 == 0x602) { *v = (u64)__builtin_popcount((u32)a32); return 1; }
        if (f3 == 5 && f7 == 0x30) { *v = (u64)sx(rot32((u32)a32, (32 - sh5) & 31), 32); return 1; }
        return 0;
    }
    return 0;
}

static inline void note_store(u64 address, u64 b, int size) {
    u64 aligned = address & ~(u64)7;
    int lane = (int)(address & 7);
    u64 data = b << (8 * lane); /* unmasked, like reference.py's W line */
    unsigned mask = ((1u << size) - 1) << lane;
    if (tracing()) fprintf(trace_fd, "W %016" PRIx64 " %016" PRIx64 " %02x\n", aligned, data, mask);
    if (aligned == mailbox) {
        if (nmarks < MAX_MARKS) { mark_value[nmarks] = data; mark_index[nmarks] = count; }
        nmarks++;
    } else if (aligned > mailbox && aligned < mailbox + 256 && mask == 0xff) {
        mbox_words[(aligned - mailbox) / 8] = data;
        mbox_seen |= 1u << ((aligned - mailbox) / 8);
    }
}

/* One instruction; returns 0 when the run stops (stop_cause set). */
static inline int step(void) {
    if (pc & 3) TRAP(0, pc);
    if ((pc & ~(u64)7) >= ram) TRAP(1, pc);
    u32 ins;
    memcpy(&ins, mem + pc, 4);
    u32 op = ins & 127, rd = (ins >> 7) & 31, f3 = (ins >> 12) & 7, rs1 = (ins >> 15) & 31, rs2 = (ins >> 20) & 31;
    u32 f7 = ins >> 25;
    u64 a = regs[rs1], b = regs[rs2];
    i64 imm = (i64)(int32_t)ins >> 20;
    u64 nxt = pc + 4, value = 0;
    u32 dest = 0;
    int ok = 0;
    switch (op) {
    case 0x37: value = (u64)(i64)(int32_t)(ins & 0xfffff000u); dest = rd; ok = 1; break;
    case 0x17: value = (u64)(i64)(int32_t)(ins & 0xfffff000u) + pc; dest = rd; ok = 1; break;
    case 0x6f: {
        u64 d = ((u64)(ins >> 31) << 20) | (((ins >> 12) & 255) << 12) | (((ins >> 20) & 1) << 11) | (((ins >> 21) & 1023) << 1);
        nxt = pc + (u64)sx(d, 21);
        value = pc + 4; dest = rd; ok = 1;
        break;
    }
    case 0x67:
        if (f3 == 0) { nxt = (a + (u64)imm) & ~(u64)1; value = pc + 4; dest = rd; ok = 1; }
        break;
    case 0x63: {
        int t;
        switch (f3) {
        case 0: t = a == b; break;
        case 1: t = a != b; break;
        case 4: t = (i64)a < (i64)b; break;
        case 5: t = (i64)a >= (i64)b; break;
        case 6: t = a < b; break;
        case 7: t = a >= b; break;
        default: t = -1;
        }
        if (t >= 0) {
            ok = 1;
            if (t) {
                u64 d = ((u64)(ins >> 31) << 12) | (((ins >> 7) & 1) << 11) | (((ins >> 25) & 63) << 5) | (((ins >> 8) & 15) << 1);
                nxt = pc + (u64)sx(d, 13);
            }
        }
        break;
    }
    case 0x03: case 0x23: {
        int load = op == 0x03;
        if ((load && f3 != 7) || (!load && f3 < 4)) {
            int size = 1 << (f3 & 3);
            i64 off = load ? imm : sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12);
            u64 address = a + (u64)off;
            if (address & (u64)(size - 1)) TRAP(load ? 4 : 6, address);
            if ((address & ~(u64)7) >= ram) TRAP(load ? 5 : 7, address);
            if (load) {
                u64 v = 0;
                memcpy(&v, mem + address, (size_t)size);
                if (f3 < 4 && size < 8) v = (u64)sx(v, 8 * size);
                value = v; dest = rd;
            } else {
                memcpy(mem + address, &b, (size_t)size);
                note_store(address, b, size);
            }
            ok = 1;
        }
        break;
    }
    case 0x0f: if (f3 == 0 || f3 == 1) ok = 1; break;
    case 0x73:
        if (ins == 0x73) TRAP(11, 0);
        if (ins == 0x100073) TRAP(3, 0);
        break;
    case 0x13: case 0x1b: case 0x33: case 0x3b: {
        int word = op == 0x1b || op == 0x3b;
        if ((op == 0x33 || op == 0x3b) && f7 == 1) {
            if (!word || f3 == 0 || f3 >= 4) {
                if (f3 < 4) {
                    if (word) value = (u64)(i64)(int32_t)(u32)(a * b);
                    else if (f3 == 0) value = a * b;
                    else if (f3 == 1) value = mulh64(a, b);
                    else if (f3 == 2) value = mulhsu64(a, b);
                    else value = mulhu64(a, b);
                } else value = divide((int)f3, word, a, b);
                dest = rd; ok = 1;
            }
            break;
        }
        if (bitmanip(ins, a, b, &value)) { dest = rd; ok = 1; break; }
        int immediate = op == 0x13 || op == 0x1b;
        int width = word ? 32 : 64;
        u64 rhs = immediate ? (u64)imm : b;
        unsigned shift = (unsigned)(rhs & (u64)(width - 1));
        int subtract = !immediate && f7 == 32;
        int arith = (ins >> 30) & 1;
        int valid = 1;
        if (immediate) {
            if (f3 == 1 || f3 == 5) {
                u32 top = ins >> (word ? 25 : 26);
                valid = top == 0 || (f3 == 5 && top == (word ? 32u : 16u));
            }
        } else valid = f7 == 0 || (f7 == 32 && (f3 == 0 || f3 == 5));
        if (word && f3 != 0 && f3 != 1 && f3 != 5) valid = 0;
        if (!valid) break;
        switch (f3) {
        case 0: value = subtract ? a - rhs : a + rhs; break;
        case 1: value = a << shift; break;
        case 2: value = (i64)a < (i64)rhs; break;
        case 3: value = a < rhs; break;
        case 4: value = a ^ rhs; break;
        case 5:
            if (arith) value = word ? (u64)((i64)(int32_t)(u32)a >> shift) : (u64)((i64)a >> shift);
            else value = word ? (u64)((u32)a >> shift) : a >> shift;
            break;
        case 6: value = a | rhs; break;
        default: value = a & rhs;
        }
        if (word) value = (u64)(i64)(int32_t)(u32)value;
        dest = rd; ok = 1;
        break;
    }
    default: break;
    }
    if (!ok) TRAP(2, ins);
    if (nxt & 3) TRAP(0, nxt);
    if (dest) regs[dest] = value; else value = 0;
    if (tracing())
        fprintf(trace_fd, "R %016" PRIx64 " %08x %02x %016" PRIx64 " %016" PRIx64 "\n", pc, ins, dest, value, nxt);
    pc = nxt;
    count++;
    return 1;
}

static void parse_dumps(const char *list) {
    char *copy = strdup(list), *save = NULL;
    for (char *t = strtok_r(copy, ",", &save); t; t = strtok_r(NULL, ",", &save)) {
        dumps = realloc(dumps, (ndumps + 1) * sizeof *dumps);
        dumps[ndumps++] = strtoull(t, NULL, 0);
        if (ndumps > 1 && dumps[ndumps - 1] <= dumps[ndumps - 2]) die("--dump-at must be increasing");
    }
    free(copy);
}

int main(int argc, char **argv) {
    const char *image = NULL, *state = NULL, *trace = NULL, *final_memory = NULL, *final_state = NULL;
    u64 max = (u64)1 << 62;
    for (int i = 1; i < argc; i++) {
        const char *k = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) die("option without a value");
        i++;
        if (!strcmp(k, "--ram")) ram = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--image")) image = v;
        else if (!strcmp(k, "--state")) state = v;
        else if (!strcmp(k, "--mailbox")) mailbox = strtoull(v, NULL, 16);
        else if (!strcmp(k, "--max")) max = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--dump-at")) parse_dumps(v);
        else if (!strcmp(k, "--dump-prefix")) dump_prefix = v;
        else if (!strcmp(k, "--trace")) trace = v;
        else if (!strcmp(k, "--trace-from")) trace_from = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--trace-to")) trace_to = strtoull(v, NULL, 0);
        else if (!strcmp(k, "--final-memory")) final_memory = v;
        else if (!strcmp(k, "--final-state")) final_state = v;
        else die("unknown option");
    }
    if (!ram || (ram & 7) || (!image == !state)) die("need --ram and one of --image / --state");
    mem = calloc(1, ram + 8); /* +8: an aligned 4-byte fetch or load never reads past the end */
    if (!mem) die("out of memory");
    if (image) {
        FILE *f = fopen(image, "rb");
        if (!f) die("cannot read image");
        size_t n = fread(mem, 1, ram, f);
        if (!feof(f) && fgetc(f) != EOF) die("image larger than --ram");
        fclose(f);
        (void)n;
    } else read_state(state);
    if (trace && !(trace_fd = fopen(trace, "w"))) die("cannot write trace");
    if (trace_fd) setvbuf(trace_fd, NULL, _IOFBF, 1 << 20);
    double t0 = now();
    u64 start = count;
    char path[4096];
    for (;;) {
        while (next_dump < ndumps && dumps[next_dump] < count) next_dump++;
        u64 limit = next_dump < ndumps ? dumps[next_dump] : max;
        if (limit > max) limit = max;
        if (count == limit) {
            if (next_dump < ndumps && dumps[next_dump] == count) {
                snprintf(path, sizeof path, "%s%" PRIu64 ".state", dump_prefix, count);
                write_state(path);
                next_dump++;
                continue;
            }
            stop_cause = -2; /* instruction budget */
            break;
        }
        if (trace_fd) {
            while (count < limit && step()) {}
        } else {
            while (count < limit && step()) {}
        }
        if (stop_cause != -1) break;
    }
    double t1 = now();
    if (stop_cause >= 0 && tracing())
        fprintf(trace_fd, "T %016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n", pc, (u64)stop_cause, stop_tval);
    if (trace_fd && fclose(trace_fd)) die("trace write failed");
    if (final_memory) {
        FILE *f = fopen(final_memory, "wb");
        if (!f || fwrite(mem, 1, ram, f) != ram || fclose(f)) die("final memory write failed");
    }
    if (final_state) write_state(final_state);
    printf("{\"instructions\": %" PRIu64 ", \"start_index\": %" PRIu64 ", ", count, start);
    if (stop_cause == -2) printf("\"stop\": \"budget\", ");
    else printf("\"stop\": {\"pc\": %" PRIu64 ", \"cause\": %d, \"tval\": %" PRIu64 "}, ", pc, stop_cause, stop_tval);
    printf("\"marks\": [");
    for (int i = 0; i < nmarks && i < MAX_MARKS; i++)
        printf("%s[%" PRIu64 ", %" PRIu64 "]", i ? ", " : "", mark_value[i], mark_index[i]);
    printf("], \"marks_total\": %d, \"mailbox\": {", nmarks);
    int first = 1;
    for (int i = 1; i < 32; i++)
        if (mbox_seen >> i & 1) { printf("%s\"%d\": %" PRIu64, first ? "" : ", ", i, mbox_words[i]); first = 0; }
    double secs = t1 - t0;
    printf("}, \"seconds\": %.3f, \"mips\": %.3f}\n", secs, secs > 0 ? (double)(count - start) / secs / 1e6 : 0.0);
    return 0;
}
