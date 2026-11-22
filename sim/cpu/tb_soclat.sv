// SPDX-License-Identifier: MIT
// Memory hand-off 1 directed check: SoC read latency (multicycle core). Reports the trap cycle
// and cause of a short program; the driver checks them against the parameters.
`timescale 1ns/1ps
module tb_soclat #(parameter integer L2_KIB = 0, parameter integer L2_WAYS = 8, parameter integer L2_LINE = 64,
                   parameter integer L2_LAT = 12, parameter integer MEM_LAT = 1);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc #(.L2_KIB(L2_KIB),.L2_WAYS(L2_WAYS),.L2_LINE(L2_LINE),.L2_LAT(L2_LAT),.MEM_LAT(MEM_LAT)) dut(
        .clk(clk),.reset(reset),.trapped(trapped),.trap_pc(pc),.trap_cause(cause),.trap_tval(tval),
        .retire_valid(retired),.retire_pc(rpc));
    string image_path;
    integer cycles=0;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing image");
        $readmemh(image_path,dut.ram);
        repeat (4) @(negedge clk);
        reset=0;
    end
    always @(negedge clk) if (!reset) begin
        cycles=cycles+1;
        if (cycles>5000000) $fatal(1,"SoC latency test timeout");
        if (trapped) begin
            $display("TRAP cycles=%0d cause=%0d tval=%h",cycles,cause,tval);
            $finish;
        end
    end
endmodule
