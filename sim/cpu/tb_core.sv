// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_core #(parameter integer MEM_BYTES=16384, parameter integer ICACHE_BEATS=512,
                 parameter integer DCACHE_BEATS=512, parameter integer N_MISS=1);
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
    // Wide retirement trace (out-of-order core, 0.10.0): up to RWT per clock (16 since
    // 0.12.0), slot 0 oldest.
    localparam integer RWT = 32;
    wire [RWT-1:0] rtv;
    wire [RWT*64-1:0] rtpc,rtdata,rtnext;
    wire [RWT*32-1:0] rtinsn;
    wire [RWT*5-1:0] rtrd;
    integer q;
    // Paired store write (0.11.0).
    wire [63:0] addr2,wdata2;
    wire [7:0] wstrb2;
    reg error2=0;
    wire [127:0] xaddr,xwdata;
    wire [15:0] xwstrb;
    reg [1:0] xerror=0;
    // Split data reads (memory hand-off 2, N_MISS > 1).
    wire [3:0] mtag;
    reg rsp_valid=0, rsp_error=0;
    reg [3:0] rsp_tag=0;
    reg [63:0] rsp_data=0;
    // One queued answer per beat (a line read, mem_len > 0, queues its beats in answer order sp_ord).
    reg [63:0] sp_v=0;
    reg [3:0] sp_tag [0:63];
    reg [63:0] sp_data [0:63];
    reg sp_err [0:63];
    integer sp_due [0:63];
    integer sp_seq [0:63];
    integer sp_ord [0:63];
    wire [2:0] mlen;
`ifndef RV64_OOO_DLINE
    assign mlen = 3'd0;
`endif
    integer sp_b, line_overlaps=0, line_errors=0, sp_ov;
    integer fault5_fired=0, fault5_slot=-1, fault5_answered=0, fault5_reads=0;
    reg [2:0] sp_lmk [0:63];
    reg [63:0] sp_ba;
    function sp_first(input integer q);   // no earlier beat of q's tag is still queued
        integer r;
        begin
            sp_first = 1;
            for (r = 0; r < 64; r = r + 1) if (sp_v[r] && sp_tag[r] == sp_tag[q] && sp_ord[r] < sp_ord[q]) sp_first = 0;
        end
    endfunction
    integer split_lat=0;   // +split_lat=N: fixed timing; the answer is valid in the clock that starts N+1 edges after the accepting edge
    reg [60:0] sp_beat [0:63];
    // Covers: split reads, answers given before an older outstanding one, and reads whose beat a
    // store wrote between acceptance and answer (the core must drop those answers).
    integer sp_k, sp_n, sp_pick, sp_min, sp_j, split_reads=0, split_ireads=0, split_reorders=0, split_stale=0, sp_next=0;
    // Split: a data read, or an instruction read with mem_tag 8-15 (the instruction side's tags).
    wire split_read = N_MISS > 1 && valid && wstrb == 0 && (!instr || mtag[3]);
`endif
    rv64_core #(.ICACHE_BEATS(ICACHE_BEATS),.DCACHE_BEATS(DCACHE_BEATS)
`ifdef WIDE_TRACE
        ,.PAIR_WRITES(1),.EXTRA_WRITES(2),.RW(RWT),.N_MISS(N_MISS)
`endif
        ) dut(.clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),.mem_ready(ready),
        .mem_rdata(rdata),.mem_error(error),.trap_valid(trapped),.trap_pc(tpc),
        .trap_cause(cause),.trap_tval(tval),.retire_valid(retired),.retire_pc(rpc),
        .retire_insn(rinsn),.retire_rd(rd),.retire_data(rval),.retire_next_pc(npc),
        .retire2_valid(retired2),.retire2_pc(rpc2),.retire2_insn(rinsn2),.retire2_rd(rd2),
        .retire2_data(rval2),.retire2_next_pc(npc2),
        .retire3_valid(retired3),.retire3_pc(rpc3),.retire3_insn(rinsn3),.retire3_rd(rd3),
        .retire3_data(rval3),.retire3_next_pc(npc3)
`ifdef WIDE_TRACE
        ,.rt_valid(rtv),.rt_pc(rtpc),.rt_insn(rtinsn),.rt_rd(rtrd),.rt_data(rtdata),.rt_next(rtnext),
        .mem_addr2(addr2),.mem_wdata2(wdata2),.mem_wstrb2(wstrb2),.mem_error2(error2),
        .mem_xaddr(xaddr),.mem_xwdata(xwdata),.mem_xwstrb(xwstrb),.mem_xerror(xerror),
        .mem_tag(mtag),
`ifdef RV64_OOO_DLINE
        .mem_len(mlen),
`endif
        .rsp_valid(rsp_valid),.rsp_tag(rsp_tag),.rsp_data(rsp_data),.rsp_error(rsp_error)
`endif
        );

    string image_path,trace_path,pending_write="",pending_write2="",pending_write3="",pending_write4="";
    integer fd,i,lane,cycles=0,retire_count=0,slot2_count=0,slot3_count=0,slot3_branches=0;
    // Multi-store write lanes used, and store faults reported on lanes 2..4 (lane cover).
    integer lane2=0,lane3=0,lane4=0,fault_lane2=0,fault_lane3=0,fault_lane4=0;
    integer max_stall=0,delay_left=0,seed_arg=1,fault_kind=0,max_cycles=200000;
    // +max_retired=N (benchmark checkpoint pieces): stop once N instructions have
    // retired, closing the trace without a trap line. Off by default.
    integer max_retired=0,image_bin=0;
`ifdef RV64_OOO_V
    reg [63:0] vqa [0:4095]; reg [63:0] vqd [0:4095]; reg [7:0] vqs [0:4095];   // W records of the vector store in flight
    integer vqn=0, vk;
    reg [7:0] vrn; reg [11:0] vcn;
    // The write capture runs at posedge, the edge on which the core may clear vx_wv; so it uses the value
    // sampled at the previous negedge (stable there), whatever the order of the posedge processes.
    reg vx_wv_q=0;
    always @(negedge clk) vx_wv_q = dut.vx_wv;
`endif
    reg [31:0] rng;
    reg [63:0] fault_addr=64'hffffffffffffffff;
    reg active=0,held=0;
    reg fault_once=0;      // fault_kind 4: the one write fault has been given
`ifdef WIDE_TRACE
    reg [551:0] held_request;
    // mem_tag and mem_len are part of the request a stall must hold (split reads, line reads).
    wire [551:0] request={mlen,mtag,instr,addr,wdata,wstrb,addr2,wdata2,wstrb2,xaddr,xwdata,xwstrb};
`else
    reg [136:0] held_request;
    wire [136:0] request={instr,addr,wdata,wstrb};
`endif
    initial begin
        // +image_bin=FILE (large benchmark checkpoints): raw little-endian bytes from
        // address 0 instead of a +image hex file, the rest of memory zero. Off by default.
        if ($value$plusargs("image_bin=%s",image_path)) image_bin=1;
        else if (!$value$plusargs("image=%s",image_path)) $fatal(1,"missing image");
        if (!$value$plusargs("trace=%s",trace_path)) $fatal(1,"missing trace");
        if ($value$plusargs("stall=%d",max_stall)) begin end
        if ($value$plusargs("seed=%d",seed_arg)) begin end
`ifdef WIDE_TRACE
        if ($value$plusargs("split_lat=%d",split_lat)) begin end
`endif
        if ($value$plusargs("fault_kind=%d",fault_kind)) begin end
        if ($value$plusargs("fault_addr=%h",fault_addr)) begin end
        if ($value$plusargs("max_cycles=%d",max_cycles)) begin end
        if ($value$plusargs("max_retired=%d",max_retired)) begin end
        rng=seed_arg==0 ? 1 : seed_arg;
        for (i=0;i<MEM_BYTES;i=i+1) memory[i]=0;
        if (image_bin) begin
            fd=$fopen(image_path,"rb");
            if (!fd) $fatal(1,"cannot open +image_bin file");
            if ($fread(memory,fd)<=0) $fatal(1,"empty +image_bin file");
            $fclose(fd);
        end else $readmemh(image_path,memory);
        fd=$fopen(trace_path,"w");
        if (!fd) $fatal(1,"cannot open trace");
        repeat (4) @(negedge clk);
        reset=0;
    end

    // Drive response on falling edges so all inputs are stable at sampling edge.
    always @(negedge clk) begin
        if (reset) begin
            ready=0; active=0;
`ifdef WIDE_TRACE
            rsp_valid=0;           // no answer is driven during reset (the queue clears at the edge)
`endif
        end
        else begin
`ifdef WIDE_TRACE
            // Writes completed at the last edge belong to the store retiring now: its
            // write is logged just before its own retirement, whatever its slot.
            for (q=0;q<RWT;q=q+1) if (rtv[q]) begin
                if (q>0 && !rtv[q-1]) $fatal(1,"retirement slots not contiguous");
`ifdef RV64_OOO_FPU
                if (rtinsn[32*q +: 7]==7'h23 || rtinsn[32*q +: 7]==7'h27) begin
`else
                if (rtinsn[32*q +: 7]==7'h23) begin
`endif
                    // Paired writes (0.11.0) belong to two stores, in program order.
                    if (pending_write!="") begin $fdisplay(fd,"%s",pending_write); pending_write=""; end
                    else if (pending_write2!="") begin $fdisplay(fd,"%s",pending_write2); pending_write2=""; end
                    else if (pending_write3!="") begin $fdisplay(fd,"%s",pending_write3); pending_write3=""; end
                    else if (pending_write4!="") begin $fdisplay(fd,"%s",pending_write4); pending_write4=""; end
                end
`ifdef RV64_OOO_FPU
`ifdef RV64_OOO_V
                if (q==0 && dut.rt_vec) begin for (vk=0;vk<vqn;vk=vk+1) $fdisplay(fd,"W %016h %016h %02h",vqa[vk],vqd[vk],vqs[vk]); vqn=0; end
`endif
                // F/D (FP-CONTRACT.md 7): flags raised, a written fcsr, then R with rd 0x20+n for f registers.
                if (dut.rt_ff[5*q +: 5] != 0) $fdisplay(fd,"F %02h",{3'b0,dut.rt_ff[5*q +: 5]});
                if (dut.rt_csrw[q]) $fdisplay(fd,"C 003 %016h",{56'b0,dut.rt_csrv[8*q +: 8]});
`ifdef RV64_OOO_V
                if (q==0 && dut.rt_vec) begin
                    for (vk=0;vk<dut.rt_cn;vk=vk+1) begin vcn=dut.rt_vcsr[12*vk +: 12]; $fdisplay(fd,"C %03h %016h",vcn,dut.rt_vcval[64*vk +: 64]); end
                    for (vk=0;vk<dut.rt_vn;vk=vk+1) begin vrn=dut.rt_vb+vk; $fdisplay(fd,"V %02h %h",vrn,dut.vreg[vrn]); end
                end
`endif
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rtpc[64*q +: 64],rtinsn[32*q +: 32],
                          {2'b0,dut.rt_rdfp[q],rtrd[5*q +: 5]},rtdata[64*q +: 64],rtnext[64*q +: 64]);
`else
                $fdisplay(fd,"R %016h %08h %02h %016h %016h",rtpc[64*q +: 64],rtinsn[32*q +: 32],
                          rtrd[5*q +: 5],rtdata[64*q +: 64],rtnext[64*q +: 64]);
`endif
                retire_count=retire_count+1;
                if (q==1) slot2_count=slot2_count+1;
                if (q==2) slot3_count=slot3_count+1;
            end
            // A successful write belongs to a store retiring on the same edge (0.10.2):
            // a write left over here was not followed by its store's retirement.
            if (pending_write!="" || pending_write2!="" || pending_write3!="" || pending_write4!="")
                $fatal(1,"store write without its store retiring on the same clock");
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
            if (max_retired>0 && retire_count>=max_retired && !trapped) begin
                // A write still pending belongs to a store beyond the limit; it is not logged.
                $fclose(fd);
                $display("LIMIT retirements=%0d cycles=%0d",retire_count,cycles);
                $finish;
            end
            if (trapped) begin
                if (valid) $fatal(1,"request after terminal trap");
`ifdef WIDE_TRACE
                // Trap drain rule: no split read may still be outstanding when the core halts.
                if (sp_v != 0) $fatal(1,"terminal trap with split reads outstanding");
`endif
                if (pending_write!="") $fdisplay(fd,"%s",pending_write);
                if (pending_write2!="") $fdisplay(fd,"%s",pending_write2);
                if (pending_write3!="") $fdisplay(fd,"%s",pending_write3);
                if (pending_write4!="") $fdisplay(fd,"%s",pending_write4);
`ifdef RV64_OOO_V
                if (dut.rt_vtrap) begin
                    for (vk=0;vk<vqn;vk=vk+1) $fdisplay(fd,"W %016h %016h %02h",vqa[vk],vqd[vk],vqs[vk]); vqn=0;
                    for (vk=0;vk<dut.rt_vn;vk=vk+1) begin vrn=dut.rt_vb+vk; $fdisplay(fd,"V %02h %h",vrn,dut.vreg[vrn]); end
                    for (vk=0;vk<dut.rt_cn;vk=vk+1) begin vcn=dut.rt_vcsr[12*vk +: 12]; $fdisplay(fd,"C %03h %016h",vcn,dut.rt_vcval[64*vk +: 64]); end
                end
`endif
                $fdisplay(fd,"T %016h %016h %016h",tpc,cause,tval);
                $fclose(fd);
`ifdef RV64_OOO_FPU
                // The final fcsr (test_cpu --fpu compares it with the golden model's: flags of squashed or
                // post-trap instructions never reach the trace).
                $display("DONE retirements=%0d cycles=%0d slot2=%0d slot3=%0d slot3_branches=%0d lane2=%0d lane3=%0d lane4=%0d fault_lane2=%0d fault_lane3=%0d fault_lane4=%0d fcsr=%02h",
                         retire_count,cycles,slot2_count,slot3_count,slot3_branches,lane2,lane3,lane4,fault_lane2,fault_lane3,fault_lane4,dut.fcsr);
`else
                $display("DONE retirements=%0d cycles=%0d slot2=%0d slot3=%0d slot3_branches=%0d lane2=%0d lane3=%0d lane4=%0d fault_lane2=%0d fault_lane3=%0d fault_lane4=%0d",
                         retire_count,cycles,slot2_count,slot3_count,slot3_branches,lane2,lane3,lane4,fault_lane2,fault_lane3,fault_lane4);
`endif
`ifdef WIDE_TRACE
                if (N_MISS > 1) $display("SPLIT split_reads=%0d split_ireads=%0d split_reorders=%0d split_stale=%0d%s",split_reads,split_ireads,split_reorders,split_stale,
                    line_overlaps+line_errors+fault5_fired != 0 ? $sformatf(" line_store_overlaps=%0d line_error_beats=%0d fault_once_fired=%0d fault_once_answered=%0d fault_once_reads=%0d",line_overlaps,line_errors,fault5_fired,fault5_answered,fault5_reads) : "");
`endif
                $finish;
            end
`ifdef WIDE_TRACE
            rsp_valid=0;
            if (N_MISS > 1) begin
                sp_n=0;
                for (sp_k=0;sp_k<64;sp_k=sp_k+1) if (sp_v[sp_k] && sp_due[sp_k]<=cycles && sp_first(sp_k)) sp_n=sp_n+1;
                if (sp_n>0) begin
                    rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5);
                    sp_pick=rng % sp_n; sp_n=0;
                    for (sp_k=0;sp_k<64;sp_k=sp_k+1) if (sp_v[sp_k] && sp_due[sp_k]<=cycles && sp_first(sp_k)) begin
                        if (sp_n==sp_pick) begin
                            sp_min=sp_seq[sp_k];
                            for (sp_j=0;sp_j<64;sp_j=sp_j+1) if (sp_v[sp_j] && sp_seq[sp_j]<sp_min) sp_min=sp_seq[sp_j];
                            if (sp_min!=sp_seq[sp_k]) split_reorders=split_reorders+1;
                            rsp_valid=1; rsp_tag=sp_tag[sp_k]; rsp_data=sp_data[sp_k]; rsp_error=sp_err[sp_k]; sp_v[sp_k]=0; if (sp_k==fault5_slot) begin fault5_answered=1; fault5_slot=-1; end
                        end
                        sp_n=sp_n+1;
                    end
                end
            end
`endif
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
                     (fault_kind==3 && !instr && wstrb!=0) || (fault_kind==4 && !fault_once && !instr && wstrb!=0)));
`ifdef WIDE_TRACE
                error2=wstrb2!=0 && (addr2>=MEM_BYTES || (addr2==fault_addr && (fault_kind==3 || (fault_kind==4 && !fault_once))));
                xerror[0]=xwstrb[7:0]!=0 && (xaddr[63:0]>=MEM_BYTES || (xaddr[63:0]==fault_addr && (fault_kind==3 || (fault_kind==4 && !fault_once))));
                xerror[1]=xwstrb[15:8]!=0 && (xaddr[127:64]>=MEM_BYTES || (xaddr[127:64]==fault_addr && (fault_kind==3 || (fault_kind==4 && !fault_once))));
`endif
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
`ifdef WIDE_TRACE
            if (valid && mlen!=0 && !split_read) $fatal(1,"mem_len %0d on a request that is not a split read",mlen);
`endif
            held=valid && !ready;
            held_request=request;
`ifdef WIDE_TRACE
            for (sp_k=0;sp_k<64;sp_k=sp_k+1) if (sp_v[sp_k] && !sp_err[sp_k])
                for (lane=0;lane<8;lane=lane+1) sp_data[sp_k][8*lane+:8]=memory[{sp_beat[sp_k],3'b000}+lane];
            if (valid && ready && split_read) begin
                sp_pick=-1;
                for (sp_k=63;sp_k>=0;sp_k=sp_k-1) if (!sp_v[sp_k]) sp_pick=sp_k;
                if (sp_pick<0) $fatal(1,"more than 64 split beats outstanding");
                if (instr && mlen!=0) $fatal(1,"line read on the instruction side");
                if (mlen!=0 && mlen!=1 && mlen!=3 && mlen!=7) $fatal(1,"mem_len %0d is not 2^n - 1",mlen);
                for (sp_k=0;sp_k<64;sp_k=sp_k+1) if (sp_v[sp_k] && sp_tag[sp_k]==mtag) $fatal(1,"split read tag %0d reused while outstanding",mtag);
                if (mtag>=N_MISS && !mtag[3]) $fatal(1,"split read tag %0d >= N_MISS",mtag);
                if (instr != mtag[3]) $fatal(1,"split read tag %0d on the wrong side",mtag);
                if (instr) split_ireads=split_ireads+1;
                rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5);
                sp_v[sp_pick]=1; sp_tag[sp_pick]=mtag; sp_err[sp_pick]=error; sp_seq[sp_pick]=sp_next; sp_next=sp_next+1;
                sp_due[sp_pick]=split_lat>0 ? cycles+split_lat : cycles+1+(rng % (3*max_stall+3));
                sp_data[sp_pick]=0; sp_beat[sp_pick]=addr[63:3]; sp_ord[sp_pick]=0; sp_lmk[sp_pick]=mlen;
`ifdef RV64_OOO_DLINE
                if (fault_kind==5 && fault5_fired==0 && !instr && addr==fault_addr) begin sp_err[sp_pick]=1; fault5_fired=1; fault5_slot=sp_pick; end
                if (fault_kind==5 && !instr && addr[63:3]==fault_addr[63:3]) fault5_reads=fault5_reads+1;
`endif
                if (!error) for (lane=0;lane<8;lane=lane+1) sp_data[sp_pick][8*lane+:8]=memory[addr+lane];
                // A line read (mem_len > 0): the following beats of the line, wrapping, each queued with its
                // own delay, answered after the beats before it (sp_first), with its own error.
                for (sp_b=1;sp_b<=mlen;sp_b=sp_b+1) begin
                    sp_pick=-1;
                    for (sp_k=63;sp_k>=0;sp_k=sp_k-1) if (!sp_v[sp_k]) sp_pick=sp_k;
                    if (sp_pick<0) $fatal(1,"more than 64 split beats outstanding");
                    sp_ba={addr[63:3] & ~{58'b0,mlen},3'b000} | {58'b0,(addr[5:3]+sp_b[2:0]) & mlen,3'b000};
                    rng=rng^(rng<<13); rng=rng^(rng>>17); rng=rng^(rng<<5);
                    sp_v[sp_pick]=1; sp_tag[sp_pick]=mtag; sp_seq[sp_pick]=sp_next; sp_next=sp_next+1; sp_ord[sp_pick]=sp_b;
                    sp_err[sp_pick]=sp_ba>=MEM_BYTES || (sp_ba==fault_addr && fault_kind==2);
                    sp_due[sp_pick]=split_lat>0 ? cycles+split_lat+sp_b : cycles+1+(rng % (3*max_stall+3));
                    sp_data[sp_pick]=0; sp_beat[sp_pick]=sp_ba[63:3]; sp_lmk[sp_pick]=mlen; if (sp_err[sp_pick]) line_errors=line_errors+1;
`ifdef RV64_OOO_DLINE
                    if (fault_kind==5 && fault5_fired==0 && sp_ba==fault_addr) begin sp_err[sp_pick]=1; fault5_fired=1; fault5_slot=sp_pick; end
`endif
                    if (!sp_err[sp_pick]) for (lane=0;lane<8;lane=lane+1) sp_data[sp_pick][8*lane+:8]=memory[sp_ba+lane];
                end
                split_reads=split_reads+1;
            end
`endif
            if (valid && ready && wstrb!=0 && fault_kind==4 && (error
`ifdef WIDE_TRACE
                || error2 || xerror!=0
`endif
                )) fault_once=1;
            if (valid && ready) begin
                active=0;
                if (!error && wstrb!=0) begin
`ifdef WIDE_TRACE
                    sp_ov=0;
                    for (sp_k=0;sp_k<64;sp_k=sp_k+1)
                        if (sp_v[sp_k] && sp_lmk[sp_k]!=0 && (addr[63:3] & ~{58'b0,sp_lmk[sp_k]})==(sp_beat[sp_k] & ~{58'b0,sp_lmk[sp_k]})) sp_ov=1;
                    if (sp_ov) line_overlaps=line_overlaps+1;
                    for (sp_k=0;sp_k<64;sp_k=sp_k+1)
                        if (sp_v[sp_k] && (sp_beat[sp_k]==addr[63:3] || (wstrb2!=0 && sp_beat[sp_k]==addr2[63:3]) ||
                            (xwstrb[7:0]!=0 && sp_beat[sp_k]==xaddr[63:3]) || (xwstrb[15:8]!=0 && sp_beat[sp_k]==xaddr[127:67])))
                            split_stale=split_stale+1;
`endif
`ifdef RV64_OOO_V
                    if (vx_wv_q) begin vqa[vqn]=addr; vqd[vqn]=wdata; vqs[vqn]=wstrb; vqn=vqn+1; end
                    else
`endif
                    $sformat(pending_write,"W %016h %016h %02h",addr,wdata,wstrb);
                    for (lane=0;lane<8;lane=lane+1)
                        if (wstrb[lane]) memory[addr+lane]=wdata[8*lane+:8];
`ifdef WIDE_TRACE
                    if (wstrb2!=0) lane2=lane2+1;
                    if (xwstrb[7:0]!=0) lane3=lane3+1;
                    if (xwstrb[15:8]!=0) lane4=lane4+1;
                    if (wstrb2!=0 && error2) fault_lane2=fault_lane2+1;
                    if (wstrb2!=0 && !error2 && xwstrb[7:0]!=0 && xerror[0]) fault_lane3=fault_lane3+1;
                    if (wstrb2!=0 && !error2 && xwstrb[7:0]!=0 && !xerror[0] && xwstrb[15:8]!=0 && xerror[1]) fault_lane4=fault_lane4+1;
                    if (wstrb2!=0 && !error2) begin
                        $sformat(pending_write2,"W %016h %016h %02h",addr2,wdata2,wstrb2);
                        for (lane=0;lane<8;lane=lane+1)
                            if (wstrb2[lane]) memory[addr2+lane]=wdata2[8*lane+:8];
                        if (xwstrb[7:0]!=0 && !xerror[0]) begin
                            $sformat(pending_write3,"W %016h %016h %02h",xaddr[63:0],xwdata[63:0],xwstrb[7:0]);
                            for (lane=0;lane<8;lane=lane+1)
                                if (xwstrb[lane]) memory[xaddr[63:0]+lane]=xwdata[8*lane+:8];
                            if (xwstrb[15:8]!=0 && !xerror[1]) begin
                                $sformat(pending_write4,"W %016h %016h %02h",xaddr[127:64],xwdata[127:64],xwstrb[15:8]);
                                for (lane=0;lane<8;lane=lane+1)
                                    if (xwstrb[8+lane]) memory[xaddr[127:64]+lane]=xwdata[64+8*lane+:8];
                            end
                        end
                    end
`endif
                end
            end
        end else begin
            held=0;
`ifdef WIDE_TRACE
            sp_v=0;                // reset cancels queued split answers, at the synchronous reset edge
`endif
        end
    end
endmodule
