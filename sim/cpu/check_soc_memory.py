"""Directed checks of the SoC memory model in rtl/cpu/rv64_bram_soc.sv (since architecture 0.15.0;
memory engineer, after a Codex review): read latency is not truncated, out-of-range reads fault
after MEM_LAT, and invalid L2 geometries or latencies stop elaboration. Icarus Verilog, the
multicycle core; every step has a 300 s limit.
usage: python3 -B sim/cpu/check_soc_memory.py [--out-dir DIR]
SPDX-License-Identifier: MIT"""
import argparse, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def image(path, words):
    data = b''.join(w.to_bytes(4, 'little') for w in words).ljust(16384, b'\0')
    path.write_text(''.join(f'{int.from_bytes(data[i:i + 8], "little"):016x}\n' for i in range(0, len(data), 8)),
                    encoding='ascii')


# name, program, parameters, expected (trap cycle, cause) or None when elaboration must stop
CASES = [
    ('lat70000', 'ebreak', {'MEM_LAT': 70000}, (70003, 3)),            # a latency beyond 16 bits
    ('lat1', 'ebreak', {'MEM_LAT': 1}, (4, 3)),                        # default: today's timing
    ('oor80', 'badload', {'MEM_LAT': 80}, (164, 5)),                   # out-of-range load faults after MEM_LAT
    ('oor1', 'badload', {'MEM_LAT': 1}, (6, 5)),
    ('zero_sets', 'ebreak', {'L2_KIB': 1, 'L2_LINE': 2048, 'L2_WAYS': 1, 'MEM_LAT': 100}, None),
    ('inexact', 'ebreak', {'L2_KIB': 3, 'L2_LINE': 2048, 'L2_WAYS': 1, 'MEM_LAT': 100}, None),
    ('l2_not_faster', 'ebreak', {'L2_KIB': 64, 'L2_LAT': 12, 'MEM_LAT': 12}, None),
    ('lat_too_big', 'ebreak', {'MEM_LAT': 2000000}, None),
    ('l2_3k_3way', 'ebreak', {'L2_KIB': 3, 'L2_LINE': 64, 'L2_WAYS': 3, 'MEM_LAT': 100}, 'trap'),
    # DRAM start spacing: three write fills (WRITE_FILL 1) book DRAM slots MEM_GAP apart, then a load misses
    ('wfgap100', 'wfill', {'L2_KIB': 64, 'L2_LAT': 12, 'MEM_LAT': 100, 'MEM_GAP': 100, 'WRITE_FILL': 1}, (504, 3)),
    # the same with MEM_GAP 2^30: the load's delay is about 2^32 clocks and must be waited for (before the 64-bit fix
    # it wrapped and the load answered at once): no trap in 20,000 clocks
    ('wfgap2p30', 'wfill', {'L2_KIB': 64, 'L2_LAT': 12, 'MEM_LAT': 100, 'MEM_GAP': 1073741824, 'WRITE_FILL': 1}, 'timeout'),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out-dir', default='build/cpu/check-soc-memory')
    out = ROOT / ap.parse_args().out_dir
    out.mkdir(parents=True, exist_ok=True)
    image(out / 'ebreak.hex', [0x00100073])
    image(out / 'badload.hex', [0x00004137, 0x00013083, 0x00100073])  # lui x2,4; ld x1,0(x2); ebreak
    # addi x2,x0,1024; sd x0,0(x2); sd x0,64(x2); sd x0,128(x2); ld x1,192(x2); ebreak
    image(out / 'wfill.hex', [0x40000113, 0x00013023, 0x04013023, 0x08013023, 0x0c013083, 0x00100073])
    fails = 0
    for name, prog, params, expect in CASES:
        vvp = out / f'{name}.vvp'
        build = subprocess.run(['iverilog', '-g2012', *[f'-Ptb_soclat.{k}={v}' for k, v in params.items()],
                                '-o', str(vvp), str(ROOT / 'rtl/cpu/rv64_core.sv'), str(ROOT / 'rtl/cpu/rv64_bram_soc.sv'),
                                str(ROOT / 'sim/cpu/tb_soclat.sv')], capture_output=True, text=True, timeout=300)
        run = None
        if build.returncode == 0:
            run = subprocess.run(['vvp', '-n', str(vvp), f'+image={out / (prog + ".hex")}',
                                  *(['+max_cycles=20000'] if expect == 'timeout' else [])],
                                 capture_output=True, text=True, timeout=300)
        text = (build.stdout + build.stderr + (run.stdout + run.stderr if run else ''))
        m = re.search(r'TRAP cycles=(\d+) cause=(\d+)', text)
        if expect is None:
            ok = m is None and re.search(r'memory model|fatal', text, re.I) is not None
            got = 'stopped' if ok else (f'trap at {m.group(1)}' if m else 'no fatal message')
        elif expect == 'timeout':
            ok = m is None and 'SoC latency test timeout' in text
            got = 'waited (no answer in 20,000 clocks)' if ok else (f'trap at {m.group(1)}' if m else 'no timeout message')
        elif expect == 'trap':
            ok, got = m is not None, (f'trap at {m.group(1)}' if m else 'no trap')
        else:
            ok = m is not None and (int(m.group(1)), int(m.group(2))) == expect
            got = f'cycle {m.group(1)} cause {m.group(2)}' if m else 'no trap'
        print(f'{"ok  " if ok else "FAIL"} {name}: {got}' + ('' if expect in (None, 'trap', 'timeout') else f' (expected cycle {expect[0]} cause {expect[1]})'))
        fails += not ok
    print('PASS: SoC memory-model checks' if not fails else f'FAIL: {fails} SoC memory-model checks')
    raise SystemExit(1 if fails else 0)


if __name__ == '__main__':
    main()
