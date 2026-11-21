// SPDX-License-Identifier: MIT
// Original CPU foundation, out-of-order implementation (added in architecture 0.9.0).
// RV64IM + B execution, serialized FENCE.I, terminal EEI. Same module name, ports and
// architectural contract as rv64_core.sv and rv64_pipe.sv; build with one of the
// three files, never more. Architecture version: cpu/VERSION, cpu/architecture.md
// section 9. No RVA23 compliance claim. See cpu/architecture.md and cpu/README.md.
module rv64_core #(
    parameter [63:0] RESET_PC = 64'h0,
    // Direct-mapped instruction cache size in 8-byte beats; power of two, >= 2.
    parameter integer ICACHE_BEATS = 512,
    // Direct-mapped write-through data cache size in 8-byte beats; power of two, >= 2.
    parameter integer DCACHE_BEATS = 512
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
    output reg [63:0]  retire3_next_pc
);
    // Out-of-order core, after the principles of large out-of-order cores scaled to an
    // FPGA. Since 0.9.2 it is two-wide: F fetches up to two instructions from an
    // aligned beat, D checks both predictions, two instructions are renamed onto 64
    // physical registers per clock into a 32-entry reorder buffer and an 8-entry issue
    // queue, three ports execute (a full integer port with branches and a multiply/
    // divide unit behind it, a second integer port for simple integer and B
    // operations, a load/store port), and two instructions retire per clock.
    //   F  instruction cache (registered read), two BTB lookups, return stack;
    //   fetch queue (8 entries);
    //   D  two slots: prediction check and redirect; rename and dispatch;
    //   integer ports: select, then read physical registers and execute;
    //   load/store port: select, address and data-cache read, then tag check, store
    //   forwarding or a bus access;
    //   retire: up to two per clock from the ROB head; stores write the bus here.
    // A load issues once every older store has its address and data; it takes the
    // data of the youngest older store to its beat when that store covers its bytes,
    // and otherwise (partial overlap) waits for those stores to retire and reads the
    // bus. A mispredicted branch redirects fetch when it executes; rename waits until
    // it retires, then the younger instructions are discarded and the map restored.
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
    localparam integer ROB_N = 32;
    localparam integer IQ_N = 8;
    integer i, k;
    // Registers used before their main section.
    reg div_early_r;
    reg [63:0] div_early_val;
    reg e_mdu_pending;  // an M instruction is in the execute stage (unit not yet busy)
    reg ld_active;      // a load-miss request was presented and has not completed
    reg mp_pending;     // a mispredicted branch has redirected fetch; rename waits for it
    reg [4:0] mp_rob;

    reg halted;
    reg started;  // one clock after reset, fetch begins

    // ---------------- physical registers and maps -------------------------------
    // Physical register 0 is architectural x0 forever (always zero, never freed).
    reg [63:0] prf [0:63];
    reg [63:0] prf_ready;
    reg [5:0] rat [0:31];    // speculative map, updated at rename
    reg [5:0] rrat [0:31];   // retirement map
    reg [63:0] free_mask;

    // ---------------- full integer port, execute stage (named as in the other cores)
    reg e_valid;
    reg [63:0] pc;
    reg [31:0] insn;
    reg [5:0] e_ps1, e_ps2, e_pdst;
    reg [4:0] e_rob;
    reg [63:0] e_pred, e_alt;
    reg e_ptaken, e_writes;
    wire [6:0] op = insn[6:0];
    wire [2:0] f3 = insn[14:12];
    wire [6:0] f7 = insn[31:25];
    wire [4:0] rd = insn[11:7];
    wire [4:0] rs1 = insn[19:15];
    wire [4:0] rs2 = insn[24:20];
    wire [63:0] a = prf[e_ps1];
    wire [63:0] b = prf[e_ps2];
    wire [63:0] imm_i = {{52{insn[31]}},insn[31:20]};
    wire [63:0] imm_s = {{52{insn[31]}},insn[31:25],insn[11:7]};
    wire [63:0] imm_b = {{51{insn[31]}},insn[31],insn[7],insn[30:25],insn[11:8],1'b0};
    wire [63:0] imm_u = {{32{insn[31]}},insn[31:12],12'b0};
    wire [63:0] imm_j = {{43{insn[31]}},insn[31],insn[19:12],insn[20],insn[30:21],1'b0};

    reg legal, write_rd, load_op, store_op, branch_taken, exception;
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
    wire [64:0] bm0 = bitmanip(insn, a, b);
    reg [63:0] result, next_pc, effective_addr, exception_cause, exception_tval;
    reg [31:0] word_result;
    reg [7:0] byte_mask;
    reg [63:0] access_mask;

    // M extension (0.4.0). Multiply and divide operands are registered as the
    // instruction enters M, so neither unit follows forwarding in the same clock.
    // The product is taken in M's first clock (0.7.1). A divide's first M clock
    // completes divide-by-zero, signed overflow and a dividend smaller than the
    // divisor, or sets up the shift-subtract loop, which then runs one step per clock
    // from the quotient's highest possible bit (clz difference + 1 steps).
    wire m_op = (op == 7'h33 || op == 7'h3b) && f7 == 7'h01;
    wire m_word = op == 7'h3b;
    wire is_div = m_op && f3[2];
    reg [63:0] dv_a, dv_b;   // divide operands, registered as the divide enters M
    reg [2:0] dv_f3;
    reg dv_word, div_setup;
    wire div_signed = !dv_f3[0];
    wire want_rem = dv_f3[1];
    wire [63:0] sext_a32 = {{32{dv_a[31]}},dv_a[31:0]};
    wire [63:0] da = dv_word ? (div_signed ? sext_a32 : {32'b0,dv_a[31:0]}) : dv_a;
    wire [63:0] db = dv_word ? (div_signed ? {{32{dv_b[31]}},dv_b[31:0]} : {32'b0,dv_b[31:0]}) : dv_b;
    wire neg_a = div_signed && da[63];
    wire neg_b = div_signed && db[63];
    wire [63:0] mag_a = neg_a ? 64'd0 - da : da;
    wire [63:0] mag_b = neg_b ? 64'd0 - db : db;
    wire div_by_zero = db == 0;
    wire div_overflow = div_signed && da == (dv_word ? 64'hffffffff80000000 : 64'h8000000000000000) && db == {64{1'b1}};
    wire div_early = div_by_zero || div_overflow || mag_a < mag_b;  // decided in M's first clock
    wire mul_a_signed = f3 == 1 || f3 == 2;
    wire mul_b_signed = f3 == 1;
    wire signed [64:0] mul_a = {mul_a_signed & a[63], a};
    wire signed [64:0] mul_b = {mul_b_signed & b[63], b};
    reg [63:0] m_result;
    function automatic [6:0] clz64(input [63:0] value);
        integer k;
        begin
            clz64 = 64;
            for (k = 0; k < 64; k = k + 1) if (value[k]) clz64 = 63 - k;
        end
    endfunction
    function automatic [63:0] div_finish(input [63:0] q, input [63:0] r, input nq, input nr,
                                         input rem_wanted, input word);
        reg [63:0] v;
        begin
            v = rem_wanted ? (nr ? 64'd0 - r : r) : (nq ? 64'd0 - q : q);
            div_finish = word ? {{32{v[31]}},v[31:0]} : v;
        end
    endfunction

    // A divide's early result (when div_early), from the registered operands.
    always @* begin
        if (div_by_zero) m_result = want_rem ? (dv_word ? sext_a32 : dv_a) : {64{1'b1}};
        else if (div_overflow) m_result = want_rem ? 64'b0 : da;
        else m_result = div_finish(64'b0, mag_a, neg_a ^ neg_b, neg_a, want_rem, dv_word);
    end
    wire mul_start = m_op && !f3[2];
    reg signed [64:0] mul_op_a, mul_op_b;
    reg mul_high, mul_word;
    wire signed [129:0] product = mul_op_a * mul_op_b;
    wire [63:0] mul_value = mul_high ? product[127:64]
                          : mul_word ? {{32{product[31]}},product[31:0]} : product[63:0];
    reg [63:0] div_rem, div_den, div_quot, div_bit;
    reg div_neg_q, div_neg_r, div_want_rem, div_is_word;
    wire div_take = div_rem >= div_den;
    wire [63:0] div_rem_next = div_take ? div_rem - div_den : div_rem;
    wire [63:0] div_quot_next = div_take ? div_quot | div_bit : div_quot;

    always @* begin
        legal=1; write_rd=0; load_op=0; store_op=0; branch_taken=0;
        exception=0; exception_cause=0; exception_tval=0;
        result=0; word_result=0; next_pc=pc+64'd4; effective_addr=0;
        byte_mask=0; access_mask=0;
        case (op)
            7'h37: begin write_rd=1; result=imm_u; end // LUI sign extends on RV64
            7'h17: begin write_rd=1; result=pc+imm_u; end
            7'h6f: begin write_rd=1; result=pc+4; next_pc=pc+imm_j; end
            7'h67: begin
                legal=f3==0; write_rd=1; result=pc+4;
                next_pc=(a+imm_i)&~64'd1;
            end
            7'h63: begin
                case (f3)
                    0: branch_taken=a==b;
                    1: branch_taken=a!=b;
                    4: branch_taken=$signed(a)<$signed(b);
                    5: branch_taken=$signed(a)>=$signed(b);
                    6: branch_taken=a<b;
                    7: branch_taken=a>=b;
                    default: legal=0;
                endcase
                if (branch_taken) next_pc=pc+imm_b;
            end
            7'h13: begin
                write_rd=1;
                case (f3)
                    0: result=a+imm_i;
                    2: result={63'b0,$signed(a)<$signed(imm_i)};
                    3: result={63'b0,a<imm_i};
                    4: result=a^imm_i;
                    6: result=a|imm_i;
                    7: result=a&imm_i;
                    1: begin legal=insn[31:26]==0; result=a<<insn[25:20]; end
                    5: begin
                        legal=insn[31:26]==0 || insn[31:26]==6'h10;
                        if (insn[30]) result=$signed(a)>>>insn[25:20];
                        else result=a>>insn[25:20];
                    end
                endcase
            end
            7'h33: begin
                write_rd=1;
                legal=f7==0 || (f7==7'h20 && (f3==0 || f3==5)) || f7==7'h01;
                case (f3)
                    0: result=insn[30] ? a-b : a+b;
                    1: result=a<<b[5:0];
                    2: result={63'b0,$signed(a)<$signed(b)};
                    3: result={63'b0,a<b};
                    4: result=a^b;
                    5: if (insn[30]) result=$signed(a)>>>b[5:0]; else result=a>>b[5:0];
                    6: result=a|b;
                    7: result=a&b;
                endcase
                if (f7==7'h01) result=0;  // multiply and divide complete in M
            end
            7'h1b: begin
                write_rd=1;
                case (f3)
                    0: word_result=a[31:0]+imm_i[31:0];
                    1: begin legal=f7==0; word_result=a[31:0]<<insn[24:20]; end
                    5: begin
                        legal=f7==0 || f7==7'h20;
                        if (insn[30]) word_result=$signed(a[31:0])>>>insn[24:20];
                        else word_result=a[31:0]>>insn[24:20];
                    end
                    default: legal=0;
                endcase
                result={{32{word_result[31]}},word_result};
            end
            7'h3b: begin
                write_rd=1;
                case (f3)
                    0: word_result=insn[30] ? a[31:0]-b[31:0] : a[31:0]+b[31:0];
                    1: word_result=a[31:0]<<b[4:0];
                    5: if (insn[30]) word_result=$signed(a[31:0])>>>b[4:0]; else word_result=a[31:0]>>b[4:0];
                    default: word_result=0;
                endcase
                result={{32{word_result[31]}},word_result};
                // RV64I word ops, plus mulw/divw/divuw/remw/remuw (M, 0.4.0).
                legal=(f7==0 && (f3==0 || f3==1 || f3==5)) || (f7==7'h20 && (f3==0 || f3==5)) ||
                      (f7==7'h01 && (f3==0 || f3[2]));
                if (f7==7'h01) result=0;  // multiply and divide complete in M
            end
            7'h03,7'h23: begin
                load_op=op==7'h03; store_op=op==7'h23;
                effective_addr=a+(load_op ? imm_i : imm_s);
                legal=load_op ? f3!=7 : f3<4;
                case (f3[1:0])
                    0: begin byte_mask=8'h01; access_mask=0; end
                    1: begin byte_mask=8'h03; access_mask=1; end
                    2: begin byte_mask=8'h0f; access_mask=3; end
                    3: begin byte_mask=8'hff; access_mask=7; end
                endcase
                if ((effective_addr & access_mask)!=0) begin
                    exception=1; exception_cause=load_op ? 4 : 6;
                    exception_tval=effective_addr;
                end
            end
            7'h0f: begin
                // No caches, prefetch or posted writes: both fences serialize.
                legal=f3==0 || f3==1;
            end
            7'h73: begin
                exception=1;
                if (insn==32'h00000073) exception_cause=11; // laboratory M-origin ECALL
                else if (insn==32'h00100073) exception_cause=3;
                else legal=0;
            end
            default: legal=0;
        endcase
        if ((op==7'h13 || op==7'h1b || op==7'h33 || op==7'h3b) && bm0[64]) begin
            legal=1; write_rd=1; result=bm0[63:0];  // B extension (0.6.0)
        end
        if (!legal) begin
            exception=1; exception_cause=2; exception_tval={32'b0,insn};
        end else if (next_pc[1:0]!=0) begin
            exception=1; exception_cause=0; exception_tval=next_pc;
        end
    end

    // Simple integer and B operations for the second integer port (from rv64_core.sv).
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

    // ---------------- second integer port, execute stage ------------------------
    reg x1_valid, x1_writes;
    reg [63:0] x1_pc;
    reg [31:0] x1_insn;
    reg [5:0] x1_ps1, x1_ps2, x1_pdst;
    reg [4:0] x1_rob;
    wire [66:0] x1_out = simple_alu(x1_insn, prf[x1_ps1], prf[x1_ps2], x1_pc);
    wire [63:0] x1_result = x1_out[63:0];

    // ---------------- caches -------------------------------------------------------
    reg [ICACHE_BEATS-1:0] ic_valid;
    reg [IC_TAG-1:0] ic_tag [0:ICACHE_BEATS-1];
    reg [IC_TAG-1:0] ic_tag2 [0:ICACHE_BEATS-1];  // copy read for the retiring store
    reg [63:0] ic_data [0:ICACHE_BEATS-1];
    reg [IC_TAG-1:0] ic_tq, ic_sq;
    reg [63:0] ic_q;
    reg [DCACHE_BEATS-1:0] dc_valid;
    reg [DC_TAG-1:0] dc_tag [0:DCACHE_BEATS-1];
    reg [DC_TAG-1:0] dc_tag2 [0:DCACHE_BEATS-1];  // copy read for the retiring store
    reg [63:0] dc_data [0:DCACHE_BEATS-1];
    reg [DC_TAG-1:0] dq_tag, ds_tag;
    reg [63:0] dq_data;

    // ---------------- F stage -----------------------------------------------------
    reg f_valid;
    reg [63:0] f_pc;
    reg fetch_active;
    reg [63:0] fetch_addr;
    wire [IC_INDEX-1:0] f_idx = f_pc[3 +: IC_INDEX];
    wire f_misaligned = f_pc[1:0] != 0;
    wire f_hit = ic_valid[f_idx] && ic_tq == f_pc[63 -: IC_TAG];
    localparam integer BTB_BITS = 8;
    localparam integer BTB_TAG = 10;
    localparam integer BTB_ENTRIES = 1 << BTB_BITS;
    reg [BTB_ENTRIES-1:0] btb_valid, btb_ret;
    reg [BTB_TAG-1:0] btb_tag [0:BTB_ENTRIES-1];
    reg [29:0] btb_target [0:BTB_ENTRIES-1];
    reg [1:0] btb_ctr [0:BTB_ENTRIES-1];
    reg [63:0] ras [0:3];
    reg [1:0] ras_sp;
    wire [63:0] f_pc1 = {f_pc[63:3],3'b100};   // second instruction of an aligned beat
    wire [BTB_BITS-1:0] f_bidx = f_pc[2 +: BTB_BITS];
    wire [BTB_BITS-1:0] f_bidx1 = f_pc1[2 +: BTB_BITS];
    wire f_bhit = btb_valid[f_bidx] && btb_tag[f_bidx] == f_pc[2+BTB_BITS +: BTB_TAG];
    wire f_bhit1 = btb_valid[f_bidx1] && btb_tag[f_bidx1] == f_pc1[2+BTB_BITS +: BTB_TAG];
    wire f_btaken = f_bhit && (btb_ret[f_bidx] || btb_ctr[f_bidx][1]);
    wire f_btaken1 = f_bhit1 && (btb_ret[f_bidx1] || btb_ctr[f_bidx1][1]);

    // ---------------- D stage: two slots ------------------------------------------
    reg d0_valid, d0_fault, d0_fpred, d0_bhit, d0_red;
    reg [1:0] d0_fcause, d0_bctr;
    reg [63:0] d0_pc, d0_pred;
    reg [31:0] d0_insn;
    wire [6:0] d0_op = d0_insn[6:0];
    wire [4:0] d0_rd = d0_insn[11:7];
    wire [4:0] d0_rs1 = d0_insn[19:15];
    wire [4:0] d0_rs2 = d0_insn[24:20];
    wire d0_jal = d0_op == 7'h6f;
    wire d0_branch = d0_op == 7'h63;
    wire d0_jalr = d0_op == 7'h67;
    wire d0_back = d0_branch && d0_insn[31];
    wire [63:0] d0_offset = d0_jal ? {{43{d0_insn[31]}},d0_insn[31],d0_insn[19:12],d0_insn[20],d0_insn[30:21],1'b0}
                                   : {{51{d0_insn[31]}},d0_insn[31],d0_insn[7],d0_insn[30:25],d0_insn[11:8],1'b0};
    wire [63:0] d0_target = d0_pc + d0_offset;
    wire d0_take_pred = (d0_jal || (d0_branch && (d0_fpred || d0_back))) && d0_target[1:0] == 0;
    wire [63:0] d0_seq = d0_pc + 64'd4;
    wire [63:0] d0_want = d0_jalr ? d0_pred : d0_take_pred ? d0_target : d0_seq;
    wire d0_mismatch = d0_valid && !d0_fault && d0_want != d0_pred;
    wire d0_load = d0_op == 7'h03;
    wire d0_store = d0_op == 7'h23;
    wire d0_mem = (d0_load || d0_store) && !d0_fault;
    wire d0_writes = !d0_fault && d0_rd != 0 && (d0_op == 7'h37 || d0_op == 7'h17 || d0_op == 7'h6f || d0_op == 7'h67 ||
                     d0_op == 7'h13 || d0_op == 7'h1b || d0_op == 7'h33 || d0_op == 7'h3b || d0_op == 7'h03);
    wire d0_uses1 = !(d0_op == 7'h37 || d0_op == 7'h17 || d0_op == 7'h6f);
    wire d0_uses2 = d0_op == 7'h33 || d0_op == 7'h3b || d0_op == 7'h63 || d0_op == 7'h23;
    wire d0_mdu = (d0_op == 7'h33 || d0_op == 7'h3b) && d0_insn[31:25] == 7'h01;
    wire [66:0] d0_sa = simple_alu(d0_insn, 64'b0, 64'b0, 64'b0);
    wire d0_simple = !d0_fault && d0_sa[66];  // the second integer port can execute it

    reg d1_valid, d1_fault, d1_fpred, d1_bhit, d1_red;
    reg [1:0] d1_fcause, d1_bctr;
    reg [63:0] d1_pc, d1_pred;
    reg [31:0] d1_insn;
    wire [6:0] d1_op = d1_insn[6:0];
    wire [4:0] d1_rd = d1_insn[11:7];
    wire [4:0] d1_rs1 = d1_insn[19:15];
    wire [4:0] d1_rs2 = d1_insn[24:20];
    wire d1_jal = d1_op == 7'h6f;
    wire d1_branch = d1_op == 7'h63;
    wire d1_jalr = d1_op == 7'h67;
    wire d1_back = d1_branch && d1_insn[31];
    wire [63:0] d1_offset = d1_jal ? {{43{d1_insn[31]}},d1_insn[31],d1_insn[19:12],d1_insn[20],d1_insn[30:21],1'b0}
                                   : {{51{d1_insn[31]}},d1_insn[31],d1_insn[7],d1_insn[30:25],d1_insn[11:8],1'b0};
    wire [63:0] d1_target = d1_pc + d1_offset;
    wire d1_take_pred = (d1_jal || (d1_branch && (d1_fpred || d1_back))) && d1_target[1:0] == 0;
    wire [63:0] d1_seq = d1_pc + 64'd4;
    wire [63:0] d1_want = d1_jalr ? d1_pred : d1_take_pred ? d1_target : d1_seq;
    wire d1_mismatch = d1_valid && !d1_fault && d1_want != d1_pred;
    wire d1_load = d1_op == 7'h03;
    wire d1_store = d1_op == 7'h23;
    wire d1_mem = (d1_load || d1_store) && !d1_fault;
    wire d1_writes = !d1_fault && d1_rd != 0 && (d1_op == 7'h37 || d1_op == 7'h17 || d1_op == 7'h6f || d1_op == 7'h67 ||
                     d1_op == 7'h13 || d1_op == 7'h1b || d1_op == 7'h33 || d1_op == 7'h3b || d1_op == 7'h03);
    wire d1_uses1 = !(d1_op == 7'h37 || d1_op == 7'h17 || d1_op == 7'h6f);
    wire d1_uses2 = d1_op == 7'h33 || d1_op == 7'h3b || d1_op == 7'h63 || d1_op == 7'h23;
    wire d1_mdu = (d1_op == 7'h33 || d1_op == 7'h3b) && d1_insn[31:25] == 7'h01;
    wire [66:0] d1_sa = simple_alu(d1_insn, 64'b0, 64'b0, 64'b0);
    wire d1_simple = !d1_fault && d1_sa[66];  // the second integer port can execute it


    // ---------------- fetch queue -------------------------------------------------
    reg [63:0] q_pc [0:7];
    reg [31:0] q_insn [0:7];
    reg [63:0] q_pred [0:7];
    reg [7:0] q_fpred, q_bhit, q_fault, q_fmis, q_used;
    reg [1:0] q_bctr [0:7];
    reg [2:0] q_head, q_tail;
    reg [3:0] q_count;
    wire [2:0] q_head1 = q_head + 3'd1;

    // ---------------- reorder buffer ----------------------------------------------
    reg [ROB_N-1:0] rob_done, rob_exc, rob_store, rob_load, rob_fencei, rob_writes, rob_mp;
    reg [ROB_N-1:0] rob_ctl, rob_taken, rob_ret, rob_bhit;
    reg [1:0] rob_bctr [0:ROB_N-1];
    reg [63:0] rob_pc [0:ROB_N-1];
    reg [31:0] rob_insn [0:ROB_N-1];
    reg [63:0] rob_next [0:ROB_N-1];
    reg [4:0] rob_rd [0:ROB_N-1];
    reg [5:0] rob_pdst [0:ROB_N-1];
    reg [5:0] rob_opdst [0:ROB_N-1];
    reg [63:0] rob_value [0:ROB_N-1];
    reg [63:0] rob_cause [0:ROB_N-1];
    reg [63:0] rob_tval [0:ROB_N-1];
    reg [63:0] rob_addr [0:ROB_N-1];   // store address
    reg [63:0] rob_wdata [0:ROB_N-1];  // store data, shifted to its lanes
    reg [7:0] rob_wstrb [0:ROB_N-1];
    reg [4:0] rob_head, rob_tail;
    reg [5:0] rob_count;
    reg [ROB_N-1:0] rob_live;  // entries holding instructions
    wire [4:0] rob_tail1 = rob_tail + 5'd1;

    // ---------------- issue queue -------------------------------------------------
    reg [IQ_N-1:0] iq_valid, iq_r1, iq_r2, iq_mem, iq_load, iq_mdu, iq_ptaken, iq_writes, iq_simple;
    reg [4:0] iq_rob [0:IQ_N-1];
    reg [63:0] iq_pc [0:IQ_N-1];
    reg [31:0] iq_insn [0:IQ_N-1];
    reg [5:0] iq_ps1 [0:IQ_N-1];
    reg [5:0] iq_ps2 [0:IQ_N-1];
    reg [5:0] iq_pdst [0:IQ_N-1];
    reg [63:0] iq_pred [0:IQ_N-1];
    reg [63:0] iq_alt [0:IQ_N-1];

    // ---------------- multiply/divide unit -----------------------------------------
    reg md_busy, md_mul;
    reg [5:0] md_pdst;
    reg [4:0] md_rob;
    reg md_writes;
    wire md_done = md_busy && (md_mul || (!div_setup && (div_early_r || div_bit == 64'd1)));
    wire [63:0] md_value = md_mul ? mul_value
                         : div_early_r ? div_early_val
                         : div_finish(div_quot_next,div_rem_next,div_neg_q,div_neg_r,div_want_rem,div_is_word);

    // ---------------- load/store port ---------------------------------------------
    // L1: address and data-cache read; L2: tag check, store forwarding, or the bus.
    reg l1_valid, l1_load, l2_valid, l2_load, l2_exc, l2_dead;
    reg [31:0] l1_insn;
    reg [5:0] l1_ps1, l1_ps2, l1_pdst, l2_pdst;
    reg [4:0] l1_rob, l2_rob;
    reg l1_writes, l2_writes;
    reg [63:0] l2_addr, l2_cause, l2_tval;
    reg [2:0] l2_f3;
    reg [7:0] l2_bytes;   // the load's bytes within its beat
    reg l2_force;         // an older store overlapped partly: read the bus
    wire [63:0] l1_a = prf[l1_ps1];
    wire [63:0] l1_b = prf[l1_ps2];
    wire [2:0] l1_f3 = l1_insn[14:12];
    wire [63:0] l1_imm = l1_load ? {{52{l1_insn[31]}},l1_insn[31:20]} : {{52{l1_insn[31]}},l1_insn[31:25],l1_insn[11:7]};
    wire [63:0] l1_ea = l1_a + l1_imm;
    wire [2:0] l1_mask = l1_f3[1:0] == 0 ? 3'd0 : l1_f3[1:0] == 1 ? 3'd1 : l1_f3[1:0] == 2 ? 3'd3 : 3'd7;
    wire l1_illegal = l1_load ? l1_f3 == 3'd7 : l1_f3[2];
    wire l1_misaligned = (l1_ea[2:0] & l1_mask) != 0;
    wire [7:0] l1_bytes = l1_f3[1:0] == 0 ? 8'h01 : l1_f3[1:0] == 1 ? 8'h03 : l1_f3[1:0] == 2 ? 8'h0f : 8'hff;
    wire [DC_INDEX-1:0] l1_idx = l1_ea[3 +: DC_INDEX];
    wire [DC_INDEX-1:0] l2_idx = l2_addr[3 +: DC_INDEX];
    wire l2_hit = dc_valid[l2_idx] && dq_tag == l2_addr[63 -: DC_TAG] && !l2_force;
    // Older stores waiting to retire that write the load's beat; the youngest wins.
    wire [4:0] l2_age = l2_rob - rob_head;
    reg fwd_hit;
    reg [4:0] fwd_idx;
    reg [4:0] fwd_scan;
    always @* begin
        fwd_hit = 0; fwd_idx = 0;
        for (k = 0; k < ROB_N; k = k + 1) begin
            fwd_scan = rob_head + k[4:0];
            if (k[4:0] < l2_age && rob_live[fwd_scan] && rob_store[fwd_scan] &&
                rob_addr[fwd_scan][63:3] == l2_addr[63:3] && (rob_wstrb[fwd_scan] & l2_bytes) != 0) begin
                fwd_hit = 1; fwd_idx = fwd_scan;
            end
        end
    end
    wire fwd_full = fwd_hit && ((rob_wstrb[fwd_idx] & l2_bytes) == l2_bytes);
    // Oldest store without its address and data yet: younger loads wait for it.
    reg ou_valid;
    reg [4:0] ou_age;
    always @* begin
        ou_valid = 0; ou_age = 0;
        for (k = ROB_N-1; k >= 0; k = k - 1)
            if (rob_live[rob_head + k[4:0]] && rob_store[rob_head + k[4:0]] && !rob_done[rob_head + k[4:0]]) begin
                ou_valid = 1; ou_age = k[4:0];
            end
    end

    function automatic [63:0] load_align(input [63:0] beat, input [2:0] lane, input [2:0] size);
        reg [63:0] s;
        begin
            s = beat >> {lane,3'b000};
            case (size)
                3'b000: load_align = {{56{s[7]}},s[7:0]};
                3'b001: load_align = {{48{s[15]}},s[15:0]};
                3'b010: load_align = {{32{s[31]}},s[31:0]};
                3'b011: load_align = s;
                3'b100: load_align = {56'b0,s[7:0]};
                3'b101: load_align = {48'b0,s[15:0]};
                3'b110: load_align = {32'b0,s[31:0]};
                default: load_align = 64'b0;
            endcase
        end
    endfunction

    // ---------------- retirement and bus ------------------------------------------
    wire [4:0] h = rob_head;
    wire [4:0] h1 = rob_head + 5'd1;
    wire h_valid = rob_count != 0;
    wire h_store = h_valid && rob_done[h] && !rob_exc[h] && rob_store[h];
    wire [63:0] h_addr = rob_addr[h];
    wire [DC_INDEX-1:0] h_dc_idx = h_addr[3 +: DC_INDEX];
    wire [IC_INDEX-1:0] h_ic_idx = h_addr[3 +: IC_INDEX];
    // Bus: the retiring store first, then a load miss, then a fetch; a presented
    // request is held until it completes.
    wire l2_miss = l2_valid && l2_load && !l2_exc && !fwd_hit && !l2_hit;
    // The retiring store's cache tags are read one clock ahead (ds_tag, ic_sq); ds_ok
    // says that read was for this head after its address was known.
    reg ds_ok;
    wire h_exc = h_valid && rob_done[h] && rob_exc[h];
    wire st_req = h_store && ds_ok && !fetch_active && !ld_active && !halted;
    wire ld_req = !fetch_active && !halted && (ld_active || (l2_miss && !h_store && !h_exc));
    wire f_want = f_valid && started && !halted && !f_misaligned && !f_hit;
    wire fetch_req = !halted && (fetch_active || (f_want && !h_store && !l2_miss && !h_exc));
    wire [63:0] fetch_beat = fetch_active ? fetch_addr : {f_pc[63:3],3'b000};
    wire data_req = st_req || ld_req;
    assign mem_valid = !reset && (fetch_req || data_req);
    assign mem_instr = fetch_req;
    assign mem_addr = fetch_req ? fetch_beat : ld_req ? {l2_addr[63:3],3'b000} : {h_addr[63:3],3'b000};
    assign mem_wdata = (fetch_req || ld_req) ? 64'b0 : rob_wdata[h];
    assign mem_wstrb = (fetch_req || ld_req) ? 8'b0 : rob_wstrb[h];
    wire fetch_done = fetch_req && mem_ready;
    wire fill = fetch_done && !mem_error;
    wire [IC_INDEX-1:0] fill_idx = fetch_beat[3 +: IC_INDEX];
    wire fetch_for_f = fetch_done && f_valid && fetch_beat[63:3] == f_pc[63:3];
    wire st_done = st_req && mem_ready;
    wire ld_done = ld_req && mem_ready;

    // F output: up to two instructions (the second only from an aligned beat, and not
    // after a predicted-taken transfer, a call or a return, or a fault).
    wire [63:0] f_beat = fetch_for_f ? mem_rdata : ic_q;
    wire [31:0] f_word = f_pc[2] ? f_beat[63:32] : f_beat[31:0];
    wire [31:0] f_word1 = f_beat[63:32];
    wire f_fault = f_misaligned || (fetch_for_f && mem_error);
    wire f_ready = f_valid && started && !halted && (f_misaligned || f_hit || fetch_for_f);
    wire [6:0] f_op = f_word[6:0];
    wire f_jump = f_op == 7'h6f || (f_op == 7'h67 && f_word[14:12] == 0);
    wire f_call = f_jump && (f_word[11:7] == 1 || f_word[11:7] == 5);
    wire f_return = f_op == 7'h67 && f_word[14:12] == 0 && f_word[11:7] == 0 &&
                    (f_word[19:15] == 1 || f_word[19:15] == 5);
    wire [6:0] f_op1 = f_word1[6:0];
    wire f_jump1 = f_op1 == 7'h6f || (f_op1 == 7'h67 && f_word1[14:12] == 0);
    wire f_call1 = f_jump1 && (f_word1[11:7] == 1 || f_word1[11:7] == 5);
    wire f_return1 = f_op1 == 7'h67 && f_word1[14:12] == 0 && f_word1[11:7] == 0 &&
                     (f_word1[19:15] == 1 || f_word1[19:15] == 5);
    wire [63:0] f_btarget = btb_ret[f_bidx] ? ras[ras_sp] : {f_pc[63:32],btb_target[f_bidx],2'b00};
    wire [63:0] f_btarget1 = btb_ret[f_bidx1] ? ras[ras_sp] : {f_pc1[63:32],btb_target[f_bidx1],2'b00};
    wire [63:0] f_pred = f_btaken ? f_btarget : f_pc + 64'd4;
    wire [63:0] f_pred1 = f_btaken1 ? f_btarget1 : f_pc1 + 64'd4;
    wire f_two = !f_pc[2] && !f_fault && !f_btaken && !f_call && !f_return;

    // L2 completes: a hit now, forwarding, or a miss when its bus read returns.
    wire [63:0] l2_beat = fwd_full ? rob_wdata[fwd_idx] : l2_hit ? dq_data : mem_rdata;
    wire [63:0] l2_value = load_align(l2_beat, l2_addr[2:0], l2_f3);
    wire l2_done = l2_valid && (l2_exc || fwd_full || (!fwd_hit && l2_hit) || ld_done);
    wire l2_fault = ld_done && mem_error;

    // Retirement: the head, and the next entry when it needs nothing special.
    wire h_ready = h_valid && rob_done[h];
    wire st_fault = st_done && mem_error;
    wire h_trap = h_ready && (rob_exc[h] || st_fault) && !fetch_active && !ld_active && !halted;
    wire retire = h_ready && !rob_exc[h] && !halted && (!rob_store[h] || (st_done && !mem_error));
    // A retiring store to the beat of any younger fetched instruction, a fence.i, or
    // a mispredicted branch discards everything younger.
    reg younger_beat;
    always @* begin
        younger_beat = (d0_valid && d0_pc[63:3] == h_addr[63:3]) || (d1_valid && d1_pc[63:3] == h_addr[63:3]) ||
                       (f_valid && f_pc[63:3] == h_addr[63:3]);
        for (k = 0; k < 8; k = k + 1)
            if (q_used[k] && q_pc[k][63:3] == h_addr[63:3]) younger_beat = 1;
        for (k = 0; k < ROB_N; k = k + 1)
            if (rob_live[k] && k[4:0] != h && rob_pc[k][63:3] == h_addr[63:3]) younger_beat = 1;
    end
    wire flush_back = retire && (rob_mp[h] || rob_fencei[h] || (rob_store[h] && younger_beat));
    wire flush_front = retire && (rob_fencei[h] || (rob_store[h] && younger_beat));
    wire retire1 = retire && !flush_back && rob_count >= 6'd2 && rob_done[h1] && !rob_exc[h1] &&
                   !rob_store[h1] && !rob_fencei[h1] && !rob_mp[h1] && !(rob_ctl[h] && rob_ctl[h1]);

    // ---------------- select ------------------------------------------------------
    // The second integer port takes the lowest-indexed ready simple operation; the full
    // port the lowest-indexed other ready non-memory instruction. Memory instructions
    // issue in program order: the load/store port takes the oldest one, when it is
    // ready (a load also once every older store is known), so a load waiting for older
    // stores to retire never blocks an older memory instruction.
    reg sel_valid, sel1_valid, msel_valid, mem_any;
    reg [2:0] sel, sel1, msel;
    reg [4:0] mem_age;
    always @* begin
        sel1_valid = 0; sel1 = 0;
        for (k = IQ_N-1; k >= 0; k = k - 1)
            if (iq_valid[k] && !iq_mem[k] && iq_simple[k] && iq_r1[k] && iq_r2[k]) begin
                sel1_valid = 1; sel1 = k[2:0];
            end
        sel_valid = 0; sel = 0;
        for (k = IQ_N-1; k >= 0; k = k - 1)
            if (iq_valid[k] && !iq_mem[k] && iq_r1[k] && iq_r2[k] && !(sel1_valid && sel1 == k[2:0]) &&
                !(iq_mdu[k] && (md_busy || e_mdu_pending))) begin
                sel_valid = 1; sel = k[2:0];
            end
        // Oldest memory instruction in the issue queue.
        mem_any = 0; msel = 0; mem_age = 0;
        for (k = 0; k < IQ_N; k = k + 1)
            if (iq_valid[k] && iq_mem[k] && (!mem_any || iq_rob[k] - rob_head < mem_age)) begin
                mem_any = 1; msel = k[2:0]; mem_age = iq_rob[k] - rob_head;
            end
        msel_valid = mem_any && iq_r1[msel] &&
                     (iq_load[msel] ? (!ou_valid || mem_age < ou_age) : iq_r2[msel]);
    end
    // L1 moves on when it holds a store (which completes there) or L2 is free.
    wire l1_advance = l1_valid && (!l1_load || !l2_valid || l2_done);
    wire msel_go = msel_valid && (!l1_valid || l1_advance) && !flush_back;
    wire wk_alu = sel_valid && iq_writes[sel] && !iq_mdu[sel];
    wire [5:0] wk_alu_tag = iq_pdst[sel];
    wire wk_alu1 = sel1_valid && iq_writes[sel1];
    wire [5:0] wk_alu1_tag = iq_pdst[sel1];
    wire wk_ld = l2_valid && l2_done && !l2_dead && !l2_exc && !l2_fault && l2_writes;
    wire [5:0] wk_ld_tag = l2_pdst;
    wire wk_md = md_done && md_writes;
    wire [5:0] wk_md_tag = md_pdst;
    function automatic woke(input [5:0] tag, input a1, input [5:0] t1, input a2, input [5:0] t2,
                            input a3, input [5:0] t3, input a4, input [5:0] t4);
        woke = (a1 && t1 == tag) || (a2 && t2 == tag) || (a3 && t3 == tag) || (a4 && t4 == tag);
    endfunction
    `define WOKE(t) woke(t, wk_alu, wk_alu_tag, wk_alu1, wk_alu1_tag, wk_ld, wk_ld_tag, wk_md, wk_md_tag)

    // Execute results for the full integer port.
    wire e_branch = op == 7'h63;
    wire e_jalr = op == 7'h67;
    wire [63:0] e_jalr_target = (a + imm_i) & ~64'd1;
    wire e_mispredict = e_valid && !exception && ((e_branch && branch_taken != e_ptaken) ||
                        (e_jalr && e_jalr_target != e_pred));
    wire [63:0] e_fix = e_branch ? e_alt : e_jalr_target;
    // Redirect when no older mispredicted branch is waiting to retire.
    wire [4:0] e_age = e_rob - rob_head;
    wire [4:0] mp_age = mp_rob - rob_head;
    wire e_redirect = e_mispredict && !flush_back && (!mp_pending || e_age < mp_age);

    // ---------------- rename and dispatch (two per clock) -----------------------
    reg [5:0] fp0, fp1;      // lowest and second-lowest free physical registers
    reg [1:0] free_n;        // how many free (saturating at 2)
    always @* begin
        free_n = 0; fp0 = 0; fp1 = 0;
        for (k = 63; k >= 1; k = k - 1) if (free_mask[k]) begin
            fp1 = fp0; fp0 = k[5:0]; free_n = free_n == 2'd2 ? 2'd2 : free_n + 2'd1;
        end
    end
    reg [2:0] is0, is1;      // lowest and second-lowest free issue-queue slots
    reg [1:0] iq_n;
    always @* begin
        iq_n = 0; is0 = 0; is1 = 0;
        for (k = IQ_N-1; k >= 0; k = k - 1) if (!iq_valid[k]) begin
            is1 = is0; is0 = k[2:0]; iq_n = iq_n == 2'd2 ? 2'd2 : iq_n + 2'd1;
        end
    end
    wire [5:0] pdst0 = fp0;
    wire [5:0] pdst1 = d0_writes ? fp1 : fp0;
    wire [5:0] d0_ps1 = (d0_uses1 && d0_rs1 != 0) ? rat[d0_rs1] : 6'd0;
    wire [5:0] d0_ps2 = (d0_uses2 && d0_rs2 != 0) ? rat[d0_rs2] : 6'd0;
    // The second instruction may read what the first writes in the same group.
    wire d1_dep1 = d1_uses1 && d1_rs1 != 0 && d0_writes && d0_rd == d1_rs1;
    wire d1_dep2 = d1_uses2 && d1_rs2 != 0 && d0_writes && d0_rd == d1_rs2;
    wire [5:0] d1_ps1 = !(d1_uses1 && d1_rs1 != 0) ? 6'd0 : d1_dep1 ? pdst0 : rat[d1_rs1];
    wire [5:0] d1_ps2 = !(d1_uses2 && d1_rs2 != 0) ? 6'd0 : d1_dep2 ? pdst0 : rat[d1_rs2];
    wire [5:0] d1_opdst = (d0_writes && d0_rd == d1_rd) ? pdst0 : rat[d1_rd];
    // ---------------- front end control ------------------------------------------
    wire d0_fire_raw = d0_mismatch && !d0_red;
    wire d1_fire_raw = d1_mismatch && !d1_red && !d0_fire_raw;
    wire d_fire = (d0_fire_raw || d1_fire_raw) && !e_redirect && !flush_front && !flush_back;
    wire [63:0] d_fire_pc = d0_fire_raw ? d0_want : d1_want;
    wire kill1 = d_fire && d0_fire_raw;          // d1 followed a wrong prediction
    wire front_kill = flush_front || e_redirect || d_fire || (flush_back && !mp_pending);
    wire back_ok = !mp_pending && !flush_back && !halted && !e_redirect && !flush_front;
    wire go0 = d0_valid && back_ok && rob_count <= 6'd31 && iq_n >= 2'd1 && (free_n >= 2'd1 || !d0_writes);
    wire go1 = go0 && d1_valid && !kill1 && rob_count <= 6'd30 && iq_n >= 2'd2 &&
               (free_n >= ({1'b0,d0_writes} + {1'b0,d1_writes}));
    wire keep0 = d0_valid && !go0;
    wire keep1 = d1_valid && !go1 && !kill1;
    wire [1:0] kept = {1'b0,keep0} + {1'b0,keep1};
    wire [1:0] q_take = front_kill ? 2'd0 : (q_count >= {2'b0, 2'd2 - kept}) ? 2'd2 - kept : q_count[1:0];
    wire f_go = f_ready && q_count <= 4'd6 && !front_kill;
    wire [1:0] q_push = f_go ? (f_two ? 2'd2 : 2'd1) : 2'd0;
    reg [63:0] fetch_next;
    always @* begin
        if (flush_front) fetch_next = rob_next[h];
        else if (e_redirect) fetch_next = e_fix;
        else if (d_fire) fetch_next = d_fire_pc;
        else if (f_go) fetch_next = f_two ? f_pred1 : f_pred;
        else fetch_next = f_pc;
    end
    wire [IC_INDEX-1:0] next_idx = fetch_next[3 +: IC_INDEX];
    // The ROB head after this clock, so the store-check tag copies are read ahead.
    wire [4:0] h_next = rob_head + {4'b0,retire} + {4'b0,retire1};
    wire [63:0] hn_addr = rob_addr[h_next];
    wire [DC_INDEX-1:0] hn_dc_idx = hn_addr[3 +: DC_INDEX];
    wire [IC_INDEX-1:0] hn_ic_idx = hn_addr[3 +: IC_INDEX];
    // Data-cache writes: a load fill (L2 miss returning) or a retiring store that hits.
    wire st_hit = dc_valid[h_dc_idx] && ds_tag == h_addr[63 -: DC_TAG];
    wire dc_fill = ld_done && !mem_error;
    wire dc_st = retire && rob_store[h] && st_hit;
    // The line a retiring store leaves, for a load reading the same line this clock.
    reg [63:0] st_line;
    always @* begin
        st_line = dc_data[h_dc_idx];
        for (k = 0; k < 8; k = k + 1) if (rob_wstrb[h][k]) st_line[8*k +: 8] = rob_wdata[h][8*k +: 8];
    end
    // Free list after discarding younger instructions: every register not mapped by
    // the retirement map (including the instruction retiring this clock).
    reg [63:0] flush_free;
    always @* begin
        flush_free = {64{1'b1}};
        for (k = 0; k < 32; k = k + 1)
            flush_free[(retire && rob_writes[h] && rob_rd[h] == k[4:0]) ? rob_pdst[h] : rrat[k]] = 1'b0;
        flush_free[0] = 1'b0;
    end

    wire [2:0] state = halted ? HALTED : (data_req && !mem_ready) ? MEMORY
                     : (!retire && f_valid && !f_ready) ? FETCH : EXECUTE;

    always @(posedge clk) begin
        // Cache read ports, with a write of the same edge passed through.
        ic_q <= (fill && fill_idx == next_idx) ? mem_rdata : ic_data[next_idx];
        ic_tq <= (fill && fill_idx == next_idx) ? fetch_beat[63 -: IC_TAG] : ic_tag[next_idx];
        ic_sq <= (fill && fill_idx == hn_ic_idx) ? fetch_beat[63 -: IC_TAG] : ic_tag2[hn_ic_idx];
        if (fill) begin
            ic_tag[fill_idx] <= fetch_beat[63 -: IC_TAG];
            ic_tag2[fill_idx] <= fetch_beat[63 -: IC_TAG];
            ic_data[fill_idx] <= mem_rdata;
        end
        if (l1_valid && l1_load && l1_advance) begin
            dq_data <= (dc_fill && l2_idx == l1_idx) ? mem_rdata : (dc_st && h_dc_idx == l1_idx) ? st_line : dc_data[l1_idx];
            dq_tag <= (dc_fill && l2_idx == l1_idx) ? l2_addr[63 -: DC_TAG] : dc_tag[l1_idx];
        end
        ds_tag <= (dc_fill && l2_idx == hn_dc_idx) ? l2_addr[63 -: DC_TAG] : dc_tag2[hn_dc_idx];
        ds_ok <= !reset && rob_live[h_next] && rob_done[h_next] && !(flush_back) &&
                 !(l1_advance && !l1_load && l1_rob == h_next);
        if (dc_fill) begin
            dc_tag[l2_idx] <= l2_addr[63 -: DC_TAG];
            dc_tag2[l2_idx] <= l2_addr[63 -: DC_TAG];
            dc_data[l2_idx] <= mem_rdata;
        end else if (dc_st) begin
            for (k = 0; k < 8; k = k + 1)
                if (rob_wstrb[h][k]) dc_data[h_dc_idx][8*k +: 8] <= rob_wdata[h][8*k +: 8];
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            halted<=0; started<=0;
            f_valid<=0; f_pc<=RESET_PC; fetch_active<=0; fetch_addr<=0; ld_active<=0;
            d0_valid<=0; d0_fault<=0; d0_fpred<=0; d0_bhit<=0; d0_red<=0; d0_fcause<=0; d0_bctr<=0;
            d0_pc<=0; d0_pred<=0; d0_insn<=0;
            d1_valid<=0; d1_fault<=0; d1_fpred<=0; d1_bhit<=0; d1_red<=0; d1_fcause<=0; d1_bctr<=0;
            d1_pc<=0; d1_pred<=0; d1_insn<=0;
            q_head<=0; q_tail<=0; q_count<=0; q_used<=0; q_fpred<=0; q_bhit<=0; q_fault<=0; q_fmis<=0;
            btb_valid<=0; btb_ret<=0; ras_sp<=0; ras[0]<=0; ras[1]<=0; ras[2]<=0; ras[3]<=0;
            ic_valid<=0; dc_valid<=0;
            for (i = 0; i < 64; i = i + 1) prf[i]<=0;
            prf_ready<={64{1'b1}};
            for (i = 0; i < 32; i = i + 1) begin rat[i]<=i[5:0]; rrat[i]<=i[5:0]; end
            free_mask<={{32{1'b1}},32'b0};
            rob_head<=0; rob_tail<=0; rob_count<=0; rob_live<=0; rob_done<=0; rob_mp<=0;
            mp_pending<=0; mp_rob<=0;
            iq_valid<=0;
            e_valid<=0; pc<=0; insn<=0; e_ps1<=0; e_ps2<=0; e_pdst<=0; e_rob<=0; e_pred<=0; e_alt<=0;
            e_ptaken<=0; e_writes<=0; e_mdu_pending<=0;
            x1_valid<=0; x1_writes<=0; x1_pc<=0; x1_insn<=0; x1_ps1<=0; x1_ps2<=0; x1_pdst<=0; x1_rob<=0;
            md_busy<=0; md_mul<=0; md_pdst<=0; md_rob<=0; md_writes<=0;
            mul_op_a<=0; mul_op_b<=0; mul_high<=0; mul_word<=0;
            div_rem<=0; div_den<=0; div_quot<=0; div_bit<=0;
            div_neg_q<=0; div_neg_r<=0; div_want_rem<=0; div_is_word<=0;
            dv_a<=0; dv_b<=0; dv_f3<=0; dv_word<=0; div_setup<=0; div_early_r<=0; div_early_val<=0;
            l1_valid<=0; l1_load<=0; l1_insn<=0; l1_ps1<=0; l1_ps2<=0; l1_pdst<=0; l1_rob<=0; l1_writes<=0;
            l2_valid<=0; l2_load<=0; l2_exc<=0; l2_dead<=0; l2_pdst<=0; l2_rob<=0; l2_writes<=0;
            l2_addr<=0; l2_cause<=0; l2_tval<=0; l2_f3<=0; l2_bytes<=0; l2_force<=0;
            trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_tval<=0;
            retire_valid<=0; retire_pc<=0; retire_insn<=0;
            retire_rd<=0; retire_data<=0; retire_next_pc<=0;
            retire2_valid<=0; retire2_pc<=0; retire2_insn<=0;
            retire2_rd<=0; retire2_data<=0; retire2_next_pc<=0;
            retire3_valid<=0; retire3_pc<=0; retire3_insn<=0;
            retire3_rd<=0; retire3_data<=0; retire3_next_pc<=0;
        end else begin
            retire_valid<=0; retire2_valid<=0;
            if (!started) begin started<=1; f_valid<=1; end
            if (fetch_req) begin
                if (mem_ready) fetch_active<=0;
                else begin fetch_active<=1; fetch_addr<=fetch_beat; end
            end
            if (ld_req) ld_active<=!mem_ready;
            if (fill) ic_valid[fill_idx]<=1'b1;

            if (h_trap) begin
                trap_valid<=1; trap_pc<=rob_pc[h];
                trap_cause<=st_fault ? 64'd7 : rob_cause[h];
                trap_tval<=st_fault ? h_addr : rob_tval[h];
                halted<=1; f_valid<=0;
            end else if (!halted) begin
                // ---------------- retire ----------------
                if (retire) begin
                    retire_valid<=1; retire_pc<=rob_pc[h]; retire_insn<=rob_insn[h];
                    retire_rd<=rob_writes[h] ? rob_rd[h] : 5'd0;
                    retire_data<=rob_writes[h] ? rob_value[h] : 64'b0;
                    retire_next_pc<=rob_next[h];
                    if (rob_writes[h]) begin
                        rrat[rob_rd[h]]<=rob_pdst[h];
                        free_mask[rob_opdst[h]]<=1'b1;
                    end
                    if (rob_store[h] && ic_valid[h_ic_idx] && ic_sq == h_addr[63 -: IC_TAG]) ic_valid[h_ic_idx]<=1'b0;
                    if (rob_fencei[h]) ic_valid<=0;
                    rob_live[h]<=1'b0; rob_done[h]<=1'b0;
                    if (mp_pending && mp_rob == h) mp_pending<=0;
                end
                if (retire1) begin
                    retire2_valid<=1; retire2_pc<=rob_pc[h1]; retire2_insn<=rob_insn[h1];
                    retire2_rd<=rob_writes[h1] ? rob_rd[h1] : 5'd0;
                    retire2_data<=rob_writes[h1] ? rob_value[h1] : 64'b0;
                    retire2_next_pc<=rob_next[h1];
                    if (rob_writes[h1]) begin
                        rrat[rob_rd[h1]]<=rob_pdst[h1];
                        free_mask[rob_opdst[h1]]<=1'b1;
                    end
                    rob_live[h1]<=1'b0; rob_done[h1]<=1'b0;
                end
                rob_head<=h_next;
                // BTB update from the control transfer retiring this clock (at most one).
                if ((retire && rob_ctl[h]) || (retire1 && rob_ctl[h1])) begin : btb_update
                    reg [4:0] c;
                    c = (retire && rob_ctl[h]) ? h : h1;
                    if (rob_taken[c]) begin
                        btb_valid[rob_pc[c][2 +: BTB_BITS]]<=1'b1;
                        btb_tag[rob_pc[c][2 +: BTB_BITS]]<=rob_pc[c][2+BTB_BITS +: BTB_TAG];
                        btb_target[rob_pc[c][2 +: BTB_BITS]]<=rob_next[c][31:2];
                        btb_ret[rob_pc[c][2 +: BTB_BITS]]<=rob_ret[c];
                        btb_ctr[rob_pc[c][2 +: BTB_BITS]]<=!rob_bhit[c] ? 2'd2 :
                            rob_bctr[c]==2'd3 ? 2'd3 : rob_bctr[c]+2'd1;
                    end else if (rob_bhit[c])
                        btb_ctr[rob_pc[c][2 +: BTB_BITS]]<=rob_bctr[c]==2'd0 ? 2'd0 : rob_bctr[c]-2'd1;
                end
                if (dc_fill) dc_valid[l2_idx]<=1'b1;

                // ---------------- issue: integer ports ----------------
                e_valid<=0; x1_valid<=0;
                if (sel_valid && !flush_back) begin
                    iq_valid[sel]<=1'b0;
                    e_valid<=1; pc<=iq_pc[sel]; insn<=iq_insn[sel]; e_ps1<=iq_ps1[sel]; e_ps2<=iq_ps2[sel];
                    e_pdst<=iq_pdst[sel]; e_rob<=iq_rob[sel]; e_pred<=iq_pred[sel]; e_alt<=iq_alt[sel];
                    e_ptaken<=iq_ptaken[sel]; e_writes<=iq_writes[sel];
                    if (wk_alu) prf_ready[wk_alu_tag]<=1'b1;
                end
                if (sel1_valid && !flush_back) begin
                    iq_valid[sel1]<=1'b0;
                    x1_valid<=1; x1_pc<=iq_pc[sel1]; x1_insn<=iq_insn[sel1]; x1_ps1<=iq_ps1[sel1];
                    x1_ps2<=iq_ps2[sel1]; x1_pdst<=iq_pdst[sel1]; x1_rob<=iq_rob[sel1]; x1_writes<=iq_writes[sel1];
                    if (wk_alu1) prf_ready[wk_alu1_tag]<=1'b1;
                end
                e_mdu_pending<=sel_valid && !flush_back && iq_mdu[sel];
                // ---------------- execute: full integer port ----------------
                if (e_valid && !flush_back) begin
                    if (m_op && !exception) begin
                        md_busy<=1; md_mul<=!is_div; md_pdst<=e_pdst; md_rob<=e_rob; md_writes<=e_writes;
                        if (!is_div) begin
                            mul_op_a<=mul_a; mul_op_b<=mul_b; mul_high<=f3!=0; mul_word<=m_word;
                        end else begin
                            dv_a<=a; dv_b<=b; dv_f3<=f3; dv_word<=m_word; div_setup<=1; div_early_r<=0;
                        end
                        rob_next[e_rob]<=next_pc;
                    end else begin
                        if (e_writes) prf[e_pdst]<=result;
                        rob_value[e_rob]<=result; rob_done[e_rob]<=1'b1;
                        rob_exc[e_rob]<=exception; rob_cause[e_rob]<=exception_cause; rob_tval[e_rob]<=exception_tval;
                        rob_next[e_rob]<=next_pc;
                        rob_mp[e_rob]<=e_mispredict;
                        rob_ctl[e_rob]<=!exception && (e_branch || op == 7'h6f || e_jalr);
                        rob_taken[e_rob]<=op == 7'h6f || e_jalr || branch_taken;
                        rob_ret[e_rob]<=e_jalr && rd == 0 && (rs1 == 1 || rs1 == 5);
                        rob_fencei[e_rob]<=op == 7'h0f && f3 == 1 && !exception;
                        if (e_redirect) begin mp_pending<=1; mp_rob<=e_rob; end
                    end
                end
                // ---------------- execute: second integer port ----------------
                if (x1_valid && !flush_back) begin
                    if (x1_writes) prf[x1_pdst]<=x1_result;
                    rob_value[x1_rob]<=x1_result; rob_done[x1_rob]<=1'b1; rob_exc[x1_rob]<=1'b0;
                    rob_next[x1_rob]<=x1_pc + 64'd4;
                    rob_mp[x1_rob]<=1'b0; rob_ctl[x1_rob]<=1'b0; rob_fencei[x1_rob]<=1'b0;
                end
                // ---------------- multiply/divide unit ----------------
                if (md_busy && !flush_back) begin
                    if (md_done) begin
                        md_busy<=0;
                        if (md_writes) begin prf[md_pdst]<=md_value; prf_ready[md_pdst]<=1'b1; end
                        rob_value[md_rob]<=md_value; rob_done[md_rob]<=1'b1; rob_exc[md_rob]<=1'b0;
                        rob_mp[md_rob]<=1'b0; rob_ctl[md_rob]<=1'b0; rob_fencei[md_rob]<=1'b0;
                    end else if (!md_mul) begin
                        if (div_setup) begin
                            div_setup<=0; div_early_r<=div_early; div_early_val<=m_result;
                            div_rem<=mag_a; div_quot<=0;
                            div_den<=mag_b << (clz64(mag_b) - clz64(mag_a));
                            div_bit<=64'd1 << (clz64(mag_b) - clz64(mag_a));
                            div_neg_q<=neg_a ^ neg_b; div_neg_r<=neg_a;
                            div_want_rem<=want_rem; div_is_word<=dv_word;
                        end else begin
                            div_rem<=div_rem_next; div_quot<=div_quot_next;
                            div_den<=div_den >> 1; div_bit<=div_bit >> 1;
                        end
                    end
                end
                // ---------------- issue: load/store port ----------------
                if (l1_advance) l1_valid<=0;
                if (msel_go) begin
                    iq_valid[msel]<=1'b0;
                    l1_valid<=1; l1_load<=iq_load[msel]; l1_insn<=iq_insn[msel]; l1_ps1<=iq_ps1[msel];
                    l1_ps2<=iq_ps2[msel]; l1_pdst<=iq_pdst[msel]; l1_rob<=iq_rob[msel]; l1_writes<=iq_writes[msel];
                end
                // L1 -> L2
                if (l1_advance && !flush_back && l1_load) begin
                    l2_valid<=1; l2_load<=1; l2_dead<=0; l2_exc<=l1_illegal || l1_misaligned;
                    l2_cause<=l1_illegal ? 64'd2 : 64'd4; l2_tval<=l1_illegal ? {32'b0,l1_insn} : l1_ea;
                    l2_addr<=l1_ea; l2_f3<=l1_f3; l2_pdst<=l1_pdst; l2_rob<=l1_rob; l2_writes<=l1_writes;
                    l2_bytes<=l1_bytes << l1_ea[2:0]; l2_force<=0;
                end else if (l2_done) begin l2_valid<=0; l2_dead<=0; end
                else if (l2_valid && fwd_hit && !fwd_full) l2_force<=1;  // read the bus once they retire
                if (l1_advance && !flush_back && !l1_load) begin
                    // A store only records its address and data; it writes at retirement.
                    rob_done[l1_rob]<=1'b1; rob_exc[l1_rob]<=l1_illegal || l1_misaligned;
                    rob_cause[l1_rob]<=l1_illegal ? 64'd2 : 64'd6; rob_tval[l1_rob]<=l1_illegal ? {32'b0,l1_insn} : l1_ea;
                    rob_addr[l1_rob]<=l1_ea; rob_wdata[l1_rob]<=l1_b << {l1_ea[2:0],3'b000};
                    rob_wstrb[l1_rob]<=l1_bytes << l1_ea[2:0];
                    rob_mp[l1_rob]<=1'b0; rob_ctl[l1_rob]<=1'b0; rob_fencei[l1_rob]<=1'b0;
                end
                // L2 completes (a dead load, discarded while its request was on the bus,
                // only finishes the request)
                if (l2_valid && l2_done && !l2_dead && !flush_back) begin
                    rob_done[l2_rob]<=1'b1;
                    rob_exc[l2_rob]<=l2_exc || l2_fault;
                    rob_cause[l2_rob]<=l2_exc ? l2_cause : 64'd5;
                    rob_tval[l2_rob]<=l2_exc ? l2_tval : l2_addr;
                    rob_value[l2_rob]<=l2_value;
                    rob_mp[l2_rob]<=1'b0; rob_ctl[l2_rob]<=1'b0; rob_fencei[l2_rob]<=1'b0;
                    if (l2_writes && !l2_exc && !l2_fault) begin
                        prf[l2_pdst]<=l2_value; prf_ready[l2_pdst]<=1'b1;
                    end
                end
                // ---------------- wakeup of waiting issue-queue entries ----------------
                for (i = 0; i < IQ_N; i = i + 1) begin
                    if (`WOKE(iq_ps1[i])) iq_r1[i]<=1'b1;
                    if (`WOKE(iq_ps2[i])) iq_r2[i]<=1'b1;
                end
                // ---------------- rename and dispatch ----------------
                if (go0) begin
                    iq_valid[is0]<=!d0_fault; iq_rob[is0]<=rob_tail; iq_pc[is0]<=d0_pc;
                    iq_insn[is0]<=d0_insn; iq_ps1[is0]<=d0_ps1; iq_ps2[is0]<=d0_ps2;
                    iq_r1[is0]<=prf_ready[d0_ps1] || `WOKE(d0_ps1);
                    iq_r2[is0]<=prf_ready[d0_ps2] || `WOKE(d0_ps2);
                    iq_mem[is0]<=d0_mem; iq_load[is0]<=d0_load; iq_mdu[is0]<=d0_mdu && !d0_fault;
                    iq_simple[is0]<=d0_simple;
                    iq_writes[is0]<=d0_writes; iq_pdst[is0]<=d0_writes ? pdst0 : 6'd0;
                    iq_pred[is0]<=d0_want; iq_ptaken[is0]<=d0_take_pred;
                    iq_alt[is0]<=d0_take_pred ? d0_seq : d0_target;
                    rob_live[rob_tail]<=1'b1; rob_done[rob_tail]<=d0_fault; rob_exc[rob_tail]<=d0_fault;
                    rob_cause[rob_tail]<={62'b0,d0_fcause}; rob_tval[rob_tail]<=d0_pc;
                    rob_pc[rob_tail]<=d0_pc; rob_insn[rob_tail]<=d0_insn; rob_next[rob_tail]<=d0_want;
                    rob_rd[rob_tail]<=d0_rd; rob_writes[rob_tail]<=d0_writes;
                    rob_pdst[rob_tail]<=pdst0; rob_opdst[rob_tail]<=rat[d0_rd];
                    rob_store[rob_tail]<=d0_store && !d0_fault; rob_load[rob_tail]<=d0_load && !d0_fault;
                    rob_mp[rob_tail]<=1'b0; rob_ctl[rob_tail]<=1'b0; rob_fencei[rob_tail]<=1'b0;
                    rob_bhit[rob_tail]<=d0_bhit; rob_bctr[rob_tail]<=d0_bctr;
                    if (d0_writes) begin
                        rat[d0_rd]<=pdst0; free_mask[pdst0]<=1'b0; prf_ready[pdst0]<=1'b0;
                    end
                end
                if (go1) begin
                    iq_valid[is1]<=!d1_fault; iq_rob[is1]<=rob_tail1; iq_pc[is1]<=d1_pc;
                    iq_insn[is1]<=d1_insn; iq_ps1[is1]<=d1_ps1; iq_ps2[is1]<=d1_ps2;
                    iq_r1[is1]<=!d1_dep1 && (prf_ready[d1_ps1] || `WOKE(d1_ps1));
                    iq_r2[is1]<=!d1_dep2 && (prf_ready[d1_ps2] || `WOKE(d1_ps2));
                    iq_mem[is1]<=d1_mem; iq_load[is1]<=d1_load; iq_mdu[is1]<=d1_mdu && !d1_fault;
                    iq_simple[is1]<=d1_simple;
                    iq_writes[is1]<=d1_writes; iq_pdst[is1]<=d1_writes ? pdst1 : 6'd0;
                    iq_pred[is1]<=d1_want; iq_ptaken[is1]<=d1_take_pred;
                    iq_alt[is1]<=d1_take_pred ? d1_seq : d1_target;
                    rob_live[rob_tail1]<=1'b1; rob_done[rob_tail1]<=d1_fault; rob_exc[rob_tail1]<=d1_fault;
                    rob_cause[rob_tail1]<={62'b0,d1_fcause}; rob_tval[rob_tail1]<=d1_pc;
                    rob_pc[rob_tail1]<=d1_pc; rob_insn[rob_tail1]<=d1_insn; rob_next[rob_tail1]<=d1_want;
                    rob_rd[rob_tail1]<=d1_rd; rob_writes[rob_tail1]<=d1_writes;
                    rob_pdst[rob_tail1]<=pdst1; rob_opdst[rob_tail1]<=d1_opdst;
                    rob_store[rob_tail1]<=d1_store && !d1_fault; rob_load[rob_tail1]<=d1_load && !d1_fault;
                    rob_mp[rob_tail1]<=1'b0; rob_ctl[rob_tail1]<=1'b0; rob_fencei[rob_tail1]<=1'b0;
                    rob_bhit[rob_tail1]<=d1_bhit; rob_bctr[rob_tail1]<=d1_bctr;
                    if (d1_writes) begin
                        rat[d1_rd]<=pdst1; free_mask[pdst1]<=1'b0; prf_ready[pdst1]<=1'b0;
                    end
                end
                rob_tail<=rob_tail + {4'b0,go0} + {4'b0,go1};
                rob_count<=rob_count + {5'b0,go0} + {5'b0,go1} - {5'b0,retire} - {5'b0,retire1};

                // ---------------- discard younger instructions ----------------
                if (flush_back) begin
                    iq_valid<=0; e_valid<=0; x1_valid<=0; l1_valid<=0; md_busy<=0; e_mdu_pending<=0;
                    if (l2_valid && l2_miss && (ld_active || (ld_req && !mem_ready))) l2_dead<=1;
                    else l2_valid<=0;
                    rob_live<=0; rob_done<=0; rob_count<=0;
                    rob_head<=rob_head+5'd1; rob_tail<=rob_head+5'd1;
                    mp_pending<=0;
                    prf_ready<={64{1'b1}};
                    for (i = 0; i < 32; i = i + 1) rat[i]<=(retire && rob_writes[h] && rob_rd[h] == i[4:0]) ? rob_pdst[h] : rrat[i];
                    free_mask<=flush_free;
                end
                // ---------------- queue -> D (two slots) ----------------
                if (flush_front || e_redirect || (flush_back && !mp_pending)) begin
                    d0_valid<=0; d1_valid<=0;
                end else begin
                    // Slot 0: the instruction kept there, else the one kept in slot 1, else the queue.
                    if (keep0) begin
                        if (d_fire && d0_fire_raw) d0_red<=1;
                    end else if (keep1) begin
                        d0_valid<=1; d0_pc<=d1_pc; d0_insn<=d1_insn; d0_pred<=d1_pred; d0_fpred<=d1_fpred; d0_bhit<=d1_bhit; d0_bctr<=d1_bctr; d0_fault<=d1_fault; d0_fcause<=d1_fcause; d0_red<=d1_red || (d_fire && d1_fire_raw);
                    end else if (q_take >= 2'd1) begin
                        d0_valid<=1; d0_pc<=q_pc[q_head]; d0_insn<=q_insn[q_head]; d0_pred<=q_pred[q_head]; d0_fpred<=q_fpred[q_head]; d0_bhit<=q_bhit[q_head]; d0_bctr<=q_bctr[q_head]; d0_fault<=q_fault[q_head]; d0_fcause<=q_fmis[q_head] ? 2'd0 : 2'd1; d0_red<=0;
                    end else d0_valid<=0;
                    // Slot 1.
                    if (keep0 && keep1) begin
                        if (d_fire && d1_fire_raw) d1_red<=1;
                    end else if (keep0 || keep1) begin
                        if (q_take >= 2'd1) begin d1_valid<=1; d1_pc<=q_pc[q_head]; d1_insn<=q_insn[q_head]; d1_pred<=q_pred[q_head]; d1_fpred<=q_fpred[q_head]; d1_bhit<=q_bhit[q_head]; d1_bctr<=q_bctr[q_head]; d1_fault<=q_fault[q_head]; d1_fcause<=q_fmis[q_head] ? 2'd0 : 2'd1; d1_red<=0; end else d1_valid<=0;
                    end else begin
                        if (q_take == 2'd2) begin d1_valid<=1; d1_pc<=q_pc[q_head1]; d1_insn<=q_insn[q_head1]; d1_pred<=q_pred[q_head1]; d1_fpred<=q_fpred[q_head1]; d1_bhit<=q_bhit[q_head1]; d1_bctr<=q_bctr[q_head1]; d1_fault<=q_fault[q_head1]; d1_fcause<=q_fmis[q_head1] ? 2'd0 : 2'd1; d1_red<=0; end else d1_valid<=0;
                    end
                end
                // ---------------- fetch queue ----------------
                if (front_kill) begin
                    q_head<=0; q_tail<=0; q_count<=0; q_used<=0;
                end else begin
                    if (q_push != 0) begin
                        q_pc[q_tail]<=f_pc; q_insn[q_tail]<=f_word; q_pred[q_tail]<=f_pred;
                        q_fpred[q_tail]<=f_btaken; q_bhit[q_tail]<=f_bhit; q_bctr[q_tail]<=btb_ctr[f_bidx];
                        q_fault[q_tail]<=f_fault; q_fmis[q_tail]<=f_misaligned;
                    end
                    if (q_push == 2'd2) begin
                        q_pc[q_tail+3'd1]<=f_pc1; q_insn[q_tail+3'd1]<=f_word1; q_pred[q_tail+3'd1]<=f_pred1;
                        q_fpred[q_tail+3'd1]<=f_btaken1; q_bhit[q_tail+3'd1]<=f_bhit1;
                        q_bctr[q_tail+3'd1]<=btb_ctr[f_bidx1];
                        q_fault[q_tail+3'd1]<=1'b0; q_fmis[q_tail+3'd1]<=1'b0;
                    end
                    q_tail<=q_tail + {1'b0,q_push};
                    q_head<=q_head + {1'b0,q_take};
                    q_count<=q_count + {2'b0,q_push} - {2'b0,q_take};
                    for (i = 0; i < 8; i = i + 1) begin
                        if ((q_take >= 2'd1 && i[2:0] == q_head) || (q_take == 2'd2 && i[2:0] == q_head1)) q_used[i]<=1'b0;
                        if ((q_push >= 2'd1 && i[2:0] == q_tail) || (q_push == 2'd2 && i[2:0] == q_tail + 3'd1)) q_used[i]<=1'b1;
                    end
                end
                // Return stack, as calls and returns are fetched (at most one per clock).
                if (f_go && !f_fault && f_call) begin
                    ras[ras_sp+2'd1]<=f_pc+64'd4; ras_sp<=ras_sp+2'd1;
                end else if (f_go && !f_fault && f_return) ras_sp<=ras_sp-2'd1;
                else if (f_go && f_two && f_call1) begin
                    ras[ras_sp+2'd1]<=f_pc1+64'd4; ras_sp<=ras_sp+2'd1;
                end else if (f_go && f_two && f_return1) ras_sp<=ras_sp-2'd1;
                f_pc<=fetch_next;
            end
        end
    end
    `undef WOKE
endmodule
