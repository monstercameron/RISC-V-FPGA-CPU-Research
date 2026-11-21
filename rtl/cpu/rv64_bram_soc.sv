// SPDX-License-Identifier: MIT
// Board-independent single-clock prototype. Add exact board pins/clock/reset
// constraints only after choosing a board. RAM has no synchronous bulk reset.
module rv64_bram_soc #(
    parameter integer RAM_WORDS = 2048, // 16 KiB at 64 bits/word; power of two
    parameter INIT_HEX = "",
    parameter [63:0] RESET_PC = 0,
    parameter integer ICACHE_BEATS = 512, // core instruction cache, 8-byte beats
    parameter integer DCACHE_BEATS = 512  // core data cache, 8-byte beats
) (
    input wire clk,
    input wire reset, // already synchronized to clk; resets core AND adapter
    output wire trapped,
    output wire [63:0] trap_pc,
    output wire [63:0] trap_cause,
    output wire [63:0] trap_tval,
    output wire retire_valid,
    output wire [63:0] retire_pc,
    output wire retire2_valid, // second retirement slot, same clock (0.5.0)
    output wire retire3_valid  // third retirement slot, same clock (0.7.0)
);
    localparam integer INDEX_BITS = $clog2(RAM_WORDS);
    reg [63:0] ram [0:RAM_WORDS-1];
    initial begin
        if (INIT_HEX != "") $readmemh(INIT_HEX,ram);
    end
    wire valid, instr;
    wire [63:0] addr,wdata;
    wire [7:0] wstrb;
    reg read_ready,read_error;
    reg [63:0] rdata;
    wire [INDEX_BITS-1:0] index=addr[INDEX_BITS+2:3];
    wire outside_ram=addr>=RAM_WORDS*64'd8;
    // Writes (0.2.2) complete in the clock they are presented: the RAM writes on
    // that clock's edge, and the range check that decides the error is
    // combinational. Reads answer one clock later from the synchronous RAM.
    wire write_request=valid && wstrb!=0;
    wire ready=write_request || read_ready;
    wire error=write_request ? outside_ram : read_error;
`ifdef WIDE_TRACE
    // Paired store write (out-of-order core, 0.11.0): the second write applies only
    // when the first succeeds; its error is its own range check.
    wire [63:0] addr2,wdata2;
    wire [7:0] wstrb2;
    wire [INDEX_BITS-1:0] index2=addr2[INDEX_BITS+2:3];
    wire outside2=addr2>=RAM_WORDS*64'd8;
    wire error2=wstrb2!=0 && outside2;
    // Stores three and four of a write (memory 4): each applies only if every earlier one did.
    wire [127:0] xaddr,xwdata;
    wire [15:0] xwstrb;
    wire [INDEX_BITS-1:0] xindex0=xaddr[INDEX_BITS+2:3], xindex1=xaddr[64+INDEX_BITS+2:67];
    wire xout0=xaddr[63:0]>=RAM_WORDS*64'd8, xout1=xaddr[127:64]>=RAM_WORDS*64'd8;
    wire [1:0] xerror={xwstrb[15:8]!=0 && xout1, xwstrb[7:0]!=0 && xout0};
    wire xok0=write_request && !outside_ram && wstrb2!=0 && !outside2 && xwstrb[7:0]!=0 && !xout0;
    wire xok1=xok0 && xwstrb[15:8]!=0 && !xout1;
`endif
    integer lane;
    always @(posedge clk) begin
        if (reset) begin read_ready<=0; read_error<=0; rdata<=0; end
        else begin
            read_ready<=0;
            if (valid && !write_request && !read_ready) begin
                read_ready<=1;
                read_error<=outside_ram;
                rdata<=outside_ram ? 64'b0 : ram[index];
            end
            if (write_request && !outside_ram)
                for (lane=0;lane<8;lane=lane+1)
                    if (wstrb[lane]) ram[index][8*lane+:8]<=wdata[8*lane+:8];
`ifdef WIDE_TRACE
            if (write_request && !outside_ram && wstrb2!=0 && !outside2)
                for (lane=0;lane<8;lane=lane+1)
                    if (wstrb2[lane]) ram[index2][8*lane+:8]<=wdata2[8*lane+:8];
            if (xok0) for (lane=0;lane<8;lane=lane+1) if (xwstrb[lane]) ram[xindex0][8*lane+:8]<=xwdata[8*lane+:8];
            if (xok1) for (lane=0;lane<8;lane=lane+1) if (xwstrb[8+lane]) ram[xindex1][8*lane+:8]<=xwdata[64+8*lane+:8];
`endif
        end
    end
    rv64_core #(.RESET_PC(RESET_PC),.ICACHE_BEATS(ICACHE_BEATS),.DCACHE_BEATS(DCACHE_BEATS)
`ifdef WIDE_TRACE
        ,.PAIR_WRITES(1),.EXTRA_WRITES(2)
`endif
        ) cpu (
        .clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),
        .mem_ready(ready),.mem_rdata(rdata),.mem_error(error),
        .trap_valid(trapped),.trap_pc(trap_pc),.trap_cause(trap_cause),.trap_tval(trap_tval),
        .retire_valid(retire_valid),.retire_pc(retire_pc),.retire_insn(),
        .retire_rd(),.retire_data(),.retire_next_pc(),
        .retire2_valid(retire2_valid),.retire2_pc(),.retire2_insn(),.retire2_rd(),
        .retire2_data(),.retire2_next_pc(),
        .retire3_valid(retire3_valid),.retire3_pc(),.retire3_insn(),.retire3_rd(),
        .retire3_data(),.retire3_next_pc()
`ifdef WIDE_TRACE
        ,.rt_valid(),.rt_pc(),.rt_insn(),.rt_rd(),.rt_data(),.rt_next(),
        .mem_addr2(addr2),.mem_wdata2(wdata2),.mem_wstrb2(wstrb2),.mem_error2(error2),
        .mem_xaddr(xaddr),.mem_xwdata(xwdata),.mem_xwstrb(xwstrb),.mem_xerror(xerror)
`endif
    );
endmodule
