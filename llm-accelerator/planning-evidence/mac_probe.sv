`timescale 1ns/1ps
module mac_probe;
  parameter W=4;
  localparam signed [W-1:0] MINW = -(1 << (W-1));
  localparam signed [W-1:0] MAXW = (1 << (W-1))-1;
  reg clk=0;
  always #5 clk=~clk;
  reg reset=1, valid=0;
  reg signed [7:0] a=0;
  reg signed [W-1:0] w=0;
  wire signed [8+W-1:0] product = a*w;
  reg signed [31:0] acc=0;
  integer accepted=0;
  always @(posedge clk) begin
    if(reset) begin acc<=0; accepted<=0; end
    else if(valid) begin acc<=acc+{{(32-8-W){product[8+W-1]}},product}; accepted<=accepted+1; end
  end
  task send(input signed [7:0] x,input signed [W-1:0] y,input bit v);
    @(negedge clk); a=x;w=y;valid=v;
  endtask
  initial begin
    repeat(2) @(negedge clk); reset=0;
    send(-128,MINW,1);
    send(127,MINW,1);
    send(-128,MAXW,1);
    send(127,MAXW,0); // stall: must not accumulate
    send(127,MAXW,1); // total = 1 for either supported weight width
    send(0,0,0);
    @(negedge clk);
    if(acc!==32'sd1 || accepted!=4) $fatal(1,"Signed/stall probe failed: %d / %d",acc,accepted);
    reset=1; @(negedge clk); reset=0;
    if(acc!==0 || accepted!=0) $fatal(1,"Reset probe failed");
    $display("PASS: W%0dA8 signed extrema, valid stalls, and reset",W);
    $finish;
  end
  initial begin #1000; $fatal(1,"Timeout");end
endmodule
