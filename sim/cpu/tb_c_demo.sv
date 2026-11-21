// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_c_demo;
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc dut(.clk(clk),.reset(reset),.trapped(trapped),.trap_pc(pc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc));
    string image_path;
    integer cycles=0,retirements=0,i;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing BRAM image");
        $readmemh(image_path,dut.ram);
        // Release away from the checking edge to avoid a reset race.
        repeat (4) @(negedge clk);
        #1 reset=0;
    end
    always @(negedge clk) if (!reset) begin
        cycles=cycles+1;
        if (retired) retirements=retirements+1;
        if (dut.retire2_valid) retirements=retirements+1; // second slot (0.5.0)
        if (cycles>2000000) $fatal(1,"C demo timeout");
        if (trapped) begin
            if (cause!==3 || tval!==0) $fatal(1,"unexpected trap");
            if (dut.cpu.regs[10]!==0) $fatal(1,"main returned failure");
            $display("COUNTERS cycles=%0d retirements=%0d trap_pc=%016h",cycles,retirements,pc);
            for (i=0;i<8;i=i+1)
                $display("RESULT %0d %016h",i,dut.ram[1536+i]);
            $finish;
        end
    end
endmodule
