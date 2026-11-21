// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_core #(parameter integer MEM_BYTES=16384);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    reg [7:0] memory [0:MEM_BYTES-1];
    wire valid,instr;
    wire [63:0] addr,wdata;
    wire [7:0] wstrb;
    reg ready=0,error=0;
    reg [63:0] rdata=0;
    wire trapped,retired;
    wire [63:0] tpc,cause,tval,rpc,rval,npc;
    wire [31:0] rinsn;
    wire [4:0] rd;
    rv64_core dut(.clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),.mem_ready(ready),
        .mem_rdata(rdata),.mem_error(error),.trap_valid(trapped),.trap_pc(tpc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),
        .retire_insn(rinsn),.retire_rd(rd),.retire_data(rval),.retire_next_pc(npc));

    string image_path,trace_path;
    integer fd,i,lane,cycles=0,retire_count=0;
    integer max_stall=0,delay_left=0,seed_arg=1,fault_kind=0,max_cycles=200000;
    reg [31:0] rng;
    reg [63:0] fault_addr=64'hffffffffffffffff;
    reg active=0,held=0;
    reg [136:0] held_request;
    wire [136:0] request={instr,addr,wdata,wstrb};
    initial begin
        if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing image");
        if (!$value$plusargs("trace=%s",trace_path)) $fatal(1,"missing trace");
        if ($value$plusargs("stall=%d",max_stall)) begin end
        if ($value$plusargs("seed=%d",seed_arg)) begin end
        if ($value$plusargs("fault_kind=%d",fault_kind)) begin end
        if ($value$plusargs("fault_addr=%h",fault_addr)) begin end
        if ($value$plusargs("max_cycles=%d",max_cycles)) begin end
        rng=seed_arg==0 ? 1 : seed_arg;
        for (i=0;i<MEM_BYTES;i=i+1) memory[i]=0;
        $readmemh(image_path,memory);
        fd=$fopen(trace_path,"w");
        if (!fd) $fatal(1,"cannot open trace");
        repeat (4) @(negedge clk);
        reset=0;
    end

    // Drive response on falling edges so all inputs are stable at sampling edge.
    always @(negedge clk) begin
        if (reset) begin ready=0; active=0; end
        else begin
            if (retired) begin
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rpc,rinsn,rd,rval,npc);
                retire_count=retire_count+1;
            end
            if (trapped) begin
                if (valid) $fatal(1,"request after terminal trap");
                $fdisplay(fd,"T %016h %016h %016h",tpc,cause,tval);
                $fclose(fd);
                $display("DONE retirements=%0d cycles=%0d",retire_count,cycles);
                $finish;
            end
            if (!valid) begin ready=0; active=0; end
            else begin
                if (!active) begin
                    rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5);
                    delay_left=rng % (max_stall+1);
                    active=1;
                end
                ready=delay_left==0;
                if (delay_left>0) delay_left=delay_left-1;
                error=addr>=MEM_BYTES || (addr==fault_addr &&
                    ((fault_kind==1 && instr) || (fault_kind==2 && !instr && wstrb==0) ||
                     (fault_kind==3 && !instr && wstrb!=0)));
                rdata=0;
                if (!error)
                    for (lane=0;lane<8;lane=lane+1) rdata[8*lane+:8]=memory[addr+lane];
            end
        end
    end

    always @(posedge clk) begin
        if (!reset) begin
            cycles=cycles+1;
            if (cycles>max_cycles) $fatal(1,"timeout");
            if (held && (!valid || request!==held_request)) $fatal(1,"unstable stalled request");
            held=valid && !ready;
            held_request=request;
            if (valid && ready) begin
                active=0;
                if (!error && wstrb!=0) begin
                    $fdisplay(fd,"W %016h %016h %02h",addr,wdata,wstrb);
                    for (lane=0;lane<8;lane=lane+1)
                        if (wstrb[lane]) memory[addr+lane]=wdata[8*lane+:8];
                end
            end
        end else held=0;
    end
endmodule
