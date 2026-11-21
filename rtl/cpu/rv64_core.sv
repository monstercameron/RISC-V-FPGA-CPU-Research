// SPDX-License-Identifier: MIT
// Original CPU foundation. RV64IM execution + serialized FENCE.I, terminal EEI.
// Architecture version: see cpu/VERSION and cpu/architecture.md section 9.
// No RVA23 compliance claim. See cpu/architecture.md and cpu/README.md.
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
    output reg [63:0]  retire2_next_pc
);
    localparam [2:0] FETCH=0, EXECUTE=1, MEMORY=2, HALTED=3, DIVIDE=4;
    reg [2:0] state;
    reg [63:0] pc;
    reg [31:0] insn;
    reg [63:0] regs [0:31];
    wire [6:0] op = insn[6:0];
    wire [2:0] f3 = insn[14:12];
    wire [6:0] f7 = insn[31:25];
    wire [4:0] rd = insn[11:7];
    wire [63:0] a = insn[19:15] == 0 ? 64'b0 : regs[insn[19:15]];
    wire [63:0] b = insn[24:20] == 0 ? 64'b0 : regs[insn[24:20]];
    wire [63:0] imm_i = {{52{insn[31]}},insn[31:20]};
    wire [63:0] imm_s = {{52{insn[31]}},insn[31:25],insn[11:7]};
    wire [63:0] imm_b = {{51{insn[31]}},insn[31],insn[7],insn[30:25],insn[11:8],1'b0};
    wire [63:0] imm_u = {{32{insn[31]}},insn[31:12],12'b0};
    wire [63:0] imm_j = {{43{insn[31]}},insn[31],insn[19:12],insn[20],insn[30:21],1'b0};

    reg legal, write_rd, load_op, store_op, branch_taken, exception;
    reg [63:0] result, next_pc, effective_addr, exception_cause, exception_tval;
    reg [31:0] word_result;
    reg [7:0] byte_mask;
    reg [63:0] access_mask;

    // M extension (0.4.0). Multiplies complete in EXECUTE. Divides and remainders
    // complete in EXECUTE for divide-by-zero, signed overflow and a dividend smaller
    // than the divisor; otherwise DIVIDE runs one shift-subtract step per clock,
    // starting at the quotient's highest possible bit (clz difference + 1 steps).
    wire m_op = (op == 7'h33 || op == 7'h3b) && f7 == 7'h01;
    wire m_word = op == 7'h3b;
    wire is_div = m_op && f3[2];
    wire div_signed = !f3[0];
    wire want_rem = f3[1];
    wire [63:0] sext_a32 = {{32{a[31]}},a[31:0]};
    wire [63:0] da = m_word ? (div_signed ? sext_a32 : {32'b0,a[31:0]}) : a;
    wire [63:0] db = m_word ? (div_signed ? {{32{b[31]}},b[31:0]} : {32'b0,b[31:0]}) : b;
    wire neg_a = div_signed && da[63];
    wire neg_b = div_signed && db[63];
    wire [63:0] mag_a = neg_a ? 64'd0 - da : da;
    wire [63:0] mag_b = neg_b ? 64'd0 - db : db;
    wire div_by_zero = db == 0;
    wire div_overflow = div_signed && da == (m_word ? 64'hffffffff80000000 : 64'h8000000000000000) && db == {64{1'b1}};
    wire div_start = is_div && !div_by_zero && !div_overflow && mag_a >= mag_b;
    wire [127:0] p_uu = {64'b0,a} * {64'b0,b};
    wire [127:0] p_ss = {{64{a[63]}},a} * {{64{b[63]}},b};
    wire [127:0] p_su = {{64{a[63]}},a} * {64'b0,b};
    wire [31:0] p_w = a[31:0] * b[31:0];
    reg [63:0] m_result;
    reg [63:0] div_rem, div_den, div_quot, div_bit;
    reg div_neg_q, div_neg_r, div_want_rem, div_is_word;

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

    always @* begin
        case (f3)
            0: m_result = m_word ? {{32{p_w[31]}},p_w} : p_uu[63:0];
            1: m_result = p_ss[127:64];
            2: m_result = p_su[127:64];
            3: m_result = p_uu[127:64];
            default:
                if (div_by_zero) m_result = want_rem ? (m_word ? sext_a32 : a) : {64{1'b1}};
                else if (div_overflow) m_result = want_rem ? 64'b0 : da;
                else m_result = div_finish(64'b0, mag_a, neg_a ^ neg_b, neg_a, want_rem, m_word);
        endcase
    end
    // Dual issue (0.5.0). insn2 is the instruction at pc+4 when it is in the same
    // 8-byte beat as insn. It executes alongside insn when it is a simple integer
    // operation (OP, OP-IMM, their 32-bit forms, LUI, AUIPC; no M), reads no register
    // that insn writes, does not write the same register, and insn completes this
    // clock: an integer operation other than a divide, a load that hits the data
    // cache, or a store to a different beat (which therefore cannot modify insn2).
    reg [31:0] insn2;
    reg insn2_valid;
    wire [6:0] op2 = insn2[6:0];
    wire [2:0] f3_2 = insn2[14:12];
    wire [6:0] f7_2 = insn2[31:25];
    wire [4:0] rd2 = insn2[11:7];
    wire [4:0] rs1_2 = insn2[19:15];
    wire [4:0] rs2_2 = insn2[24:20];
    wire [63:0] a2 = rs1_2 == 0 ? 64'b0 : regs[rs1_2];
    wire [63:0] b2 = rs2_2 == 0 ? 64'b0 : regs[rs2_2];
    wire [63:0] pc2 = pc + 64'd4;
    wire [63:0] imm_i2 = {{52{insn2[31]}},insn2[31:20]};
    wire [63:0] imm_u2 = {{32{insn2[31]}},insn2[31:12],12'b0};
    reg simple2, uses_rs1_2, uses_rs2_2;
    reg [63:0] result2;
    reg [31:0] word2;
    always @* begin
        simple2=0; uses_rs1_2=1; uses_rs2_2=0; result2=0; word2=0;
        case (op2)
            7'h37: begin simple2=1; uses_rs1_2=0; result2=imm_u2; end
            7'h17: begin simple2=1; uses_rs1_2=0; result2=pc2+imm_u2; end
            7'h13: begin
                simple2=1;
                case (f3_2)
                    0: result2=a2+imm_i2;
                    2: result2={63'b0,$signed(a2)<$signed(imm_i2)};
                    3: result2={63'b0,a2<imm_i2};
                    4: result2=a2^imm_i2;
                    6: result2=a2|imm_i2;
                    7: result2=a2&imm_i2;
                    1: begin simple2=insn2[31:26]==0; result2=a2<<insn2[25:20]; end
                    5: begin
                        simple2=insn2[31:26]==0 || insn2[31:26]==6'h10;
                        if (insn2[30]) result2=$signed(a2)>>>insn2[25:20]; else result2=a2>>insn2[25:20];
                    end
                endcase
            end
            7'h1b: begin
                case (f3_2)
                    0: begin simple2=1; word2=a2[31:0]+imm_i2[31:0]; end
                    1: begin simple2=f7_2==0; word2=a2[31:0]<<insn2[24:20]; end
                    5: begin
                        simple2=f7_2==0 || f7_2==7'h20;
                        if (insn2[30]) word2=$signed(a2[31:0])>>>insn2[24:20]; else word2=a2[31:0]>>insn2[24:20];
                    end
                    default: simple2=0;
                endcase
                result2={{32{word2[31]}},word2};
            end
            7'h33: begin
                uses_rs2_2=1;
                simple2=f7_2==0 || (f7_2==7'h20 && (f3_2==0 || f3_2==5));
                case (f3_2)
                    0: result2=insn2[30] ? a2-b2 : a2+b2;
                    1: result2=a2<<b2[5:0];
                    2: result2={63'b0,$signed(a2)<$signed(b2)};
                    3: result2={63'b0,a2<b2};
                    4: result2=a2^b2;
                    5: if (insn2[30]) result2=$signed(a2)>>>b2[5:0]; else result2=a2>>b2[5:0];
                    6: result2=a2|b2;
                    7: result2=a2&b2;
                endcase
            end
            7'h3b: begin
                uses_rs2_2=1;
                simple2=(f7_2==0 && (f3_2==0 || f3_2==1 || f3_2==5)) || (f7_2==7'h20 && (f3_2==0 || f3_2==5));
                case (f3_2)
                    0: word2=insn2[30] ? a2[31:0]-b2[31:0] : a2[31:0]+b2[31:0];
                    1: word2=a2[31:0]<<b2[4:0];
                    5: if (insn2[30]) word2=$signed(a2[31:0])>>>b2[4:0]; else word2=a2[31:0]>>b2[4:0];
                    default: word2=0;
                endcase
                result2={{32{word2[31]}},word2};
            end
            default: simple2=0;
        endcase
    end
    wire slot0_writes = (load_op || write_rd) && rd != 0;
    wire hazard2 = slot0_writes && ((uses_rs1_2 && rs1_2 == rd) || (uses_rs2_2 && rs2_2 == rd) || rd2 == rd);
    wire can_pair = insn2_valid && simple2 && !hazard2;
    wire slot0_alu = op == 7'h37 || op == 7'h17 || op == 7'h13 || op == 7'h1b ||
                     ((op == 7'h33 || op == 7'h3b) && !is_div);
    wire pair_alu = can_pair && slot0_alu;
    wire pair_load = can_pair && load_hit;
    wire pair_store = can_pair && store_op && effective_addr[63:3] != pc[63:3];

    // One DIVIDE step, and whether it is the last.
    wire div_take = div_rem >= div_den;
    wire [63:0] div_rem_next = div_take ? div_rem - div_den : div_rem;
    wire [63:0] div_quot_next = div_take ? div_quot | div_bit : div_quot;

    // Instruction cache (0.2.0): direct-mapped, one 8-byte beat per line, filled by
    // every bus fetch. A successor that hits skips FETCH. Reset and fence.i clear
    // every line; a successful store clears the line holding its beat, so fetched
    // instructions always reflect completed stores, as without the cache.
    localparam integer IC_INDEX = $clog2(ICACHE_BEATS);
    localparam integer IC_TAG = 61 - IC_INDEX;
    generate if (ICACHE_BEATS < 2 || (ICACHE_BEATS & (ICACHE_BEATS - 1)) != 0) begin : bad_icache_size
        initial $fatal(1, "ICACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    reg [ICACHE_BEATS-1:0] ic_valid;

    // Data cache (0.3.0): direct-mapped, one 8-byte beat per line, write-through
    // with no allocation on stores. A successful load fills its line; a successful
    // store updates a line that holds its beat. A load that hits completes in
    // EXECUTE with no bus request. All addresses are treated as cacheable.
    localparam integer DC_INDEX = $clog2(DCACHE_BEATS);
    localparam integer DC_TAG = 61 - DC_INDEX;
    generate if (DCACHE_BEATS < 2 || (DCACHE_BEATS & (DCACHE_BEATS - 1)) != 0) begin : bad_dcache_size
        initial $fatal(1, "DCACHE_BEATS must be a power of two of at least 2");
    end endgenerate
    reg [DCACHE_BEATS-1:0] dc_valid;
    reg [DC_TAG-1:0] dc_tag [0:DCACHE_BEATS-1];
    reg [63:0] dc_data [0:DCACHE_BEATS-1];
    reg [IC_TAG-1:0] ic_tag [0:ICACHE_BEATS-1];
    reg [63:0] ic_data [0:ICACHE_BEATS-1];

    reg [63:0] pending_addr, pending_wdata, pending_next_pc;
    reg [7:0] pending_wstrb;
    reg [2:0] pending_f3;
    reg [4:0] pending_rd;
    reg pending_load;
    // Data accesses (0.2.1) start in EXECUTE as soon as the address is known and
    // no exception is pending; if the bus has not completed by the end of that
    // clock, MEMORY holds the identical request from the pending registers.
    wire [DC_INDEX-1:0] dc_index = effective_addr[3 +: DC_INDEX];
    wire load_hit = state == EXECUTE && load_op && !exception &&
                    dc_valid[dc_index] && dc_tag[dc_index] == effective_addr[63 -: DC_TAG];
    wire issue_data = state == EXECUTE && (load_op || store_op) && !exception && !load_hit;
    wire [63:0] access_addr = state == MEMORY ? pending_addr : effective_addr;
    wire [2:0] access_f3 = state == MEMORY ? pending_f3 : f3;
    wire [63:0] issue_wdata = b << {effective_addr[2:0],3'b000};
    wire [7:0] issue_wstrb = store_op ? byte_mask << effective_addr[2:0] : 8'b0;
    wire [63:0] read_beat = load_hit ? dc_data[dc_index] : mem_rdata;
    wire [63:0] shifted_read = read_beat >> {access_addr[2:0],3'b000};
    reg [63:0] load_result;

    assign mem_valid = !reset && ((state == FETCH && pc[1:0] == 0) || state == MEMORY || issue_data);
    assign mem_instr = state == FETCH;
    assign mem_addr = state == FETCH ? {pc[63:3],3'b0} : {access_addr[63:3],3'b0};
    assign mem_wdata = state == MEMORY ? pending_wdata : issue_data ? issue_wdata : 64'b0;
    assign mem_wstrb = state == MEMORY ? pending_wstrb : issue_data ? issue_wstrb : 8'b0;

    always @* begin
        case (access_f3)
            3'b000: load_result = {{56{shifted_read[7]}},shifted_read[7:0]};
            3'b001: load_result = {{48{shifted_read[15]}},shifted_read[15:0]};
            3'b010: load_result = {{32{shifted_read[31]}},shifted_read[31:0]};
            3'b011: load_result = shifted_read;
            3'b100: load_result = {56'b0,shifted_read[7:0]};
            3'b101: load_result = {48'b0,shifted_read[15:0]};
            3'b110: load_result = {32'b0,shifted_read[31:0]};
            default: load_result = 64'b0;
        endcase
    end

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
                if (f7==7'h01) result=m_result;
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
                if (f7==7'h01) result=m_result;
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
        if (!legal) begin
            exception=1; exception_cause=2; exception_tval={32'b0,insn};
        end else if (next_pc[1:0]!=0) begin
            exception=1; exception_cause=0; exception_tval=next_pc;
        end
    end

    task automatic report_trap(input [63:0] cause, input [63:0] tval);
        begin
            trap_valid<=1; trap_pc<=pc; trap_cause<=cause; trap_tval<=tval;
            state<=HALTED;
        end
    endtask
    // flush: fence.i clears the cache. stored: a store to store_addr completed.
    // pair: insn2 retires on the second slot in the same clock; successor is pc+8.
    task automatic retire(input [4:0] dest, input [63:0] data, input [63:0] successor,
                          input flush, input stored, input [63:0] store_addr, input pair);
        begin
            retire_valid<=1; retire_pc<=pc; retire_insn<=insn;
            retire_rd<=dest; retire_data<=dest==0 ? 64'b0 : data;
            retire_next_pc<=pair ? pc2 : successor;
            if (dest!=0) regs[dest]<=data;
            if (pair) begin
                retire2_valid<=1; retire2_pc<=pc2; retire2_insn<=insn2;
                retire2_rd<=rd2; retire2_data<=rd2==0 ? 64'b0 : result2;
                retire2_next_pc<=successor;
                if (rd2!=0) regs[rd2]<=result2;
            end
            pc<=successor;
            insn2_valid<=0;
            if (flush) ic_valid<=0;
            else if (stored && ic_tag[store_addr[3 +: IC_INDEX]]==store_addr[63 -: IC_TAG])
                ic_valid[store_addr[3 +: IC_INDEX]]<=1'b0;
            if (!flush && ic_valid[successor[3 +: IC_INDEX]] &&
                ic_tag[successor[3 +: IC_INDEX]]==successor[63 -: IC_TAG] &&
                !(stored && store_addr[63:3]==successor[63:3])) begin
                insn<=successor[2] ? ic_data[successor[3 +: IC_INDEX]][63:32]
                                   : ic_data[successor[3 +: IC_INDEX]][31:0];
                insn2<=ic_data[successor[3 +: IC_INDEX]][63:32];
                insn2_valid<=!successor[2];
                state<=EXECUTE;
            end else state<=FETCH;
        end
    endtask

    // Record a completed data access in the data cache.
    task automatic dcache_update(input is_load, input [63:0] addr, input [63:0] beat,
                                 input [63:0] wdata, input [7:0] wstrb);
        integer lane;
        begin
            if (is_load) begin
                dc_valid[addr[3 +: DC_INDEX]]<=1'b1;
                dc_tag[addr[3 +: DC_INDEX]]<=addr[63 -: DC_TAG];
                dc_data[addr[3 +: DC_INDEX]]<=beat;
            end else if (dc_valid[addr[3 +: DC_INDEX]] && dc_tag[addr[3 +: DC_INDEX]]==addr[63 -: DC_TAG]) begin
                for (lane=0;lane<8;lane=lane+1)
                    if (wstrb[lane]) dc_data[addr[3 +: DC_INDEX]][8*lane+:8]<=wdata[8*lane+:8];
            end
        end
    endtask

    integer i;
    always @(posedge clk) begin
        if (reset) begin
            state<=FETCH; pc<=RESET_PC; insn<=0;
            trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_tval<=0;
            retire_valid<=0; retire_pc<=0; retire_insn<=0;
            retire_rd<=0; retire_data<=0; retire_next_pc<=0;
            retire2_valid<=0; retire2_pc<=0; retire2_insn<=0;
            retire2_rd<=0; retire2_data<=0; retire2_next_pc<=0;
            insn2<=0; insn2_valid<=0;
            pending_addr<=0; pending_wdata<=0; pending_wstrb<=0;
            pending_f3<=0; pending_rd<=0; pending_load<=0; pending_next_pc<=0;
            ic_valid<=0; dc_valid<=0;
            div_rem<=0; div_den<=0; div_quot<=0; div_bit<=0;
            div_neg_q<=0; div_neg_r<=0; div_want_rem<=0; div_is_word<=0;
            for (i=0;i<32;i=i+1) regs[i]<=0;
        end else begin
            retire_valid<=0; retire2_valid<=0;
            case (state)
                FETCH: begin
                    if (pc[1:0]!=0) report_trap(0,pc);
                    else if (mem_ready) begin
                        if (mem_error) report_trap(1,pc);
                        else begin
                            insn<=pc[2] ? mem_rdata[63:32] : mem_rdata[31:0];
                            insn2<=mem_rdata[63:32]; insn2_valid<=!pc[2];
                            ic_valid[pc[3 +: IC_INDEX]]<=1'b1;
                            ic_tag[pc[3 +: IC_INDEX]]<=pc[63 -: IC_TAG];
                            ic_data[pc[3 +: IC_INDEX]]<=mem_rdata;
                            state<=EXECUTE;
                        end
                    end
                end
                EXECUTE: begin
                    if (exception) report_trap(exception_cause,exception_tval);
                    else if (div_start) begin
                        div_rem<=mag_a; div_quot<=0;
                        div_den<=mag_b << (clz64(mag_b) - clz64(mag_a));
                        div_bit<=64'd1 << (clz64(mag_b) - clz64(mag_a));
                        div_neg_q<=neg_a ^ neg_b; div_neg_r<=neg_a;
                        div_want_rem<=want_rem; div_is_word<=m_word;
                        state<=DIVIDE;
                    end
                    else if (load_hit) retire(rd,load_result,pair_load ? pc+64'd8 : next_pc,1'b0,1'b0,64'b0,pair_load);
                    else if (load_op || store_op) begin
                        if (mem_ready) begin // completed in the same clock it was issued
                            if (mem_error) report_trap(load_op ? 5 : 7,effective_addr);
                            else begin
                                dcache_update(load_op,effective_addr,mem_rdata,issue_wdata,issue_wstrb);
                                retire(load_op ? rd : 5'b0,load_result,pair_store ? pc+64'd8 : next_pc,
                                       1'b0,store_op,effective_addr,pair_store);
                            end
                        end else begin
                            pending_addr<=effective_addr; pending_wdata<=issue_wdata;
                            pending_wstrb<=issue_wstrb;
                            pending_load<=load_op; pending_f3<=f3; pending_rd<=rd;
                            pending_next_pc<=next_pc; state<=MEMORY;
                        end
                    end else retire(write_rd ? rd : 5'b0,result,pair_alu ? pc+64'd8 : next_pc,
                                    op==7'h0f && f3==1,1'b0,64'b0,pair_alu);
                end
                MEMORY: if (mem_ready) begin
                    if (mem_error) report_trap(pending_load ? 5 : 7,pending_addr);
                    else begin
                        dcache_update(pending_load,pending_addr,mem_rdata,pending_wdata,pending_wstrb);
                        retire(pending_load ? pending_rd : 5'b0,load_result,pending_next_pc,
                               1'b0,!pending_load,pending_addr,1'b0);
                    end
                end
                DIVIDE: begin
                    if (div_bit == 64'd1)
                        retire(rd,div_finish(div_quot_next,div_rem_next,div_neg_q,div_neg_r,div_want_rem,div_is_word),
                               next_pc,1'b0,1'b0,64'b0,1'b0);
                    else begin
                        div_rem<=div_rem_next; div_quot<=div_quot_next;
                        div_den<=div_den >> 1; div_bit<=div_bit >> 1;
                    end
                end
                HALTED: begin end
                default: report_trap(2,0);
            endcase
        end
    end
endmodule
