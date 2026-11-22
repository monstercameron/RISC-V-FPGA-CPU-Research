// SPDX-License-Identifier: MIT
// Benchmark bench: the core with its synchronous RAM wrapper. Counts clocks
// and retired instructions between the program's start and stop marker writes
// to mailbox word 0, then prints the mailbox for the Python runner to check.
// Marker values 16-255 are laps, printed without changing the region. With
// +sample_from=N +sample_to=M (retirement counts since reset) the bench instead
// times that retirement window, prints it and stops there; markers are then only
// reported. The LZMA benchmark runner uses both; Dhrystone uses neither.
// +image_bin=FILE loads RAM from raw big-endian 64-bit words (word 0 first), the
// rest zero, instead of +image hex; the runner uses it for multi-MiB images. Off
// by default. Clock and retirement counts are 64-bit (longint), so whole runs of
// billions of clocks do not wrap.
`timescale 1ns/1ps
// ICACHE_BEATS/DCACHE_BEATS set the core's cache sizes (8-byte beats); the defaults keep the SoC's 4 KiB.
module tb_bench #(parameter integer RAM_WORDS = 8192, parameter integer ICACHE_BEATS = 512,
                  parameter integer DCACHE_BEATS = 512, parameter integer L2_KIB = 0, parameter integer L2_WAYS = 8,
                  parameter integer L2_LINE = 64, parameter integer L2_LAT = 12, parameter integer MEM_LAT = 1,
                  parameter integer MEM_GAP = 0, parameter integer WRITE_FILL = 0, parameter integer N_MISS = 1);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    wire trapped,retired,retired2,retired3;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc #(.RAM_WORDS(RAM_WORDS),.ICACHE_BEATS(ICACHE_BEATS),.DCACHE_BEATS(DCACHE_BEATS),.L2_KIB(L2_KIB),
        .L2_WAYS(L2_WAYS),.L2_LINE(L2_LINE),.L2_LAT(L2_LAT),.MEM_LAT(MEM_LAT),.MEM_GAP(MEM_GAP),.WRITE_FILL(WRITE_FILL),.N_MISS(N_MISS)) dut(.clk(clk),.reset(reset),.trapped(trapped),
        .trap_pc(pc),.trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),.retire2_valid(retired2),
        .retire3_valid(retired3));

    string image_path,profile_path;
    // Not named `mailbox`: that is a SystemVerilog built-in class Verilator reserves.
    reg [63:0] mailbox_addr=64'hffffffffffffffff, marker=0;
    integer index,i,profile_fd=0,laps=0,image_fd=0;
`ifdef L2_PRELOAD
    string preload_path;
    integer preload_fd;
    reg [3:0] pl_v;
    reg [63:0] pl_tag,pl_use;
`endif
    longint cycles=0,retirements=0,max_cycles=50000000;
    longint start_cycle=-1,start_retired=-1,stop_cycle=-1,stop_retired=-1;
    longint sample_from=-1,sample_to=-1,sample_cycle=-1,sample_retired=-1;
    // Clocks spent in each core state since the previous retirement.
    integer in_fetch=0,in_execute=0,in_memory=0,w;
    initial begin
        if ($value$plusargs("image_bin=%s",image_path)) image_fd=1;
        else if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing +image");
        if ($value$plusargs("profile=%s",profile_path)) begin
            profile_fd=$fopen(profile_path,"w");
            if (!profile_fd) $fatal(1,"cannot open +profile file");
        end
        if (!$value$plusargs("mailbox=%h",mailbox_addr)) $fatal(1,"missing +mailbox");
        if ($value$plusargs("max_cycles=%d",max_cycles)) begin end
        if ($value$plusargs("sample_from=%d",sample_from) != $value$plusargs("sample_to=%d",sample_to))
            $fatal(1,"+sample_from and +sample_to go together");
        if (sample_to>=0 && !(sample_from>=0 && sample_to>sample_from)) $fatal(1,"bad sample window");
        if (mailbox_addr[2:0]!=0 || mailbox_addr+256>RAM_WORDS*8) $fatal(1,"mailbox outside RAM");
        index=mailbox_addr>>3;
        if (image_fd) begin
            for (i=0;i<RAM_WORDS;i=i+1) dut.ram[i]=0;
            image_fd=$fopen(image_path,"rb");
            if (!image_fd) $fatal(1,"cannot open +image_bin file");
            if ($fread(dut.ram,image_fd)<=0) $fatal(1,"empty +image_bin file");
            $fclose(image_fd);
        end else $readmemh(image_path,dut.ram);
        repeat (4) @(negedge clk);
        #1 reset=0;
`ifdef L2_PRELOAD
        // +l2_preload=FILE (built with -DL2_PRELOAD for an SoC with the tags-only L2): L2 tags
        // from rv_iss --warm-caches, loaded once reset has stopped clearing them. Off by default.
        if ($value$plusargs("l2_preload=%s",preload_path)) begin
            preload_fd=$fopen(preload_path,"r");
            if (!preload_fd) $fatal(1,"cannot open +l2_preload file");
            for (i=0;;i=i+1) begin
                if ($fscanf(preload_fd,"%h %h %h\n",pl_v,pl_tag,pl_use)!=3) $fatal(1,"short +l2_preload file");
                if (pl_v==2) begin dut.l2_clock=pl_tag; break; end
                dut.l2_valid[i]=pl_v[0]; dut.l2_tag[i]=pl_tag; dut.l2_use[i]=pl_use;
`ifdef L2_PRELOAD_READY
                dut.l2_ready[i]=0;   // SoCs that time line fills (memory hand-off 2)
`endif
            end
            $fclose(preload_fd);
            $display("L2PRELOAD entries=%0d",i);
        end
`endif
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
        for (w=0;w<$bits(dut.cpu.rt_valid);w=w+1) if (dut.cpu.rt_valid[w]) retirements=retirements+1;
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
            for (w=3;w<$bits(dut.cpu.rt_valid);w=w+1) if (dut.cpu.rt_valid[w] && profile_fd!=0 && start_cycle>=0 && stop_cycle<0)
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
        if (sample_to>=0) begin
            if (sample_cycle<0 && retirements>=sample_from) begin
                sample_cycle=cycles; sample_retired=retirements;
            end
            if (dut.ram[index]!==marker) begin
                $display("MARK %0d cycles=%0d retirements=%0d",dut.ram[index],cycles,retirements);
                marker=dut.ram[index];
            end
            if (retirements>=sample_to || trapped) begin
                $display("SAMPLE cycles=%0d retirements=%0d from_cycle=%0d from_retired=%0d to_cycle=%0d to_retired=%0d trapped=%0d",
                    cycles-sample_cycle,retirements-sample_retired,sample_cycle,sample_retired,cycles,retirements,trapped);
                $finish;
            end
        end else if (dut.ram[index]!==marker) begin
            if (dut.ram[index]==1 && start_cycle<0) begin
                start_cycle=cycles; start_retired=retirements;
            end else if (dut.ram[index]==2 && start_cycle>=0 && stop_cycle<0) begin
                stop_cycle=cycles; stop_retired=retirements;
            end else if (dut.ram[index]>=16 && dut.ram[index]<256) begin
                // Lap markers (16-255, used by the LZMA benchmark to split its phases):
                // reported with the same sampling as the region, which they do not change.
                $display("LAP %0d cycles=%0d retirements=%0d",dut.ram[index],cycles,retirements);
                laps=laps+1;
            end else $fatal(1,"unexpected marker value %0h",dut.ram[index]);
            marker=dut.ram[index];
        end
        if (trapped && sample_to<0) begin
            if (cause!==3 || tval!==0) $fatal(1,"unexpected trap cause=%0d tval=%016h pc=%016h",cause,tval,pc);
            if (stop_cycle<0) $fatal(1,"benchmark did not write both markers");
            $display("COUNTERS cycles=%0d retirements=%0d trap_pc=%016h",cycles,retirements,pc);
            $display("REGION cycles=%0d retirements=%0d",stop_cycle-start_cycle,stop_retired-start_retired);
            // With laps, also the region's absolute edges, so laps can be related to it.
            if (laps>0) $display("EDGES start_cycle=%0d start_retired=%0d stop_cycle=%0d stop_retired=%0d",
                start_cycle,start_retired,stop_cycle,stop_retired);
            for (i=1;i<32;i=i+1) $display("MAILBOX %0d %016h",i,dut.ram[index+i]);
            if (profile_fd!=0) $fclose(profile_fd);
            $finish;
        end
    end
endmodule
