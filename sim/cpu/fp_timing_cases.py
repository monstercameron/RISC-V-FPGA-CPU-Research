"""FP timing cases for test_cpu.py --fpu (council backend; latency and throughput of the
FP execute patch handoff-fp-exec.py). Usage inside test_cpu.py:
    import fp_timing_cases as FT
    cases():  yield from FT.cases(globals())          # only with --fpu
    after the run loop:  FT.check(records, args)      # only with --fpu, default caches
Each program is plain RV64IFD (results checked against the golden model as usual). The checks use
the stall-0 'cycles=' of chains of 40 and 72 steps (and loops of 20 and 52 iterations), so start-up
costs cancel. They hold only at default caches and stall 0 (as the --ld-lat checks); with 2-beat
caches or bus waits the programs still run and are compared, but not timed.
"""
import re

FMA_LAT, FADD_LAT, FMISC_LAT, FCVT_LAT = 4, 3, 2, 3
FDIV_S, FDIV_D, FSQRT_S, FSQRT_D = 11, 13, 12, 18
FDIV_II_S, FDIV_II_D, FSQRT_II_S, FSQRT_II_D = 3, 4, 4, 6   # handoff-fp-div.py


def _ops(T):
    opfp = lambda f7, rs2, rs1, rm, rd: f7 << 25 | rs2 << 20 | rs1 << 15 | rm << 12 | rd << 7 | 0x53
    fma = lambda rs3, rs2, rs1, rd: rs3 << 27 | 1 << 25 | rs2 << 20 | rs1 << 15 | rd << 7 | 0x43
    # f1 = f2 = 1.0, f3 = 0.0 from x2 = 1 and x1 = 0 (test_cpu prefix constants)
    setup = [opfp(0b1101001, 2, 2, 0, 1), opfp(0b1101001, 2, 2, 0, 2), opfp(0b1101001, 2, 1, 0, 3)]
    chains = {   # name: (prelude, step, clocks per step)
        'fmadd_d': ([], [fma(3, 2, 1, 1)], FMA_LAT),
        'fmul_d': ([], [opfp(0b0001001, 2, 1, 0, 1)], FMA_LAT),
        'fadd_d': ([], [opfp(0b0000001, 2, 1, 0, 1)], FADD_LAT),
        'fsgnjn_d': ([], [opfp(0b0010001, 1, 1, 1, 1)], FMISC_LAT),
        'fcvt_sd_ds': ([], [opfp(0b0100000, 1, 1, 0, 1), opfp(0b0100001, 0, 1, 0, 1)], 2 * FCVT_LAT),
        'fmv_xd_dx': ([], [opfp(0b1110001, 0, 1, 0, 5), opfp(0b1111001, 0, 5, 0, 1)], 2 * FMISC_LAT),
        'fdiv_d': ([], [opfp(0b0001101, 2, 1, 0, 1)], FDIV_D),
        'fdiv_s': ([opfp(0b0100000, 1, 1, 0, 1), opfp(0b0100000, 1, 2, 0, 2)], [opfp(0b0001100, 2, 1, 0, 1)], FDIV_S),
        'fsqrt_d': ([], [opfp(0b0101101, 0, 1, 0, 1)], FSQRT_D),
        'fsqrt_s': ([opfp(0b0100000, 1, 1, 0, 1)], [opfp(0b0101100, 0, 1, 0, 1)], FSQRT_S),
    }
    loops = {    # name: (32-op body, clocks per iteration)
        'fmadd_d': ([fma(3, 2, 1, 4 + i % 24) for i in range(32)], 16),   # 2 FMA ports
        'fadd_d': ([opfp(1, 3, 1, 0, 4 + i % 24) for i in range(32)], 8),  # all 4 FP ports
        'fsgnj_d': ([opfp(0b0010001, 2, 1, 0, 4 + i % 24) for i in range(32)], 16),  # 2 misc ports
        # pipelined divide/sqrt: 8 independent operations per iteration, one start per II
        'fdiv_d': ([opfp(0b0001101, 2, 1, 0, 4 + i) for i in range(8)], 8 * FDIV_II_D),
        'fsqrt_d': ([opfp(0b0101101, 0, 1, 0, 4 + i) for i in range(8)], 8 * FSQRT_II_D),
        'fdiv_s': ([opfp(0b0001100, 2, 1, 0, 4 + i) for i in range(8)], 8 * FDIV_II_S),
        'fsqrt_s': ([opfp(0b0101100, 0, 1, 0, 4 + i) for i in range(8)], 8 * FSQRT_II_S),
    }
    return setup, chains, loops


def cases(g):
    T = type('T', (), {k: staticmethod(g[k]) for k in ('prefix', 'i_type', 'branch')})
    MASK = g['MASK']
    setup, chains, loops = _ops(T)
    for name, (pre, step, _) in chains.items():
        for n in (40, 72):
            yield f'fp_lat_{name}_{n}', T.prefix() + setup + pre + step * n + [0x100073], 0, MASK
    for name, (body, _) in loops.items():
        for n in (20, 52):
            loop = body + [T.i_type(0x13, 10, 0, 10, -1)]
            loop.append(T.branch(1, 10, 0, -4 * len(loop)))
            yield f'fp_tput_{name}_{n}', T.prefix() + setup + [T.i_type(0x13, 10, 0, 0, n)] + loop + [0x100073], 0, MASK


def check(records, args):
    """Raise AssertionError unless every chain and loop has its designed timing (stall 0)."""
    if args.icache_beats is not None or args.dcache_beats is not None:
        return
    cyc = {r['case']: int(re.search(r'cycles=(\d+)', r['simulator_summary'])[1]) for r in records
           if r['max_wait_cycles'] == 0 and r['case'].startswith(('fp_lat_', 'fp_tput_'))}
    _, chains, loops = _ops(type('T', (), {}))
    for name, (_, _, per) in chains.items():
        got = cyc[f'fp_lat_{name}_72'] - cyc[f'fp_lat_{name}_40']
        if not 32 * per <= got <= 32 * per + 4:
            raise AssertionError(f'FP latency {name}: 32 chained steps took {got} clocks, expected {32 * per}')
    for name, (_, per) in loops.items():
        got = cyc[f'fp_tput_{name}_52'] - cyc[f'fp_tput_{name}_20']
        if not 32 * per <= got <= 32 * per + 8:
            raise AssertionError(f'FP throughput {name}: 32 iterations took {got} clocks, expected {32 * per}')
