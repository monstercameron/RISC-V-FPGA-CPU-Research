// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_reset;
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire valid,instr,trapped,retired;
    wire [63:0] addr,wdata,tpc,cause,tval,rpc,rval,npc;
    wire [7:0] mask;
    wire [31:0] rinsn;
    wire [4:0] rd;
    reg ready=0;
    reg [63:0] rdata=0;
    integer cycles=0,writes=0,phase=0,reset_cycles=0;
    rv64_core dut(.clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(mask),.mem_ready(ready),
        .mem_rdata(rdata),.mem_error(1'b0),.trap_valid(trapped),.trap_pc(tpc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),
        .retire_insn(rinsn),.retire_rd(rd),.retire_data(rval),.retire_next_pc(npc));
    initial begin repeat(4) @(negedge clk); reset=0; end
    always @(negedge clk) begin
        cycles=cycles+1;
        if (cycles>200) $fatal(1,"reset test timeout");
        if (phase==0 && valid && mask!=0) begin
            reset=1; ready=0; phase=1; reset_cycles=0;
        end else if (phase==1) begin
            if (valid || trapped || retired) $fatal(1,"reset did not clear interface");
            reset_cycles=reset_cycles+1;
            if (reset_cycles==3) begin reset=0; phase=2; end
        end
        ready=!reset && valid && (mask==0 || phase==2);
        // addi x3,x3,1; lui x2,3; sd x3,0(x2); ebreak
        case (addr)
            0: rdata=64'h0000313700118193;
            8: rdata=64'h0010007300313023;
            default: rdata=0;
        endcase
        if (!reset && retired && rd==3 && rval!==1) $fatal(1,"registers not reset");
        if (trapped) begin
            if (phase!=2 || cause!==3 || writes!=1) $fatal(1,"reset/store lifecycle failed");
            $display("PASS reset cancels unacknowledged store with shared fabric reset; one post-reset write");
            $finish;
        end
    end
    always @(posedge clk) if (!reset && valid && ready && mask!=0) begin
        writes=writes+1;
        if (wdata!==1 || addr!==64'h3000 || mask!==8'hff) $fatal(1,"wrong store after reset");
    end
endmodule
