"""Lockstep comparison of rv_iss --sys with Spike over the first N instructions of a boot.

Runs both models on the same ELF and device tree (Spike: --dtb sets its ISA string, PMP count and MMU type;
rv_iss: --time spike reproduces Spike's scheduling, --marchid 5 its marchid), each writing its commit log
(Spike's --log-commits format) into a named pipe, and compares the two streams record by record as they are
produced, so the logs never touch the disk. Each record is (privilege, pc, instruction, x/f writes, memory
reads, memory writes); Spike's CSR records are ignored (commit_compare.py). Stops at the first difference and
prints the preceding records of both logs.

Usage (WSL): python3 -B sim/cpu/sys/spike_compare.py [--spike PATH] [--elf FILE --dtb FILE] [--instructions N]
             [--min N] [--expect-finisher-end] [--uart-in FILE] [--deadline SECONDS]
SPDX-License-Identifier: MIT
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import commit_compare  # noqa: E402
import riscv_tests  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spike', default=str(riscv_tests.LINUX_LAB / 'build/spike/spike'))
    ap.add_argument('--elf', type=Path, default=riscv_tests.LINUX_LAB / 'out/fw_payload.elf')
    ap.add_argument('--dtb', type=Path, default=riscv_tests.LINUX_LAB / 'out/lab-virt.dtb')
    ap.add_argument('--instructions', type=int, default=10_000_000)
    ap.add_argument('--ram-mib', type=int, default=64)
    ap.add_argument('--context', type=int, default=8)
    ap.add_argument('--min', type=int, default=0, help='fail unless at least this many records are equal')
    ap.add_argument('--expect-finisher-end', action='store_true',
                    help='the boot ends at the power-off read of the SiFive test finisher, which only rv_iss '
                         'models: accept that one difference and require rv_iss to exit through the finisher')
    ap.add_argument('--spike-steps', type=int, default=20_000_000_000,
                    help="Spike's --instructions limit (steps; idle WFI chunks count 5000 each)")
    ap.add_argument('--uart-in', type=Path, help="scripted console input: rv_iss --uart-in and Spike's stdin")
    ap.add_argument('--deadline', type=float, default=280.0, help='seconds before both models are killed')
    args = ap.parse_args()
    exe = riscv_tests.build_iss()
    n = args.instructions
    with tempfile.TemporaryDirectory(prefix='spikecmp-') as tmp:
        fa, fb = os.path.join(tmp, 'spike.log'), os.path.join(tmp, 'iss.log')
        os.mkfifo(fa)
        os.mkfifo(fb)
        # Spike counts steps, not retired instructions (a trap or WFI ends its 5000-step chunk early, and an
        # idle chunk counts 5000), so it gets a generous step limit and is stopped once N records compared.
        spike = subprocess.Popen([args.spike, f'--dtb={args.dtb}', f'-m{args.ram_mib}', '--triggers=0',
                                  f'--instructions={args.spike_steps}', '--log-commits', f'--log={fa}',
                                  str(args.elf)],
                                 stdin=open(args.uart_in, 'rb') if args.uart_in else subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=open(os.path.join(tmp, 'spike.err'), 'wb'))
        iss_json = os.path.join(tmp, 'iss.json')
        iss = subprocess.Popen([str(exe), '--sys', '1', '--ram', str(args.ram_mib << 20), '--elf', str(args.elf),
                                '--dtb', str(args.dtb), '--time', 'spike', '--marchid', '5', '--max', str(n),
                                '--commit-log', fb, '--uart-out', os.path.join(tmp, 'iss.uart'),
                                *(['--uart-in', str(args.uart_in)] if args.uart_in else [])],
                               stdin=subprocess.DEVNULL, stdout=open(iss_json, 'wb'),
                               stderr=open(os.path.join(tmp, 'iss.err'), 'wb'))
        expired = []

        def watchdog():
            # Kill both models at the deadline; opening each FIFO for writing (non-blocking) then releases a
            # reader still blocked in open(), which then sees end of file.
            expired.append(True)
            for p in (spike, iss):
                if p.poll() is None:
                    p.kill()
            for f in (fa, fb):
                try:
                    os.close(os.open(f, os.O_WRONLY | os.O_NONBLOCK))
                except OSError:
                    pass

        timer = threading.Timer(args.deadline, watchdog)
        timer.start()
        t0 = time.time()
        ha, hb = collections.deque(maxlen=args.context), collections.deque(maxlen=args.context)
        count, diff, recs = 0, None, None
        try:
            with open(fa, errors='replace') as a, open(fb, errors='replace') as b:
                for la, lb in zip(a, b):
                    if la != lb:
                        ra, rb = commit_compare.parse(la), commit_compare.parse(lb)
                        if ra is None or rb is None or ra != rb:
                            diff, recs = (la.rstrip(), lb.rstrip()), (ra, rb)
                            break
                    ha.append(la.rstrip())
                    hb.append(lb.rstrip())
                    count += 1
                    if count >= n:
                        break
                if spike.poll() is None:
                    spike.kill()
                if diff and args.expect_finisher_end:
                    for _ in b:          # let rv_iss run on to its finisher store and exit
                        pass
                    iss.wait(timeout=60)
        finally:
            timer.cancel()
            for p in (spike, iss):
                if p.poll() is None:
                    p.kill()
                p.wait()
        secs = time.time() - t0
        if expired:
            print(f'FAIL: spike-compare: deadline of {args.deadline:.0f} s reached after {count:,} equal records')
            return 1
        if diff and args.expect_finisher_end and count >= args.min:
            ra, rb = recs
            res = {}
            try:
                res = json.loads(Path(iss_json).read_text().strip().splitlines()[-1])
            except (OSError, ValueError, IndexError):
                pass
            # Expected: rv_iss's record is a load from the finisher at 0x10_0000 (OpenSBI's syscon regmap read);
            # Spike's is the first instruction of its M-mode trap handler after its access fault there; and
            # rv_iss then powers off through the finisher with exit code 0.
            if (rb and ra and rb[4] == (0x100000,) and not rb[5] and ra[0] == 3 and ra[1] != rb[1]
                    and res.get('stop') == 'finisher' and res.get('exit_code') == 0):
                print(f'PASS: {count} instructions of the boot equal in rv_iss and Spike, up to the test-finisher '
                      f'read at power-off that only rv_iss models; rv_iss then powered off through the finisher '
                      f'after {res["instructions"]:,} instructions ({secs:.1f} s)')
                return 0
            print(f'FAIL: spike-compare: the difference at {count:,} is not the expected finisher read '
                  f'(rv_iss stop {res.get("stop")}, exit {res.get("exit_code")})')
        if diff:
            print(f'FAIL: spike-compare: rv_iss differs from Spike at instruction {count:,} ({secs:.1f} s)')
            for x, y in zip(ha, hb):
                print(f'   both   {x}' if x == y else f'   spike  {x}\n   rv_iss {y}')
            print(f'-> spike  {diff[0]}\n-> rv_iss {diff[1]}')
            return 1
        if count < n or count < args.min:
            print(f'FAIL: spike-compare: a log ended after {count:,} equal instructions ({secs:.1f} s); '
                  f'spike stderr: {Path(tmp, "spike.err").read_text(errors="replace")[-300:]}')
            return 1
        print(f'PASS: {count} instructions of the boot equal in rv_iss and Spike ({secs:.1f} s)')
        return 0


if __name__ == '__main__':
    sys.exit(main())
