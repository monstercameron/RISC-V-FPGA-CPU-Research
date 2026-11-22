// SPDX-License-Identifier: MIT
// Original CPU foundation, wide out-of-order implementation (architecture 0.19.1).
// RV64IM + B execution (RV64F and D with define RV64_OOO_FPU, default off; with RV64_OOO_V
// also the RVV subset of the vector contract, step 1, executed in order),
// serialized FENCE.I, terminal EEI. Same module name and
// contract as rv64_core.sv and rv64_pipe.sv, plus a wider retirement trace (rt_*);
// build with one of the three files. Architecture version: cpu/VERSION,
// cpu/architecture.md section 9. No RVA23 compliance claim.
module rv64_core #(
    parameter [63:0] RESET_PC = 64'h0,
    // Direct-mapped instruction cache size in 8-byte beats; power of two, >= 2.
    parameter integer ICACHE_BEATS = 16384,   // 128 KiB, after the Apple M5's large L1s
    // Direct-mapped write-through data cache size in 8-byte beats; power of two, >= 2.
    parameter integer DCACHE_BEATS = 16384,   // 128 KiB
    // Retirement (and fetch and rename) width (16 until 0.13.1; fetch/rename stays 16).
    parameter integer RW = 32,
    // Paired store writes (0.11.0): 1 when the memory implements mem_*2.
    parameter integer PAIR_WRITES = 0,
    // Extra store writes: 1 or 2 more stores per write on mem_x*, with PAIR_WRITES.
    parameter integer EXTRA_WRITES = 0,
    // Data misses in flight (memory hand-off 2). 1: one blocking data read at a time. Above 1
    // data reads are split transactions (mem_tag, rsp_*); the memory must support them.
    parameter integer N_MISS = 1
) (
    input  wire        clk,
    input  wire        reset,
    // Completion handshake: hold request stable until valid && ready.
    // Address is 8-byte aligned. An error completion has no memory side effect.
    output wire        mem_valid,
    output wire        mem_instr,
    output wire [63:0] mem_addr,
    output wire [63:0] mem_wdata,
    output wire [7:0]  mem_wstrb,
    input  wire        mem_ready,
    input  wire [63:0] mem_rdata,
    input  wire        mem_error,
    // Terminal laboratory execution-environment exception record.
    output reg         trap_valid,
    output reg [63:0]  trap_pc,
    output reg [63:0]  trap_cause,
    output reg [63:0]  trap_tval,
    // One-cycle architectural retirement trace, not the complete RVFI interface.
    output reg         retire_valid,
    output reg [63:0]  retire_pc,
    output reg [31:0]  retire_insn,
    output reg [4:0]   retire_rd,
    output reg [63:0]  retire_data,
    output reg [63:0]  retire_next_pc,
    // Second retirement slot (0.5.0): an instruction retired in the same clock as,
    // and in program order immediately after, the one on the first slot.
    output reg         retire2_valid,
    output reg [63:0]  retire2_pc,
    output reg [31:0]  retire2_insn,
    output reg [4:0]   retire2_rd,
    output reg [63:0]  retire2_data,
    output reg [63:0]  retire2_next_pc,
    // Third retirement slot (0.7.0): after the second, in program order, same clock.
    output reg         retire3_valid,
    output reg [63:0]  retire3_pc,
    output reg [31:0]  retire3_insn,
    output reg [4:0]   retire3_rd,
    output reg [63:0]  retire3_data,
    output reg [63:0]  retire3_next_pc,
    // Wide retirement trace (0.10.0): up to RW instructions per clock, slot 0 oldest;
    // retire_*, retire2_* and retire3_* repeat slots 0 to 2.
    output reg [RW-1:0]    rt_valid,
    output reg [RW*64-1:0] rt_pc,
    output reg [RW*32-1:0] rt_insn,
    output reg [RW*5-1:0]  rt_rd,
    output reg [RW*64-1:0] rt_data,
    output reg [RW*64-1:0] rt_next,
    // Paired store write (0.11.0, with PAIR_WRITES): when mem_wstrb2 != 0 a store write
    // also carries the next store; memory applies it only if the first succeeds, and
    // mem_error2 reports it. Both complete with mem_ready.
    output wire [63:0]     mem_addr2,
    output wire [63:0]     mem_wdata2,
    output wire [7:0]      mem_wstrb2,
    input  wire            mem_error2,
    // Extra store writes (with EXTRA_WRITES): stores three and four of a write request in
    // 64-bit lanes 0 and 1 (mem_xwstrb lane 0 = bits 7:0); memory applies each only if every
    // earlier store of the request succeeded; mem_xerror reports each. All complete with mem_ready.
    output wire [127:0]    mem_xaddr,
    output wire [127:0]    mem_xwdata,
    output wire [15:0]     mem_xwstrb,
    input  wire [1:0]      mem_xerror,
    // Split data reads (N_MISS > 1): a data read (mem_instr 0, mem_wstrb 0) carries mem_tag and
    // completes at mem_ready when the memory accepts it (mem_error is then ignored); its beat comes
    // back later with rsp_valid for one clock, with that tag, rsp_data and rsp_error. The core
    // never has more than N_MISS reads outstanding, with distinct tags 0..N_MISS-1, and always
    // accepts a response. With N_MISS 1 mem_tag is 0 and rsp_* are ignored.
    output wire [3:0]      mem_tag,
    // Line reads (only with RV64_OOO_DLINE): beats - 1 of a split read; the beats answer critical first,
    // then the rest of the line wrapping, each as its own rsp_* answer with the tag. 0 otherwise.
`ifdef RV64_OOO_DLINE
    output wire [2:0]      mem_len,
`endif
    input  wire            rsp_valid,
    input  wire [3:0]      rsp_tag,
    input  wire [63:0]     rsp_data,
    input  wire            rsp_error
);
    // Wide out-of-order core (0.10.0), first configured after measurements of the Apple M5
    // performance core (useless-husband/m5-uarch); since 0.12.0 16 instructions per clock
    // through fetch, rename and retirement (wider than the M5's measured 10 per clock), a
    // 256-entry reorder buffer, 288 physical registers, a 128-entry issue queue, 8 integer ALUs of which 4 (3 until 0.14.6) also execute branches, jumps,
    // system instructions and multiply/divide, 4 load ports and 3 store-address ports (3 and 2 until 0.13.0).
    // Multiply takes 2 clocks (pipelined; 3 until 0.14.6), divide 7 (one unit). Loads that cannot finish
    // (cache miss, store data not ready, partial overlap with an older store) stay in
    // the issue queue and replay. Each branch saves the rename map, so a mispredict
    // recovers in the clock it executes. Stores write the bus when they retire (one per
    // clock). This is a behavioural simulation model: area and clock rate on an FPGA
    // are not considered yet.
    localparam [2:0] FETCH=0, EXECUTE=1, MEMORY=2, HALTED=3;
    localparam integer IC_INDEX = $clog2(ICACHE_BEATS);
    localparam integer IC_TAG = 61 - IC_INDEX;
    // Data cache: 2-way set associative, DCACHE_BEATS 8-byte beats in all (memory 1), in lines of DLINE
    // bytes (RV64_OOO_DLINE, 8 = one beat per line, the cache until 0.17.0).
`ifdef RV64_OOO_DLINE
    localparam integer DLINE = `RV64_OOO_DLINE;
`else
    localparam integer DLINE = 8;
`endif
    localparam integer LB = DLINE / 8;                          // beats per line
    localparam integer LBB = LB >= 8 ? 3 : LB >= 4 ? 2 : LB >= 2 ? 1 : 0;
    localparam integer DC_SETS = DCACHE_BEATS / (2 * LB);
    localparam integer DC_INDEX = $clog2(DC_SETS);   // set-index bits, may be 0
    localparam integer DC_TAG = 61 - LBB - DC_INDEX;
    generate if (ICACHE_BEATS < 2 || (ICACHE_BEATS & (ICACHE_BEATS - 1)) != 0) begin : bad_icache_size
        initial $fatal(1, "ICACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    generate if (DCACHE_BEATS < 2 || (DCACHE_BEATS & (DCACHE_BEATS - 1)) != 0) begin : bad_dcache_size
        initial $fatal(1, "DCACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    generate if ((DLINE != 8 && DLINE != 16 && DLINE != 32 && DLINE != 64) || (LB > 1 && N_MISS < 2) || DCACHE_BEATS < 2 * LB) begin : bad_dline
        initial $fatal(1, "RV64_OOO_DLINE must be 8, 16, 32 or 64; above 8 it needs N_MISS >= 2 and DCACHE_BEATS >= 2 lines");
    end endgenerate
    generate if (EXTRA_WRITES < 0 || EXTRA_WRITES > 2 || (EXTRA_WRITES != 0 && PAIR_WRITES == 0)) begin : bad_extra_writes
        initial $fatal(1, "EXTRA_WRITES must be 0, 1 or 2, and needs PAIR_WRITES");
    end endgenerate
    generate if (N_MISS < 1 || N_MISS > 8) begin : bad_n_miss
        initial $fatal(1, "N_MISS must be 1 to 8 (tags 8-15 are kept for instruction-side requests)");
    end endgenerate
    localparam integer FW = 32;          // fetch and rename width (RW until 0.13.0)
    localparam integer ROB_N = 512;       // 256 until 0.13.0
    localparam integer ROB_B = 9;
`ifdef RV64_OOO_FPU
    localparam integer FPU_MAP = 1;           // f0-f31 in the rename map (FPU is declared with the FP ports)
`else
    localparam integer FPU_MAP = 0;
`endif
    localparam integer AR_B = FPU_MAP != 0 ? 6 : 5;      // architectural register index: {is_f, reg} with FPU
    localparam integer NAR = 1 << AR_B;              // 64 with FPU (x0-x31, f0-f31), else 32
    localparam integer PRF_N = NAR + ROB_N;
    localparam integer P_B = 10;
    localparam integer IQ_N = 128;
    localparam integer IQ_B = $clog2(IQ_N);   // was the literal 7 (IQ_N 128)
    localparam integer Q_N = 64;
    localparam integer Q_B = 6;
    localparam integer N_ALU = 8;        // integer ports
    localparam integer N_BR = 4;         // of which these also take branches, system and M (3 until 0.14.6)
    localparam integer N_LD = 4;         // load ports (Zen 5: 4 loads per clock)
    localparam integer N_ST = 3;         // store-address ports (Lion Cove: 3)
    // F/D execution (RV64_OOO_FPU, default off): FP ports after the store-address ports.
`ifdef RV64_OOO_FPU
    localparam integer FPU = 1;
`else
    localparam integer FPU = 0;
`endif
    localparam integer N_FMA = FPU ? 2 : 0;    // FMA, FMUL, FADD
    localparam integer N_FMISC = FPU ? 2 : 0;  // FADD, min/max, compare, class, sign injection, conversions, moves; the first starts divide/sqrt
    localparam integer N_FP = N_FMA + N_FMISC;
    localparam integer P_FP = N_ALU + N_LD + N_ST;
    // FP latencies (MUL_LAT convention), 0.17.1: FADD 2 / FMUL 3 / FMA 4 as Lion Cove and Zen 5
    // (uops.info: ADDSD/SS, MULSD/SS, VFMADD231SD/SS); FADD 3 and FMUL = FMA 4 until 0.17.0.
    localparam integer FMA_LAT = 4, FMUL_LAT = 3, FADD_LAT = 2, FCVT_LAT = 3, FMISC_LAT = 2;   // behavioural assumptions
    // Divide/sqrt latencies of Lion Cove (uops.info DIVSS/DIVSD/SQRTSS/SQRTSD); 11/13/12/18 until 0.17.1.
    localparam integer FDIV_S = 7, FDIV_D = 10, FSQRT_S = 10, FSQRT_D = 15;
    // Divide/sqrt initiation intervals (clocks between starts; uops.info measured throughput of
    // DIVSS/DIVSD/SQRTSS/SQRTSD on Alder Lake-P and Zen 4). Behavioural assumption.
    localparam integer FDIV_II_S = 2, FDIV_II_D = 4, FSQRT_II_S = 4, FSQRT_II_D = 6;   // FDIV_II_S 3 until 0.17.1
    localparam integer NP = N_ALU + N_LD + N_ST + N_FP;
    localparam integer MUL_LAT = 2;         // 3 until 0.14.6; 2 is a behavioural assumption (DSP timing unproven)
    localparam integer DIV_LAT = 7;
    localparam integer MQ_N = N_BR * MUL_LAT;   // multiplies in flight (8 until 0.14.x; must be >= N_BR * (MUL_LAT - 1))
    localparam integer BTB_BITS = 10;    // 1024 entries (256 until 0.11.1)
    localparam integer BTB_TAG = 10;
    localparam integer BTB_ENTRIES = 1 << BTB_BITS;
    localparam integer RAS_N = 64;     // return stack entries (16 until 0.14.1)
    localparam integer RAS_B = 6;
    localparam integer LP_BITS = 10;     // loop predictor: 1024 entries (256 in 0.11.0)
    localparam integer LP_N = 1 << LP_BITS;
    localparam integer LP_TAG = 10;
    localparam integer TAKEN_MAX = 4;    // predicted-taken transfers followed per fetch group (2 from 0.10.1)
    // Fetch in a branch-recovery clock (frontend 11): 0 none (before), 1 the redirect target's
    // beat (default), 2 a whole fetch group (a zero-clock redirect: an idealization for studies).
    localparam integer RC_FETCH = 1;
    localparam integer CR_MAX = 4;       // calls and returns per fetch group (1 until 0.12.0)
    localparam [1:0] C_ALU = 0, C_FULL = 1, C_LD = 2, C_ST = 3;
    integer i, j, k, s, p;

    reg halted, started;

    // B extension (0.6.0): Zba, Zbb and Zbs, per the RISC-V bit-manipulation
    // specification; encodings checked against LLVM's assembler. Returns
    // {valid, result}; valid is 0 for anything that is not a B instruction.
    function automatic [64:0] bitmanip(input [31:0] ins, input [63:0] x, input [63:0] y);
        reg [6:0] opb, f7b;
        reg [2:0] f3b;
        reg [5:0] f6b, sh6;
        reg [11:0] f12b;
        reg [4:0] sh5;
        reg [63:0] r, xw;
        reg [31:0] w;
        reg ok;
        integer k;
        begin
            opb = ins[6:0]; f3b = ins[14:12]; f7b = ins[31:25]; f6b = ins[31:26];
            f12b = ins[31:20]; sh6 = ins[25:20]; sh5 = ins[24:20];
            xw = {32'b0, x[31:0]};
            ok = 1; r = 0; w = 0;
            case (opb)
                7'h33: case ({f7b, f3b})
                    {7'h10, 3'd2}: r = (x << 1) + y;
                    {7'h10, 3'd4}: r = (x << 2) + y;
                    {7'h10, 3'd6}: r = (x << 3) + y;
                    {7'h20, 3'd7}: r = x & ~y;
                    {7'h20, 3'd6}: r = x | ~y;
                    {7'h20, 3'd4}: r = ~(x ^ y);
                    {7'h05, 3'd4}: r = ($signed(x) < $signed(y)) ? x : y;
                    {7'h05, 3'd5}: r = (x < y) ? x : y;
                    {7'h05, 3'd6}: r = ($signed(x) < $signed(y)) ? y : x;
                    {7'h05, 3'd7}: r = (x < y) ? y : x;
                    {7'h30, 3'd1}: r = (x << y[5:0]) | (x >> (7'd64 - {1'b0, y[5:0]}));
                    {7'h30, 3'd5}: r = (x >> y[5:0]) | (x << (7'd64 - {1'b0, y[5:0]}));
                    {7'h24, 3'd1}: r = x & ~(64'd1 << y[5:0]);
                    {7'h24, 3'd5}: r = {63'b0, x[y[5:0]]};
                    {7'h34, 3'd1}: r = x ^ (64'd1 << y[5:0]);
                    {7'h14, 3'd1}: r = x | (64'd1 << y[5:0]);
                    default: ok = 0;
                endcase
                7'h3b: case ({f7b, f3b})
                    {7'h04, 3'd0}: r = xw + y;
                    {7'h04, 3'd4}: if (ins[24:20] == 0) r = {48'b0, x[15:0]}; else ok = 0;
                    {7'h10, 3'd2}: r = (xw << 1) + y;
                    {7'h10, 3'd4}: r = (xw << 2) + y;
                    {7'h10, 3'd6}: r = (xw << 3) + y;
                    {7'h30, 3'd1}: begin
                        w = (x[31:0] << y[4:0]) | (x[31:0] >> (6'd32 - {1'b0, y[4:0]}));
                        r = {{32{w[31]}}, w};
                    end
                    {7'h30, 3'd5}: begin
                        w = (x[31:0] >> y[4:0]) | (x[31:0] << (6'd32 - {1'b0, y[4:0]}));
                        r = {{32{w[31]}}, w};
                    end
                    default: ok = 0;
                endcase
                7'h13:
                    if (f3b == 1 && f12b == 12'h600) begin
                        r = 64; for (k = 0; k < 64; k = k + 1) if (x[k]) r = 63 - k;
                    end else if (f3b == 1 && f12b == 12'h601) begin
                        r = 64; for (k = 63; k >= 0; k = k - 1) if (x[k]) r = k;
                    end else if (f3b == 1 && f12b == 12'h602) begin
                        r = 0; for (k = 0; k < 64; k = k + 1) r = r + x[k];
                    end else if (f3b == 1 && f12b == 12'h604) r = {{56{x[7]}}, x[7:0]};
                    else if (f3b == 1 && f12b == 12'h605) r = {{48{x[15]}}, x[15:0]};
                    else if (f3b == 1 && f6b == 6'h12) r = x & ~(64'd1 << sh6);
                    else if (f3b == 1 && f6b == 6'h1a) r = x ^ (64'd1 << sh6);
                    else if (f3b == 1 && f6b == 6'h0a) r = x | (64'd1 << sh6);
                    else if (f3b == 5 && f6b == 6'h18) r = (x >> sh6) | (x << (7'd64 - {1'b0, sh6}));
                    else if (f3b == 5 && f6b == 6'h12) r = {63'b0, x[sh6]};
                    else if (f3b == 5 && f12b == 12'h287) begin
                        for (k = 0; k < 8; k = k + 1) r[8*k +: 8] = x[8*k +: 8] != 0 ? 8'hff : 8'h00;
                    end else if (f3b == 5 && f12b == 12'h6b8) begin
                        for (k = 0; k < 8; k = k + 1) r[8*k +: 8] = x[8*(7-k) +: 8];
                    end else ok = 0;
                7'h1b:
                    if (f3b == 1 && f6b == 6'h02) r = xw << sh6;
                    else if (f3b == 1 && f12b == 12'h600) begin
                        r = 32; for (k = 0; k < 32; k = k + 1) if (x[k]) r = 31 - k;
                    end else if (f3b == 1 && f12b == 12'h601) begin
                        r = 32; for (k = 31; k >= 0; k = k - 1) if (x[k]) r = k;
                    end else if (f3b == 1 && f12b == 12'h602) begin
                        r = 0; for (k = 0; k < 32; k = k + 1) r = r + x[k];
                    end else if (f3b == 5 && f7b == 7'h30) begin
                        w = (x[31:0] >> sh5) | (x[31:0] << (6'd32 - {1'b0, sh5}));
                        r = {{32{w[31]}}, w};
                    end else ok = 0;
                default: ok = 0;
            endcase
            bitmanip = {ok, r};
        end
    endfunction

    // Simple integer and B operations (from rv64_core.sv).
    function automatic [66:0] simple_alu(input [31:0] ins, input [63:0] x, input [63:0] y, input [63:0] pcv);
        reg [6:0] o, g7;
        reg [2:0] g3;
        reg [63:0] r, im;
        reg [31:0] w;
        reg ok, use1, use2;
        reg [64:0] bmv;
        begin
            o = ins[6:0]; g3 = ins[14:12]; g7 = ins[31:25];
            im = {{52{ins[31]}}, ins[31:20]};
            ok = 0; use1 = 1; use2 = 0; r = 0; w = 0;
            case (o)
                7'h37: begin ok = 1; use1 = 0; r = {{32{ins[31]}}, ins[31:12], 12'b0}; end
                7'h17: begin ok = 1; use1 = 0; r = pcv + {{32{ins[31]}}, ins[31:12], 12'b0}; end
                7'h13: begin
                    ok = 1;
                    case (g3)
                        0: r = x + im;
                        2: r = {63'b0, $signed(x) < $signed(im)};
                        3: r = {63'b0, x < im};
                        4: r = x ^ im;
                        6: r = x | im;
                        7: r = x & im;
                        1: begin ok = ins[31:26] == 0; r = x << ins[25:20]; end
                        5: begin
                            ok = ins[31:26] == 0 || ins[31:26] == 6'h10;
                            if (ins[30]) r = $signed(x) >>> ins[25:20]; else r = x >> ins[25:20];
                        end
                    endcase
                end
                7'h1b: begin
                    case (g3)
                        0: begin ok = 1; w = x[31:0] + im[31:0]; end
                        1: begin ok = g7 == 0; w = x[31:0] << ins[24:20]; end
                        5: begin
                            ok = g7 == 0 || g7 == 7'h20;
                            if (ins[30]) w = $signed(x[31:0]) >>> ins[24:20]; else w = x[31:0] >> ins[24:20];
                        end
                        default: ok = 0;
                    endcase
                    r = {{32{w[31]}}, w};
                end
                7'h33: begin
                    use2 = 1;
                    ok = g7 == 0 || (g7 == 7'h20 && (g3 == 0 || g3 == 5));
                    case (g3)
                        0: if (ins[30]) r = x - y; else r = x + y;
                        1: r = x << y[5:0];
                        2: r = {63'b0, $signed(x) < $signed(y)};
                        3: r = {63'b0, x < y};
                        4: r = x ^ y;
                        5: if (ins[30]) r = $signed(x) >>> y[5:0]; else r = x >> y[5:0];
                        6: r = x | y;
                        7: r = x & y;
                    endcase
                end
                7'h3b: begin
                    use2 = 1;
                    ok = (g7 == 0 && (g3 == 0 || g3 == 1 || g3 == 5)) || (g7 == 7'h20 && (g3 == 0 || g3 == 5));
                    case (g3)
                        0: if (ins[30]) w = x[31:0] - y[31:0]; else w = x[31:0] + y[31:0];
                        1: w = x[31:0] << y[4:0];
                        5: if (ins[30]) w = $signed(x[31:0]) >>> y[4:0]; else w = x[31:0] >> y[4:0];
                        default: w = 0;
                    endcase
                    r = {{32{w[31]}}, w};
                end
                default: ok = 0;
            endcase
            bmv = bitmanip(ins, x, y);
            if ((o == 7'h13 || o == 7'h1b || o == 7'h33 || o == 7'h3b) && bmv[64]) begin
                ok = 1; r = bmv[63:0]; use2 = o == 7'h33 || o == 7'h3b;
            end
            simple_alu = {ok, use1, use2, r};
        end
    endfunction

    // ---------------- execution helpers -------------------------------------------
    // Everything the full integer ports execute except multiply/divide results:
    // returns {exception, cause[3:0], tval[63:0], result[63:0], next_pc[63:0], mdu}.
    function automatic [197:0] exec_full(input [31:0] ins, input [63:0] pcv, input [63:0] x, input [63:0] y);
        reg [6:0] o, g7;
        reg [2:0] g3;
        reg [63:0] r, nx, iI, iB, iJ, iU;
        reg ok, tk, md;
        reg [66:0] sa;
        begin
            o = ins[6:0]; g3 = ins[14:12]; g7 = ins[31:25];
            iI = {{52{ins[31]}},ins[31:20]};
            iB = {{51{ins[31]}},ins[31],ins[7],ins[30:25],ins[11:8],1'b0};
            iJ = {{43{ins[31]}},ins[31],ins[19:12],ins[20],ins[30:21],1'b0};
            iU = {{32{ins[31]}},ins[31:12],12'b0};
            ok = 1; r = 0; nx = pcv + 64'd4; md = 0; tk = 0;
            sa = simple_alu(ins, x, y, pcv);
            case (o)
                7'h6f: begin r = pcv + 64'd4; nx = pcv + iJ; end
                7'h67: begin ok = g3 == 0; r = pcv + 64'd4; nx = (x + iI) & ~64'd1; end
                7'h63: begin
                    case (g3)
                        0: tk = x == y;
                        1: tk = x != y;
                        4: tk = $signed(x) < $signed(y);
                        5: tk = $signed(x) >= $signed(y);
                        6: tk = x < y;
                        7: tk = x >= y;
                        default: ok = 0;
                    endcase
                    if (tk) nx = pcv + iB;
                end
                7'h13, 7'h1b, 7'h33, 7'h3b, 7'h37, 7'h17: begin
                    if (sa[66]) r = sa[63:0];
                    else if ((o == 7'h33 || o == 7'h3b) && g7 == 7'h01) begin
                        md = 1; ok = o == 7'h33 || g3 == 0 || g3[2];
                    end else ok = 0;
                end
                7'h0f: ok = g3 == 0 || g3 == 1;
                7'h73: begin
                    if (ins == 32'h00000073) exec_full = {1'b1, 4'd11, 64'b0, 64'b0, nx, 1'b0};
                    else if (ins == 32'h00100073) exec_full = {1'b1, 4'd3, 64'b0, 64'b0, nx, 1'b0};
                    else ok = 0;
                end
                default: ok = 0;
            endcase
            if (o != 7'h73 || !(ins == 32'h00000073 || ins == 32'h00100073)) begin
                if (!ok) exec_full = {1'b1, 4'd2, {32'b0, ins}, 64'b0, nx, 1'b0};
                else if (nx[1:0] != 0) exec_full = {1'b1, 4'd0, nx, 64'b0, nx, 1'b0};
                else exec_full = {1'b0, 4'd0, 64'b0, r, nx, md && ok};
            end
        end
    endfunction
    function automatic [63:0] mul_value(input [2:0] g3, input word, input [63:0] x, input [63:0] y);
        reg signed [64:0] ma, mb;
        reg signed [129:0] pr;
        begin
            ma = {(g3 == 1 || g3 == 2) & x[63], x};
            mb = {(g3 == 1) & y[63], y};
            pr = ma * mb;
            mul_value = g3 != 0 ? pr[127:64] : word ? {{32{pr[31]}},pr[31:0]} : pr[63:0];
        end
    endfunction
    function automatic [63:0] div_value(input [2:0] g3, input word, input [63:0] x, input [63:0] y);
        reg sg, rm;
        reg [63:0] a64, b64, q, rr;
        reg signed [63:0] sa, sb;
        begin
            sg = !g3[0]; rm = g3[1];
            a64 = word ? (sg ? {{32{x[31]}},x[31:0]} : {32'b0,x[31:0]}) : x;
            b64 = word ? (sg ? {{32{y[31]}},y[31:0]} : {32'b0,y[31:0]}) : y;
            sa = a64; sb = b64;
            if (b64 == 0) begin q = {64{1'b1}}; rr = a64; end
            else if (sg && a64 == (word ? 64'hffffffff80000000 : 64'h8000000000000000) && b64 == {64{1'b1}}) begin
                q = a64; rr = 0;
            end else if (sg) begin q = sa / sb; rr = sa % sb; end
            else begin q = a64 / b64; rr = a64 % b64; end
            div_value = rm ? (word ? {{32{rr[31]}},rr[31:0]} : rr) : (word ? {{32{q[31]}},q[31:0]} : q);
        end
    endfunction
    function automatic [63:0] load_align(input [63:0] beat, input [2:0] lane, input [2:0] size);
        reg [63:0] sh;
        begin
            sh = beat >> {lane,3'b000};
            case (size)
                3'b000: load_align = {{56{sh[7]}},sh[7:0]};
                3'b001: load_align = {{48{sh[15]}},sh[15:0]};
                3'b010: load_align = {{32{sh[31]}},sh[31:0]};
                3'b011: load_align = sh;
                3'b100: load_align = {56'b0,sh[7:0]};
                3'b101: load_align = {48'b0,sh[15:0]};
                3'b110: load_align = {32'b0,sh[31:0]};
                default: load_align = 64'b0;
            endcase
        end
    endfunction
    function automatic [7:0] size_bytes(input [1:0] sz);
        size_bytes = sz == 0 ? 8'h01 : sz == 1 ? 8'h03 : sz == 2 ? 8'h0f : 8'hff;
    endfunction

    // ---------------- state -------------------------------------------------------
    reg [63:0] prf [0:PRF_N-1];          // physical register 0 is x0, always zero
    reg [PRF_N-1:0] prf_ready, prf_written, free_mask;
    reg [P_B-1:0] rat [0:NAR-1];
    reg [P_B-1:0] rrat [0:NAR-1];
    reg [P_B-1:0] snap [0:ROB_N-1][0:NAR-1];   // rename map after each control transfer
    // Reorder buffer.
    reg [ROB_N-1:0] rb_live, rb_done, rb_exc, rb_store, rb_load, rb_fencei, rb_writes, rb_ctl, rb_taken, rb_ret, rb_bhit, rb_sta;
    reg [1:0] rb_bctr [0:ROB_N-1];
    reg [63:0] rb_pc [0:ROB_N-1];
    reg [63:0] rb_next [0:ROB_N-1];
    reg [63:0] rb_value [0:ROB_N-1];
    reg [63:0] rb_cause [0:ROB_N-1];
    reg [63:0] rb_tval [0:ROB_N-1];
    reg [63:0] rb_addr [0:ROB_N-1];
    reg [31:0] rb_insn [0:ROB_N-1];
    reg [AR_B-1:0] rb_rd [0:ROB_N-1];
    reg [ROB_N-1:0] rb_fsw;                  // FSW: store data is bits 31:0 (FPU)
    reg [RW-1:0] rt_rdfp;                    // PROVISIONAL trace field (FPU): slot's rd is an f register
    reg [P_B-1:0] rb_pdst [0:ROB_N-1];
    reg [P_B-1:0] rb_opdst [0:ROB_N-1];
    reg [P_B-1:0] rb_sps2 [0:ROB_N-1];
    reg [7:0] rb_wstrb [0:ROB_N-1];
    reg [RAS_B-1:0] rb_rsp [0:ROB_N-1];      // return-stack pointer after this instruction's fetch
    reg [63:0] rb_rtos [0:ROB_N-1];          // and the top entry's value then (restored with it)
    reg [ROB_B-1:0] rb_head, rb_tail;
    reg [ROB_B:0] rb_count;
    // Issue queue.
    reg [IQ_N-1:0] iq_valid, iq_issued, iq_writes, iq_ptaken, iq_mdu;
    reg [2:0] iq_cls [0:IQ_N-1];
    reg [ROB_B-1:0] iq_rob [0:IQ_N-1];
    reg [63:0] iq_pc [0:IQ_N-1];
    reg [63:0] iq_pred [0:IQ_N-1];
    reg [63:0] iq_alt [0:IQ_N-1];
    reg [31:0] iq_insn [0:IQ_N-1];
    reg [P_B-1:0] iq_ps1 [0:IQ_N-1];
    reg [P_B-1:0] iq_ps2 [0:IQ_N-1];
    reg [P_B-1:0] iq_pdst [0:IQ_N-1];
    // Execute stage, one per port: ALU ports, then load ports, then store ports.
    reg [NP-1:0] ex_valid, ex_writes, ex_ptaken;
    reg [IQ_B-1:0] ex_iq [0:NP-1];
    reg [2:0] ex_cls [0:NP-1];
    reg [ROB_B-1:0] ex_rob [0:NP-1];
    reg [63:0] ex_pc [0:NP-1];
    reg [63:0] ex_pred [0:NP-1];
    reg [63:0] ex_alt [0:NP-1];
    reg [31:0] ex_insn [0:NP-1];
    reg [P_B-1:0] ex_ps1 [0:NP-1];
    reg [P_B-1:0] ex_ps2 [0:NP-1];
    reg [P_B-1:0] ex_pdst [0:NP-1];
    // FP execute state (RV64_OOO_FPU); rename fills the iq_ fields, retirement reads rb_fflags.
    localparam [2:0] C_FP = 4;
    reg [P_B-1:0] iq_ps3 [0:IQ_N-1];
    reg [4:0] iq_fop [0:IQ_N-1];
    reg [IQ_N-1:0] iq_fsz;
    reg [2:0] iq_rm [0:IQ_N-1];
    reg [1:0] iq_funit [0:IQ_N-1];
    reg [P_B-1:0] ex_ps3 [0:NP-1];
    reg [4:0] ex_fop [0:NP-1];
    reg [NP-1:0] ex_fsz;
    reg [2:0] ex_rm [0:NP-1];
    reg [1:0] ex_funit [0:NP-1];
    reg [4:0] rb_fflags [0:ROB_N-1];
    reg [7:0] fcsr;                     // frm[7:5], fflags[4:0]; written at retirement (middle)
    localparam integer FQ_N = N_FP > 0 ? N_FP * 4 + 8 : 1;   // + divides/square roots in flight
    reg [FQ_N-1:0] fq_valid, fq_writes;
    reg [4:0] fq_cnt [0:FQ_N-1];
    reg [4:0] fd_gap;                   // clocks until the divide/sqrt unit takes a new operation
    reg [ROB_B-1:0] fq_rob [0:FQ_N-1];
    reg [P_B-1:0] fq_pdst [0:FQ_N-1];
    reg [63:0] fq_val [0:FQ_N-1];
    reg [4:0] fq_fl [0:FQ_N-1];
    reg fd_pend, fdtaken;               // a divide/sqrt executing this clock, or selected this clock
    reg [ROB_B-1:0] fd_grob;            // the divide/sqrt that last set fd_gap
    reg [68:0] fy;
    reg [2:0] frm_now;
    integer flat;
    // Multiply pipeline and divide unit.
    reg [MQ_N-1:0] mq_valid, mq_writes;
    // Load-to-use latency (0.14.x knob): a dependant is selected LD_LAT clocks after the load,
    // as for MUL_LAT. 1 = the load wakes its consumers when it issues (the default timing).
    // With LD_LAT >= 2 a load that answered makes its register ready LD_LAT - 2 clocks later.
`ifdef RV64_OOO_LD_LAT
    localparam integer LD_LAT = `RV64_OOO_LD_LAT;
`else
    localparam integer LD_LAT = 1;
`endif
    localparam integer LW_N = 2 * N_LD * LD_LAT;   // pending load wakeups
    reg [LW_N-1:0] lw_valid, lw_fin;     // lw_fin: the load finishes (rb_done) when it wakes
    reg [3:0] lw_cnt [0:LW_N-1];
    reg [ROB_B-1:0] lw_rob [0:LW_N-1];
    reg [P_B-1:0] lw_pdst [0:LW_N-1];
    // L0 beat buffer (hand-off 7): loads whose beat was read by one of the last L0_N load
    // answers wake after L0_LAT clocks instead of LD_LAT. Timing only (values from the L1 model).
`ifdef RV64_OOO_L0_N
    localparam integer L0_N = `RV64_OOO_L0_N;
`else
    localparam integer L0_N = 0;
`endif
`ifdef RV64_OOO_L0_LAT
    localparam integer L0_LAT = `RV64_OOO_L0_LAT;
`else
    localparam integer L0_LAT = 2;
`endif
    localparam integer L0_S = L0_N > 0 ? L0_N : 1;
    reg [60:0] l0_beat [0:L0_S-1];
    reg [L0_S-1:0] l0_v;
    integer l0_p, l0_k, ld_lat_now;
    reg l0_hit;
    task automatic ld_wake(input [P_B-1:0] pd, input [ROB_B-1:0] rob, input fin);
        integer q;
        reg placed;
        begin
            placed = 0;
            for (q = 0; q < LW_N; q = q + 1) if (!lw_valid[q] && !placed) begin
                placed = 1; lw_valid[q] = 1; lw_cnt[q] = ld_lat_now - 2; lw_rob[q] = rob; lw_pdst[q] = pd; lw_fin[q] = fin;
            end
            if (!placed) $fatal(1, "load wakeup queue full");
        end
    endtask
    reg [3:0] mq_cnt [0:MQ_N-1];
    reg [ROB_B-1:0] mq_rob [0:MQ_N-1];
    reg [P_B-1:0] mq_pdst [0:MQ_N-1];
    reg [63:0] mq_val [0:MQ_N-1];
    reg dv_busy, dv_writes;
    reg [3:0] dv_cnt;
    reg [ROB_B-1:0] dv_rob;
    reg [P_B-1:0] dv_pdst;
    reg [63:0] dv_val;
    // Caches (direct-mapped, 8-byte lines, write-through data cache).
    reg [ICACHE_BEATS-1:0] ic_valid;
    reg [IC_TAG-1:0] ic_tag [0:ICACHE_BEATS-1];
    reg [63:0] ic_data [0:ICACHE_BEATS-1];
    reg [2*DC_SETS-1:0] dc_valid;                 // per line
    reg [DC_TAG-1:0] dc_tag [0:2*DC_SETS-1];
    reg [63:0] dc_data [0:DCACHE_BEATS-1];
    // Line l is way l / DC_SETS of set l % DC_SETS. A fill replaces the way that was
    // not filled last in its set (for two ways, the older fill).
    reg [DC_SETS-1:0] dc_last;           // way of the set's most recent fill
    initial dc_last = 0;
    integer dc_l;
    function automatic integer dc_set(input [63:0] a);
        dc_set = (a >> (3 + LBB)) & (DC_SETS - 1);
    endfunction
    function automatic integer dc_di(input integer l, input [63:0] a);   // data index of a's beat in line l
        dc_di = l * LB + ((a >> 3) % LB);
    endfunction
    function automatic [60:0] dl_ln(input [63:0] a);                     // line number of a
        dl_ln = a[63:3] >> LBB;
    endfunction
    function automatic integer dc_line(input [63:0] a);   // line holding a's beat, else -1
        integer s0;
        begin
            s0 = dc_set(a);
            if (dc_valid[s0] && dc_tag[s0] == a[63 -: DC_TAG]) dc_line = s0;
            else if (dc_valid[DC_SETS + s0] && dc_tag[DC_SETS + s0] == a[63 -: DC_TAG]) dc_line = DC_SETS + s0;
            else dc_line = -1;
        end
    endfunction
    // Branch target buffer and return stack.
    reg [BTB_ENTRIES-1:0] btb_valid, btb_ret;
    reg [BTB_TAG-1:0] btb_tag [0:BTB_ENTRIES-1];
    reg [29:0] btb_target [0:BTB_ENTRIES-1];    // (target - PC) >> 2, signed (frontend 15)
    function automatic btb_fits(input [63:0] pc, input [63:0] t);
        reg [63:0] d;
        begin d = t - pc; btb_fits = d[1:0] == 0 && (d[63:31] == {33{1'b0}} || d[63:31] == {33{1'b1}}); end
    endfunction
    function automatic [29:0] btb_enc(input [63:0] pc, input [63:0] t);
        reg [63:0] d;
        begin d = t - pc; btb_enc = d[31:2]; end
    endfunction
    function automatic [63:0] btb_dec(input [63:0] pc, input [29:0] f);
        btb_dec = pc + {{32{f[29]}}, f, 2'b00};
    endfunction
    reg [1:0] btb_ctr [0:BTB_ENTRIES-1];
    reg [63:0] ras [0:RAS_N-1];
    reg [RAS_B-1:0] ras_sp;
    // Fetch.
    reg [63:0] f_pc;
    reg [63:0] q_pc [0:Q_N-1];
    reg [63:0] q_pred [0:Q_N-1];
    reg [31:0] q_insn [0:Q_N-1];
    reg [Q_N-1:0] q_fpred, q_bhit, q_fault, q_fmis;
    // Front-end depth (realistic-latency mode): extra clocks from fetch to rename; 0 = idealized.
    localparam integer FE_DEPTH = 0;
    reg [31:0] fe_clk;                 // clock count, for the fetch-queue stamps
    reg [31:0] q_t [0:Q_N-1];          // clock from which a queue entry may be renamed
    reg [1:0] q_bctr [0:Q_N-1];
    reg [RAS_B-1:0] q_rsp [0:Q_N-1];
    reg [63:0] q_rtos [0:Q_N-1];
    // Loop predictor (0.11.0): for each conditional branch, the run length of its usual
    // direction before one opposite outcome. An instance's iteration number comes from
    // the youngest earlier instance still in flight, else from the retired count, so
    // a discarded path leaves nothing to repair.
    reg [LP_N-1:0] lp_valid, lp_dir;
    reg [LP_TAG-1:0] lp_tag [0:LP_N-1];
    reg [7:0] lp_trip [0:LP_N-1];
    reg [7:0] lp_ret [0:LP_N-1];
    reg [1:0] lp_conf [0:LP_N-1];
    // Global-history direction predictor (frontend hand-off 12), over the base prediction.
    localparam integer TG_N = 6;           // tagged tables (0: off; 4 until hand-off 17)
    localparam integer TG_B = 10;          // index bits: 1024 entries per table
    localparam integer TG_T = 10;          // tag bits
    localparam integer GH_L = 128;         // global history (conditional-branch outcomes)
    localparam integer TG_PG = 4;          // conditional branches per fetch group (2 costs decompress 2.3%)
    localparam integer TG_RU = 4;          // trainings per clock
    localparam integer TQ_N = 32;          // training queue
    localparam integer TG_E = 1 << TG_B;
    localparam integer TG_NN = TG_N == 0 ? 1 : TG_N;
    function automatic integer tg_len(input integer t);
        tg_len = t == 0 ? 4 : t == 1 ? 8 : t == 2 ? 16 : t == 3 ? 32 : t == 4 ? 64 : 128;
    endfunction
    reg [TG_T-1:0] tg_tag [0:TG_NN*TG_E-1];
    reg [2:0] tg_ctr [0:TG_NN*TG_E-1];
    reg [1:0] tg_u [0:TG_NN*TG_E-1];
    reg [TG_NN*TG_E-1:0] tg_v;
    reg [3:0] tg_alt;                      // use-alt-on-new-entry counter
    reg [17:0] tg_age;
    integer tg_ap;                         // aging pointer over all entries
    reg [GH_L-1:0] f_gh, r_gh, cur_gh, d_redirect_gh;
    reg [GH_L-1:0] q_gh [0:Q_N-1];
    reg [GH_L-1:0] rb_gh [0:ROB_N-1];
    reg [GH_L-1:0] g_gh [0:FW-1];
    // per conditional branch: {lc, bp, provider (7 none), provider prediction, alternate, new}
    reg [7:0] q_tp [0:Q_N-1];
    reg [7:0] rb_tp [0:ROB_N-1];
    reg [7:0] g_tp [0:FW-1];
    reg g_lpc;
    integer g_cb, n_tq, tq_cnt, tq_h, tq_k;
    reg [63:0] tq_pc [0:TQ_N-1];
    reg [GH_L-1:0] tq_gh [0:TQ_N-1];
    reg [8:0] tq_b [0:TQ_N-1];             // {taken, rb_tp}
    function automatic [15:0] tg_fold(input [GH_L-1:0] h, input integer len, input integer w);
        integer k;
        begin
            tg_fold = 0;
            for (k = 0; k < GH_L; k = k + 1) if (k < len) tg_fold[k % w] = tg_fold[k % w] ^ h[k];
        end
    endfunction
    function automatic [15:0] tg_pcf(input [63:0] pc, input integer w);   // all PC bits folded
        integer k;
        begin
            tg_pcf = 0;
            for (k = 2; k < 64; k = k + 1) tg_pcf[(k - 2) % w] = tg_pcf[(k - 2) % w] ^ pc[k];
        end
    endfunction
    function automatic integer tg_idx(input [63:0] pc, input [GH_L-1:0] h, input integer t);
        reg [TG_B-1:0] x;
        begin
            x = tg_pcf(pc, TG_B) ^ tg_fold(h, tg_len(t), TG_B) ^ (t * 337);
            tg_idx = t * TG_E + x;
        end
    endfunction
    function automatic [TG_T-1:0] tg_tg(input [63:0] pc, input [GH_L-1:0] h, input integer t);
        // The PC folded to TG_T-1 bits here and to TG_B bits in the index: bit differences that
        // cancel in one fold (distance a multiple of TG_B) do not cancel in the other.
        tg_tg = tg_pcf(pc, TG_T - 1) ^ tg_fold(h, tg_len(t), TG_T) ^ (tg_fold(h, tg_len(t), TG_T - 1) << 1);
    endfunction
    // Lookup: {hit, final prediction, provider table, provider prediction, alternate prediction, provider new}.
    function automatic [7:0] tg_look(input [63:0] pc, input [GH_L-1:0] h, input bp);
        integer t, p, a, ix;
        reg pp, pa, nw;
        begin
            p = -1; a = -1;
            for (t = 0; t < TG_N; t = t + 1) begin
                ix = tg_idx(pc, h, t);
                if (tg_v[ix] && tg_tag[ix] == tg_tg(pc, h, t)) begin a = p; p = t; end
            end
            pp = 0; pa = bp; nw = 0;
            if (p >= 0) begin
                ix = tg_idx(pc, h, p); pp = tg_ctr[ix][2];
                nw = (tg_ctr[ix] == 3 || tg_ctr[ix] == 4) && tg_u[ix] == 0;
            end
            if (a >= 0) begin ix = tg_idx(pc, h, a); pa = tg_ctr[ix][2]; end
            tg_look = {p >= 0, p < 0 ? bp : (nw && tg_alt >= 8) ? pa : pp, p < 0 ? 3'd7 : p[2:0], pp, pa, nw};
        end
    endfunction
    // Indirect-target predictor (frontend, RV64_OOO_ITTAGE, default off): ITTAGE-style tagged
    // tables (Seznec and Michaud, JILP 2006) over the BTB's last target, for non-return JALRs,
    // indexed by the PC and a path history of indirect targets. Prediction at fetch; training
    // at retirement from the history the JALR was fetched with (tables re-read there).
`ifdef RV64_OOO_ITTAGE
    localparam integer IT_N = 5;           // tagged tables
`else
    localparam integer IT_N = 0;
`endif
    localparam integer IT_B = 9;           // index bits per table
    localparam integer IT_T = 12;          // tag bits
    localparam integer IT_S = 8;           // path-history bits per indirect target
    localparam integer IT_PG = 2;          // non-return JALRs per fetch group
    localparam integer IT_RU = 2;          // non-return JALRs retired (trained) per clock
    localparam integer IT_E = 1 << IT_B;
    localparam integer IT_NN = IT_N == 0 ? 1 : IT_N;
    function automatic integer it_len(input integer t);   // path-history bits of table t
        it_len = t == 0 ? 8 : t == 1 ? 16 : t == 2 ? 32 : t == 3 ? 64 : 128;
    endfunction
    reg [IT_T-1:0] it_tag [0:IT_NN*IT_E-1];
    reg [29:0] it_tgt [0:IT_NN*IT_E-1];        // (target - PC) >> 2, signed, as the BTB
    reg [1:0] it_ctr [0:IT_NN*IT_E-1];         // confidence
    reg [1:0] it_u [0:IT_NN*IT_E-1];           // useful
    reg [IT_NN*IT_E-1:0] it_v;
    reg [5:0] it_age;
    integer it_ap, g_ij, n_it;
    reg [65:0] it_r;
    reg [GH_L-1:0] f_ph, r_ph, cur_ph, d_redirect_ph;   // path history: fetch, retirement
    reg [GH_L-1:0] q_ph [0:Q_N-1];
    reg [GH_L-1:0] rb_ph [0:ROB_N-1];          // before the instruction
    reg [GH_L-1:0] g_ph [0:FW-1];
    reg [63:0] rb_ipt [0:ROB_N-1];             // fetch-time predicted next PC
    function automatic is_ind(input [31:0] w);   // a JALR that is not a return
        is_ind = w[6:0] == 7'h67 && w[14:12] == 0 && !(w[11:7] == 0 && (w[19:15] == 1 || w[19:15] == 5));
    endfunction
    function automatic [GH_L-1:0] ph_upd(input [GH_L-1:0] h, input [63:0] t);
        reg [15:0] f;
        begin f = tg_pcf(t, IT_S); ph_upd = {h[GH_L-1-IT_S:0], f[IT_S-1:0]}; end
    endfunction
    function automatic integer it_idx(input [63:0] pc, input [GH_L-1:0] h, input integer t);
        reg [IT_B-1:0] x;
        begin
            x = tg_pcf(pc, IT_B) ^ tg_fold(h, it_len(t), IT_B) ^ (t * 337);
            it_idx = t * IT_E + x;
        end
    endfunction
    function automatic [IT_T-1:0] it_tg(input [63:0] pc, input [GH_L-1:0] h, input integer t);
        it_tg = tg_pcf(pc, IT_T - 1) ^ tg_fold(h, it_len(t), IT_T) ^ (tg_fold(h, it_len(t), IT_T - 1) << 1);
    endfunction
    // Lookup: {hit, weak, target}. The longest matching table provides; while its entry is new
    // (confidence and useful 0) the next matching table does; weak: new and no other match.
    function automatic [65:0] it_look(input [63:0] pc, input [GH_L-1:0] h);
        integer t, p, a, ix;
        begin
            p = -1; a = -1; it_look = 0;
            for (t = 0; t < IT_N; t = t + 1) begin
                ix = it_idx(pc, h, t);
                if (it_v[ix] && it_tag[ix] == it_tg(pc, h, t)) begin a = p; p = t; end
            end
            if (p >= 0) begin
                ix = it_idx(pc, h, p);
                if (it_ctr[ix] == 0 && it_u[ix] == 0) begin
                    if (a >= 0) ix = it_idx(pc, h, a);
                    it_look[64] = a < 0;
                end
                it_look[65] = 1; it_look[63:0] = btb_dec(pc, it_tgt[ix]);
            end
        end
    endfunction
    // Training at retirement: tk the actual target, wrong = the fetch-time prediction missed,
    // {bv, bt} the BTB's prediction (the alternate when no other table matches).
    task automatic it_train(input [63:0] pc, input [GH_L-1:0] h, input [63:0] tk, input wrong, input bv, input [63:0] bt);
        integer t, p, a, ix, done;
        reg pok, aok;
        begin
            p = -1; a = -1; pok = 0;
            for (t = 0; t < IT_N; t = t + 1) begin
                ix = it_idx(pc, h, t);
                if (it_v[ix] && it_tag[ix] == it_tg(pc, h, t)) begin a = p; p = t; end
            end
            if (p >= 0) begin
                ix = it_idx(pc, h, p);
                pok = btb_dec(pc, it_tgt[ix]) == tk;
                aok = a >= 0 ? btb_dec(pc, it_tgt[it_idx(pc, h, a)]) == tk : (bv && bt == tk);
                if (pok != aok) it_u[ix] = pok ? (it_u[ix] == 3 ? 2'd3 : it_u[ix] + 2'd1) : (it_u[ix] == 0 ? 2'd0 : it_u[ix] - 2'd1);
                if (pok) it_ctr[ix] = it_ctr[ix] == 3 ? 2'd3 : it_ctr[ix] + 2'd1;
                else if (it_ctr[ix] != 0) it_ctr[ix] = it_ctr[ix] - 2'd1;
                else if (btb_fits(pc, tk)) it_tgt[ix] = btb_enc(pc, tk);
                else it_v[ix] = 0;
            end
            if (wrong && p < IT_N - 1 && btb_fits(pc, tk)) begin   // allocate on a fetch-time miss (rev. 2, Codex finding 4)
                done = 0;
                for (t = p + 1; t < IT_N; t = t + 1) begin
                    ix = it_idx(pc, h, t);
                    if (!done && (!it_v[ix] || it_u[ix] == 0)) begin
                        done = 1; it_v[ix] = 1; it_tag[ix] = it_tg(pc, h, t); it_tgt[ix] = btb_enc(pc, tk); it_ctr[ix] = 0; it_u[ix] = 0;
                    end
                end
                if (!done) for (t = p + 1; t < IT_N; t = t + 1) begin
                    ix = it_idx(pc, h, t); if (it_u[ix] != 0) it_u[ix] = it_u[ix] - 2'd1;
                end
            end
            // Aging, spread out: one entry's useful bits halve every 64 trainings.
            it_age = it_age + 1;
            if (it_age == 0) begin
                it_u[it_ap] = it_u[it_ap] >> 1; it_ap = it_ap == IT_NN*IT_E - 1 ? 0 : it_ap + 1;
            end
        end
    endtask
    function automatic br_cond(input [2:0] f3, input [63:0] x, input [63:0] y);
        case (f3)
            3'd0: br_cond = x == y;
            3'd1: br_cond = x != y;
            3'd4: br_cond = $signed(x) < $signed(y);
            3'd5: br_cond = $signed(x) >= $signed(y);
            3'd6: br_cond = x < y;
            default: br_cond = x >= y;
        endcase
    endfunction
    // Training (from the queue): tp = {lc, bp, provider, pp, pa, nw} recorded at fetch.
    task automatic tg_train(input [63:0] pc, input [GH_L-1:0] h, input [7:0] tp, input tk);
        integer p, t, ix, done;
        reg wrong, bp;
        begin
            bp = tp[6];
            if (!tp[7]) begin
                p = tp[5:3] == 7 ? -1 : tp[5:3];
                if (p >= 0) begin
                    ix = tg_idx(pc, h, p);
                    if (tg_v[ix] && tg_tag[ix] == tg_tg(pc, h, p)) begin
                        if (tp[0] && tp[2] != tp[1]) tg_alt = (tp[1] == tk) ? (tg_alt == 15 ? 4'd15 : tg_alt + 4'd1) : (tg_alt == 0 ? 4'd0 : tg_alt - 4'd1);
                        if (tp[2] != tp[1]) tg_u[ix] = (tp[2] == tk) ? (tg_u[ix] == 3 ? 2'd3 : tg_u[ix] + 2'd1) : (tg_u[ix] == 0 ? 2'd0 : tg_u[ix] - 2'd1);
                        tg_ctr[ix] = tk ? (tg_ctr[ix] == 7 ? 3'd7 : tg_ctr[ix] + 3'd1) : (tg_ctr[ix] == 0 ? 3'd0 : tg_ctr[ix] - 3'd1);
                    end
                end
                wrong = (p >= 0 ? tp[2] : bp) != tk;
                if (wrong && p < TG_N - 1) begin
                    // An earlier queued instance may already have allocated this branch in a
                    // longer table: then nothing is allocated (or decayed) again.
                    done = 0;
                    for (t = p + 1; t < TG_N; t = t + 1) begin
                        ix = tg_idx(pc, h, t);
                        if (tg_v[ix] && tg_tag[ix] == tg_tg(pc, h, t)) done = 1;
                    end
                    if (!done) begin : alloc
                    for (t = p + 1; t < TG_N; t = t + 1) begin
                        ix = tg_idx(pc, h, t);
                        if (!done && (!tg_v[ix] || tg_u[ix] == 0)) begin
                            done = 1; tg_v[ix] = 1; tg_tag[ix] = tg_tg(pc, h, t); tg_ctr[ix] = tk ? 3'd4 : 3'd3; tg_u[ix] = 0;
                        end
                    end
                    if (!done) for (t = p + 1; t < TG_N; t = t + 1) begin
                        ix = tg_idx(pc, h, t); if (tg_u[ix] != 0) tg_u[ix] = tg_u[ix] - 2'd1;
                    end
                    end
                end
                // Aging, spread out: one entry's useful bits halve every 64 trainings.
                tg_age = tg_age + 1;
                if (tg_age[5:0] == 0) begin
                    tg_u[tg_ap] = tg_u[tg_ap] >> 1; tg_ap = tg_ap == TG_NN*TG_E - 1 ? 0 : tg_ap + 1;
                end
            end
        end
    endtask
    reg [7:0] tg_r;
    reg [Q_N-1:0] q_lp, q_ld;                  // loop predictor decided; predicted direction
    reg [7:0] q_li [0:Q_N-1];                  // iteration number of this instance
    reg [ROB_N-1:0] rb_lp, rb_ld;
    reg [ROB_N-1:0] rb_fence;
    // Fusion: operand 1 / 2 of this entry is the result of the simple ALU instruction just
    // before it, computed here from that instruction's own sources.
    reg [IQ_N-1:0] iq_fz1, iq_fz2;
    reg [31:0] iq_fzi [0:IQ_N-1];
    reg [63:0] iq_fzpc [0:IQ_N-1];
    reg [P_B-1:0] iq_fza [0:IQ_N-1];
    reg [P_B-1:0] iq_fzb [0:IQ_N-1];
    reg [NP-1:0] ex_fz1, ex_fz2;
    reg [31:0] ex_fzi [0:NP-1];
    reg [63:0] ex_fzpc [0:NP-1];
    reg [P_B-1:0] ex_fza [0:NP-1];
    reg [P_B-1:0] ex_fzb [0:NP-1];
    reg pv_ok;
    reg [AR_B-1:0] pv_rd;
    reg [AR_B-1:0] ard_, ars1_, ars2_, ars3_;
    reg fpop_, fpld_, fpst_, uses3_, fdst_, fs1_, fs2_, fpw_;
    reg [20:0] fdc_;
    reg u2fp_;
    reg [P_B-1:0] ps3_;
    function automatic [63:0] fbox(input [63:0] x); fbox = {32'hffffffff, x[31:0]}; endfunction
    // PROVISIONAL trace fields (FP-CONTRACT.md section 7), kept together: rt_rdfp (above) and the
    // flags each retired slot raised.
    reg [RW*5-1:0] rt_ff;
    reg [RW-1:0] rt_csrw; reg [RW*8-1:0] rt_csrv;   // PROVISIONAL trace: slot wrote fcsr, and its new value
    reg [ROB_N-1:0] rb_csrw; reg [7:0] rb_csrv [0:ROB_N-1];
    reg csr_, csr_busy; reg [63:0] csr_old, csr_src, csr_new; reg [7:0] csr_fcsr;
    reg [31:0] pv_insn;
    reg [63:0] pv_pc;
    reg [P_B-1:0] pv_a, pv_b;
    reg cur_fz;                  // FENCE (not FENCE.I), 0.11.0
    // Value prediction: a load, multiply or divide whose last VP_CONF results were the
    // same gives that value to its consumers at rename; its own result is compared when
    // it executes, and a wrong guess refetches after it retires.
    localparam integer VP_BITS = 8;
    localparam integer VP_N = 1 << VP_BITS;
    localparam integer VP_TAG = 10;
    localparam integer VP_CONF = 31;
    localparam integer VP_PEN = 1;
    reg [VP_N-1:0] vp_valid;
    reg [VP_TAG-1:0] vp_tag [0:VP_N-1];
    reg [63:0] vp_val [0:VP_N-1];
    reg [5:0] vp_conf [0:VP_N-1];
    reg [1:0] vp_strk [0:VP_N-1];
    function automatic integer vp_thr(input [1:0] s);
        integer x;
        begin x = (VP_CONF + 1) << (VP_PEN ? s : 0); vp_thr = (x > 64 ? 64 : x) - 1; end
    endfunction
    reg [ROB_N-1:0] rb_vp, rb_vpbad;
    reg [63:0] rb_vpv [0:ROB_N-1];
    reg [VP_BITS-1:0] vpi;
    // Folding at rename (council): a map entry is a physical register plus an offset; an
    // eliminated instruction's result is its physical register's value plus rb_off.
    localparam integer FOLD = 1;
    localparam integer OFF_LAT = 1;      // extra clocks for a non-memory operand with an offset
    reg [63:0] rat_off [0:NAR-1];
    // Written this clock without an earlier wakeup (multiply, divide, value prediction):
    // an offset consumer may not be selected in the next clock (OFF_LAT, Codex 1609-2).
    reg [PRF_N-1:0] prf_late;
    reg [63:0] rrat_off [0:NAR-1];
    reg [63:0] snap_off [0:ROB_N-1][0:NAR-1];
    reg [ROB_N-1:0] rb_elim;
    reg [63:0] rb_off [0:ROB_N-1];
    reg [63:0] rb_soff [0:ROB_N-1];      // store data offset
    reg [63:0] iq_off1 [0:IQ_N-1];
    reg [63:0] iq_off2 [0:IQ_N-1];
    reg [63:0] ex_off1 [0:NP-1];
    reg [63:0] ex_off2 [0:NP-1];
    reg [P_B:0] refcnt [0:PRF_N-1];        // committed map entries + in-flight writers
    reg [63:0] o1_, o2_, eoff, jt_;
    reg [P_B-1:0] ep_;
    reg elim_, done_;
    // Rename-stage constant ALU and branch resolution (council middle, after 0.14.1).
    localparam integer CFOLD = 1;      // 0 off, 1 one level per clock, 2 chains
    localparam integer BRREN = 1;      // conditional branches with known outcome finish at rename
    reg [NAR-1:0] cf_lvl;                   // arch reg holds a constant computed this clock
    reg cf_now, br_now, bt_;
    integer n_cf, n_br;                  // debug: instructions per clock
    reg [66:0] csa_;
    reg [7:0] rb_li [0:ROB_N-1];
    reg [7:0] g_li [0:FW-1];
    reg [LP_BITS-1:0] g_lpi;
    reg [7:0] lp_it;
    reg [RAS_B-1:0] d_redirect_sp;
    reg [63:0] d_redirect_tos;
    reg [RAS_B-1:0] g_ras_pop_sp;
    reg f_stale;                    // the held fetch was issued before a redirect
    reg [FW-1:0] g_lpmask;
    reg g_lpu, g_lpd, lp_found, lp_d;
    reg [Q_N-1:0] q_lp_c;                      // queue entry is a conditional branch
    reg [LP_BITS-1:0] li_;
    integer qj;
    reg [Q_B-1:0] q_head, q_tail;
    reg [Q_B:0] q_count;
    reg f_err;                  // the last fetch of f_pc's beat failed
    reg f_hold;                 // a fetch fault was delivered: wait for a redirect
    // Bus: one request at a time, held until it completes.
    reg [1:0] bus_hold;         // 0 none, 1 fetch, 2 load miss, 3 store
    reg [63:0] hold_addr;
    reg hold_pair;              // a held store write carries a second store
    reg mu_valid;               // a load miss is waiting for its beat
    reg [63:0] mu_beat;
    reg mu_errv;                // the last load miss failed, for this beat
    // The last beat a load miss brought in stays readable here even if the cache line
    // is replaced before the load replays (so tiny caches cannot livelock); retiring
    // stores to that beat update it.
    reg fb_valid;
    reg [63:0] fb_beat, fb_data;
    // The load that asked for the miss owns the buffer until it completes: no other miss
    // starts before then, so the oldest missing load always gets its data.
    reg [ROB_B-1:0] mu_owner, fb_owner;
    reg fb_lock;                // fb_owner has not yet taken the buffered beat
    reg mu_owner_v;             // the load that asked for the miss is still in flight
    reg [63:0] mu_err_beat;
    reg [ROB_B-1:0] mu_err_owner;   // the load the failed fill belongs to (0.11.0)
    // Several misses in flight (memory hand-off 2, N_MISS > 1): split data reads. Entry 0 is the
    // miss unit above (the oldest load's); entries 1..N_MISS-1 fill the cache for younger loads.
    localparam integer SPLIT = N_MISS > 1;
    localparam integer PM_N = N_MISS > 1 ? N_MISS : 2;
    reg mu_sent;                // entry 0's request was accepted; its beat comes on rsp_*
    reg mu_stale;               // a store wrote its beat after the request was accepted
    reg [PM_N-1:0] pm_valid, pm_sent, pm_stale;   // younger-miss entries (index 0 unused)
    reg [63:0] pm_beat [0:PM_N-1];
    // Line fills (LB > 1): the line read by entry t, its beats received so far, bytes stores wrote since
    // the read was accepted (kept against the answer), and whether a beat answered with an error.
    reg [63:0] lb_data [0:PM_N-1][0:LB-1];
    reg [7:0] lb_wm [0:PM_N-1][0:LB-1];
    reg [3:0] lb_cnt [0:PM_N-1];
    reg [PM_N-1:0] lb_bad;
    integer lt, lk;
    reg [63:0] la;
    reg pf_v;                   // this clock's oldest younger miss (to allocate)
    reg [63:0] pc_beat [0:N_LD-1];   // this clock's younger-miss candidates
    reg [ROB_B-1:0] pc_age [0:N_LD-1];
    integer pc_n, pc_i;
    reg [63:0] pf_beat;
    reg [ROB_B-1:0] pf_age;
    reg pm_dup;
    integer pm_k, pm_free, pm_j;
    reg [3:0] hold_tag, bk_tag;
    // Wake-on-fill (middle): a sleeping load waits for the response to its beat (iq_wb) or,
    // with iq_wany, for any response.
    reg [IQ_N-1:0] iq_slp, iq_wany;
    reg [60:0] iq_wb [0:IQ_N-1];
    reg [IQ_B-1:0] ms_iq [0:N_LD-1];
    reg [60:0] ms_beat [0:N_LD-1];
    integer ms_n, ms_k, wk_k;
    reg ms_infl, ms_free;
    task automatic wake_beat(input [60:0] wb);   // the beat's line (the beat itself with 8-byte lines)
        for (wk_k = 0; wk_k < IQ_N; wk_k = wk_k + 1)
            if (iq_slp[wk_k] && (iq_wany[wk_k] || (iq_wb[wk_k] >> LBB) == (wb >> LBB))) begin iq_slp[wk_k] = 0; iq_wany[wk_k] = 0; end
    endtask
    task automatic wake_exact(input [60:0] wb);  // loads of this beat only (they can read the fill buffer)
        for (wk_k = 0; wk_k < IQ_N; wk_k = wk_k + 1)
            if (iq_slp[wk_k] && !iq_wany[wk_k] && iq_wb[wk_k] == wb) iq_slp[wk_k] = 0;
    endtask
    reg sf_wait;                // a store write faulted while split reads were outstanding: no new
                                // requests; the trap is taken, with the latched store, once they return
    reg [63:0] sf_pc, sf_addr;

`ifdef RV64_OOO_V
    // ---------------- RVV subset, step 1 (RV64_OOO_V; council simd) ----------------
    // build/cpu/fp/RVV-CONTRACT.md, executed in order at the head of the reorder buffer: a vector
    // instruction renames only into an empty ROB and holds rename until it retires, so it is never
    // speculative and nothing older can flush it. Architectural register file of 32 x VLEN bits.
    // Step 1 implements vsetvli/vsetivli/vsetvl, the vector CSRs, unit-stride and strided loads and
    // stores (EEW 8-64, masked, whole-register, mask, fault-only-first; element-precise faults with
    // vstart) and the FP32 vector instructions of the contract; the integer, mask-logical, permute and
    // indexed instructions are illegal (cause 2) in this step. Functional first: one memory element per
    // clock; other instructions take the scalar FP latency of their operation + beats - 1 (beats = DLEN-bit groups).
`ifndef RV64_OOO_FPU
    initial $fatal(1, "RV64_OOO_V needs RV64_OOO_FPU (vector FP uses the F state)");
`endif
`ifdef RV64_OOO_VLEN
    localparam integer VLEN = `RV64_OOO_VLEN;
`else
    localparam integer VLEN = 256;
`endif
`ifdef RV64_OOO_DLEN
    localparam integer DLEN = `RV64_OOO_DLEN;
`else
    localparam integer DLEN = VLEN;
`endif
    localparam integer VLENB = VLEN / 8;
    localparam integer VE_MAX = 8 * VLEN / 32;     // FP32 elements of an LMUL-8 group
    // Vector FP timing uses the scalar FP latency parameters (FMA_LAT, FMUL_LAT, FADD_LAT, FMISC_LAT, FCVT_LAT,
    // FDIV_S/FSQRT_S with FDIV_II_S/FSQRT_II_S), plus one clock per further DLEN beat (functional step: no pipes).
    initial if (!(VLEN == 128 || VLEN == 256 || VLEN == 512) || DLEN < 64 || DLEN > VLEN || (DLEN & (DLEN - 1)) != 0)
        $fatal(1, "RV64_OOO_VLEN must be 128, 256 or 512 and RV64_OOO_DLEN a power of two from 64 to VLEN");
    reg [VLEN-1:0] vreg [0:31];
    reg [63:0] vtype, vl, vstart;
    reg vxsat;
    reg [1:0] vxrm;
    reg v_busy;                              // a vector instruction is in the ROB
    reg [ROB_N-1:0] rb_vec, rb_vref;         // vector instruction; a vector store (refetch after it)
    // The head engine (one instruction at a time).
    reg [1:0] vx_st;                          // 0 start, 1 memory elements, 2 finishing
    integer vx_i, vx_evl, vx_cnt, vx_eewb, vx_regs, vx_start;
    reg vx_load, vx_vm, vx_whole, vx_mtail, vx_ff, vx_wv;
    reg [4:0] vx_vd;
    reg [63:0] vx_base, vx_stride, vx_res, vx_waddr, vx_wdata;
    reg [7:0] vx_wstrb;
    reg [4:0] vx_fl;
    // Trace records of the instruction in flight (RVV-CONTRACT.md 7), copied to rt_v* at retirement or
    // trap and printed by the simd testbench: C records (in order) and the V group (base, count).
    reg [4:0] vr_vb; reg [3:0] vr_vn; reg [1:0] vr_cn;
    reg [11:0] vr_csr [0:2]; reg [63:0] vr_cval [0:2];
    reg rt_vec, rt_vtrap; reg [4:0] rt_vb; reg [3:0] rt_vn; reg [1:0] rt_cn;
    reg [35:0] rt_vcsr; reg [191:0] rt_vcval;       // three C records, record k at bits 12k / 64k
    // scratch
    reg vok, vill_, vmask_any;
    integer vsew, vnum, vden, vlmax, vlm, vq, vr, vn2, vd2, vi2;
    reg [63:0] vt_, avl_, xs1_, xs2_, fsv_, vold_, vnew_, va_;
    reg [31:0] vfs_, vin_;
    reg [31:0] vtmp [0:VE_MAX-1];
    reg [VE_MAX-1:0] vtv;
    reg [36:0] vfr_;
    reg [5:0] vf6_;
    integer vemax_r, vlen_r;                 // VE_MAX and VLEN as run-time values (no loop unrolling)
    reg [2:0] vf3_;
    reg [4:0] vrd_, vrs1_, vvs2_;
    reg vvm_, vvf_;

    reg isv_, vfd_;                          // rename: a vector instruction; vfmv.f.s (writes f[rd])
`endif
    // ---------------- bus request (combinational) -------------------------------
    // The retiring store: the first store in the retirement window, when everything
    // before it there is finished, will retire this clock and is no fence.i.
    reg st_cand;
    reg [ROB_B-1:0] st_idx;
    reg st2_cand;               // a second store that can share the write
    reg [ROB_B-1:0] st2_idx;
    reg [1:0] sx_n;              // extra stores (third, fourth) that share the write
    reg [ROB_B-1:0] sx0_idx, sx1_idx;
    reg [1:0] hold_nx;           // extra stores of a held write
    reg [ROB_N-1:0] rb_viol;    // a finished load read bytes an older store then wrote
    localparam integer MDP_BITS = 12;   // load-wait table: 2^MDP_BITS entries by PC bits MDP_BITS+1:2
    localparam integer MDP_CLR = 65536;    // clocks between clears of the whole table (0: never)
    reg [(1 << MDP_BITS)-1:0] mdp_wait;
    function automatic [MDP_BITS-1:0] mdp_i(input [63:0] a); mdp_i = a[2 +: MDP_BITS]; endfunction
    // Instructions that retire and then end the retirement group with a refetch (fence.i,
    // a wrong value prediction): retirement and the store-write scan both stop after them.
`ifdef RV64_OOO_V
    wire [ROB_N-1:0] rb_ends = rb_fencei | rb_vpbad | rb_vref;
`else
    wire [ROB_N-1:0] rb_ends = rb_fencei | rb_vpbad;
`endif
    reg [ROB_N-1:0] rb_ldv;     // the load gave its consumers a value it read or forwarded
    reg [ROB_N-1:0] rb_ans;     // LD_LAT >= 2: the load answered and waits only for its wakeup
    reg rflush_ld;              // this clock's flush refetches a load that read stale bytes
    reg [ROB_B-1:0] rflush_e;   // that load
    reg [ROB_B-1:0] vc_e;       // memory-dependence check: a store between the two
    reg [7:0] vc_mask;          // bytes a resolving store makes stale
    integer vc_k;
    reg h_exc;
    always @* begin
        st_cand = 0; st_idx = 0; st2_cand = 0; st2_idx = 0; sx_n = 0; sx0_idx = 0; sx1_idx = 0;
        h_exc = rb_count != 0 && rb_done[rb_head] && rb_exc[rb_head];
        begin : scan
            reg stop;
            reg [ROB_B-1:0] e;
            integer sc_nb, sc_bud, sc_ni;
            stop = 0;
            sc_nb = 0; sc_ni = 0; sc_bud = TQ_N - (tq_cnt > TG_RU ? tq_cnt - TG_RU : 0);
            for (k = 0; k < RW; k = k + 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (!stop) begin
                    if (k >= rb_count || !rb_done[e] || rb_exc[e]) stop = 1;
                    // After the first store the scan looks for a second one; an instruction
                    // between them (or the second store) in the first store's beat ends it,
                    // since the first write would make it stale.
                    else if (rb_viol[e]) stop = 1;
                    else if (st_cand && (rb_pc[e][63:3] == rb_addr[st_idx][63:3] ||
                             (st2_cand && rb_pc[e][63:3] == rb_addr[st2_idx][63:3]) ||
                             (sx_n != 0 && rb_pc[e][63:3] == rb_addr[sx0_idx][63:3]))) stop = 1;
                    else if (TG_N != 0 && rb_ctl[e] && rb_insn[e][6:0] == 7'h63 && sc_nb >= sc_bud) stop = 1;
                    else if (IT_N != 0 && is_ind(rb_insn[e]) && sc_ni >= IT_RU) stop = 1;   // retirement's IT_RU stop
                    else if (rb_store[e]) begin
                        if (!st_cand) begin st_cand = 1; st_idx = e; if (!PAIR_WRITES) stop = 1; end
                        else if (!st2_cand) begin st2_cand = 1; st2_idx = e; if (EXTRA_WRITES == 0) stop = 1; end
                        else begin
                            if (sx_n == 0) sx0_idx = e; else sx1_idx = e;
                            sx_n = sx_n + 2'd1;
                            if (sx_n >= EXTRA_WRITES) stop = 1;
                        end
                    end
                    else if (rb_ends[e]) stop = 1;   // retirement refetches after these
                    if (!stop && TG_N != 0 && rb_ctl[e] && rb_insn[e][6:0] == 7'h63) sc_nb = sc_nb + 1;
                    if (!stop && IT_N != 0 && is_ind(rb_insn[e])) sc_ni = sc_ni + 1;
                end
            end
        end
    end
    wire [63:0] st_addr = rb_addr[st_idx];
    wire [63:0] st_wdata = ((prf[rb_sps2[st_idx]] + rb_soff[st_idx]) & (rb_fsw[st_idx] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {st_addr[2:0],3'b000};
    wire [63:0] st2_addr = rb_addr[st2_idx];
    wire pair_now = bus_hold == 3 ? hold_pair : st2_cand;
    // Extra stores carried by this write (held unchanged while the bus waits).
    wire [1:0] nx_now = bus_hold == 3 ? hold_nx : st2_cand ? sx_n : 2'd0;
    wire f_beat_hit = ic_valid[f_pc[3 +: IC_INDEX]] && ic_tag[f_pc[3 +: IC_INDEX]] == f_pc[63 -: IC_TAG];
    wire want_store = st_cand && !sf_wait;   // no write after a latched store fault
    wire want_miss = mu_valid && !mu_sent && !h_exc && !sf_wait;
    // The lowest-numbered younger entry waiting to be sent (a function, not always @*, so a
    // constant input with N_MISS 1 still gives a defined value in every simulator).
    function [4:0] pm_first(input [PM_N-1:0] m);
        integer q;
        begin
            pm_first = 0;
            for (q = PM_N - 1; q >= 1; q = q - 1) if (m[q]) pm_first = {1'b1, q[3:0]};
        end
    endfunction
    wire [4:0] pm_sel = pm_first(SPLIT ? pm_valid & ~pm_sent : {PM_N{1'b0}});
    wire pm_pick_v = pm_sel[4];
    wire [3:0] pm_pick = pm_sel[3:0];
    wire want_pm = pm_pick_v && !h_exc && !sf_wait;
    // A split read is outstanding (accepted, not yet answered): no trap is taken meanwhile.
    // (a function, so the clock block sees this clock's updates, not the value at the clock start)
    function split_out(input dummy);
        split_out = SPLIT && ((mu_valid && mu_sent) || (pm_valid & pm_sent) != {PM_N{1'b0}});
    endfunction
    // A beat some entry is reading (or will read).
    function in_flight(input [63:0] a);
        integer q;
        begin
            in_flight = mu_valid && dl_ln(mu_beat) == dl_ln(a);
            for (q = 1; q < PM_N; q = q + 1) if (pm_valid[q] && dl_ln(pm_beat[q]) == dl_ln(a)) in_flight = 1;
        end
    endfunction
    wire want_fetch = started && !halted && f_pc[1:0] == 0 && !f_beat_hit && !f_err && !f_hold && !h_exc && !sf_wait;
    // Priority: store write, the oldest load's miss, younger misses, fetch.
`ifdef RV64_OOO_V
    wire [1:0] bus_kind = halted ? 2'd0 : bus_hold != 0 ? bus_hold : (want_store || vx_wv) ? 2'd3 : want_miss ? 2'd2 :
`else
    wire [1:0] bus_kind = halted ? 2'd0 : bus_hold != 0 ? bus_hold : want_store ? 2'd3 : want_miss ? 2'd2 :
`endif
                          want_pm ? 2'd2 : want_fetch ? 2'd1 : 2'd0;
    assign mem_tag = bus_kind != 2 ? 4'd0 : bus_hold == 2 ? hold_tag : want_miss ? 4'd0 : pm_pick;
`ifdef RV64_OOO_DLINE
    assign mem_len = bus_kind == 2 && LB > 1 ? LB - 1 : 3'd0;   // a data read is a whole line
`endif
    assign mem_valid = !reset && bus_kind != 0;
    assign mem_instr = bus_kind == 1;
    assign mem_addr = bus_kind == 1 ? (bus_hold == 1 ? hold_addr : {f_pc[63:3],3'b000})
`ifdef RV64_OOO_V
                    : bus_kind == 2 ? (bus_hold == 2 ? hold_addr : want_miss ? mu_beat : pm_beat[pm_pick]) : (vx_wv ? vx_waddr : {st_addr[63:3],3'b000});
`else
                    : bus_kind == 2 ? (bus_hold == 2 ? hold_addr : want_miss ? mu_beat : pm_beat[pm_pick]) : {st_addr[63:3],3'b000};
`endif
`ifdef RV64_OOO_V
    assign mem_wdata = bus_kind == 3 ? (vx_wv ? vx_wdata : st_wdata) : 64'b0;
`else
    assign mem_wdata = bus_kind == 3 ? st_wdata : 64'b0;
`endif
`ifdef RV64_OOO_V
    assign mem_wstrb = bus_kind == 3 ? (vx_wv ? vx_wstrb : rb_wstrb[st_idx]) : 8'b0;
`else
    assign mem_wstrb = bus_kind == 3 ? rb_wstrb[st_idx] : 8'b0;
`endif
    assign mem_addr2 = bus_kind == 3 && pair_now ? {st2_addr[63:3],3'b000} : 64'b0;
    assign mem_wdata2 = bus_kind == 3 && pair_now ? ((prf[rb_sps2[st2_idx]] + rb_soff[st2_idx]) & (rb_fsw[st2_idx] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {st2_addr[2:0],3'b000} : 64'b0;
    assign mem_wstrb2 = bus_kind == 3 && pair_now ? rb_wstrb[st2_idx] : 8'b0;
    wire x0v = bus_kind == 3 && pair_now && nx_now != 0, x1v = bus_kind == 3 && pair_now && nx_now == 2;
    assign mem_xaddr = {x1v ? {rb_addr[sx1_idx][63:3],3'b000} : 64'b0, x0v ? {rb_addr[sx0_idx][63:3],3'b000} : 64'b0};
    assign mem_xwdata = {x1v ? ((prf[rb_sps2[sx1_idx]] + rb_soff[sx1_idx]) & (rb_fsw[sx1_idx] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {rb_addr[sx1_idx][2:0],3'b000} : 64'b0,
                         x0v ? ((prf[rb_sps2[sx0_idx]] + rb_soff[sx0_idx]) & (rb_fsw[sx0_idx] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {rb_addr[sx0_idx][2:0],3'b000} : 64'b0};
    assign mem_xwstrb = {x1v ? rb_wstrb[sx1_idx] : 8'b0, x0v ? rb_wstrb[sx0_idx] : 8'b0};
    wire [2:0] state = halted ? HALTED : (bus_kind >= 2) ? MEMORY : (bus_kind == 1) ? FETCH : EXECUTE;

    // ---------------- the clock -------------------------------------------------
    // Decisions are taken from the state at the start of the clock (phase 1), then
    // applied (phase 2), mirroring registered hardware.
    reg [ROB_B-1:0] e, b_rob, x_rob, o_age, a_age, ou_age, h_after;
    reg [ROB_B:0] n_ret;
    reg st1_seen, smc;
    reg st_last, wb2v;          // this clock's write is used up; a second beat written
    reg [60:0] wb1, wb2;        // beats written this clock
    reg [60:0] wb3, wb4;
    reg [2:0] st_n;             // stores retired with this clock's write
    reg [63:0] r_wd;
    reg ou_valid, mp_any, rflush, trap_now, stop, fired, fdone, ok, hit, full, dok;
    reg [7:0] fwd_mask, fwd_byte_w;
    reg fwd_wait, dc_hit_, fb_hit_;
    reg [63:0] fwd_data;
    integer b2;
    reg fo_valid;                   // an older FENCE has not retired (0.11.0)
    reg [ROB_B-1:0] fo_age;
    reg [63:0] mp_fix, rflush_pc, d_want, v, ea, tgt, npc, lw;
    reg [197:0] ef;
    reg [66:0] sa;
    reg [P_B-1:0] trat [0:NAR-1];
    reg [PRF_N-1:0] tready;
    reg [IQ_N-1:0] chosen;
    reg [IQ_B-1:0] pick [0:NP-1];
    reg [NP-1:0] pick_v;
    reg [IQ_B-1:0] best;
    reg bestv, divtaken;
    reg [ROB_B-1:0] best_age;
    reg [31:0] wi;
    reg [63:0] wpc;
    reg [6:0] op;
    reg [4:0] rd_, rs1_, rs2_;
    reg writes_, uses1_, uses2_, isfault, tkp, isctl;
    reg [P_B-1:0] ps1_, ps2_, pd_;
    reg [2:0] cls_;
    reg [7:0] bytes_;
    reg [ROB_B-1:0] fwd_e;
    reg fwd_hit, fwd_full;
    reg [63:0] g_pc [0:FW-1];
    reg [31:0] g_insn [0:FW-1];
    reg [63:0] g_pred [0:FW-1];
    reg [FW-1:0] g_fp, g_bh, g_fault, g_fmis;
    reg [1:0] g_bc [0:FW-1];
    reg [6:0] g_n;
    reg [63:0] g_next;
    reg [RAS_B-1:0] g_sp [0:FW-1];
    reg [63:0] g_tos [0:FW-1];
    reg [4:0] g_taken;
    reg [4:0] g_cr;
    reg [63:0] gras [0:RAS_N-1];      // the fetch group's copy of the return stack
    reg [RAS_B-1:0] cur_sp;
    reg [BTB_BITS-1:0] bi;
    reg [IC_INDEX-1:0] fi;
    reg [6:0] n_ren;
    reg d_redirect;
    reg [63:0] d_redirect_pc;
    reg [IQ_B-1:0] slot;
    reg slot_ok;
    reg [P_B-1:0] fp;
    reg fp_ok;
    reg [2:0] f3_;
    reg [ROB_B:0] rb_count_new;
    reg dv_pend;
    reg [IQ_B-1:0] fiq [0:FW-1];   // free issue-queue slots and physical registers, lowest first
    reg [P_B-1:0] fpl [0:FW-1];
    integer nfi, nfp, ui, up;
    reg miss_v;
    reg [63:0] miss_beat;
    reg [ROB_B-1:0] miss_age, miss_owner, ol_age;
    reg ol_valid;
    reg [Q_B-1:0] qa;

    initial if (RW < 3 || RW > 32) $fatal(1, "rv64_ooo.sv supports RW from 3 to 32, got %0d", RW);
    initial if (FDIV_II_S < 2 || FDIV_II_D < 2 || FSQRT_II_S < 2 || FSQRT_II_D < 2) $fatal(1, "FP divide/sqrt initiation intervals must be >= 2");
    initial if (LD_LAT < 1 || LD_LAT > 16) $fatal(1, "rv64_ooo.sv needs LD_LAT from 1 to 16, got %0d", LD_LAT);
    initial if (L0_N < 0 || L0_N > 64 || (L0_N > 0 && (L0_LAT < 2 || L0_LAT >= LD_LAT)))
        $fatal(1, "rv64_ooo.sv: L0_N 0..64, and with L0_N > 0 2 <= L0_LAT < LD_LAT (got L0_N %0d, L0_LAT %0d, LD_LAT %0d)", L0_N, L0_LAT, LD_LAT);
    initial if (MUL_LAT < 2) $fatal(1, "rv64_ooo.sv needs MUL_LAT >= 2, got %0d", MUL_LAT);

    // Fused producer's value for execute port pp.
    function [63:0] fz_value(input integer pp);
        reg [66:0] t;
        begin
            t = simple_alu(ex_fzi[pp], prf[ex_fza[pp]], prf[ex_fzb[pp]], ex_fzpc[pp]);
            fz_value = t[63:0];
        end
    endfunction
    // Operand values at execute: the register, or (fused, producer not yet written) the
    // producer's value computed from its sources.
    function [63:0] opa(input integer pp);
        opa = (ex_fz1[pp] && !prf_written[ex_ps1[pp]]) ? fz_value(pp) : prf[ex_ps1[pp]] + ex_off1[pp];
    endfunction
    function [63:0] opb(input integer pp);
        opb = (ex_fz2[pp] && !prf_written[ex_ps2[pp]]) ? fz_value(pp) : prf[ex_ps2[pp]] + ex_off2[pp];
    endfunction
    // F/D arithmetic and decoder (council backend; bit exact, checked against the FP golden model).
    // Bit-exact RISC-V F/D arithmetic as SystemVerilog functions (council backend, draft).
    // Pure SystemVerilog (no DPI), so Icarus and Verilator both run it. One entry point:
    //   fp_exec(op, d, rm, a, b, c) -> {fflags[4:0], result[63:0]}
    // d = 1: binary64, 0: binary32 (NaN-boxed in 64 bits). rm: 0 RNE, 1 RTZ, 2 RDN, 3 RUP, 4 RMM
    // (already resolved from frm by the caller). fflags: {NV, DZ, OF, UF, NX}. Tininess is
    // detected after rounding (RISC-V). NaN results are canonical. Encodings and the contract
    // (build/cpu/fp/FP-CONTRACT.md) decide how instructions map to these ops.
    localparam [4:0] FOP_ADD = 0, FOP_SUB = 1, FOP_MUL = 2, FOP_DIV = 3, FOP_SQRT = 4,
                     FOP_MADD = 5, FOP_MSUB = 6, FOP_NMSUB = 7, FOP_NMADD = 8,
                     FOP_MIN = 9, FOP_MAX = 10, FOP_EQ = 11, FOP_LT = 12, FOP_LE = 13, FOP_CLASS = 14,
                     FOP_SGNJ = 15, FOP_SGNJN = 16, FOP_SGNJX = 17,
                     FOP_CVT_W = 18, FOP_CVT_WU = 19, FOP_CVT_L = 20, FOP_CVT_LU = 21,     // fp -> int
                     FOP_CVT_FW = 22, FOP_CVT_FWU = 23, FOP_CVT_FL = 24, FOP_CVT_FLU = 25, // int -> fp
                     FOP_CVT_SD = 26, FOP_CVT_DS = 27,                                     // D->S, S->D
                     FOP_MV_XF = 28, FOP_MV_FX = 29;

    localparam integer FPW = 320;   // exact-arithmetic workspace

    // ---- formats
    function automatic integer fp_p(input d); fp_p = d ? 53 : 24; endfunction       // precision
    function automatic integer fp_bias(input d); fp_bias = d ? 1023 : 127; endfunction
    function automatic integer fp_emax_field(input d); fp_emax_field = d ? 2047 : 255; endfunction
    function automatic [63:0] fp_qnan(input d); fp_qnan = d ? 64'h7ff8000000000000 : 64'hffffffff7fc00000; endfunction
    // An FP32 value must be NaN-boxed; an unboxed one reads as the canonical NaN.
    function automatic [63:0] fp_in(input d, input [63:0] x);
        fp_in = d ? x : (x[63:32] == 32'hffffffff ? x : 64'hffffffff7fc00000);
    endfunction
    function automatic fp_sign(input d, input [63:0] x); fp_sign = d ? x[63] : x[31]; endfunction
    function automatic [10:0] fp_expf(input d, input [63:0] x); fp_expf = d ? x[62:52] : {3'b0, x[30:23]}; endfunction
    function automatic [51:0] fp_frac(input d, input [63:0] x); fp_frac = d ? x[51:0] : {29'b0, x[22:0]}; endfunction
    function automatic fp_isnan(input d, input [63:0] x);
        fp_isnan = fp_expf(d, x) == fp_emax_field(d) && fp_frac(d, x) != 0;
    endfunction
    function automatic fp_issnan(input d, input [63:0] x);
        fp_issnan = fp_isnan(d, x) && !(d ? x[51] : x[22]);
    endfunction
    function automatic fp_isinf(input d, input [63:0] x);
        fp_isinf = fp_expf(d, x) == fp_emax_field(d) && fp_frac(d, x) == 0;
    endfunction
    function automatic fp_iszero(input d, input [63:0] x);
        fp_iszero = fp_expf(d, x) == 0 && fp_frac(d, x) == 0;
    endfunction
    function automatic [63:0] fp_pack(input d, input s, input [10:0] e, input [51:0] f);
        fp_pack = d ? {s, e, f} : {32'hffffffff, s, e[7:0], f[22:0]};
    endfunction
    function automatic [63:0] fp_inf(input d, input s); fp_inf = fp_pack(d, s, d ? 11'h7ff : 11'hff, 52'b0); endfunction
    function automatic [63:0] fp_zero(input d, input s); fp_zero = fp_pack(d, s, 11'b0, 52'b0); endfunction
    // Finite nonzero value as an integer significand and exponent: x = sig * 2^e.
    function automatic [52:0] fp_sig(input d, input [63:0] x);
        fp_sig = fp_expf(d, x) == 0 ? {1'b0, fp_frac(d, x)} : (d ? {1'b1, x[51:0]} : {30'b1, x[22:0]});
    endfunction
    function automatic integer fp_exp(input d, input [63:0] x);
        fp_exp = (fp_expf(d, x) == 0 ? 1 : fp_expf(d, x)) - fp_bias(d) - (fp_p(d) - 1);
    endfunction
    function automatic integer fp_msb(input [FPW-1:0] v);   // index of the highest set bit, -1 if zero
        integer i; begin fp_msb = -1; for (i = 0; i < FPW; i = i + 1) if (v[i]) fp_msb = i; end
    endfunction

    // ---- rounding: value = (-1)^s * sig * 2^e, sig != 0 -> {flags, result}
    function automatic [68:0] fp_round(input d, input s, input integer e, input [FPW-1:0] sig, input [2:0] rm);
        integer p, msb, E, emin, lsbexp, sh, bexp;
        reg [FPW-1:0] m, mu;
        reg g, st, inc, incu, tiny, nx, of;
        reg [63:0] r;
        begin
            p = fp_p(d); emin = 1 - fp_bias(d);
            msb = fp_msb(sig); E = msb + e;
            lsbexp = (E > emin ? E : emin) - (p - 1);
            sh = lsbexp - e;
            if (sh > 0) begin
                m = sig >> sh; g = sh <= FPW ? sig[sh - 1] : 1'b0;
                st = (sig & ((({{(FPW-1){1'b0}}, 1'b1}) << (sh - 1)) - 1)) != 0;
            end else begin m = sig << (-sh); g = 0; st = 0; end
            nx = g | st;
            case (rm)
                3'd0: inc = g && (st || m[0]);
                3'd1: inc = 0;
                3'd2: inc = s && nx;
                3'd3: inc = !s && nx;
                default: inc = g;
            endcase
            // Tininess after rounding: round with the exponent unbounded and see whether 2^emin is reached.
            tiny = 0;
            if (E < emin) begin
                sh = (E - (p - 1)) - e;
                if (sh > 0) begin
                    mu = sig >> sh; g = sig[sh - 1]; st = (sig & ((({{(FPW-1){1'b0}}, 1'b1}) << (sh - 1)) - 1)) != 0;
                end else begin mu = sig << (-sh); g = 0; st = 0; end
                case (rm)
                    3'd0: incu = g && (st || mu[0]);
                    3'd1: incu = 0;
                    3'd2: incu = s && (g | st);
                    3'd3: incu = !s && (g | st);
                    default: incu = g;
                endcase
                mu = mu + incu;
                tiny = !(E == emin - 1 && mu[p]);
            end
            m = m + inc;
            if (m[p]) begin m = m >> 1; lsbexp = lsbexp + 1; end
            of = 0;
            if (m[p - 1]) begin
                bexp = lsbexp + (p - 1) + fp_bias(d);
                if (bexp >= fp_emax_field(d)) begin
                    of = 1; nx = 1;
                    if (rm == 3'd1 || (rm == 3'd2 && !s) || (rm == 3'd3 && s))
                        r = fp_pack(d, s, fp_emax_field(d) - 1, d ? 52'hfffffffffffff : 52'h7fffff);
                    else r = fp_inf(d, s);
                end else r = fp_pack(d, s, bexp[10:0], m[51:0]);
            end else r = fp_pack(d, s, 11'b0, m[51:0]);
            fp_round = {1'b0, 1'b0, of, tiny && nx, nx, r};
        end
    endfunction

    // Exact sum of two signed values sig * 2^e (sig < 2^128), rounded.
    function automatic [68:0] fp_addx(input d, input s1, input [127:0] m1, input integer e1,
                                      input s2, input [127:0] m2, input integer e2, input [2:0] rm);
        reg [FPW-1:0] a, b, r;
        integer ea, eb, n1, n2, gap, ee;
        reg sr, sa, sb;
        begin
            // normalize both to the msb at bit 127
            n1 = fp_msb({192'b0, m1}); n2 = fp_msb({192'b0, m2});
            a = {192'b0, m1} << (127 - n1); ea = e1 - (127 - n1); sa = s1;
            b = {192'b0, m2} << (127 - n2); eb = e2 - (127 - n2); sb = s2;
            if (eb > ea) begin r = a; a = b; b = r; ee = ea; ea = eb; eb = ee; sr = sa; sa = sb; sb = sr; end
            gap = ea - eb;
            if (gap > 130) begin a = a << 131; ea = ea - 131; b = 1; eb = ea; end
            else begin a = a << gap; ea = eb; end
            if (sa == sb) begin r = a + b; sr = sa; end
            else if (a >= b) begin r = a - b; sr = sa; end
            else begin r = b - a; sr = sb; end
            if (r == 0) fp_addx = {5'b0, fp_zero(d, rm == 3'd2)};   // exact cancellation
            else fp_addx = fp_round(d, sr, ea, r, rm);
        end
    endfunction

    // ---- the operations
    function automatic [68:0] fp_exec(input [4:0] op, input d, input [2:0] rm, input [63:0] ai, input [63:0] bi, input [63:0] ci);
        reg [63:0] a, b, c, r;
        reg [4:0] fl;
        reg sa, sb, sc, sp, nv, sx;
        reg [127:0] pm, q, rem, x, root, tmp;
        reg [FPW-1:0] wide;
        integer ea, eb, ec, ep, k, i, p, n;
        reg [68:0] t;
        reg [63:0] iv, lim;
        reg [63:0] bits_;
        begin
            fl = 0; r = 0;
            // NaN-boxing applies to FP32 sources (not to integer sources of int->fp, nor FMV.W.X)
            a = fp_in(op == FOP_CVT_DS ? 1'b0 : (op == FOP_CVT_SD ? 1'b1 : d), ai);
            b = fp_in(d, bi); c = fp_in(d, ci);
            sa = fp_sign(d, a); sb = fp_sign(d, b); sc = fp_sign(d, c);
            p = fp_p(d);
            case (op)
            FOP_ADD, FOP_SUB: begin
                if (op == FOP_SUB) sb = !sb;
                if (fp_isnan(d, a) || fp_isnan(d, b)) begin r = fp_qnan(d); fl[4] = fp_issnan(d, a) || fp_issnan(d, b); end
                else if (fp_isinf(d, a) && fp_isinf(d, b) && sa != sb) begin r = fp_qnan(d); fl[4] = 1; end
                else if (fp_isinf(d, a)) r = fp_inf(d, sa);
                else if (fp_isinf(d, b)) r = fp_inf(d, sb);
                else if (fp_iszero(d, a) && fp_iszero(d, b)) r = fp_zero(d, sa == sb ? sa : rm == 3'd2);
                else if (fp_iszero(d, a)) begin t = fp_round(d, sb, fp_exp(d, b), {267'b0, fp_sig(d, b)}, rm); fl = t[68:64]; r = t[63:0]; end
                else if (fp_iszero(d, b)) begin t = fp_round(d, sa, fp_exp(d, a), {267'b0, fp_sig(d, a)}, rm); fl = t[68:64]; r = t[63:0]; end
                else begin
                    t = fp_addx(d, sa, {75'b0, fp_sig(d, a)}, fp_exp(d, a), sb, {75'b0, fp_sig(d, b)}, fp_exp(d, b), rm);
                    fl = t[68:64]; r = t[63:0];
                end
            end
            FOP_MUL: begin
                sp = sa ^ sb;
                if (fp_isnan(d, a) || fp_isnan(d, b)) begin r = fp_qnan(d); fl[4] = fp_issnan(d, a) || fp_issnan(d, b); end
                else if ((fp_isinf(d, a) && fp_iszero(d, b)) || (fp_iszero(d, a) && fp_isinf(d, b))) begin r = fp_qnan(d); fl[4] = 1; end
                else if (fp_isinf(d, a) || fp_isinf(d, b)) r = fp_inf(d, sp);
                else if (fp_iszero(d, a) || fp_iszero(d, b)) r = fp_zero(d, sp);
                else begin
                    pm = fp_sig(d, a) * fp_sig(d, b);
                    t = fp_round(d, sp, fp_exp(d, a) + fp_exp(d, b), {192'b0, pm}, rm); fl = t[68:64]; r = t[63:0];
                end
            end
            FOP_MADD, FOP_MSUB, FOP_NMSUB, FOP_NMADD: begin
                sp = sa ^ sb ^ (op == FOP_NMSUB || op == FOP_NMADD);
                sc = sc ^ (op == FOP_MSUB || op == FOP_NMADD);
                nv = fp_issnan(d, a) || fp_issnan(d, b) || fp_issnan(d, c) ||
                     (fp_isinf(d, a) && fp_iszero(d, b)) || (fp_iszero(d, a) && fp_isinf(d, b));
                if (fp_isnan(d, a) || fp_isnan(d, b) || fp_isnan(d, c) || nv) begin r = fp_qnan(d); fl[4] = nv; end
                else if (fp_isinf(d, a) || fp_isinf(d, b)) begin
                    if (fp_isinf(d, c) && sc != sp) begin r = fp_qnan(d); fl[4] = 1; end
                    else r = fp_inf(d, sp);
                end
                else if (fp_isinf(d, c)) r = fp_inf(d, sc);
                else if (fp_iszero(d, a) || fp_iszero(d, b)) begin
                    if (fp_iszero(d, c)) r = fp_zero(d, sp == sc ? sp : rm == 3'd2);
                    else begin t = fp_round(d, sc, fp_exp(d, c), {267'b0, fp_sig(d, c)}, rm); fl = t[68:64]; r = t[63:0]; end
                end else begin
                    pm = fp_sig(d, a) * fp_sig(d, b); ep = fp_exp(d, a) + fp_exp(d, b);
                    if (fp_iszero(d, c)) begin t = fp_round(d, sp, ep, {192'b0, pm}, rm); end
                    else t = fp_addx(d, sp, pm, ep, sc, {75'b0, fp_sig(d, c)}, fp_exp(d, c), rm);
                    fl = t[68:64]; r = t[63:0];
                end
            end
            FOP_DIV: begin
                sp = sa ^ sb;
                if (fp_isnan(d, a) || fp_isnan(d, b)) begin r = fp_qnan(d); fl[4] = fp_issnan(d, a) || fp_issnan(d, b); end
                else if ((fp_isinf(d, a) && fp_isinf(d, b)) || (fp_iszero(d, a) && fp_iszero(d, b))) begin r = fp_qnan(d); fl[4] = 1; end
                else if (fp_isinf(d, a)) r = fp_inf(d, sp);
                else if (fp_isinf(d, b)) r = fp_zero(d, sp);
                else if (fp_iszero(d, b)) begin r = fp_inf(d, sp); fl[3] = 1; end
                else if (fp_iszero(d, a)) r = fp_zero(d, sp);
                else begin
                    // q = (sig_a << k) / sig_b with k so the quotient keeps at least p + 2 bits; remainder -> sticky
                    // both significands normalized to the msb at bit 52 (subnormals shifted up)
                    x = fp_sig(d, a); ea = fp_exp(d, a); n = fp_msb({192'b0, x}); x = x << (52 - n); ea = ea - (52 - n);
                    tmp = fp_sig(d, b); eb = fp_exp(d, b); n = fp_msb({192'b0, tmp}); tmp = tmp << (52 - n); eb = eb - (52 - n);
                    k = p + 3;
                    x = x << k;
                    q = x / tmp; rem = x % tmp;
                    wide = {192'b0, q} << 1 | (rem != 0);
                    t = fp_round(d, sp, ea - eb - k - 1, wide, rm); fl = t[68:64]; r = t[63:0];
                end
            end
            FOP_SQRT: begin
                if (fp_isnan(d, a)) begin r = fp_qnan(d); fl[4] = fp_issnan(d, a); end
                else if (fp_iszero(d, a)) r = a;
                else if (sa) begin r = fp_qnan(d); fl[4] = 1; end
                else if (fp_isinf(d, a)) r = a;
                else begin
                    ea = fp_exp(d, a); x = fp_sig(d, a);
                    n = fp_msb({192'b0, x}); x = x << (52 - n); ea = ea - (52 - n);
                    if (ea % 2 != 0) begin x = x << 1; ea = ea - 1; end
                    x = x << 72; ea = ea - 72;                   // even shift: the root keeps at least 63 bits
                    root = 0; rem = 0;
                    for (i = 127; i >= 0; i = i - 2) begin
                        rem = (rem << 2) | ((x >> i - 1) & 3);
                        tmp = (root << 2) | 1;
                        root = root << 1;
                        if (rem >= tmp) begin rem = rem - tmp; root = root | 1; end
                    end
                    wide = {192'b0, root} << 1 | (rem != 0);
                    t = fp_round(d, 1'b0, ea / 2 - 1, wide, rm); fl = t[68:64]; r = t[63:0];
                end
            end
            FOP_MIN, FOP_MAX: begin
                fl[4] = fp_issnan(d, a) || fp_issnan(d, b);
                if (fp_isnan(d, a) && fp_isnan(d, b)) r = fp_qnan(d);
                else if (fp_isnan(d, a)) r = b;
                else if (fp_isnan(d, b)) r = a;
                else begin
                    // a < b ?  (-0 < +0)
                    if (sa != sb) sx = sa;
                    else sx = sa ? (d ? a[62:0] > b[62:0] : a[30:0] > b[30:0]) : (d ? a[62:0] < b[62:0] : a[30:0] < b[30:0]);
                    r = (op == FOP_MIN) == sx ? a : b;
                end
            end
            FOP_EQ, FOP_LT, FOP_LE: begin
                if (fp_isnan(d, a) || fp_isnan(d, b)) begin
                    r = 0; fl[4] = op == FOP_EQ ? (fp_issnan(d, a) || fp_issnan(d, b)) : 1'b1;
                end else begin
                    if (fp_iszero(d, a) && fp_iszero(d, b)) sx = 0;   // a < b?
                    else if (sa != sb) sx = sa;
                    else sx = sa ? (d ? a[62:0] > b[62:0] : a[30:0] > b[30:0]) : (d ? a[62:0] < b[62:0] : a[30:0] < b[30:0]);
                    nv = (fp_iszero(d, a) && fp_iszero(d, b)) || (d ? a == b : a[31:0] == b[31:0]);   // equal
                    r = op == FOP_EQ ? nv : op == FOP_LT ? sx : (sx || nv);
                end
            end
            FOP_CLASS: begin
                r = 0;
                if (fp_isinf(d, a)) r[sa ? 0 : 7] = 1;
                else if (fp_isnan(d, a)) r[fp_issnan(d, a) ? 8 : 9] = 1;
                else if (fp_iszero(d, a)) r[sa ? 3 : 4] = 1;
                else if (fp_expf(d, a) == 0) r[sa ? 2 : 5] = 1;
                else r[sa ? 1 : 6] = 1;
            end
            FOP_SGNJ, FOP_SGNJN, FOP_SGNJX: begin
                sx = op == FOP_SGNJ ? sb : op == FOP_SGNJN ? !sb : sa ^ sb;
                r = d ? {sx, a[62:0]} : {32'hffffffff, sx, a[30:0]};
            end
            FOP_CVT_W, FOP_CVT_WU, FOP_CVT_L, FOP_CVT_LU: begin
                // limits: W [-2^31, 2^31-1], WU [0, 2^32-1], L [-2^63, 2^63-1], LU [0, 2^64-1]
                if (fp_isnan(d, a) || (fp_isinf(d, a) && !sa)) begin
                    fl[4] = 1;
                    r = op == FOP_CVT_W ? 64'h7fffffff : op == FOP_CVT_WU ? 64'hffffffffffffffff :
                        op == FOP_CVT_L ? 64'h7fffffffffffffff : 64'hffffffffffffffff;
                end else if (fp_isinf(d, a)) begin
                    fl[4] = 1;
                    r = op == FOP_CVT_W ? 64'hffffffff80000000 : op == FOP_CVT_L ? 64'h8000000000000000 : 64'h0;
                end else if (fp_iszero(d, a)) r = 0;
                else begin
                    // round |a| to an integer (value = sig * 2^e)
                    ea = fp_exp(d, a); x = fp_sig(d, a);
                    if (ea >= 0) begin
                        if (ea > 70) begin iv = 64'hffffffffffffffff; nv = 1; sx = 0; end
                        else begin tmp = x << ea; iv = tmp[63:0]; nv = tmp[127:64] != 0; sx = 0; end
                    end else begin
                        k = -ea;
                        tmp = k > 120 ? 0 : x >> k;
                        sx = k > 120 ? (x != 0) : ((x & ((128'b1 << k) - 1)) != 0);    // inexact
                        // rounding increment
                        case (rm)
                            3'd0: begin
                                if (k <= 120) begin
                                    if (x[k - 1] && (((x & ((128'b1 << (k - 1)) - 1)) != 0) || tmp[0])) tmp = tmp + 1;
                                end
                            end
                            3'd1: ;
                            3'd2: if (sa && sx) tmp = tmp + 1;
                            3'd3: if (!sa && sx) tmp = tmp + 1;
                            default: if (k <= 120 && x[k - 1]) tmp = tmp + 1;
                        endcase
                        iv = tmp[63:0]; nv = tmp[127:64] != 0;
                    end
                    // range check on the signed result
                    if (op == FOP_CVT_W) begin
                        if (nv || (!sa && iv > 64'h7fffffff) || (sa && iv > 64'h80000000)) begin fl[4] = 1; r = sa ? 64'hffffffff80000000 : 64'h7fffffff; end
                        else begin r = sa ? -iv : iv; r = {{32{r[31]}}, r[31:0]}; fl[0] = sx; end
                    end else if (op == FOP_CVT_WU) begin
                        if ((sa && iv != 0) || nv || iv > 64'hffffffff) begin fl[4] = 1; r = sa ? 64'h0 : 64'hffffffffffffffff; end
                        else begin r = {{32{iv[31]}}, iv[31:0]}; fl[0] = sx; end
                    end else if (op == FOP_CVT_L) begin
                        if (nv || (!sa && iv > 64'h7fffffffffffffff) || (sa && iv > 64'h8000000000000000)) begin fl[4] = 1; r = sa ? 64'h8000000000000000 : 64'h7fffffffffffffff; end
                        else begin r = sa ? -iv : iv; fl[0] = sx; end
                    end else begin
                        if ((sa && iv != 0) || nv) begin fl[4] = 1; r = sa ? 64'h0 : 64'hffffffffffffffff; end
                        else begin r = iv; fl[0] = sx; end
                    end
                end
            end
            FOP_CVT_FW, FOP_CVT_FWU, FOP_CVT_FL, FOP_CVT_FLU: begin
                iv = op == FOP_CVT_FW ? {{32{ai[31]}}, ai[31:0]} : op == FOP_CVT_FWU ? {32'b0, ai[31:0]} : ai;
                sx = (op == FOP_CVT_FW || op == FOP_CVT_FL) && iv[63];
                if (sx) iv = -iv;
                if (iv == 0) r = fp_zero(d, 1'b0);
                else begin t = fp_round(d, sx, 0, {256'b0, iv}, rm); fl = t[68:64]; r = t[63:0]; end
            end
            FOP_CVT_SD: begin   // binary64 a -> binary32
                if (fp_isnan(1'b1, a)) begin r = fp_qnan(1'b0); fl[4] = fp_issnan(1'b1, a); end
                else if (fp_isinf(1'b1, a)) r = fp_inf(1'b0, a[63]);
                else if (fp_iszero(1'b1, a)) r = fp_zero(1'b0, a[63]);
                else begin t = fp_round(1'b0, a[63], fp_exp(1'b1, a), {267'b0, fp_sig(1'b1, a)}, rm); fl = t[68:64]; r = t[63:0]; end
            end
            FOP_CVT_DS: begin   // binary32 a -> binary64 (exact)
                if (fp_isnan(1'b0, a)) begin r = fp_qnan(1'b1); fl[4] = fp_issnan(1'b0, a); end
                else if (fp_isinf(1'b0, a)) r = fp_inf(1'b1, a[31]);
                else if (fp_iszero(1'b0, a)) r = fp_zero(1'b1, a[31]);
                else begin t = fp_round(1'b1, a[31], fp_exp(1'b0, a), {267'b0, fp_sig(1'b0, a)}, rm); fl = t[68:64]; r = t[63:0]; end
            end
            FOP_MV_XF: r = d ? ai : {{32{ai[31]}}, ai[31:0]};     // raw bits, no box check
            FOP_MV_FX: r = d ? ai : {32'hffffffff, ai[31:0]};
            default: r = 0;
            endcase
            fp_exec = {fl, r};
        end
    endfunction
    // RISC-V F/D decoder for the out-of-order core (council backend, draft; standard encodings,
    // to be checked against build/cpu/fp/FP-CONTRACT.md). Requires fpu.svh (FOP_*).
    // fp_decode(insn) -> fields below; valid = 0 for anything that is not an F/D instruction or
    // is a reserved F/D encoding (illegal: rename treats it as an illegal instruction).
    //   [0]     valid
    //   [2:1]   kind: 0 FP execute (C_FP), 1 FP load (flw/fld, C_LD), 2 FP store (fsw/fsd, C_ST)
    //   [7:3]   fop (FOP_*), for kind 0
    //   [8]     d: 1 binary64 (for loads/stores: 8-byte access)
    //   [11:9]  rm: the instruction's rm field (7 = dynamic); ops that ignore rm have 0
    //   [13:12] unit: 0 FMA pipe (FMA, FMUL), 1 add (FMA or misc port), 2 misc, 3 divide/sqrt
    //   [14]    rs1 is an FP register (else integer)
    //   [15]    rs2 used, [16] rs2 is an FP register
    //   [17]    rs3 used (FP)
    //   [18]    rd written, [19] rd is an FP register (else integer)
    //   [20]    uses rm (rounding or reserved-rm check applies)
    function automatic [20:0] fp_decode(input [31:0] insn);
        reg [6:0] opc, f7; reg [2:0] f3; reg [4:0] rs2; reg [1:0] fmt;
        reg v; reg [1:0] kind, unit; reg [4:0] fop; reg d, r1f, r2u, r2f, r3u, rdw, rdf, urm; reg [2:0] rm;
        begin
            opc = insn[6:0]; f7 = insn[31:25]; f3 = insn[14:12]; rs2 = insn[24:20]; fmt = insn[26:25];
            v = 0; kind = 0; unit = 2; fop = 0; d = 0; r1f = 1; r2u = 0; r2f = 1; r3u = 0; rdw = 1; rdf = 1; urm = 0; rm = 0;
            case (opc)
            7'h07: if (f3 == 3'd2 || f3 == 3'd3) begin v = 1; kind = 1; d = f3[0]; r1f = 0; end            // flw, fld
            7'h27: if (f3 == 3'd2 || f3 == 3'd3) begin v = 1; kind = 2; d = f3[0]; r1f = 0; r2u = 1; rdw = 0; end  // fsw, fsd
            7'h43, 7'h47, 7'h4b, 7'h4f: if (fmt <= 2'd1) begin
                v = 1; d = fmt[0]; unit = 0; r2u = 1; r3u = 1; urm = 1; rm = f3;
                fop = opc == 7'h43 ? FOP_MADD : opc == 7'h47 ? FOP_MSUB : opc == 7'h4b ? FOP_NMSUB : FOP_NMADD;
            end
            7'h53: if (f7[1] == 1'b0 || f7[6:2] == 5'b01000) begin
                d = f7[0];
                case (f7[6:2])
                5'b00000: begin v = 1; fop = FOP_ADD; unit = 1; r2u = 1; urm = 1; rm = f3; end
                5'b00001: begin v = 1; fop = FOP_SUB; unit = 1; r2u = 1; urm = 1; rm = f3; end
                5'b00010: begin v = 1; fop = FOP_MUL; unit = 0; r2u = 1; urm = 1; rm = f3; end
                5'b00011: begin v = 1; fop = FOP_DIV; unit = 3; r2u = 1; urm = 1; rm = f3; end
                5'b01011: if (rs2 == 0) begin v = 1; fop = FOP_SQRT; unit = 3; urm = 1; rm = f3; end
                5'b00100: if (f3 <= 3'd2) begin v = 1; fop = f3 == 0 ? FOP_SGNJ : f3 == 1 ? FOP_SGNJN : FOP_SGNJX; r2u = 1; end
                5'b00101: if (f3 <= 3'd1) begin v = 1; fop = f3 == 0 ? FOP_MIN : FOP_MAX; r2u = 1; end
                5'b01000: if ((f7[1:0] == 2'b00 && rs2 == 5'd1) || (f7[1:0] == 2'b01 && rs2 == 5'd0)) begin   // fcvt.s.d, fcvt.d.s
                    v = 1; d = f7[0]; fop = f7[0] ? FOP_CVT_DS : FOP_CVT_SD; urm = 1; rm = f3;
                end
                5'b11000: if (rs2 <= 5'd3) begin            // fcvt.{w,wu,l,lu}.{s,d}: integer rd
                    v = 1; fop = rs2 == 0 ? FOP_CVT_W : rs2 == 1 ? FOP_CVT_WU : rs2 == 2 ? FOP_CVT_L : FOP_CVT_LU; rdf = 0; urm = 1; rm = f3;
                end
                5'b11010: if (rs2 <= 5'd3) begin            // fcvt.{s,d}.{w,wu,l,lu}: integer rs1
                    v = 1; fop = rs2 == 0 ? FOP_CVT_FW : rs2 == 1 ? FOP_CVT_FWU : rs2 == 2 ? FOP_CVT_FL : FOP_CVT_FLU; r1f = 0; urm = 1; rm = f3;
                end
                5'b10100: if (f3 <= 3'd2) begin v = 1; fop = f3 == 2 ? FOP_EQ : f3 == 1 ? FOP_LT : FOP_LE; r2u = 1; rdf = 0; end
                5'b11100: if (rs2 == 0 && f3 <= 3'd1) begin v = 1; fop = f3 == 0 ? FOP_MV_XF : FOP_CLASS; rdf = 0; end
                5'b11110: if (rs2 == 0 && f3 == 0) begin v = 1; fop = FOP_MV_FX; r1f = 0; end
                default: ;
                endcase
                if (v && f7[1]) v = 0;                    // fmt 2/3 (H/Q) are not implemented
                if (v && urm && (rm == 3'd5 || rm == 3'd6)) v = 0;   // reserved static rm
                if (fop == FOP_SQRT || fop == FOP_CVT_SD || fop == FOP_CVT_DS || fop == FOP_CLASS || fop == FOP_MV_XF ||
                    fop == FOP_MV_FX || fop >= FOP_CVT_W) r2u = r2u;     // rs2 is an op selector there, not a source
            end
            default: ;
            endcase
            if (v && opc[6:4] == 3'b100 && (rm == 3'd5 || rm == 3'd6)) v = 0;   // FMA reserved rm
            fp_decode = {urm, rdf, rdw, r3u, r2f, r2u, r1f, unit, rm, d, fop, kind, v};
        end
    endfunction
    function rdy3(input integer kk); rdy3 = prf_ready[iq_ps3[kk]]; endfunction
`ifdef RV64_OOO_V
    function automatic integer v_ceil_beats(input integer bits);
        v_ceil_beats = bits <= 0 ? 1 : (bits + DLEN - 1) / DLEN;
    endfunction
    // Step-1 latency of a vector FP instruction: the scalar unit's latency for the operation, + beats - 1;
    // divide/sqrt at their initiation interval per beat; reductions as a chain (ordered) or tree (unordered).
    function automatic integer v_lat(input [5:0] f6, input [4:0] r1, input [63:0] n);
        integer b, lg, l;
        begin
            b = v_ceil_beats(n * 32); lg = 0; while ((1 << lg) < n) lg = lg + 1;
            case (f6)
                6'h28, 6'h29, 6'h2a, 6'h2b, 6'h2c, 6'h2d, 6'h2e, 6'h2f: l = FMA_LAT + b - 1;
                6'h24: l = FMUL_LAT + b - 1;
                6'h00, 6'h02, 6'h27: l = FADD_LAT + b - 1;
                6'h20, 6'h21: l = FDIV_S + (b - 1) * FDIV_II_S;
                6'h13: l = r1 == 0 ? FSQRT_S + (b - 1) * FSQRT_II_S : FMISC_LAT + b - 1;
                6'h12: l = FCVT_LAT + b - 1;
                6'h03: l = FADD_LAT * (n > 0 ? n : 1);              // vfredosum: one add per element, in order
                6'h01: l = FADD_LAT * (lg + 1);                       // vfredusum: the tree, then vs1[0]
                6'h05, 6'h07: l = FMISC_LAT * (n > 0 ? n : 1);        // vfredmin / vfredmax
                default: l = FMISC_LAT + b - 1;                      // compares, min/max, sign injection, moves, slides
            endcase
            v_lat = l < 1 ? 1 : l;
        end
    endfunction
    // vtype: ok, SEW, LMUL = num/den, VLMAX (contract section 3; ELEN 64)
    task automatic vconf(input [63:0] vt, output ok, output integer sew, output integer num, output integer den, output integer vmax);
        integer vs, vlmul;
        begin
            ok = 1; vs = vt[5:3]; vlmul = vt[2:0];
            if (vt[63] || vt[62:8] != 0 || vs > 3 || vlmul == 4) ok = 0;
            sew = 8 << vs;
            if (vlmul < 4) begin num = 1 << vlmul; den = 1; end else begin num = 1; den = 1 << (8 - vlmul); end
            if (den > 1 && sew > 64 / den) ok = 0;
            vmax = num * VLEN / (den * sew);
            if (!ok) begin sew = 0; num = 1; den = 1; vmax = 0; end
        end
    endtask
    // Element i (EEW eew bits) of the group starting at register r.
    function automatic [63:0] vget(input integer r, input integer i, input integer eew);
        integer b;
        reg [VLEN-1:0] w;
        begin
            b = i * eew; w = vreg[(r + b / VLEN) % 32] >> (b % VLEN);
            vget = eew == 64 ? w[63:0] : w[63:0] & ((64'd1 << eew) - 1);
        end
    endfunction
    task automatic vput(input integer r, input integer i, input integer eew, input [63:0] val);
        integer b, rr, o;
        reg [VLEN-1:0] m, dv;
        begin
            b = i * eew; rr = (r + b / VLEN) % 32; o = b % VLEN;
            m = 0; m[63:0] = eew == 64 ? ~64'd0 : (64'd1 << eew) - 1;
            dv = 0; dv[63:0] = val & m[63:0];
            vreg[rr] = (vreg[rr] & ~(m << o)) | (dv << o);
        end
    endtask
    function automatic vbit(input integer r, input integer i);
        vbit = vreg[r][i];
    endfunction
    function automatic [63:0] vbox(input [31:0] x); vbox = {32'hffffffff, x}; endfunction
    // One FP32 vector element: {fflags, result}. f6 = funct6, r1 = the vs1 field (unary forms),
    // a = vs2[i], b = vs1[i] or f[rs1], d = vd[i]; rm resolved. Compares return the bit in result[0].
    function automatic [36:0] v_fe(input [5:0] f6, input [4:0] r1, input [31:0] a, input [31:0] b, input [31:0] d, input [2:0] rm);
        /* verilator no_inline_task */
        reg [68:0] t;
        reg [63:0] x, y, z;
        reg [4:0] fop;
        reg [2:0] r;
        reg raw, inv;
        begin
            // One fp_exec call site (Verilator build time): choose the operation and operands first.
            raw = 0; inv = 0; r = rm; x = vbox(a); y = vbox(b); z = 64'b0; fop = FOP_ADD;
            case (f6)
                6'h00: fop = FOP_ADD;
                6'h02: fop = FOP_SUB;
                6'h27: begin fop = FOP_SUB; x = vbox(b); y = vbox(a); end
                6'h24: fop = FOP_MUL;
                6'h20: fop = FOP_DIV;
                6'h21: begin fop = FOP_DIV; x = vbox(b); y = vbox(a); end
                6'h04: fop = FOP_MIN;
                6'h06: fop = FOP_MAX;
                6'h08, 6'h09, 6'h0a: raw = 1;
                6'h28, 6'h29, 6'h2a, 6'h2b, 6'h2c, 6'h2d, 6'h2e, 6'h2f: begin
                    // vfmadd family: vs1 * vd + vs2; vfmacc family: vs1 * vs2 + vd. Negations (np, nc):
                    // madd/macc (0,0), nmadd/nmacc (1,1), msub/msac (0,1), nmsub/nmsac (1,0).
                    x = vbox(b); y = vbox(f6 < 6'h2c ? d : a); z = vbox(f6 < 6'h2c ? a : d);
                    fop = f6[1:0] == 2'd0 ? FOP_MADD : f6[1:0] == 2'd1 ? FOP_NMADD : f6[1:0] == 2'd2 ? FOP_MSUB : FOP_NMSUB;
                end
                6'h18: fop = FOP_EQ;
                6'h19: fop = FOP_LE;
                6'h1b: fop = FOP_LT;
                6'h1c: begin fop = FOP_EQ; inv = 1; end
                6'h1d: begin fop = FOP_LT; x = vbox(b); y = vbox(a); end
                6'h1f: begin fop = FOP_LE; x = vbox(b); y = vbox(a); end
                6'h12: begin
                    y = 64'b0;
                    case (r1)
                        5'd0: fop = FOP_CVT_WU;
                        5'd1: fop = FOP_CVT_W;
                        5'd2: begin fop = FOP_CVT_FWU; x = {32'b0, a}; end
                        5'd3: begin fop = FOP_CVT_FW; x = {32'b0, a}; end
                        5'd6: begin fop = FOP_CVT_WU; r = 3'd1; end
                        default: begin fop = FOP_CVT_W; r = 3'd1; end
                    endcase
                end
                6'h13: begin y = 64'b0; fop = r1 == 0 ? FOP_SQRT : FOP_CLASS; end
                default: raw = 1;
            endcase
            t = raw ? 69'b0 : fp_exec(fop, 1'b0, r, x, y, z);
            if (raw) t[31:0] = f6 == 6'h08 ? ((a & 32'h7fffffff) | (b & 32'h80000000)) :
                               f6 == 6'h09 ? ((a & 32'h7fffffff) | (~b & 32'h80000000)) : (a ^ (b & 32'h80000000));
            if (inv) t[63:0] = {63'b0, !t[0]};
            v_fe = {t[68:64], t[31:0]};
        end
    endfunction
    // RVV-CONTRACT.md section 7 record helpers
    task automatic vrec_c(input [11:0] csr, input [63:0] val);
        begin if (vr_cn < 3) begin vr_csr[vr_cn] = csr; vr_cval[vr_cn] = val; vr_cn = vr_cn + 2'd1; end end
    endtask
`endif
    // Source readiness in the issue queue.
    function rdy1(input integer kk);
        rdy1 = (prf_ready[iq_ps1[kk]] && (OFF_LAT == 0 || iq_off1[kk] == 0 || iq_cls[kk] == C_LD ||
                iq_cls[kk] == C_ST || (prf_written[iq_ps1[kk]] && !prf_late[iq_ps1[kk]]))) || (iq_fz1[kk] && prf_ready[iq_fza[kk]] && prf_ready[iq_fzb[kk]]);
    endfunction
    function rdy2(input integer kk);
        rdy2 = (prf_ready[iq_ps2[kk]] && (OFF_LAT == 0 || iq_off2[kk] == 0 || (prf_written[iq_ps2[kk]] && !prf_late[iq_ps2[kk]]))) || (iq_fz2[kk] && prf_ready[iq_fza[kk]] && prf_ready[iq_fzb[kk]]);
    endfunction

    task automatic squash_after(input [ROB_B-1:0] keep_age);  // keep entries with age <= keep_age
        reg [ROB_B-1:0] en;
        begin
            for (k = 0; k < ROB_N; k = k + 1) begin
                en = k[ROB_B-1:0];
                if (rb_live[en] && (en - rb_head) > keep_age) begin
                    rb_live[en] = 0; rb_done[en] = 0;
                    if (rb_writes[en] && rb_pdst[en] != 0) begin
                        refcnt[rb_pdst[en]] = refcnt[rb_pdst[en]] - 1;
                        if (refcnt[rb_pdst[en]] == 0) free_mask[rb_pdst[en]] = 1;
                    end
                end
            end
            for (k = 0; k < IQ_N; k = k + 1)
                if (iq_valid[k] && (iq_rob[k] - rb_head) > keep_age) iq_valid[k] = 0;
            for (k = 0; k < MQ_N; k = k + 1)
                if (mq_valid[k] && (mq_rob[k] - rb_head) > keep_age) mq_valid[k] = 0;
            for (k = 0; k < LW_N; k = k + 1)
                if (lw_valid[k] && (lw_rob[k] - rb_head) > keep_age) lw_valid[k] = 0;
            if (dv_busy && (dv_rob - rb_head) > keep_age) dv_busy = 0;
            for (k = 0; k < FQ_N; k = k + 1)
                if (fq_valid[k] && (fq_rob[k] - rb_head) > keep_age) fq_valid[k] = 0;
            if (fd_gap != 0 && (fd_grob - rb_head) > keep_age) fd_gap = 0;
            if (fb_lock && (fb_owner - rb_head) > keep_age) fb_lock = 0;
            if (mu_owner_v && (mu_owner - rb_head) > keep_age) mu_owner_v = 0;
            if (mu_errv && (mu_err_owner - rb_head) > keep_age) mu_errv = 0;
        end
    endtask

    always @(posedge clk) begin
        if (reset) begin
            halted = 0; started = 0; f_pc = RESET_PC; fe_clk = 0; f_err = 0; f_hold = 0; f_stale = 0;
            bus_hold = 0; hold_addr = 0; hold_pair = 0; hold_nx = 0; mu_valid = 0; mu_beat = 0; mu_errv = 0; mu_err_beat = 0;
            fb_valid = 0; fb_beat = 0; fb_data = 0; mu_owner = 0; fb_owner = 0; fb_lock = 0; mu_owner_v = 0;
            mu_sent = 0; mu_stale = 0; pm_valid = 0; pm_sent = 0; pm_stale = 0; hold_tag = 0; sf_wait = 0; iq_slp = 0; iq_wany = 0;
            for (i = 0; i < PRF_N; i = i + 1) prf[i] = 0;
            prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}}; prf_late = 0;
            free_mask = {PRF_N{1'b1}}; for (i = 0; i < NAR; i = i + 1) free_mask[i] = 0;
            for (i = 0; i < NAR; i = i + 1) begin rat[i] = i; rrat[i] = i; rat_off[i] = 0; rrat_off[i] = 0; end
            for (i = 0; i < PRF_N; i = i + 1) refcnt[i] = i < NAR ? 1 : 0;
            rt_rdfp <= 0; rt_ff <= 0; rt_csrw <= 0; csr_busy = 0;
`ifdef RV64_OOO_V
            for (i = 0; i < 32; i = i + 1) vreg[i] = 0;
            vtype = 64'h8000000000000000; vl = 0; vstart = 0; vxsat = 0; vxrm = 0; v_busy = 0; rb_vec = 0; rb_vref = 0;
            vx_st = 0; vx_wv = 0; vr_vn = 0; vr_cn = 0; rt_vec <= 0; rt_vtrap <= 0; vemax_r = VE_MAX; vlen_r = VLEN;
`endif
            pv_ok = 0; rb_viol = 0; mdp_wait = 0; rb_live = 0; rb_done = 0; rb_head = 0; rb_tail = 0; rb_count = 0;
            iq_valid = 0; iq_issued = 0; ex_valid = 0; mq_valid = 0; dv_busy = 0; fq_valid = 0; fd_gap = 0; fcsr = 0; lw_valid = 0; rb_ans = 0; l0_v = 0; l0_p = 0; ld_lat_now = LD_LAT;
            ic_valid = 0; dc_valid = 0; btb_valid = 0; btb_ret = 0; ras_sp = 0; vp_valid = 0; lp_valid = 0; lp_dir = 0; tg_v = 0; tg_alt = 8; tg_age = 0; tg_ap = 0; f_gh = 0; r_gh = 0; tq_cnt = 0; tq_h = 0;
            it_v = 0; it_age = 0; it_ap = 0; f_ph = 0; r_ph = 0;
            for (i = 0; i < RAS_N; i = i + 1) ras[i] = 0;
            q_head = 0; q_tail = 0; q_count = 0;
            trap_valid <= 0; trap_pc <= 0; trap_cause <= 0; trap_tval <= 0;
            retire_valid <= 0; retire_pc <= 0; retire_insn <= 0; retire_rd <= 0; retire_data <= 0; retire_next_pc <= 0;
            retire2_valid <= 0; retire2_pc <= 0; retire2_insn <= 0; retire2_rd <= 0; retire2_data <= 0; retire2_next_pc <= 0;
            retire3_valid <= 0; retire3_pc <= 0; retire3_insn <= 0; retire3_rd <= 0; retire3_data <= 0; retire3_next_pc <= 0;
            rt_valid <= 0; rt_pc <= 0; rt_insn <= 0; rt_rd <= 0; rt_data <= 0; rt_next <= 0;
        end else if (!halted) begin
            retire_valid <= 0; retire2_valid <= 0; retire3_valid <= 0; rt_valid <= 0; rt_rdfp <= 0; rt_csrw <= 0;
`ifdef RV64_OOO_V
            rt_vec <= 0;
`endif
            if (!started) started = 1;
            fe_clk = fe_clk + 1;
            // ================= bus completion =================
            bk_tag = mem_tag;
            if (bus_kind != 0) begin
                if (mem_ready) begin
                    bus_hold = 0;
                    if (bus_kind == 1) begin
                        // A fetch held across a redirect belongs to the discarded path: its
                        // error is not the redirected fetch's (0.11.1).
                        if (mem_error) begin if (!f_stale && mem_addr[63:3] == f_pc[63:3]) f_err = 1; end
                        else begin
                            fi = mem_addr[3 +: IC_INDEX];
                            ic_valid[fi] = 1; ic_tag[fi] = mem_addr[63 -: IC_TAG]; ic_data[fi] = mem_rdata;
                        end
                        f_stale = 0;
                    end else if (bus_kind == 2 && SPLIT) begin
                        if (bk_tag == 0) mu_sent = 1; else pm_sent[bk_tag] = 1;
                        if (LB > 1) begin lb_cnt[bk_tag] = 0; lb_bad[bk_tag] = 0; for (k = 0; k < LB; k = k + 1) lb_wm[bk_tag][k] = 0; end
                    end else if (bus_kind == 2) begin
                        mu_valid = 0; wake_beat(mu_beat[63:3]);
                        if (mem_error) begin mu_errv = mu_owner_v; mu_err_beat = mu_beat; mu_err_owner = mu_owner; end
                        else begin
                            dc_l = dc_line(mu_beat);
                            if (dc_l < 0) begin
                                dc_l = dc_set(mu_beat);
                                if (dc_valid[dc_l] && (!dc_valid[DC_SETS + dc_l] || !dc_last[dc_l])) dc_l = DC_SETS + dc_l;
                            end
                            dc_valid[dc_l] = 1; dc_tag[dc_l] = mu_beat[63 -: DC_TAG]; dc_data[dc_l] = mem_rdata;
                            dc_last[dc_set(mu_beat)] = dc_l >= DC_SETS;
                            fb_valid = 1; fb_beat = mu_beat; fb_data = mem_rdata; fb_owner = mu_owner; fb_lock = mu_owner_v;
                        end
                    end
                end else begin
                    bus_hold = bus_kind; hold_addr = mem_addr; hold_pair = bus_kind == 3 && pair_now; hold_nx = bus_kind == 3 ? nx_now : 2'd0;
                    hold_tag = bk_tag;
                end
            end
            // Split read responses (N_MISS > 1), at most one per clock.
            if (SPLIT && rsp_valid && LB == 1) begin
                if (rsp_tag == 0) begin
                    if (mu_valid && mu_sent) begin
                        wake_beat(mu_beat[63:3]);
                        mu_valid = 0; mu_sent = 0;
                        if (mu_stale) mu_stale = 0;   // dropped: the owner misses again
                        else if (rsp_error) begin mu_errv = mu_owner_v; mu_err_beat = mu_beat; mu_err_owner = mu_owner; end
                        else begin
                            dc_l = dc_line(mu_beat);
                            if (dc_l < 0) begin
                                dc_l = dc_set(mu_beat);
                                if (dc_valid[dc_l] && (!dc_valid[DC_SETS + dc_l] || !dc_last[dc_l])) dc_l = DC_SETS + dc_l;
                            end
                            dc_valid[dc_l] = 1; dc_tag[dc_l] = mu_beat[63 -: DC_TAG]; dc_data[dc_l] = rsp_data;
                            dc_last[dc_set(mu_beat)] = dc_l >= DC_SETS;
                            fb_valid = 1; fb_beat = mu_beat; fb_data = rsp_data; fb_owner = mu_owner; fb_lock = mu_owner_v;
                        end
                    end
                end else if (rsp_tag < PM_N && pm_valid[rsp_tag] && pm_sent[rsp_tag]) begin
                    wake_beat(pm_beat[rsp_tag][63:3]);
                    // A younger miss fills only the cache, and only a line not already there
                    // (a cached line is kept current by every retiring store).
                    if (!pm_stale[rsp_tag] && !rsp_error && dc_line(pm_beat[rsp_tag]) < 0) begin
                        dc_l = dc_set(pm_beat[rsp_tag]);
                        if (dc_valid[dc_l] && (!dc_valid[DC_SETS + dc_l] || !dc_last[dc_l])) dc_l = DC_SETS + dc_l;
                        dc_valid[dc_l] = 1; dc_tag[dc_l] = pm_beat[rsp_tag][63 -: DC_TAG]; dc_data[dc_l] = rsp_data;
                        dc_last[dc_set(pm_beat[rsp_tag])] = dc_l >= DC_SETS;
                    end
                    pm_valid[rsp_tag] = 0; pm_sent[rsp_tag] = 0; pm_stale[rsp_tag] = 0;
                end
            end else if (SPLIT && rsp_valid && rsp_tag < PM_N &&
                         (rsp_tag == 0 ? mu_valid && mu_sent : pm_valid[rsp_tag] && pm_sent[rsp_tag])) begin
                // Line fill: beat lb_cnt after the critical beat, wrapping inside the line.
                lt = rsp_tag; la = lt == 0 ? mu_beat : pm_beat[lt];
                lk = ((la >> 3) + lb_cnt[lt]) % LB;
                if (rsp_error) lb_bad[lt] = 1;
                else for (k = 0; k < 8; k = k + 1) if (!lb_wm[lt][lk][k]) lb_data[lt][lk][8*k +: 8] = rsp_data[8*k +: 8];
                if (lt == 0 && lb_cnt[0] == 0) begin
                    // Entry 0's critical beat: for its owner, as a one-beat answer. A store wrote the beat
                    // after the read was accepted (lb_wm): as for a stale one-beat answer, the error is not
                    // the owner's (it reads the beat again once the line read ends; Codex review, item 1).
                    wake_exact(mu_beat[63:3]);
                    if (rsp_error) begin if (lb_wm[0][lk] == 0) begin mu_errv = mu_owner_v; mu_err_beat = mu_beat; mu_err_owner = mu_owner; end end
                    else begin fb_valid = 1; fb_beat = mu_beat; fb_data = lb_data[0][lk]; fb_owner = mu_owner; fb_lock = mu_owner_v; end
                end
                lb_cnt[lt] = lb_cnt[lt] + 4'd1;
                if (lb_cnt[lt] == LB) begin
                    // Complete: install unless a beat failed (entry 0 rewrites a present line, a younger
                    // entry fills only an absent one); wake the loads of the line; free the entry.
                    if (!lb_bad[lt] && (lt == 0 || dc_line(la) < 0)) begin
                        dc_l = dc_line(la);
                        if (dc_l < 0) begin
                            dc_l = dc_set(la);
                            if (dc_valid[dc_l] && (!dc_valid[DC_SETS + dc_l] || !dc_last[dc_l])) dc_l = DC_SETS + dc_l;
                        end
                        dc_valid[dc_l] = 1; dc_tag[dc_l] = la[63 -: DC_TAG];
                        for (k = 0; k < LB; k = k + 1) dc_data[dc_l * LB + k] = lb_data[lt][k];
                        dc_last[dc_set(la)] = dc_l >= DC_SETS;
                    end
                    wake_beat(la[63:3]);
                    if (lt == 0) begin mu_valid = 0; mu_sent = 0; end else begin pm_valid[lt] = 0; pm_sent[lt] = 0; end
                end
            end
            // ================= phase 1: decisions from the state at the clock start =====
            if (MDP_CLR != 0 && fe_clk % MDP_CLR == 0) mdp_wait = 0;
            // ---- issue selection: oldest first per port class
            ou_valid = 0; ou_age = 0;
            for (k = ROB_N-1; k >= 0; k = k - 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (k < rb_count && rb_store[e] && !rb_sta[e]) begin ou_valid = 1; ou_age = k[ROB_B-1:0]; end
            end
            fo_valid = 0; fo_age = 0;
            for (k = ROB_N-1; k >= 0; k = k - 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (k < rb_count && rb_fence[e]) begin fo_valid = 1; fo_age = k[ROB_B-1:0]; end
            end
            fd_pend = 0;
            for (p = P_FP; p < NP; p = p + 1) if (ex_valid[p] && ex_cls[p] == C_FP && ex_funit[p] == 2'd3) fd_pend = 1;
            dv_pend = 0;
            for (p = 0; p < N_BR; p = p + 1)
                if (ex_valid[p] && ex_cls[p] == C_FULL && (ex_insn[p][6:0] == 7'h33 || ex_insn[p][6:0] == 7'h3b) &&
                    ex_insn[p][31:25] == 7'h01 && ex_insn[p][14]) dv_pend = 1;
            // The oldest unfinished load: only it may start a cache miss, so younger loads
            // cannot keep taking the single miss unit while it replays (0.10.0 fix).
            ol_valid = 0; ol_age = 0;
            for (k = ROB_N-1; k >= 0; k = k - 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (k < rb_count && rb_load[e] && !rb_done[e] && !rb_ans[e]) begin ol_valid = 1; ol_age = k[ROB_B-1:0]; end
            end
            chosen = 0; pick_v = 0; divtaken = 0; fdtaken = 0;
            for (p = 0; p < NP; p = p + 1) begin
                bestv = 0; best = 0; best_age = 0;
                for (k = 0; k < IQ_N; k = k + 1) begin
                    a_age = iq_rob[k] - rb_head;
                    ok = iq_valid[k] && !iq_issued[k] && !chosen[k] && rdy1(k);
                    if (p < N_ALU) begin
                        ok = ok && rdy2(k) &&
                             (iq_cls[k] == C_ALU || (p < N_BR && iq_cls[k] == C_FULL &&
                              !(iq_mdu[k] && iq_insn[k][14] && (dv_busy || dv_pend || divtaken))));
                    end else if (p < N_ALU + N_LD) ok = ok && iq_cls[k] == C_LD && (!iq_slp[k] || (ol_valid && a_age == ol_age)) && (!ou_valid || a_age < ou_age || !mdp_wait[mdp_i(iq_pc[k])]) && (!fo_valid || a_age < fo_age);
                    else if (p < P_FP) ok = ok && iq_cls[k] == C_ST;
                    // FP ports: FMA-capable ports take FMA/FMUL/FADD, misc ports FADD and the rest;
                    // the first misc port starts divide/sqrt when the unit is free.
                    else ok = ok && iq_cls[k] == C_FP && rdy2(k) && rdy3(k) &&
                              (p < P_FP + N_FMA ? iq_funit[k] <= 2'd1 :
                               (iq_funit[k] == 2'd1 || iq_funit[k] == 2'd2 ||
                                (iq_funit[k] == 2'd3 && p == P_FP + N_FMA && !(fd_gap != 0 || fd_pend || fdtaken))));
                    // Branch-capable ports: a full-class instruction (branch, jump, system, M)
                    // before any plain ALU one, oldest first within each.
                    if (ok && (!bestv || (p < N_BR && iq_cls[k] == C_FULL && iq_cls[best] != C_FULL) ||
                               (a_age < best_age && !(p < N_BR && iq_cls[k] != C_FULL && iq_cls[best] == C_FULL)))) begin
                        bestv = 1; best = k[IQ_B-1:0]; best_age = a_age;
                    end
                end
                if (bestv) begin
                    pick_v[p] = 1; pick[p] = best; chosen[best] = 1;
                    if (iq_mdu[best] && iq_insn[best][14]) divtaken = 1;
                    if (iq_cls[best] == C_FP && iq_funit[best] == 2'd3) fdtaken = 1;
                end
            end
            prf_late = 0;

            // ---- branch-predictor training queue (frontend 12): TG_RU per clock, in order
            for (tq_k = 0; tq_k < TG_RU; tq_k = tq_k + 1) if (TG_N != 0 && tq_cnt != 0) begin
                tg_train(tq_pc[tq_h], tq_gh[tq_h], tq_b[tq_h][7:0], tq_b[tq_h][8]);
                tq_h = (tq_h + 1) % TQ_N; tq_cnt = tq_cnt - 1;
            end
            // ---- retirement window
            n_ret = 0; n_tq = 0; n_it = 0; rflush = 0; trap_now = 0; stop = 0; rflush_pc = 0; rflush_ld = 0; rflush_e = 0; st1_seen = 0; smc = 0; st_last = 0; wb2v = 0; wb1 = 0; wb2 = 0; st_n = 0; wb3 = 0; wb4 = 0;
            // A store write faulted while split reads were outstanding: nothing retires; once they
            // have returned and no request is on the bus, that store traps (cause 7).
            if (sf_wait) begin
                stop = 1;
                if (!split_out(1'b0) && bus_kind == 0) begin
                    trap_now = 1; trap_pc <= sf_pc; trap_cause <= 7; trap_tval <= sf_addr;
                end
            end
            for (s = 0; s < RW; s = s + 1) begin
                e = rb_head + s[ROB_B-1:0];
                if (!stop) begin
                    if (s >= rb_count || !rb_done[e]) stop = 1;
                    else if (rb_exc[e]) begin
                        if (s == 0 && bus_kind == 0 && !split_out(1'b0)) begin
                            trap_now = 1;
                            trap_pc <= rb_pc[e]; trap_cause <= rb_cause[e]; trap_tval <= rb_tval[e];
`ifdef RV64_OOO_V
                            rt_vtrap <= rb_vec[e]; rt_vb <= vr_vb; rt_vn <= vr_vn; rt_cn <= vr_cn;
                            rt_vcsr <= {vr_csr[2], vr_csr[1], vr_csr[0]}; rt_vcval <= {vr_cval[2], vr_cval[1], vr_cval[0]};
`endif
                        end
                        stop = 1;
                    end else if (rb_store[e]) begin
                        // Stores retire with this clock's write in program order: the first
                        // with mem_error, the second with mem_error2, up to two more with
                        // mem_xerror; one whose part failed traps; a store after those waits
                        // for next clock's write.
                        if (st_n == 0 && !(bus_kind == 3 && mem_ready)) stop = 1;
                        else if (st_n == 3'd1 + {2'b0, pair_now} + (pair_now ? {1'b0, nx_now} : 3'd0)) stop = 1;
                        else if ((st_n == 0 ? mem_error : st_n == 1 ? mem_error2 : mem_xerror[st_n[0]]) && split_out(1'b0)) begin
                            sf_wait = 1; sf_pc = rb_pc[e]; sf_addr = rb_addr[e]; stop = 1;   // trap after the drain
                        end else if (st_n == 0 ? mem_error : st_n == 1 ? mem_error2 : mem_xerror[st_n[0]]) begin
                            trap_now = 1; trap_pc <= rb_pc[e]; trap_cause <= 7; trap_tval <= rb_addr[e]; stop = 1;
                        end else begin
                            n_ret = s + 1;
                            case (st_n)
                                3'd0: wb1 = rb_addr[e][63:3];
                                3'd1: wb2 = rb_addr[e][63:3];
                                3'd2: wb3 = rb_addr[e][63:3];
                                default: wb4 = rb_addr[e][63:3];
                            endcase
                            st_n = st_n + 3'd1;
                        end
                    end else if (st_n != 0 && (rb_pc[e][63:3] == wb1 || (st_n > 1 && rb_pc[e][63:3] == wb2) ||
                                 (st_n > 2 && rb_pc[e][63:3] == wb3) || (st_n > 3 && rb_pc[e][63:3] == wb4))) begin
                        stop = 1;   // fetched from a beat written this clock: refetched after
                    end else if (rb_viol[e]) begin
                        // Read stale bytes: refetch from this load; it waits for older stores from now on.
                        rflush = 1; rflush_pc = rb_pc[e]; stop = 1; mdp_wait[mdp_i(rb_pc[e])] = 1; rflush_ld = 1; rflush_e = e;
                    end else if (TG_N != 0 && rb_ctl[e] && rb_insn[e][6:0] == 7'h63 && tq_cnt + n_tq >= TQ_N) begin
                        stop = 1;   // the predictor's training queue is full (frontend 12)
                    end else if (IT_N != 0 && is_ind(rb_insn[e]) && n_it >= IT_RU) begin
                        stop = 1;   // IT_RU indirect-target trainings per clock
                    end else begin
                        n_ret = s + 1;
                        if (IT_N != 0 && is_ind(rb_insn[e])) n_it = n_it + 1;
                        if (TG_N != 0 && rb_ctl[e] && rb_insn[e][6:0] == 7'h63) n_tq = n_tq + 1;
                        if (rb_ends[e]) begin rflush = 1; rflush_pc = rb_next[e]; stop = 1; end
                    end
                end
            end

            // ================= phase 2: apply =================
            // ---- retire
            for (s = 0; s < RW; s = s + 1) if (s < n_ret) begin
                e = rb_head + s[ROB_B-1:0];
                if (rb_elim[e]) rb_value[e] = prf[rb_pdst[e]] + rb_off[e];
                v = rb_writes[e] ? rb_value[e] : 64'b0;
                rt_valid[s] <= 1'b1; rt_pc[64*s +: 64] <= rb_pc[e]; rt_insn[32*s +: 32] <= rb_insn[e];
                rt_rd[5*s +: 5] <= rb_writes[e] ? rb_rd[e][4:0] : 5'd0; rt_data[64*s +: 64] <= v;
                if (FPU != 0) begin rt_rdfp[s] <= rb_writes[e] && rb_rd[e][AR_B-1]; rt_ff[5*s +: 5] <= rb_fflags[e]; fcsr[4:0] = fcsr[4:0] | rb_fflags[e]; end
                rt_next[64*s +: 64] <= rb_next[e];
                if (s == 0) begin
                    retire_valid <= 1; retire_pc <= rb_pc[e]; retire_insn <= rb_insn[e];
                    retire_rd <= rb_writes[e] ? rb_rd[e][4:0] : 5'd0; retire_data <= v; retire_next_pc <= rb_next[e];
                end
                if (s == 1) begin
                    retire2_valid <= 1; retire2_pc <= rb_pc[e]; retire2_insn <= rb_insn[e];
                    retire2_rd <= rb_writes[e] ? rb_rd[e][4:0] : 5'd0; retire2_data <= v; retire2_next_pc <= rb_next[e];
                end
                if (s == 2) begin
                    retire3_valid <= 1; retire3_pc <= rb_pc[e]; retire3_insn <= rb_insn[e];
                    retire3_rd <= rb_writes[e] ? rb_rd[e][4:0] : 5'd0; retire3_data <= v; retire3_next_pc <= rb_next[e];
                end
                if (rb_writes[e]) begin
                    rrat[rb_rd[e]] = rb_pdst[e]; rrat_off[rb_rd[e]] = rb_elim[e] ? rb_off[e] : 64'b0;
                    if (rb_opdst[e] != 0) begin
                        refcnt[rb_opdst[e]] = refcnt[rb_opdst[e]] - 1;
                        if (refcnt[rb_opdst[e]] == 0) free_mask[rb_opdst[e]] = 1;
                    end
                end
                if (rb_writes[e] && !(FPU != 0 && rb_rd[e][AR_B-1]) && (rb_load[e] || ((rb_insn[e][6:0] == 7'h33 || rb_insn[e][6:0] == 7'h3b) && rb_insn[e][31:25] == 7'h01))) begin
                    vpi = rb_pc[e][2 +: VP_BITS];
                    if (vp_valid[vpi] && vp_tag[vpi] == rb_pc[e][2+VP_BITS +: VP_TAG] && vp_val[vpi] == rb_value[e]) begin
                        if (vp_conf[vpi] != 63) vp_conf[vpi] = vp_conf[vpi] + 1;
                    end else begin
                        if (!(vp_valid[vpi] && vp_tag[vpi] == rb_pc[e][2+VP_BITS +: VP_TAG])) vp_strk[vpi] = 0;
                        else if (rb_vp[e] && rb_vpbad[e] && vp_strk[vpi] != 3) vp_strk[vpi] = vp_strk[vpi] + 1;
                        vp_valid[vpi] = 1; vp_tag[vpi] = rb_pc[e][2+VP_BITS +: VP_TAG]; vp_val[vpi] = rb_value[e]; vp_conf[vpi] = 0;
                    end
                end
                if (rb_ctl[e] && rb_insn[e][6:0] == 7'h63) begin
                    if (TG_N != 0) begin
                        tq_k = (tq_h + tq_cnt) % TQ_N; tq_cnt = tq_cnt + 1;
                        tq_pc[tq_k] = rb_pc[e]; tq_gh[tq_k] = rb_gh[e]; tq_b[tq_k] = {rb_taken[e], rb_tp[e]};
                    end
                    r_gh = {r_gh[GH_L-2:0], rb_taken[e]};
                    li_ = rb_pc[e][2 +: LP_BITS];
                    if (!lp_valid[li_] || lp_tag[li_] != rb_pc[e][2+LP_BITS +: LP_TAG]) begin
                        lp_valid[li_] = 1; lp_tag[li_] = rb_pc[e][2+LP_BITS +: LP_TAG]; lp_dir[li_] = rb_taken[e];
                        lp_ret[li_] = 1; lp_trip[li_] = 0; lp_conf[li_] = 0;
                    end else if (rb_taken[e] == lp_dir[li_]) begin
                        if (lp_ret[li_] != 255) lp_ret[li_] = lp_ret[li_] + 1;
                        if (lp_ret[li_] > lp_trip[li_]) lp_conf[li_] = 0;
                    end else if (lp_ret[li_] == 0) begin
                        lp_dir[li_] = rb_taken[e]; lp_ret[li_] = 1; lp_trip[li_] = 0; lp_conf[li_] = 0;
                    end else begin
                        if (lp_ret[li_] == lp_trip[li_]) begin if (lp_conf[li_] != 3) lp_conf[li_] = lp_conf[li_] + 1; end
                        else begin lp_trip[li_] = lp_ret[li_]; lp_conf[li_] = 0; end
                        lp_ret[li_] = 0;
                    end
                end
                if (IT_N != 0 && is_ind(rb_insn[e])) begin
                    bi = rb_pc[e][2 +: BTB_BITS];
                    it_train(rb_pc[e], rb_ph[e], rb_next[e], rb_ipt[e] != rb_next[e],
                             btb_valid[bi] && btb_tag[bi] == rb_pc[e][2+BTB_BITS +: BTB_TAG] && !btb_ret[bi] && btb_ctr[bi][1],
                             btb_dec(rb_pc[e], btb_target[bi]));
                    r_ph = ph_upd(r_ph, rb_next[e]);
                end
                if (rb_ctl[e]) begin
                    bi = rb_pc[e][2 +: BTB_BITS];
                    if (rb_taken[e]) begin
                        btb_ctr[bi] = (btb_valid[bi] && btb_tag[bi] == rb_pc[e][2+BTB_BITS +: BTB_TAG]) ?
                                      (btb_ctr[bi] == 3 ? 2'd3 : btb_ctr[bi] + 2'd1) : 2'd2;
                        btb_valid[bi] = 1; btb_tag[bi] = rb_pc[e][2+BTB_BITS +: BTB_TAG];
                        btb_target[bi] = btb_enc(rb_pc[e], rb_next[e]); btb_ret[bi] = rb_ret[e];
                        if (!btb_fits(rb_pc[e], rb_next[e])) btb_valid[bi] = 0;   // beyond the offset's reach
                    end else if (btb_valid[bi] && btb_tag[bi] == rb_pc[e][2+BTB_BITS +: BTB_TAG])
                        btb_ctr[bi] = btb_ctr[bi] == 0 ? 2'd0 : btb_ctr[bi] - 2'd1;
                end
                if (rb_store[e]) begin
                    // Write-through: update a cached line; drop a cached instruction beat.
                    r_wd = ((prf[rb_sps2[e]] + rb_soff[e]) & (rb_fsw[e] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {rb_addr[e][2:0],3'b000};
                    fi = rb_addr[e][3 +: IC_INDEX];
                    if (dc_line(rb_addr[e]) >= 0)
                        for (k = 0; k < 8; k = k + 1)
                            if (rb_wstrb[e][k]) dc_data[dc_di(dc_line(rb_addr[e]), rb_addr[e])][8*k +: 8] = r_wd[8*k +: 8];
                    if (ic_valid[fi] && ic_tag[fi] == rb_addr[e][63 -: IC_TAG]) ic_valid[fi] = 0;
                    if (fb_valid && fb_beat[63:3] == rb_addr[e][63:3])
                        for (k = 0; k < 8; k = k + 1) if (rb_wstrb[e][k]) fb_data[8*k +: 8] = r_wd[8*k +: 8];
                    if (LB == 1 && SPLIT && mu_valid && mu_sent && mu_beat[63:3] == rb_addr[e][63:3]) mu_stale = 1;
                    for (k = 1; k < PM_N; k = k + 1)
                        if (LB == 1 && SPLIT && pm_valid[k] && pm_sent[k] && pm_beat[k][63:3] == rb_addr[e][63:3]) pm_stale[k] = 1;
                    // Line fills: a store after acceptance merges into the line (and keeps its bytes).
                    if (LB > 1) for (k = 0; k < PM_N; k = k + 1)
                        if (k == 0 ? (mu_valid && mu_sent && dl_ln(mu_beat) == dl_ln(rb_addr[e])) :
                                     (pm_valid[k] && pm_sent[k] && dl_ln(pm_beat[k]) == dl_ln(rb_addr[e]))) begin
                            lk = (rb_addr[e] >> 3) % LB;
                            for (b2 = 0; b2 < 8; b2 = b2 + 1)
                                if (rb_wstrb[e][b2]) begin lb_data[k][lk][8*b2 +: 8] = r_wd[8*b2 +: 8]; lb_wm[k][lk][b2] = 1; end
                        end
                    // Younger instructions already fetched from this beat are refetched.
                    hit = 0;
                    for (k = 0; k < ROB_N; k = k + 1)
                        if (rb_live[k] && (k[ROB_B-1:0] - rb_head) > s[ROB_B-1:0] && rb_pc[k][63:3] == rb_addr[e][63:3]) hit = 1;
                    for (k = 0; k < q_count; k = k + 1)
                        if (q_pc[(q_head + k) % Q_N][63:3] == rb_addr[e][63:3]) hit = 1;
                    for (k = 0; k <= FW/2; k = k + 1)
                        if (f_pc[63:3] + k == rb_addr[e][63:3]) hit = 1;
                    if (hit) smc = 1;
                end
                if (rb_fencei[e]) ic_valid = 0;
                if (FPU != 0 && rb_csrw[e]) begin fcsr = rb_csrv[e]; rt_csrw[s] <= 1; rt_csrv[8*s +: 8] <= rb_csrv[e]; end
                if (FPU != 0 && rb_live[e] && rb_insn[e][6:0] == 7'h73 && rb_insn[e][14:12] != 0) csr_busy = 0;
`ifdef RV64_OOO_V
                if (rb_vec[e]) begin
                    v_busy = 0; rt_vec <= 1; rt_vb <= vr_vb; rt_vn <= vr_vn; rt_cn <= vr_cn;
                    rt_vcsr <= {vr_csr[2], vr_csr[1], vr_csr[0]}; rt_vcval <= {vr_cval[2], vr_cval[1], vr_cval[0]};
                    rb_vec[e] = 0; rb_vref[e] = 0;
                end
`endif
                rb_live[e] = 0; rb_done[e] = 0;
            end
            // A retired store wrote the beat of a younger fetched instruction: refetch
            // after the last instruction retired this clock.
            if (smc) begin rflush = 1; rflush_pc = rb_next[rb_head + n_ret[ROB_B-1:0] - 1'b1]; end
            if (trap_now) begin
                trap_valid <= 1; halted = 1;
            end else begin
            // ---- execute: results of the instructions selected last clock
            mp_any = 0; b_rob = 0; mp_fix = 0;
            for (p = 0; p < N_BR; p = p + 1) if (ex_valid[p] && ex_cls[p] == C_FULL) begin
                ef = exec_full(ex_insn[p], ex_pc[p], opa(p), opb(p));
                op = ex_insn[p][6:0];
                if (!ef[197] && !ef[0] && ((op == 7'h63 && ((TG_N != 0) ? br_cond(ex_insn[p][14:12], opa(p), opb(p)) : (ef[64:1] != ex_pc[p] + 64'd4)) != ex_ptaken[p]) ||
                                           (op == 7'h67 && ef[64:1] != ex_pred[p]))) begin
                    a_age = ex_rob[p] - rb_head;
                    if (!mp_any || a_age < (b_rob - rb_head)) begin mp_any = 1; b_rob = ex_rob[p]; mp_fix = ef[64:1]; end
                end
            end
            if (rflush) mp_any = 0;
            o_age = b_rob - rb_head;
            miss_v = 0; miss_beat = 0; miss_age = 0; pf_v = 0; pf_beat = 0; pf_age = 0; pc_n = 0; ms_n = 0;
            // Store-address ports first, then ALU and load ports, so a load sees the
            // addresses of older stores executing in the same clock.
            for (p = N_ALU + N_LD; p < NP; p = p == NP - 1 ? 0 : p == N_ALU + N_LD - 1 ? NP : p + 1)
                if (ex_valid[p] && !rflush && !(mp_any && (ex_rob[p] - rb_head) > o_age)) begin
                x_rob = ex_rob[p];
                if (p < N_ALU) begin
                    if (ex_cls[p] == C_ALU) begin
                        sa = simple_alu(ex_insn[p], opa(p), opb(p), ex_pc[p]);
                        if (ex_writes[p]) begin prf[ex_pdst[p]] = sa[63:0]; prf_written[ex_pdst[p]] = 1; end
                        rb_value[x_rob] = sa[63:0]; rb_done[x_rob] = 1; rb_exc[x_rob] = 0; rb_next[x_rob] = ex_pc[p] + 64'd4;
                    end else begin
                        ef = exec_full(ex_insn[p], ex_pc[p], opa(p), opb(p));
                        op = ex_insn[p][6:0]; f3_ = ex_insn[p][14:12];
                        rb_next[x_rob] = ef[64:1];
                        if (ef[0]) begin
                            if (!f3_[2]) begin : mul_start
                                reg placed;
                                placed = 0;
                                for (k = 0; k < MQ_N; k = k + 1) if (!mq_valid[k] && !placed) begin
                                    placed = 1; mq_valid[k] = 1; mq_cnt[k] = MUL_LAT - 2; mq_rob[k] = x_rob;
                                    mq_pdst[k] = ex_pdst[p]; mq_writes[k] = ex_writes[p];
                                    mq_val[k] = mul_value(f3_, op == 7'h3b, opa(p), opb(p));
                                end
                                if (!placed) $fatal(1, "multiply pipeline full (MQ_N too small for N_BR)");
                            end else begin
                                dv_busy = 1; dv_cnt = DIV_LAT - 2; dv_rob = x_rob; dv_pdst = ex_pdst[p]; dv_writes = ex_writes[p];
                                dv_val = div_value(f3_, op == 7'h3b, opa(p), opb(p));
                            end
                        end else begin
                            if (ex_writes[p] && !ef[197]) begin prf[ex_pdst[p]] = ef[128:65]; prf_written[ex_pdst[p]] = 1; end
                            rb_value[x_rob] = ef[128:65]; rb_done[x_rob] = 1; rb_exc[x_rob] = ef[197];
                            rb_cause[x_rob] = {60'b0, ef[196:193]}; rb_tval[x_rob] = ef[192:129];
                            rb_ctl[x_rob] = !ef[197] && (op == 7'h63 || op == 7'h6f || op == 7'h67);
                            rb_taken[x_rob] = op == 7'h6f || op == 7'h67 ||
                                              ((op == 7'h63 && TG_N != 0) ? br_cond(f3_, opa(p), opb(p)) : (ef[64:1] != ex_pc[p] + 64'd4));
                            rb_ret[x_rob] = op == 7'h67 && ex_insn[p][11:7] == 0 &&
                                            (ex_insn[p][19:15] == 1 || ex_insn[p][19:15] == 5);
                            rb_fencei[x_rob] = op == 7'h0f && f3_ == 1 && !ef[197];
                        end
                    end
                end else if (p < N_ALU + N_LD) begin
                    // A load woke its consumers when it issued; until it answers below, its
                    // register is not ready, which cancels consumers selected this clock
                    // (a value-predicted load's register stays ready with its prediction).
                    if (ex_writes[p] && !rb_vp[x_rob] && (LD_LAT < 2 || !prf_written[ex_pdst[p]])) prf_ready[ex_pdst[p]] = 0;
                    // Load: forward from the youngest older store to its beat, else the cache;
                    // if neither can answer now, the load stays queued and replays.
                    f3_ = ex_insn[p][14:12];
                    ea = opa(p) + {{52{ex_insn[p][31]}}, ex_insn[p][31:20]};
                    bytes_ = size_bytes(f3_[1:0]) << ea[2:0];
                    rb_addr[x_rob] = ea; rb_wstrb[x_rob] = bytes_;   // checked by older stores' addresses
                    fdone = 0;
                    if (f3_ == 3'd7 || (ea[2:0] & (f3_[1:0] == 0 ? 3'd0 : f3_[1:0] == 1 ? 3'd1 : f3_[1:0] == 2 ? 3'd3 : 3'd7)) != 0) begin
                        rb_done[x_rob] = 1; rb_exc[x_rob] = 1;
                        rb_cause[x_rob] = f3_ == 3'd7 ? 64'd2 : 64'd4; rb_tval[x_rob] = f3_ == 3'd7 ? {32'b0, ex_insn[p]} : ea;
                        iq_valid[ex_iq[p]] = 0;
                    end else if (mu_errv && x_rob == mu_err_owner && mu_err_beat[63:3] == ea[63:3]) begin
                        if (fb_lock && x_rob == fb_owner) fb_lock = 0;
                        rb_done[x_rob] = 1; rb_exc[x_rob] = 1; rb_cause[x_rob] = 5; rb_tval[x_rob] = ea;
                        iq_valid[ex_iq[p]] = 0;
                    end else begin
                        // Each byte comes from the youngest older store that writes it, the
                        // rest from the cache or fill buffer (0.11.0). The beat must have been
                        // read successfully (a cache or fill-buffer hit) even when stores cover
                        // every byte, so forwarding cannot hide a read access fault; a byte
                        // whose store data is not yet written makes the load replay.
                        fwd_mask = 0; fwd_byte_w = 0; fwd_wait = 0; fwd_data = 0;
                        a_age = x_rob - rb_head;
                        for (k = 0; k < ROB_N; k = k + 1) begin
                            e = rb_head + k[ROB_B-1:0];
                            if (k[ROB_B-1:0] < a_age && rb_live[e] && rb_store[e] && rb_sta[e] &&
                                rb_addr[e][63:3] == ea[63:3] && (rb_wstrb[e] & bytes_) != 0) begin
                                lw = ((prf[rb_sps2[e]] + rb_soff[e]) & (rb_fsw[e] ? 64'h00000000ffffffff : 64'hffffffffffffffff)) << {rb_addr[e][2:0],3'b000};
                                for (b2 = 0; b2 < 8; b2 = b2 + 1) if (rb_wstrb[e][b2] && bytes_[b2]) begin
                                    fwd_mask[b2] = 1; fwd_byte_w[b2] = prf_written[rb_sps2[e]]; fwd_data[8*b2 +: 8] = lw[8*b2 +: 8];
                                end
                            end
                        end
                        for (b2 = 0; b2 < 8; b2 = b2 + 1) if (fwd_mask[b2] && !fwd_byte_w[b2]) fwd_wait = 1;
                        dc_hit_ = dc_line(ea) >= 0;
                        fb_hit_ = fb_valid && fb_beat[63:3] == ea[63:3];
                        if (fwd_wait) begin end
                        else if (dc_hit_ || fb_hit_) begin
                            lw = dc_hit_ ? dc_data[dc_di(dc_line(ea), ea)] : fb_data;
                            for (b2 = 0; b2 < 8; b2 = b2 + 1) if (fwd_mask[b2]) lw[8*b2 +: 8] = fwd_data[8*b2 +: 8];
                            v = load_align(lw, ea[2:0], f3_); fdone = 1;
                            if (FPU != 0 && ex_insn[p][6:0] == 7'h07 && f3_ == 3'd2) v = {32'hffffffff, v[31:0]};   // flw: NaN-box
                        end else begin
                            // Stores cover every byte but the beat has not been read: the value
                            // goes to consumers now, and the load finishes after the read.
                            if (fwd_mask == bytes_ && ex_writes[p]) begin
                                prf[ex_pdst[p]] = (FPU != 0 && ex_insn[p][6:0] == 7'h07 && f3_ == 3'd2) ?
                                    fbox(load_align(fwd_data, ea[2:0], f3_)) : load_align(fwd_data, ea[2:0], f3_);
                                prf_written[ex_pdst[p]] = 1;
                                if (LD_LAT < 2 || rb_vp[x_rob]) prf_ready[ex_pdst[p]] = 1;
                                else if (!prf_ready[ex_pdst[p]]) ld_wake(ex_pdst[p], x_rob, 1'b0);
                            end
                            if (ol_valid && a_age == ol_age) begin
                                miss_v = 1; miss_beat = {ea[63:3],3'b000}; miss_age = a_age; miss_owner = x_rob;
                            end else if (SPLIT && pc_n < N_LD && !in_flight(ea)) begin
                                // a younger miss whose beat no entry is reading yet (chosen after
                                // entry 0 is allocated, so a duplicate of its beat cannot win)
                                pc_beat[pc_n] = {ea[63:3],3'b000}; pc_age[pc_n] = a_age; pc_n = pc_n + 1;
                            end
                            if (!(ol_valid && a_age == ol_age) && ms_n < N_LD) begin
                                ms_iq[ms_n] = ex_iq[p]; ms_beat[ms_n] = ea[63:3]; ms_n = ms_n + 1;
                            end
                        end
                        if (fdone && fb_lock && x_rob == fb_owner) fb_lock = 0;
                        // A finished owner gives up entry 0: a later answer fills without a lock.
                        if (fdone && mu_owner_v && x_rob == mu_owner) mu_owner_v = 0;
                        // It gave a value read or forwarded (finished, or full early forwarding).
                        if (fdone || (!fwd_wait && fwd_mask == bytes_ && ex_writes[p])) rb_ldv[x_rob] = 1;
                        if (fdone) begin
                            // With LD_LAT >= 2 the load finishes (and may retire) only when it
                            // wakes its consumers, so its register cannot be freed and reused first.
                            if (ex_writes[p]) begin prf[ex_pdst[p]] = v; prf_written[ex_pdst[p]] = 1; end
                            if (LD_LAT < 2 || rb_vp[x_rob]) begin
                                if (ex_writes[p]) prf_ready[ex_pdst[p]] = 1;
                                rb_done[x_rob] = 1;
                            end else begin
                                // L0 (hand-off 7): a beat read by a recent load answers sooner.
                                l0_hit = 0;
                                if (L0_N > 0) begin
                                    for (l0_k = 0; l0_k < L0_S; l0_k = l0_k + 1)
                                        if (l0_v[l0_k] && l0_beat[l0_k] == ea[63:3]) l0_hit = 1;
                                    if (!l0_hit) begin l0_v[l0_p] = 1; l0_beat[l0_p] = ea[63:3]; l0_p = (l0_p + 1) % L0_S; end
                                end
                                ld_lat_now = l0_hit ? L0_LAT : LD_LAT;
                                ld_wake(ex_writes[p] ? ex_pdst[p] : {P_B{1'b0}}, x_rob, 1'b1);
                                ld_lat_now = LD_LAT;
                                rb_ans[x_rob] = 1;
                            end
                            rb_value[x_rob] = v; rb_exc[x_rob] = 0;
                            if (rb_vp[x_rob] && v != rb_vpv[x_rob]) rb_vpbad[x_rob] = 1;
                            iq_valid[ex_iq[p]] = 0;
                        end else iq_issued[ex_iq[p]] = 0;
                    end
                end else if (p < P_FP) begin
                    // Store: record the address; the data register is read at retirement.
                    f3_ = ex_insn[p][14:12];
                    ea = opa(p) + {{52{ex_insn[p][31]}}, ex_insn[p][31:25], ex_insn[p][11:7]};
                    ok = !f3_[2] && (ea[2:0] & (f3_[1:0] == 0 ? 3'd0 : f3_[1:0] == 1 ? 3'd1 : f3_[1:0] == 2 ? 3'd3 : 3'd7)) == 0;
                    rb_done[x_rob] = 1; rb_sta[x_rob] = 1; rb_exc[x_rob] = !ok;
                    rb_cause[x_rob] = f3_[2] ? 64'd2 : 64'd6; rb_tval[x_rob] = f3_[2] ? {32'b0, ex_insn[p]} : ea;
                    rb_addr[x_rob] = ea; rb_wstrb[x_rob] = size_bytes(f3_[1:0]) << ea[2:0]; rb_sps2[x_rob] = ex_ps2[p]; rb_soff[x_rob] = ex_off2[p];
                    // A younger load that already gave its value (finished, or forwarded to its
                    // consumers early) and read bytes this store writes is stale, except bytes a
                    // store between the two writes that already has its address (the load took
                    // them from that store, or that store marks the load when it resolves).
                    if (ok) for (k = 0; k < ROB_N; k = k + 1) begin
                        e = k[ROB_B-1:0];
                        if (rb_live[e] && rb_load[e] && !rb_exc[e] &&
                            rb_ldv[e] && (e - rb_head) > (x_rob - rb_head) &&
                            rb_addr[e][63:3] == ea[63:3] && (rb_wstrb[e] & rb_wstrb[x_rob]) != 0) begin
                            vc_mask = rb_wstrb[e] & rb_wstrb[x_rob];
                            for (vc_k = 0; vc_k < ROB_N; vc_k = vc_k + 1) begin
                                vc_e = vc_k[ROB_B-1:0];
                                if (rb_live[vc_e] && rb_store[vc_e] && rb_sta[vc_e] && (vc_e - rb_head) > (x_rob - rb_head) &&
                                    (vc_e - rb_head) < (e - rb_head) && rb_addr[vc_e][63:3] == ea[63:3])
                                    vc_mask = vc_mask & ~rb_wstrb[vc_e];
                            end
                            if (vc_mask != 0) rb_viol[e] = 1;
                        end
                    end
                end else begin
                    // F/D execute (RV64_OOO_FPU). DYN rounding with frm 5-7 is an illegal instruction.
                    if (ex_rm[p] == 3'd7 && fcsr[7:5] > 3'd4) begin
                        rb_done[x_rob] = 1; rb_exc[x_rob] = 1; rb_cause[x_rob] = 2; rb_tval[x_rob] = {32'b0, ex_insn[p]};
                    end else begin
                        frm_now = ex_rm[p] == 3'd7 ? fcsr[7:5] : ex_rm[p];
                        fy = fp_exec(ex_fop[p], ex_fsz[p], frm_now, opa(p), opb(p), prf[ex_ps3[p]]);
                        rb_next[x_rob] = ex_pc[p] + 64'd4;
                        begin : fq_start
                            reg placed;
                            placed = 0;
                            // Divide/sqrt: pipelined at its initiation interval (the next start waits fd_gap).
                            if (ex_funit[p] == 2'd3) begin
                                flat = ex_fop[p] == FOP_SQRT ? (ex_fsz[p] ? FSQRT_D : FSQRT_S) : (ex_fsz[p] ? FDIV_D : FDIV_S);
                                fd_gap = (ex_fop[p] == FOP_SQRT ? (ex_fsz[p] ? FSQRT_II_D : FSQRT_II_S) : (ex_fsz[p] ? FDIV_II_D : FDIV_II_S)) - 1;
                                fd_grob = x_rob;
                            end else
                                flat = ex_funit[p] == 2'd0 ? (ex_fop[p] == FOP_MUL ? FMUL_LAT : FMA_LAT) : ex_funit[p] == 2'd1 ? FADD_LAT :
                                       (ex_fop[p] >= FOP_CVT_W && ex_fop[p] <= FOP_CVT_DS) ? FCVT_LAT : FMISC_LAT;
                            for (k = 0; k < FQ_N; k = k + 1) if (!fq_valid[k] && !placed) begin
                                placed = 1; fq_valid[k] = 1; fq_cnt[k] = flat - 2; fq_rob[k] = x_rob; fq_pdst[k] = ex_pdst[p];
                                fq_writes[k] = ex_writes[p]; fq_val[k] = fy[63:0]; fq_fl[k] = fy[68:64];
                            end
                            if (!placed) $fatal(1, "FP pipeline full (FQ_N)");
                        end
                    end
                end
            end
            // The oldest load always takes entry 0, even when a younger entry reads the same
            // beat (that entry has no owner; a fault it gets is dropped, so the oldest load must
            // read the beat itself to fault precisely: Codex review of hand-off 2, item 1).
            if (miss_v && !mu_valid && !fb_lock) begin
                mu_valid = 1; mu_beat = miss_beat; mu_errv = 0; mu_owner = miss_owner; mu_owner_v = 1; mu_sent = 0; mu_stale = 0;
            end
            // The oldest of this clock's younger misses whose beat no entry reads takes a free entry.
            for (pc_i = 0; pc_i < N_LD; pc_i = pc_i + 1)
                if (SPLIT && pc_i < pc_n && !in_flight(pc_beat[pc_i]) && (!pf_v || pc_age[pc_i] < pf_age)) begin
                    pf_v = 1; pf_beat = pc_beat[pc_i]; pf_age = pc_age[pc_i];
                end
            if (SPLIT && pf_v && !(mu_valid && dl_ln(mu_beat) == dl_ln(pf_beat))) begin
                pm_dup = 0; pm_free = 0;
                for (pm_k = PM_N - 1; pm_k >= 1; pm_k = pm_k - 1) begin
                    if (pm_valid[pm_k] && dl_ln(pm_beat[pm_k]) == dl_ln(pf_beat)) pm_dup = 1;
                    if (!pm_valid[pm_k]) pm_free = pm_k;
                end
                if (!pm_dup && pm_free != 0) begin
                    pm_valid[pm_free] = 1; pm_sent[pm_free] = 0; pm_stale[pm_free] = 0; pm_beat[pm_free] = pf_beat;
                end
            end
            for (ms_k = 0; ms_k < N_LD; ms_k = ms_k + 1) if (ms_k < ms_n) begin
                ms_infl = mu_valid && dl_ln(mu_beat) == (ms_beat[ms_k] >> LBB);
                ms_free = !SPLIT;
                for (pm_k = 1; pm_k < PM_N; pm_k = pm_k + 1) begin
                    if (SPLIT && pm_valid[pm_k] && dl_ln(pm_beat[pm_k]) == (ms_beat[ms_k] >> LBB)) ms_infl = 1;
                    if (SPLIT && !pm_valid[pm_k]) ms_free = 1;
                end
                if (ms_infl || !ms_free) begin
                    iq_slp[ms_iq[ms_k]] = 1; iq_wany[ms_iq[ms_k]] = !ms_infl; iq_wb[ms_iq[ms_k]] = ms_beat[ms_k];
                end
            end
            // ---- load wakeups (LD_LAT >= 2)
            if (LD_LAT >= 2) for (k = 0; k < LW_N; k = k + 1) if (lw_valid[k]) begin
                if (rflush || (mp_any && (lw_rob[k] - rb_head) > o_age)) lw_valid[k] = 0;
                else if (lw_cnt[k] == 0) begin
                    // The value was written when the load answered: an offset consumer
                    // still pays its clock (prf_late, as for multiply and divide writes).
                    lw_valid[k] = 0; prf_ready[lw_pdst[k]] = 1; if (lw_pdst[k] != 0) prf_late[lw_pdst[k]] = 1;
                    if (lw_fin[k]) rb_done[lw_rob[k]] = 1;
                end else lw_cnt[k] = lw_cnt[k] - 1;
            end
            // ---- FP pipelines and the FP divide/sqrt unit (RV64_OOO_FPU)
            // A squashed divide/sqrt frees the unit (it no longer holds the next start).
            if (fd_gap != 0 && (rflush || (mp_any && (fd_grob - rb_head) > o_age))) fd_gap = 0;
            if (fd_gap != 0) fd_gap = fd_gap - 1;
            for (k = 0; k < FQ_N; k = k + 1) if (fq_valid[k]) begin
                if (rflush || (mp_any && (fq_rob[k] - rb_head) > o_age)) fq_valid[k] = 0;
                else if (fq_cnt[k] == 0) begin
                    fq_valid[k] = 0;
                    if (fq_writes[k]) begin prf_late[fq_pdst[k]] = !prf_ready[fq_pdst[k]]; prf[fq_pdst[k]] = fq_val[k]; prf_written[fq_pdst[k]] = 1; prf_ready[fq_pdst[k]] = 1; end
                    rb_value[fq_rob[k]] = fq_val[k]; rb_done[fq_rob[k]] = 1; rb_exc[fq_rob[k]] = 0; rb_fflags[fq_rob[k]] = fq_fl[k];
                end else fq_cnt[k] = fq_cnt[k] - 1;
            end
            // ---- multiply pipeline and divide unit
            for (k = 0; k < MQ_N; k = k + 1) if (mq_valid[k]) begin
                if (rflush || (mp_any && (mq_rob[k] - rb_head) > o_age)) mq_valid[k] = 0;
                else if (mq_cnt[k] == 0) begin
                    mq_valid[k] = 0;
                    if (mq_writes[k]) begin prf_late[mq_pdst[k]] = !prf_ready[mq_pdst[k]]; prf[mq_pdst[k]] = mq_val[k]; prf_written[mq_pdst[k]] = 1; prf_ready[mq_pdst[k]] = 1; end
                    rb_value[mq_rob[k]] = mq_val[k]; rb_done[mq_rob[k]] = 1; rb_exc[mq_rob[k]] = 0;
                    if (rb_vp[mq_rob[k]] && mq_val[k] != rb_vpv[mq_rob[k]]) rb_vpbad[mq_rob[k]] = 1;
                end else mq_cnt[k] = mq_cnt[k] - 1;
            end
            if (dv_busy) begin
                if (rflush || (mp_any && (dv_rob - rb_head) > o_age)) dv_busy = 0;
                else if (dv_cnt == 0) begin
                    dv_busy = 0;
                    if (dv_writes) begin prf_late[dv_pdst] = !prf_ready[dv_pdst]; prf[dv_pdst] = dv_val; prf_written[dv_pdst] = 1; prf_ready[dv_pdst] = 1; end
                    rb_value[dv_rob] = dv_val; rb_done[dv_rob] = 1; rb_exc[dv_rob] = 0;
                    if (rb_vp[dv_rob] && dv_val != rb_vpv[dv_rob]) rb_vpbad[dv_rob] = 1;
                end else dv_cnt = dv_cnt - 1;
            end

            // ---- issue: the instructions selected this clock execute next clock
            ex_valid = 0;
            for (p = 0; p < NP; p = p + 1) if (pick_v[p]) begin
                k = pick[p];
                // Sources are checked again: a load that did not answer this clock takes
                // back the wakeup it gave when it issued.
                if (iq_valid[k] && !rflush && !(mp_any && (iq_rob[k] - rb_head) > o_age) && rdy1(k) &&
                    (iq_cls[k] == C_LD || iq_cls[k] == C_ST || rdy2(k)) && (iq_cls[k] != C_FP || rdy3(k))) begin
                    ex_valid[p] = 1; ex_iq[p] = k; ex_cls[p] = iq_cls[k]; ex_rob[p] = iq_rob[k]; ex_pc[p] = iq_pc[k];
                    ex_insn[p] = iq_insn[k]; ex_ps1[p] = iq_ps1[k]; ex_ps2[p] = iq_ps2[k]; ex_pdst[p] = iq_pdst[k];
                    ex_fz1[p] = iq_fz1[k]; ex_fz2[p] = iq_fz2[k]; ex_fzi[p] = iq_fzi[k]; ex_fzpc[p] = iq_fzpc[k];
                    ex_fza[p] = iq_fza[k]; ex_fzb[p] = iq_fzb[k]; ex_off1[p] = iq_off1[k]; ex_off2[p] = iq_off2[k];
                    ex_writes[p] = iq_writes[k]; ex_pred[p] = iq_pred[k]; ex_alt[p] = iq_alt[k]; ex_ptaken[p] = iq_ptaken[k];
                    ex_ps3[p] = iq_ps3[k]; ex_fop[p] = iq_fop[k]; ex_fsz[p] = iq_fsz[k]; ex_rm[p] = iq_rm[k]; ex_funit[p] = iq_funit[k];
                    if (iq_cls[k] == C_LD) iq_issued[k] = 1;
                    else iq_valid[k] = 0;
                    // A result one clock away wakes its consumers now.
                    // A load assumes it will answer (taken back above if not).
                    if ((iq_cls[k] == C_ALU || (iq_cls[k] == C_LD && LD_LAT < 2) || (iq_cls[k] == C_FULL && !iq_mdu[k])) && iq_writes[k])
                        prf_ready[iq_pdst[k]] = 1;
                end
            end

            // ---- recovery
            h_after = rb_head + n_ret[ROB_B-1:0];
            rb_count_new = rb_count - n_ret;
            if (rflush || mp_any) begin pv_ok = 0; csr_busy = 0; end
            if (rflush) begin
                squash_after(n_ret[ROB_B-1:0] - 1);
                for (i = 0; i < NAR; i = i + 1) begin rat[i] = rrat[i]; rat_off[i] = rrat_off[i]; end
                free_mask = {PRF_N{1'b1}};
                for (i = 0; i < PRF_N; i = i + 1) refcnt[i] = 0;
                for (i = 0; i < NAR; i = i + 1) begin free_mask[rrat[i]] = 0; refcnt[rrat[i]] = refcnt[rrat[i]] + 1; end
                prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}}; prf_late = 0;
                ex_valid = 0; iq_valid = 0; iq_issued = 0; fb_lock = 0; mu_owner_v = 0; mu_errv = 0;
                rb_live = 0; rb_tail = h_after; rb_count_new = 0;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = rflush_pc; f_err = 0; f_hold = 0; if (bus_hold == 1) f_stale = 1;
                // A refetched load restores its own return-stack pointer (it may be the oldest).
                ras_sp = rflush_ld ? rb_rsp[rflush_e] : rb_rsp[rb_head + n_ret[ROB_B-1:0] - 1'b1];
                ras[ras_sp] = rflush_ld ? rb_rtos[rflush_e] : rb_rtos[rb_head + n_ret[ROB_B-1:0] - 1'b1];
                f_gh = rflush_ld ? rb_gh[rflush_e] : r_gh;
                if (IT_N != 0) f_ph = rflush_ld ? rb_ph[rflush_e] : r_ph;
            end else if (mp_any) begin
                squash_after(o_age);
                for (i = 0; i < NAR; i = i + 1) begin rat[i] = snap[b_rob][i]; rat_off[i] = snap_off[b_rob][i]; end
                ras_sp = rb_rsp[b_rob]; ras[ras_sp] = rb_rtos[b_rob];
                f_gh = rb_insn[b_rob][6:0] == 7'h63 ? {rb_gh[b_rob][GH_L-2:0], rb_taken[b_rob]} : rb_gh[b_rob];
                if (IT_N != 0) f_ph = is_ind(rb_insn[b_rob]) ? ph_upd(rb_ph[b_rob], mp_fix) : rb_ph[b_rob];
                rb_tail = b_rob + 1;
                rb_count_new = {1'b0, o_age} + 1 - n_ret;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = mp_fix; f_err = 0; f_hold = 0; if (bus_hold == 1) f_stale = 1;
            end
            rb_head = h_after;
`ifdef RV64_OOO_V
            // ---- vector unit (RV64_OOO_V, council simd): the vector instruction at the ROB head.
            // It renamed into an empty ROB and nothing younger renames before it retires, so it is
            // never squashed: it writes the vector registers and memory as it goes (a load element
            // as it arrives, a store element per bus write), which is what element-precise faults need.
            if (!rflush && !mp_any && rb_count_new != 0 && rb_live[rb_head] && rb_vec[rb_head] && !rb_done[rb_head]) begin : vunit
                reg [31:0] vins;
                reg vbad, vfin, vflt, vkeep, vact, vhit, vdone_el;
                reg [4:0] vcause;
                reg [63:0] vtval, vaddr, vbeat_d, vel;
                integer vkind, vsrcs, vk, vlo, vw, vcnt2, vsz;
                reg vallb, vnoov;
                e = rb_head; vins = rb_insn[e];
                vbad = 0; vfin = 0; vflt = 0; vcause = 0; vtval = 0;
                vf3_ = vins[14:12]; vrd_ = vins[11:7]; vrs1_ = vins[19:15]; vvs2_ = vins[24:20]; vvm_ = vins[25]; vf6_ = vins[31:26];
                // Scalar sources: everything older has retired, so the retirement map holds them.
                xs1_ = vrs1_ == 0 ? 64'b0 : prf[rrat[vrs1_]] + rrat_off[vrs1_];
                xs2_ = vvs2_ == 0 ? 64'b0 : prf[rrat[vvs2_]] + rrat_off[vvs2_];
                fsv_ = prf[rrat[{1'b1, vrs1_}]];
                vconf(vtype, vok, vsew, vnum, vden, vlmax);
                vlm = vnum / vden; if (vlm < 1) vlm = 1;
                if (vx_st == 2'd0) begin
                    vr_vn = 0; vr_cn = 0; vx_fl = 0; vx_res = 0; vx_cnt = 1;
                    if (vins[6:0] == 7'h57 && vf3_ == 3'd7) begin
                        // vsetvli / vsetivli / vsetvl (contract section 3)
                        if (!vins[31]) vt_ = {53'b0, vins[30:20]};
                        else if (vins[31:30] == 2'b11) vt_ = {54'b0, vins[29:20]};
                        else if (vins[30:25] == 6'd0) vt_ = xs2_;
                        else vbad = 1;
                        if (!vbad) begin : vset_blk
                            reg okn; integer s2, n2, d2, m2;
                            vconf(vt_, okn, s2, n2, d2, m2);
                            vkeep = vins[31:30] != 2'b11 && vrs1_ == 0 && vrd_ == 0;
                            if (!okn || (vkeep && (!vok || vlmax != m2))) begin vtype = 64'h8000000000000000; vl = 0; end
                            else begin
                                avl_ = vins[31:30] == 2'b11 ? {59'b0, vrs1_} : vrs1_ != 0 ? xs1_ : vrd_ != 0 ? ~64'd0 : vl;
                                vtype = vt_; vl = avl_ < m2 ? avl_ : m2;
                            end
                            vrec_c(12'hc20, vl); vrec_c(12'hc21, vtype); vx_res = vl; vfin = 1;
                            // vset* ends with vstart = 0 (RVV 1.0 section 3.7); the record only when it was non-zero
                            if (vstart != 0) begin vstart = 0; vrec_c(12'h008, 64'b0); end
                        end
                    end else if (vins[6:0] == 7'h73) begin
                        // Zicsr on the vector CSRs (vstart, vxsat, vxrm, vcsr, vl, vtype, vlenb)
                        case (vins[31:20])
                            12'h008: vold_ = vstart; 12'h009: vold_ = {63'b0, vxsat}; 12'h00a: vold_ = {62'b0, vxrm};
                            12'h00f: vold_ = {61'b0, vxrm, vxsat}; 12'hc20: vold_ = vl; 12'hc21: vold_ = vtype;
                            default: vold_ = VLENB;
                        endcase
                        va_ = vf3_[2] ? {59'b0, vrs1_} : xs1_;
                        vnew_ = vf3_[1:0] == 2'd1 ? va_ : vf3_[1:0] == 2'd2 ? (vold_ | va_) : (vold_ & ~va_);
                        if (vf3_[1:0] == 2'd1 || vrs1_ != 0) begin
                            case (vins[31:20])
                                12'h008: begin vstart = vnew_ & (VLEN - 1); vrec_c(12'h008, vstart); end
                                12'h009: begin vxsat = vnew_[0]; vrec_c(12'h009, {63'b0, vxsat}); end
                                12'h00a: begin vxrm = vnew_[1:0]; vrec_c(12'h00a, {62'b0, vxrm}); end
                                12'h00f: begin vxsat = vnew_[0]; vxrm = vnew_[2:1]; vrec_c(12'h00f, {61'b0, vxrm, vxsat}); end
                                default: vbad = 1;    // vl, vtype, vlenb are read-only
                            endcase
                        end
                        vx_res = vold_; vfin = 1;
                    end else if (vins[6:0] == 7'h07 || vins[6:0] == 7'h27) begin
                        // Loads and stores: set up the element loop (contract section 6).
                        vx_load = vins[6:0] == 7'h07; vx_vd = vrd_; vx_vm = vvm_;
                        vx_eewb = vf3_ == 3'd0 ? 1 : vf3_ == 3'd5 ? 2 : vf3_ == 3'd6 ? 4 : 8;
                        vx_base = xs1_; vx_stride = vx_eewb; vx_whole = 0; vx_mtail = 0; vx_ff = 0; vx_regs = 1;
                        if (vins[28]) vbad = 1;                                   // mew
                        else if (vins[27:26] == 2'd0 && vvs2_ == 5'd8) begin      // whole registers
                            vx_whole = 1; vx_regs = vins[31:29] + 1; vx_vm = 1;
                            if (!(vx_regs == 1 || vx_regs == 2 || vx_regs == 4 || vx_regs == 8) || !vvm_ || (!vx_load && vf3_ != 3'd0)) vbad = 1;
                            else if (vx_vd % vx_regs != 0) vbad = 1;
                            vx_evl = vx_regs * VLEN / (8 * vx_eewb);
                        end else if (vins[31:29] != 0 || !vok) vbad = 1;          // segments; vill
                        else if (vins[27:26] == 2'd0 && vvs2_ == 5'd11) begin     // vlm.v / vsm.v
                            if (vf3_ != 3'd0 || !vvm_) vbad = 1;
                            vx_evl = (vl + 7) / 8; vx_mtail = 1;
                        end else if ((vins[27:26] == 2'd0 && vvs2_ != 5'd0 && vvs2_ != 5'd16) || (vins[27:26] == 2'd0 && vvs2_ == 5'd16 && !vx_load))
                            vbad = 1;
                        else if (vins[27:26] == 2'd1 || vins[27:26] == 2'd3) vbad = 1;   // indexed: a later step
                        else begin
                            // EMUL = EEW / SEW * LMUL, from 1/8 to 8 (emul_regs)
                            vn2 = 8 * vx_eewb * vnum; vd2 = vsew * vden;
                            if (vn2 * 8 < vd2 || vn2 > 8 * vd2) vbad = 1;
                            else begin vx_regs = vn2 / vd2; if (vx_regs < 1) vx_regs = 1; end
                            if (!vbad && vx_vd % vx_regs != 0) vbad = 1;
                            if (vins[27:26] == 2'd2) vx_stride = xs2_;
                            vx_ff = vx_load && vins[27:26] == 2'd0 && vvs2_ == 5'd16;
                            vx_evl = vl;
                        end
                        if (!vbad && vx_load && !vx_vm && vx_vd == 0) vbad = 1;
                        if (!vbad) begin vx_st = 2'd1; vx_i = vstart; vx_start = vstart; vx_wv = 0; end
                    end else if (vins[6:0] == 7'h57 && (vf3_ == 3'd1 || vf3_ == 3'd5)) begin
                        // FP32 vector arithmetic (vec_ref.vfp)
                        vvf_ = vf3_ == 3'd5;
                        vfs_ = fsv_[63:32] == 32'hffffffff ? fsv_[31:0] : 32'h7fc00000;
                        frm_now = fcsr[7:5];
                        vkind = -1; vsrcs = vvf_ ? 1 : 2; vallb = 0; vnoov = 0;
                        if (!vok || vsew != 32 || frm_now > 3'd4 || vstart != 0) vbad = 1;
                        else case (vf6_)
                            6'h00, 6'h02, 6'h24, 6'h20, 6'h04, 6'h06, 6'h08, 6'h09, 6'h0a,
                            6'h28, 6'h29, 6'h2a, 6'h2b, 6'h2c, 6'h2d, 6'h2e, 6'h2f: vkind = 0;
                            6'h27, 6'h21: if (vvf_) vkind = 0;
                            6'h18, 6'h19, 6'h1b, 6'h1c: vkind = 1;
                            6'h1d, 6'h1f: if (vvf_) vkind = 1;
                            6'h17: if (vvf_) begin
                                       if (vvm_) begin if (vvs2_ == 0) begin vkind = 0; vsrcs = 0; end end
                                       else begin vkind = 0; vallb = 1; end
                                   end
                            6'h10: if (!vvf_) begin if (vrs1_ == 0 && vvm_) vkind = 3; end
                                   else if (vvs2_ == 0 && vvm_) vkind = 4;
                            6'h12: if (!vvf_ && (vrs1_ <= 5'd3 || vrs1_ == 5'd6 || vrs1_ == 5'd7)) begin vkind = 0; vsrcs = 1; end
                            6'h13: if (!vvf_ && (vrs1_ == 5'd0 || vrs1_ == 5'd16)) begin vkind = 0; vsrcs = 1; end
                            6'h0e: if (vvf_) begin vkind = 0; vnoov = 1; end
                            6'h0f: if (vvf_) vkind = 0;
                            6'h01, 6'h03, 6'h05, 6'h07: if (!vvf_) vkind = 2;
                            default: vkind = -1;
                        endcase
                        if (!vbad && vkind < 0) vbad = 1;
                        if (!vbad && vkind == 0) begin
                            // vector destination: group alignment, v0 with a mask, overlap
                            if (vrd_ % vlm != 0 || (!vvm_ && vrd_ == 0)) vbad = 1;
                            if (vsrcs >= 1 && vvs2_ % vlm != 0) vbad = 1;
                            if (vsrcs >= 2 && vrs1_ % vlm != 0) vbad = 1;
                            if (vnoov && vrd_ < vvs2_ + vlm && vvs2_ < vrd_ + vlm) vbad = 1;
                            if (!vbad && vl != 0) begin
                                vtv = 0;
                                for (vk = 0; vk < vemax_r; vk = vk + 1) if (vk < vl && (vallb || vvm_ || vbit(0, vk))) begin
                                    vtv[vk] = 1;
                                    if (vf6_ == 6'h17) vtmp[vk] = (vvm_ || vbit(0, vk)) ? vfs_ : vget(vvs2_, vk, 32);
                                    else if (vf6_ == 6'h0e) vtmp[vk] = vk == 0 ? vfs_ : vget(vvs2_, vk - 1, 32);
                                    else if (vf6_ == 6'h0f) vtmp[vk] = vk == vl - 1 ? vfs_ : vget(vvs2_, vk + 1, 32);
                                    else begin
                                        vfr_ = v_fe(vf6_, vrs1_, vget(vvs2_, vk, 32), vvf_ ? vfs_ : vget(vrs1_, vk, 32), vget(vrd_, vk, 32), frm_now);
                                        vtmp[vk] = vfr_[31:0]; vx_fl = vx_fl | vfr_[36:32];
                                    end
                                end
                                for (vk = 0; vk < vemax_r; vk = vk + 1) begin
                                    if (vk < vl) begin
                                        if (vtv[vk]) vput(vrd_, vk, 32, {32'b0, vtmp[vk]});
                                        else if (vtype[7]) vput(vrd_, vk, 32, 64'hffffffff);
                                    end else if (vk < vlm * VLEN / 32 && vtype[6]) vput(vrd_, vk, 32, 64'hffffffff);
                                end
                                vr_vb = vrd_; vr_vn = vlm;
                            end
                        end
                        if (!vbad && vkind == 1) begin
                            // mask destination
                            if (vvs2_ % vlm != 0 || (vsrcs >= 2 && vrs1_ % vlm != 0)) vbad = 1;
                            if (vlm > 1 && vrd_ != vvs2_ && vrd_ >= vvs2_ && vrd_ < vvs2_ + vlm) vbad = 1;
                            if (vsrcs >= 2 && vlm > 1 && vrd_ != vrs1_ && vrd_ >= vrs1_ && vrd_ < vrs1_ + vlm) vbad = 1;
                            if (!vbad && vl != 0) begin
                                vtv = 0;
                                for (vk = 0; vk < vemax_r; vk = vk + 1) if (vk < vl && (vvm_ || vbit(0, vk))) begin
                                    vfr_ = v_fe(vf6_, vrs1_, vget(vvs2_, vk, 32), vvf_ ? vfs_ : vget(vrs1_, vk, 32), 32'b0, frm_now);
                                    vtv[vk] = 1; vtmp[vk] = {31'b0, vfr_[0]}; vx_fl = vx_fl | vfr_[36:32];
                                end
                                for (vk = 0; vk < vlen_r; vk = vk + 1) begin
                                    if (vk < vl) begin
                                        if (vk < VE_MAX && vtv[vk]) vreg[vrd_][vk] = vtmp[vk][0];
                                        else if (vtype[7]) vreg[vrd_][vk] = 1'b1;
                                    end else vreg[vrd_][vk] = 1'b1;
                                end
                                vr_vb = vrd_; vr_vn = 1;
                            end
                        end
                        if (!vbad && vkind == 2) begin
                            // reductions: vd[0] = op(vs1[0], active elements of vs2) (contract section 5)
                            if (vvs2_ % vlm != 0) vbad = 1;
                            else if (vl != 0) begin
                                vin_ = vget(vrs1_, 0, 32); vmask_any = 0;
                                for (vk = 0; vk < vemax_r; vk = vk + 1) begin
                                    vtv[vk] = vk < vl && (vvm_ || vbit(0, vk));
                                    vtmp[vk] = vget(vvs2_, vk, 32);
                                    if (vtv[vk]) vmask_any = 1;
                                end
                                if (vmask_any) begin
                                    if (vf6_ == 6'h01) begin
                                        // vfredusum: the fixed pairwise tree on element indices
                                        for (vw = 1; vw < vemax_r; vw = vw * 2)
                                            for (vlo = 0; vlo + vw < vemax_r; vlo = vlo + 2 * vw) begin
                                                if (!vtv[vlo]) begin vtv[vlo] = vtv[vlo + vw]; vtmp[vlo] = vtmp[vlo + vw]; end
                                                else if (vtv[vlo + vw]) begin
                                                    vfr_ = v_fe(6'h00, 5'd0, vtmp[vlo], vtmp[vlo + vw], 32'b0, frm_now);
                                                    vtmp[vlo] = vfr_[31:0]; vx_fl = vx_fl | vfr_[36:32];
                                                end
                                            end
                                        vfr_ = v_fe(6'h00, 5'd0, vin_, vtmp[0], 32'b0, frm_now);
                                        vin_ = vfr_[31:0]; vx_fl = vx_fl | vfr_[36:32];
                                    end else begin
                                        for (vk = 0; vk < vemax_r; vk = vk + 1) if (vtv[vk]) begin
                                            vfr_ = v_fe(vf6_ == 6'h03 ? 6'h00 : vf6_ == 6'h05 ? 6'h04 : 6'h06, 5'd0, vin_, vtmp[vk], 32'b0, frm_now);
                                            vin_ = vfr_[31:0]; vx_fl = vx_fl | vfr_[36:32];
                                        end
                                    end
                                end
                                vput(vrd_, 0, 32, {32'b0, vin_});
                                if (vtype[6]) for (vk = 1; vk < vlen_r / 32; vk = vk + 1) vput(vrd_, vk, 32, 64'hffffffff);
                                vr_vb = vrd_; vr_vn = 1;
                            end
                        end
                        if (!vbad && vkind == 3) begin vel = vget(vvs2_, 0, 32); vx_res = {32'hffffffff, vel[31:0]}; end   // vfmv.f.s
                        if (!vbad && vkind == 4 && vl != 0) begin                                       // vfmv.s.f
                            vput(vrd_, 0, 32, {32'b0, vfs_});
                            if (vtype[6]) for (vk = 1; vk < vlen_r / 32; vk = vk + 1) vput(vrd_, vk, 32, 64'hffffffff);
                            vr_vb = vrd_; vr_vn = 1;
                        end
                        vfin = !vbad;
                        vx_cnt = v_lat(vf6_, vrs1_, vl);
                    end else vbad = 1;                    // integer, mask-logical, permute: later steps
                    if (vbad) begin
                        vr_vn = 0; vr_cn = 0; vx_fl = 0; vx_st = 2'd0;
                        rb_done[e] = 1; rb_exc[e] = 1; rb_cause[e] = 2; rb_tval[e] = {32'b0, vins};
                    end else if (vfin) vx_st = 2'd2;
                end else if (vx_st == 2'd1) begin
                    // One memory element per clock, in element order.
                    vsz = vx_eewb;
                    vdone_el = 0;
                    // a store element's write completes this clock
                    if (!vx_load && vx_wv && bus_kind == 3 && mem_ready) begin
                        vx_wv = 0;
                        if (mem_error) begin vflt = 1; vcause = 7; vtval = vx_base + vx_i * vx_stride; end
                        else begin
                            // write-through effects of a retiring store (copied from retirement)
                            if (dc_line(vx_waddr) >= 0)
                                for (vk = 0; vk < 8; vk = vk + 1)
                                    if (vx_wstrb[vk]) dc_data[dc_di(dc_line(vx_waddr), vx_waddr)][8*vk +: 8] = vx_wdata[8*vk +: 8];
                            fi = vx_waddr[3 +: IC_INDEX];
                            if (ic_valid[fi] && ic_tag[fi] == vx_waddr[63 -: IC_TAG]) ic_valid[fi] = 0;
                            if (fb_valid && fb_beat[63:3] == vx_waddr[63:3])
                                for (vk = 0; vk < 8; vk = vk + 1) if (vx_wstrb[vk]) fb_data[8*vk +: 8] = vx_wdata[8*vk +: 8];
                            if (LB == 1 && SPLIT && mu_valid && mu_sent && mu_beat[63:3] == vx_waddr[63:3]) mu_stale = 1;
                            for (vk = 1; vk < PM_N; vk = vk + 1)
                                if (LB == 1 && SPLIT && pm_valid[vk] && pm_sent[vk] && pm_beat[vk][63:3] == vx_waddr[63:3]) pm_stale[vk] = 1;
                            // Line fills: the element's bytes merge into in-flight line reads (as a scalar store's).
                            if (LB > 1) for (vk = 0; vk < PM_N; vk = vk + 1)
                                if (vk == 0 ? (mu_valid && mu_sent && dl_ln(mu_beat) == dl_ln(vx_waddr)) :
                                              (pm_valid[vk] && pm_sent[vk] && dl_ln(pm_beat[vk]) == dl_ln(vx_waddr))) begin
                                    lk = (vx_waddr >> 3) % LB;
                                    for (b2 = 0; b2 < 8; b2 = b2 + 1)
                                        if (vx_wstrb[b2]) begin lb_data[vk][lk][8*b2 +: 8] = vx_wdata[8*b2 +: 8]; lb_wm[vk][lk][b2] = 1; end
                                end
                            vx_i = vx_i + 1;
                        end
                    end
                    if (!vflt && !vx_wv) begin
                        // skip inactive elements (not accessed, cannot fault)
                        while (vx_i < vx_evl && !(vx_whole || vx_mtail || vx_vm || vbit(0, vx_i))) vx_i = vx_i + 1;
                        if (vx_i >= vx_evl) vdone_el = 1;
                        else begin
                            vaddr = vx_base + vx_i * vx_stride;
                            if ((vaddr & (vsz - 1)) != 0) begin vflt = 1; vcause = vx_load ? 4 : 6; vtval = vaddr; end
                            else if (vx_load) begin
                                vhit = dc_line(vaddr) >= 0 || (fb_valid && fb_beat[63:3] == vaddr[63:3]);
                                if (vhit) begin
                                    vbeat_d = dc_line(vaddr) >= 0 ? dc_data[dc_di(dc_line(vaddr), vaddr)] : fb_data;
                                    vel = vbeat_d >> {vaddr[2:0], 3'b000};
                                    vput(vx_vd, vx_i, 8 * vsz, vel);
                                    if (fb_lock && fb_owner == e) fb_lock = 0;
                                    if (mu_owner_v && mu_owner == e) mu_owner_v = 0;
                                    vx_i = vx_i + 1;
                                end else if (mu_errv && mu_err_owner == e && mu_err_beat[63:3] == vaddr[63:3]) begin
                                    mu_errv = 0;
                                    vflt = 1; vcause = 5; vtval = vaddr;
                                end else if (!mu_valid && !fb_lock) begin
                                    // the oldest instruction's miss: entry 0
                                    mu_valid = 1; mu_beat = {vaddr[63:3], 3'b000}; mu_errv = 0; mu_owner = e; mu_owner_v = 1; mu_sent = 0; mu_stale = 0;
                                end
                            end else begin
                                vel = vget(vx_vd, vx_i, 8 * vsz);
                                vx_wv = 1; vx_waddr = {vaddr[63:3], 3'b000}; vx_wdata = vel << {vaddr[2:0], 3'b000};
                                vx_wstrb = (vsz == 1 ? 8'h01 : vsz == 2 ? 8'h03 : vsz == 4 ? 8'h0f : 8'hff) << vaddr[2:0];
                            end
                        end
                    end
                    if (vflt && vx_ff && vx_i > 0) begin
                        // fault-only-first: vl becomes the faulting index, no trap
                        vflt = 0; vl = vx_i; vx_evl = vx_i; vrec_c(12'hc20, vl); vdone_el = 1;
                    end
                    if (vflt) begin
                        // element-precise trap: completed elements stay, vstart = the faulting index
                        if (vx_load && vx_i > vx_start) begin vr_vb = vx_vd; vr_vn = vx_regs; end
                        if (vx_i != 0) begin vstart = vx_i; vrec_c(12'h008, vstart); end
                        rb_done[e] = 1; rb_exc[e] = 1; rb_cause[e] = {59'b0, vcause}; rb_tval[e] = vtval; vx_st = 2'd0;
                    end else if (vdone_el) begin
                        if (vx_start != 0) vrec_c(12'h008, 64'b0);
                        vstart = 0;
                        if (vx_load && (vx_start < vx_evl || vx_whole)) begin
                            // inactive body elements (mask agnostic) and the tail
                            for (vk = vx_start; vk < vx_evl; vk = vk + 1)
                                if (!(vx_whole || vx_mtail || vx_vm || vbit(0, vk)) && vtype[7]) vput(vx_vd, vk, 8 * vsz, ~64'd0);
                            if (vx_mtail) for (vk = vx_evl; vk < vlen_r / 8; vk = vk + 1) vput(vx_vd, vk, 8, 64'hff);
                            else if (!vx_whole && vtype[6]) for (vk = vx_evl; vk < vx_regs * VLEN / (8 * vsz); vk = vk + 1) vput(vx_vd, vk, 8 * vsz, ~64'd0);
                            vr_vb = vx_vd; vr_vn = vx_regs;
                        end
                        rb_done[e] = 1; rb_exc[e] = 0; rb_fflags[e] = 0; vx_st = 2'd0;
                    end
                end else begin
                    // finishing: the result latency, then the scalar destination
                    if (vx_cnt > 1) vx_cnt = vx_cnt - 1;
                    else begin
                        if (rb_writes[e]) begin
                            prf_late[rb_pdst[e]] = !prf_ready[rb_pdst[e]]; prf[rb_pdst[e]] = vx_res; prf_written[rb_pdst[e]] = 1; prf_ready[rb_pdst[e]] = 1;
                        end
                        rb_value[e] = vx_res; rb_done[e] = 1; rb_exc[e] = 0; rb_fflags[e] = vx_fl; vx_st = 2'd0;
                    end
                end
            end
`endif

            // ---- rename and dispatch (not in a clock that recovered)
            d_redirect = 0; n_ren = 0;
            if (!rflush && !mp_any) begin
                stop = 0;
                nfi = 0; nfp = 0; ui = 0; up = 0; cf_lvl = 0; n_cf = 0; n_br = 0;
                for (k = 0; k < IQ_N; k = k + 1) if (!iq_valid[k] && nfi < FW) begin fiq[nfi] = k; nfi = nfi + 1; end
                for (k = 1; k < PRF_N; k = k + 1) if (free_mask[k] && nfp < FW) begin fpl[nfp] = k; nfp = nfp + 1; end
                for (s = 0; s < FW; s = s + 1) if (!stop) begin
`ifdef RV64_OOO_V
                    if (s >= q_count || (FE_DEPTH > 0 && q_t[(q_head + s) % Q_N] >= fe_clk) || (FPU != 0 && csr_busy) || v_busy) stop = 1;
`else
                    if (s >= q_count || (FE_DEPTH > 0 && q_t[(q_head + s) % Q_N] >= fe_clk) || (FPU != 0 && csr_busy)) stop = 1;
`endif
                    else begin
                        j = (q_head + s) % Q_N;
                        wi = q_insn[j]; wpc = q_pc[j]; isfault = q_fault[j];
                        op = wi[6:0]; rd_ = wi[11:7]; rs1_ = wi[19:15]; rs2_ = wi[24:20]; f3_ = wi[14:12];
                        fdc_ = (FPU != 0 && !isfault) ? fp_decode(wi) : 21'b0;
                        fpop_ = fdc_[0] && fdc_[2:1] == 2'd0; fpld_ = fdc_[0] && fdc_[2:1] == 2'd1; fpst_ = fdc_[0] && fdc_[2:1] == 2'd2;
                        fs1_ = fdc_[0] && fdc_[14]; u2fp_ = fdc_[0] && fdc_[15]; fs2_ = fdc_[0] && fdc_[16]; uses3_ = fdc_[0] && fdc_[17];
                        fpw_ = fdc_[0] && fdc_[18]; fdst_ = fdc_[0] && fdc_[19];
                        if (FPU != 0) begin ard_ = {fdst_, rd_}; ars1_ = {fs1_, rs1_}; ars2_ = {fs2_, rs2_}; ars3_ = {1'b1, wi[31:27]}; end
                        else begin ard_ = rd_; ars1_ = rs1_; ars2_ = rs2_; ars3_ = 0; end
                        csr_ = FPU != 0 && !isfault && op == 7'h73 && f3_ != 0 && f3_ != 3'd4 && wi[31:22] == 0 && wi[21:20] != 0;
`ifdef RV64_OOO_V
                        isv_ = !isfault && (op == 7'h57 || ((op == 7'h07 || op == 7'h27) && (f3_ == 3'd0 || f3_ >= 3'd5)) ||
                               (op == 7'h73 && f3_ != 0 && f3_ != 3'd4 && (wi[31:20] == 12'h008 || wi[31:20] == 12'h009 ||
                                wi[31:20] == 12'h00a || wi[31:20] == 12'h00f || wi[31:20] == 12'hc20 || wi[31:20] == 12'hc21 || wi[31:20] == 12'hc22)));
                        vfd_ = isv_ && op == 7'h57 && f3_ == 3'd1 && wi[31:26] == 6'h10;
                        if (isv_) ard_ = {vfd_, rd_};
`endif
                        writes_ = !isfault && ard_ != 0 && (fpw_ || csr_ || op == 7'h37 || op == 7'h17 || op == 7'h6f || op == 7'h67 ||
                                  op == 7'h13 || op == 7'h1b || op == 7'h33 || op == 7'h3b || op == 7'h03);
`ifdef RV64_OOO_V
                        if (isv_) writes_ = ard_ != 0 && ((op == 7'h57 && f3_ == 3'd7) || op == 7'h73 || vfd_);
`endif
                        uses1_ = !(op == 7'h37 || op == 7'h17 || op == 7'h6f);
                        uses2_ = op == 7'h33 || op == 7'h3b || op == 7'h63 || op == 7'h23 || u2fp_;
                        // Prediction check (what D did in the earlier cores).
                        tgt = wpc + (op == 7'h6f ? {{43{wi[31]}},wi[31],wi[19:12],wi[20],wi[30:21],1'b0}
                                                 : {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0});
                        tkp = (op == 7'h6f || (op == 7'h63 && q_fpred[j])) && tgt[1:0] == 0 && !isfault;
                        npc = wpc + 64'd4;
                        d_want = isfault ? q_pred[j] : op == 7'h67 ? q_pred[j] : tkp ? tgt : npc;
                        ps1_ = (uses1_ && ars1_ != 0) ? rat[ars1_] : 0;
                        ps2_ = (uses2_ && ars2_ != 0) ? rat[ars2_] : 0;
                        o1_ = (uses1_ && ars1_ != 0) ? rat_off[ars1_] : 64'b0;
                        o2_ = (uses2_ && ars2_ != 0) ? rat_off[ars2_] : 64'b0;
                        ps3_ = (FPU != 0 && uses3_) ? rat[ars3_] : 0;   // before the destination map update (rd may equal rs3)
                        // Folding: finished at rename, no issue-queue entry, no port; a
                        // writer maps rd to (ep_, eoff) without a new physical register.
                        elim_ = 0; done_ = 0; ep_ = 0; eoff = 0;
                        jt_ = (o1_ + {{52{wi[31]}},wi[31:20]}) & ~64'd1;
                        if (FOLD && !isfault) begin
                            if (op == 7'h13 && f3_ == 0) begin
                                done_ = 1; elim_ = writes_; ep_ = ps1_; eoff = o1_ + {{52{wi[31]}},wi[31:20]};
                            end else if (op == 7'h37) begin
                                done_ = 1; elim_ = writes_; eoff = {{32{wi[31]}},wi[31:12],12'b0};
                            end else if (op == 7'h17) begin
                                done_ = 1; elim_ = writes_; eoff = wpc + {{32{wi[31]}},wi[31:12],12'b0};
                            end else if (op == 7'h6f && tkp) begin
                                done_ = 1; elim_ = writes_; eoff = npc;
                            end else if (op == 7'h67 && f3_ == 0 && ps1_ == 0 && jt_[1:0] == 0) begin
                                // Constant base: the target is known here.
                                done_ = 1; elim_ = writes_; eoff = npc; d_want = jt_;
                            end
                        end
                        if (csr_) begin
                            csr_fcsr = fcsr;
                            csr_old = wi[21:20] == 2'd1 ? {59'b0, fcsr[4:0]} : wi[21:20] == 2'd2 ? {61'b0, fcsr[7:5]} : {56'b0, fcsr};
                            csr_src = f3_[2] ? {59'b0, rs1_} : (rs1_ == 0 ? 64'b0 : prf[rat[rs1_]] + rat_off[rs1_]);
                            csr_new = f3_[1:0] == 2'd1 ? csr_src : f3_[1:0] == 2'd2 ? (csr_old | csr_src) : (csr_old & ~csr_src);
                            if (wi[21:20] == 2'd1) csr_fcsr[4:0] = csr_new[4:0];
                            else if (wi[21:20] == 2'd2) csr_fcsr[7:5] = csr_new[2:0];
                            else csr_fcsr = csr_new[7:0];
                            done_ = 1; elim_ = writes_; ep_ = 0; eoff = csr_old;
                        end
                        cf_now = 0; br_now = 0; bt_ = 0;
                        // Every source a constant: a simple op is computed here.
                        if (CFOLD != 0 && !isfault && !done_ && writes_ &&
                            (op == 7'h13 || op == 7'h1b || op == 7'h33 || op == 7'h3b) &&
                            !((op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01) &&
                            ps1_ == 0 && (!uses2_ || ps2_ == 0) &&
                            (CFOLD > 1 || (!cf_lvl[ars1_] && !(uses2_ && cf_lvl[ars2_])))) begin
                            csa_ = simple_alu(wi, o1_, o2_, wpc);
                            if (csa_[66]) begin
                                done_ = 1; elim_ = 1; ep_ = 0; eoff = csa_[63:0]; cf_now = 1; n_cf = n_cf + 1;
                            end
                        end
                        // A branch whose outcome is known: same register (equality) or constants.
                        if (BRREN != 0 && !isfault && op == 7'h63 && f3_ != 3'd2 && f3_ != 3'd3 &&
                            ps1_ == ps2_ && (ps1_ == 0 || f3_[2:1] == 2'b00)) begin
                            case (f3_)
                                3'd0: bt_ = o1_ == o2_;
                                3'd1: bt_ = o1_ != o2_;
                                3'd4: bt_ = $signed(o1_) < $signed(o2_);
                                3'd5: bt_ = $signed(o1_) >= $signed(o2_);
                                3'd6: bt_ = o1_ < o2_;
                                default: bt_ = o1_ >= o2_;
                            endcase
                            if (!bt_ || tgt[1:0] == 0) begin
                                done_ = 1; br_now = 1; d_want = bt_ ? tgt : npc; n_br = n_br + 1;
                            end
                        end
                        // Resources: ROB entry, issue-queue entry, physical register.
                        slot_ok = ui < nfi; slot = fiq[ui % FW];
                        fp_ok = up < nfp; fp = fpl[up % FW];
`ifdef RV64_OOO_V
                        if (((csr_ || isv_) && (s != 0 || rb_count_new != 0)) || rb_count_new >= ROB_N || (!isfault && !done_ && !isv_ && !slot_ok) || (writes_ && !elim_ && !fp_ok)) stop = 1;
`else
                        if ((csr_ && (s != 0 || rb_count_new != 0)) || rb_count_new >= ROB_N || (!isfault && !done_ && !slot_ok) || (writes_ && !elim_ && !fp_ok)) stop = 1;
`endif
                        else begin
                            sa = simple_alu(wi, 64'b0, 64'b0, 64'b0);
                            cls_ = (op == 7'h03 || fpld_) ? C_LD : (op == 7'h23 || fpst_) ? C_ST : fpop_ ? C_FP : sa[66] ? C_ALU : C_FULL;
                            e = rb_tail;
                            rb_live[e] = 1; rb_done[e] = isfault; rb_exc[e] = isfault;
                            rb_cause[e] = q_fmis[j] ? 64'd0 : 64'd1; rb_tval[e] = wpc;
                            rb_pc[e] = wpc; rb_insn[e] = wi; rb_next[e] = d_want; rb_rd[e] = ard_; rb_writes[e] = writes_; rb_fflags[e] = 0; rb_csrw[e] = csr_ && (f3_[1:0] == 2'd1 || rs1_ != 0); rb_csrv[e] = csr_fcsr; rb_fsw[e] = fpst_ && f3_ == 3'd2;
                            rb_store[e] = (op == 7'h23 || fpst_) && !isfault; rb_load[e] = (op == 7'h03 || fpld_) && !isfault;
                            rb_fencei[e] = 0; rb_ctl[e] = 0; rb_sta[e] = 0; rb_viol[e] = 0; rb_ldv[e] = 0; rb_ans[e] = 0; rb_wstrb[e] = 0; rb_taken[e] = 0; rb_ret[e] = 0;
                            rb_bhit[e] = q_bhit[j]; rb_bctr[e] = q_bctr[j]; rb_rsp[e] = q_rsp[j]; rb_rtos[e] = q_rtos[j]; rb_gh[e] = q_gh[j]; rb_tp[e] = q_tp[j];
                            if (IT_N != 0) begin rb_ph[e] = q_ph[j]; rb_ipt[e] = q_pred[j]; end
                            rb_li[e] = q_li[j]; rb_lp[e] = op == 7'h63 && !isfault; rb_ld[e] = tkp;
                            rb_fence[e] = op == 7'h0f && f3_ == 3'd0 && !isfault;
`ifdef RV64_OOO_V
                            rb_vec[e] = isv_; rb_vref[e] = isv_ && op == 7'h27;
`endif
                            rb_opdst[e] = rat[ard_]; rb_pdst[e] = writes_ ? (elim_ ? ep_ : fp) : 0;
                            rb_elim[e] = elim_; rb_off[e] = eoff;
                            if (done_) begin
                                rb_done[e] = 1; rb_exc[e] = 0;
                                if (op == 7'h6f || op == 7'h67) begin
                                    rb_ctl[e] = 1; rb_taken[e] = 1;
                                    rb_ret[e] = op == 7'h67 && rd_ == 0 && (rs1_ == 1 || rs1_ == 5);
                                end else if (op == 7'h63) begin
                                    rb_ctl[e] = 1; rb_taken[e] = bt_;
                                end
                            end
                            if (writes_) cf_lvl[ard_] = cf_now;
                            if (writes_ && elim_) begin
                                rat[ard_] = ep_; rat_off[ard_] = eoff;
                                if (ep_ != 0) refcnt[ep_] = refcnt[ep_] + 1;
                            end else if (writes_) begin
                                rat[ard_] = fp; rat_off[ard_] = 0; refcnt[fp] = 1;
                                free_mask[fp] = 0; prf_ready[fp] = 0; prf_written[fp] = 0;
                            end
                            vpi = wpc[2 +: VP_BITS];
                            rb_vp[e] = 0; rb_vpbad[e] = 0;
                            if (writes_ && (op == 7'h03 || ((op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01)) &&
                                vp_valid[vpi] && vp_tag[vpi] == wpc[2+VP_BITS +: VP_TAG] && vp_conf[vpi] >= vp_thr(vp_strk[vpi])) begin
                                rb_vp[e] = 1; rb_vpv[e] = vp_val[vpi];
                                prf[fp] = vp_val[vpi]; prf_written[fp] = 1; prf_ready[fp] = 1; prf_late[fp] = 1;
                            end
                            if (op == 7'h63 || op == 7'h67) for (i = 0; i < NAR; i = i + 1) begin snap[e][i] = rat[i]; snap_off[e][i] = rat_off[i]; end
`ifdef RV64_OOO_V
                            if (!isfault && !done_ && !isv_) begin
`else
                            if (!isfault && !done_) begin
`endif
                                iq_valid[slot] = 1; iq_issued[slot] = 0; iq_slp[slot] = 0; iq_wany[slot] = 0; iq_cls[slot] = cls_; iq_rob[slot] = e;
                                iq_pc[slot] = wpc; iq_insn[slot] = wi; iq_ps1[slot] = ps1_; iq_ps2[slot] = ps2_;
                                iq_pdst[slot] = writes_ ? fp : 0; iq_writes[slot] = writes_;
                                iq_mdu[slot] = (op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01;
                                iq_pred[slot] = d_want; iq_ptaken[slot] = tkp; iq_alt[slot] = tkp ? npc : tgt;
                                iq_fz1[slot] = pv_ok && uses1_ && ars1_ == pv_rd && cls_ != C_FP;
                                iq_fz2[slot] = pv_ok && uses2_ && ars2_ == pv_rd && cls_ != C_ST && cls_ != C_FP;
                                iq_fzi[slot] = pv_insn; iq_fzpc[slot] = pv_pc; iq_fza[slot] = pv_a; iq_fzb[slot] = pv_b;
                                iq_off1[slot] = o1_; iq_off2[slot] = o2_;
                                iq_ps3[slot] = ps3_;
                                iq_fop[slot] = fdc_[7:3]; iq_fsz[slot] = fdc_[8]; iq_rm[slot] = fdc_[11:9]; iq_funit[slot] = fdc_[13:12];
                            end
                            cur_fz = pv_ok && cls_ != C_FP && ((uses1_ && ars1_ == pv_rd) || (uses2_ && ars2_ == pv_rd && cls_ != C_ST));
                            pv_ok = !isfault && cls_ == C_ALU && writes_ && !cur_fz && !done_ && o1_ == 0 && o2_ == 0;
                            pv_rd = ard_; pv_insn = wi; pv_pc = wpc; pv_a = ps1_; pv_b = ps2_;
                            rb_tail = rb_tail + 1; rb_count_new = rb_count_new + 1; n_ren = n_ren + 1;
`ifdef RV64_OOO_V
                            if (!isfault && !done_ && !isv_) ui = ui + 1;
`else
                            if (!isfault && !done_) ui = ui + 1;
`endif
                            if (writes_ && !elim_) up = up + 1;
                            if (csr_) begin csr_busy = 1; stop = 1; end
`ifdef RV64_OOO_V
                            if (isv_) begin v_busy = 1; stop = 1; end
`endif
                            if (d_want != q_pred[j] || (TG_N != 0 && op == 7'h63 && !isfault && (br_now ? bt_ : tkp) != q_fpred[j])) begin
                                d_redirect = 1; d_redirect_pc = d_want; d_redirect_sp = q_rsp[j]; d_redirect_tos = q_rtos[j];
                                d_redirect_gh = op == 7'h63 ? {q_gh[j][GH_L-2:0], br_now ? bt_ : tkp} : q_gh[j]; stop = 1;
                                d_redirect_ph = (IT_N != 0 && !isfault && is_ind(wi)) ? ph_upd(q_ph[j], d_want) : q_ph[j];
                            end
                        end
                    end
                end
                q_head = q_head + n_ren; q_count = q_count - n_ren;
                if (d_redirect) begin
                    q_head = 0; q_tail = 0; q_count = 0;
                    f_pc = d_redirect_pc; f_err = 0; f_hold = 0; ras_sp = d_redirect_sp; ras[ras_sp] = d_redirect_tos; f_gh = d_redirect_gh; if (IT_N != 0) f_ph = d_redirect_ph; if (bus_hold == 1) f_stale = 1;
                end
            end
            rb_count = rb_count_new;

            // ---- fetch: up to FW instructions from the cache, following up to TAKEN_MAX
            // predicted-taken transfers (since 0.10.1) and at most one call or return
            if (!rflush && (RC_FETCH != 0 || !mp_any) && !d_redirect && !f_hold) begin
                g_n = 0; g_next = f_pc; stop = 0; g_cr = 0;
                g_taken = 0; cur_sp = ras_sp; cur_gh = f_gh; g_cb = 0; cur_ph = f_ph; g_ij = 0;
                for (k = 0; k < RAS_N; k = k + 1) gras[k] = ras[k];
                if (f_pc[1:0] != 0 || f_err) begin
                    // A fetch fault becomes one instruction that traps if it retires.
                    g_pc[0] = f_pc; g_insn[0] = 0; g_pred[0] = f_pc + 64'd4; g_fp[0] = 0; g_bh[0] = 0; g_bc[0] = 0;
                    g_fault[0] = 1; g_fmis[0] = f_pc[1:0] != 0; g_n = 1; g_next = f_pc; stop = 1; g_sp[0] = ras_sp; g_tos[0] = ras[ras_sp]; g_gh[0] = f_gh; g_tp[0] = 8'h38; g_ph[0] = f_ph;
                end
                npc = f_pc;
                for (s = 0; s < FW; s = s + 1) if (!stop) begin
                    fi = npc[3 +: IC_INDEX];
                    wi = 0;
                    if (ic_valid[fi] && ic_tag[fi] == npc[63 -: IC_TAG]) wi = npc[2] ? ic_data[fi][63:32] : ic_data[fi][31:0];
                    op = wi[6:0];
                    isctl = op == 7'h6f || (op == 7'h67 && wi[14:12] == 0);
                    ok = isctl && (wi[11:7] == 1 || wi[11:7] == 5);                     // a call
                    hit = op == 7'h67 && wi[14:12] == 0 && wi[11:7] == 0 && (wi[19:15] == 1 || wi[19:15] == 5);  // a return
                    if (!(ic_valid[fi] && ic_tag[fi] == npc[63 -: IC_TAG]) || (RC_FETCH == 1 && mp_any && npc[63:3] != f_pc[63:3])) stop = 1;
                    else if ((ok || hit) && g_cr >= CR_MAX) stop = 1;     // CR_MAX calls or returns per group
                    else if (TG_N != 0 && op == 7'h63 && g_cb >= TG_PG) stop = 1;   // TG_PG conditional branches per group
                    else if (IT_N != 0 && is_ind(wi) && g_ij >= IT_PG) stop = 1;     // IT_PG indirect lookups per group
                    else begin
                        bi = npc[2 +: BTB_BITS];
                        fdone = btb_valid[bi] && btb_tag[bi] == npc[2+BTB_BITS +: BTB_TAG] &&
                                (op == 7'h63 || op == 7'h6f || op == 7'h67);   // predecode: control transfers only
                        tkp = fdone && (btb_ret[bi] || btb_ctr[bi][1]);
                        tgt = btb_ret[bi] ? ((gras[cur_sp] + (op == 7'h67 ? {{52{wi[31]}},wi[31:20]} : 64'd0)) & ~64'd1)
                                          : btb_dec(npc, btb_target[bi]);
                        g_ras_pop_sp = cur_sp;
                        g_lpu = 0; g_li[s] = 0; g_lpc = 0;
                        if (op == 7'h63) begin
                            g_lpi = npc[2 +: LP_BITS];
                            if (lp_valid[g_lpi] && lp_tag[g_lpi] == npc[2+LP_BITS +: LP_TAG]) begin
                                // Iteration number: after the youngest earlier instance in flight.
                                lp_found = 0; lp_it = lp_ret[g_lpi];
                                for (k = 0; k < ROB_N; k = k + 1) begin
                                    e = rb_head + k[ROB_B-1:0];
                                    if (k < rb_count && rb_lp[e] && rb_pc[e] == npc) begin
                                        lp_d = (rb_done[e] && rb_ctl[e]) ? rb_taken[e] : rb_ld[e];
                                        lp_it = lp_d == lp_dir[g_lpi] ? (rb_li[e] == 255 ? 8'd255 : rb_li[e] + 8'd1) : 8'd0;
                                    end
                                end
                                for (k = 0; k < q_count; k = k + 1) begin
                                    qj = (q_head + k) % Q_N;
                                    if (q_lp_c[qj] && q_pc[qj] == npc)
                                        lp_it = q_ld[qj] == lp_dir[g_lpi] ? (q_li[qj] == 255 ? 8'd255 : q_li[qj] + 8'd1) : 8'd0;
                                end
                                for (k = 0; k < FW; k = k + 1)
                                    if (k < s && g_pc[k] == npc && g_insn[k][6:0] == 7'h63)
                                        lp_it = g_fp[k] == lp_dir[g_lpi] ? (g_li[k] == 255 ? 8'd255 : g_li[k] + 8'd1) : 8'd0;
                                g_li[s] = lp_it;
                                if (lp_conf[g_lpi] >= 2 && lp_trip[g_lpi] != 0 && lp_trip[g_lpi] != 255) begin
                                    g_lpu = 1; g_lpc = 1;
                                    g_lpd = lp_it < lp_trip[g_lpi] ? lp_dir[g_lpi] : !lp_dir[g_lpi];
                                    tkp = g_lpd;
                                    tgt = npc + {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0};
                                end else if (lp_trip[g_lpi] == 0 && lp_ret[g_lpi] >= 4) begin
                                    // Gone one way at least 4 times and never exited: that way.
                                    g_lpu = 1; g_lpd = lp_dir[g_lpi]; tkp = g_lpd;
                                    tgt = npc + {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0};
                                end
                            end
                        end
                        g_lpmask[s] = g_lpu;
                        // Predecode: fetch holds the instruction, so a direct jump or call
                        // goes to its target, a return to the return stack, and a
                        // conditional branch missing in the BTB is taken when backward.
                        if (op == 7'h6f) begin
                            tkp = 1; tgt = npc + {{43{wi[31]}},wi[31],wi[19:12],wi[20],wi[30:21],1'b0};
                        end else if (hit) begin
                            tkp = 1; tgt = (gras[g_ras_pop_sp] + {{52{wi[31]}},wi[31:20]}) & ~64'd1;   // ra + imm
                        end else if (op == 7'h63 && !g_lpu && !fdone) begin
                            tkp = wi[31]; tgt = npc + {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0};
                        end
                        // Indirect target: the tagged tables over the BTB (a weak entry yields to a BTB entry
                        // that predicts a taken non-return target, the alternate training compares with).
                        g_ph[s] = cur_ph;
                        if (IT_N != 0 && is_ind(wi)) begin
                            it_r = it_look(npc, cur_ph); g_ij = g_ij + 1;
                            if (it_r[65] && !(it_r[64] && fdone && !btb_ret[bi] && btb_ctr[bi][1])) begin tkp = 1; tgt = it_r[63:0]; end
                        end
                        // Global history (frontend 12): the tagged tables over the base prediction.
                        g_gh[s] = cur_gh; g_tp[s] = {g_lpc, tkp, 6'b111000};
                        if (TG_N != 0 && op == 7'h63 && !g_lpc) begin
                            tg_r = tg_look(npc, cur_gh, tkp);
                            g_tp[s] = {1'b0, tkp, tg_r[5:0]};
                            if (tg_r[7]) begin
                                tkp = tg_r[6]; tgt = npc + {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0};
                            end
                        end
                        if (op == 7'h63) begin cur_gh = {cur_gh[GH_L-2:0], tkp}; g_cb = g_cb + 1; end
                        g_pc[s] = npc; g_insn[s] = wi; g_pred[s] = tkp ? tgt : npc + 64'd4;
                        if (IT_N != 0 && is_ind(wi)) cur_ph = ph_upd(cur_ph, g_pred[s]);
                        g_fp[s] = tkp; g_bh[s] = fdone; g_bc[s] = btb_ctr[bi]; g_fault[s] = 0; g_fmis[s] = 0;
                        g_n = s + 1;
                        if (ok) begin g_cr = g_cr + 1; cur_sp = cur_sp + 1; gras[cur_sp] = npc + 64'd4; end
                        else if (hit) begin g_cr = g_cr + 1; cur_sp = cur_sp - 1; end
                        g_sp[s] = cur_sp; g_tos[s] = gras[cur_sp];
                        g_next = g_pred[s];
                        if (tkp) begin
                            g_taken = g_taken + 1;
                            if (g_taken >= TAKEN_MAX || tgt[1:0] != 0) stop = 1;
                        end
                        npc = g_pred[s];
                    end
                end
                if (g_n != 0 && q_count + g_n <= Q_N) begin
                    for (s = 0; s < FW; s = s + 1) if (s < g_n) begin
                        j = (q_tail + s) % Q_N;
                        q_pc[j] = g_pc[s]; q_insn[j] = g_insn[s]; q_pred[j] = g_pred[s]; q_fpred[j] = g_fp[s];
                        q_bhit[j] = g_bh[s]; q_bctr[j] = g_bc[s]; q_fault[j] = g_fault[s]; q_fmis[j] = g_fmis[s];
                        q_rsp[j] = g_sp[s]; q_rtos[j] = g_tos[s]; q_gh[j] = g_gh[s]; q_tp[j] = g_tp[s]; q_ph[j] = g_ph[s]; q_t[j] = fe_clk + FE_DEPTH;
                        q_lp[j] = g_lpmask[s]; q_ld[j] = g_fp[s]; q_li[j] = g_li[s]; q_lp_c[j] = g_insn[s][6:0] == 7'h63 && !g_fault[s];
                    end
                    q_tail = q_tail + g_n; q_count = q_count + g_n;
                    ras_sp = cur_sp; f_gh = cur_gh; if (IT_N != 0) f_ph = cur_ph;
                    for (k = 0; k < RAS_N; k = k + 1) ras[k] = gras[k];
                    if (g_fault[0]) begin f_hold = 1; f_err = 0; end   // wait for a redirect after a fault
                    else f_pc = g_next;
                end
            end
            end

        end else begin
            // Halted (0.11.0): the retirements of the halting clock pulse once.
            retire_valid <= 0; retire2_valid <= 0; retire3_valid <= 0; rt_valid <= 0;
        end
    end
endmodule
