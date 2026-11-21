// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_core #(parameter integer MEM_BYTES=16384, parameter integer ICACHE_BEATS=512,
                 parameter integer DCACHE_BEATS=512);
    reg clk=0,reset=1;
    always #5 clk=~clk;
    reg [7:0] memory [0:MEM_BYTES-1];
    wire valid,instr;
    wire [63:0] addr,wdata;
    wire [7:0] wstrb;
    reg ready=0,error=0;
    reg [63:0] rdata=0;
    wire trapped,retired,retired2,retired3;
    wire [63:0] tpc,cause,tval,rpc,rval,npc,rpc2,rval2,npc2,rpc3,rval3,npc3;
    wire [31:0] rinsn,rinsn2,rinsn3;
    wire [4:0] rd,rd2,rd3;
`ifdef WIDE_TRACE
    // Wide retirement trace (out-of-order core, 0.10.0): up to 8 per clock, slot 0 oldest.
    wire [7:0] rtv;
    wire [511:0] rtpc,rtdata,rtnext;
    wire [255:0] rtinsn;
    wire [39:0] rtrd;
    integer q;
`endif
    rv64_core #(.ICACHE_BEATS(ICACHE_BEATS),.DCACHE_BEATS(DCACHE_BEATS)) dut(.clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),.mem_ready(ready),
        .mem_rdata(rdata),.mem_error(error),.trap_valid(trapped),.trap_pc(tpc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),
        .retire_insn(rinsn),.retire_rd(rd),.retire_data(rval),.retire_next_pc(npc),
        .retire2_valid(retired2),.retire2_pc(rpc2),.retire2_insn(rinsn2),.retire2_rd(rd2),
        .retire2_data(rval2),.retire2_next_pc(npc2),
        .retire3_valid(retired3),.retire3_pc(rpc3),.retire3_insn(rinsn3),.retire3_rd(rd3),
        .retire3_data(rval3),.retire3_next_pc(npc3)
`ifdef WIDE_TRACE
        ,.rt_valid(rtv),.rt_pc(rtpc),.rt_insn(rtinsn),.rt_rd(rtrd),.rt_data(rtdata),.rt_next(rtnext)
`endif
        );

    string image_path,trace_path,pending_write="";
    integer fd,i,lane,cycles=0,retire_count=0,slot2_count=0,slot3_count=0,slot3_branches=0;
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
`ifdef WIDE_TRACE
            // Writes completed at the last edge belong to the store retiring now: its
            // write is logged just before its own retirement, whatever its slot.
            for (q=0;q<8;q=q+1) if (rtv[q]) begin
                if (q>0 && !rtv[q-1]) $fatal(1,"retirement slots not contiguous");
                if (pending_write!="" && rtinsn[32*q +: 7]==7'h23) begin
                    $fdisplay(fd,"%s",pending_write); pending_write="";
                end
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rtpc[64*q +: 64],rtinsn[32*q +: 32],
                          rtrd[5*q +: 5],rtdata[64*q +: 64],rtnext[64*q +: 64]);
                retire_count=retire_count+1;
                if (q==1) slot2_count=slot2_count+1;
                if (q==2) slot3_count=slot3_count+1;
            end
            if (pending_write!="" && !trapped) begin $fdisplay(fd,"%s",pending_write); pending_write=""; end
`else
            // Writes completed at the last edge belong to a store retiring now. A store
            // on the first slot (or alone) logs its write before its retirement; a
            // second-slot store (0.5.4) logs it after the first slot's retirement.
            if (!(retired2 && rinsn2[6:0]==7'h23) && pending_write!="") begin
                $fdisplay(fd,"%s",pending_write); pending_write="";
            end
            if (retired) begin
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rpc,rinsn,rd,rval,npc);
                retire_count=retire_count+1;
            end
            if (retired2) begin // second slot: after the first, in program order
                if (!retired) $fatal(1,"second retirement slot without the first");
                if (pending_write!="") begin $fdisplay(fd,"%s",pending_write); pending_write=""; end
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rpc2,rinsn2,rd2,rval2,npc2);
                retire_count=retire_count+1; slot2_count=slot2_count+1;
            end
            if (retired3) begin // third slot (0.7.0): after the second, never a store
                if (!retired2) $fatal(1,"third retirement slot without the second");
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rpc3,rinsn3,rd3,rval3,npc3);
                retire_count=retire_count+1; slot3_count=slot3_count+1;
                if (rinsn3[6:0]==7'h63) slot3_branches=slot3_branches+1;
            end
`endif
            if (trapped) begin
                if (valid) $fatal(1,"request after terminal trap");
                if (pending_write!="") $fdisplay(fd,"%s",pending_write);
                $fdisplay(fd,"T %016h %016h %016h",tpc,cause,tval);
                $fclose(fd);
                $display("DONE retirements=%0d cycles=%0d slot2=%0d slot3=%0d slot3_branches=%0d",
                         retire_count,cycles,slot2_count,slot3_count,slot3_branches);
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
                    $sformat(pending_write,"W %016h %016h %02h",addr,wdata,wstrb);
                    for (lane=0;lane<8;lane=lane+1)
                        if (wstrb[lane]) memory[addr+lane]=wdata[8*lane+:8];
                end
            end
        end else held=0;
    end
endmodule
