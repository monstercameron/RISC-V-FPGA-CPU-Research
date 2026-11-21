// SPDX-License-Identifier: MIT
// Benchmark bench: the core with its synchronous RAM wrapper. Counts clocks
// and retired instructions between the program's start and stop marker writes
// to mailbox word 0, then prints the mailbox for the Python runner to check.
`timescale 1ns/1ps
module tb_bench #(parameter integer RAM_WORDS = 8192);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired,retired2,retired3;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc #(.RAM_WORDS(RAM_WORDS)) dut(.clk(clk),.reset(reset),.trapped(trapped),
        .trap_pc(pc),.trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),.retire2_valid(retired2),
        .retire3_valid(retired3));

    string image_path,profile_path;
    reg [63:0] mailbox=64'hffffffffffffffff, marker=0;
    integer index,i,cycles=0,retirements=0,max_cycles=50000000,profile_fd=0;
    integer start_cycle=-1,start_retired=-1,stop_cycle=-1,stop_retired=-1;
    // Clocks spent in each core state since the previous retirement.
    integer in_fetch=0,in_execute=0,in_memory=0,w;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing +image");
        if ($value$plusargs("profile=%s",profile_path)) begin
            profile_fd=$fopen(profile_path,"w");
            if (!profile_fd) $fatal(1,"cannot open +profile file");
        end
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
    // The out-of-order core (WIDE_TRACE) retires a store on the edge its write
    // completes, so there the region and the profile exclude the start-marker store
    // and include the stop one (found by the Codex review). With paired stores the
    // retirement group of a marker can move one instruction across the boundary:
    // 0.11.0 regions count 275,031 and 223,031 instructions where the trace has
    // 275,030 and 223,030 (second Codex review); clock counts are unaffected.
    always @(negedge clk) if (!reset) begin
        cycles=cycles+1;
`ifdef WIDE_TRACE
        // Out-of-order core (0.10.0): up to 8 retirements per clock in rt_*.
        for (w=0;w<8;w=w+1) if (dut.cpu.rt_valid[w]) retirements=retirements+1;
`else
        if (retired) retirements=retirements+1;
        if (retired2) retirements=retirements+1;
        if (retired3) retirements=retirements+1;
`endif
        // +profile: one line per instruction retired inside the timed region with
        // the clocks it spent in FETCH, EXECUTE (with DIVIDE) and MEMORY.
        if (retired) begin
            if (profile_fd!=0 && start_cycle>=0 && stop_cycle<0)
                $fdisplay(profile_fd,"R %016h %08h %02h %016h %0d %0d %0d",dut.cpu.retire_pc,
                    dut.cpu.retire_insn,dut.cpu.retire_rd,dut.cpu.retire_next_pc,in_fetch,in_execute,in_memory);
            // The second slot retires in the same clock and adds no clocks of its own.
            if (retired2 && profile_fd!=0 && start_cycle>=0 && stop_cycle<0)
                $fdisplay(profile_fd,"R %016h %08h %02h %016h 0 0 0",dut.cpu.retire2_pc,
                    dut.cpu.retire2_insn,dut.cpu.retire2_rd,dut.cpu.retire2_next_pc);
            if (retired3 && profile_fd!=0 && start_cycle>=0 && stop_cycle<0)
                $fdisplay(profile_fd,"R %016h %08h %02h %016h 0 0 0",dut.cpu.retire3_pc,
                    dut.cpu.retire3_insn,dut.cpu.retire3_rd,dut.cpu.retire3_next_pc);
`ifdef WIDE_TRACE
            for (w=3;w<8;w=w+1) if (dut.cpu.rt_valid[w] && profile_fd!=0 && start_cycle>=0 && stop_cycle<0)
                $fdisplay(profile_fd,"R %016h %08h %02h %016h 0 0 0",dut.cpu.rt_pc[64*w +: 64],
                    dut.cpu.rt_insn[32*w +: 32],dut.cpu.rt_rd[5*w +: 5],dut.cpu.rt_next[64*w +: 64]);
`endif
            in_fetch=0; in_execute=0; in_memory=0;
        end
        case (dut.cpu.state)
            0: in_fetch=in_fetch+1;
            1,4,5: in_execute=in_execute+1; // EXECUTE, DIVIDE (0.4.0) and MULTIPLY (0.7.1)
            2: in_memory=in_memory+1;
            default: begin end
        endcase
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
            if (profile_fd!=0) $fclose(profile_fd);
            $finish;
        end
    end
endmodule
