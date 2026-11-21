// SPDX-License-Identifier: MIT
// Original CPU foundation, wide out-of-order implementation (architecture 0.10.0).
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
    // Retirement (and fetch and rename) width.
    parameter integer RW = 8
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
    output reg [RW*64-1:0] rt_next
);
    // Wide out-of-order core (0.10.0), configured after measurements of the Apple M5
    // performance core (useless-husband/m5-uarch): 8 instructions per clock through
    // fetch, rename and retirement, a 128-entry reorder buffer, 160 physical registers,
    // a 64-entry issue queue, 8 integer ALUs of which 3 also execute branches, jumps,
    // system instructions and multiply/divide, 3 load ports and 2 store-address ports.
    // Multiply takes 3 clocks (pipelined), divide 7 (one unit). Loads that cannot finish
    // (cache miss, store data not ready, partial overlap with an older store) stay in
    // the issue queue and replay. Each branch saves the rename map, so a mispredict
    // recovers in the clock it executes. Stores write the bus when they retire (one per
    // clock). This is a behavioural simulation model: area and clock rate on an FPGA
    // are not considered yet.
    localparam [2:0] FETCH=0, EXECUTE=1, MEMORY=2, HALTED=3;
    localparam integer IC_INDEX = $clog2(ICACHE_BEATS);
    localparam integer IC_TAG = 61 - IC_INDEX;
    localparam integer DC_INDEX = $clog2(DCACHE_BEATS);
    localparam integer DC_TAG = 61 - DC_INDEX;
    generate if (ICACHE_BEATS < 2 || (ICACHE_BEATS & (ICACHE_BEATS - 1)) != 0) begin : bad_icache_size
        initial $fatal(1, "ICACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    generate if (DCACHE_BEATS < 2 || (DCACHE_BEATS & (DCACHE_BEATS - 1)) != 0) begin : bad_dcache_size
        initial $fatal(1, "DCACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    localparam integer FW = RW;          // fetch and rename width
    localparam integer ROB_N = 128;
    localparam integer ROB_B = 7;
    localparam integer PRF_N = 32 + ROB_N;
    localparam integer P_B = 8;
    localparam integer IQ_N = 64;
    localparam integer IQ_B = 6;
    localparam integer Q_N = 32;
    localparam integer Q_B = 5;
    localparam integer N_ALU = 8;        // integer ports
    localparam integer N_BR = 3;         // of which these also take branches, system and M
    localparam integer N_LD = 3;
    localparam integer N_ST = 2;
    localparam integer NP = N_ALU + N_LD + N_ST;
    localparam integer MUL_LAT = 3;
    localparam integer DIV_LAT = 7;
    localparam integer MQ_N = 8;         // multiplies in flight
    localparam integer BTB_BITS = 8;
    localparam integer BTB_TAG = 10;
    localparam integer BTB_ENTRIES = 1 << BTB_BITS;
    localparam integer RAS_N = 16;
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
    reg [3:0] rb_rsp [0:ROB_N-1];      // return-stack pointer after this instruction's fetch
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
    // Branch target buffer and return stack.
    reg [BTB_ENTRIES-1:0] btb_valid, btb_ret;
    reg [BTB_TAG-1:0] btb_tag [0:BTB_ENTRIES-1];
    reg [29:0] btb_target [0:BTB_ENTRIES-1];
    reg [1:0] btb_ctr [0:BTB_ENTRIES-1];
    reg [63:0] ras [0:RAS_N-1];
    reg [3:0] ras_sp;
    // Fetch.
    reg [63:0] f_pc;
    reg [63:0] q_pc [0:Q_N-1];
    reg [63:0] q_pred [0:Q_N-1];
    reg [31:0] q_insn [0:Q_N-1];
    reg [Q_N-1:0] q_fpred, q_bhit, q_fault, q_fmis;
    reg [1:0] q_bctr [0:Q_N-1];
    reg [3:0] q_rsp [0:Q_N-1];
    reg [Q_B-1:0] q_head, q_tail;
    reg [Q_B:0] q_count;
    reg f_err;                  // the last fetch of f_pc's beat failed
    reg f_hold;                 // a fetch fault was delivered: wait for a redirect
    // Bus: one request at a time, held until it completes.
    reg [1:0] bus_hold;         // 0 none, 1 fetch, 2 load miss, 3 store
    reg [63:0] hold_addr;
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

    // ---------------- bus request (combinational) -------------------------------
    // The retiring store: the first store in the retirement window, when everything
    // before it there is finished, will retire this clock and is no fence.i.
    reg st_cand;
    reg [ROB_B-1:0] st_idx;
    reg h_exc;
    always @* begin
        st_cand = 0; st_idx = 0;
        h_exc = rb_count != 0 && rb_done[rb_head] && rb_exc[rb_head];
        begin : scan
            reg stop;
            reg [ROB_B-1:0] e;
            stop = 0;
            for (k = 0; k < RW; k = k + 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (!stop) begin
                    if (k >= rb_count || !rb_done[e] || rb_exc[e]) stop = 1;
                    else if (rb_store[e]) begin st_cand = 1; st_idx = e; stop = 1; end
                    else if (rb_fencei[e]) stop = 1;
                end
            end
        end
    end
    wire [63:0] st_addr = rb_addr[st_idx];
    wire [63:0] st_wdata = prf[rb_sps2[st_idx]] << {st_addr[2:0],3'b000};
    wire f_beat_hit = ic_valid[f_pc[3 +: IC_INDEX]] && ic_tag[f_pc[3 +: IC_INDEX]] == f_pc[63 -: IC_TAG];
    wire want_store = st_cand;
    wire want_miss = mu_valid && !h_exc;
    wire want_fetch = started && !halted && f_pc[1:0] == 0 && !f_beat_hit && !f_err && !f_hold && !h_exc;
    wire [1:0] bus_kind = halted ? 2'd0 : bus_hold != 0 ? bus_hold : want_store ? 2'd3 : want_miss ? 2'd2 :
                          want_fetch ? 2'd1 : 2'd0;
    assign mem_valid = !reset && bus_kind != 0;
    assign mem_instr = bus_kind == 1;
    assign mem_addr = bus_kind == 1 ? (bus_hold == 1 ? hold_addr : {f_pc[63:3],3'b000})
                    : bus_kind == 2 ? mu_beat : {st_addr[63:3],3'b000};
    assign mem_wdata = bus_kind == 3 ? st_wdata : 64'b0;
    assign mem_wstrb = bus_kind == 3 ? rb_wstrb[st_idx] : 8'b0;
    wire [2:0] state = halted ? HALTED : (bus_kind >= 2) ? MEMORY : (bus_kind == 1) ? FETCH : EXECUTE;

    // ---------------- the clock -------------------------------------------------
    // Decisions are taken from the state at the start of the clock (phase 1), then
    // applied (phase 2), mirroring registered hardware.
    reg [ROB_B-1:0] e, b_rob, x_rob, o_age, a_age, ou_age, h_after;
    reg [ROB_B:0] n_ret;
    reg ou_valid, mp_any, rflush, trap_now, stop, fired, fdone, ok, hit, full, dok;
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
    reg [63:0] g_pc [0:7];
    reg [31:0] g_insn [0:7];
    reg [63:0] g_pred [0:7];
    reg [7:0] g_fp, g_bh, g_fault, g_fmis;
    reg [1:0] g_bc [0:7];
    reg [3:0] g_n;
    reg [63:0] g_next;
    reg g_ras_push, g_ras_pop;
    reg [63:0] g_ras_val;
    reg [BTB_BITS-1:0] bi;
    reg [IC_INDEX-1:0] fi;
    reg [3:0] n_ren;
    reg d_redirect;
    reg [63:0] d_redirect_pc;
    reg [IQ_B-1:0] slot;
    reg slot_ok;
    reg [P_B-1:0] fp;
    reg fp_ok;
    reg [2:0] f3_;
    reg [ROB_B:0] rb_count_new;
    reg dv_pend;
    reg [IQ_B-1:0] fiq [0:7];   // free issue-queue slots and physical registers, lowest first
    reg [P_B-1:0] fpl [0:7];
    integer nfi, nfp, ui, up;
    reg miss_v;
    reg [63:0] miss_beat;
    reg [ROB_B-1:0] miss_age, miss_owner, ol_age;
    reg ol_valid;
    reg [Q_B-1:0] qa;

    task automatic squash_after(input [ROB_B-1:0] keep_age);  // keep entries with age <= keep_age
        reg [ROB_B-1:0] en;
        begin
            for (k = 0; k < ROB_N; k = k + 1) begin
                en = k[ROB_B-1:0];
                if (rb_live[en] && (en - rb_head) > keep_age) begin
                    rb_live[en] = 0; rb_done[en] = 0;
                    if (rb_writes[en]) free_mask[rb_pdst[en]] = 1;
                end
            end
            for (k = 0; k < IQ_N; k = k + 1)
                if (iq_valid[k] && (iq_rob[k] - rb_head) > keep_age) iq_valid[k] = 0;
            for (k = 0; k < MQ_N; k = k + 1)
                if (mq_valid[k] && (mq_rob[k] - rb_head) > keep_age) mq_valid[k] = 0;
            if (dv_busy && (dv_rob - rb_head) > keep_age) dv_busy = 0;
            if (fb_lock && (fb_owner - rb_head) > keep_age) fb_lock = 0;
            if (mu_owner_v && (mu_owner - rb_head) > keep_age) mu_owner_v = 0;
        end
    endtask

    always @(posedge clk) begin
        if (reset) begin
            halted = 0; started = 0; f_pc = RESET_PC; f_err = 0; f_hold = 0;
            bus_hold = 0; hold_addr = 0; mu_valid = 0; mu_beat = 0; mu_errv = 0; mu_err_beat = 0;
            fb_valid = 0; fb_beat = 0; fb_data = 0; mu_owner = 0; fb_owner = 0; fb_lock = 0; mu_owner_v = 0;
            for (i = 0; i < PRF_N; i = i + 1) prf[i] = 0;
            prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}};
            free_mask = {PRF_N{1'b1}}; for (i = 0; i < 32; i = i + 1) free_mask[i] = 0;
            for (i = 0; i < 32; i = i + 1) begin rat[i] = i; rrat[i] = i; end
            rb_live = 0; rb_done = 0; rb_head = 0; rb_tail = 0; rb_count = 0;
            iq_valid = 0; iq_issued = 0; ex_valid = 0; mq_valid = 0; dv_busy = 0;
            ic_valid = 0; dc_valid = 0; btb_valid = 0; btb_ret = 0; ras_sp = 0;
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
            // ================= bus completion =================
            if (bus_kind != 0) begin
                if (mem_ready) begin
                    bus_hold = 0;
                    if (bus_kind == 1) begin
                        if (mem_error) begin if (mem_addr[63:3] == f_pc[63:3]) f_err = 1; end
                        else begin
                            fi = mem_addr[3 +: IC_INDEX];
                            ic_valid[fi] = 1; ic_tag[fi] = mem_addr[63 -: IC_TAG]; ic_data[fi] = mem_rdata;
                        end
                    end else if (bus_kind == 2) begin
                        mu_valid = 0;
                        if (mem_error) begin mu_errv = 1; mu_err_beat = mu_beat; end
                        else begin
                            dc_valid[mu_beat[3 +: DC_INDEX]] = 1; dc_tag[mu_beat[3 +: DC_INDEX]] = mu_beat[63 -: DC_TAG];
                            dc_data[mu_beat[3 +: DC_INDEX]] = mem_rdata;
                            fb_valid = 1; fb_beat = mu_beat; fb_data = mem_rdata; fb_owner = mu_owner; fb_lock = mu_owner_v;
                        end
                    end
                end else begin
                    bus_hold = bus_kind; hold_addr = mem_addr;
                end
            end
            // ================= phase 1: decisions from the state at the clock start =====
            // ---- issue selection: oldest first per port class
            ou_valid = 0; ou_age = 0;
            for (k = ROB_N-1; k >= 0; k = k - 1) begin
                e = rb_head + k[ROB_B-1:0];
                if (k < rb_count && rb_store[e] && !rb_sta[e]) begin ou_valid = 1; ou_age = k[ROB_B-1:0]; end
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
                if (k < rb_count && rb_load[e] && !rb_done[e]) begin ol_valid = 1; ol_age = k[ROB_B-1:0]; end
            end
            chosen = 0; pick_v = 0; divtaken = 0;
            for (p = 0; p < NP; p = p + 1) begin
                bestv = 0; best = 0; best_age = 0;
                for (k = 0; k < IQ_N; k = k + 1) begin
                    a_age = iq_rob[k] - rb_head;
                    ok = iq_valid[k] && !iq_issued[k] && !chosen[k] && prf_ready[iq_ps1[k]];
                    if (p < N_ALU) begin
                        ok = ok && prf_ready[iq_ps2[k]] &&
                             (iq_cls[k] == C_ALU || (p < N_BR && iq_cls[k] == C_FULL &&
                              !(iq_mdu[k] && iq_insn[k][14] && (dv_busy || dv_pend || divtaken))));
                    end else if (p < N_ALU + N_LD) ok = ok && iq_cls[k] == C_LD && (!ou_valid || a_age < ou_age);
                    else ok = ok && iq_cls[k] == C_ST;
                    if (ok && (!bestv || a_age < best_age)) begin bestv = 1; best = k[IQ_B-1:0]; best_age = a_age; end
                end
                if (bestv) begin
                    pick_v[p] = 1; pick[p] = best; chosen[best] = 1;
                    if (iq_mdu[best] && iq_insn[best][14]) divtaken = 1;
                end
            end

            // ---- retirement window
            n_ret = 0; rflush = 0; trap_now = 0; stop = 0; rflush_pc = 0;
            for (s = 0; s < RW; s = s + 1) begin
                e = rb_head + s[ROB_B-1:0];
                if (!stop) begin
                    if (s >= rb_count || !rb_done[e]) stop = 1;
                    else if (rb_exc[e]) begin
                        if (s == 0 && bus_kind == 0) begin
                            trap_now = 1;
                            trap_pc <= rb_pc[e]; trap_cause <= rb_cause[e]; trap_tval <= rb_tval[e];
                        end
                        stop = 1;
                    end else if (rb_store[e]) begin
                        if (bus_kind == 3 && mem_ready) begin
                            if (mem_error) begin
                                trap_now = 1; trap_pc <= rb_pc[e]; trap_cause <= 7; trap_tval <= rb_addr[e];
                            end else n_ret = s + 1;
                        end
                        stop = 1;
                    end else begin
                        n_ret = s + 1;
                        if (rb_fencei[e]) begin rflush = 1; rflush_pc = rb_next[e]; stop = 1; end
                    end
                end
            end

            // ================= phase 2: apply =================
            // ---- retire
            for (s = 0; s < RW; s = s + 1) if (s < n_ret) begin
                e = rb_head + s[ROB_B-1:0];
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
                if (rb_writes[e]) begin rrat[rb_rd[e]] = rb_pdst[e]; free_mask[rb_opdst[e]] = 1; end
                if (rb_ctl[e]) begin
                    bi = rb_pc[e][2 +: BTB_BITS];
                    if (rb_taken[e]) begin
                        btb_ctr[bi] = (btb_valid[bi] && btb_tag[bi] == rb_pc[e][2+BTB_BITS +: BTB_TAG]) ?
                                      (btb_ctr[bi] == 3 ? 2'd3 : btb_ctr[bi] + 2'd1) : 2'd2;
                        btb_valid[bi] = 1; btb_tag[bi] = rb_pc[e][2+BTB_BITS +: BTB_TAG];
                        btb_target[bi] = rb_next[e][31:2]; btb_ret[bi] = rb_ret[e];
                    end else if (btb_valid[bi] && btb_tag[bi] == rb_pc[e][2+BTB_BITS +: BTB_TAG])
                        btb_ctr[bi] = btb_ctr[bi] == 0 ? 2'd0 : btb_ctr[bi] - 2'd1;
                end
                if (rb_store[e]) begin
                    // Write-through: update a cached line; drop a cached instruction beat.
                    fi = rb_addr[e][3 +: IC_INDEX];
                    if (dc_valid[rb_addr[e][3 +: DC_INDEX]] && dc_tag[rb_addr[e][3 +: DC_INDEX]] == rb_addr[e][63 -: DC_TAG])
                        for (k = 0; k < 8; k = k + 1)
                            if (rb_wstrb[e][k]) dc_data[rb_addr[e][3 +: DC_INDEX]][8*k +: 8] = st_wdata[8*k +: 8];
                    if (ic_valid[fi] && ic_tag[fi] == rb_addr[e][63 -: IC_TAG]) ic_valid[fi] = 0;
                    if (fb_valid && fb_beat[63:3] == rb_addr[e][63:3])
                        for (k = 0; k < 8; k = k + 1) if (rb_wstrb[e][k]) fb_data[8*k +: 8] = st_wdata[8*k +: 8];
                    // Younger instructions already fetched from this beat are refetched.
                    hit = 0;
                    for (k = 0; k < ROB_N; k = k + 1)
                        if (rb_live[k] && (k[ROB_B-1:0] - rb_head) > s[ROB_B-1:0] && rb_pc[k][63:3] == rb_addr[e][63:3]) hit = 1;
                    for (k = 0; k < Q_N; k = k + 1) begin
                        qa = k[Q_B-1:0] - q_head;
                        if (qa < q_count && q_pc[k][63:3] == rb_addr[e][63:3]) hit = 1;
                    end
                    for (k = 0; k <= FW/2; k = k + 1)
                        if (f_pc[63:3] + k == rb_addr[e][63:3]) hit = 1;
                    if (hit) begin rflush = 1; rflush_pc = rb_next[e]; end
                end
                if (rb_fencei[e]) ic_valid = 0;
                rb_live[e] = 0; rb_done[e] = 0;
            end
            if (trap_now) begin
                trap_valid <= 1; halted = 1;
            end else begin
            // ---- execute: results of the instructions selected last clock
            mp_any = 0; b_rob = 0; mp_fix = 0;
            for (p = 0; p < N_BR; p = p + 1) if (ex_valid[p] && ex_cls[p] == C_FULL) begin
                ef = exec_full(ex_insn[p], ex_pc[p], prf[ex_ps1[p]], prf[ex_ps2[p]]);
                op = ex_insn[p][6:0];
                if (!ef[197] && !ef[0] && ((op == 7'h63 && (ef[64:1] != ex_pc[p] + 64'd4) != ex_ptaken[p]) ||
                                           (op == 7'h67 && ef[64:1] != ex_pred[p]))) begin
                    a_age = ex_rob[p] - rb_head;
                    if (!mp_any || a_age < (b_rob - rb_head)) begin mp_any = 1; b_rob = ex_rob[p]; mp_fix = ef[64:1]; end
                end
            end
            if (rflush) mp_any = 0;
            o_age = b_rob - rb_head;
            miss_v = 0; miss_beat = 0; miss_age = 0;
            for (p = 0; p < NP; p = p + 1) if (ex_valid[p] && !rflush && !(mp_any && (ex_rob[p] - rb_head) > o_age)) begin
                x_rob = ex_rob[p];
                if (p < N_ALU) begin
                    if (ex_cls[p] == C_ALU) begin
                        sa = simple_alu(ex_insn[p], prf[ex_ps1[p]], prf[ex_ps2[p]], ex_pc[p]);
                        if (ex_writes[p]) begin prf[ex_pdst[p]] = sa[63:0]; prf_written[ex_pdst[p]] = 1; end
                        rb_value[x_rob] = sa[63:0]; rb_done[x_rob] = 1; rb_exc[x_rob] = 0; rb_next[x_rob] = ex_pc[p] + 64'd4;
                    end else begin
                        ef = exec_full(ex_insn[p], ex_pc[p], prf[ex_ps1[p]], prf[ex_ps2[p]]);
                        op = ex_insn[p][6:0]; f3_ = ex_insn[p][14:12];
                        rb_next[x_rob] = ef[64:1];
                        if (ef[0]) begin
                            if (!f3_[2]) begin : mul_start
                                reg placed;
                                placed = 0;
                                for (k = 0; k < MQ_N; k = k + 1) if (!mq_valid[k] && !placed) begin
                                    placed = 1; mq_valid[k] = 1; mq_cnt[k] = MUL_LAT - 3; mq_rob[k] = x_rob;
                                    mq_pdst[k] = ex_pdst[p]; mq_writes[k] = ex_writes[p];
                                    mq_val[k] = mul_value(f3_, op == 7'h3b, prf[ex_ps1[p]], prf[ex_ps2[p]]);
                                end
                            end else begin
                                dv_busy = 1; dv_cnt = DIV_LAT - 3; dv_rob = x_rob; dv_pdst = ex_pdst[p]; dv_writes = ex_writes[p];
                                dv_val = div_value(f3_, op == 7'h3b, prf[ex_ps1[p]], prf[ex_ps2[p]]);
                            end
                        end else begin
                            if (ex_writes[p] && !ef[197]) begin prf[ex_pdst[p]] = ef[128:65]; prf_written[ex_pdst[p]] = 1; end
                            rb_value[x_rob] = ef[128:65]; rb_done[x_rob] = 1; rb_exc[x_rob] = ef[197];
                            rb_cause[x_rob] = {60'b0, ef[196:193]}; rb_tval[x_rob] = ef[192:129];
                            rb_ctl[x_rob] = !ef[197] && (op == 7'h63 || op == 7'h6f || op == 7'h67);
                            rb_taken[x_rob] = op == 7'h6f || op == 7'h67 || ef[64:1] != ex_pc[p] + 64'd4;
                            rb_ret[x_rob] = op == 7'h67 && ex_insn[p][11:7] == 0 &&
                                            (ex_insn[p][19:15] == 1 || ex_insn[p][19:15] == 5);
                            rb_fencei[x_rob] = op == 7'h0f && f3_ == 1 && !ef[197];
                        end
                    end
                end else if (p < N_ALU + N_LD) begin
                    // Load: forward from the youngest older store to its beat, else the cache;
                    // if neither can answer now, the load stays queued and replays.
                    f3_ = ex_insn[p][14:12];
                    ea = prf[ex_ps1[p]] + {{52{ex_insn[p][31]}}, ex_insn[p][31:20]};
                    bytes_ = size_bytes(f3_[1:0]) << ea[2:0];
                    fdone = 0;
                    if (f3_ == 3'd7 || (ea[2:0] & (f3_[1:0] == 0 ? 3'd0 : f3_[1:0] == 1 ? 3'd1 : f3_[1:0] == 2 ? 3'd3 : 3'd7)) != 0) begin
                        rb_done[x_rob] = 1; rb_exc[x_rob] = 1;
                        rb_cause[x_rob] = f3_ == 3'd7 ? 64'd2 : 64'd4; rb_tval[x_rob] = f3_ == 3'd7 ? {32'b0, ex_insn[p]} : ea;
                        iq_valid[ex_iq[p]] = 0;
                    end else if (mu_errv && mu_err_beat[63:3] == ea[63:3]) begin
                        if (fb_lock && x_rob == fb_owner) fb_lock = 0;
                        rb_done[x_rob] = 1; rb_exc[x_rob] = 1; rb_cause[x_rob] = 5; rb_tval[x_rob] = ea;
                        iq_valid[ex_iq[p]] = 0;
                    end else begin
                        fwd_hit = 0; fwd_e = 0;
                        a_age = x_rob - rb_head;
                        for (k = 0; k < ROB_N; k = k + 1) begin
                            e = rb_head + k[ROB_B-1:0];
                            if (k[ROB_B-1:0] < a_age && rb_live[e] && rb_store[e] && rb_sta[e] &&
                                rb_addr[e][63:3] == ea[63:3] && (rb_wstrb[e] & bytes_) != 0) begin fwd_hit = 1; fwd_e = e; end
                        end
                        if (fwd_hit) begin
                            if ((rb_wstrb[fwd_e] & bytes_) == bytes_ && prf_written[rb_sps2[fwd_e]]) begin
                                v = load_align(prf[rb_sps2[fwd_e]] << {rb_addr[fwd_e][2:0],3'b000}, ea[2:0], f3_);
                                fdone = 1;
                            end
                        end else if (dc_valid[ea[3 +: DC_INDEX]] && dc_tag[ea[3 +: DC_INDEX]] == ea[63 -: DC_TAG]) begin
                            v = load_align(dc_data[ea[3 +: DC_INDEX]], ea[2:0], f3_); fdone = 1;
                        end else if (fb_valid && fb_beat[63:3] == ea[63:3]) begin
                            v = load_align(fb_data, ea[2:0], f3_); fdone = 1;
                        end else if (ol_valid && a_age == ol_age) begin
                            miss_v = 1; miss_beat = {ea[63:3],3'b000}; miss_age = a_age; miss_owner = x_rob;
                        end
                        if (fdone && fb_lock && x_rob == fb_owner) fb_lock = 0;
                        if (fdone) begin
                            if (ex_writes[p]) begin prf[ex_pdst[p]] = v; prf_written[ex_pdst[p]] = 1; prf_ready[ex_pdst[p]] = 1; end
                            rb_value[x_rob] = v; rb_done[x_rob] = 1; rb_exc[x_rob] = 0;
                            iq_valid[ex_iq[p]] = 0;
                        end else iq_issued[ex_iq[p]] = 0;
                    end
                end else begin
                    // Store: record the address; the data register is read at retirement.
                    f3_ = ex_insn[p][14:12];
                    ea = prf[ex_ps1[p]] + {{52{ex_insn[p][31]}}, ex_insn[p][31:25], ex_insn[p][11:7]};
                    ok = !f3_[2] && (ea[2:0] & (f3_[1:0] == 0 ? 3'd0 : f3_[1:0] == 1 ? 3'd1 : f3_[1:0] == 2 ? 3'd3 : 3'd7)) == 0;
                    rb_done[x_rob] = 1; rb_sta[x_rob] = 1; rb_exc[x_rob] = !ok;
                    rb_cause[x_rob] = f3_[2] ? 64'd2 : 64'd6; rb_tval[x_rob] = f3_[2] ? {32'b0, ex_insn[p]} : ea;
                    rb_addr[x_rob] = ea; rb_wstrb[x_rob] = size_bytes(f3_[1:0]) << ea[2:0]; rb_sps2[x_rob] = ex_ps2[p];
                end
            end
            if (miss_v && !mu_valid && !fb_lock) begin
                mu_valid = 1; mu_beat = miss_beat; mu_errv = 0; mu_owner = miss_owner; mu_owner_v = 1;
            end
            // ---- multiply pipeline and divide unit
            for (k = 0; k < MQ_N; k = k + 1) if (mq_valid[k]) begin
                if (rflush || (mp_any && (mq_rob[k] - rb_head) > o_age)) mq_valid[k] = 0;
                else if (mq_cnt[k] == 0) begin
                    mq_valid[k] = 0;
                    if (mq_writes[k]) begin prf[mq_pdst[k]] = mq_val[k]; prf_written[mq_pdst[k]] = 1; prf_ready[mq_pdst[k]] = 1; end
                    rb_value[mq_rob[k]] = mq_val[k]; rb_done[mq_rob[k]] = 1; rb_exc[mq_rob[k]] = 0;
                end else mq_cnt[k] = mq_cnt[k] - 1;
            end
            if (dv_busy) begin
                if (rflush || (mp_any && (dv_rob - rb_head) > o_age)) dv_busy = 0;
                else if (dv_cnt == 0) begin
                    dv_busy = 0;
                    if (dv_writes) begin prf[dv_pdst] = dv_val; prf_written[dv_pdst] = 1; prf_ready[dv_pdst] = 1; end
                    rb_value[dv_rob] = dv_val; rb_done[dv_rob] = 1; rb_exc[dv_rob] = 0;
                end else dv_cnt = dv_cnt - 1;
            end

            // ---- issue: the instructions selected this clock execute next clock
            ex_valid = 0;
            for (p = 0; p < NP; p = p + 1) if (pick_v[p]) begin
                k = pick[p];
                if (iq_valid[k] && !rflush && !(mp_any && (iq_rob[k] - rb_head) > o_age)) begin
                    ex_valid[p] = 1; ex_iq[p] = k; ex_cls[p] = iq_cls[k]; ex_rob[p] = iq_rob[k]; ex_pc[p] = iq_pc[k];
                    ex_insn[p] = iq_insn[k]; ex_ps1[p] = iq_ps1[k]; ex_ps2[p] = iq_ps2[k]; ex_pdst[p] = iq_pdst[k];
                    ex_writes[p] = iq_writes[k]; ex_pred[p] = iq_pred[k]; ex_alt[p] = iq_alt[k]; ex_ptaken[p] = iq_ptaken[k];
                    if (iq_cls[k] == C_LD) iq_issued[k] = 1;
                    else iq_valid[k] = 0;
                    // A result one clock away wakes its consumers now.
                    if ((iq_cls[k] == C_ALU || (iq_cls[k] == C_FULL && !iq_mdu[k])) && iq_writes[k]) prf_ready[iq_pdst[k]] = 1;
                end
            end

            // ---- recovery
            h_after = rb_head + n_ret[ROB_B-1:0];
            rb_count_new = rb_count - n_ret;
            if (rflush) begin
                squash_after(n_ret[ROB_B-1:0] - 1);
                for (i = 0; i < 32; i = i + 1) rat[i] = rrat[i];
                free_mask = {PRF_N{1'b1}};
                for (i = 0; i < 32; i = i + 1) free_mask[rrat[i]] = 0;
                prf_ready = {PRF_N{1'b1}}; prf_written = {PRF_N{1'b1}};
                ex_valid = 0; iq_valid = 0; iq_issued = 0; fb_lock = 0; mu_owner_v = 0;
                rb_live = 0; rb_tail = h_after; rb_count_new = 0;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = rflush_pc; f_err = 0; f_hold = 0;
            end else if (mp_any) begin
                squash_after(o_age);
                for (i = 0; i < 32; i = i + 1) rat[i] = snap[b_rob][i];
                ras_sp = rb_rsp[b_rob];
                rb_tail = b_rob + 1;
                rb_count_new = {1'b0, o_age} + 1 - n_ret;
                q_head = 0; q_tail = 0; q_count = 0;
                f_pc = mp_fix; f_err = 0; f_hold = 0;
            end
            rb_head = h_after;

            // ---- rename and dispatch (not in a clock that recovered)
            d_redirect = 0; n_ren = 0;
            if (!rflush && !mp_any) begin
                stop = 0;
                nfi = 0; nfp = 0; ui = 0; up = 0;
                for (k = 0; k < IQ_N; k = k + 1) if (!iq_valid[k] && nfi < FW) begin fiq[nfi] = k; nfi = nfi + 1; end
                for (k = 1; k < PRF_N; k = k + 1) if (free_mask[k] && nfp < FW) begin fpl[nfp] = k; nfp = nfp + 1; end
                for (s = 0; s < FW; s = s + 1) if (!stop) begin
                    if (s >= q_count) stop = 1;
                    else begin
                        j = (q_head + s) % Q_N;
                        wi = q_insn[j]; wpc = q_pc[j]; isfault = q_fault[j];
                        op = wi[6:0]; rd_ = wi[11:7]; rs1_ = wi[19:15]; rs2_ = wi[24:20]; f3_ = wi[14:12];
                        writes_ = !isfault && rd_ != 0 && (op == 7'h37 || op == 7'h17 || op == 7'h6f || op == 7'h67 ||
                                  op == 7'h13 || op == 7'h1b || op == 7'h33 || op == 7'h3b || op == 7'h03);
                        uses1_ = !(op == 7'h37 || op == 7'h17 || op == 7'h6f);
                        uses2_ = op == 7'h33 || op == 7'h3b || op == 7'h63 || op == 7'h23;
                        // Resources: ROB entry, issue-queue entry, physical register.
                        slot_ok = ui < nfi; slot = fiq[ui % 8];
                        fp_ok = up < nfp; fp = fpl[up % 8];
                        if (rb_count_new >= ROB_N || (!isfault && !slot_ok) || (writes_ && !fp_ok)) stop = 1;
                        else begin
                            // Prediction check (what D did in the earlier cores).
                            tgt = wpc + (op == 7'h6f ? {{43{wi[31]}},wi[31],wi[19:12],wi[20],wi[30:21],1'b0}
                                                     : {{51{wi[31]}},wi[31],wi[7],wi[30:25],wi[11:8],1'b0});
                            tkp = (op == 7'h6f || (op == 7'h63 && (q_fpred[j] || wi[31]))) && tgt[1:0] == 0 && !isfault;
                            npc = wpc + 64'd4;
                            d_want = isfault ? q_pred[j] : op == 7'h67 ? q_pred[j] : tkp ? tgt : npc;
                            ps1_ = (uses1_ && rs1_ != 0) ? rat[rs1_] : 0;
                            ps2_ = (uses2_ && rs2_ != 0) ? rat[rs2_] : 0;
                            sa = simple_alu(wi, 64'b0, 64'b0, 64'b0);
                            cls_ = op == 7'h03 ? C_LD : op == 7'h23 ? C_ST : sa[66] ? C_ALU : C_FULL;
                            e = rb_tail;
                            rb_live[e] = 1; rb_done[e] = isfault; rb_exc[e] = isfault;
                            rb_cause[e] = q_fmis[j] ? 64'd0 : 64'd1; rb_tval[e] = wpc;
                            rb_pc[e] = wpc; rb_insn[e] = wi; rb_next[e] = d_want; rb_rd[e] = rd_; rb_writes[e] = writes_;
                            rb_store[e] = op == 7'h23 && !isfault; rb_load[e] = op == 7'h03 && !isfault;
                            rb_fencei[e] = 0; rb_ctl[e] = 0; rb_sta[e] = 0; rb_taken[e] = 0; rb_ret[e] = 0;
                            rb_bhit[e] = q_bhit[j]; rb_bctr[e] = q_bctr[j]; rb_rsp[e] = q_rsp[j];
                            rb_opdst[e] = rat[rd_]; rb_pdst[e] = writes_ ? fp : 0;
                            if (writes_) begin
                                rat[rd_] = fp; free_mask[fp] = 0; prf_ready[fp] = 0; prf_written[fp] = 0;
                            end
                            if (op == 7'h63 || op == 7'h67) for (i = 0; i < 32; i = i + 1) snap[e][i] = rat[i];
                            if (!isfault) begin
                                iq_valid[slot] = 1; iq_issued[slot] = 0; iq_cls[slot] = cls_; iq_rob[slot] = e;
                                iq_pc[slot] = wpc; iq_insn[slot] = wi; iq_ps1[slot] = ps1_; iq_ps2[slot] = ps2_;
                                iq_pdst[slot] = writes_ ? fp : 0; iq_writes[slot] = writes_;
                                iq_mdu[slot] = (op == 7'h33 || op == 7'h3b) && wi[31:25] == 7'h01;
                                iq_pred[slot] = d_want; iq_ptaken[slot] = tkp; iq_alt[slot] = tkp ? npc : tgt;
                            end
                            rb_tail = rb_tail + 1; rb_count_new = rb_count_new + 1; n_ren = n_ren + 1;
                            if (!isfault) ui = ui + 1;
                            if (writes_) up = up + 1;
                            if (d_want != q_pred[j]) begin d_redirect = 1; d_redirect_pc = d_want; stop = 1; end
                        end
                    end
                end
                q_head = q_head + n_ren; q_count = q_count - n_ren;
                if (d_redirect) begin
                    q_head = 0; q_tail = 0; q_count = 0;
                    f_pc = d_redirect_pc; f_err = 0; f_hold = 0;
                end
            end
            rb_count = rb_count_new;

            // ---- fetch: up to FW instructions from the cache, ending at a predicted-taken
            // transfer, a call or a return
            if (!rflush && !mp_any && !d_redirect && !f_hold) begin
                g_n = 0; g_next = f_pc; stop = 0; g_ras_push = 0; g_ras_pop = 0; g_ras_val = 0;
                if (f_pc[1:0] != 0 || f_err) begin
                    // A fetch fault becomes one instruction that traps if it retires.
                    g_pc[0] = f_pc; g_insn[0] = 0; g_pred[0] = f_pc + 64'd4; g_fp[0] = 0; g_bh[0] = 0; g_bc[0] = 0;
                    g_fault[0] = 1; g_fmis[0] = f_pc[1:0] != 0; g_n = 1; g_next = f_pc; stop = 1;
                end
                npc = f_pc;
                for (s = 0; s < FW; s = s + 1) if (!stop) begin
                    fi = npc[3 +: IC_INDEX];
                    if (!(ic_valid[fi] && ic_tag[fi] == npc[63 -: IC_TAG])) stop = 1;
                    else begin
                        wi = npc[2] ? ic_data[fi][63:32] : ic_data[fi][31:0];
                        bi = npc[2 +: BTB_BITS];
                        hit = btb_valid[bi] && btb_tag[bi] == npc[2+BTB_BITS +: BTB_TAG];
                        tkp = hit && (btb_ret[bi] || btb_ctr[bi][1]);
                        tgt = btb_ret[bi] ? ras[ras_sp] : {npc[63:32], btb_target[bi], 2'b00};
                        g_pc[s] = npc; g_insn[s] = wi; g_pred[s] = tkp ? tgt : npc + 64'd4;
                        g_fp[s] = tkp; g_bh[s] = hit; g_bc[s] = btb_ctr[bi]; g_fault[s] = 0; g_fmis[s] = 0;
                        g_n = s + 1;
                        op = wi[6:0];
                        isctl = op == 7'h6f || (op == 7'h67 && wi[14:12] == 0);
                        if (isctl && (wi[11:7] == 1 || wi[11:7] == 5)) begin g_ras_push = 1; g_ras_val = npc + 64'd4; stop = 1; end
                        else if (op == 7'h67 && wi[14:12] == 0 && wi[11:7] == 0 && (wi[19:15] == 1 || wi[19:15] == 5)) begin
                            g_ras_pop = 1; stop = 1;
                        end
                        if (tkp) stop = 1;
                        g_next = g_pred[s];
                        npc = npc + 64'd4;
                    end
                end
                if (g_n != 0 && q_count + g_n <= Q_N) begin
                    for (s = 0; s < FW; s = s + 1) if (s < g_n) begin
                        j = (q_tail + s) % Q_N;
                        q_pc[j] = g_pc[s]; q_insn[j] = g_insn[s]; q_pred[j] = g_pred[s]; q_fpred[j] = g_fp[s];
                        q_bhit[j] = g_bh[s]; q_bctr[j] = g_bc[s]; q_fault[j] = g_fault[s]; q_fmis[j] = g_fmis[s];
                        q_rsp[j] = (s == g_n - 1) ? (g_ras_push ? ras_sp + 4'd1 : g_ras_pop ? ras_sp - 4'd1 : ras_sp) : ras_sp;
                    end
                    q_tail = q_tail + g_n; q_count = q_count + g_n;
                    if (g_ras_push) begin ras_sp = ras_sp + 1; ras[ras_sp] = g_ras_val; end
                    else if (g_ras_pop) ras_sp = ras_sp - 1;
                    if (g_fault[0]) begin f_hold = 1; f_err = 0; end   // wait for a redirect after a fault
                    else f_pc = g_next;
                end
            end
            end

        end
    end
endmodule
