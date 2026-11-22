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
    parameter integer MEM_LAT = 1,       // read latency of an L2 miss (or of every read without L2)
    // Memory hand-off 2: DRAM reads overlap; MEM_GAP > 0 spaces their starts by that many clocks
    // (a bandwidth limit); a read of an L2 line still arriving waits for it. N_MISS > 1 makes data
    // reads of the out-of-order core split transactions (accepted at once, answered on rsp_*); an
    // instruction read is split when its mem_tag is 8-15, otherwise it stays a blocking read.
    parameter integer MEM_GAP = 0,
    parameter integer N_MISS = 1,
    // 1: a write that misses the L2 also starts a DRAM fill of its line (reads of that line wait
    // for it); 0 (default, as 0.15.0): the posted write allocates the line with no fill.
    parameter integer WRITE_FILL = 0,
    // L2 stream prefetcher (bandwidth engineer, docket item 11 / prefetch research D1; L2_PF 0, the default,
    // is off and leaves the SoC unchanged). L2_PF stream trackers are trained on every read that looks up the
    // L2 (instruction and data): a read within 16 lines of a tracker's last line, in its direction, advances it,
    // and two steps in the same direction confirm the stream. On each read that advances a confirmed stream, the
    // next L2_PF_DEG lines after the tracker's frontier, up to L2_PF_DIST lines past the read, are looked up (no
    // replacement update; a present line only advances the frontier); an absent one joins a 16-entry prefetch
    // queue. Each clock the oldest queued line starts a DRAM fill exactly like a demand miss (mem_start: a
    // MEM_GAP slot and the DRAM latency), but only when the DRAM slot is idle (no start booked for a later
    // clock; demands start as they arrive, so they always win the slot), fewer than L2_PF_N prefetch fills are
    // on their way, and the line is still absent. It is installed most recently used with its arrival clock
    // (l2_ready), never replacing a line whose fill is still arriving. Nothing is sent to the core: a later
    // read hits the L2, waiting for the fill if it is still arriving. Stated, not charged: up to L2_PF_DEG extra
    // L2 tag lookups per read, and one per clock for the queue, beyond the one lookup per request. A demand
    // that arrives while a prefetch holds the current DRAM slot waits for the next one (non-preemptive DRAM).
    parameter integer L2_PF = 0,
    parameter integer L2_PF_DIST = 16,
    parameter integer L2_PF_DEG = 4,
    parameter integer L2_PF_N = 16
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
    generate if (L2_PF < 0 || L2_PF > 16 || (L2_PF != 0 && (L2_KIB == 0 || L2_PF_DIST < 1 || L2_PF_DIST > 64 ||
                 L2_PF_DEG < 1 || L2_PF_DEG > 8 || L2_PF_N < 1 || L2_PF_N > 64))) begin : bad_l2_prefetch
        initial $fatal(1, "L2 prefetcher: L2_PF 0 to 16; when on, an L2, L2_PF_DIST 1 to 64, L2_PF_DEG 1 to 8, L2_PF_N 1 to 64");
    end endgenerate
    // Tags-only L2: line address and last use per line, least recently used replaced (64-bit use
    // stamps: they would wrap only after 2^64 accesses).
    reg [63:0] l2_tag [0:L2_N-1];
    reg [63:0] l2_use [0:L2_N-1];
    reg [L2_N-1:0] l2_valid;
    reg [63:0] l2_clock;
    reg [63:0] l2_ready [0:L2_N-1];   // clock at which the line's DRAM fill has arrived
    reg [63:0] now, mem_next;         // clocks since reset; earliest next DRAM start
    reg [63:0] l2_lat_v;           // clocks to a read's answer (64-bit, so a long DRAM backlog no longer wraps)
    integer l2_rd_hit = 0, l2_rd_miss = 0, l2_wr_hit = 0, l2_wr_miss = 0;   // statistics for probes
    // L2 stream prefetcher state (L2_PF != 0). Trackers: valid, last line, direction (+1, -1 or 0 while
    // untrained), confidence 0-3, frontier (the last line prefetched or found present), use stamp. pf_fly holds
    // the arrival clocks of the prefetch fills in flight.
    localparam integer PF_T = L2_PF > 0 ? L2_PF : 1;
    localparam integer PF_F = L2_PF > 0 ? L2_PF_N : 1;
    localparam integer PF_WIN = 16;
    reg [PF_T-1:0] pf_ok;
    reg [63:0] pf_last [0:PF_T-1];
    reg [63:0] pf_front [0:PF_T-1];
    reg [63:0] pf_stamp [0:PF_T-1];
    integer pf_dir [0:PF_T-1];
    integer pf_conf [0:PF_T-1];
    reg [63:0] pf_fly [0:PF_F-1];
    reg [63:0] pf_clock;
    reg [L2_N-1:0] l2_pfb;            // brought in by a prefetch and not yet read by a demand read
    localparam integer PF_Q = 16;     // prefetch queue entries
    reg [63:0] pfq [0:PF_Q-1];
    integer pfq_n;
    function automatic pf_queued(input [63:0] line);
        integer q;
        begin
            pf_queued = 0;
            for (q = 0; q < PF_Q; q = q + 1) if (q < pfq_n && pfq[q] == line) pf_queued = 1;
        end
    endfunction
    // A demand access to a queued line removes it from the queue.
    task automatic pf_cancel(input [63:0] line);
        integer q, o;
        begin
            o = 0;
            for (q = 0; q < PF_Q; q = q + 1) if (q < pfq_n && pfq[q] != line) begin pfq[o] = pfq[q]; o = o + 1; end
            pfq_n = o;
        end
    endtask
    // Statistics: fills issued; lookups that found the line present; prefetched lines whose first access was a
    // demand read (late: it arrived after now + L2_LAT, so the read waited) or a write; prefetched lines evicted
    // before any access; candidates dropped because the queue was full (full, candidates), clocks the queue
    // head waited for a busy DRAM slot or the in-flight limit (busy, clocks), and queued lines dropped because
    // every way of their set was still arriving (pending, candidates). A queued line that a demand access
    // touches leaves the queue.
    reg [63:0] l2_pf_issue = 0, l2_pf_present = 0, l2_pf_used = 0, l2_pf_late = 0, l2_pf_wfirst = 0, l2_pf_evict = 0;
    reg [63:0] l2_pf_full = 0, l2_pf_busy = 0, l2_pf_pend = 0;
    reg rd_busy;                // a read is waiting for its latency
    reg [63:0] rd_cnt;
    integer l2_w;
    reg [63:0] l2_v;
    reg l2_h;
    task automatic mem_start(output reg [63:0] lat);
        reg [63:0] st;
        begin
            st = mem_next > now ? mem_next : now;
            lat = st - now + MEM_LAT;
            mem_next = st + MEM_GAP;
        end
    endtask
    // Split data reads (N_MISS > 1): accepted when presented, answered lat clocks later.
    // Tags 0-7: data reads; tags 8-15: instruction reads a core sends as split (mem_tag[3] set).
    localparam integer SP_N = N_MISS > 1 ? 16 : 1;
    reg [SP_N-1:0] sp_v;
    reg [3:0] sp_tag [0:SP_N-1];
    reg [63:0] sp_addr [0:SP_N-1];
    reg [63:0] sp_cnt [0:SP_N-1];
    reg [2:0] sp_left [0:SP_N-1];     // line reads (mem_len > 0): beats still to answer after this one
    reg [2:0] sp_lm [0:SP_N-1];       // beats - 1 of the line (its wrap mask)
    reg rsp_valid, rsp_error;
    reg [3:0] rsp_tag;
    reg [63:0] rsp_data;
    wire [3:0] tag;
    wire [2:0] len;
`ifndef RV64_OOO_DLINE
    assign len = 3'd0;                 // a core without line reads has no mem_len
`endif
    integer sp_k, sp_free, sp_pick;
    reg [63:0] sp_seq [0:SP_N-1];     // acceptance order: the oldest due read is answered first
    reg [63:0] sp_next;
`ifndef WIDE_TRACE
    // Split reads exist only for the out-of-order core (its mem_tag and rsp_* ports).
    generate if (N_MISS > 1) begin : split_needs_ooo
        initial $fatal(1, "N_MISS > 1 needs the out-of-order core (WIDE_TRACE build)");
    end endgenerate
`endif
    // Look up (and on a miss allocate) the line of byte address a; returns 1 on a hit.
    task automatic l2_touch(input [63:0] a, input is_read, output reg hit, output reg [63:0] lat);
        integer base, w, v;
        reg [63:0] line;
        begin
            line = a >> L2_OFF;
            base = (line % L2_SETS) * L2_WAYS;
            hit = 0; v = -1; lat = 0;
            l2_clock = l2_clock + 1;
            if (L2_PF != 0) pf_cancel(line);
            for (w = 0; w < L2_WAYS; w = w + 1)
                if (l2_valid[base + w] && l2_tag[base + w] == line) begin
                    hit = 1; l2_use[base + w] = l2_clock;
                    lat = l2_ready[base + w] > now + L2_LAT ? l2_ready[base + w] - now : L2_LAT;
                    if (L2_PF != 0 && l2_pfb[base + w]) begin
                        l2_pfb[base + w] = 0;
                        if (!is_read) l2_pf_wfirst = l2_pf_wfirst + 1;
                        else begin
                            l2_pf_used = l2_pf_used + 1;
                            if (l2_ready[base + w] > now + L2_LAT) l2_pf_late = l2_pf_late + 1;
                        end
                    end
                end
            if (!hit) begin
                for (w = 0; w < L2_WAYS; w = w + 1) if (v < 0 && !l2_valid[base + w]) v = w;
                // with the prefetcher on, prefer the least recently used way whose fill has arrived
                if (v < 0 && L2_PF != 0)
                    for (w = 0; w < L2_WAYS; w = w + 1)
                        if (l2_ready[base + w] <= now && (v < 0 || l2_use[base + w] < l2_use[base + v])) v = w;
                if (v < 0) begin
                    v = 0;
                    for (w = 1; w < L2_WAYS; w = w + 1) if (l2_use[base + w] < l2_use[base + v]) v = w;
                end
                if (L2_PF != 0) begin
                    if (l2_valid[base + v] && l2_pfb[base + v]) l2_pf_evict = l2_pf_evict + 1;
                    l2_pfb[base + v] = 0;
                end
                l2_valid[base + v] = 1; l2_tag[base + v] = line; l2_use[base + v] = l2_clock;
                if (is_read) begin mem_start(lat); l2_ready[base + v] = now + lat; end
                else if (WRITE_FILL != 0) begin mem_start(lat); l2_ready[base + v] = now + lat; lat = 0; end
                else begin lat = 0; l2_ready[base + v] = now; end   // a posted write allocates without a fill
            end
        end
    endtask
    // Prefetcher: train on the line of a read that looked up the L2, then issue for a confirmed stream.
    task automatic pf_access(input [63:0] line);
        integer t, m, v, k, w, base;
        reg signed [63:0] d, bd;
        reg [63:0] cand, lim;
        reg present, stop;
        begin
            m = -1; bd = 0; pf_clock = pf_clock + 1;
            for (t = 0; t < PF_T; t = t + 1) if (pf_ok[t]) begin
                d = $signed(line - pf_last[t]);
                if (d >= -PF_WIN && d <= PF_WIN && (pf_dir[t] == 0 || d == 0 || (d > 0) == (pf_dir[t] > 0)) &&
                    (m < 0 || (d < 0 ? -d : d) < (bd < 0 ? -bd : bd))) begin m = t; bd = d; end
            end
            if (m < 0) begin
                v = 0;
                for (t = 0; t < PF_T; t = t + 1) if (!pf_ok[t] && pf_ok[v]) v = t;
                for (t = 0; t < PF_T; t = t + 1) if (pf_ok[t] && pf_ok[v] && pf_stamp[t] < pf_stamp[v]) v = t;
                pf_ok[v] = 1; pf_last[v] = line; pf_front[v] = line; pf_dir[v] = 0; pf_conf[v] = 0; pf_stamp[v] = pf_clock;
            end else begin
                pf_stamp[m] = pf_clock;
                if (bd != 0) begin
                    if (pf_dir[m] == 0) begin pf_dir[m] = bd > 0 ? 1 : -1; pf_conf[m] = 1; end
                    else if (pf_conf[m] < 3) pf_conf[m] = pf_conf[m] + 1;
                    pf_last[m] = line;
                    if (pf_dir[m] > 0 ? $signed(pf_front[m] - line) < 0 : $signed(pf_front[m] - line) > 0) pf_front[m] = line;
                    // Issue: up to L2_PF_DEG lookups, walking the frontier toward L2_PF_DIST lines past this read.
                    if (pf_conf[m] >= 2) begin
                        k = 0; stop = 0;
                        lim = pf_dir[m] > 0 ? line + L2_PF_DIST : line - L2_PF_DIST;
                        while (!stop && k < L2_PF_DEG && pf_front[m] != lim) begin
                            cand = pf_dir[m] > 0 ? pf_front[m] + 64'd1 : pf_front[m] - 64'd1;
                            if ((cand << L2_OFF) >= RAM_WORDS * 64'd8 || ((cand << L2_OFF) >> L2_OFF) != cand) stop = 1;   // past the RAM
                            else begin
                                base = (cand % L2_SETS) * L2_WAYS; present = 0;
                                for (w = 0; w < L2_WAYS; w = w + 1) if (l2_valid[base + w] && l2_tag[base + w] == cand) present = 1;
                                k = k + 1;
                                if (present) begin pf_front[m] = cand; l2_pf_present = l2_pf_present + 1; end
                                else if (pf_queued(cand)) pf_front[m] = cand;
                                else if (pfq_n >= PF_Q) begin l2_pf_full = l2_pf_full + 1; stop = 1; end
                                else begin pfq[pfq_n] = cand; pfq_n = pfq_n + 1; pf_front[m] = cand; end
                            end
                        end
                    end
                end
            end
        end
    endtask
    // One queue step per clock, after this clock's demand requests: the oldest queued line starts its fill
    // when the DRAM slot is idle and fewer than L2_PF_N prefetch fills are in flight.
    task automatic pf_step;
        integer t, n, f, w, base, vv;
        reg [63:0] pl;
        reg present;
        begin
            n = 0; f = 0;
            for (t = PF_F - 1; t >= 0; t = t - 1) if (pf_fly[t] > now) n = n + 1; else f = t;
            if (pfq_n > 0) begin
                if (mem_next > now || n >= L2_PF_N) l2_pf_busy = l2_pf_busy + 1;
                else begin
                    base = (pfq[0] % L2_SETS) * L2_WAYS; present = 0;
                    for (w = 0; w < L2_WAYS; w = w + 1) if (l2_valid[base + w] && l2_tag[base + w] == pfq[0]) present = 1;
                    // the victim: an invalid way, else the least recently used way whose fill has arrived
                    vv = -1;
                    for (w = 0; w < L2_WAYS; w = w + 1) if (vv < 0 && !l2_valid[base + w]) vv = w;
                    if (vv < 0)
                        for (w = 0; w < L2_WAYS; w = w + 1)
                            if (l2_ready[base + w] <= now && (vv < 0 || l2_use[base + w] < l2_use[base + vv])) vv = w;
                    if (present) l2_pf_present = l2_pf_present + 1;
                    else if (vv < 0) l2_pf_pend = l2_pf_pend + 1;
                    else begin
                        if (l2_valid[base + vv] && l2_pfb[base + vv]) l2_pf_evict = l2_pf_evict + 1;
                        l2_clock = l2_clock + 1;
                        l2_valid[base + vv] = 1; l2_tag[base + vv] = pfq[0]; l2_use[base + vv] = l2_clock;
                        mem_start(pl); l2_ready[base + vv] = now + pl; l2_pfb[base + vv] = 1;
                        pf_fly[f] = now + pl; l2_pf_issue = l2_pf_issue + 1;
                    end
                    for (t = 0; t < PF_Q - 1; t = t + 1) pfq[t] = pfq[t + 1];
                    pfq_n = pfq_n - 1;
                end
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
    wire split_read=N_MISS > 1 && valid && wstrb==0 && (!instr || tag[3]);
    wire ready=write_request || read_ready || (split_read && sp_v != {SP_N{1'b1}});
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
            now=0; mem_next=0; sp_v=0; sp_next=0; rsp_valid<=0; rsp_error<=0; rsp_tag<=0; rsp_data<=0;
            l2_rd_hit=0; l2_rd_miss=0; l2_wr_hit=0; l2_wr_miss=0;
            if (L2_PF != 0) begin
                pf_ok=0; pf_clock=0; l2_pfb=0; pfq_n=0;
                for (sp_k=0; sp_k<PF_F; sp_k=sp_k+1) pf_fly[sp_k]=0;
                l2_pf_issue=0; l2_pf_present=0; l2_pf_used=0; l2_pf_late=0; l2_pf_wfirst=0; l2_pf_evict=0;
                l2_pf_full=0; l2_pf_busy=0; l2_pf_pend=0;
            end
        end else begin
            read_ready<=0;
            // A read answers lat clocks after it is first presented; the request is held
            // stable meanwhile (section 3). An out-of-range read faults after MEM_LAT clocks.
            now = now + 1;
            rsp_valid<=0;
            if (valid && !write_request && !split_read && !read_ready && !rd_busy) begin
                l2_h = 0;
                if (L2_KIB != 0 && !outside_ram) begin
                    l2_touch(addr, 1'b1, l2_h, l2_lat_v);
                    if (l2_h) l2_rd_hit = l2_rd_hit + 1; else l2_rd_miss = l2_rd_miss + 1;
                    if (L2_PF != 0) pf_access(addr >> L2_OFF);
                end else if (!outside_ram) mem_start(l2_lat_v);
                l2_v = outside_ram ? MEM_LAT : l2_lat_v;
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
            // Split reads: accept into a free entry; answer the entry that is due (lowest index
            // first, one per clock), reading the RAM as it is at that edge.
            if (split_read && sp_v != {SP_N{1'b1}}) begin
                sp_free = 0;
                for (sp_k = SP_N - 1; sp_k >= 0; sp_k = sp_k - 1) if (!sp_v[sp_k]) sp_free = sp_k;
                l2_h = 0;
                if (L2_KIB != 0 && !outside_ram) begin
                    l2_touch(addr, 1'b1, l2_h, l2_lat_v);
                    if (l2_h) l2_rd_hit = l2_rd_hit + 1; else l2_rd_miss = l2_rd_miss + 1;
                    if (L2_PF != 0) pf_access(addr >> L2_OFF);
                end else if (!outside_ram) mem_start(l2_lat_v);
                sp_v[sp_free] = 1; sp_tag[sp_free] = tag; sp_addr[sp_free] = addr; sp_seq[sp_free] = sp_next; sp_next = sp_next + 1;
                sp_cnt[sp_free] = outside_ram ? MEM_LAT : l2_lat_v;
                sp_left[sp_free] = len; sp_lm[sp_free] = len;
                if (L2_KIB != 0 && (len + 1) * 8 > L2_LINE) $fatal(1, "a line read longer than L2_LINE");
            end
            sp_pick = -1;
            for (sp_k = 0; sp_k < SP_N; sp_k = sp_k + 1)
                if (sp_v[sp_k] && sp_cnt[sp_k] <= 1 && (sp_pick < 0 || sp_seq[sp_k] < sp_seq[sp_pick])) sp_pick = sp_k;
            for (sp_k = 0; sp_k < SP_N; sp_k = sp_k + 1) if (sp_v[sp_k]) begin
                if (sp_k == sp_pick) begin
                    sp_v[sp_k] = 0;
                    rsp_valid<=1; rsp_tag<=sp_tag[sp_k];
                    rsp_error<=sp_addr[sp_k]>=RAM_WORDS*64'd8;
                    rsp_data<=sp_addr[sp_k]>=RAM_WORDS*64'd8 ? 64'b0 : ram[sp_addr[sp_k][INDEX_BITS+2:3]];
                    if (sp_left[sp_k] != 0) begin
                        // the next beat of the line, wrapping, in the next clock
                        sp_v[sp_k] = 1; sp_left[sp_k] = sp_left[sp_k] - 3'd1; sp_cnt[sp_k] = 1;
                        sp_addr[sp_k] = (sp_addr[sp_k] & ~({58'b0, sp_lm[sp_k], 3'b000})) |
                                        ({58'b0, (sp_addr[sp_k][5:3] + 3'd1) & sp_lm[sp_k], 3'b000});
                    end
                end else if (sp_cnt[sp_k] > 1) sp_cnt[sp_k] = sp_cnt[sp_k] - 1;
            end
            if (L2_KIB != 0 && write_request && !outside_ram) begin
                l2_touch(addr, 1'b0, l2_h, l2_lat_v); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1;
`ifdef WIDE_TRACE
                if (wstrb2!=0 && !outside2) begin l2_touch(addr2, 1'b0, l2_h, l2_lat_v); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
                if (xok0) begin l2_touch(xaddr[63:0], 1'b0, l2_h, l2_lat_v); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
                if (xok1) begin l2_touch(xaddr[127:64], 1'b0, l2_h, l2_lat_v); if (l2_h) l2_wr_hit = l2_wr_hit + 1; else l2_wr_miss = l2_wr_miss + 1; end
`endif
            end
            // the prefetch queue step comes after every demand request of this clock (reads and writes)
            if (L2_PF != 0) pf_step;
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
        ,.PAIR_WRITES(1),.EXTRA_WRITES(2),.N_MISS(N_MISS)
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
        .mem_xaddr(xaddr),.mem_xwdata(xwdata),.mem_xwstrb(xwstrb),.mem_xerror(xerror),
        .mem_tag(tag),
`ifdef RV64_OOO_DLINE
        .mem_len(len),
`endif
        .rsp_valid(rsp_valid),.rsp_tag(rsp_tag),.rsp_data(rsp_data),.rsp_error(rsp_error)
`endif
    );
endmodule
