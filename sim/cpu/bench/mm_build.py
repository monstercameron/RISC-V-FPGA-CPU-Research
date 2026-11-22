"""Build the mm benchmark (build_bench.py --benchmark mm).

The kernels (mm/mm_kernels.c), the driver (mm/mm_bench.c), the harness
(mm/mm_runtime.c) and the generated inputs (mm_data.S from mm/mm_export.sh, linked
with .incbin) are compiled for bare-metal RV64 like the rt build:
  rv64imb                       soft float: compiler-rt addsf3/mulsf3 and the integer conversion in the kernel
  rv64imfd_zba_zbb_zbs          hard float: run_bench.py --core ooo --fpu
Both use -ffp-contract=off, so every FP result is the unfused one the native reference computed.
--mm-variant names the kernel source: scalar is the only one today. A vector variant (mm_kernels_rvv.c,
defining the same functions, built only with --vector once the vector unit is released) adds an entry to
VARIANTS; no other file changes. The RAM size is the smallest power of two that holds the data and the
program (the full profile needs 32 MiB, so it has no hex files).
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import json
import re
import time

import build_bench as bb

MM_DIR = bb.BENCH / 'mm'
MM_DATA_DEFAULT = 'build/cpu/bench/mm-data/small'  # mm/mm_export.sh small
MM_ISAS = bb.ISAS[2:]
VARIANTS = {'scalar': [MM_DIR / 'mm_kernels.c']}  # later: 'rvv': [MM_DIR / 'mm_kernels_rvv.c'] (needs --vector)
MM_STACK_SLACK = 16 << 10
MM_PROGRAM_BYTES = 128 << 10  # program, soft-float builtins and BSS outputs, with room


def build(args, parser):
    if args.isa is None:
        args.isa = MM_ISAS[0]
    if args.isa not in MM_ISAS:
        parser.error('--benchmark mm needs rv64imb (soft float) or rv64imfd_zba_zbb_zbs')
    if args.runtime != 'reference':
        parser.error('--runtime applies to dhrystone only')
    data = (bb.ROOT / (args.mm_data or MM_DATA_DEFAULT)).resolve()
    for name in ('mm_data.S', 'expected.json', 'export.json'):
        if not (data / name).is_file():
            parser.error(f'{data / name} is missing: run sim/cpu/bench/mm/mm_export.sh first')
    export = json.loads((data / 'export.json').read_bytes())
    for name, digest in export['data_sha256'].items():
        if bb.sha(data / name) != digest:
            parser.error(f'{data / name} differs from the one mm_export.sh recorded')
    expected = json.loads((data / 'expected.json').read_bytes())
    rows = export['rows']
    data_bytes = sum((data / n).stat().st_size for n in export['data_sha256'] if n.endswith('.bin'))
    if args.ram_kib is None:
        need = data_bytes + MM_PROGRAM_BYTES + bb.STACK_RESERVE + bb.MAILBOX_BYTES + MM_STACK_SLACK
        args.ram_kib = next(k for k in bb.RAM_KIB if k >= 256 and k * 1024 >= need)
    if args.ram_kib not in bb.RAM_KIB:
        parser.error('--ram-kib must be a power of two from 32 to 65536')
    out = (bb.ROOT / (args.out_dir or f'build/cpu/bench/mm-{data.name}-{bb.isa_label(args.isa)}')).resolve()
    if not out.is_relative_to((bb.ROOT / 'build').resolve()):
        parser.error('--out-dir must be inside the repository build/ directory')
    for name, digest in bb.VENDOR_SHA256.items():
        if bb.sha(bb.VENDOR / name) != digest:
            raise SystemExit(f'Vendored {name} differs from its recorded upstream identity')
    soft = bb.abi_of(args.isa) == bb.ABI
    if soft:
        for name, digest in bb.RT_VENDOR_SHA256.items():
            if bb.sha(bb.RT_VENDOR / name) != digest:
                raise SystemExit(f'Vendored {name} differs from its recorded upstream identity')
    out.mkdir(parents=True, exist_ok=True)

    sources = [(p, 'port') for p in (MM_DIR / 'mm_bench.c', *VARIANTS[args.mm_variant], MM_DIR / 'mm_runtime.c')]
    sources.append((data / 'mm_data.S', 'data'))
    if soft:
        sources += [(bb.RT_VENDOR / name, 'vendor') for name in bb.RT_SOFT_FLOAT]
    ram_bytes = args.ram_kib * 1024
    mailbox = ram_bytes - bb.MAILBOX_BYTES
    program_limit = mailbox - bb.STACK_RESERVE
    linker = out / 'link.ld'
    linker.write_text(bb.LINKER_SCRIPT.format(ram_bytes=ram_bytes, mailbox=mailbox, program_limit=program_limit,
                                              extra=''), encoding='ascii', newline='\n')
    defines = ['-ffp-contract=off', '-fno-math-errno', f'-DMM_V1_ROWS={rows["v1"]}', f'-DMM_V3_ROWS={rows["v3"]}',
               f'-DMM_V4_ROWS={rows["v4"]}', f'-DMM_V1B_ROWS={rows["v1b"]}']
    common = [args.clang, '--target=riscv64-unknown-elf', f'-march={args.isa}', f'-mabi={bb.abi_of(args.isa)}',
              '-mcmodel=medany', '-msmall-data-limit=0', '-mno-relax', f'-{args.opt}',
              '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-common',
              '-nostdlibinc', '-I', bb.BENCH / 'include', '-I', MM_DIR, *defines]
    port_flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    started = time.perf_counter()
    commands, objects = [], []
    start_object = out / 'start.o'
    command = common + ['-c', bb.BENCH / 'start.S', '-o', start_object]
    bb.run(command, out / 'compile-start.log')
    commands.append([bb.shown(x) for x in command])
    for source, kind in sources:
        obj = out / (source.stem + '.o')
        if kind == 'vendor':
            flags = bb.BENCHMARKS['rt']['vendor_flags']
        elif kind == 'data':
            flags = ['-I', data]
        else:
            flags = port_flags
        command = common + flags + ['-c', source, '-o', obj]
        bb.run(command, out / f'compile-{source.stem}.log')
        commands.append([bb.shown(x) for x in command])
        objects.append(obj)
    elf, binary = out / 'bench.elf', out / 'bench.bin'
    command = [args.clang, '--target=riscv64-unknown-elf', f'-march={args.isa}', f'-mabi={bb.abi_of(args.isa)}',
               '-nostdlib', '-fuse-ld=lld', '-Wl,--no-relax', f'-Wl,-T,{linker}', start_object, *objects, '-o', elf]
    bb.run(command, out / 'link.log')
    commands.append([bb.shown(x) for x in command])
    bb.run([args.objcopy, '-O', 'binary', elf, binary])
    build_seconds = time.perf_counter() - started

    symbols, kinds = {}, {}
    for line in bb.run([args.nm, elf]).splitlines():
        match = re.match(r'^([0-9a-fA-F]+)\s+(\S)\s+(\S+)$', line)
        if match:
            symbols[match[3]] = int(match[1], 16)
            kinds[match[3]] = match[2]
    for required in ('_start', 'main', '__bss_start', '__bss_end', '__bench_mailbox', 'mm_bench_run', 'mm_gemm_i8',
                     'mm_gemv_q4', 'mm_g1_a', 'mm_v4_w'):
        if required not in symbols:
            raise RuntimeError(f'Missing symbol {required}')
    if symbols['__bench_mailbox'] != mailbox:
        raise RuntimeError('Linked mailbox address differs from the requested layout')
    (out / 'symbols.txt').write_text(''.join(f'{v:016x} {kinds[k]} {k}\n' for k, v in
                                             sorted(symbols.items(), key=lambda x: x[1])), encoding='ascii')
    if args.objdump:
        (out / 'bench.disasm.txt').write_text(bb.run([args.objdump, '-d', out / 'bench.elf']), encoding='utf-8')
        (out / 'sections.txt').write_text(bb.run([args.objdump, '-h', elf]), encoding='utf-8')
    payload = binary.read_bytes()
    if len(payload) > symbols['__bss_start']:
        raise RuntimeError('Binary image extends past the start of .bss')
    hex_images = ram_bytes <= bb.HEX_LIMIT_BYTES
    for name in ('bench-bytes.hex', 'bench-words.hex'):
        (out / name).unlink(missing_ok=True)
    if hex_images:
        image = payload.ljust(ram_bytes, b'\0')
        (out / 'bench-bytes.hex').write_text(''.join(f'{b:02x}\n' for b in image), encoding='ascii')
        (out / 'bench-words.hex').write_text(''.join(f'{int.from_bytes(image[i:i+8], "little"):016x}\n'
                                                     for i in range(0, ram_bytes, 8)), encoding='ascii')
    padded = payload.ljust(-(-len(payload) // 8) * 8, b'\0')
    (out / 'bench-words-be.bin').write_bytes(b''.join(padded[i:i + 8][::-1] for i in range(0, len(padded), 8)))
    images = ('bench-bytes.hex', 'bench-words.hex') if hex_images else ()

    inputs = [source for source, _ in sources if source.parent != data] + [bb.BENCH / 'start.S', Path(bb.__file__),
                                                                         Path(__file__), MM_DIR / 'mm_bench.h',
                                                                         data / 'mm_data.S', data / 'expected.json',
                                                                         data / 'export.json']
    inputs += sorted((bb.BENCH / 'include').glob('*.h')) + sorted(data.glob('*.bin'))
    inputs = list(dict.fromkeys(inputs))
    report = {
        'benchmark': 'mm',
        'compiler': bb.run([args.clang, '--version']).splitlines()[0],
        'isa': args.isa, 'abi': bb.abi_of(args.isa), 'optimization': args.opt, 'runtime': args.runtime,
        'mm': {'data_dir': data.relative_to(bb.ROOT).as_posix() if data.is_relative_to(bb.ROOT) else str(data),
               'profile': export['profile'], 'rows': rows, 'variant': args.mm_variant, 'export': export,
               'expected': expected, 'soft_float': soft, 'kernels': expected['kernels'],
               'data_bytes': data_bytes, 'free_bytes_below_reserved_stack': program_limit - symbols['__bss_end']},
        'hex_images': hex_images,
        'ram_bytes': ram_bytes, 'ram_words': ram_bytes // 8,
        'mailbox_address': mailbox, 'stack_top': mailbox, 'stack_reserve_bytes': bb.STACK_RESERVE,
        'payload_bytes': len(payload),
        'bss_bytes': symbols['__bss_end'] - symbols['__bss_start'],
        'program_end': symbols['__bss_end'],
        'build_wall_seconds': build_seconds,
        'commands': commands,
        'input_sha256': {p.relative_to(bb.ROOT).as_posix(): bb.sha(p) for p in inputs},
        'artifact_sha256': {name: bb.sha(out / name) for name in
                            ('link.ld', 'bench.elf', 'bench.bin', 'bench-words-be.bin', *images)},
    }
    (out / 'build.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'Built mm ({export["profile"]}, {args.mm_variant}, {"soft" if soft else "hard"} float): '
          f'{len(payload):,} bytes loaded, {report["bss_bytes"]:,} bytes .bss, '
          f'program ends at {symbols["__bss_end"]:#x} of {ram_bytes // 1024} KiB RAM.')
    print(f'Output: {out.relative_to(bb.ROOT).as_posix()}/')
