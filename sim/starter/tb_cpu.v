`timescale 1ns/1ps
module tb_cpu;
  reg clk = 0;
  always #5 clk = ~clk;
  reg resetn = 0;
  wire trap, mem_valid, mem_instr;
  reg mem_ready = 0;
  wire [31:0] mem_addr, mem_wdata;
  wire [3:0] mem_wstrb;
  reg [31:0] mem_rdata = 0;
  reg [31:0] memory [0:255];
  integer i, lane, cycles = 0;

  picorv32 #(.PROGADDR_RESET(0), .STACKADDR(1024)) cpu (
    .clk(clk), .resetn(resetn), .trap(trap),
    .mem_valid(mem_valid), .mem_instr(mem_instr),
    .mem_ready(mem_ready), .mem_addr(mem_addr),
    .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb),
    .mem_rdata(mem_rdata), .irq(32'b0),
    .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0)
  );

  initial begin
    $dumpfile("cpu.vcd");
    $dumpvars(0, tb_cpu);
    for (i=0; i<256; i=i+1) memory[i] = 0;
    memory[0] = 32'h00500093; // addi x1,x0,5
    memory[1] = 32'h00700113; // addi x2,x0,7
    memory[2] = 32'h002081b3; // add x3,x1,x2
    memory[3] = 32'h10302023; // sw x3,256(x0)
    memory[4] = 32'h00100073; // ebreak: reference core asserts trap
    repeat (8) @(negedge clk);
    resetn = 1;
  end

  always @(posedge clk) begin
    mem_ready <= 0;
    if (resetn && mem_valid && !mem_ready) begin
      if (mem_addr[31:10] != 0 || mem_addr[1:0] != 0)
        $fatal(1, "Unexpected memory access: %h", mem_addr);
      mem_ready <= 1;
      mem_rdata <= memory[mem_addr >> 2];
      for (lane=0; lane<4; lane=lane+1)
        if (mem_wstrb[lane])
          memory[mem_addr >> 2][8*lane +: 8] <= mem_wdata[8*lane +: 8];
      if (|mem_wstrb)
        $display("STORE address=0x%08h data=%0d", mem_addr, mem_wdata);
    end
    if (resetn) begin
      cycles <= cycles + 1;
      if (trap) begin
        if (memory[64] !== 32'd12) $fatal(1, "Expected 12, got %h", memory[64]);
        $display("PASS: simulated RISC-V CPU computed 5 + 7 = 12 (%0d cycles)", cycles);
        $finish;
      end
      if (cycles > 1000) $fatal(1, "CPU timed out");
    end
  end
endmodule

