// SPDX-License-Identifier: MIT
// Original CPU foundation. RV64I execution + serialized FENCE.I, terminal EEI.
// Architecture version: see cpu/VERSION and cpu/architecture.md section 9.
// No RVA23 compliance claim. See cpu/architecture.md and cpu/README.md.
module rv64_core #(
    parameter [63:0] RESET_PC = 64'h0,
    // Direct-mapped instruction cache size in 8-byte beats; power of two, >= 2.
    parameter integer ICACHE_BEATS = 512
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
    output reg [63:0]  retire_next_pc
);
    localparam [1:0] FETCH=0, EXECUTE=1, MEMORY=2, HALTED=3;
    reg [1:0] state;
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
    wire issue_data = state == EXECUTE && (load_op || store_op) && !exception;
    wire [63:0] access_addr = state == MEMORY ? pending_addr : effective_addr;
    wire [2:0] access_f3 = state == MEMORY ? pending_f3 : f3;
    wire [63:0] issue_wdata = b << {effective_addr[2:0],3'b000};
    wire [7:0] issue_wstrb = store_op ? byte_mask << effective_addr[2:0] : 8'b0;
    wire [63:0] shifted_read = mem_rdata >> {access_addr[2:0],3'b000};
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
                legal=f7==0 || (f7==7'h20 && (f3==0 || f3==5));
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
                legal=f7==0 || (f7==7'h20 && (f3==0 || f3==5));
                case (f3)
                    0: word_result=insn[30] ? a[31:0]-b[31:0] : a[31:0]+b[31:0];
                    1: word_result=a[31:0]<<b[4:0];
                    5: if (insn[30]) word_result=$signed(a[31:0])>>>b[4:0]; else word_result=a[31:0]>>b[4:0];
                    default: legal=0;
                endcase
                result={{32{word_result[31]}},word_result};
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
    task automatic retire(input [4:0] dest, input [63:0] data, input [63:0] successor,
                          input flush, input stored, input [63:0] store_addr);
        begin
            retire_valid<=1; retire_pc<=pc; retire_insn<=insn;
            retire_rd<=dest; retire_data<=dest==0 ? 64'b0 : data;
            retire_next_pc<=successor;
            if (dest!=0) regs[dest]<=data;
            pc<=successor;
            if (flush) ic_valid<=0;
            else if (stored && ic_tag[store_addr[3 +: IC_INDEX]]==store_addr[63 -: IC_TAG])
                ic_valid[store_addr[3 +: IC_INDEX]]<=1'b0;
            if (!flush && ic_valid[successor[3 +: IC_INDEX]] &&
                ic_tag[successor[3 +: IC_INDEX]]==successor[63 -: IC_TAG] &&
                !(stored && store_addr[63:3]==successor[63:3])) begin
                insn<=successor[2] ? ic_data[successor[3 +: IC_INDEX]][63:32]
                                   : ic_data[successor[3 +: IC_INDEX]][31:0];
                state<=EXECUTE;
            end else state<=FETCH;
        end
    endtask

    integer i;
    always @(posedge clk) begin
        if (reset) begin
            state<=FETCH; pc<=RESET_PC; insn<=0;
            trap_valid<=0; trap_pc<=0; trap_cause<=0; trap_tval<=0;
            retire_valid<=0; retire_pc<=0; retire_insn<=0;
            retire_rd<=0; retire_data<=0; retire_next_pc<=0;
            pending_addr<=0; pending_wdata<=0; pending_wstrb<=0;
            pending_f3<=0; pending_rd<=0; pending_load<=0; pending_next_pc<=0;
            ic_valid<=0;
            for (i=0;i<32;i=i+1) regs[i]<=0;
        end else begin
            retire_valid<=0;
            case (state)
                FETCH: begin
                    if (pc[1:0]!=0) report_trap(0,pc);
                    else if (mem_ready) begin
                        if (mem_error) report_trap(1,pc);
                        else begin
                            insn<=pc[2] ? mem_rdata[63:32] : mem_rdata[31:0];
                            ic_valid[pc[3 +: IC_INDEX]]<=1'b1;
                            ic_tag[pc[3 +: IC_INDEX]]<=pc[63 -: IC_TAG];
                            ic_data[pc[3 +: IC_INDEX]]<=mem_rdata;
                            state<=EXECUTE;
                        end
                    end
                end
                EXECUTE: begin
                    if (exception) report_trap(exception_cause,exception_tval);
                    else if (load_op || store_op) begin
                        if (mem_ready) begin // completed in the same clock it was issued
                            if (mem_error) report_trap(load_op ? 5 : 7,effective_addr);
                            else retire(load_op ? rd : 5'b0,load_result,next_pc,1'b0,store_op,effective_addr);
                        end else begin
                            pending_addr<=effective_addr; pending_wdata<=issue_wdata;
                            pending_wstrb<=issue_wstrb;
                            pending_load<=load_op; pending_f3<=f3; pending_rd<=rd;
                            pending_next_pc<=next_pc; state<=MEMORY;
                        end
                    end else retire(write_rd ? rd : 5'b0,result,next_pc,op==7'h0f && f3==1,1'b0,64'b0);
                end
                MEMORY: if (mem_ready) begin
                    if (mem_error) report_trap(pending_load ? 5 : 7,pending_addr);
                    else retire(pending_load ? pending_rd : 5'b0,load_result,pending_next_pc,
                                1'b0,!pending_load,pending_addr);
                end
                HALTED: begin end
                default: report_trap(2,0);
            endcase
        end
    end
endmodule
