/* SPDX-License-Identifier: MIT
 * Port layer for the riscv-tests Dhrystone on this core.
 *
 * Upstream main() calls setStats(1) just before the timed loop and
 * setStats(0) just after it. Here they write the start and stop markers the
 * testbench counts, and setStats(0) also copies the benchmark's final global
 * values into the mailbox so the runner can check them. The local variables
 * upstream prints are not reachable from here and are not checked.
 *
 * The core has no cycle counter yet. bench_timer() returns 1, 2, 3, ... so
 * the program's own timing sees a non-zero interval and runs exactly once;
 * the time it prints (to the empty printf) is meaningless.
 */
#include "bench.h"
#include "dhrystone.h"

extern Rec_Pointer Ptr_Glob, Next_Ptr_Glob;
extern int Int_Glob;
extern Boolean Bool_Glob;
extern char Ch_1_Glob, Ch_2_Glob;
extern int Arr_1_Glob[50];
extern int Arr_2_Glob[50][50];

enum {
    RESULT_MAGIC,
    RESULT_RUNS,
    RESULT_INT_GLOB,
    RESULT_BOOL_GLOB,
    RESULT_CH_1_GLOB,
    RESULT_CH_2_GLOB,
    RESULT_ARR_1_GLOB_8,
    RESULT_ARR_2_GLOB_8_7,
    RESULT_PTR_DISCR,
    RESULT_PTR_ENUM_COMP,
    RESULT_PTR_INT_COMP,
    RESULT_PTR_STR_MATCHES,
    RESULT_NEXT_DISCR,
    RESULT_NEXT_ENUM_COMP,
    RESULT_NEXT_INT_COMP,
    RESULT_NEXT_STR_MATCHES,
    RESULT_PTR_COMP_EQUAL
};

/* "DHRYSTON" in little-endian ASCII. */
#define DHRYSTONE_MAGIC 0x4e4f545359524844ull

static const char expected_string[] = "DHRYSTONE PROGRAM, SOME STRING";

/* Independent of the runtime's strcmp, which is part of the code under test. */
static bench_u64 same_string(const char *actual) {
    unsigned i = 0;
    for (;;) {
        if (actual[i] != expected_string[i]) return 0;
        if (expected_string[i] == '\0') return 1;
        ++i;
    }
}

long bench_timer(void) {
    static long ticks;
    return ++ticks;
}

void setStats(int enable) {
    if (enable) {
        bench_marker(BENCH_MARKER_START);
        return;
    }
    bench_marker(BENCH_MARKER_STOP);
    bench_result(RESULT_MAGIC, DHRYSTONE_MAGIC);
    bench_result(RESULT_RUNS, NUMBER_OF_RUNS);
    bench_result(RESULT_INT_GLOB, (bench_u64)Int_Glob);
    bench_result(RESULT_BOOL_GLOB, (bench_u64)Bool_Glob);
    bench_result(RESULT_CH_1_GLOB, (bench_u64)(unsigned char)Ch_1_Glob);
    bench_result(RESULT_CH_2_GLOB, (bench_u64)(unsigned char)Ch_2_Glob);
    bench_result(RESULT_ARR_1_GLOB_8, (bench_u64)Arr_1_Glob[8]);
    bench_result(RESULT_ARR_2_GLOB_8_7, (bench_u64)Arr_2_Glob[8][7]);
    bench_result(RESULT_PTR_DISCR, (bench_u64)Ptr_Glob->Discr);
    bench_result(RESULT_PTR_ENUM_COMP, (bench_u64)Ptr_Glob->variant.var_1.Enum_Comp);
    bench_result(RESULT_PTR_INT_COMP, (bench_u64)Ptr_Glob->variant.var_1.Int_Comp);
    bench_result(RESULT_PTR_STR_MATCHES, same_string(Ptr_Glob->variant.var_1.Str_Comp));
    bench_result(RESULT_NEXT_DISCR, (bench_u64)Next_Ptr_Glob->Discr);
    bench_result(RESULT_NEXT_ENUM_COMP, (bench_u64)Next_Ptr_Glob->variant.var_1.Enum_Comp);
    bench_result(RESULT_NEXT_INT_COMP, (bench_u64)Next_Ptr_Glob->variant.var_1.Int_Comp);
    bench_result(RESULT_NEXT_STR_MATCHES, same_string(Next_Ptr_Glob->variant.var_1.Str_Comp));
    bench_result(RESULT_PTR_COMP_EQUAL, Ptr_Glob->Ptr_Comp == Next_Ptr_Glob->Ptr_Comp);
}
