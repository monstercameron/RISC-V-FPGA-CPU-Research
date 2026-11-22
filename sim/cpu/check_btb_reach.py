"""SPDX-License-Identifier: MIT
Frontend hand-off 15 directed test: BTB targets in another 4 GiB region (Codex 1639-4).

A program cannot run on both sides of a 4 GiB boundary in tb_core's 16 KiB memory, and a
transfer to an address outside it ends the run with a fetch fault before the BTB could be
used again, so the encoding is checked directly: a copy of tb_core.sv calls the core's
btb_fits / btb_enc / btb_dec (hierarchical function calls) for branch and target pairs that
cross 4 GiB boundaries, lie within reach, and lie beyond it. For each pair the target the BTB
would predict must be the real one, or the pair must be rejected as beyond reach. The old
rebuild ({PC[63:32], target[31:2], 00}) is evaluated beside it and reported: it is wrong for
every pair that crosses a 4 GiB boundary. On 0.15.1 the test does not build (the core has no
such functions); with handoff-15 it passes. A short program also runs (trace vs reference).
usage: python3 -B sim/cpu/check_btb_reach.py <core.sv> <out dir> [--sim icarus|verilator]"""
import sys, re, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim/cpu'))
from test_cpu import i_type, image_for, MASK, command   # noqa: E402
from reference import execute                          # noqa: E402
import simulator                                       # noqa: E402

PAIRS = [  # (branch PC, target)
    (0x00000000fffffff0, 0x0000000100000010),   # forward across 4 GiB
    (0x0000000100000010, 0x00000000fffffff0),   # backward across 4 GiB
    (0x00000007fffff000, 0x0000000800000400),
    (0x0000000000001000, 0x0000000000003008),   # same region, near
    (0x0000000000001000, 0x000000007ffff000),   # +2 GiB - 4 KiB: within reach
    (0x0000000080000000, 0x0000000000000004),   # -2 GiB + 4: within reach
    (0x0000000000001000, 0x0000000100001000),   # +4 GiB: beyond reach
    (0xffffffff80000000, 0x0000000000000000),   # +2 GiB exactly: beyond reach
]

def check_block():
    lines = ["    // hand-off 15 test: BTB target encoding",
             "    integer bt_ok=0, bt_bad=0, bt_old_bad=0;",
             "    reg [63:0] bt_p, bt_t, bt_d, bt_o;",
             "    initial begin",
             "        #1;"]
    for pc, t in PAIRS:
        d = (t - pc) & MASK
        fits = (d & 3) == 0 and ((d >> 31) in (0, (1 << 33) - 1))
        lines += [f"        bt_p = 64'h{pc:016x}; bt_t = 64'h{t:016x};",
                  "        bt_o = {bt_p[63:32], bt_t[31:2], 2'b00};",
                  "        if (bt_o != bt_t) bt_old_bad = bt_old_bad + 1;",
                  "        bt_d = dut.btb_dec(bt_p, dut.btb_enc(bt_p, bt_t));",
                  f"        if (dut.btb_fits(bt_p, bt_t) == 1'b{int(fits)} && (!dut.btb_fits(bt_p, bt_t) || bt_d == bt_t)) bt_ok = bt_ok + 1; else bt_bad = bt_bad + 1;"]
    lines += ['        $display("BTBTEST ok=%0d bad=%0d old_wrong=%0d", bt_ok, bt_bad, bt_old_bad);', "    end"]
    return '\n'.join(lines) + '\n'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('core'); ap.add_argument('out')
    ap.add_argument('--sim', default='icarus')
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    tb = (ROOT / 'sim/cpu/tb_core.sv').read_text(encoding='utf-8')
    anchor = "    integer max_retired=0,image_bin=0;\n"
    assert tb.count(anchor) == 1
    tb = tb.replace(anchor, anchor + check_block())
    (out / 'tb_core_h15.sv').write_text(tb, encoding='utf-8', newline='\n')
    sim = simulator.get(a.sim)
    try:
        exe = sim.build('tb_core', [Path(a.core).resolve(), out / 'tb_core_h15.sv'], out / 'h15.vvp',
                        defines=['WIDE_TRACE'], timeout=300)
    except RuntimeError as e:
        print('FAIL: the bench does not build against this core (no BTB target functions)')
        print(str(e).splitlines()[-1] if str(e) else '')
        return 1
    words = [i_type(0x13, 10, 0, 0, 5), 0x100073]
    image = image_for(words)
    expected, _ = execute(image, 0, MASK)
    hexfile = out / 'btb_target.hex'
    hexfile.write_text(''.join(f'{x:02x}\n' for x in image), encoding='ascii')
    trace = out / 'btb_target.trace'
    res = command([*exe, f'+image={hexfile}', f'+trace={trace}', '+stall=0', '+seed=1',
                   '+fault_kind=0', f'+fault_addr={MASK:x}'], timeout=300)
    m = re.search(r'BTBTEST ok=(\d+) bad=(\d+) old_wrong=(\d+)', res)
    ok = m and int(m[2]) == 0 and int(m[1]) == len(PAIRS) and trace.read_text().splitlines() == expected
    print(f'{m[0] if m else "no BTBTEST line"} of {len(PAIRS)} pairs: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
