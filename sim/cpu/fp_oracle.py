"""Independent FP oracle: Berkeley TestFloat 3e against the F/D golden model, rv_iss.c and the RTL FPU.

TestFloat's testfloat_gen generates test cases (operands, the correctly rounded result and the exception
flags) from Berkeley SoftFloat 3e, which was written independently of this project. Release 3e has no RISC-V
specialization, so `build` derives one, `RISCV-lab`, from SoftFloat's `ARM-VFPv2-defaultNaN`. That
specialization already gives the default NaN 0x7fc00000 / 0x7ff8000000000000 for every NaN result, with no
payload propagation, invalid on signalling NaNs, and no traps. Two changes make it RISC-V: tininess is
detected after rounding, and a NaN converted to an integer gives the maximum positive value instead of 0.
Each vector becomes a RISC-V instruction (the four FMA forms come from f32/f64_mulAdd by negating operands)
and is checked on:
  - fp_ref_core.fp_compute (the Python golden model behind reference.py);
  - rv_iss.c's fp_exec (sim/cpu/bench/fp_oracle_iss.c), as --fp 1, --fp-soft 1 and, on AArch64, --host-fz 1;
  - the RTL's fp_decode and fp_exec, cut from rtl/cpu/rv64_ooo.sv and run under Verilator with the testbench
    of backend's fptest2.py, unless --no-rtl is given.
TestFloat has no min/max, classify, sign-injection or move functions, so the report lists those as not covered.

Usage (Linux or WSL):
  python3 sim/cpu/fp_oracle.py fetch      # bash sim/cpu/fetch_softfloat.sh (SHA-256 locked)
  python3 sim/cpu/fp_oracle.py build      # SoftFloat with RISCV-lab + testfloat_gen, in build/third-party
  python3 sim/cpu/fp_oracle.py run [--muladd-stride N] [--only FUNC ...] [--modes rne ...] [--no-rtl]
Exit status: 0 = every model agrees with TestFloat; 1 = a mismatch; 2 = setup failure (missing sources,
compiler or make).
SPDX-License-Identifier: MIT
"""
import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
SRC = ROOT / 'build/third-party/softfloat'
BLD = ROOT / 'build/third-party/softfloat-build'
OUT = ROOT / 'build/cpu/fp-oracle'
GEN = BLD / 'TestFloat-3e/build/Linux-x86_64-GCC/testfloat_gen'
VT = ROOT / 'build/third-party/verilator/root'

# RISCV-lab: SoftFloat 3e ARM-VFPv2-defaultNaN/specialize.h with these exact substitutions.
SPECIALIZE = [
    ('#define init_detectTininess softfloat_tininess_beforeRounding',
     '#define init_detectTininess softfloat_tininess_afterRounding'),
    ('#define ui32_fromNaN         0', '#define ui32_fromNaN         0xFFFFFFFF'),
    ('#define i32_fromNaN          0', '#define i32_fromNaN          0x7FFFFFFF'),
    ('#define ui64_fromNaN         0', '#define ui64_fromNaN         UINT64_C( 0xFFFFFFFFFFFFFFFF )'),
    ('#define i64_fromNaN          0', '#define i64_fromNaN          INT64_C( 0x7FFFFFFFFFFFFFFF )'),
]

MODES = [('rne', '-rnear_even', 0), ('rtz', '-rminMag', 1), ('rdn', '-rmin', 2), ('rup', '-rmax', 3),
         ('rmm', '-rnear_maxMag', 4)]
SIGN = {32: 0x80000000, 64: 0x8000000000000000}
REC = struct.Struct('<IB3xQQQQ')       # ins, frm, xa, fa, fb, fc  (input to fp_oracle_iss)
RES = struct.Struct('<bB6xQ')          # kind (-1 illegal, 0 x, 1 f), flags, value  (its output)
EXP = struct.Struct('<HBBQ')           # batch, expected f/x destination, expected flags, expected value


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw)


def tool_env():
    """PATH with make: the host's, or the one unpacked with the vendored Verilator."""
    return dict(os.environ, PATH=f'{os.environ["PATH"]}:{VT}/usr/bin', VERILATOR_ROOT=f'{VT}/usr/share/verilator',
                VERILATOR_BIN='../../../bin/verilator_bin')


def build():
    if not (SRC / 'SoftFloat-3e/source/ARM-VFPv2-defaultNaN/specialize.h').is_file():
        print('fp_oracle: SoftFloat/TestFloat sources missing: run `python3 sim/cpu/fp_oracle.py fetch` first')
        raise SystemExit(2)
    if BLD.exists():
        shutil.rmtree(BLD)
    BLD.mkdir(parents=True)
    for name in ('SoftFloat-3e', 'TestFloat-3e'):
        shutil.copytree(SRC / name, BLD / name)
    spec = BLD / 'SoftFloat-3e/source/RISCV-lab'
    shutil.copytree(BLD / 'SoftFloat-3e/source/ARM-VFPv2-defaultNaN', spec)
    text = (spec / 'specialize.h').read_text()
    for old, new in SPECIALIZE:
        if text.count(old) != 1:
            raise SystemExit(f'specialize.h: expected one "{old}"')
        text = text.replace(old, new)
    (spec / 'specialize.h').write_text(text)
    # The GCC makefiles call gcc; without gcc a shim runs clang.
    shim = BLD / 'bin'
    shim.mkdir()
    cc = shutil.which('gcc') or shutil.which('clang')
    if cc is None:
        print('fp_oracle build: no C compiler')
        raise SystemExit(2)
    (shim / 'gcc').write_text(f'#!/bin/sh\nexec {cc} "$@"\n')
    (shim / 'gcc').chmod(0o755)
    env = tool_env()
    env['PATH'] = f'{shim}:{env["PATH"]}'
    if not shutil.which('make', path=env['PATH']):
        print('fp_oracle build: no make on PATH')
        raise SystemExit(2)
    run(['make', '-C', BLD / 'SoftFloat-3e/build/Linux-x86_64-GCC', '-j', '3', 'SPECIALIZE_TYPE=RISCV-lab'],
        env=env, timeout=280)
    run(['make', '-C', BLD / 'TestFloat-3e/build/Linux-x86_64-GCC', '-j', '3', 'testfloat_gen',
         'TESTFLOAT_OPTS=-DFLOAT16 -DFLOAT64 -DEXTFLOAT80 -DFLOAT128 -DFLOAT_ROUND_ODD'], env=env, timeout=280)
    version = run([cc, '--version']).stdout.splitlines()[0]
    (BLD / 'BUILD.txt').write_text(f'SoftFloat 3e, specialization RISCV-lab (ARM-VFPv2-defaultNaN + {len(SPECIALIZE)} '
                                   f'substitutions in fp_oracle.py); TestFloat 3e testfloat_gen; compiler {version}\n')
    print(f'built {GEN} ({version})')


# ---- TestFloat functions and their RISC-V instructions ----------------------------------------------
def fop(f5, fmt, rs2=0, rm=0):
    return f5 << 27 | fmt << 25 | rs2 << 20 | 2 << 15 | rm << 12 | 1 << 7 | 0x53


def r4(op, fmt, rm):
    return 4 << 27 | fmt << 25 | 3 << 20 | 2 << 15 | rm << 12 | 1 << 7 | op


def functions():
    """[(TestFloat function, takes a rounding mode, [(instruction, ins(rm), operands(inputs) -> (xa, fa, fb, fc))])]."""
    out = []
    for w, fmt, t in ((32, 0, 'f32'), (64, 1, 'f64')):
        bx = 0xffffffff00000000 if w == 32 else 0            # NaN-boxing of single operands
        s = SIGN[w]
        sfx = '.s' if w == 32 else '.d'
        two = lambda i, bx=bx: (0, i[0] | bx, i[1] | bx, 0)
        for f5, nm in ((0, 'add'), (1, 'sub'), (2, 'mul'), (3, 'div')):
            out.append((f'{t}_{nm}', True, [(f'f{nm}{sfx}', lambda rm, f5=f5, fmt=fmt: fop(f5, fmt, 0, rm), two)]))
        out.append((f'{t}_sqrt', True, [(f'fsqrt{sfx}', lambda rm, fmt=fmt: fop(0x0b, fmt, 0, rm),
                                         lambda i, bx=bx: (0, i[0] | bx, 0, 0))]))
        out.append((f'{t}_mulAdd', True, [
            (f'fmadd{sfx}', lambda rm, fmt=fmt: r4(0x43, fmt, rm),
             lambda i, bx=bx: (0, i[0] | bx, i[1] | bx, i[2] | bx)),
            (f'fmsub{sfx}', lambda rm, fmt=fmt: r4(0x47, fmt, rm),                  # a*b + (-c)
             lambda i, bx=bx, s=s: (0, i[0] | bx, i[1] | bx, (i[2] ^ s) | bx)),
            (f'fnmsub{sfx}', lambda rm, fmt=fmt: r4(0x4b, fmt, rm),                 # (-a)*b + c
             lambda i, bx=bx, s=s: (0, (i[0] ^ s) | bx, i[1] | bx, i[2] | bx)),
            (f'fnmadd{sfx}', lambda rm, fmt=fmt: r4(0x4f, fmt, rm),                 # (-a)*b + (-c)
             lambda i, bx=bx, s=s: (0, (i[0] ^ s) | bx, i[1] | bx, (i[2] ^ s) | bx))]))
        for tf, k in (('eq', 2), ('le', 0), ('lt', 1)):
            out.append((f'{t}_{tf}', False, [(f'f{tf}{sfx}', lambda rm, k=k, fmt=fmt: fop(0x14, fmt, 0, k), two)]))
        for kind, it in enumerate(('i32', 'ui32', 'i64', 'ui64')):
            iname = ('w', 'wu', 'l', 'lu')[kind]
            out.append((f'{t}_to_{it}', True, [(f'fcvt.{iname}{sfx}', lambda rm, kind=kind, fmt=fmt: fop(0x18, fmt, kind, rm),
                                               lambda i, bx=bx: (0, i[0] | bx, 0, 0))]))
            out.append((f'{it}_to_{t}', True, [(f'fcvt{sfx}.{iname}', lambda rm, kind=kind, fmt=fmt: fop(0x1a, fmt, kind, rm),
                                               lambda i: (i[0], 0, 0, 0))]))
    out.append(('f32_to_f64', True, [('fcvt.d.s', lambda rm: fop(8, 1, 0, rm), lambda i: (0, i[0] | 0xffffffff00000000, 0, 0))]))
    out.append(('f64_to_f32', True, [('fcvt.s.d', lambda rm: fop(8, 0, 1, rm), lambda i: (0, i[0], 0, 0))]))
    return out


def result_kind(name):
    if name.startswith(('feq', 'flt', 'fle')):
        return 'bool'
    if name.startswith(('fcvt.w.', 'fcvt.wu.')):
        return 'int32'
    if name.startswith(('fcvt.l.', 'fcvt.lu.')):
        return 'int64'
    if name.startswith('fcvt.d.'):
        return 'f64'
    if name.startswith('fcvt.s.'):
        return 'f32'
    return 'f32' if name.endswith('.s') else 'f64'


def expected_value(kind, r):
    """TestFloat's result as the 64-bit register value RISC-V writes (singles boxed, 32-bit ints sign-extended)."""
    if kind == 'f32':
        return r | 0xffffffff00000000
    if kind == 'int32':
        return r | 0xffffffff00000000 if r >> 31 else r
    return r


def generate(args, tmp):
    """Stream every vector through the Python model and write the C and RTL inputs and the expectations.

    Returns (count per (instruction, mode), batch names, Python mismatches)."""
    from fp_ref_core import fp_compute
    per, batches, bad = {}, [], []
    rec, exp = open(tmp / 'vec.bin', 'wb'), open(tmp / 'exp.bin', 'wb')
    hexf = None if args.no_rtl else open(tmp / 'vec.hex', 'w')
    for func, rounding, insts in functions():
        if args.only and func not in args.only:
            continue
        for mname, mopt, rm in (MODES if rounding else [('-', '-rnear_even', 0)]):
            if args.modes and rounding and mname not in args.modes:
                continue
            cmd = [str(GEN), '-tininessafter', mopt]
            if func.split('_to_')[-1] in ('i32', 'ui32', 'i64', 'ui64'):
                cmd.append('-exact')                                  # FCVT to an integer raises NX
            stride = args.muladd_stride if 'mulAdd' in func else 1
            gen = subprocess.Popen(cmd + [func], stdout=subprocess.PIPE)
            if stride > 1:      # every Nth case, picked by awk at C speed
                pick = subprocess.Popen(['awk', f'NR % {stride} == {(args.muladd_offset + 1) % stride}'],
                                        stdin=gen.stdout, stdout=subprocess.PIPE)
                gen.stdout.close()
                lines = pick.communicate()[0].decode().split('\n')
            else:
                lines = gen.communicate()[0].decode().split('\n')
            if gen.wait():
                raise SystemExit(f'testfloat_gen failed: {cmd}')
            parsed = [[int(x, 16) for x in line.split()] for line in lines if len(line.split()) >= 3]
            for name, insf, opf in insts:
                ins = insf(rm)
                kind = result_kind(name)
                tof = int(kind not in ('bool', 'int32', 'int64'))
                batch = len(batches)
                batches.append(f'{name} {mname}')
                for vals in parsed:
                    xa, fa, fb, fc = opf(vals[:-2])
                    want, wfl = expected_value(kind, vals[-2]), vals[-1]
                    r = fp_compute(ins, xa, fa, fb, fc, 0)
                    if r is None or r[2] != want or r[3] != wfl or int(r[1]) != tof:
                        bad.append((len(batches) - 1, (name, mname, ins, xa, fa, fb, fc, want, wfl),
                                    'illegal' if r is None else f'{r[2]:016x}/{r[3]:02x}'))
                    rec.write(REC.pack(ins, 0, xa, fa, fb, fc))
                    exp.write(EXP.pack(batch, tof, wfl, want))
                    if hexf:
                        hexf.write(f'{ins:08x} {xa:016x} {fa:016x} {fb:016x} {fc:016x} 0\n')
                per[(name, mname)] = len(parsed)
    rec.close(); exp.close()
    if hexf:
        hexf.close()
    return per, batches, bad


def expectations(tmp):
    return EXP.iter_unpack((tmp / 'exp.bin').read_bytes())


def describe(tmp, index, batches, got):
    v = REC.unpack_from((tmp / 'vec.bin').read_bytes(), index * REC.size)
    b, tof, wfl, want = EXP.unpack_from((tmp / 'exp.bin').read_bytes(), index * EXP.size)
    return (f'{batches[b]} ins={v[0]:08x} xa={v[2]:016x} fa={v[3]:016x} fb={v[4]:016x} fc={v[5]:016x} '
            f'want={want:016x}/{wfl:02x} got={got}')


def check_iss(tmp, extra):
    exe = tmp / 'fp_oracle_iss'
    if not exe.exists():
        cc = shutil.which('clang') or shutil.which('gcc') or shutil.which('cc')
        run([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', HERE / 'bench',
             '-o', exe, HERE / 'bench/fp_oracle_iss.c'], timeout=120)
    run([exe, tmp / 'vec.bin', tmp / 'res.bin', *extra], timeout=250)
    bad = []
    data = (tmp / 'res.bin').read_bytes()
    total = os.path.getsize(tmp / 'exp.bin') // EXP.size
    if len(data) != total * RES.size:
        return [(0, 0, f'result file has {len(data) // RES.size} records, expected {total}')] * max(1, total)
    res = RES.iter_unpack(data)
    for k, ((b, tof, wfl, want), (kind, fl, val)) in enumerate(zip(expectations(tmp), res)):
        if kind != tof or val != want or fl != wfl:
            bad.append((b, k, f'{val:016x}/{fl:02x}' + (' illegal' if kind < 0 else '')))
    return bad


def rtl_functions():
    """fp_exec, fp_decode and their helpers, cut from the released core between these markers."""
    src = (ROOT / 'rtl/cpu/rv64_ooo.sv').read_text()
    start = src.index('    localparam [4:0] FOP_ADD')
    dec = src.index('function automatic [20:0] fp_decode')
    return src[start:src.index('endfunction', dec) + len('endfunction')]


def check_rtl(tmp):
    env = tool_env()
    if not shutil.which('verilator', path=env['PATH']):
        return None
    (tmp / 'fpfuncs.svh').write_text(rtl_functions())
    # The testbench of backend's fptest2.py (build/cpu/ooo-debug/council/backend/fp), with the functions cut
    # from the released RTL instead of backend's copies.
    tb = f'''`timescale 1ns/1ps
module tb_fpd;
    localparam integer FPU = 1;
`include "{tmp}/fpfuncs.svh"
    integer fd, fo, r, frm; reg [31:0] ins; reg [63:0] xa, fa, fb, fc, a; reg [68:0] y; reg [20:0] dc; reg [2:0] rm;
    initial begin
        fd = $fopen("{tmp}/vec.hex", "r"); fo = $fopen("{tmp}/sv.out", "w");
        while (!$feof(fd)) begin
            r = $fscanf(fd, "%h %h %h %h %h %h\\n", ins, xa, fa, fb, fc, frm);
            if (r == 6) begin
                dc = fp_decode(ins);
                rm = dc[11:9] == 3'd7 ? frm[2:0] : dc[11:9];
                if (!dc[0] || dc[2:1] != 0 || (dc[20] && rm > 3'd4)) $fdisplay(fo, "ILL");
                else begin
                    a = dc[14] ? fa : xa;
                    y = fp_exec(dc[7:3], dc[8], rm, a, fb, fc);
                    $fdisplay(fo, "%0d %016h %02h", dc[19], y[63:0], y[68:64]);
                end
            end
        end
        $fclose(fo); $finish;
    end
endmodule
'''
    (tmp / 'tb_fpd.sv').write_text(tb)
    obj = tmp / 'obj'
    run(['verilator', '--cc', '--exe', '--main', '--timing', '-Wno-fatal', '-Wno-lint', '-Wno-style', '--top-module',
         'tb_fpd', '-Mdir', obj, tmp / 'tb_fpd.sv'], env=env, cwd=tmp, timeout=280)
    run(['make', '-C', obj, '-f', 'Vtb_fpd.mk', '-j', '3', 'CXX=clang++', 'LINK=clang++', 'CFG_CXXFLAGS_STD=-std=gnu++20',
         'CFG_CXXFLAGS_COROUTINES=', 'OPT_FAST=-O1'], env=env, timeout=280)
    run([obj / 'Vtb_fpd'], cwd=tmp, timeout=280)
    bad = []
    lines = (tmp / 'sv.out').read_text().split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    total = os.path.getsize(tmp / 'exp.bin') // EXP.size
    if len(lines) != total:
        return [(0, 0, f'testbench wrote {len(lines)} results, expected {total}')] * max(1, total)
    for k, ((b, tof, wfl, want), line) in enumerate(zip(expectations(tmp), lines)):
        if line.strip() != f'{tof} {want:016x} {wfl:02x}':
            bad.append((b, k, line.strip()))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('action', choices=('fetch', 'build', 'run'))
    ap.add_argument('--muladd-stride', type=int, default=60,
                    help='use every Nth f32/f64_mulAdd level-1 case (6,133,248 per mode); 1 = all (split with --only/--modes)')
    ap.add_argument('--muladd-offset', type=int, default=0,
                    help='which of the --muladd-stride residue classes to take (0..stride-1): stride 4 with offsets '
                         '0-3 covers all of level 1 in four runs per function and mode')
    ap.add_argument('--only', nargs='*', help='TestFloat functions to run (default: all)')
    ap.add_argument('--modes', nargs='*', help='rounding modes to run: rne rtz rdn rup rmm (default: all)')
    ap.add_argument('--no-rtl', action='store_true', help='skip the RTL fp_exec check')
    ap.add_argument('--json', type=Path, help='report file (default build/cpu/fp-oracle/report.json)')
    args = ap.parse_args()
    if args.action == 'fetch':
        sys.exit(subprocess.run(['bash', str(HERE / 'fetch_softfloat.sh')]).returncode)
    if args.action == 'build':
        build()
        return
    started = time.time()
    if not GEN.is_file():
        build()
    OUT.mkdir(parents=True, exist_ok=True)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix='fp-oracle-'))       # a local file system (not /mnt/c) for the vector files
    per, batches, pybad = generate(args, tmp)
    total = os.path.getsize(tmp / 'exp.bin') // EXP.size
    t_gen = time.time() - started
    results = {'python fp_ref_core': pybad}
    results['rv_iss --fp 1'] = check_iss(tmp, [])
    results['rv_iss --fp-soft 1'] = check_iss(tmp, ['--fp-soft'])
    if platform.machine() in ('aarch64', 'arm64'):
        results['rv_iss --host-fz 1'] = check_iss(tmp, ['--host-fz'])
    if not args.no_rtl:
        rtl = check_rtl(tmp)
        if rtl is None:
            print('fp_oracle: Verilator not found; RTL check skipped')
        else:
            results['RTL fp_exec (Verilator)'] = rtl
    matrix = {}
    for (name, mode), n in per.items():
        matrix.setdefault(name, {})[mode] = n
    report = {'tool': 'TestFloat 3e testfloat_gen -tininessafter, level 1 (SoftFloat 3e, specialization RISCV-lab)',
              'mulAdd_sample_stride': args.muladd_stride, 'mulAdd_sample_offset': args.muladd_offset, 'vectors': total, 'per_op_mode': matrix,
              'not_covered_by_testfloat': ['fmin', 'fmax', 'fclass', 'fsgnj', 'fsgnjn', 'fsgnjx', 'fmv', 'flw/fld/fsw/fsd',
                                           'NaN-boxing of inputs', 'invalid encodings and rounding modes', 'DYN'],
              'models': {}}
    print(f'{"instruction":12s} ' + ' '.join(f'{m:>8s}' for m, _, _ in MODES))
    for name, modes in matrix.items():
        if '-' in modes:
            print(f'{name:12s} {modes["-"]:>8,}   (no rounding mode)')
        else:
            print(f'{name:12s} ' + ' '.join(f'{modes[m]:>8,}' if m in modes else f'{"":>8s}' for m, _, _ in MODES))
    status = 0
    for model, bad in results.items():
        per_bad, first = {}, []
        for b, k, got in bad:
            per_bad[batches[b]] = per_bad.get(batches[b], 0) + 1
            if len(first) < 10:
                if isinstance(k, tuple):
                    v = k
                    first.append(f'{v[0]} {v[1]} ins={v[2]:08x} xa={v[3]:016x} fa={v[4]:016x} fb={v[5]:016x} '
                                 f'fc={v[6]:016x} want={v[7]:016x}/{v[8]:02x} got={got}')
                else:
                    first.append(describe(tmp, k, batches, got))
        report['models'][model] = {'mismatches': len(bad), 'by_op_mode': per_bad, 'first': first}
        status |= bool(bad)
        print(f'{model:26s} {total - len(bad):>10,} / {total:,} agree with TestFloat'
              + (f'  MISMATCHES {len(bad)}: ' + ', '.join(f'{key} {n}' for key, n in sorted(per_bad.items())[:8])
                 if bad else ''))
        for line in first[:5]:
            print('   ', line)
    report['seconds'] = round(time.time() - started, 1)
    report['generate_and_python_seconds'] = round(t_gen, 1)
    (args.json or OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    shutil.rmtree(tmp, ignore_errors=True)
    print(f'{"PASS" if not status else "FAIL"}: {total:,} TestFloat vectors, {len(matrix)} instructions, '
          f'{report["seconds"]} s; report {args.json or OUT / "report.json"}')
    sys.exit(1 if status else 0)


if __name__ == '__main__':
    main()
