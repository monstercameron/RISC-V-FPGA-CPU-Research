// SPDX-License-Identifier: MIT
// Original CPU foundation, wide out-of-order implementation (architecture 0.16.0).
// RV64IM + B execution, serialized FENCE.I, terminal EEI. Same module name and
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
    // Data cache: 2-way set associative, DCACHE_BEATS 8-byte lines in all (memory 1).
    localparam integer DC_SETS = DCACHE_BEATS / 2;
    localparam integer DC_INDEX = $clog2(DC_SETS);   // set-index bits, may be 0
    localparam integer DC_TAG = 61 - DC_INDEX;
    generate if (ICACHE_BEATS < 2 || (ICACHE_BEATS & (ICACHE_BEATS - 1)) != 0) begin : bad_icache_size
        initial $fatal(1, "ICACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    generate if (DCACHE_BEATS < 2 || (DCACHE_BEATS & (DCACHE_BEATS - 1)) != 0) begin : bad_dcache_size
        initial $fatal(1, "DCACHE_BEATS must be a power of two of at least 2");
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
    localparam integer PRF_N = 32 + ROB_N;
    localparam integer P_B = 10;
    localparam integer IQ_N = 128;
    localparam integer IQ_B = 7;
    localparam integer Q_N = 64;
    localparam integer Q_B = 6;
    localparam integer N_ALU = 8;        // integer ports
    localparam integer N_BR = 4;         // of which these also take branches, system and M (3 until 0.14.6)
    localparam integer N_LD = 4;         // load ports (Zen 5: 4 loads per clock)
    localparam integer N_ST = 3;         // store-address ports (Lion Cove: 3)
    localparam integer NP = N_ALU + N_LD + N_ST;
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
    reg [P_B-1:0] rat [0:31];
    reg [P_B-1:0] rrat [0:31];
    reg [P_B-1:0] snap [0:ROB_N-1][0:31];   // rename map after each control transfer
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
    reg [4:0] rb_rd [0:ROB_N-1];
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
    reg [1:0] iq_cls [0:IQ_N-1];
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
    reg [1:0] ex_cls [0:NP-1];
    reg [ROB_B-1:0] ex_rob [0:NP-1];
    reg [63:0] ex_pc [0:NP-1];
    reg [63:0] ex_pred [0:NP-1];
    reg [63:0] ex_alt [0:NP-1];
    reg [31:0] ex_insn [0:NP-1];
    reg [P_B-1:0] ex_ps1 [0:NP-1];
    reg [P_B-1:0] ex_ps2 [0:NP-1];
    reg [P_B-1:0] ex_pdst [0:NP-1];
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
    reg [DCACHE_BEATS-1:0] dc_valid;
    reg [DC_TAG-1:0] dc_tag [0:DCACHE_BEATS-1];
    reg [63:0] dc_data [0:DCACHE_BEATS-1];
    // Line l is way l / DC_SETS of set l % DC_SETS. A fill replaces the way that was
    // not filled last in its set (for two ways, the older fill).
    reg [DC_SETS-1:0] dc_last;           // way of the set's most recent fill
    initial dc_last = 0;
    integer dc_l;
    function automatic integer dc_set(input [63:0] a);
        dc_set = (a >> 3) & (DC_SETS - 1);
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
    reg [4:0] pv_rd;
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
    reg [63:0] rat_off [0:31];
    // Written this clock without an earlier wakeup (multiply, divide, value prediction):
    // an offset consumer may not be selected in the next clock (OFF_LAT, Codex 1609-2).
    reg [PRF_N-1:0] prf_late;
    reg [63:0] rrat_off [0:31];
    reg [63:0] snap_off [0:ROB_N-1][0:31];
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
    reg [31:0] cf_lvl;                   // arch reg holds a constant computed this clock
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
    reg pf_v;                   // this clock's oldest younger miss (to allocate)
    reg [63:0] pc_beat [0:N_LD-1];   // this clock's younger-miss candidates
    reg [ROB_B-1:0] pc_age [0:N_LD-1];
    integer pc_n, pc_i;
    reg [63:0] pf_beat;
    reg [ROB_B-1:0] pf_age;
    reg pm_dup;
    integer pm_k, pm_free, pm_j;
    reg [3:0] hold_tag, bk_tag;
    reg sf_wait;                // a store write faulted while split reads were outstanding: no new
                                // requests; the trap is taken, with the latched store, once they return
    reg [63:0] sf_pc, sf_addr;

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
    wire [ROB_N-1:0] rb_ends = rb_fencei | rb_vpbad;
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
            integer sc_nb, sc_bud;
            stop = 0;
            sc_nb = 0; sc_bud = TQ_N - (tq_cnt > TG_RU ? tq_cnt - TG_RU : 0);
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
                end
            end
        end
    end
    wire [63:0] st_addr = rb_addr[st_idx];
    wire [63:0] st_wdata = (prf[rb_sps2[st_idx]] + rb_soff[st_idx]) << {st_addr[2:0],3'b000};
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
            in_flight = mu_valid && mu_beat[63:3] == a[63:3];
            for (q = 1; q < PM_N; q = q + 1) if (pm_valid[q] && pm_beat[q][63:3] == a[63:3]) in_flight = 1;
        end
    endfunction
    wire want_fetch = started && !halted && f_pc[1:0] == 0 && !f_beat_hit && !f_err && !f_hold && !h_exc && !sf_wait;
    // Priority: store write, the oldest load's miss, younger misses, fetch.
    wire [1:0] bus_kind = halted ? 2'd0 : bus_hold != 0 ? bus_hold : want_store ? 2'd3 : want_miss ? 2'd2 :
                          want_pm ? 2'd2 : want_fetch ? 2'd1 : 2'd0;
    assign mem_tag = bus_kind != 2 ? 4'd0 : bus_hold == 2 ? hold_tag : want_miss ? 4'd0 : pm_pick;
    assign mem_valid = !reset && bus_kind != 0;
    assign mem_instr = bus_kind == 1;
    assign mem_addr = bus_kind == 1 ? (bus_hold == 1 ? hold_addr : {f_pc[63:3],3'b000})
                    : bus_kind == 2 ? (bus_hold == 2 ? hold_addr : want_miss ? mu_beat : pm_beat[pm_pick]) : {st_addr[63:3],3'b000};
    assign mem_wdata = bus_kind == 3 ? st_wdata : 64'b0;
    assign mem_wstrb = bus_kind == 3 ? rb_wstrb[st_idx] : 8'b0;
    assign mem_addr2 = bus_kind == 3 && pair_now ? {st2_addr[63:3],3'b000} : 64'b0;
    assign mem_wdata2 = bus_kind == 3 && pair_now ? (prf[rb_sps2[st2_idx]] + rb_soff[st2_idx]) << {st2_addr[2:0],3'b000} : 64'b0;
    assign mem_wstrb2 = bus_kind == 3 && pair_now ? rb_wstrb[st2_idx] : 8'b0;
    wire x0v = bus_kind == 3 && pair_now && nx_now != 0, x1v = bus_kind == 3 && pair_now && nx_now == 2;
    assign mem_xaddr = {x1v ? {rb_addr[sx1_idx][63:3],3'b000} : 64'b0, x0v ? {rb_addr[sx0_idx][63:3],3'b000} : 64'b0};
    assign mem_xwdata = {x1v ? (prf[rb_sps2[sx1_idx]] + rb_soff[sx1_idx]) << {rb_addr[sx1_idx][2:0],3'b000} : 64'b0,
                         x0v ? (prf[rb_sps2[sx0_idx]] + rb_soff[sx0_idx]) << {rb_addr[sx0_idx][2:0],3'b000} : 64'b0};
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
    reg [P_B-1:0] trat [0:31];
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
    reg [1:0] cls_;
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
            mu_sent = 0; mu_stale = 0; pm_valid = 0; pm_sent = 0; pm_stale = 0; hold_tag = 0; sf_wait = 0;
            for (i = 0; i < PRF_N; i = i + 1) prf[i] = 0;
            prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}}; prf_late = 0;
            free_mask = {PRF_N{1'b1}}; for (i = 0; i < 32; i = i + 1) free_mask[i] = 0;
            for (i = 0; i < 32; i = i + 1) begin rat[i] = i; rrat[i] = i; rat_off[i] = 0; rrat_off[i] = 0; end
            for (i = 0; i < PRF_N; i = i + 1) refcnt[i] = i < 32 ? 1 : 0;
            rb_viol = 0; mdp_wait = 0; rb_live = 0; rb_done = 0; rb_head = 0; rb_tail = 0; rb_count = 0;
            iq_valid = 0; iq_issued = 0; ex_valid = 0; mq_valid = 0; dv_busy = 0; lw_valid = 0; rb_ans = 0; l0_v = 0; l0_p = 0; ld_lat_now = LD_LAT;
            ic_valid = 0; dc_valid = 0; btb_valid = 0; btb_ret = 0; ras_sp = 0; vp_valid = 0; lp_valid = 0; lp_dir = 0; tg_v = 0; tg_alt = 8; tg_age = 0; tg_ap = 0; f_gh = 0; r_gh = 0; tq_cnt = 0; tq_h = 0;
            for (i = 0; i < RAS_N; i = i + 1) ras[i] = 0;
            q_head = 0; q_tail = 0; q_count = 0;
            trap_valid <= 0; trap_pc <= 0; trap_cause <= 0; trap_tval <= 0;
            retire_valid <= 0; retire_pc <= 0; retire_insn <= 0; retire_rd <= 0; retire_data <= 0; retire_next_pc <= 0;
            retire2_valid <= 0; retire2_pc <= 0; retire2_insn <= 0; retire2_rd <= 0; retire2_data <= 0; retire2_next_pc <= 0;
            retire3_valid <= 0; retire3_pc <= 0; retire3_insn <= 0; retire3_rd <= 0; retire3_data <= 0; retire3_next_pc <= 0;
            rt_valid <= 0; rt_pc <= 0; rt_insn <= 0; rt_rd <= 0; rt_data <= 0; rt_next <= 0;
        end else if (!halted) begin
            retire_valid <= 0; retire2_valid <= 0; retire3_valid <= 0; rt_valid <= 0;
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
                    end else if (bus_kind == 2) begin
                        mu_valid = 0;
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
            if (SPLIT && rsp_valid) begin
                if (rsp_tag == 0) begin
                    if (mu_valid && mu_sent) begin
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
            chosen = 0; pick_v = 0; divtaken = 0;
            for (p = 0; p < NP; p = p + 1) begin
                bestv = 0; best = 0; best_age = 0;
                for (k = 0; k < IQ_N; k = k + 1) begin
                    a_age = iq_rob[k] - rb_head;
                    ok = iq_valid[k] && !iq_issued[k] && !chosen[k] && rdy1(k);
                    if (p < N_ALU) begin
                        ok = ok && rdy2(k) &&
                             (iq_cls[k] == C_ALU || (p < N_BR && iq_cls[k] == C_FULL &&
                              !(iq_mdu[k] && iq_insn[k][14] && (dv_busy || dv_pend || divtaken))));
                    end else if (p < N_ALU + N_LD) ok = ok && iq_cls[k] == C_LD && (!ou_valid || a_age < ou_age || !mdp_wait[mdp_i(iq_pc[k])]) && (!fo_valid || a_age < fo_age);
                    else ok = ok && iq_cls[k] == C_ST;
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
                end
            end
            prf_late = 0;

            // ---- branch-predictor training queue (frontend 12): TG_RU per clock, in order
            for (tq_k = 0; tq_k < TG_RU; tq_k = tq_k + 1) if (TG_N != 0 && tq_cnt != 0) begin
                tg_train(tq_pc[tq_h], tq_gh[tq_h], tq_b[tq_h][7:0], tq_b[tq_h][8]);
                tq_h = (tq_h + 1) % TQ_N; tq_cnt = tq_cnt - 1;
            end
            // ---- retirement window
            n_ret = 0; n_tq = 0; rflush = 0; trap_now = 0; stop = 0; rflush_pc = 0; rflush_ld = 0; rflush_e = 0; st1_seen = 0; smc = 0; st_last = 0; wb2v = 0; wb1 = 0; wb2 = 0; st_n = 0; wb3 = 0; wb4 = 0;
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
                    end else begin
                        n_ret = s + 1;
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
                rt_rd[5*s +: 5] <= rb_writes[e] ? rb_rd[e] : 5'd0; rt_data[64*s +: 64] <= v;
                rt_next[64*s +: 64] <= rb_next[e];
                if (s == 0) begin
                    retire_valid <= 1; retire_pc <= rb_pc[e]; retire_insn <= rb_insn[e];
                    retire_rd <= rb_writes[e] ? rb_rd[e] : 5'd0; retire_data <= v; retire_next_pc <= rb_next[e];
                end
                if (s == 1) begin
                    retire2_valid <= 1; retire2_pc <= rb_pc[e]; retire2_insn <= rb_insn[e];
                    retire2_rd <= rb_writes[e] ? rb_rd[e] : 5'd0; retire2_data <= v; retire2_next_pc <= rb_next[e];
                end
                if (s == 2) begin
                    retire3_valid <= 1; retire3_pc <= rb_pc[e]; retire3_insn <= rb_insn[e];
                    retire3_rd <= rb_writes[e] ? rb_rd[e] : 5'd0; retire3_data <= v; retire3_next_pc <= rb_next[e];
                end
                if (rb_writes[e]) begin
                    rrat[rb_rd[e]] = rb_pdst[e]; rrat_off[rb_rd[e]] = rb_elim[e] ? rb_off[e] : 64'b0;
                    if (rb_opdst[e] != 0) begin
                        refcnt[rb_opdst[e]] = refcnt[rb_opdst[e]] - 1;
                        if (refcnt[rb_opdst[e]] == 0) free_mask[rb_opdst[e]] = 1;
                    end
                end
                if (rb_writes[e] && (rb_load[e] || ((rb_insn[e][6:0] == 7'h33 || rb_insn[e][6:0] == 7'h3b) && rb_insn[e][31:25] == 7'h01))) begin
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
                    r_wd = (prf[rb_sps2[e]] + rb_soff[e]) << {rb_addr[e][2:0],3'b000};
                    fi = rb_addr[e][3 +: IC_INDEX];
                    if (dc_line(rb_addr[e]) >= 0)
                        for (k = 0; k < 8; k = k + 1)
                            if (rb_wstrb[e][k]) dc_data[dc_line(rb_addr[e])][8*k +: 8] = r_wd[8*k +: 8];
                    if (ic_valid[fi] && ic_tag[fi] == rb_addr[e][63 -: IC_TAG]) ic_valid[fi] = 0;
                    if (fb_valid && fb_beat[63:3] == rb_addr[e][63:3])
                        for (k = 0; k < 8; k = k + 1) if (rb_wstrb[e][k]) fb_data[8*k +: 8] = r_wd[8*k +: 8];
                    if (SPLIT && mu_valid && mu_sent && mu_beat[63:3] == rb_addr[e][63:3]) mu_stale = 1;
                    for (k = 1; k < PM_N; k = k + 1)
                        if (SPLIT && pm_valid[k] && pm_sent[k] && pm_beat[k][63:3] == rb_addr[e][63:3]) pm_stale[k] = 1;
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
            miss_v = 0; miss_beat = 0; miss_age = 0; pf_v = 0; pf_beat = 0; pf_age = 0; pc_n = 0;
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
                                lw = (prf[rb_sps2[e]] + rb_soff[e]) << {rb_addr[e][2:0],3'b000};
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
                            lw = dc_hit_ ? dc_data[dc_line(ea)] : fb_data;
                            for (b2 = 0; b2 < 8; b2 = b2 + 1) if (fwd_mask[b2]) lw[8*b2 +: 8] = fwd_data[8*b2 +: 8];
                            v = load_align(lw, ea[2:0], f3_); fdone = 1;
                        end else begin
                            // Stores cover every byte but the beat has not been read: the value
                            // goes to consumers now, and the load finishes after the read.
                            if (fwd_mask == bytes_ && ex_writes[p]) begin
                                prf[ex_pdst[p]] = load_align(fwd_data, ea[2:0], f3_);
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
                end else begin
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
            if (SPLIT && pf_v && !(mu_valid && mu_beat[63:3] == pf_beat[63:3])) begin
                pm_dup = 0; pm_free = 0;
                for (pm_k = PM_N - 1; pm_k >= 1; pm_k = pm_k - 1) begin
                    if (pm_valid[pm_k] && pm_beat[pm_k][63:3] == pf_beat[63:3]) pm_dup = 1;
                    if (!pm_valid[pm_k]) pm_free = pm_k;
                end
                if (!pm_dup && pm_free != 0) begin
                    pm_valid[pm_free] = 1; pm_sent[pm_free] = 0; pm_stale[pm_free] = 0; pm_beat[pm_free] = pf_beat;
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
                    (iq_cls[k] == C_LD || iq_cls[k] == C_ST || rdy2(k))) begin
                    ex_valid[p] = 1; ex_iq[p] = k; ex_cls[p] = iq_cls[k]; ex_rob[p] = iq_rob[k]; ex_pc[p] = iq_pc[k];
                    ex_insn[p] = iq_insn[k]; ex_ps1[p] = iq_ps1[k]; ex_ps2[p] = iq_ps2[k]; ex_pdst[p] = iq_pdst[k];
                    ex_fz1[p] = iq_fz1[k]; ex_fz2[p] = iq_fz2[k]; ex_fzi[p] = iq_fzi[k]; ex_fzpc[p] = iq_fzpc[k];
                    ex_fza[p] = iq_fza[k]; ex_fzb[p] = iq_fzb[k]; ex_off1[p] = iq_off1[k]; ex_off2[p] = iq_off2[k];
                    ex_writes[p] = iq_writes[k]; ex_pred[p] = iq_pred[k]; ex_alt[p] = iq_alt[k]; ex_ptaken[p] = iq_ptaken[k];
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
            if (rflush) begin
                squash_after(n_ret[ROB_B-1:0] - 1);
                for (i = 0; i < 32; i = i + 1) begin rat[i] = rrat[i]; rat_off[i] = rrat_off[i]; end
                free_mask = {PRF_N{1'b1}};
                for (i = 0; i < PRF_N; i = i + 1) refcnt[i] = 0;
                for (i = 0; i < 32; i = i + 1) begin free_mask[rrat[i]] = 0; refcnt[rrat[i]] = refcnt[rrat[i]] + 1; end
                prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}}; prf_late = 0;
                ex_valid = 0; iq_valid = 0; iq_issued = 0; fb_lock = 0; mu_owner_v = 0; mu_errv = 0;
                rb_live = 0; rb_tail = h_after; rb_count_new = 0;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = rflush_pc; f_err = 0; f_hold = 0; if (bus_hold == 1) f_stale = 1;
                // A refetched load restores its own return-stack pointer (it may be the oldest).
                ras_sp = rflush_ld ? rb_rsp[rflush_e] : rb_rsp[rb_head + n_ret[ROB_B-1:0] - 1'b1];
                ras[ras_sp] = rflush_ld ? rb_rtos[rflush_e] : rb_rtos[rb_head + n_ret[ROB_B-1:0] - 1'b1];
                f_gh = rflush_ld ? rb_gh[rflush_e] : r_gh;
            end else if (mp_any) begin
                squash_after(o_age);
                for (i = 0; i < 32; i = i + 1) begin rat[i] = snap[b_rob][i]; rat_off[i] = snap_off[b_rob][i]; end
                ras_sp = rb_rsp[b_rob]; ras[ras_sp] = rb_rtos[b_rob];
                f_gh = rb_insn[b_rob][6:0] == 7'h63 ? {rb_gh[b_rob][GH_L-2:0], rb_taken[b_rob]} : rb_gh[b_rob];
                rb_tail = b_rob + 1;
                rb_count_new = {1'b0, o_age} + 1 - n_ret;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = mp_fix; f_err = 0; f_hold = 0; if (bus_hold == 1) f_stale = 1;
            end
            rb_head = h_after;

            // ---- rename and dispatch (not in a clock that recovered)
            d_redirect = 0; n_ren = 0;
            if (!rflush && !mp_any) begin
                stop = 0;
                nfi = 0; nfp = 0; ui = 0; up = 0; pv_ok = 0; cf_lvl = 0; n_cf = 0; n_br = 0;
                for (k = 0; k < IQ_N; k = k + 1) if (!iq_valid[k] && nfi < FW) begin fiq[nfi] = k; nfi = nfi + 1; end
                for (k = 1; k < PRF_N; k = k + 1) if (free_mask[k] && nfp < FW) begin fpl[nfp] = k; nfp = nfp + 1; end
                for (s = 0; s < FW; s = s + 1) if (!stop) begin
                    if (s >= q_count || (FE_DEPTH > 0 && q_t[(q_head + s) % Q_N] >= fe_clk)) stop = 1;
                    else begin
                        j = (q_head + s) % Q_N;
                        wi = q_insn[j]; wpc = q_pc[j]; isfault = q_fault[j];
                        op = wi[6:0]; rd_ = wi[11:7]; rs1_ = wi[19:15]; rs2_ = wi[24:20]; f3_ = wi[14:12];
                        writes_ = !isfault && rd_ != 0 && (op == 7'h37 || op == 7'h17 || op == 7'h6f || op == 7'h67 ||
                                  op == 7'h13 || op == 7'h1b || op == 7'h33 || op == 7'h3b || op == 7'h03);
                        uses1_ = !(op == 7'h37 || op == 7'h17 || op == 7'h6f);
                        uses2_ = op == 7'h33 || op == 7'h3b || op == 7'h63 || op == 7'h23;
                        // Prediction check (what D did in the earlier cores).
                        tgt = wpc + (op == 7'h6f ? {{43{wi[31]}},wi[31],wi[19:12],wi[20],wi[30:21],1'b0}
                                                 : {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0});
                        tkp = (op == 7'h6f || (op == 7'h63 && q_fpred[j])) && tgt[1:0] == 0 && !isfault;
                        npc = wpc + 64'd4;
                        d_want = isfault ? q_pred[j] : op == 7'h67 ? q_pred[j] : tkp ? tgt : npc;
                        ps1_ = (uses1_ && rs1_ != 0) ? rat[rs1_] : 0;
                        ps2_ = (uses2_ && rs2_ != 0) ? rat[rs2_] : 0;
                        o1_ = (uses1_ && rs1_ != 0) ? rat_off[rs1_] : 64'b0;
                        o2_ = (uses2_ && rs2_ != 0) ? rat_off[rs2_] : 64'b0;
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
                        cf_now = 0; br_now = 0; bt_ = 0;
                        // Every source a constant: a simple op is computed here.
                        if (CFOLD != 0 && !isfault && !done_ && writes_ &&
                            (op == 7'h13 || op == 7'h1b || op == 7'h33 || op == 7'h3b) &&
                            !((op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01) &&
                            ps1_ == 0 && (!uses2_ || ps2_ == 0) &&
                            (CFOLD > 1 || (!cf_lvl[rs1_] && !(uses2_ && cf_lvl[rs2_])))) begin
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
                        if (rb_count_new >= ROB_N || (!isfault && !done_ && !slot_ok) || (writes_ && !elim_ && !fp_ok)) stop = 1;
                        else begin
                            sa = simple_alu(wi, 64'b0, 64'b0, 64'b0);
                            cls_ = op == 7'h03 ? C_LD : op == 7'h23 ? C_ST : sa[66] ? C_ALU : C_FULL;
                            e = rb_tail;
                            rb_live[e] = 1; rb_done[e] = isfault; rb_exc[e] = isfault;
                            rb_cause[e] = q_fmis[j] ? 64'd0 : 64'd1; rb_tval[e] = wpc;
                            rb_pc[e] = wpc; rb_insn[e] = wi; rb_next[e] = d_want; rb_rd[e] = rd_; rb_writes[e] = writes_;
                            rb_store[e] = op == 7'h23 && !isfault; rb_load[e] = op == 7'h03 && !isfault;
                            rb_fencei[e] = 0; rb_ctl[e] = 0; rb_sta[e] = 0; rb_viol[e] = 0; rb_ldv[e] = 0; rb_ans[e] = 0; rb_wstrb[e] = 0; rb_taken[e] = 0; rb_ret[e] = 0;
                            rb_bhit[e] = q_bhit[j]; rb_bctr[e] = q_bctr[j]; rb_rsp[e] = q_rsp[j]; rb_rtos[e] = q_rtos[j]; rb_gh[e] = q_gh[j]; rb_tp[e] = q_tp[j];
                            rb_li[e] = q_li[j]; rb_lp[e] = op == 7'h63 && !isfault; rb_ld[e] = tkp;
                            rb_fence[e] = op == 7'h0f && f3_ == 3'd0 && !isfault;
                            rb_opdst[e] = rat[rd_]; rb_pdst[e] = writes_ ? (elim_ ? ep_ : fp) : 0;
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
                            if (writes_) cf_lvl[rd_] = cf_now;
                            if (writes_ && elim_) begin
                                rat[rd_] = ep_; rat_off[rd_] = eoff;
                                if (ep_ != 0) refcnt[ep_] = refcnt[ep_] + 1;
                            end else if (writes_) begin
                                rat[rd_] = fp; rat_off[rd_] = 0; refcnt[fp] = 1;
                                free_mask[fp] = 0; prf_ready[fp] = 0; prf_written[fp] = 0;
                            end
                            vpi = wpc[2 +: VP_BITS];
                            rb_vp[e] = 0; rb_vpbad[e] = 0;
                            if (writes_ && (op == 7'h03 || ((op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01)) &&
                                vp_valid[vpi] && vp_tag[vpi] == wpc[2+VP_BITS +: VP_TAG] && vp_conf[vpi] >= vp_thr(vp_strk[vpi])) begin
                                rb_vp[e] = 1; rb_vpv[e] = vp_val[vpi];
                                prf[fp] = vp_val[vpi]; prf_written[fp] = 1; prf_ready[fp] = 1; prf_late[fp] = 1;
                            end
                            if (op == 7'h63 || op == 7'h67) for (i = 0; i < 32; i = i + 1) begin snap[e][i] = rat[i]; snap_off[e][i] = rat_off[i]; end
                            if (!isfault && !done_) begin
                                iq_valid[slot] = 1; iq_issued[slot] = 0; iq_cls[slot] = cls_; iq_rob[slot] = e;
                                iq_pc[slot] = wpc; iq_insn[slot] = wi; iq_ps1[slot] = ps1_; iq_ps2[slot] = ps2_;
                                iq_pdst[slot] = writes_ ? fp : 0; iq_writes[slot] = writes_;
                                iq_mdu[slot] = (op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01;
                                iq_pred[slot] = d_want; iq_ptaken[slot] = tkp; iq_alt[slot] = tkp ? npc : tgt;
                                iq_fz1[slot] = pv_ok && uses1_ && rs1_ == pv_rd;
                                iq_fz2[slot] = pv_ok && uses2_ && rs2_ == pv_rd && cls_ != C_ST;
                                iq_fzi[slot] = pv_insn; iq_fzpc[slot] = pv_pc; iq_fza[slot] = pv_a; iq_fzb[slot] = pv_b;
                                iq_off1[slot] = o1_; iq_off2[slot] = o2_;
                            end
                            cur_fz = pv_ok && ((uses1_ && rs1_ == pv_rd) || (uses2_ && rs2_ == pv_rd && cls_ != C_ST));
                            pv_ok = !isfault && cls_ == C_ALU && writes_ && !cur_fz && !done_ && o1_ == 0 && o2_ == 0;
                            pv_rd = rd_; pv_insn = wi; pv_pc = wpc; pv_a = ps1_; pv_b = ps2_;
                            rb_tail = rb_tail + 1; rb_count_new = rb_count_new + 1; n_ren = n_ren + 1;
                            if (!isfault && !done_) ui = ui + 1;
                            if (writes_ && !elim_) up = up + 1;
                            if (d_want != q_pred[j] || (TG_N != 0 && op == 7'h63 && !isfault && (br_now ? bt_ : tkp) != q_fpred[j])) begin
                                d_redirect = 1; d_redirect_pc = d_want; d_redirect_sp = q_rsp[j]; d_redirect_tos = q_rtos[j];
                                d_redirect_gh = op == 7'h63 ? {q_gh[j][GH_L-2:0], br_now ? bt_ : tkp} : q_gh[j]; stop = 1;
                            end
                        end
                    end
                end
                q_head = q_head + n_ren; q_count = q_count - n_ren;
                if (d_redirect) begin
                    q_head = 0; q_tail = 0; q_count = 0;
                    f_pc = d_redirect_pc; f_err = 0; f_hold = 0; ras_sp = d_redirect_sp; ras[ras_sp] = d_redirect_tos; f_gh = d_redirect_gh; if (bus_hold == 1) f_stale = 1;
                end
            end
            rb_count = rb_count_new;

            // ---- fetch: up to FW instructions from the cache, following up to TAKEN_MAX
            // predicted-taken transfers (since 0.10.1) and at most one call or return
            if (!rflush && (RC_FETCH != 0 || !mp_any) && !d_redirect && !f_hold) begin
                g_n = 0; g_next = f_pc; stop = 0; g_cr = 0;
                g_taken = 0; cur_sp = ras_sp; cur_gh = f_gh; g_cb = 0;
                for (k = 0; k < RAS_N; k = k + 1) gras[k] = ras[k];
                if (f_pc[1:0] != 0 || f_err) begin
                    // A fetch fault becomes one instruction that traps if it retires.
                    g_pc[0] = f_pc; g_insn[0] = 0; g_pred[0] = f_pc + 64'd4; g_fp[0] = 0; g_bh[0] = 0; g_bc[0] = 0;
                    g_fault[0] = 1; g_fmis[0] = f_pc[1:0] != 0; g_n = 1; g_next = f_pc; stop = 1; g_sp[0] = ras_sp; g_tos[0] = ras[ras_sp]; g_gh[0] = f_gh; g_tp[0] = 8'h38;
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
                        q_rsp[j] = g_sp[s]; q_rtos[j] = g_tos[s]; q_gh[j] = g_gh[s]; q_tp[j] = g_tp[s]; q_t[j] = fe_clk + FE_DEPTH;
                        q_lp[j] = g_lpmask[s]; q_ld[j] = g_fp[s]; q_li[j] = g_li[s]; q_lp_c[j] = g_insn[s][6:0] == 7'h63 && !g_fault[s];
                    end
                    q_tail = q_tail + g_n; q_count = q_count + g_n;
                    ras_sp = cur_sp; f_gh = cur_gh;
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
