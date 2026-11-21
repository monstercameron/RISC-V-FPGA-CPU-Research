// SPDX-License-Identifier: MIT
// Original CPU foundation, pipelined implementation (added in architecture 0.8.0).
// RV64IM + B execution, serialized FENCE.I, terminal EEI. Same module name, ports and
// architectural contract as the multicycle core in rv64_core.sv; build with one of
// the two files, never both. Architecture version: cpu/VERSION, cpu/architecture.md
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
    // Pipelined core (0.8.0). Four stages, one instruction per clock at most:
    //   F  instruction cache read (registered, block-RAM style) and bus fill;
    //   D  decode for prediction, register read; JAL and backward branches redirect F;
    //   E  execute: ALU, B, branch decision, address, data-cache read address;
    //   M  data cache, bus access, retirement and register write; traps act here.
    // Results are forwarded to E from M (integer results) and from the instruction
    // that retired last. A load or multiply result used by the next instruction costs
    // one clock; store data from a load is taken late, in M, without a stall.
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

    reg halted;
    // No reset loop on the register file (so it can be LUT RAM): after reset a
    // sequencer writes zero to every register, one per clock, before fetch starts.
    reg [5:0] init_count;
    wire init_done = init_count[5];
    reg [63:0] regs [0:31];

    // ---------------- E stage registers (named as in the multicycle core) ----------
    reg e_valid;
    reg [63:0] pc;          // E-stage PC
    reg [31:0] insn;        // E-stage instruction
    reg [63:0] e_a, e_b;    // operands read in D (refreshed while E waits)
    reg [63:0] e_pred;      // the PC fetch followed after this instruction
    reg e_fault;            // instruction fetch failed (cause in e_fcause)
    reg [1:0] e_fcause;
    wire [6:0] op = insn[6:0];
    wire [2:0] f3 = insn[14:12];
    wire [6:0] f7 = insn[31:25];
    wire [4:0] rd = insn[11:7];
    wire [4:0] rs1 = insn[19:15];
    wire [4:0] rs2 = insn[24:20];

    // ---------------- M stage registers -------------------------------------------
    reg m_valid, m_load, m_store, m_mul, m_div, m_fencei, m_exc, m_sdata_late, m_icdirty;
    reg [63:0] m_pc, m_next, m_alu, m_addr, m_sdata, m_cause, m_tval;
    reg [31:0] m_insn;
    reg [4:0] m_rd;
    reg [2:0] m_f3;
    reg [7:0] m_mask;
    // Last retired instruction, for forwarding into E.
    reg w_valid;
    reg [4:0] w_rd;
    reg [63:0] w_data;

    // Forwarding into E: M's integer result first, then the last retirement.
    wire m_late = m_valid && (m_load || m_mul || m_div);
    wire m_fwd = m_valid && !m_late && !m_exc && m_rd != 0;
    wire [63:0] a = rs1 == 0 ? 64'b0 : (m_fwd && m_rd == rs1) ? m_alu
                  : (w_valid && w_rd == rs1) ? w_data : e_a;
    wire [63:0] b = rs2 == 0 ? 64'b0 : (m_fwd && m_rd == rs2) ? m_alu
                  : (w_valid && w_rd == rs2) ? w_data : e_b;
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

    // ---------------- caches -------------------------------------------------------
    // Instruction cache: direct-mapped, one 8-byte beat per line, filled by bus fetches.
    // Tags and data are read through a register (block-RAM style); valid bits are
    // flip-flops so reset and fence.i clear them at once.
    reg [ICACHE_BEATS-1:0] ic_valid;
    reg [IC_TAG-1:0] ic_tag [0:ICACHE_BEATS-1];
    reg [63:0] ic_data [0:ICACHE_BEATS-1];
    reg [IC_TAG-1:0] ic_tq;  // tag and data of f_pc's line, read at the last edge
    reg [63:0] ic_q;
    reg [IC_TAG-1:0] ic_stq; // instruction-cache tag at M's store address, read as it entered M
    // Data cache: direct-mapped, write-through, no allocation on stores; read at the
    // edge where an instruction enters M, written when M retires.
    reg [DCACHE_BEATS-1:0] dc_valid;
    reg [DC_TAG-1:0] dc_tag [0:DCACHE_BEATS-1];
    reg [63:0] dc_data [0:DCACHE_BEATS-1];
    reg [DC_TAG-1:0] dq_tag;
    reg [63:0] dq_data;

    // ---------------- F stage -----------------------------------------------------
    reg f_valid;
    reg [63:0] f_pc;
    reg fetch_active;        // a fetch was presented and has not completed
    reg [63:0] fetch_addr;
    wire [IC_INDEX-1:0] f_idx = f_pc[3 +: IC_INDEX];
    wire f_misaligned = f_pc[1:0] != 0;
    wire f_hit = ic_valid[f_idx] && ic_tq == f_pc[63 -: IC_TAG];
    // Branch target buffer, read with f_pc: direct-mapped on pc[9:2], 10-bit partial
    // tags, 2-bit counters for conditional branches; entries marked as returns take
    // their target from a 4-entry return-address stack. The BTB is updated in E; the
    // return stack in F, as calls and returns are fetched (wrong-path updates are not
    // undone).
    localparam integer BTB_BITS = 8;
    localparam integer BTB_TAG = 10;
    localparam integer BTB_ENTRIES = 1 << BTB_BITS;
    reg [BTB_ENTRIES-1:0] btb_valid, btb_ret;
    reg [BTB_TAG-1:0] btb_tag [0:BTB_ENTRIES-1];
    reg [29:0] btb_target [0:BTB_ENTRIES-1];  // target[31:2]; upper bits from the PC
    reg [1:0] btb_ctr [0:BTB_ENTRIES-1];
    reg [63:0] ras [0:3];
    reg [1:0] ras_sp;
    wire [BTB_BITS-1:0] f_bidx = f_pc[2 +: BTB_BITS];
    wire f_bhit = btb_valid[f_bidx] && btb_tag[f_bidx] == f_pc[2+BTB_BITS +: BTB_TAG];
    wire f_btaken = f_bhit && (btb_ret[f_bidx] || btb_ctr[f_bidx][1]);

    // ---------------- D stage -----------------------------------------------------
    reg d_valid, d_fault;
    reg [1:0] d_fcause;
    reg [63:0] d_pc;
    reg [31:0] d_insn;
    reg [63:0] d_pred;       // where fetch went after this instruction
    reg d_fpred, d_bhit, e_bhit;  // predicted taken by the BTB; BTB entry matched
    reg [1:0] d_bctr, e_bctr;
    wire [4:0] d_rs1 = d_insn[19:15];
    wire [4:0] d_rs2 = d_insn[24:20];
    wire [63:0] d_a = d_rs1 == 0 ? 64'b0 : regs[d_rs1];
    wire [63:0] d_b = d_rs2 == 0 ? 64'b0 : regs[d_rs2];
    // Static prediction when the BTB did not predict: JAL and backward conditional
    // branches are taken.
    wire d_jal = d_insn[6:0] == 7'h6f;
    wire d_back = d_insn[6:0] == 7'h63 && d_insn[31];
    wire [63:0] d_offset = d_jal ? {{43{d_insn[31]}},d_insn[31],d_insn[19:12],d_insn[20],d_insn[30:21],1'b0}
                                 : {{51{d_insn[31]}},d_insn[31],d_insn[7],d_insn[30:25],d_insn[11:8],1'b0};
    wire [63:0] d_target = d_pc + d_offset;
    // D checks what fetch predicted for this instruction against what it can work out
    // itself: JAL goes to its target; a conditional branch keeps the BTB's direction (or
    // is taken if backward when the BTB had no entry) with the target recomputed here;
    // JALR keeps the prediction (E checks it); anything else falls through. A mismatch
    // redirects fetch once, while D holds the instruction.
    wire d_branch = d_insn[6:0] == 7'h63;
    wire d_jalr = d_insn[6:0] == 7'h67;
    wire d_take_pred = (d_jal || (d_branch && (d_fpred || d_back))) && d_target[1:0] == 0;
    wire [63:0] d_seq = d_pc + 64'd4;
    wire [63:0] d_want = d_jalr ? d_pred : d_take_pred ? d_target : d_seq;
    wire d_mismatch = d_valid && !d_fault && d_want != d_pred;
    reg d_redirected, e_redirected;  // the stage's redirect has already been sent
    reg e_ptaken;                    // E's conditional branch was predicted taken
    reg [63:0] e_alt;                // where E's branch goes if the prediction was wrong

    // ---------------- fetch queue (0.8.1) -------------------------------------------
    // Four entries between F and D, so F advances whenever the queue is not full (a
    // registered condition) instead of waiting for the whole pipeline's stall decision.
    // When the queue is empty, D takes F's instruction directly.
    reg [63:0] q_pc [0:3];
    reg [31:0] q_insn [0:3];
    reg [63:0] q_pred [0:3];
    reg [3:0] q_fpred, q_bhit, q_fault, q_fmis;
    reg [1:0] q_bctr [0:3];
    reg [1:0] q_head, q_tail;
    reg [2:0] q_count;

    // ---------------- M and X stages ----------------------------------------------
    // M finishes its instruction in one clock without waiting: it retires it (integer
    // result, load hit, multiply, or a bus access that completes in that clock), or
    // hands a bus access that did not complete to X. X holds that one access until the
    // bus finishes and retires it; M waits while X is busy. So whether M takes the next
    // instruction depends only on registers, not on this clock's cache hit.
    wire [DC_INDEX-1:0] m_idx = m_addr[3 +: DC_INDEX];
    wire [IC_INDEX-1:0] m_ic_idx = m_addr[3 +: IC_INDEX];
    wire m_hit = dc_valid[m_idx] && dq_tag == m_addr[63 -: DC_TAG];
    wire [63:0] m_sval = m_sdata_late ? w_data : m_sdata;
    wire [63:0] m_wdata = m_sval << {m_addr[2:0],3'b000};
    wire [7:0] m_wstrb = m_store ? m_mask << m_addr[2:0] : 8'b0;
    // A store to the beat of an already-fetched younger instruction, or fence.i, sets
    // m_flush_r as it retires; the next clock discards every younger instruction
    // (including one that entered M at that edge) and refetches from m_flush_pc.
    reg m_flush_r;
    reg [63:0] m_flush_pc;
    reg x_valid, x_load, x_fault, x_hit, x_icdirty;
    reg [63:0] x_pc, x_next, x_addr, x_wdata, x_line;
    reg [31:0] x_insn;
    reg [4:0] x_rd;
    reg [2:0] x_f3;
    reg [7:0] x_wstrb;
    reg [IC_TAG-1:0] x_stq;
    wire [DC_INDEX-1:0] x_idx = x_addr[3 +: DC_INDEX];
    wire [IC_INDEX-1:0] x_ic_idx = x_addr[3 +: IC_INDEX];
    reg div_early_r;
    reg [63:0] div_early_val;
    wire m_active = m_valid && !m_exc && !m_flush_r && !x_valid && !halted;
    wire m_wait_div = m_div && (div_setup || (!div_early_r && div_bit != 64'd1));
    wire m_leaves = m_active && !m_wait_div;           // from registers only
    wire m_needs_bus = m_store || (m_load && !m_hit);
    wire m_bus = m_leaves && m_needs_bus;               // M's first-clock attempt

    // ---------------- bus ---------------------------------------------------------
    // One bus. X's access first, then M's first-clock attempt, then a new fetch; a
    // presented request is held until it completes (X holds what M presented). No
    // fetch starts while M holds a load or store (whether it needs the bus depends on
    // this clock's cache hit, which would lengthen fetch's path) or a faulting
    // instruction.
    wire f_want = f_valid && init_done && !halted && !f_misaligned && !f_hit;
    wire x_req = x_valid && !x_fault && !halted;
    wire data_req = !fetch_active && !halted && (x_req || m_bus);
    wire m_memop = m_leaves && (m_load || m_store);
    wire fetch_req = !halted && (fetch_active || (f_want && !x_valid && !m_memop && !(m_valid && m_exc)));
    wire [63:0] fetch_beat = fetch_active ? fetch_addr : {f_pc[63:3],3'b000};
    assign mem_valid = !reset && (fetch_req || data_req);
    assign mem_instr = fetch_req;
    assign mem_addr = fetch_req ? fetch_beat : x_valid ? {x_addr[63:3],3'b000} : {m_addr[63:3],3'b000};
    assign mem_wdata = fetch_req ? 64'b0 : x_valid ? x_wdata : m_wdata;
    assign mem_wstrb = fetch_req ? 8'b0 : x_valid ? x_wstrb : m_wstrb;
    wire fetch_done = fetch_req && mem_ready;
    wire fill = fetch_done && !mem_error;
    wire [IC_INDEX-1:0] fill_idx = fetch_beat[3 +: IC_INDEX];
    wire fetch_for_f = fetch_done && f_valid && fetch_beat[63:3] == f_pc[63:3];
    wire data_done = data_req && mem_ready;

    // F output: from the cache, or straight from a fetch completing this clock.
    wire [63:0] f_beat = fetch_for_f ? mem_rdata : ic_q;
    wire [31:0] f_word = f_pc[2] ? f_beat[63:32] : f_beat[31:0];
    wire f_fault = f_misaligned || (fetch_for_f && mem_error);
    wire f_ready = f_valid && init_done && !halted && (f_misaligned || f_hit || fetch_for_f);

    // Load data, for M (cache or bus) and for X (bus).
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
    wire [63:0] load_result = load_align(m_hit ? dq_data : mem_rdata, m_addr[2:0], m_f3);
    wire [63:0] x_result = load_align(mem_rdata, x_addr[2:0], x_f3);
    reg [63:0] store_line;  // M's line with the store's bytes merged (store hits)
    integer lane;
    always @* begin
        store_line = dq_data;
        for (lane = 0; lane < 8; lane = lane + 1)
            if (m_wstrb[lane]) store_line[8*lane +: 8] = m_wdata[8*lane +: 8];
    end
    wire [63:0] m_value = m_load ? load_result : m_mul ? mul_value
                        : m_div ? (div_early_r ? div_early_val
                                  : div_finish(div_quot_next,div_rem_next,div_neg_q,div_neg_r,div_want_rem,div_is_word))
                        : m_alu;
    wire m_bus_ok = data_done && !mem_error;   // M's attempt completed (when x is empty)
    wire m_done = m_leaves && (!m_needs_bus || m_bus_ok);   // M retires this clock
    wire m_to_x = m_leaves && m_needs_bus && !m_bus_ok;     // M hands its access to X
    wire x_done = x_req && data_done && !mem_error;         // X retires this clock
    wire x_trap = x_valid && !halted && (x_fault || (x_req && data_done && mem_error));
    wire m_trap = m_valid && m_exc && !x_valid && !fetch_active && !m_flush_r && !halted;
    wire any_trap = x_trap || m_trap;
    reg [3:0] q_used;  // occupied fetch-queue entries
    // Store retiring this clock (from X if X is busy, else from M): younger instructions
    // already fetched from its beat must be refetched.
    wire [63:0] s_addr = x_valid ? x_addr : m_addr;
    wire q_match = (q_used[0] && q_pc[0][63:3] == s_addr[63:3]) || (q_used[1] && q_pc[1][63:3] == s_addr[63:3]) ||
                   (q_used[2] && q_pc[2][63:3] == s_addr[63:3]) || (q_used[3] && q_pc[3][63:3] == s_addr[63:3]);
    wire s_younger = (x_valid && m_valid && m_pc[63:3] == s_addr[63:3]) ||
                     (e_valid && pc[63:3] == s_addr[63:3]) ||
                     (d_valid && d_pc[63:3] == s_addr[63:3]) || q_match ||
                     (f_valid && f_pc[63:3] == s_addr[63:3]);
    wire m_flush = (m_done && (m_fencei || (m_store && s_younger))) || (x_done && !x_load && s_younger);

    // ---------------- stage control -----------------------------------------------
    wire uses1 = !(op == 7'h37 || op == 7'h17 || op == 7'h6f);
    wire uses2 = op == 7'h33 || op == 7'h3b || op == 7'h63 || op == 7'h23;
    wire x_late = x_valid && x_load && x_rd != 0;
    wire late_hit1 = (m_late && m_rd != 0 && uses1 && rs1 == m_rd) || (x_late && uses1 && rs1 == x_rd);
    wire late_hit2 = (m_late && m_rd != 0 && uses2 && rs2 == m_rd) || (x_late && uses2 && rs2 == x_rd);
    wire e_hazard = late_hit1 || (late_hit2 && !store_op);
    wire e_exc = e_fault || exception;
    wire e_jump = op == 7'h6f || (op == 7'h67 && f3 == 0);
    wire e_control = e_jump || op == 7'h63;
    wire e_taken = e_jump || branch_taken;
    wire e_return = op == 7'h67 && f3 == 0 && rd == 0 && (rs1 == 1 || rs1 == 5);
    wire e_go = e_valid && (!m_valid || m_leaves) && !e_hazard && !m_flush_r;
    wire e_load = !e_valid || e_go;
    // Redirects are sent once, as soon as the stage knows, without waiting to advance.
    // E waits for valid operands (no load-use hazard) before judging its prediction.
    // E checks only what D cannot: a conditional branch's direction and a JALR's
    // target. A faulting instruction may redirect too; it traps in M either way.
    wire e_branch = op == 7'h63;
    wire e_jalr = op == 7'h67;
    wire [63:0] e_jalr_target = (a + imm_i) & ~64'd1;
    wire e_redirect = e_valid && !e_hazard && !e_redirected && !m_flush_r &&
                      ((e_branch && branch_taken != e_ptaken) || (e_jalr && e_jalr_target != e_pred));
    wire [63:0] e_redirect_pc = e_branch ? e_alt : e_jalr_target;
    wire d_fire = d_mismatch && !d_redirected && !e_redirect && !m_flush_r;
    wire front_kill = m_flush_r || e_redirect || d_fire;
    wire d_go = d_valid && e_load && !e_redirect && !m_flush_r;
    wire d_take = (!d_valid || d_go) && !front_kill;  // D loads a new instruction
    wire f_go = f_ready && q_count != 3'd4 && !front_kill;
    wire q_pop = d_take && q_count != 0;
    wire f_bypass = d_take && q_count == 0 && f_go;
    wire q_push = f_go && !f_bypass;
    wire [6:0] f_op = f_word[6:0];
    wire f_jump = f_op == 7'h6f || (f_op == 7'h67 && f_word[14:12] == 0);
    wire f_call = f_jump && (f_word[11:7] == 1 || f_word[11:7] == 5);
    wire f_return = f_op == 7'h67 && f_word[14:12] == 0 && f_word[11:7] == 0 &&
                    (f_word[19:15] == 1 || f_word[19:15] == 5);
    wire [63:0] f_btarget = btb_ret[f_bidx] ? ras[ras_sp] : {f_pc[63:32],btb_target[f_bidx],2'b00};
    wire [63:0] f_pred = f_btaken ? f_btarget : f_pc + 64'd4;
    reg [63:0] fetch_next;
    always @* begin
        if (m_flush_r) fetch_next = m_flush_pc;
        else if (e_redirect) fetch_next = e_redirect_pc;
        else if (d_fire) fetch_next = d_want;
        else if (f_go) fetch_next = f_pred;
        else fetch_next = f_pc;
    end
    wire [IC_INDEX-1:0] next_idx = fetch_next[3 +: IC_INDEX];
    wire [DC_INDEX-1:0] e_dc_idx = effective_addr[3 +: DC_INDEX];
    wire [IC_INDEX-1:0] e_ic_idx = effective_addr[3 +: IC_INDEX];
    // Data-cache write this clock: a load fill or store hit, retiring from M or X.
    wire dc_write_m = m_done && ((m_load && !m_hit) || (m_store && m_hit));
    wire dc_write_x = x_done && (x_load || x_hit);
    wire dc_write = dc_write_m || dc_write_x;
    wire [DC_INDEX-1:0] dcw_idx = dc_write_x ? x_idx : m_idx;
    wire [DC_TAG-1:0] dcw_tag = dc_write_x ? x_addr[63 -: DC_TAG] : m_addr[63 -: DC_TAG];
    wire [63:0] dcw_line = dc_write_x ? (x_load ? mem_rdata : x_line) : (m_load ? mem_rdata : store_line);

    // Debug view for the testbenches and the visualizer: what the core waits for.
    wire [2:0] state = halted ? HALTED : (x_valid || m_to_x) ? MEMORY
                     : (!m_done && f_valid && !f_ready) ? FETCH : EXECUTE;

    always @(posedge clk) begin
        // Cache read ports, with the write of the same edge passed through.
        ic_q <= (fill && fill_idx == next_idx) ? mem_rdata : ic_data[next_idx];
        ic_tq <= (fill && fill_idx == next_idx) ? fetch_beat[63 -: IC_TAG] : ic_tag[next_idx];
        if (fill) begin
            ic_tag[fill_idx] <= fetch_beat[63 -: IC_TAG];
            ic_data[fill_idx] <= mem_rdata;
        end
        if (e_go) begin
            dq_data <= (dc_write && dcw_idx == e_dc_idx) ? dcw_line : dc_data[e_dc_idx];
            dq_tag <= (dc_write && dcw_idx == e_dc_idx) ? dcw_tag : dc_tag[e_dc_idx];
            ic_stq <= (fill && fill_idx == e_ic_idx) ? fetch_beat[63 -: IC_TAG] : ic_tag[e_ic_idx];
        end else if (dc_write_x && m_valid && x_idx == m_idx) begin
            dq_data <= dcw_line;  // X updates the line M (waiting behind it) already read
            dq_tag <= dcw_tag;
        end
        if (dc_write) begin
            dc_tag[dcw_idx] <= dcw_tag;
            dc_data[dcw_idx] <= dcw_line;
        end
        // Register file: the reset sequencer, or a retirement from X or M.
        if (!init_done) regs[init_count[4:0]] <= 64'b0;
        else if (x_done && x_rd != 0) regs[x_rd] <= x_result;
        else if (m_done && m_rd != 0) regs[m_rd] <= m_value;
    end

    always @(posedge clk) begin
        if (reset) begin
            halted<=0; init_count<=0;
            f_valid<=0; f_pc<=RESET_PC; fetch_active<=0; fetch_addr<=0;
            d_valid<=0; d_fault<=0; d_fcause<=0; d_pc<=0; d_insn<=0;
            d_pred<=0; d_fpred<=0; d_bhit<=0; d_bctr<=0; e_bhit<=0; e_bctr<=0;
            btb_valid<=0; btb_ret<=0; ras_sp<=0; ras[0]<=0; ras[1]<=0; ras[2]<=0; ras[3]<=0;
            d_redirected<=0; e_redirected<=0; m_flush_r<=0; m_flush_pc<=0; e_ptaken<=0; e_alt<=0;
            q_head<=0; q_tail<=0; q_count<=0; q_used<=0;
            q_fpred<=0; q_bhit<=0; q_fault<=0; q_fmis<=0;
            e_valid<=0; pc<=0; insn<=0; e_a<=0; e_b<=0; e_pred<=0; e_fault<=0; e_fcause<=0;
            m_valid<=0; m_load<=0; m_store<=0; m_mul<=0; m_div<=0; m_fencei<=0; m_exc<=0;
            m_sdata_late<=0; m_icdirty<=0; m_pc<=0; m_next<=0; m_alu<=0; m_addr<=0; m_sdata<=0;
            m_cause<=0; m_tval<=0; m_insn<=0; m_rd<=0; m_f3<=0; m_mask<=0;
            w_valid<=0; w_rd<=0; w_data<=0;
            ic_valid<=0; dc_valid<=0;
            mul_op_a<=0; mul_op_b<=0; mul_high<=0; mul_word<=0;
            div_rem<=0; div_den<=0; div_quot<=0; div_bit<=0;
            div_neg_q<=0; div_neg_r<=0; div_want_rem<=0; div_is_word<=0;
            dv_a<=0; dv_b<=0; dv_f3<=0; dv_word<=0; div_setup<=0; div_early_r<=0; div_early_val<=0;
            x_valid<=0; x_load<=0; x_fault<=0; x_hit<=0; x_icdirty<=0; x_pc<=0; x_next<=0; x_addr<=0;
            x_wdata<=0; x_line<=0; x_insn<=0; x_rd<=0; x_f3<=0; x_wstrb<=0; x_stq<=0;
            trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_tval<=0;
            retire_valid<=0; retire_pc<=0; retire_insn<=0;
            retire_rd<=0; retire_data<=0; retire_next_pc<=0;
            retire2_valid<=0; retire2_pc<=0; retire2_insn<=0;
            retire2_rd<=0; retire2_data<=0; retire2_next_pc<=0;
            retire3_valid<=0; retire3_pc<=0; retire3_insn<=0;
            retire3_rd<=0; retire3_data<=0; retire3_next_pc<=0;
        end else begin
            retire_valid<=0;
            if (!init_done) begin
                init_count<=init_count+6'd1;
                if (init_count==6'd31) f_valid<=1;
            end
            // Bus fetch bookkeeping.
            if (fetch_req) begin
                if (mem_ready) fetch_active<=0;
                else begin fetch_active<=1; fetch_addr<=fetch_beat; end
            end
            if (fill) ic_valid[fill_idx]<=1'b1;

            if (any_trap) begin
                trap_valid<=1;
                trap_pc<=x_trap ? x_pc : m_pc;
                trap_cause<=x_trap ? (x_load ? 64'd5 : 64'd7) : m_cause;
                trap_tval<=x_trap ? x_addr : m_tval;
                halted<=1; f_valid<=0; d_valid<=0; e_valid<=0; m_valid<=0; x_valid<=0;
                q_count<=0; q_used<=0;
            end else if (!halted) begin
                // ---- X: retire a completed access
                if (x_done) begin
                    retire_valid<=1; retire_pc<=x_pc; retire_insn<=x_insn; retire_rd<=x_rd;
                    retire_data<=x_rd==0 ? 64'b0 : x_result; retire_next_pc<=x_next;
                    w_valid<=1; w_rd<=x_rd; w_data<=x_result;
                    if (x_load) dc_valid[x_idx]<=1'b1;
                    if (m_flush) begin m_flush_r<=1; m_flush_pc<=x_next; end
                    if (!x_load && ic_valid[x_ic_idx] && (x_stq == x_addr[63 -: IC_TAG] || x_icdirty))
                        ic_valid[x_ic_idx]<=1'b0;
                    x_valid<=0;
                end
                if (x_valid && fill && fill_idx == x_ic_idx) x_icdirty<=1;
                // ---- M: retire, or hand the access to X
                if (m_done) begin
                    retire_valid<=1; retire_pc<=m_pc; retire_insn<=m_insn; retire_rd<=m_rd;
                    retire_data<=m_rd==0 ? 64'b0 : m_value; retire_next_pc<=m_next;
                    w_valid<=1; w_rd<=m_rd; w_data<=m_value;
                    if (m_load && !m_hit) dc_valid[m_idx]<=1'b1;
                    if (m_flush) begin m_flush_r<=1; m_flush_pc<=m_next; end
                    if (m_fencei) ic_valid<=0;
                    else if (m_store && ic_valid[m_ic_idx] && (ic_stq == m_addr[63 -: IC_TAG] || m_icdirty))
                        ic_valid[m_ic_idx]<=1'b0;
                end
                if (m_to_x) begin
                    x_valid<=1; x_fault<=data_done && mem_error;  // an error here traps from X next clock
                    x_load<=m_load; x_hit<=m_hit; x_pc<=m_pc; x_insn<=m_insn; x_next<=m_next;
                    x_rd<=m_rd; x_f3<=m_f3; x_addr<=m_addr; x_wdata<=m_wdata; x_wstrb<=m_wstrb;
                    x_line<=store_line; x_stq<=ic_stq;
                    x_icdirty<=m_icdirty || (fill && fill_idx == m_ic_idx);
                end
                if (m_active && m_div && m_wait_div) begin
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
                if (m_valid && !m_leaves && fill && fill_idx == m_ic_idx) m_icdirty<=1;
                // ---- E -> M
                if (e_go) begin
                    m_valid<=1; m_pc<=pc; m_insn<=insn; m_next<=next_pc;
                    m_exc<=e_exc;
                    m_cause<=e_fault ? {62'b0,e_fcause} : exception_cause;
                    m_tval<=e_fault ? pc : exception_tval;
                    m_rd<=(e_exc || !(write_rd || load_op)) ? 5'b0 : rd;
                    m_load<=load_op && !e_exc; m_store<=store_op && !e_exc;
                    m_f3<=f3; m_mask<=byte_mask; m_addr<=effective_addr;
                    m_sdata<=b; m_sdata_late<=store_op && late_hit2;
                    m_mul<=mul_start && !e_exc; m_div<=is_div && !e_exc;
                    m_fencei<=op==7'h0f && f3==1 && !e_exc;
                    m_alu<=result; m_icdirty<=0;
                    if (mul_start) begin
                        mul_op_a<=mul_a; mul_op_b<=mul_b; mul_high<=f3!=0; mul_word<=m_word;
                    end
                    if (is_div) begin
                        dv_a<=a; dv_b<=b; dv_f3<=f3; dv_word<=m_word; div_setup<=1; div_early_r<=0;
                    end
                end else if (m_leaves || m_flush_r) m_valid<=0;
                if (m_flush_r) m_flush_r<=0;
                // ---- BTB and return stack, from the instruction leaving E
                if (e_go && !e_exc && e_control) begin
                    if (e_taken) begin
                        btb_valid[pc[2 +: BTB_BITS]]<=1'b1;
                        btb_tag[pc[2 +: BTB_BITS]]<=pc[2+BTB_BITS +: BTB_TAG];
                        btb_target[pc[2 +: BTB_BITS]]<=next_pc[31:2];
                        btb_ret[pc[2 +: BTB_BITS]]<=e_return;
                        btb_ctr[pc[2 +: BTB_BITS]]<=!e_bhit ? 2'd2 : e_bctr==2'd3 ? 2'd3 : e_bctr+2'd1;
                    end else if (e_bhit)
                        btb_ctr[pc[2 +: BTB_BITS]]<=e_bctr==2'd0 ? 2'd0 : e_bctr-2'd1;
                end
                // Return stack, as calls and returns are fetched.
                if (f_go && !f_fault && f_call) begin
                    ras[ras_sp+2'd1]<=f_pc+64'd4; ras_sp<=ras_sp+2'd1;
                end else if (f_go && !f_fault && f_return) ras_sp<=ras_sp-2'd1;
                // ---- D -> E
                if (e_redirect) e_redirected<=1;
                if (m_flush_r) e_valid<=0;
                else if (e_load) begin
                    if (d_go) begin
                        e_valid<=1; pc<=d_pc; insn<=d_insn; e_a<=d_a; e_b<=d_b;
                        e_pred<=d_want; e_ptaken<=d_take_pred; e_alt<=d_take_pred ? d_seq : d_target;
                        e_bhit<=d_bhit; e_bctr<=d_bctr;
                        e_fault<=d_fault; e_fcause<=d_fcause; e_redirected<=0;
                    end else e_valid<=0;
                end else if (e_valid) begin e_a<=a; e_b<=b; end  // waiting: keep forwarded values
                // ---- queue or F -> D
                if (m_flush_r || e_redirect) d_valid<=0;
                else if (d_fire) begin
                    d_redirected<=1;
                    if (d_go) d_valid<=0;
                end else if (d_take) begin
                    if (q_pop) begin
                        d_valid<=1; d_pc<=q_pc[q_head]; d_insn<=q_insn[q_head]; d_pred<=q_pred[q_head];
                        d_fpred<=q_fpred[q_head]; d_bhit<=q_bhit[q_head]; d_bctr<=q_bctr[q_head];
                        d_fault<=q_fault[q_head]; d_fcause<=q_fmis[q_head] ? 2'd0 : 2'd1;
                        d_redirected<=0;
                    end else if (f_bypass) begin
                        d_valid<=1; d_pc<=f_pc; d_insn<=f_word; d_pred<=f_pred;
                        d_fpred<=f_btaken; d_bhit<=f_bhit; d_bctr<=btb_ctr[f_bidx];
                        d_fault<=f_fault; d_fcause<=f_misaligned ? 2'd0 : 2'd1;
                        d_redirected<=0;
                    end else d_valid<=0;
                end
                // ---- fetch queue
                if (front_kill) begin
                    q_head<=0; q_tail<=0; q_count<=0; q_used<=0;
                end else begin
                    if (q_push) begin
                        q_pc[q_tail]<=f_pc; q_insn[q_tail]<=f_word; q_pred[q_tail]<=f_pred;
                        q_fpred[q_tail]<=f_btaken; q_bhit[q_tail]<=f_bhit; q_bctr[q_tail]<=btb_ctr[f_bidx];
                        q_fault[q_tail]<=f_fault; q_fmis[q_tail]<=f_misaligned;
                        q_tail<=q_tail+2'd1;
                    end
                    if (q_pop) q_head<=q_head+2'd1;
                    q_count<=q_count + {2'b0,q_push} - {2'b0,q_pop};
                    q_used<=(q_used & ~(q_pop ? 4'b0001 << q_head : 4'b0)) | (q_push ? 4'b0001 << q_tail : 4'b0);
                end
                // ---- F
                if (init_done) f_pc<=fetch_next;
            end
        end
    end
endmodule
