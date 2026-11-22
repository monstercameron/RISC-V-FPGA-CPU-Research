// SPDX-License-Identifier: MIT
// Machine-mode CSR file and trap state (S1, cpu/PRIV-CONTRACT.md sections 2-3), shared by the cores that
// build with RV64_PRIV. This step implements an M-only hart without Zicntr: the subset that rv_iss
// --isa rv64im_zba_zbb_zbs_zicsr_zifencei --priv m and Spike configured the same implement.
//   mstatus   MIE and MPIE writable, MPP read-only 3, every other field 0
//   misa      read-only (parameter); writes ignored
//   mie       MSIE, MTIE, MEIE writable (no interrupt is taken before the interrupt step)
//   mip       0 (no interrupt sources yet)
//   mtvec     bit 1 read-only 0 (modes 0 and 1); exceptions always go to the base
//   mepc      bits 1:0 read 0 (IALIGN 32: no C)
//   mcause, mtval, mscratch   64-bit registers
//   mcycle    counts clocks (the RTL is the source of its value; a read is marked in the trace by an N record)
//   minstret  counts retired instructions; a write wins over the writing instruction's own count
//   mcountinhibit, mhpmcounter3-31, mhpmevent3-31, mvendorid, marchid, mimpid, mhartid, mconfigptr,
//   tselect, tdata1-3, tinfo           read 0, writes ignored
//   mcontext                            13-bit register (Spike: writable even with 0 triggers)
//   mseccfg (it exists only with Smepmp, Smmpm, Zicfilp or Zkr), anything else, and any write to a read-only
//   address (bits 11:10 = 3), is an illegal instruction
// Reads are combinational; a write commits at the edge where its instruction retires. A trap or an MRET is
// applied at the edge where the core requests it.
module rv64_csr #(
    parameter [63:0] MISA = 64'h8000000000001102   // MXL 2, I, M, B (Zba + Zbb + Zbs, reported as Spike does)
) (
    input  wire        clk,
    input  wire        reset,
    // access port
    input  wire [11:0] addr,
    input  wire        write,        // the instruction writes (CSRRW/CSRRWI, or CSRRS/CSRRC with rs1/uimm != 0)
    output reg  [63:0] rdata,
    output reg         illegal,
    input  wire        commit,       // the access retires at this edge: write wdata to addr
    input  wire [63:0] wdata,
    // trap entry and MRET
    input  wire        trap,
    input  wire [63:0] trap_cause,
    input  wire [63:0] trap_epc,
    input  wire [63:0] trap_tval,
    input  wire        mret,
    // retirement count for minstret: instructions retired at the previous edge, not yet added (the read
    // value includes them)
    input  wire [1:0]  instret_inc,
    output wire [63:0] mtvec_base,
    output wire [63:0] mepc_value
);
    reg mie_bit, mpie_bit;
    reg msie, mtie, meie;
    reg [63:0] mtvec, mepc, mcause, mtval, mscratch, mcycle, minstret;
    reg [12:0] mcontext;
    wire [63:0] mstatus = {51'b0, 2'b11, 3'b0, mpie_bit, 3'b0, mie_bit, 3'b0};
    wire [63:0] instret_now = minstret + {62'b0, instret_inc};
    assign mtvec_base = {mtvec[63:2], 2'b00};
    assign mepc_value = mepc;

    always @* begin
        illegal = 0;
        rdata = 64'b0;
        case (addr)
            12'h300: rdata = mstatus;
            12'h301: rdata = MISA;
            12'h304: rdata = {52'b0, meie, 3'b0, mtie, 3'b0, msie, 3'b0};
            12'h305: rdata = mtvec;
            12'h340: rdata = mscratch;
            12'h7a8: rdata = {51'b0, mcontext};
            12'h341: rdata = mepc;
            12'h342: rdata = mcause;
            12'h343: rdata = mtval;
            12'hb00: rdata = mcycle;
            12'hb02: rdata = instret_now;
            12'h320, 12'h344, 12'h7a0, 12'h7a1, 12'h7a2, 12'h7a3, 12'h7a4,
            12'hf11, 12'hf12, 12'hf13, 12'hf14, 12'hf15: rdata = 64'b0;
            default: illegal = !((addr >= 12'h323 && addr <= 12'h33f) || (addr >= 12'hb03 && addr <= 12'hb1f));
        endcase
        if (write && addr[11:10] == 2'b11) illegal = 1;
    end

    always @(posedge clk) begin
        if (reset) begin
            mie_bit <= 0; mpie_bit <= 0; msie <= 0; mtie <= 0; meie <= 0;
            mtvec <= 0; mepc <= 0; mcause <= 0; mtval <= 0; mscratch <= 0; mcontext <= 0; mcycle <= 0; minstret <= 0;
        end else begin
            mcycle <= mcycle + 64'd1;
            minstret <= instret_now;
            if (trap) begin
                mepc <= {trap_epc[63:2], 2'b00};
                mcause <= trap_cause;
                mtval <= trap_tval;
                mpie_bit <= mie_bit;
                mie_bit <= 0;
            end else if (mret) begin
                mie_bit <= mpie_bit;
                mpie_bit <= 1;
            end else if (commit) begin
                case (addr)
                    12'h300: begin mie_bit <= wdata[3]; mpie_bit <= wdata[7]; end
                    12'h304: begin msie <= wdata[3]; mtie <= wdata[7]; meie <= wdata[11]; end
                    12'h305: mtvec <= {wdata[63:2], 1'b0, wdata[0]};
                    12'h340: mscratch <= wdata;
                    12'h7a8: mcontext <= wdata[12:0];
                    12'h341: mepc <= {wdata[63:2], 2'b00};
                    12'h342: mcause <= wdata;
                    12'h343: mtval <= wdata;
                    12'hb00: mcycle <= wdata;
                    12'hb02: minstret <= wdata;
                    default: begin end
                endcase
            end
        end
    end
endmodule
