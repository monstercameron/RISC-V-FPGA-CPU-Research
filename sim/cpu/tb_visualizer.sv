// SPDX-License-Identifier: MIT
// Observe the actual core and synchronous RAM. No changes to synthesizable RTL.
`timescale 1ns/1ps
module tb_visualizer;
    reg clk=0, reset=1;
    always #5 clk=~clk;
    wire trapped,retired;
    wire [63:0] pc,cause,tval,rpc;
    rv64_bram_soc dut(.clk(clk),.reset(reset),.trapped(trapped),.trap_pc(pc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc));
    string image_path,trace_path;
    integer fd,cycles=0,retirements=0,flags;
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing image");
        if (!$value$plusargs("trace=%s",trace_path)) $fatal(1,"missing trace path");
        $readmemh(image_path,dut.ram);
        fd=$fopen(trace_path,"w");
        if (!fd) $fatal(1,"cannot open capture");
        repeat (4) @(negedge clk);
        #1 reset=0;
    end
    always @(posedge clk) if (!reset) begin
        cycles=cycles+1;
        if (cycles>2000000) $fatal(1,"capture timeout");
        // Sample inputs immediately before the edge's nonblocking updates.
        // Since architecture 0.2.2 the RAM writes on the edge that ends the clock in
        // which a write request is presented, and acknowledges it in that clock.
        flags=(dut.valid ? 1:0) | (dut.ready ? 2:0) | (dut.instr ? 4:0) |
              (dut.error ? 8:0) |
              ((dut.write_request && !dut.outside_ram) ? 16:0);
        $fwrite(fd,"%0d %h %h %h %h %h %h %h %h %h %h %h %h ",
            cycles,dut.cpu.state,dut.cpu.pc,dut.cpu.insn,dut.cpu.a,dut.cpu.b,
            dut.cpu.result,dut.cpu.effective_addr,flags,dut.addr,dut.wdata,dut.rdata,dut.wstrb);
        // All architectural effects below are sampled after the same edge.
        #1;
        $fdisplay(fd,"%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h",
            dut.cpu.state,dut.cpu.pc,retired,dut.cpu.retire_pc,dut.cpu.retire_insn,
            dut.cpu.retire_rd,dut.cpu.retire_data,dut.cpu.retire_next_pc,
            trapped,cause,tval,
            dut.cpu.retire2_valid,dut.cpu.retire2_pc,dut.cpu.retire2_insn,
            dut.cpu.retire2_rd,dut.cpu.retire2_data,dut.cpu.retire2_next_pc,
            dut.cpu.retire3_valid,dut.cpu.retire3_pc,dut.cpu.retire3_insn,
            dut.cpu.retire3_rd,dut.cpu.retire3_data,dut.cpu.retire3_next_pc);
        if (retired) retirements=retirements+1;
        if (dut.cpu.retire2_valid) retirements=retirements+1; // second slot (0.5.0)
        if (dut.cpu.retire3_valid) retirements=retirements+1; // third slot (0.7.0)
        if (trapped) begin
            if (cause!==3 || tval!==0 || dut.cpu.regs[10]!==0)
                $fatal(1,"unexpected terminal condition");
            $fclose(fd);
            $display("PASS captured cycles=%0d retirements=%0d",cycles,retirements);
            $finish;
        end
    end
endmodule
