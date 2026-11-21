// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_soc;
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc dut(.clk(clk),.reset(reset),.trapped(trapped),.trap_pc(pc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc));
    string image_path;
    reg [63:0] expected=12;
    integer cycles=0;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing BRAM image");
        if ($value$plusargs("expected=%h",expected)) begin end
        $readmemh(image_path,dut.ram);
        repeat (4) @(negedge clk);
        reset=0;
    end
    always @(negedge clk) if (!reset) begin
        cycles=cycles+1;
        if (cycles>10000) $fatal(1,"SoC timeout");
        if (trapped) begin
            if (cause!==3 || dut.ram[1536]!==expected) $fatal(1,"wrong SoC result/cause");
            if ($test$plusargs("second") && dut.ram[1537]!==64'h000000240000007e)
                $fatal(1,"wrong second firmware signature");
            $display("PASS BRAM SoC signature=%0d cycles=%0d",dut.ram[1536],cycles);
            $finish;
        end
    end
endmodule
