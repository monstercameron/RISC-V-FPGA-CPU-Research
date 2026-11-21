// SPDX-License-Identifier: MIT
// Benchmark bench: the core with its synchronous RAM wrapper. Counts clocks
// and retired instructions between the program's start and stop marker writes
// to mailbox word 0, then prints the mailbox for the Python runner to check.
`timescale 1ns/1ps
module tb_bench #(parameter integer RAM_WORDS = 8192);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc #(.RAM_WORDS(RAM_WORDS)) dut(.clk(clk),.reset(reset),.trapped(trapped),
        .trap_pc(pc),.trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc));

    string image_path;
    reg [63:0] mailbox=64'hffffffffffffffff, marker=0;
    integer index,i,cycles=0,retirements=0,max_cycles=50000000;
    integer start_cycle=-1,start_retired=-1,stop_cycle=-1,stop_retired=-1;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing +image");
        if (!$value$plusargs("mailbox=%h",mailbox)) $fatal(1,"missing +mailbox");
        if ($value$plusargs("max_cycles=%d",max_cycles)) begin end
        if (mailbox[2:0]!=0 || mailbox+256>RAM_WORDS*8) $fatal(1,"mailbox outside RAM");
        index=mailbox>>3;
        $readmemh(image_path,dut.ram);
        repeat (4) @(negedge clk);
        #1 reset=0;
    end

    // Sampled between edges: a marker store has updated RAM and not yet retired,
    // so each region includes the start-marker store and excludes the stop one.
    always @(negedge clk) if (!reset) begin
        cycles=cycles+1;
        if (retired) retirements=retirements+1;
        if (cycles>max_cycles) $fatal(1,"benchmark exceeded %0d cycles",max_cycles);
        if (dut.ram[index]!==marker) begin
            if (dut.ram[index]==1 && start_cycle<0) begin
                start_cycle=cycles; start_retired=retirements;
            end else if (dut.ram[index]==2 && start_cycle>=0 && stop_cycle<0) begin
                stop_cycle=cycles; stop_retired=retirements;
            end else $fatal(1,"unexpected marker value %0h",dut.ram[index]);
            marker=dut.ram[index];
        end
        if (trapped) begin
            if (cause!==3 || tval!==0) $fatal(1,"unexpected trap cause=%0d tval=%016h pc=%016h",cause,tval,pc);
            if (stop_cycle<0) $fatal(1,"benchmark did not write both markers");
            $display("COUNTERS cycles=%0d retirements=%0d trap_pc=%016h",cycles,retirements,pc);
            $display("REGION cycles=%0d retirements=%0d",stop_cycle-start_cycle,stop_retired-start_retired);
            for (i=1;i<32;i=i+1) $display("MAILBOX %0d %016h",i,dut.ram[index+i]);
            $finish;
        end
    end
endmodule
