#!/usr/bin/env python3
"""Lockstep of the RTL cores' retirement traces with Spike (riscv-isa-sim), for user-mode lab programs.

The external-model check of the C2 gate: an RTL core's tb_core.sv trace (R/W/F/C/T records) is compared
record by record with Spike's --log-commits output for the same program. Spike is the independent reference
built by sim/cpu/sys/build_spike.sh (BSD-3-Clause, pinned in sim/cpu/sys/sources.lock).

The address-translating adapter. Lab programs are linked at address 0 and run with all registers 0 in the
terminal laboratory environment (architecture.md section 4), but Spike's boot ROM sits at 0x1000 and its RAM at
0x8000_0000. Nothing in the program or the contract changes: an M-mode shim at physical 0xC000_0000 (outside
the program's view) maps virtual 0-1 GiB onto physical 0x8000_0000 with one Sv39 gigapage, loads the program's
registers (zero for a whole program; the rv_iss state for a checkpoint piece), sets mstatus.FS when F/D is in
use, and MRETs to the program's pc in U-mode. U-mode makes the same SYSTEM instructions illegal as the lab
environment (SFENCE.VMA, SRET, WFI and every CSR but the FP ones; counters need mcounteren, which is 0). Spike
logs virtual addresses, so its pcs and store addresses are the lab ones. The program's image is placed at
physical 0x8000_0000, and Spike's RAM there is exactly the lab RAM size, so an access beyond it is an access
fault as in the lab. Any trap enters the shim's M-mode handler, whose first three instructions read mcause,
mepc and mtval into the log; that is the terminal trap, compared with the lab T record after mapping U-mode
ECALL (8) to the lab's 11 and a page fault at or above 1 GiB (outside the window) to the access fault the lab
reports, and dropping Spike's EBREAK tval (the pc; the lab's must be 0).

Compared per instruction: pc, instruction bits, the x or f register written and its value, each store's
address, data and width (a store before the terminal trap included), and the accumulated fflags whenever an
FP instruction raises flags (Spike's c1_fflags record; CSR instructions are compared through their
destination register). The RTL trace is also checked for internal consistency (each successor pc is the next
record's pc; no data without a destination), and a checkpoint's restore stub must load exactly the state
Spike starts from. Not comparable: load addresses (the lab trace has none; a wrong load shows only through
the value it writes) and Spike's privilege field.

Programs:
  rvt SUITE...                 the lab-environment riscv-tests (sim/cpu/riscv_tests), whole tests
  image BENCH_DIR              a build_bench.py folder's bench.bin from instruction 0 (--max N: first N)
  pieces BENCH_DIR             --pieces K windows of --window W instructions from rv_iss checkpoints, spread
                               over the run (--total T: its length; default: rv_iss measures it, which is slow
                               for long runs), restored on the core by bench_checkpoint's stub
Usage (WSL): python3 -B sim/cpu/spike_lockstep.py --core ooo --sim verilator [--fpu] rvt rv64ui rv64um
             python3 -B sim/cpu/spike_lockstep.py --core pipe image --out-dir build/cpu/bench/vl-dhrystone-rv64imb-ooo
Last line: "PASS: N records ..." or "FAIL: spike-lockstep: ...".
SPDX-License-Identifier: MIT
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, HERE / 'bench', HERE / 'sys', HERE / 'riscv_tests'):
    sys.path.insert(0, str(p))
import simulator          # noqa: E402
import bench_checkpoint   # noqa: E402
import commit_compare     # noqa: E402
import riscv_tests as sysrt   # noqa: E402  (third_party lookup)

if not (simulator.VENDORED / 'usr/bin/verilator').is_file():     # a worktree under build/: the enclosing one's
    simulator.VENDORED = sysrt.third_party(ROOT, 'verilator') / 'root'
CORES = {'multicycle': 'rtl/cpu/rv64_core.sv', 'pipe': 'rtl/cpu/rv64_pipe.sv', 'ooo': 'rtl/cpu/rv64_ooo.sv'}
DRAM = 0x80000000
SHIM = 0xC0000000
LIMIT = 280.0
# A tb_core trace larger than this is killed (a run that never ends must not fill the disk). The largest
# legitimate trace, LZMA d12 whole (4.2M instructions), is about 0.35 GB.
TRACE_CAP = 1 << 30
# penv: the instruction budget of both Spike and tb_core; a run that reaches it has not ended at tohost.
PENV_MAX = 2_000_000


def run(args, timeout=LIMIT, **kw):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout, **kw)
    if r.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} rc={r.returncode}: {(r.stdout + r.stderr).strip()[-600:]}')
    return r.stdout


# ---------------------------------------------------------------- Spike side

SHIM_S = r'''
    .section .text.shim, "ax"
    .globl _start
_start:
    la t0, trap
    csrw mtvec, t0
    la t0, pt
    srli t0, t0, 12
    li t1, 8 << 60
    or t0, t0, t1
    csrw satp, t0
    sfence.vma
    li t0, (0 << 11) | ({fs} << 13)            # MPP = U
    csrw mstatus, t0
    la t0, entry
    ld t0, 0(t0)
    csrw mepc, t0
{fp_restore}
    la x31, xtab
{x_restore}
    ld x31, 248(x31)
    mret
    .balign 4
trap:
    csrr t0, mcause
    csrr t1, mepc
    csrr t2, mtval
    la t3, tohost
    li t4, 1
    sd t4, 0(t3)
1:  j 1b

    .section .data.shim, "aw"
    .balign 4096
pt:                                     # Sv39 root: entry 0 = 1 GiB leaf at 0x8000_0000, V R W X U A D
    .dword ((0x80000000 >> 12) << 10) | 0xdf
    .zero 4088
    .balign 8
entry: .dword {pc:#x}
xtab:
{x_table}
ftab:
{f_table}
fcsr_val: .dword {fcsr:#x}
    .globl tohost
tohost: .dword 0
    .globl fromhost
fromhost: .dword 0

    .section .image, "aw"
    .incbin "{image}"
'''

SHIM_LD = '''
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .image : { *(.image) }
  . = 0xC0000000;
  .text.shim : { *(.text.shim) }
  .data.shim : { *(.data.shim) }
}
'''


def shim_elf(work, image, regs, pc, fp, fregs=None, fcsr=0, clang='clang'):
    """An ELF holding the shim (at 0xC000_0000) and the program image (at 0x8000_0000)."""
    img = work / 'image.bin'
    img.write_bytes(image)
    fregs = fregs or [0] * 32
    fp_restore = ''
    if fp:
        fp_restore = '    la t0, fcsr_val\n    ld t0, 0(t0)\n    csrw fcsr, t0\n    la t0, ftab\n' + \
                     ''.join(f'    fld f{i}, {8 * i}(t0)\n' for i in range(32))
    text = SHIM_S.format(fs=3 if fp else 0, fp_restore=fp_restore,
                         x_restore=''.join(f'    ld x{i}, {8 * i}(x31)\n' for i in range(1, 31)),
                         pc=pc, x_table=''.join(f'    .dword {v:#x}\n' for v in regs),
                         f_table=''.join(f'    .dword {v:#x}\n' for v in fregs), fcsr=fcsr, image=img.as_posix())
    (work / 'shim.S').write_text(text)
    (work / 'shim.ld').write_text(SHIM_LD)
    elf = work / 'shim.elf'
    run([clang, '--target=riscv64-unknown-elf', '-march=rv64imafd_zicsr', '-mabi=lp64', '-mcmodel=medany',
         '-mno-relax', '-nostdlib', '-static', '-fuse-ld=lld', f'-T{work / "shim.ld"}', '-o', elf, work / 'shim.S'])
    return elf


def spike_isa(fp):
    return f'rv64im{"fd" if fp else ""}_zba_zbb_zbs_zicsr_zifencei'


FFLAGS = re.compile(r' c1_fflags (0x[0-9a-f]+)')


def spike_records(log):
    """('R', pc, insn, regs, stores, fflags) for the program's instructions, then ('T', cause, pc, tval, ()).
    fflags: fflags after the instruction when it wrote them (Spike's c1_fflags record), CSR instructions
    excluded; else None."""
    phase = 0
    trap = []
    for line in log:
        r = commit_compare.parse(line)
        if r is None:
            if line.startswith('core'):
                raise ValueError(f'unparsable Spike record {line.rstrip()!r}')
            continue
        prv, pc, insn, regs, _loads, stores = r
        if phase == 0:              # the shim, up to and including its MRET
            if insn == 0x30200073:
                phase = 1
            continue
        if phase == 1:
            if prv == 0:
                m = FFLAGS.search(line)
                fl = int(m[1], 16) if m and (insn & 0x7f) != 0x73 else None
                yield ('R', pc, insn, regs, stores, fl)
                continue
            phase = 2
        trap.append(regs[0][1] if regs else None)       # csrr t0/t1/t2 at the shim's handler
        if len(trap) == 3:
            cause, epc, tval = trap
            if cause in (12, 13, 15) and tval >= 1 << 30:   # outside the 1 GiB window: an access fault in the lab
                cause = {12: 1, 13: 5, 15: 7}[cause]
            cause = 11 if cause == 8 else cause                 # ECALL from U is the lab's ECALL
            yield ('T', cause, epc, 0 if cause == 3 else tval, ())
            return


# ---------------------------------------------------------------- RTL side

def rtl_records(lines, skip=0, fflags=0, stub=None):
    """Records from a tb_core/reference.py trace in the form of spike_records. The first `skip` R records (a
    restore stub) are dropped; their register writes go into `stub` (dict) if given. Internal consistency is
    checked: each R record's successor pc must be the next record's pc (or the trap pc), and a record without
    a destination must report data 0. fflags: the initial accumulated flags."""
    stores = []
    seen = 0
    expect_pc = None
    raised = False
    sourced = False
    for line in lines:
        k = line[:1]
        if k == 'W':
            _, a, d, m = line.split()
            a, d, m = int(a, 16), int(d, 16), int(m, 16)
            lane = (m & -m).bit_length() - 1
            width = bin(m).count('1')
            if m == 0 or m >> lane != (1 << width) - 1:
                raise ValueError(f'bad store mask in {line!r}')
            stores.append((a + lane, (d >> (8 * lane)) & ((1 << (8 * width)) - 1), width))
        elif k == 'F':
            fflags |= int(line.split()[1], 16)
            raised = True
        elif k == 'C':
            _, csr, v = line.split()
            if int(csr, 16) == 3:
                fflags = int(v, 16) & 0x1f
        elif k == 'R':
            _, pc, insn, rd, val, nxt = line.split()
            pc, insn, rd, val, nxt = int(pc, 16), int(insn, 16), int(rd, 16), int(val, 16), int(nxt, 16)
            if expect_pc is not None and pc != expect_pc:
                raise ValueError(f'RTL trace: pc {pc:#x} after a record whose successor was {expect_pc:#x}')
            if rd == 0 and val != 0:
                raise ValueError(f'RTL trace: data {val:#x} reported without a destination at pc {pc:#x}')
            expect_pc = nxt
            seen += 1
            fl = fflags if raised else None
            if seen > skip:
                # after an N record the value is the RTL's own (mcycle): DUT-sourced, not compared (None)
                regs = () if rd == 0 else (((f'x{rd}' if rd < 32 else f'f{rd - 32}'), None if sourced else val),)
                yield ('R', pc, insn, regs, tuple(stores), None if (insn & 0x7f) == 0x73 else fl)
            elif stub is not None and rd:
                stub[rd] = val
            stores = []
            raised = False
            sourced = False
        elif k == 'N':
            sourced = True
        elif k in ('E', 'I'):
            expect_pc = None        # a trap taken (not terminal): the next record is at the handler
        elif k == 'T':
            _, pc, cause, tval = line.split()
            pc = int(pc, 16)
            if expect_pc is not None and pc != expect_pc:
                raise ValueError(f'RTL trace: trap at {pc:#x} after a record whose successor was {expect_pc:#x}')
            yield ('T', int(cause, 16), pc, int(tval, 16), tuple(stores))
            return
        # V (vector) records do not occur in these programs; any other line is ignored


def same(x, y):
    """x (Spike) equals y (RTL), where a register value None in y (an N record: DUT-sourced) matches any."""
    if x is None or y is None or x[0] != y[0] or len(x) != len(y):
        return x == y
    if x[0] == 'R' and y[3] and y[3][0][1] is None:
        return x[:3] == y[:3] and x[4:] == y[4:] and bool(x[3]) and x[3][0][0] == y[3][0][0]
    if x[0] == 'R' and (x[2] & 0x707f) == 0x2073 and x[2] >> 20 == 0xf12 and x[:3] == y[:3] and x[4:] == y[4:]             and x[3] and y[3] and x[3][0][0] == y[3][0][0] and (x[3][0][1], y[3][0][1]) == (5, 0):
        return True    # marchid: Spike's is its registered 5, the lab cores' 0 (a known difference, csrr only)
    return x == y


def fmt(r):
    if r is None:
        return 'end of trace'
    if r[0] == 'T':
        return f'trap cause {r[1]} pc {r[2]:#x} tval {r[3]:#x}' + ''.join(f' st{w} {a:#x}={v:#x}' for a, v, w in r[4])
    _, pc, insn, regs, stores, fl = r
    return (f'{pc:#018x} ({insn:#010x}) ' + ' '.join(f'{n}={v:#x}' for n, v in regs) +
            ''.join(f' st{w} {a:#x}={v:#x}' for a, v, w in stores) + ('' if fl is None else f' fflags={fl:#x}'))


def lockstep(spike, elf, ram, fp, rtl_trace, skip, fflags0, limit, deadline, stub=None):
    """Compare the RTL trace with Spike's log streamed through a FIFO. Returns (outcome, count, message, end):
    outcome 'trap' (both ended with the same trap), 'limit' (`limit` records equal), or 'diff'/'error'."""
    with tempfile.TemporaryDirectory(prefix='spikelock-') as tmp:
        fifo = os.path.join(tmp, 'spike.log')
        os.mkfifo(fifo)
        proc = subprocess.Popen([spike, f'--isa={spike_isa(fp)}', '--priv=msu', '--pmpregions=0', '--triggers=0',
                                 f'-m{DRAM:#x}:{ram:#x},{SHIM:#x}:0x10000', '--log-commits', f'--log={fifo}', str(elf)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=open(os.path.join(tmp, 'spike.err'), 'wb'))
        expired = []

        def watchdog():
            expired.append(True)
            if proc.poll() is None:
                proc.kill()
            try:
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
        timer = threading.Timer(deadline, watchdog)
        timer.start()
        count, result = 0, None
        try:
            with open(fifo, errors='replace') as log, open(rtl_trace, errors='replace') as tr:
                s_it, r_it = spike_records(log), rtl_records(tr, skip, fflags0, stub)
                while True:
                    if limit is not None and count >= limit:
                        result = ('limit', count, f'{count} records equal (window of {limit})', None)
                        break
                    a, b = next(s_it, None), next(r_it, None)
                    if a is None or b is None or not same(a, b):
                        what = 'differs' if a is not None and b is not None else 'a log ended'
                        result = ('diff', count, f'{what} at record {count}: spike {fmt(a)}; rtl {fmt(b)}', None)
                        break
                    count += 1
                    if a[0] == 'T':
                        result = ('trap', count, f'{count} records equal, ending in {fmt(a)}', a)
                        break
        except ValueError as e:
            result = ('error', count, f'error at record {count}: {e}', None)
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        if expired:
            return 'error', count, f'deadline of {deadline:.0f} s reached after {count} equal records', None
        return result


# ---------------------------------------------------------------- the RTL run

# S1 negative controls (penv --rtl-priv --mutant NAME): one-line mutations of the CSR file or the core that the
# p-environment tests plus sim/cpu/sys/tests/s1_directed.S must catch. (file, old, new)
MUTANTS = {
    'csr-mret-mpie': ('csr', 'mpie_bit <= 1;', 'mpie_bit <= 0;'),
    'csr-mtvec-mode': ('csr', "12'h305: mtvec <= {wdata[63:2], 1'b0, wdata[0]};", "12'h305: mtvec <= {wdata[63:2], 2'b00};"),
    'csr-trap-mepc': ('csr', "mepc <= {trap_epc[63:2], 2'b00};", "mepc <= {trap_epc[63:2], 2'b00} + 64'd4;"),
    'csr-minstret-write': ('csr', "12'hb02: minstret <= wdata;", "12'hb02: minstret <= wdata + 64'd1;"),
    'core-ebreak-tval': ('core', 'exception_cause=3; exception_tval=pc;', 'exception_cause=3; exception_tval=0;'),
    'core-pair-store-epc': ('core', 'take_trap(pc2, 7, ea2s);', 'take_trap(pc, 7, ea2s);'),
}


def mutant_file(src, name, work):
    """A copy of src with MUTANTS[name] applied (its anchor must occur exactly once)."""
    _, old, new = MUTANTS[name]
    text = src.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'error: mutant {name}: anchor {old!r} occurs {text.count(old)} times in {src}')
    out = work / f'{name}-{src.name}'
    out.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    return out


class Core:
    def __init__(self, a, ram, fp, work):
        src = Path(a.core_source).resolve() if a.core_source else ROOT / CORES[a.core]
        if fp and 'RV64_OOO_FPU' not in src.read_text(encoding='utf-8'):
            raise SystemExit(f'error: {src.name} has no RV64_OOO_FPU option (F/D programs need --core ooo)')
        self.sim = simulator.get(a.sim)
        defines = (['WIDE_TRACE'] if a.core == 'ooo' else []) + (['RV64_OOO_FPU'] if fp else [])
        extra = []
        if getattr(a, 'rtl_priv', False):
            # S1: the privilege option (RV64_PRIV) and its CSR file
            defines.append('RV64_PRIV')
            extra = [Path(a.csr_source).resolve() if getattr(a, 'csr_source', None) else ROOT / 'rtl/cpu/rv64_csr.sv']
        if getattr(a, 'mutant', None):
            if MUTANTS[a.mutant][0] == 'csr':
                extra = [mutant_file(extra[0], a.mutant, work)]
            else:
                src = mutant_file(src, a.mutant, work)
        params = {'MEM_BYTES': ram, **{k: v for k, v in (('ICACHE_BEATS', a.icache_beats),
                                                          ('DCACHE_BEATS', a.dcache_beats)) if v}}
        self.src = src
        if getattr(a, 'mem_base', 0):
            params['MEM_BASE'] = f"64'h{a.mem_base:x}"
        self.exe = self.sim.build('tb_core', [*extra, src, ROOT / 'sim/cpu/tb_core.sv'], work / f'tb_core-{a.core}-{ram}.vvp',
                                  params=params, defines=defines, timeout=simulator.STEP_TIMEOUT)

    def trace(self, image_path, trace_path, stall, seed, max_retired=0, timeout=LIMIT, tohost=None):
        args = [*self.exe, f'+image_bin={image_path}', f'+trace={trace_path}', f'+stall={stall}', f'+seed={seed}',
                '+fault_kind=0', '+fault_addr=ffffffffffffffff', '+max_cycles=2000000000']
        if tohost is not None:
            args.append(f'+tohost={tohost:x}')
        if max_retired:
            args.append(f'+max_retired={max_retired}')
        # run() with a size cap on the trace, polled every 0.2 s
        trace_path = Path(trace_path)
        t_end = time.time() + timeout
        with tempfile.TemporaryFile('w+') as out:
            proc = subprocess.Popen([str(x) for x in args], stdout=out, stderr=subprocess.STDOUT, text=True)
            try:
                while proc.poll() is None:
                    try:
                        size = trace_path.stat().st_size
                    except FileNotFoundError:
                        size = 0
                    if size > TRACE_CAP:
                        raise RuntimeError(f'tb_core trace passed the {TRACE_CAP >> 20} MiB cap; run killed')
                    if time.time() > t_end:
                        raise subprocess.TimeoutExpired(args[0], timeout)
                    time.sleep(0.2)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                    trace_path.unlink(missing_ok=True)
            out.seek(0)
            text = out.read()
        if proc.returncode:
            raise RuntimeError(f'{Path(str(args[0])).name} rc={proc.returncode}: {text.strip()[-600:]}')
        return text


def spike_path(a):
    p = Path(a.spike) if a.spike else sysrt.third_party(ROOT, 'linux-lab') / 'build/spike/spike'
    if not p.is_file():
        raise SystemExit(f'error: no Spike at {p}; build it with sim/cpu/sys/build_spike.sh')
    return p


def check_one(a, core, spike, work, job, stall, seed, t_end):
    """One program: the RTL trace, then the streamed comparison and the job's end condition. (ok, n, msg)."""
    tag = job['tag']
    img = work / f'{tag}.bin'
    img.write_bytes(job['rtl_image'])
    trc = work / f'{tag}.trace'
    limit, skip = job['limit'], job['skip']
    core.trace(img, trc, stall, seed, max_retired=(skip + limit) if limit else 0,
               timeout=max(10.0, t_end - time.time()))
    shim_dir = work / tag
    shim_dir.mkdir(exist_ok=True)
    elf = shim_elf(shim_dir, job['spike_image'], job['regs'], job['pc'], job['fp'], job['fregs'], job['fcsr'], a.clang)
    stub = {} if skip else None
    outcome, n, msg, end = lockstep(spike, elf, len(job['spike_image']), job['fp'], trc, skip, job['fcsr'] & 0x1f,
                                    limit, max(10.0, t_end - time.time()), stub)
    ok = outcome in ('trap', 'limit')
    if ok and skip:
        # The restore stub must have loaded exactly the checkpoint's registers (and fcsr), as Spike starts with.
        want = {r: job['regs'][r] for r in range(1, 32)}
        if job['fp']:
            want.update({32 + r: job['fregs'][r] for r in range(32)})
        bad = [r for r, v in want.items() if stub.get(r) != v]
        if bad:
            ok, msg = False, f'{msg}; but the restore stub loaded different values into {bad[:6]}'
    if ok and job['end'] == 'window':
        # A checkpoint window: all `limit` records, unless the program itself ended (EBREAK) inside it.
        if not (outcome == 'limit' or (outcome == 'trap' and end[1] == 3)):
            ok, msg = False, f'{msg}; but the window ended early in a trap'
    elif ok and job['end'] == 'program':
        # A whole benchmark: it must end at its EBREAK (cause 3) or run the requested --max records.
        if not (outcome == 'trap' and end[1] == 3) and not (limit and outcome == 'limit'):
            ok, msg = False, f'{msg}; but the benchmark did not reach its EBREAK'
    elif ok and isinstance(job['end'], int):
        # A riscv-test: the lab environment's ECALL with gp = 1 and a0 = 0, or its expected trap;
        # agreeing with Spike on a failure is not a pass.
        last = {3: 0, 10: 0}
        for r in rtl_records(trc.read_text().splitlines()):
            if r[0] == 'R' and r[3] and r[3][0][0] in ('x3', 'x10'):
                last[int(r[3][0][0][1:])] = r[3][0][1]
        if outcome != 'trap' or end[1] != job['end'] or (job['end'] == 11 and (last[3], last[10]) != (1, 0)):
            ok, msg = False, f'{msg}; but the test did not pass (gp {last[3]}, a0 {last[10]})'
    if ok:
        trc.unlink()
        img.unlink()
        shutil.rmtree(shim_dir, ignore_errors=True)
    return ok, n, msg


def job(tag, image, end, spike_image=None, regs=None, pc=0, fp=False, fstate=None, skip=0, limit=None):
    fregs, fcsr = fstate if fstate else ([0] * 32, 0)
    return {'tag': tag, 'rtl_image': image, 'spike_image': spike_image if spike_image is not None else image,
            'regs': regs or [0] * 32, 'pc': pc, 'fp': fp, 'fregs': fregs, 'fcsr': fcsr, 'skip': skip,
            'limit': limit, 'end': end}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('rvt', 'image', 'pieces', 'penv', 'self-test'))
    ap.add_argument('suites', nargs='*')
    ap.add_argument('--core', choices=sorted(CORES), default='ooo')
    ap.add_argument('--core-source')
    ap.add_argument('--sim', choices=simulator.CHOICES, default='verilator')
    ap.add_argument('--fpu', action='store_true', help='F/D program (ooo core with RV64_OOO_FPU)')
    ap.add_argument('--icache-beats', type=int)
    ap.add_argument('--dcache-beats', type=int)
    ap.add_argument('--out-dir', type=Path, help='image/pieces: the build_bench.py folder (also gets the result)')
    ap.add_argument('--max', type=int, help='image: compare only the first N instructions')
    ap.add_argument('--pieces', type=int, default=3)
    ap.add_argument('--window', type=int, default=100_000)
    ap.add_argument('--total', type=int, help='pieces: program length in instructions (else measured by rv_iss)')
    ap.add_argument('--stalls', default='0,7',
                    help='tb_core wait patterns: rvt and pieces alternate them over the programs; image runs each')
    ap.add_argument('--spike')
    ap.add_argument('--clang', default='clang')
    ap.add_argument('--objcopy', default='llvm-objcopy')
    ap.add_argument('--deadline', type=float, default=LIMIT, help='seconds for the whole invocation')
    ap.add_argument('--isa', default='rv64im_zba_zbb_zbs_zicsr_zifencei_zicntr', help='penv: the ISA of Spike, '
                    'rv_iss and the test build')
    ap.add_argument('--priv', default='m', choices=('m', 'mu', 'msu'), help='penv: the privilege modes')
    ap.add_argument('--asm', action='append', default=[], help='penv: an extra M-mode program (its directory has '
                    's1.ld), compared with Spike like the riscv-tests')
    ap.add_argument('--rtl-priv', action='store_true', help='build the core with RV64_PRIV (S1) and rv64_csr.sv')
    ap.add_argument('--csr-source', help='a candidate rv64_csr.sv instead of rtl/cpu/rv64_csr.sv')
    ap.add_argument('--mutant', choices=sorted(MUTANTS), help='penv --rtl-priv: a negative control, one of the '
                    'built-in S1 mutations (the run must then FAIL)')
    ap.add_argument('--model', default='rtl', choices=('rtl', 'iss'),
                    help='penv: compare the RTL core (tb_core, MEM_BASE 0x8000_0000, +tohost) or rv_iss --sys')
    a = ap.parse_args()
    if a.mode == 'self-test':
        return self_test()
    if a.mutant and not (a.mode == 'penv' and a.rtl_priv and a.model == 'rtl'):
        raise SystemExit('error: --mutant needs penv --rtl-priv --model rtl')
    if a.mode == 'penv':
        return penv(a)
    t_end = time.time() + a.deadline
    stalls = [int(s) for s in a.stalls.split(',')]
    spike = spike_path(a)
    work = Path(tempfile.mkdtemp(prefix='spike-lockstep-', dir=os.environ.get('TMPDIR', '/tmp')))
    results, failed = [], []
    try:
        jobs = []
        if a.mode == 'rvt':
            # A worktree under build/ uses the enclosing checkout's fetched sources.
            os.environ.setdefault('RISCV_TESTS_DIR', str(sysrt.third_party(ROOT, 'riscv-tests-src')))
            import run_riscv_tests as rvt
            rvt.check_lock()
            fp = a.fpu
            for suite in a.suites:
                if (suite in rvt.FP_SUITES) != a.fpu:
                    raise SystemExit(f'error: {suite} {"needs" if a.fpu is False else "must not use"} --fpu')
                for name in rvt.tests_of(suite):
                    src = rvt.TESTS / 'isa' / suite / f'{name}.S'
                    image = rvt.build(src, rvt.MARCH[suite], a.fpu, work, f'{suite}-{name}', a.clang, a.objcopy)
                    trap = rvt.EXPECTED_TRAPS.get((suite, name))
                    jobs.append(job(f'{suite}-{name}', image, trap[0] if trap else 11, fp=a.fpu))
            ram = rvt.RAM
            plan = [(j, stalls[i % len(stalls)]) for i, j in enumerate(jobs)]
        else:
            if not a.out_dir:
                raise SystemExit('error: image/pieces need --out-dir BENCH_DIR')
            build = json.loads((a.out_dir / 'build.json').read_text())
            ram, fp = build['ram_bytes'], 'f' in build['isa'].split('_')[0][4:]
            if fp != a.fpu:
                raise SystemExit(f'error: {a.out_dir.name} is {build["isa"]}: {"add" if fp else "drop"} --fpu')
            image = (a.out_dir / 'bench.bin').read_bytes().ljust(ram, b'\0')
            if a.mode == 'image':
                jobs.append(job(a.out_dir.name, image, 'program', fp=fp, limit=a.max))
                plan = [(jobs[0], s) for s in stalls]
            else:
                jobs += pieces(a, build, ram, fp, work)
                plan = [(j, stalls[i % len(stalls)]) for i, j in enumerate(jobs)]
        core = Core(a, ram, fp, work)
        for i, (j, stall) in enumerate(plan):
            try:
                ok, n, msg = check_one(a, core, spike, work, j, stall, i + 1, t_end)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
                ok, n, msg = False, 0, f'error: {str(e)[-400:]}'
            results.append({'program': j['tag'], 'stall': stall, 'records': n, 'result': 'PASS' if ok else 'FAIL',
                            'note': msg})
            print(f'{"ok  " if ok else "FAIL"} {j["tag"]} (stall {stall}): {msg}', flush=True)
            if not ok:
                failed.append(j['tag'])
            if time.time() > t_end:
                failed.append('deadline')
                break
        total = sum(r['records'] for r in results)
        summary = {'core': a.core, 'core_source': str(core.src),
                   'core_sha256': hashlib.sha256(core.src.read_bytes()).hexdigest(), 'sim': a.sim,
                   'sim_version': core.sim.version(), 'spike': str(spike), 'spike_isa': spike_isa(fp), 'mode': a.mode,
                   'stalls': stalls, 'icache_beats': a.icache_beats, 'dcache_beats': a.dcache_beats,
                   'runs': len(results), 'records': total, 'failed': failed, 'results': results}
        if a.out_dir and a.mode != 'rvt':
            name = f'spike-lockstep-{a.mode}-{a.core}{"-" + str(a.icache_beats) if a.icache_beats else ""}.json'
            (a.out_dir / name).write_text(json.dumps(summary, indent=1) + '\n')
        if failed or not results:
            print(f'FAIL: spike-lockstep: {len(failed)} of {len(plan)} runs differ from Spike ({a.core} {a.sim}): '
                  f'{", ".join(failed[:8])}')
            return 1
        print(f'PASS: {total} records of {len(results)} runs equal in {a.core} ({a.sim}) and Spike '
              f'({spike_isa(fp)}; stalls {a.stalls}' + (f'; {a.icache_beats}-beat caches' if a.icache_beats else '') + ')')
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def self_test():
    """The adapter's conversions and the comparison on synthetic records (no simulator needed)."""
    spike = ['core   0: 3 0x00000000c0000000 (0x00000297) x5  0x00000000c0000000',
             'core   0: 3 0x00000000c0000040 (0x30200073) c768_mstatus 0x0000000a00000080',
             'core   0: 0 0x0000000000000000 (0x00100093) x1  0x0000000000000001',
             'core   0: 0 0x0000000000000004 (0x00108123) mem 0x0000000000000002 0x01',
             'core   0: 3 0x00000000c00000f0 (0x342022f3) x5  0x0000000000000008',
             'core   0: 3 0x00000000c00000f4 (0x34102373) x6  0x0000000000000008',
             'core   0: 3 0x00000000c00000f8 (0x343023f3) x7  0x0000000000000000']
    rtl = ['R 0000000000000000 00100093 01 0000000000000001 0000000000000004',
           'W 0000000000000000 0000000000010000 04',
           'R 0000000000000004 00108123 00 0000000000000000 0000000000000008',
           'T 0000000000000008 000000000000000b 0000000000000000']
    a, b = list(spike_records(spike)), list(rtl_records(rtl))
    checks = [('equal program and trap (ECALL from U maps to 11)', a == b and a[-1] == ('T', 11, 8, 0, ()))]

    def differs(lines):
        try:
            return list(rtl_records(lines)) != a
        except ValueError:
            return True
    checks.append(('store width difference found', differs([rtl[0], 'W 0000000000000000 0000000000010000 0c', *rtl[2:]])))
    checks.append(('store data difference found', differs([rtl[0], 'W 0000000000000000 0000000000020000 04', *rtl[2:]])))
    checks.append(('register value difference found',
                   differs([rtl[0].replace('01 0000000000000001', '01 0000000000000002'), *rtl[1:]])))
    checks.append(('wrong successor pc found', differs([rtl[0].replace(' 0000000000000004', ' 0000000000000008'), *rtl[1:]])))
    checks.append(('data without a destination found',
                   differs([*rtl[:2], rtl[2].replace('00 0000000000000000', '00 0000000000000005'), rtl[3]])))
    checks.append(('a store before the trap is not lost',
                   differs([*rtl[:3], 'W 0000000000000008 0000000000000001 01', rtl[3]])))
    checks.append(('flags raised only in the RTL found', differs([rtl[0], 'F 01', *rtl[1:]])))
    brk = [*rtl[:3], 'T 0000000000000008 0000000000000003 0000000000000000']
    sbrk = [*spike[:4], spike[4].replace('0x0000000000000008', '0x0000000000000003'), spike[5],
            spike[6].replace('0x0000000000000000', '0x0000000000000008')]
    checks.append(('EBREAK: Spike tval (the pc) dropped, lab tval 0', list(rtl_records(brk)) == list(spike_records(sbrk))))
    checks.append(('EBREAK: a non-zero lab tval found',
                   list(rtl_records([*brk[:3], 'T 0000000000000008 0000000000000003 0000000000000004']))
                   != list(spike_records(sbrk))))
    first = [*spike[:2], spike[4].replace('0x0000000000000008', '0x0000000000000003'), spike[5].replace(
        '0x0000000000000008', '0x0000000000000000'), spike[6]]
    checks.append(('a trap at the first instruction is seen', list(spike_records(first)) == [('T', 3, 0, 0, ())]))
    stub = {}
    skip = list(rtl_records(rtl, skip=1, stub=stub))
    checks.append(('stub records skipped and their writes kept', skip[0][1] == 4 and len(skip) == 2 and stub == {1: 1}))
    try:
        list(spike_records([*spike[:2], spike[2].replace('(0x00100093)', '(0x00100093') + ' junk']))
        checks.append(('unparsable Spike record is an error', False))
    except ValueError:
        checks.append(('unparsable Spike record is an error', True))
    failed = [n for n, ok in checks if not ok]
    if failed:
        print(f'FAIL: spike-lockstep self-test: {failed}')
        return 1
    print(f'PASS: spike-lockstep self-test, {len(checks)} checks')
    return 0


PENV_BASE = 0x80000000
PENV_RAM = 0x10000


def spike_penv_records(log):
    """Spike records of a p-environment program run directly (no shim): its boot ROM (below 0x8000_0000) is
    skipped; every later record is compared, the privilege field included."""
    for line in log:
        r = commit_compare.parse(line)
        if r is None:
            if line.startswith('core'):
                raise ValueError(f'unparsable Spike record {line.rstrip()!r}')
            continue
        prv, pc, insn, regs, _loads, stores = r
        if pc < PENV_BASE:
            continue
        m = FFLAGS.search(line)
        yield ('R', pc, insn, regs, stores, int(m[1], 16) if m and (insn & 0x7f) != 0x73 else None), prv


def adopt_check(iss, elf, trc, itrc, a):
    """The N-record path (mcycle counts the RTL's clocks): rv_iss --sys takes the RTL trace's N values for its
    mcycle reads (--adopt) and must then write the RTL's R, N, W and E records exactly, values included; rv_iss's
    own boot ROM below 0x8000_0000 is skipped. A failure raises RuntimeError."""
    run([iss, '--sys', '1', '--ram', str(PENV_RAM), '--elf', elf, '--isa', a.isa, '--priv', a.priv,
         '--trace', itrc, '--max', str(PENV_MAX), '--adopt', trc])

    def body(path):
        out = []
        for line in path.read_text().splitlines():
            k = line[:1]
            if k == 'R' and int(line.split()[1], 16) < PENV_BASE:
                continue
            if k in ('R', 'N', 'W', 'E'):
                out.append(line.lower())
        return out
    r, i = body(trc), body(itrc)
    for n, (x, y) in enumerate(zip(r, i)):
        if x != y:
            raise RuntimeError(f'rv_iss --adopt differs from the RTL trace at line {n}: rtl {x!r}; iss {y!r}')
    # The RTL may retire the instruction after the tohost store in the same clock (pairing), where rv_iss stops at
    # the store: a trailing `jal x0, 0` (the program's spin loop) is the only record allowed beyond rv_iss's end.
    while len(r) > len(i) and r[-1].split()[:1] == ['r'] and r[-1].split()[2] == '0000006f':
        r.pop()
    if len(r) != len(i):
        raise RuntimeError(f'rv_iss --adopt wrote {len(i)} records where the RTL trace has {len(r)} '
                           f'(rtl tail {r[len(i) - 1:len(i) + 2]!r}; iss tail {i[-2:]!r})')


def penv(a):
    """P0: riscv-tests in the official p environment (M-mode traps, linked at 0x8000_0000, HTIF tohost end) on a
    subset machine, compared with Spike configured the same (--isa, --priv). --model rtl runs tb_core with
    MEM_BASE 0x8000_0000 and +tohost (the RTL needs privilege, docket item 15, before these pass); --model iss
    runs rv_iss --sys with --isa/--priv and its trace instead, which validates this path today."""
    t_end = time.time() + a.deadline
    spike = spike_path(a)
    rt = HERE / 'sys'
    sys.path.insert(0, str(rt))
    import riscv_tests as srt
    work = Path(tempfile.mkdtemp(prefix='spike-penv-', dir=os.environ.get('TMPDIR', '/tmp')))
    failed, total, n_rec, passed = [], 0, 0, 0
    try:
        core = None
        if a.model == 'rtl':
            a.mem_base = PENV_BASE
            core = Core(a, PENV_RAM, 'f' in a.isa.split('_')[0][4:], work)
        iss = srt.build_iss()
        programs = [(s_, n_) for s_ in a.suites for n_ in srt.suite_tests(s_)] + [('asm', Path(f)) for f in a.asm]
        for suite, name in programs:
            if True:
                total += 1
                tag = f'{suite}-{name}' if suite != 'asm' else name.stem
                try:
                    if suite == 'asm':
                        elf = work / f'{tag}.elf'
                        run(['clang', '--target=riscv64-unknown-elf', f'-march={a.isa.replace("_zicntr", "")}',
                             '-mabi=lp64', '-mcmodel=medany', '-mno-relax', '-nostdlib', '-static', '-fuse-ld=lld',
                             f'-T{name.with_name("s1.ld")}', '-o', elf, name])
                    else:
                        elf = srt.build_test(suite, name, a.isa)
                    sym = run(['llvm-nm', elf])
                    tohost = int(next(l.split()[0] for l in sym.splitlines() if l.split()[-1] == 'tohost'), 16)
                    trc = work / f'{tag}.trace'
                    if core:
                        binf = work / f'{tag}.bin'
                        run([a.objcopy, '-O', 'binary', elf, binf])
                        data = binf.read_bytes()
                        if len(data) > PENV_RAM:
                            raise RuntimeError(f'{len(data)} bytes exceed {PENV_RAM}')
                        binf.write_bytes(data.ljust(PENV_RAM, b'\0'))
                        out = core.trace(binf, trc, 0, 1, max_retired=PENV_MAX,
                                         timeout=max(10.0, t_end - time.time()), tohost=tohost)
                        ended = 'TOHOST' in out
                        if not ended:
                            raise RuntimeError(f'tb_core stopped without a tohost write (the {PENV_MAX} instruction '
                                               f'budget or a halt): {out.strip()[-200:]}')
                        m = re.search(r'TOHOST value=([0-9a-f]+)', out)
                        value = int(m[1], 16) & 0xffffffff if m else None
                    else:
                        # the same platform as Spike's: 64 KiB of RAM at 0x8000_0000 and Spike's time model
                        res = json.loads(run([iss, '--sys', '1', '--ram', str(PENV_RAM), '--elf', elf, '--isa', a.isa,
                                              '--priv', a.priv, '--trace', trc, '--max', str(PENV_MAX), '--marchid', '5',
                                              '--time', 'spike']).strip().splitlines()[-1])
                        ended = res['stop'] == 'tohost'
                        value = res['exit_code'] & 0xffffffff
                    fifo = work / f'{tag}.fifo'
                    os.mkfifo(fifo)
                    proc = subprocess.Popen([spike, f'--isa={a.isa}', f'--priv={a.priv}', '--pmpregions=0', '--triggers=0',
                                             f'-m{PENV_BASE:#x}:{PENV_RAM:#x}', f'--instructions={PENV_MAX}', '--log-commits',
                                             f'--log={fifo}', str(elf)], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    count, msg = 0, None
                    expired = []

                    def watchdog(proc=proc, fifo=fifo):
                        expired.append(True)
                        if proc.poll() is None:
                            proc.kill()
                        try:
                            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
                        except OSError:
                            pass
                    timer = threading.Timer(max(10.0, min(120.0, t_end - time.time())), watchdog)
                    timer.start()
                    try:
                        with open(fifo, errors='replace') as log, open(trc) as tr:
                            s_it = spike_penv_records(log)
                            # rv_iss also logs its boot ROM (the RTL starts at MEM_BASE); the test starts at 0x8000_0000
                            for b in (r for r in rtl_records(tr) if r[0] != 'R' or r[1] >= PENV_BASE):
                                if b[0] == 'T':
                                    msg = f'the {a.model} run ended in a terminal trap: {fmt(b)}'
                                    break
                                x, prv = next(s_it, (None, None))
                                # The lab trace has no privilege field: compare the rest, and with --priv m require
                                # Spike to stay in M (a model or core can only be in M then).
                                if not same(x, b) or (a.priv == 'm' and prv != 3):
                                    msg = f'differs at record {count}: spike {fmt(x)} (priv {prv}); {a.model} {fmt(b)}'
                                    break
                                count += 1
                            for _ in log:      # let Spike run on to its own tohost exit
                                pass
                        rc = proc.wait(timeout=60)
                        # Spike's own verdict must agree: exit 0 for a pass, else the failing value's status
                        if msg is None and ended and rc != ((0 if value == 1 else value >> 1) & 0xff):
                            msg = f'{count} records equal, but Spike exited {rc} where the {a.model} wrote tohost {value:#x}'
                    finally:
                        timer.cancel()
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait()
                    if expired:
                        msg = f"deadline reached after {count} equal records"
                    if msg is None and not ended:
                        msg = f'{count} records equal, but the run did not end at tohost'
                    if msg is None and count == 0:
                        msg = 'no records'
                    if msg is None and core and a.rtl_priv:
                        # after Spike agrees: rv_iss must reproduce the RTL trace with its mcycle values adopted
                        adopt_check(iss, elf, trc, work / f'{tag}.iss.trace', a)
                except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired, StopIteration) as e:
                    count, msg, value = 0, f'error: {str(e)[-300:]}', None
                n_rec += count
                verdict = '' if msg else ('; the test passes' if value == 1 else f'; the test fails (tohost {value:#x}), as on Spike')
                passed += msg is None and value == 1
                print(f'{"ok  " if msg is None else "FAIL"} {tag}: ' + (msg or f'{count} records equal up to tohost{verdict}'),
                      flush=True)
                if msg:
                    failed.append(tag)
                if time.time() > t_end:
                    failed.append('deadline')
                    break
        if failed:
            print(f'FAIL: spike-lockstep: {len(failed)} of {total} p-environment tests differ from Spike '
                  f'({a.model}, {a.isa}, --priv {a.priv}): {", ".join(failed[:8])}')
            return 1
        print(f'PASS: {n_rec} records of {total} runs equal in {a.model} and Spike ({a.isa}, --priv {a.priv}, '
              f'p environment at 0x8000_0000, tohost end; {passed} tests pass, the rest fail identically on Spike)')
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def pieces(a, build, ram, fp, work):
    """Checkpoint windows: rv_iss states at K evenly spaced instruction indices, each restored on the core by
    bench_checkpoint's stub and on Spike by the shim. Spike gets the checkpoint's own memory, the core the
    same memory with the stub patched in, so a later read of a patched byte shows as a difference."""
    src = ROOT / 'sim/cpu/bench/rv_iss.c'
    iss = work / 'rv_iss'
    run(['clang', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', iss, src])
    fpo = ['--fp', '1'] if fp else []
    total = a.total
    if not total:
        total = json.loads(run([iss, '--ram', ram, '--image', a.out_dir / 'bench.bin', *fpo]))['instructions']
    at = [int(total * (k + 1) / (a.pieces + 1)) for k in range(a.pieces)]
    run([iss, '--ram', ram, '--image', a.out_dir / 'bench.bin', *fpo, '--max', at[-1] + 1, '--dump-at',
         ','.join(map(str, at)), '--dump-prefix', work / 'st-'])
    stub = build['mailbox_address'] - build['stack_reserve_bytes']
    jobs = []
    for idx in at:
        st = work / f'st-{idx}.state'
        regs, memory, pc, index = bench_checkpoint.read_iss_state(st)
        fstate = bench_checkpoint.read_iss_fstate(st) if fp else None
        original = bytes(memory)
        image, info = bench_checkpoint.build_from_state(regs, memory, pc, index, stub, fstate=fstate)
        st.unlink()
        jobs.append(job(f'{a.out_dir.name}@{idx}', image, 'window', spike_image=original, regs=regs, pc=pc, fp=fp,
                        fstate=fstate, skip=info['stub_instructions'], limit=a.window))
    return jobs


if __name__ == '__main__':
    sys.exit(main())
