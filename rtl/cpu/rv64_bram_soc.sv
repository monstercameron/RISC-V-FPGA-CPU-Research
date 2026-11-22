// SPDX-License-Identifier: MIT
// Board-independent single-clock prototype. Add exact board pins/clock/reset
// constraints only after choosing a board. RAM has no synchronous bulk reset.
module rv64_bram_soc #(
    parameter integer RAM_WORDS = 2048, // 16 KiB at 64 bits/word; power of two
    parameter INIT_HEX = "",
    parameter [63:0] RESET_PC = 0,
    parameter integer ICACHE_BEATS = 512, // core instruction cache, 8-byte beats
    parameter integer DCACHE_BEATS = 512, // core data cache, 8-byte beats
    // Memory model (memory hand-off 1). A read completes MEM_LAT clocks after it is first
    // presented (1, the default, is the synchronous RAM: ready the next clock). With
    // L2_KIB != 0 a tags-only shared L2 (instruction and data) sits in front: a read that
    // hits it completes after L2_LAT clocks, one that misses after MEM_LAT and fills the
    // line. Writes still complete in the clock they are presented (posted) and allocate
    // their line with no fill traffic (optimistic). Data always lives in the RAM array, which
    // every write reaches at once. Out-of-range reads fault after the same latency as a read
    // that misses (MEM_LAT). One request at a time, as before: a pending instruction miss
    // delays a data read behind it. Latencies are 1 to 1,048,576 clocks; with an L2, MEM_LAT
    // must exceed L2_LAT.
    parameter integer L2_KIB = 0,        // 0: no L2
    parameter integer L2_WAYS = 8,
    parameter integer L2_LINE = 64,      // bytes, power of two, >= 8
    parameter integer L2_LAT = 12,       // read latency of an L2 hit, clocks (only with L2_KIB != 0)
    parameter integer MEM_LAT = 1        // read latency of an L2 miss (or of every read without L2)
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
    localparam integer L2_LINES = L2_KIB != 0 && L2_LINE > 0 ? L2_KIB * 1024 / L2_LINE : 0;
    localparam integer L2_SETS = L2_KIB != 0 && L2_WAYS > 0 ? L2_LINES / L2_WAYS : 1;
    localparam integer L2_N = L2_KIB == 0 || L2_LINES < 1 ? 1 : L2_LINES;
    localparam integer L2_OFF = L2_LINE > 1 ? $clog2(L2_LINE) : 3;
    localparam integer LAT_MAX = 1048576;
    // The set index is the line address modulo L2_SETS, so the set count need not be a power of two.
    generate if (MEM_LAT < 1 || MEM_LAT > LAT_MAX || (L2_KIB != 0 && (L2_KIB < 0 || L2_LAT < 1 || L2_LAT >= MEM_LAT ||
                 L2_LINE < 8 || (L2_LINE & (L2_LINE - 1)) != 0 || L2_WAYS < 1 ||
                 L2_LINES * L2_LINE != L2_KIB * 1024 || L2_SETS < 1 || L2_SETS * L2_WAYS != L2_LINES))) begin : bad_memory_model
        initial $fatal(1, "memory model: 1 <= MEM_LAT <= 1048576; with an L2: 1 <= L2_LAT < MEM_LAT, line a power of two >= 8, L2_KIB*1024 an exact multiple of L2_LINE*L2_WAYS");
    end endgenerate
    // Tags-only L2: line address and last use per line, least recently used replaced (64-bit use
    // stamps: they would wrap only after 2^64 accesses).
    reg [63:0] l2_tag [0:L2_N-1];
    reg [63:0] l2_use [0:L2_N-1];
    reg [L2_N-1:0] l2_valid;
    reg [63:0] l2_clock;
    integer l2_rd_hit = 0, l2_rd_miss = 0, l2_wr_hit = 0, l2_wr_miss = 0;   // statistics for probes
    reg rd_busy;                // a read is waiting for its latency
    reg [31:0] rd_cnt;
    integer l2_w, l2_v;
    reg l2_h;
    // Look up (and on a miss allocate) the line of byte address a; returns 1 on a hit.
    task automatic l2_touch(input [63:0] a, output reg hit);
        integer base, w, v;
        reg [63:0] line;
        begin
            line = a >> L2_OFF;
            base = (line % L2_SETS) * L2_WAYS;
            hit = 0; v = -1;
            l2_clock = l2_clock + 1;
            for (w = 0; w < L2_WAYS; w = w + 1)
                if (l2_valid[base + w] && l2_tag[base + w] == line) begin hit = 1; l2_use[base + w] = l2_clock; end
            if (!hit) begin
                for (w = 0; w < L2_WAYS; w = w + 1) if (v < 0 && !l2_valid[base + w]) v = w;
                if (v < 0) begin
                    v = 0;
                    for (w = 1; w < L2_WAYS; w = w + 1) if (l2_use[base + w] < l2_use[base + v]) v = w;
                end
                l2_valid[base + v] = 1; l2_tag[base + v] = line; l2_use[base + v] = l2_clock;
            end
        end
    endtask
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
        if (reset) begin
            read_ready<=0; read_error<=0; rdata<=0; rd_busy=0; rd_cnt=0; l2_valid=0; l2_clock=0;
            l2_rd_hit=0; l2_rd_miss=0; l2_wr_hit=0; l2_wr_miss=0;
        end else begin
            read_ready<=0;
            // A read answers lat clocks after it is first presented; the request is held
            // stable meanwhile (section 3). An out-of-range read faults after MEM_LAT clocks.
            if (valid && !write_request && !read_ready && !rd_busy) begin
                l2_h = 0;
                if (L2_KIB != 0 && !outside_ram) begin
                    l2_touch(addr, l2_h);
                    if (l2_h) l2_rd_hit = l2_rd_hit + 1; else l2_rd_miss = l2_rd_miss + 1;
                end
                l2_v = l2_h ? L2_LAT : MEM_LAT;
                if (l2_v <= 1) begin
                    read_ready<=1;
                    read_error<=outside_ram;
                    rdata<=outside_ram ? 64'b0 : ram[index];
                end else begin rd_busy = 1; rd_cnt = l2_v - 1; end
            end else if (rd_busy) begin
                if (rd_cnt == 1) begin
                    rd_busy = 0;
                    read_ready<=1;
                    read_error<=outside_ram;
                    rdata<=outside_ram ? 64'b0 : ram[index];
                end
                rd_cnt = rd_cnt - 1;
            end
            if (L2_KIB != 0 && write_request && !outside_ram) begin
                l2_touch(addr, l2_h); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1;
`ifdef WIDE_TRACE
                if (wstrb2!=0 && !outside2) begin l2_touch(addr2, l2_h); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
                if (xok0) begin l2_touch(xaddr[63:0], l2_h); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
                if (xok1) begin l2_touch(xaddr[127:64], l2_h); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
`endif
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
