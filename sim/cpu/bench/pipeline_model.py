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

Out-of-order mode (--ooo) adds a small FPGA-scale out-of-order core:
  front end  fetches up to W consecutive instructions a clock; a group ends
             after a taken or predicted-taken transfer (a correct prediction
             costs no bubble, as in the in-order BTB model). An instruction
             fetched at clock f can be renamed at f + --ooo-fe (default 3).
             The front end holds (fe + 1) * W instructions (back-pressure).
  rename     W a clock, in order; needs a free ROB entry (freed the clock
             after retire) and a free issue-queue entry (freed the clock after
             issue). Earliest issue is the clock after rename.
  issue      unified issue queue, oldest-first select. Ports: N ALU ports
             (ALU ops, branches, jumps; port 0 also takes multiply, pipelined,
             latency --ooo-mul-lat, and divide, unpipelined, latency from the
             measured clocks or --div-cost) and M memory ports shared by loads
             and stores. Latency is issue-to-dependent-issue: ALU 1, load
             --load-lat. A store issues when its address and data are ready.
             CSR, fence and system instructions serialise: they issue at the
             ROB head and younger instructions rename after they retire.
  memory     a: conservative, a load issues only after every older store has
             retired (stores write the cache at retirement).
             b: loads never wait for stores. The trace has no addresses, so
             this stands for store-to-load forwarding with perfect
             disambiguation and forwarding that never delays the load: an
             optimistic bound.
             c: (not in the default grid) a load issues the clock after every
             older store has issued, i.e. once all older store addresses and
             data are known, so a store queue can compare addresses exactly
             and forward with no extra latency. Between a and b.
  retire     W a clock, in order, at or after the result clock.
  recovery   a mispredicted transfer resolves in its issue clock e.
             retire: flush when it retires at clock c; fetch resumes at c + 1.
             early: fetch resumes at e + 1; rename waits until the branch has
             retired (the front end refills meanwhile).
             checkpoint: fetch resumes at e + 1, rename at e + 2 or later.
  Scheduling is computed in program order: with oldest-first select an older
  instruction never waits for a younger one, so each instruction takes the
  first clock at or after its operands are ready with a free port. Wrong-path
  instructions are not in the trace and are not modelled (they would occupy
  ROB, queue and ports before the flush), so recovery costs are optimistic.

Not modelled: instruction- or data-cache misses (always hit; the trace has no
load addresses), bus contention, wrong-path effects on predictor state, RAS
repair. These are model estimates, not measurements of any RTL.
SPDX-License-Identifier: MIT
"""
import argparse
import heapq
import itertools
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


RECOVERY = ('retire', 'early', 'checkpoint')
ORDERS = ('a', 'c', 'b')


def simulate_ooo(recs, pred, cfg, a):
    """Out-of-order timing; cfg = (W, rob, iq, alus, mem_ports, load_lat, order, recovery).

    Returns (cycles, mispredicts)."""
    W, ROB, IQ, NALU, NMEM, LLAT, order, recov = cfg
    FE, MULLAT = a.ooo_fe, a.ooo_mul_lat
    n = len(recs)
    size = 8 * n + 4096
    nz = bytearray(size)    # ALU ports 1..NALU-1 used per clock
    p0 = bytearray(size)    # port 0 used per clock
    mem = bytearray(size)   # memory ports used per clock
    ready = [0] * 32        # clock at which a dependent may issue
    ren, ret = [0] * n, [0] * n
    iqheap = []             # the IQ largest issue times so far (min at [0])
    cap = (FE + 1) * W
    f_prev, f_cnt, end_group = -1, 0, True
    redirect = ren_floor = 0
    last_store_ret, div_free = -1, 0
    store_issued = -1       # latest issue clock of any older store
    r_prev = ret_prev = 0
    miss = 0
    conservative, known = order == 'a', order == 'c'
    nz_max = NALU - 1
    fixed_div = None if a.div_cost == 'measured' else int(a.div_cost)
    for i in range(n):
        pc, kind, rd, srcs, sdata, npc, _, mclk, _ = recs[i]
        # fetch
        f = f_prev if not end_group and f_cnt < W else f_prev + 1
        if f < redirect: f = redirect
        if i >= cap and f < ren[i - cap]: f = ren[i - cap]
        if f != f_prev: f_cnt = 0
        f_cnt += 1
        f_prev = f
        pen, ptaken, _ = pred[i]
        end_group = ptaken or npc != pc + 4
        # rename
        r = f + FE
        if r < r_prev: r = r_prev
        if r < ren_floor: r = ren_floor
        if i >= W and r <= ren[i - W]: r = ren[i - W] + 1
        if i >= ROB and r <= ret[i - ROB]: r = ret[i - ROB] + 1
        if len(iqheap) >= IQ and r <= iqheap[0]: r = iqheap[0] + 1
        ren[i] = r_prev = r
        # issue
        t = r + 1
        for s in srcs:
            if ready[s] > t: t = ready[s]
        if kind == LOAD:
            if conservative and t <= last_store_ret: t = last_store_ret + 1
            elif known and t <= store_issued: t = store_issued + 1
        elif kind == STORE:
            if sdata and ready[sdata] > t: t = ready[sdata]
        elif kind == ALONE:
            if t <= ret_prev: t = ret_prev + 1
        elif kind == DIV:
            if t < div_free: t = div_free
        if t + 256 >= size:
            grow = bytearray(size); nz += grow; p0 += grow; mem += bytearray(size); size *= 2
        if kind == LOAD or kind == STORE:
            while mem[t] >= NMEM: t += 1
            mem[t] += 1
            lat = LLAT if kind == LOAD else 1
        elif kind == MUL or kind == DIV:
            while p0[t]: t += 1
            p0[t] = 1
            if kind == MUL: lat = MULLAT
            else:
                lat = fixed_div if fixed_div is not None else max(1, mclk)
                div_free = t + lat
        else:
            while True:
                if nz[t] < nz_max: nz[t] += 1; break
                if not p0[t]: p0[t] = 1; break
                t += 1
            lat = 1
        done = t + lat
        if rd: ready[rd] = done
        if len(iqheap) < IQ: heapq.heappush(iqheap, t)
        elif t > iqheap[0]: heapq.heapreplace(iqheap, t)
        # retire
        c = done if done > ret_prev else ret_prev
        if i >= W and c <= ret[i - W]: c = ret[i - W] + 1
        ret[i] = ret_prev = c
        if kind == STORE:
            last_store_ret = c
            if t > store_issued: store_issued = t
        elif kind == ALONE and ren_floor <= c: ren_floor = c + 1
        if pen:
            miss += 1
            if recov == 'retire':
                if redirect <= c: redirect = c + 1
            else:
                if redirect <= t: redirect = t + 1
                floor = c + 1 if recov == 'early' else t + 2
                if ren_floor < floor: ren_floor = floor
    return ret_prev + 1, miss


def ooo_grid(a):
    ints = lambda s: [int(x) for x in s.split(',')]
    return list(itertools.product(ints(a.ooo_widths), ints(a.rob), ints(a.iq), ints(a.alus),
                                  ints(a.mem_ports), ints(a.load_lat), a.mem_order.split(','),
                                  a.recovery.split(',')))


def check_monotone(results):
    """Count configurations where adding one resource (or relaxing ordering or
    recovery) increased cycles; return (checked, violations, worst)."""
    checked, bad, worst = 0, 0, (0, None, None)
    values = [sorted({c[pos] for (_, c) in results}) for pos in range(6)]
    for k, cyc in results.items():
        scheme, cfg = k
        for pos, v in enumerate(cfg):
            if pos < 5:    # W, ROB, IQ, ALUs, memory ports: larger is better
                nxt = [x for x in values[pos] if x > v][:1]
            elif pos == 5:  # load latency: smaller is better
                nxt = [x for x in values[pos] if x < v][-1:]
            elif pos == 6:  # memory ordering, strictest first
                present = [x for x in ORDERS if any(c[6] == x for (_, c) in results)]
                nxt = present[present.index(v) + 1:][:1]
            else:
                j = RECOVERY.index(v) + 1
                nxt = list(RECOVERY[j:j + 1])
            for nv in nxt:
                k2 = (scheme, cfg[:pos] + (nv,) + cfg[pos + 1:])
                if k2 in results:
                    checked += 1
                    d = results[k2] - cyc
                    if d > 0:
                        bad += 1
                        if d > worst[0]: worst = (d, k, k2)
    return checked, bad, worst


def run_ooo(recs, a):
    grid = ooo_grid(a)
    n = len(recs)
    print(f'\nout-of-order: fe={a.ooo_fe} mul_lat={a.ooo_mul_lat} div={a.div_cost}; '
          'order: loads wait for older stores to a retire, c issue, b never wait')
    hdr = (f"{'pred':<9}{'W':>2}{'ROB':>5}{'IQ':>5}{'ALU':>4}{'MEM':>4}{'LL':>3}{'ord':>4}"
           f"{'recovery':>11}{'cycles':>9}{'CPI':>7}{'cyc/run':>9}{'DMIPS/MHz':>10}{'IPC':>6}{'mis/run':>8}")
    print(hdr); print('-' * len(hdr))
    results = {}
    for scheme in a.ooo_schemes.split(','):
        pred = predict(recs, scheme, a.ras, a.btb_tagless)
        for cfg in grid:
            cyc, miss = simulate_ooo(recs, pred, cfg, a)
            results[(scheme, cfg)] = cyc
            run = cyc / a.runs
            W, rob, iq, alus, mp, ll, order, recov = cfg
            print(f"{scheme:<9}{W:>2}{rob:>5}{iq:>5}{alus:>4}{mp:>4}{ll:>3}{order:>4}{recov:>11}"
                  f"{cyc:>9}{cyc / n:>7.3f}{run:>9.2f}{1e6 / (run * DMIPS_DIVISOR):>10.3f}"
                  f"{n / cyc:>6.2f}{miss / a.runs:>8.2f}", flush=True)
    checked, bad, worst = check_monotone(results)
    print(f'monotonicity: {checked} one-step resource increases checked, {bad} increased cycles'
          + (f'; worst +{worst[0]} cycles: {worst[1]} -> {worst[2]}' if bad else ''))
    return results


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
    o = p.add_argument_group('out-of-order mode (comma-separated lists sweep a grid)')
    o.add_argument('--ooo', action='store_true', help='also model out-of-order configurations')
    o.add_argument('--ooo-schemes', default='btb256,perfect', help='predictors for the OoO grid')
    o.add_argument('--ooo-widths', default='1,2,4', help='fetch/rename/retire width W')
    o.add_argument('--rob', default='16,32,64', help='reorder-buffer entries')
    o.add_argument('--iq', default='8,16', help='unified issue-queue entries')
    o.add_argument('--alus', default='2,3', help='ALU ports (port 0 also multiply/divide)')
    o.add_argument('--mem-ports', default='1', help='memory ports shared by loads and stores')
    o.add_argument('--load-lat', default='2', help='load issue to dependent issue, clocks')
    o.add_argument('--mem-order', default='a,b',
                   help='a: loads wait for older stores to retire; c: to issue; b: never wait')
    o.add_argument('--recovery', default='retire,early,checkpoint', help='mispredict recovery')
    o.add_argument('--ooo-fe', type=int, default=3, help='fetch-to-rename depth, clocks')
    o.add_argument('--ooo-mul-lat', type=int, default=3, help='multiply latency, clocks')
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
        if a.ooo:
            run_ooo(recs, a)


if __name__ == '__main__':
    main()
