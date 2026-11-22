"""Build a bare-metal benchmark for the RV64I core with LLVM.

Compiles each source file separately (Dhrystone's ground rules forbid merging
procedures across files), links with a generated linker script for the chosen
RAM size, and writes the images the testbenches load. Runs on Windows with the
installed LLVM or on Linux with clang, lld and llvm tools on PATH.

Benchmarks: dhrystone (riscv-tests edition), lzma, a scaled-down 7-Zip
LZMA benchmark kernel (lzma_bench.c with the LZMA SDK in vendor/lzma/), and rt,
the ray-tracing benchmark (RT-T BVH traversal and RT-P smallpt; rt_bench.c).
The rt build takes its scene, BVH and rays from an rt_export.sh output directory
(--rt-data); with rv64imb it links the compiler-rt soft-float builtins in
vendor/compiler-rt/, and rv64imfd_zba_zbb_zbs (lp64d) is for the F/D core (0.17.0). The
lzma build needs the M extension; --lzma-dict-log sets its dictionary (data =
dictionary + 1/64, so 22 is the 7z b -md22 shape, 4 MiB + 64 KiB) and the RAM
defaults to the smallest power of two that holds the estimated arena (1 MiB for
the 4 KiB dictionary, 64 MiB for 4 MiB). Images above 4 MiB of RAM get no hex
files: the runners load bench.bin (tb_core +image_bin) and bench-words-be.bin
(tb_bench +image_bin) instead.

js is the JavaScript benchmark: QuickJS-ng v0.18.0 (MIT, fetched by js/fetch_quickjs.sh into the
ignored build/third-party/quickjs-ng and checked file by file against QUICKJS_SHA256), the
original shim libc, harness and kernels in js/, and the script kernels.js embedded as js_src.h.
It takes its scale and expected output from a js_native.sh reference directory (--js-ref); the
generated script must be byte-identical to the one the native build ran. 32 MiB of RAM: the
shim heap runs from .bss to __heap_end, 1 MiB below the mailbox, and the stack takes that MiB.
rv64imb links the compiler-rt soft-float builtins, as rt does; rv64imfd_zba_zbb_zbs needs the
F/D core (run_bench.py --core ooo --fpu).
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / 'sim/cpu/bench'
VENDOR = BENCH / 'vendor/dhrystone'
ISAS = ('rv64i_zifencei', 'rv64im_zifencei', 'rv64im_zba_zbb_zbs_zifencei',  # M needs 0.4.0+, B needs 0.6.0+
        'rv64imfd_zba_zbb_zbs_zifencei')  # F and D: --core ooo --fpu (RV64_OOO_FPU, 0.17.0); rt, js and mm
ABI = 'lp64'


def abi_of(isa):
    """lp64d when the ISA has the F and D extensions (hardware floating-point arguments), else lp64."""
    return 'lp64d' if isa.split('_')[0].endswith('fd') else ABI


def isa_label(isa):
    """Short name for folders and records: rv64i, rv64im, rv64imb (Zba, Zbb and Zbs)."""
    return isa.split('_')[0] + ('b' if '_zbb' in isa else '')
MAILBOX_BYTES = 256
STACK_RESERVE = 8192
RAM_KIB = tuple(1 << n for n in range(5, 17))  # 32 KiB to 64 MiB
HEX_LIMIT_BYTES = 4 << 20  # larger RAM images are written only as binaries
LZMA_DICT_LOGS = range(12, 23)  # 4 KiB (the LZMA minimum) to 4 MiB (7z b -md22)


def lzma_arena_estimate(dict_log):
    """Upper estimate of lzma_bench.c's arena for a 2^dict_log dictionary (bytes).

    BT4 son table 8 x (dictionary + 1), the hash (half the dictionary, at least 64 Ki
    entries, plus 66,560 fixed entries, 4 bytes each), the match-finder window (about
    1.5 x dictionary), data, packed buffer and output, and 1 MiB for the encoder and
    decoder state. Checked against the native build's measured arena on 2026-11-21:
    1.97x at 2^12, 1.05x at 2^20, 1.013x at 2^22, never below 1.
    """
    d = 1 << dict_log
    data = d + d // 64
    capacity = data + data // 16 + 1024
    hash_entries = max(d // 2, 1 << 16) + 66560
    return 8 * (d + 1) + 4 * hash_entries + d + d // 2 + (1 << 16) + 2 * data + capacity + (1 << 20)

# Upstream identities from vendor/dhrystone/SOURCE.txt; a mismatch stops the build.
VENDOR_SHA256 = {
    'dhrystone.c': '11eb8a10d14d4a0b2e087f7d5e9ab67f76b1e9b1fd682457b5ed3ac1e7534e97',
    'dhrystone.h': 'a66aa6e73b38afb85021b2ac751402c8b27d47e48beffed852afb36aa94a2af5',
    'dhrystone_main.c': '45f1aeb092b50ccbd2f37782e5b054b446c93c49771a45a36c940386f72d338d',
}

# LZMA SDK files from 7-Zip 26.06; vendor/lzma/SOURCE.txt records them.
LZMA_VENDOR = BENCH / 'vendor/lzma'
LZMA_VENDOR_SHA256 = {
    '7zTypes.h': 'a5d03b8cb65cd3a2a56bde46dd68fb356d2ebacd9d70283e7d4d20b4e0a64713',
    'Compiler.h': 'd5e42be77d26beaa8c81d3e62ef99fc5685736cfc079779fdb9154d05fa8bc4a',
    'CpuArch.h': '259145c6f4b085f44284014574f39f3f562fc78466746bfb388efe06b4dd59b4',
    'LzFind.c': 'f73da68845094a85b006a0d2da80b3ecdec92a1ca0f85df637e565c642e8d5ba',
    'LzFind.h': '42732b38df9bb18f82866d7deaa8663f6c6f9cb10e2a2cdfa9e6f420c2e2f239',
    'LzHash.h': '42d146d2130dfe49d0b21d15cc6f0fe9d79ac0ebb629985fe3aedde7b2bee80e',
    'LzmaDec.c': '4e6ec665a6df01f1722e2b2fc36dc5e3aa7c3890e0f8cb11c6a07c9a01f3309b',
    'LzmaDec.h': '3aaf07b4ae4173a2d103179455dc7089b5ddbc7fc3db3c0e40964a7499c69266',
    'LzmaEnc.c': '67f23656339b5e19015acac41acbcf36ea7787a8419907dce91c1dd336a2fb0f',
    'LzmaEnc.h': 'c5e78398309363dd181840b7ba0bcb856f66619f755d5e2f5e04f7437186ba5f',
    'Precomp.h': 'c8903f2e36a771a272d8981e1e9ffed5ba16ca3d2f3dca6d1414d2340a6829d0',
}
LZMA_ISAS = ISAS[1:3]  # the kernel multiplies; no software helpers are linked

# Ray-tracing benchmark (rt): compiler-rt soft-float builtins from LLVM 23.1.5, linked
# into the rv64imb build only; vendor/compiler-rt/SOURCE.txt records them.
RT_VENDOR = BENCH / 'vendor/compiler-rt'
RT_ISAS = ISAS[2:]
RT_SOFT_FLOAT = ('adddf3.c', 'addsf3.c', 'subdf3.c', 'subsf3.c', 'muldf3.c', 'mulsf3.c', 'divdf3.c', 'divsf3.c',
                 'comparedf2.c', 'comparesf2.c', 'extendsfdf2.c', 'fixdfdi.c', 'floatdidf.c', 'floatsidf.c',
                 'floatundidf.c', 'floatunsidf.c', 'fp_mode.c')
RT_VENDOR_SHA256 = {
    'adddf3.c': 'c948665a4272f7155fd0cd51c3f2bb218bfd0d1dc0ab556565ee1a4eb315eb26',
    'addsf3.c': 'c462bb5e45cf6181b2803633328e2e33c1bd5e4bff7a766f057361ef88ba2c45',
    'comparedf2.c': 'c2af3f6a5ae89c08e5ee25b3ec03170b7e98d5dc699646c14820e359cd54fde5',
    'comparesf2.c': 'c24e84f8b8800e994b457dce12089ce14b693c839be5bbe74d53080aaa9597f0',
    'divdf3.c': '2c8850a107c4ab79d518d1c3246ff936dd28446c82e17c1f347717a36b7a88a8',
    'divsf3.c': '07fa9c2ac2fa467c8bcd8678ea5dae4ddafade06e6c2429eea9513b775fac2f1',
    'extendsfdf2.c': '0da160f7dcf46bf7d54a688a21477db5dfcb7147ad62e74895e00ea9778d78bf',
    'fixdfdi.c': '5542e35a576e96c17e5c9731ffa24f72cedc7369d18079d8c29c5df6702feb94',
    'floatdidf.c': 'aa8abfb4f802a359b220b4a5edcd494aa484e7ece129c9e8036143f5913e8783',
    'floatsidf.c': 'd5141b5b7e860113c75f2d03d0cf39ca41aeea3e75390c40f73979c4ac172b51',
    'floatundidf.c': '052bbd24835e69cfa03dc9c820f5022893dd69c2f8b9d9e6fe4187bb8773d28b',
    'floatunsidf.c': '9f3593197c2584c14c86a4760051be18c788d0835cf8ffdb9f11834c2ce9bf5b',
    'fp_add_impl.inc': 'd6fa6e3c97cdd0dde376e73711c7ec22a2e0b3aa6bbda310944eeb44fd0821ee',
    'fp_compare_impl.inc': 'e4693520d2eb36ff6af00ea405299cb1ba30b1375d6f2a5ab37911d9908d3366',
    'fp_div_impl.inc': '2d1d901e87805e0bb2f3a3ab951b29224a59a761d6f292c3bd86f35368186fdd',
    'fp_extend.h': 'b3da60a65ab5aca4b93ddd36df8af90051912d1c455c4cea2de0e50ce37c526d',
    'fp_extend_impl.inc': '63f9cd801c0c2a04e8becbd22f189eaaa47b5466bc098acc214fe69fd525f92a',
    'fp_fixint_impl.inc': '9f783582b31c028721a14561f2c5741b5bb19befa557a4575e1436381f966f4e',
    'fp_lib.h': 'cf3a5301c95986a9b392edba32dfe7ac27d3352d266e284e528a09413f84f6cc',
    'fp_mode.c': '0f626fefe2e19854549dfe598bd168a770bae7e1cab34b459871fabec4632f25',
    'fp_mode.h': '874aa9eee8990ae2a6f48127ddb48c3198a8fa741f634f93053ebac3f89e1e83',
    'fp_mul_impl.inc': '5fd5ec9eaf57c983ed521f3501346660221d6f2d49d48d186b2046702b54d8c3',
    'int_endianness.h': 'ec5175561075845b7b16a92ad5ecdfd42a284de2736dd07e4ca7011b75c37709',
    'int_lib.h': 'a5735bf1bfacecd6cf5785ed19ae62a981ff2f0923c38caa99f4af47f2be57b5',
    'int_math.h': 'ddc3abe104d4500630174d7e0c3190d203c968213eb189097f70aec55a33c352',
    'int_to_fp.h': '9ac8fd0650f1560e6c910979e0004c5956ae7da6e3bded7eab0b0270c51bf400',
    'int_to_fp_impl.inc': 'cc90f8dd3dc5649426463202a35c894b81189103f8b580e0b6af85658993b0f8',
    'int_types.h': '198552b25faf8a75b077ea145591cd7f6762b7f2712321b18f5e38fee8cc2a1e',
    'int_util.h': '63d06198ab720a75c20bfd84be895c2746581b129168bae6201e7384bbb0473b',
    'muldf3.c': 'e35d748cefd466cb17e4d0fd4ef9d92e0911fea97bb7a59ad138479ba9c0d553',
    'mulsf3.c': '9d93ec3313c62db3244c09827a4b27949caf94d2bcaf9ea616d8f5521eee799d',
    'subdf3.c': '201404b61436f1f617221ac20aeee67e41349baaf13ef838f0f5969e3b8b86ab',
    'subsf3.c': '5a908db14744b02835c6ccc254772d88ac229951830007cfed0a18d1e1d94db5',
}
# JavaScript benchmark (js): QuickJS-ng v0.18.0, github.com/quickjs-ng/quickjs tag v0.18.0, commit
# d7215b0ad3fc2c562e8317fd9bca058fd4863804, MIT; archive SHA-256
# 28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd (js/fetch_quickjs.sh). Not vendored:
# every file the build compiles or includes is locked here, and a mismatch stops the build.
QUICKJS_DIR = ROOT / 'build/third-party/quickjs-ng'
QUICKJS_SHA256 = {
    'LICENSE': '96f73f9d2a16c21a36b418f06073be26e7d6d5e7c1bc99756b21a4f2c74ef171',
    'builtin-array-fromasync.h': 'd313ac1e47eaa08f39b2cb0929a512d88e492906c400f650e141d00b79faa905',
    'builtin-iterator-zip-keyed.h': '5b015a8063088987f0fb19357c9da5ec44a7197493fdbb23740fde8f470049a4',
    'builtin-iterator-zip.h': '54834b615ddc59541515a7aa6d2c66fbfbf3213608f52e463d2469d63d395465',
    'cutils.h': 'dffec8bea17f08108da5a91c1178804754698bbbb6202dc100268e78e8c5b770',
    'dtoa.c': 'a8d2cf2d04db406e0c16acdd95ab0e709d309902865722f41dac07a1ba5676af',
    'dtoa.h': '1c4a4540c0038632c8a4c225472fbc21bd476fb35c4da4a857a11965b58231b9',
    'libregexp-opcode.h': '2a98d646089f3a72f25480116297c5fdb5b28fd9f815447273951f4ade4a115e',
    'libregexp.c': 'af13e996abb1767fe0cdfda123c45b811d53688d403a2ac47142e97bf79f1fae',
    'libregexp.h': '53ff95a038f7001b752c455d195d998e2955f0ae4ed62a002c13eca798db3ceb',
    'libunicode-table.h': '5840a921ac11664b505ee37b1219f518fff2a04972fe848b4bdf1e85c5a0bd83',
    'libunicode.c': 'c4724e77ec5f122373d2635b6d481cfb5d96024a38453a54a0830007c4b5f3c9',
    'libunicode.h': 'ad13f66aaea3fab1616e84b9c048f2a315e1bdbab628b966617a7a3e55bcba2b',
    'list.h': 'cb6e24e8ee54bccdd66234fe54cd702d1160b9841db2b9b9adeb5003afe301d5',
    'quickjs-atom.h': '8045b870825a43ecdb50692aac7ad21b43139b288df466ca5f7b780bde4ac13f',
    'quickjs-opcode.h': '0054b0c45fd091afa308c3fb93b5862e0b071235918d3d73e413d23fce388bbc',
    'quickjs.c': '51b1d3919ffe812d0e01793f85d347bcea48c924c11262c5c5f00df1e4759d74',
    'quickjs.h': '6d3879c856551653a1c64fabe52d6d07dc84e97bac3df45848df626702fc30de',
}
JS_DIR = BENCH / 'js'
JS_ISAS = ISAS[2:]
JS_REF_DEFAULT = 'build/cpu/bench/js-ref/s1'  # js_native.sh 1
JS_STACK_BYTES = 1 << 20  # stack below the mailbox; the harness caps QuickJS's own stack at 768 KiB
JS_RAM_KIB = 32768
# QuickJS's own configuration on these targets: no threads or atomics (-D__DJGPP), no debug dumps.
JS_DEFINES = ['-D__DJGPP', '-DNDEBUG', '-D_GNU_SOURCE']
# Ternary-weight GEMV benchmark (ternary): scalar kernels over packed weights from tern_export.py.
TERN_DIR = BENCH / 'ternary'
TERN_ISAS = ISAS[1:3]  # integer kernels: rv64im (software popcount) or rv64imb (Zbb cpop)
RT_DATA_DEFAULT = 'build/cpu/bench/rt-data/g16s2i32-pt16x12x4'  # rt_export.sh 16 2 32 16 12 4
RT_STACK_SLACK = 64 << 10  # smallpt recursion below the reserved stack (free RAM above .bss)

# Upstream sources are 1988-era K&R C, so they build as gnu89. clang ignores
# upstream's "#pragma GCC optimize no-inline"; -fno-inline keeps that intent.
BENCHMARKS = {
    'dhrystone': {
        'sources': [
            (VENDOR / 'dhrystone_main.c', 'vendor'),
            (VENDOR / 'dhrystone.c', 'vendor'),
            (BENCH / 'dhrystone_port.c', 'port'),
            (BENCH / 'runtime.c', 'port'),
        ],
        'vendor_flags': ['-std=gnu89', '-fno-inline', '-Wno-unknown-pragmas',
                         '-Wno-implicit-int', '-Wno-implicit-function-declaration',
                         '-Wno-deprecated-non-prototype', '-Wno-return-type'],
    },
    # Z7_ST: 7-Zip's single-threaded build (7z b -mmt1), no LzFindMt.
    'lzma': {
        'sources': [
            (LZMA_VENDOR / 'LzmaEnc.c', 'vendor'),
            (LZMA_VENDOR / 'LzmaDec.c', 'vendor'),
            (LZMA_VENDOR / 'LzFind.c', 'vendor'),
            (BENCH / 'lzma_bench.c', 'port'),
            (BENCH / 'lzma_bench_data.c', 'port'),
            (BENCH / 'lzma_runtime.c', 'port'),
        ],
        'vendor_flags': ['-std=c11'],
        'include': [BENCH / 'include-lzma', BENCH / 'include', LZMA_VENDOR],
        'defines': ['-DZ7_ST'],
        'required': ('lzma_bench_pass', 'bench_generate_lz', 'LzmaEnc_Encode', 'LzmaDec_DecodeToDic'),
        'headers': [BENCH / 'include-lzma', LZMA_VENDOR],
    },
    # Sources of the ray-tracing benchmark; the generated rt_data.c and, for soft float,
    # the compiler-rt builtins are added in main().
    'rt': {
        'sources': [
            (BENCH / 'rt_bench.c', 'port'),
            (BENCH / 'rt_trace.c', 'port'),
            (BENCH / 'rt_math.c', 'port'),
            (BENCH / 'smallpt_rt.cpp', 'port'),
            (BENCH / 'rt_runtime.c', 'port'),
        ],
        # __SOFTFP__ selects compiler-rt's integer-only paths (as on soft-float Arm), so a
        # builtin never calls another floating-point builtin (fixdfdi without fixunsdfdi).
        'vendor_flags': ['-std=c11', '-D__SOFTFP__'],
        'include': [BENCH / 'include', BENCH / 'include-rt'],
        'defines': ['-ffp-contract=off', '-fno-math-errno'],
        'required': ('rt_bench_run', 'rt_intersect', 'rt_occluded', 'rt_smallpt', 'rt_nodes', 'rt_rays_s'),
        'headers': [BENCH / 'include-rt', RT_VENDOR],
    },
    # QuickJS-ng from build/third-party/quickjs-ng (compiled unmodified, warnings off), the shim
    # libc and the harness; js_src.h is generated in main().
    'js': {
        'sources': [
            (QUICKJS_DIR / 'quickjs.c', 'vendor'),
            (QUICKJS_DIR / 'libregexp.c', 'vendor'),
            (QUICKJS_DIR / 'libunicode.c', 'vendor'),
            (QUICKJS_DIR / 'dtoa.c', 'vendor'),
            (JS_DIR / 'libc.c', 'port'),
            (JS_DIR / 'js_bench.c', 'port'),
        ],
        'vendor_flags': ['-std=gnu11', '-Wno-everything'],
        'include': [JS_DIR / 'include', QUICKJS_DIR],
        'defines': JS_DEFINES,
        'required': ('JS_NewRuntime2', 'JS_CallInternal', 'js_print', 'shim_heap_init', '__heap_end'),
        'headers': [JS_DIR / 'include', JS_DIR / 'include/sys'],
    },
}

# Scalar ternary GEMV kernels (i2, lut5w, bs8) and a read-bandwidth probe; the generated
# ternary_data.S (packed weights, activations, reference outputs) is added in main().
BENCHMARKS['ternary'] = {
    'sources': [(TERN_DIR / 'tern_bench.c', 'port')],
    'vendor_flags': [],
    'include': [BENCH / 'include', TERN_DIR],
    'defines': [],
    'required': ('tern_desc', 'tern_act', 'tern_yref'),
    'headers': [TERN_DIR],
}

# STREAM-like bandwidth probe (stream): read, write, copy, scale, add, triad and a dependent-load chase
# over cold-DRAM, L2-sized and L1-sized footprints (stream/stream_bench.c; original code).
STREAM_DIR = BENCH / 'stream'
BENCHMARKS['stream'] = {
    'sources': [(STREAM_DIR / 'stream_bench.c', 'port')],
    'vendor_flags': [],
    'include': [BENCH / 'include'],
    'defines': [],
    'required': ('d_q', 'd_x0'),
    'headers': [],
}
STREAM_RAM_KIB = 1024

LINKER_SCRIPT = """/* Generated by sim/cpu/bench/build_bench.py; RAM size {ram_bytes} bytes. */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {{ ram (rwx) : ORIGIN = 0, LENGTH = {ram_bytes:#x} }}
__bench_mailbox = {mailbox:#x};
__stack_top = {mailbox:#x};
SECTIONS {{
  .text : {{ KEEP(*(.text.start)) *(.text .text.*) }} > ram
  .rodata : {{ *(.rodata .rodata.*) *(.srodata .srodata.*) }} > ram
  .data : {{ *(.data .data.*) *(.sdata .sdata.*) }} > ram
  .bss (NOLOAD) : ALIGN(8) {{
    __bss_start = .;
    *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON)
    . = ALIGN(8);
    __bss_end = .;
  }} > ram
  ASSERT(__bss_end <= {program_limit:#x}, "Benchmark leaves less than the reserved stack below the mailbox")
}}{extra}
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shown(argument):
    """Command argument as recorded: repository paths relative, no local user paths."""
    text = str(argument)
    for root in (str(ROOT), ROOT.as_posix()):
        text = text.replace(root, '.')
    return text


def check_quickjs():
    """QuickJS-ng sources against their locked upstream identities."""
    for name, digest in QUICKJS_SHA256.items():
        path = QUICKJS_DIR / name
        if not path.is_file():
            raise SystemExit(f'{path} is missing: run sim/cpu/bench/js/fetch_quickjs.sh first')
        if sha(path) != digest:
            raise SystemExit(f'QuickJS-ng {name} differs from its recorded upstream identity')


def tool(name):
    found = shutil.which(name)
    return found or str(Path(r'C:\Program Files\LLVM\bin') / (name + '.exe'))


def run(command, log=None):
    completed = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=180)
    if log is not None:
        log.write_text(completed.stdout + completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'Command failed: {" ".join(map(str, command))}\n{completed.stdout}{completed.stderr}')
    return completed.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', choices=sorted([*BENCHMARKS, 'mm']), default='dhrystone')
    parser.add_argument('--ram-kib', type=int, help='RAM size in KiB, a power of two from 32 to 65536 '
                        '(default 64; for lzma the smallest that holds the estimated arena)')
    parser.add_argument('--opt', choices=['O1', 'O2', 'O3', 'Os'], default='O2')
    parser.add_argument('--isa', choices=ISAS, help=f'Default {ISAS[0]}; {LZMA_ISAS[-1]} for lzma')
    parser.add_argument('--lzma-dict-log', type=int, default=12,
                        help='lzma only: dictionary size 2^N bytes, N from 12 (the LZMA minimum) to 22 '
                             '(7z b -md22)')
    parser.add_argument('--rt-data', help=f'rt only: rt_export.sh output directory (default {RT_DATA_DEFAULT})')
    parser.add_argument('--js-ref', help=f'js only: js_native.sh output directory (default {JS_REF_DEFAULT})')
    parser.add_argument('--mm-data', help='mm only: mm/mm_export.sh output directory (default build/cpu/bench/mm-data/small)')
    parser.add_argument('--mm-variant', choices=('scalar',), default='scalar', help='mm only: kernel source (scalar; RVV later)')
    parser.add_argument('--tern-data', help='ternary only: tern_export.py output directory '
                        '(default build/cpu/bench/ternary-data/small-i2+lut5w+bs8)')
    parser.add_argument('--tern-kernels', help='ternary only: kernels to run, a comma list of i2, lut5w, bs8, stream, streamall '
                        '(default: those packed in the data directory, stream and streamall)')
    parser.add_argument('--stream-levels', type=int, default=7, help='stream only: levels mask (1 dram, 2 l2, 4 l1; default 7)')
    parser.add_argument('--runtime', choices=('reference', 'fast'), default='reference',
                        help='reference: byte-at-a-time strcpy/strcmp (compared across cores); '
                             'fast: word-at-a-time (a labelled, separate configuration)')
    for name in ('clang', 'objcopy', 'objdump', 'nm'):
        parser.add_argument('--' + name, default=tool('clang' if name == 'clang' else 'llvm-' + name))
    parser.add_argument('--out-dir', help='Default: build/cpu/bench/<benchmark>, plus -rv64im for that ISA')
    args = parser.parse_args()
    if args.benchmark == 'mm':
        import mm_build
        return mm_build.build(args, parser)
    if args.mm_data:
        parser.error('--mm-data applies to --benchmark mm only')
    lzma = args.benchmark == 'lzma'
    rt = args.benchmark == 'rt'
    tern = args.benchmark == 'ternary'
    if (args.tern_data or args.tern_kernels) and not tern:
        parser.error('--tern-data and --tern-kernels apply to --benchmark ternary only')
    if tern:
        sys.path.insert(0, str(TERN_DIR))
        import tern_build
        if args.isa is None:
            args.isa = TERN_ISAS[-1]
        if args.isa not in TERN_ISAS:
            parser.error('--benchmark ternary needs rv64im or rv64imb (integer kernels; no F, D or V)')
        if args.runtime != 'reference':
            parser.error('--runtime applies to dhrystone only')
        tern_info = tern_build.prepare(args, parser, ROOT, STACK_RESERVE, MAILBOX_BYTES, RAM_KIB)
        args.ram_kib = args.ram_kib or tern_info['ram_kib']
    stream = args.benchmark == 'stream'
    if stream:
        if args.isa is None:
            args.isa = ISAS[2]
        if args.runtime != 'reference':
            parser.error('--runtime applies to dhrystone only')
        if not 1 <= args.stream_levels <= 7:
            parser.error('--stream-levels must be 1 to 7')
        args.ram_kib = args.ram_kib or STREAM_RAM_KIB
    elif args.stream_levels != 7:
        parser.error('--stream-levels applies to --benchmark stream only')
    js = args.benchmark == 'js'
    if args.rt_data and not rt:
        parser.error('--rt-data applies to --benchmark rt only')
    if args.js_ref and not js:
        parser.error('--js-ref applies to --benchmark js only')
    if js:
        if args.isa is None:
            args.isa = JS_ISAS[0]
        if args.isa not in JS_ISAS:
            parser.error('--benchmark js needs rv64imb (soft float) or rv64imfd_zba_zbb_zbs')
        if args.runtime != 'reference':
            parser.error('--runtime applies to dhrystone only')
        js_ref = (ROOT / (args.js_ref or JS_REF_DEFAULT)).resolve()
        for name in ('reference.json', 'expected.json'):
            if not (js_ref / name).is_file():
                parser.error(f'{js_ref / name} is missing: run sim/cpu/bench/js/js_native.sh first')
        js_reference = json.loads((js_ref / 'reference.json').read_bytes())
        args.ram_kib = args.ram_kib or JS_RAM_KIB
    if rt:
        if args.isa is None:
            args.isa = RT_ISAS[0]
        if args.isa not in RT_ISAS:
            parser.error('--benchmark rt needs rv64imb (soft float) or rv64imfd_zba_zbb_zbs')
        if args.runtime != 'reference':
            parser.error('--runtime applies to dhrystone only')
        rt_dir = (ROOT / (args.rt_data or RT_DATA_DEFAULT)).resolve()
        for name in ('rt_data.c', 'expected.json', 'export.json', 'tinybvh.json'):
            if not (rt_dir / name).is_file():
                parser.error(f'{rt_dir / name} is missing: run sim/cpu/bench/rt_export.sh first')
        rt_export = json.loads((rt_dir / 'export.json').read_bytes())
        if sha(rt_dir / 'rt_data.c') != rt_export['rt_data_sha256']:
            parser.error(f'{rt_dir / "rt_data.c"} differs from the one rt_export.sh recorded')
        rt_args = rt_export['args']
        rt_data_bytes = (rt_dir / 'rt_data.c').stat().st_size // 11 * 4  # about 11 characters per 32-bit word
        if args.ram_kib is None:  # data, program, image buffer, stack slack, reserved stack and mailbox
            need = rt_data_bytes + (192 << 10) + 24 * rt_args['pt_w'] * rt_args['pt_h'] + RT_STACK_SLACK + \
                STACK_RESERVE + MAILBOX_BYTES
            args.ram_kib = next(k for k in RAM_KIB if k >= 256 and k * 1024 >= need)
    elif args.isa == ISAS[3] and not js:
        parser.error(f'{ISAS[3]} applies to --benchmark rt and js only')
    if args.ram_kib is None:
        args.ram_kib = 64
        if lzma and args.lzma_dict_log == 12:
            args.ram_kib = 1024  # the established 4 KiB-dictionary layout (arena 878,400 B measured)
        elif lzma:  # arena + up to 256 KiB of program + stack and mailbox
            need = lzma_arena_estimate(args.lzma_dict_log) + (256 << 10) + STACK_RESERVE + MAILBOX_BYTES
            args.ram_kib = next(k for k in RAM_KIB if k >= 1024 and k * 1024 >= need)
    if args.isa is None:
        args.isa = LZMA_ISAS[-1] if lzma else ISAS[0]
    if lzma:
        if args.isa not in LZMA_ISAS:
            parser.error('--benchmark lzma needs the M extension (rv64im or rv64imb)')
        if args.runtime != 'reference':
            parser.error('--runtime applies to dhrystone only')
        if args.lzma_dict_log not in LZMA_DICT_LOGS:
            parser.error('--lzma-dict-log must be from 12 to 22')
    if args.ram_kib not in RAM_KIB:
        parser.error('--ram-kib must be a power of two from 32 to 65536')
    suffix = ('' if args.isa == ISAS[0] else '-' + isa_label(args.isa)) + \
        ('' if args.runtime == 'reference' else '-fastrt')
    if lzma:
        suffix = f'-d{args.lzma_dict_log}-{isa_label(args.isa)}'
    if rt:
        suffix = f'-{rt_dir.name}-{isa_label(args.isa)}'
    if tern:
        suffix = f'-{tern_info["data_dir"].name}-{isa_label(args.isa)}' + \
            ('' if tern_info['kernels'] == [*tern_info['export']['kernels'], 'stream', 'streamall'] else '-' + '+'.join(tern_info['kernels']))
    if js:
        suffix = f'-{js_ref.name}-{isa_label(args.isa)}'
    if stream:
        suffix = f'-{isa_label(args.isa)}' + ('' if args.stream_levels == 7 else f'-lv{args.stream_levels}')
    out = (ROOT / (args.out_dir or f'build/cpu/bench/{args.benchmark}{suffix}')).resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        parser.error('--out-dir must be inside the repository build/ directory')
    for name, digest in VENDOR_SHA256.items():
        if sha(VENDOR / name) != digest:
            raise SystemExit(f'Vendored {name} differs from its recorded upstream identity')
    if lzma:
        for name, digest in LZMA_VENDOR_SHA256.items():
            if sha(LZMA_VENDOR / name) != digest:
                raise SystemExit(f'Vendored {name} differs from its recorded upstream identity')
    if rt:
        for name, digest in RT_VENDOR_SHA256.items():
            if sha(RT_VENDOR / name) != digest:
                raise SystemExit(f'Vendored {name} differs from its recorded upstream identity')
    if js:
        check_quickjs()
    out.mkdir(parents=True, exist_ok=True)

    spec = dict(BENCHMARKS[args.benchmark])
    if rt:
        soft = abi_of(args.isa) == ABI
        spec['sources'] = spec['sources'] + [(rt_dir / 'rt_data.c', 'data')] + \
            ([(RT_VENDOR / name, 'vendor') for name in RT_SOFT_FLOAT] if soft else [])
    if js:
        soft = abi_of(args.isa) == ABI
        spec['sources'] = spec['sources'] + ([(RT_VENDOR / name, 'vendor-rt') for name in RT_SOFT_FLOAT] if soft else [])
        # The script, generated exactly as the native reference generated it.
        sys.path.insert(0, str(JS_DIR))
        import gen_src
        js_text = gen_src.header((JS_DIR / 'kernels.js').read_text(encoding='utf-8'), js_reference['scale'],
                                 js_reference.get('only'))
        (out / 'js_src.h').write_bytes(js_text.encode('ascii'))
        if sha(out / 'js_src.h') != js_reference['js_src_sha256']:
            raise SystemExit('The generated js_src.h differs from the script the native reference ran '
                             f'({js_ref}): rerun js_native.sh after changing kernels.js')
    if tern:
        spec['sources'] = spec['sources'] + [(tern_info['source'], 'asm')]
    if stream:  # the cold arrays, generated (their values are a fixed formula, recorded in stream_bench.c)
        words, M = 4096, (1 << 64) - 1
        names = ('d_x0', 'd_z1', 'd_x2', 'd_z2', 'd_y3', 'd_z3', 'd_x4', 'd_y4', 'd_z4', 'd_x5', 'd_y5', 'd_z5')
        lines = ['# Generated by build_bench.py --benchmark stream: cold arrays of stream_bench.c.',
                 '.section .data.stream,"aw",@progbits']
        for a_id, name in enumerate(names + ('d_q',)):
            lines += ['.balign 64', f'.globl {name}', f'{name}:']
            vals = [8 * ((j // 8 + 389) % (words // 8)) for j in range(words)] if name == 'd_q' else \
                [(j * 0x9e3779b97f4a7c15 + a_id * 0x632be59bd9b4e019) & M for j in range(words)]
            lines += ['.quad ' + ','.join(f'{v:#x}' for v in vals[i:i + 16]) for i in range(0, words, 16)]
        (out / 'stream_data.S').write_text('\n'.join(lines) + '\n', encoding='ascii', newline='\n')
        spec['sources'] = spec['sources'] + [(out / 'stream_data.S', 'asm')]
    ram_bytes = args.ram_kib * 1024
    mailbox = ram_bytes - MAILBOX_BYTES
    stack_reserve = JS_STACK_BYTES if js else STACK_RESERVE
    program_limit = mailbox - stack_reserve
    extra = f'\n__heap_end = {program_limit:#x};\n' if js else ''
    linker = out / 'link.ld'
    linker.write_text(LINKER_SCRIPT.format(ram_bytes=ram_bytes, mailbox=mailbox, program_limit=program_limit,
                                           extra=extra), encoding='ascii', newline='\n')

    common = [args.clang, '--target=riscv64-unknown-elf', f'-march={args.isa}', f'-mabi={abi_of(args.isa)}',
              '-mcmodel=medany', '-msmall-data-limit=0', '-mno-relax', f'-{args.opt}',
              '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-common',
              '-nostdlibinc', '-I', BENCH / 'include', '-I', VENDOR]
    if lzma:
        common = common[:-4] + [x for d in spec['include'] for x in ('-I', d)] + spec['defines'] + \
            [f'-DLZMA_BENCH_DICT_LOG={args.lzma_dict_log}']
    if rt:
        common = common[:-4] + [x for d in spec['include'] for x in ('-I', d)] + spec['defines'] + \
            [f'-DRT_PT_W={rt_args["pt_w"]}', f'-DRT_PT_H={rt_args["pt_h"]}', f'-DRT_PT_SPP={rt_args["pt_spp"]}']
    if js:  # hosted-style code generation (memcpy and friends inlined), as in the native reference
        common = [x for x in common[:-4] if x not in ('-ffreestanding', '-fno-builtin')] + \
            [x for d in spec['include'] for x in ('-I', d)] + ['-I', out] + spec['defines']
    if tern:
        common = common[:-4] + [x for d in spec['include'] + tern_info['include_dirs'] for x in ('-I', d)] + \
            tern_info['flags']
    port_flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', *(['-Wno-unused-function'] if tern else [])]
    if stream:
        port_flags = port_flags + [f'-DSTREAM_LEVELS={args.stream_levels}']
    started = time.perf_counter()
    commands, objects = [], []
    start_object = out / 'start.o'
    command = common + ['-c', BENCH / 'start.S', '-o', start_object]
    run(command, out / 'compile-start.log')
    commands.append([shown(x) for x in command])
    for source, kind in spec['sources']:
        obj = out / (source.stem + '.o')
        flags = spec['vendor_flags'] if kind == 'vendor' else port_flags
        if kind == 'vendor-rt':  # compiler-rt in the js build, with rt's flags
            flags = BENCHMARKS['rt']['vendor_flags']
        if kind == 'data':
            flags = ['-std=c11']
        elif kind == 'asm':
            flags = []
        elif source.suffix == '.cpp':  # smallpt_rt.cpp; smallpt's own dangling else is kept as written
            flags = ['-std=c++20', '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror',
                     '-Wno-dangling-else']
        if source.name == 'runtime.c' and args.runtime == 'fast':
            flags = flags + ['-DBENCH_FAST_STRINGS']
        command = common + flags + ['-c', source, '-o', obj]
        run(command, out / f'compile-{source.stem}.log')
        commands.append([shown(x) for x in command])
        objects.append(obj)
    elf, binary = out / 'bench.elf', out / 'bench.bin'
    command = [args.clang, '--target=riscv64-unknown-elf', f'-march={args.isa}', f'-mabi={abi_of(args.isa)}',
               '-nostdlib', '-fuse-ld=lld', '-Wl,--no-relax', f'-Wl,-T,{linker}',
               start_object, *objects, '-o', elf]
    run(command, out / 'link.log')
    commands.append([shown(x) for x in command])
    run([args.objcopy, '-O', 'binary', elf, binary])
    build_seconds = time.perf_counter() - started

    symbols, kinds = {}, {}
    for line in run([args.nm, elf]).splitlines():
        match = re.match(r'^([0-9a-fA-F]+)\s+(\S)\s+(\S+)$', line)
        if match:
            symbols[match[3]] = int(match[1], 16)
            kinds[match[3]] = match[2]
    for required in ('_start', 'main', '__bss_start', '__bss_end', '__bench_mailbox') + \
            spec.get('required', ('setStats',)):
        if required not in symbols:
            raise RuntimeError(f'Missing symbol {required}')
    if symbols['__bench_mailbox'] != mailbox:
        raise RuntimeError('Linked mailbox address differs from the requested layout')
    # Address, nm type letter (T/t = code) and name; the profiler reads this.
    (out / 'symbols.txt').write_text(''.join(f'{v:016x} {kinds[k]} {k}\n' for k, v in
                                             sorted(symbols.items(), key=lambda x: x[1])), encoding='ascii')
    if args.objdump:
        (out / 'bench.disasm.txt').write_text(run([args.objdump, '-d', elf]), encoding='utf-8')
        (out / 'sections.txt').write_text(run([args.objdump, '-h', elf]), encoding='utf-8')
    if rt and args.objdump and re.search(r'init_array|\.ctors', (out / 'sections.txt').read_text(encoding='utf-8')):
        raise RuntimeError('Global constructors linked: start.S does not run them')

    payload = binary.read_bytes()
    if len(payload) > symbols['__bss_start']:
        raise RuntimeError('Binary image extends past the start of .bss')
    hex_images = ram_bytes <= HEX_LIMIT_BYTES
    for name in ('bench-bytes.hex', 'bench-words.hex'):
        (out / name).unlink(missing_ok=True)
    if hex_images:
        image = payload.ljust(ram_bytes, b'\0')
        (out / 'bench-bytes.hex').write_text(''.join(f'{b:02x}\n' for b in image), encoding='ascii')
        (out / 'bench-words.hex').write_text(''.join(f'{int.from_bytes(image[i:i+8], "little"):016x}\n'
                                                     for i in range(0, ram_bytes, 8)), encoding='ascii')
    # tb_bench +image_bin: the loaded payload as big-endian 64-bit words; the bench zeroes the rest.
    padded = payload.ljust(-(-len(payload) // 8) * 8, b'\0')
    (out / 'bench-words-be.bin').write_bytes(b''.join(padded[i:i + 8][::-1] for i in range(0, len(padded), 8)))
    images = ('bench-bytes.hex', 'bench-words.hex') if hex_images else ()

    inputs = [source for source, _ in spec['sources']] + [BENCH / 'start.S', Path(__file__)]
    if js:
        inputs += [JS_DIR / 'kernels.js', JS_DIR / 'gen_src.py', js_ref / 'reference.json', js_ref / 'expected.json'] + \
            [QUICKJS_DIR / name for name in QUICKJS_SHA256]
        inputs = list(dict.fromkeys(inputs))
    if tern:
        inputs += tern_info['inputs']
    if rt:
        inputs += [rt_dir / 'expected.json', rt_dir / 'export.json', rt_dir / 'tinybvh.json']
    inputs += sorted((BENCH / 'include').glob('*.h'))
    for directory in spec.get('headers', []):
        inputs += sorted(directory.glob('*.h'))
    report = {
        'benchmark': args.benchmark,
        'compiler': run([args.clang, '--version']).splitlines()[0],
        'isa': args.isa, 'abi': abi_of(args.isa), 'optimization': args.opt, 'runtime': args.runtime,
        **({'lzma': {'dict_log': args.lzma_dict_log, 'dict_bytes': 1 << args.lzma_dict_log,
                     'data_bytes': (1 << args.lzma_dict_log) + (1 << args.lzma_dict_log) // 64,
                     'arena_estimate_bytes': lzma_arena_estimate(args.lzma_dict_log),
                     'arena_available_bytes': mailbox - STACK_RESERVE - symbols['__bss_end']}} if lzma else {}),
        **({'rt': {'data_dir': rt_dir.relative_to(ROOT).as_posix() if rt_dir.is_relative_to(ROOT) else str(rt_dir),
                   'export': rt_export, 'expected': json.loads((rt_dir / 'expected.json').read_bytes()),
                   'tinybvh': json.loads((rt_dir / 'tinybvh.json').read_bytes()),
                   'soft_float': abi_of(args.isa) == ABI,
                   'free_bytes_below_reserved_stack': program_limit - symbols['__bss_end']}} if rt else {}),
        **({'js': {'reference_dir': js_ref.relative_to(ROOT).as_posix() if js_ref.is_relative_to(ROOT) else str(js_ref),
                   'reference': js_reference, 'expected': json.loads((js_ref / 'expected.json').read_bytes()),
                   'soft_float': abi_of(args.isa) == ABI, 'heap_bytes': program_limit - symbols['__bss_end'],
                   'quickjs': {'version': '0.18.0', 'commit': 'd7215b0ad3fc2c562e8317fd9bca058fd4863804',
                               'licence': 'MIT', 'archive_sha256':
                               '28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd'}}} if js else {}),
        **({'ternary': {'data_dir': tern_info['data_dir'].relative_to(ROOT).as_posix(), 'kernels': tern_info['kernels'],
                        'kernel_mask': tern_info['mask'], 'shape': tern_info['export']['shape'],
                        'export': tern_info['export'], 'expected': tern_info['expected']}} if tern else {}),
        **({'stream': {'levels': args.stream_levels, 'dram_words': 4096, 'l2_words': 16384, 'l1_words': 512,
                       'l1_reps': 8, 'chase_words': 4096, 'kernels': 127}} if stream else {}),
        'hex_images': hex_images,
        'ram_bytes': ram_bytes, 'ram_words': ram_bytes // 8,
        'mailbox_address': mailbox, 'stack_top': mailbox, 'stack_reserve_bytes': stack_reserve,
        'payload_bytes': len(payload),
        'bss_bytes': symbols['__bss_end'] - symbols['__bss_start'],
        'program_end': symbols['__bss_end'],
        'build_wall_seconds': build_seconds,
        'commands': commands,
        'input_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs},
        'artifact_sha256': {name: sha(out / name) for name in
                            ('link.ld', 'bench.elf', 'bench.bin', 'bench-words-be.bin', *images)},
    }
    (out / 'build.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(f'Built {args.benchmark}: {len(payload):,} bytes loaded, {report["bss_bytes"]:,} bytes .bss, '
          f'program ends at {symbols["__bss_end"]:#x} of {ram_bytes // 1024} KiB RAM.')
    print(f'Output: {out.relative_to(ROOT).as_posix()}/')


if __name__ == '__main__':
    main()
