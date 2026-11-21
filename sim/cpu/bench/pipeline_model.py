"""Trace-driven CPI model of an in-order five-stage pipeline.

Replays a measured retirement trace (tb_bench.sv +profile, one line per
retired instruction: `R pc insn rd next_pc fetch exec mem`) through a timing
model of a hypothetical pipeline: F1 (PC/BTB), F2 (instruction cache read),
D (decode, register read), EX (ALU, branch, address), MEM (data cache,
retire). Results forward from EX/MEM and the MEM result register into EX.

Modelled penalties (each configurable):
  load-use   a load result reaches EX two cycles after the load's EX, so a
             dependent instruction in the next issue group stalls one cycle
             (ALU operand, branch operand or address base). Store data is
             needed only in MEM when --late-store-data is on (default).
  mul/div    blocking: the pipeline stalls --mul-stall cycles per multiply;
             a divide stalls (cost - 1), where cost is either the core's
             measured EXECUTE clocks for that divide (early-terminating
             shift-subtract from the quotient's top bit, so it tracks the
             real operands) or a fixed --div-cost.
  control    nt: predict not taken, resolve in EX, 3 bubbles when taken.
             static: JAL and backward branches redirect from D (2 bubbles),
             forward branches predicted not taken, JALR 3, mispredict 3.
             btbN: direct-mapped BTB of N entries indexed by pc, full tags,
             2-bit counters, plus a return-address stack; correct = 0,
             wrong direction/target or BTB miss on a taken transfer = 3.
             perfect: no control penalty (upper bound).
  width 2    pairs consecutive instructions: no RAW between them, at most one
             load/store, at most one control transfer, and a first instruction
             that is predicted or actually taken ends the pair; mul, div,
             fence, ecall/ebreak and CSR issue alone. "2a" also requires the
             pair to lie in one aligned 8-byte beat.

Not modelled: instruction- or data-cache misses (always hit; the trace has no
load addresses), bus contention, wrong-path effects on predictor state, RAS
repair. These are model estimates, not measurements of any RTL.
SPDX-License-Identifier: MIT
"""
import argparse
from pathlib import Path

DMIPS_DIVISOR = 1757
REDIRECT_EX, REDIRECT_D = 3, 2
LINK = (1, 5)
# kinds: 0 alu, 1 load, 2 store, 3 cond branch, 4 jal, 5 jalr, 6 mul, 7 div, 8 alone
ALU, LOAD, STORE, COND, JAL, JALR, MUL, DIV, ALONE = range(9)
CAUSES = ('load-use', 'cond', 'jal', 'jalr', 'ret', 'mul', 'div')


def decode(ins):
    """Return (kind, rd, srcs, store_data_reg, imm_sign) for an RV64 word."""
    op, f3 = ins & 0x7f, (ins >> 12) & 7
    rd, rs1, rs2 = (ins >> 7) & 31, (ins >> 15) & 31, (ins >> 20) & 31
    neg = ins >> 31
    if op in (0x37, 0x17): return ALU, rd, (), 0, 0
    if op == 0x6f: return JAL, rd, (), 0, neg
    if op == 0x67: return JALR, rd, (rs1,), 0, 0
    if op == 0x63: return COND, 0, (rs1, rs2), 0, neg
    if op == 0x03: return LOAD, rd, (rs1,), 0, 0
    if op == 0x23: return STORE, 0, (rs1,), rs2, 0
    if op in (0x13, 0x1b): return ALU, rd, (rs1,), 0, 0
    if op in (0x33, 0x3b):
        if ins >> 25 == 1: return (MUL if f3 < 4 else DIV), rd, (rs1, rs2), 0, 0
        return ALU, rd, (rs1, rs2), 0, 0
    if op == 0x2f: return LOAD, rd, (rs1, rs2), 0, 0
    if op == 0x73: return ALONE, (rd if f3 else 0), ((rs1,) if f3 in (1, 2, 3) else ()), 0, 0
    return ALONE, 0, (), 0, 0  # fence, fence.i, unknown


def load_trace(path):
    recs, measured = [], 0
    for line in Path(path).read_text().splitlines():
        f = line.split()
        if len(f) < 8 or f[0] != 'R':
            continue
        pc, ins, npc = int(f[1], 16), int(f[2], 16), int(f[4], 16)
        clocks = int(f[5]) + int(f[6]) + int(f[7])
        measured += clocks
        kind, rd, srcs, sdata, neg = decode(ins)
        srcs = tuple(r for r in srcs if r)
        recs.append((pc, kind, rd, srcs, sdata, npc, neg, int(f[6]) + int(f[7]), ins))
    return recs, measured


def predict(recs, scheme, ras_depth, tagless):
    """Per-record (penalty, predicted_taken, cause) in program order."""
    out = []
    size = int(scheme[3:]) if scheme.startswith('btb') else 0
    btb, ras = {}, []
    for pc, kind, rd, srcs, _, npc, neg, _, ins in recs:
        if kind not in (COND, JAL, JALR):
            out.append((0, False, None)); continue
        taken = npc != pc + 4 or kind != COND
        rs1 = (ins >> 15) & 31
        is_ret = kind == JALR and rd == 0 and rs1 in LINK
        is_call = kind in (JAL, JALR) and rd in LINK
        cause = {COND: 'cond', JAL: 'jal'}.get(kind, 'ret' if is_ret else 'jalr')
        if scheme == 'perfect':
            out.append((0, taken, cause)); continue
        if scheme == 'nt':
            out.append((REDIRECT_EX if taken else 0, False, cause)); continue
        if scheme == 'static':
            if kind == JAL: pen, pt = REDIRECT_D, True
            elif kind == JALR: pen, pt = REDIRECT_EX, False
            elif neg: pen, pt = (REDIRECT_D if taken else REDIRECT_EX), True
            else: pen, pt = (REDIRECT_EX if taken else 0), False
            out.append((pen, pt, cause)); continue
        idx = (pc >> 2) % size
        e = btb.get(idx)
        hit = e is not None and (tagless or e[0] == pc)
        pt = hit and (e[2] != COND or e[3] >= 2)
        target = (ras[-1] if ras else None) if hit and e[4] else (e[1] if hit else None)
        ok = pt == taken and (not taken or target == npc)
        out.append((0 if ok else REDIRECT_EX, pt, cause))
        if is_ret and ras: ras.pop()
        if is_call:
            ras.append(pc + 4)
            if len(ras) > ras_depth: ras.pop(0)
        if taken:
            ctr = min(3, e[3] + 1) if hit else 2
            btb[idx] = (pc, npc, kind, ctr, is_ret)
        elif hit:
            btb[idx] = e[:3] + (max(0, e[3] - 1),) + e[4:]
    return out


def simulate(recs, pred, width, aligned, a):
    """Return (cycles, stall cycles by cause)."""
    ready = [0] * 32
    stalls = dict.fromkeys(CAUSES, 0)
    t_prev, pend, pend_cause, i, n = 2, 0, None, 0, len(recs)
    while i < n:
        grp = [i]
        if width == 2 and i + 1 < n:
            r0, r1 = recs[i], recs[i + 1]
            k0, k1 = r0[1], r1[1]
            ctl = (COND, JAL, JALR)
            ok = (k0 < MUL and k1 < MUL and r0[5] == r0[0] + 4 and not pred[i][1]
                  and not (k0 in (LOAD, STORE) and k1 in (LOAD, STORE))
                  and not (k0 in ctl and k1 in ctl)
                  and not (r0[2] and (r0[2] in r1[3] or r0[2] == r1[4]))
                  and (not aligned or r0[0] % 8 == 0))
            if ok: grp.append(i + 1)
        need = 0
        for j in grp:
            _, kind, rd, srcs, sdata, *_ = recs[j]
            for r in srcs: need = max(need, ready[r])
            if sdata: need = max(need, ready[sdata] - (1 if a.late_store_data else 0))
        base = t_prev + 1 + pend
        t = max(base, need)
        if pend: stalls[pend_cause] += pend
        stalls['load-use'] += t - base
        pend, pend_cause = 0, None
        for j in grp:
            _, kind, rd, srcs, sdata, npc, neg, mclk, _ = recs[j]
            if kind == MUL: pend, pend_cause = a.mul_stall, 'mul'
            elif kind == DIV:
                cost = max(1, mclk) if a.div_cost == 'measured' else int(a.div_cost)
                pend, pend_cause = cost - 1, 'div'
            elif pred[j][0]: pend, pend_cause = pred[j][0], pred[j][2]
            if rd: ready[rd] = t + (2 if kind == LOAD else 1 + (pend if kind in (MUL, DIV) else 0))
        t_prev, i = t, i + len(grp)
    if pend: stalls[pend_cause] += pend
    return t_prev + 2 + pend, stalls


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('traces', nargs='*', help='profile.trace files (default: the Dhrystone builds present)')
    p.add_argument('--runs', type=int, default=500, help='Dhrystone runs in each trace')
    p.add_argument('--schemes', default='nt,static,btb32,btb64,perfect')
    p.add_argument('--widths', default='1,2,2a', help='1, 2 (any consecutive pair), 2a (aligned 8-byte beat)')
    p.add_argument('--ras', type=int, default=4, help='return-address stack entries')
    p.add_argument('--btb-tagless', action='store_true', help='no BTB tags (aliasing hits)')
    p.add_argument('--mul-stall', type=int, default=3, help='stall cycles per multiply')
    p.add_argument('--div-cost', default='measured', help="cycles per divide, or 'measured'")
    p.add_argument('--late-store-data', action=argparse.BooleanOptionalAction, default=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[3] / 'build' / 'cpu' / 'bench'
    traces = a.traces or [str(root / d / 'profile.trace') for d in
                          ('dhrystone-rv64imb', 'dhrystone-rv64imb-fastrt', 'dhrystone', 'dhrystone-rv64im',
                           'dhrystone-rv64im-fastrt') if (root / d / 'profile.trace').exists()]
    print(f'options: ras={a.ras} btb_tagless={a.btb_tagless} mul_stall={a.mul_stall} '
          f'div_cost={a.div_cost} late_store_data={a.late_store_data} runs={a.runs}')
    print('caches always hit (no addresses in trace); stall columns are cycles per run')
    for tr in traces:
        recs, measured = load_trace(tr)
        n = len(recs)
        print(f'\n{tr}: {n} instructions, {n / a.runs:.2f} per run')
        hdr = (f"{'config':<14}{'cycles':>9}{'CPI':>7}{'cyc/run':>9}{'DMIPS/MHz':>10}{'IPC':>6}"
               + ''.join(f'{c:>9}' for c in CAUSES))
        print(hdr); print('-' * len(hdr))
        mrun = measured / a.runs
        print(f"{'measured core':<14}{measured:>9}{measured / n:>7.3f}{mrun:>9.2f}"
              f"{1e6 / (mrun * DMIPS_DIVISOR):>10.3f}{n / measured:>6.2f}")
        for scheme in a.schemes.split(','):
            pred = predict(recs, scheme, a.ras, a.btb_tagless)
            for w in a.widths.split(','):
                cyc, st = simulate(recs, pred, 2 if w.startswith('2') else 1, w == '2a', a)
                run = cyc / a.runs
                print(f"{'w' + w + ' ' + scheme:<14}{cyc:>9}{cyc / n:>7.3f}{run:>9.2f}"
                      f"{1e6 / (run * DMIPS_DIVISOR):>10.3f}{n / cyc:>6.2f}"
                      + ''.join(f'{st[c] / a.runs:>9.2f}' for c in CAUSES))


if __name__ == '__main__':
    main()
