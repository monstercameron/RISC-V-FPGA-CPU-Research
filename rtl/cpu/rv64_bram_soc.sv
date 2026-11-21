// SPDX-License-Identifier: MIT
// Board-independent single-clock prototype. Add exact board pins/clock/reset
// constraints only after choosing a board. RAM has no synchronous bulk reset.
module rv64_bram_soc #(
    parameter integer RAM_WORDS = 2048, // 16 KiB at 64 bits/word; power of two
    parameter INIT_HEX = "",
    parameter [63:0] RESET_PC = 0,
    parameter integer ICACHE_BEATS = 512 // core instruction cache, 8-byte beats
) (
    input wire clk,
    input wire reset, // already synchronized to clk; resets core AND adapter
    output wire trapped,
    output wire [63:0] trap_pc,
    output wire [63:0] trap_cause,
    output wire [63:0] trap_tval,
    output wire retire_valid,
    output wire [63:0] retire_pc
);
    localparam integer INDEX_BITS = $clog2(RAM_WORDS);
    reg [63:0] ram [0:RAM_WORDS-1];
    initial begin
        if (INIT_HEX != "") $readmemh(INIT_HEX,ram);
    end
    wire valid, instr;
    wire [63:0] addr,wdata;
    wire [7:0] wstrb;
    reg ready,error;
    reg [63:0] rdata;
    wire [INDEX_BITS-1:0] index=addr[INDEX_BITS+2:3];
    wire outside_ram=addr>=RAM_WORDS*64'd8;
    integer lane;
    always @(posedge clk) begin
        if (reset) begin ready<=0; error<=0; rdata<=0; end
        else begin
            ready<=0;
            if (valid && !ready) begin
                ready<=1;
                error<=outside_ram;
                if (outside_ram) rdata<=0;
                else begin
                    rdata<=ram[index];
                    for (lane=0;lane<8;lane=lane+1)
                        if (wstrb[lane]) ram[index][8*lane+:8]<=wdata[8*lane+:8];
                end
            end
        end
    end
    rv64_core #(.RESET_PC(RESET_PC),.ICACHE_BEATS(ICACHE_BEATS)) cpu (
        .clk(clk),.reset(reset),.mem_valid(valid),.mem_instr(instr),
        .mem_addr(addr),.mem_wdata(wdata),.mem_wstrb(wstrb),
        .mem_ready(ready),.mem_rdata(rdata),.mem_error(error),
        .trap_valid(trapped),.trap_pc(trap_pc),.trap_cause(trap_cause),.trap_tval(trap_tval),
        .retire_valid(retire_valid),.retire_pc(retire_pc),.retire_insn(),
        .retire_rd(),.retire_data(),.retire_next_pc()
    );
endmodule
