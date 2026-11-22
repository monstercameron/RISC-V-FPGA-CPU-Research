#!/bin/bash
# SPDX-License-Identifier: MIT
# Native reference of the JavaScript benchmark (run on a Linux or WSL host with clang; the laptop
# reference used aarch64 WSL): the same QuickJS-ng sources (build/third-party/quickjs-ng, checked
# against build_bench.py's QUICKJS_SHA256), the same configuration (-D__DJGPP -DNDEBUG
# -D_GNU_SOURCE), harness and script, built for the host with glibc's malloc and libm. One run
# records the output every RV64 build must reproduce:
#   expected.json   output hash and bytes, line count, each line's text and FNV-1a hash
#   reference.json  scale, the generated script's SHA-256, compiler and flags, host
#   qjs_bench       the native binary that js_laptop.py times
# Usage: js_native.sh [SCALE=1] [OUT=build/cpu/bench/js-ref/s<SCALE>]
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../../../.." && pwd)
SCALE=${1:-1}
OUT=${2:-$ROOT/build/cpu/bench/js-ref/s$SCALE}
Q=$ROOT/build/third-party/quickjs-ng
CC=${CC:-clang}
OPT=${OPT:--O2}
python3 -B -c "import sys; sys.path.insert(0, '$B/..'); import build_bench; build_bench.check_quickjs()"
mkdir -p "$OUT/obj"
python3 -B "$B/gen_src.py" "$B/kernels.js" "$OUT/js_src.h" "$SCALE"
DEFS="-D__DJGPP -DNDEBUG -D_GNU_SOURCE"
VFLAGS="$OPT -std=gnu11 -Wno-everything $DEFS"
for f in quickjs libregexp libunicode dtoa; do
  $CC $VFLAGS -c "$Q/$f.c" -o "$OUT/obj/$f.o"
done
HFLAGS="$OPT -std=gnu11 -Wall -Wextra -Werror $DEFS -DJS_BENCH_NATIVE -I$Q -I$OUT"
$CC $HFLAGS -c "$B/js_bench.c" -o "$OUT/obj/js_bench.o"
$CC "$OUT/obj/"*.o -lm -o "$OUT/qjs_bench"
"$OUT/qjs_bench" > "$OUT/output.txt" 2> "$OUT/native-run.txt"
# Flags as recorded: repository paths relative (no local user paths in the reference record).
python3 -B - "$OUT" "$SCALE" "$CC" "$VFLAGS" "${HFLAGS//$ROOT/.}" <<'PY'
import hashlib, json, os, platform, re, subprocess, sys
from datetime import datetime
out, scale, cc, vflags, hflags = sys.argv[1:6]
text = open(os.path.join(out, 'output.txt'), 'rb').read()
run = open(os.path.join(out, 'native-run.txt'), encoding='utf-8').read()
def fnv(data):
    h = 0xcbf29ce484222325
    for b in data:
        h = ((h ^ b) * 0x100000001b3) & (2**64 - 1)
    return h
lines = text.split(b'\n')[:-1]
reported = {int(i): int(h, 16) for i, h in re.findall(r'^line (\d+) ([0-9a-f]{16})$', run, re.M)}
total = re.search(r'^hash ([0-9a-f]{16}) bytes (\d+) lines (\d+) exception (\d+)$', run, re.M)
if not total or int(total[4]) != 0:
    raise SystemExit(f'native run failed:\n{run[-2000:]}')
if int(total[1], 16) != fnv(text) or int(total[2]) != len(text) or int(total[3]) != len(lines):
    raise SystemExit('native harness hash disagrees with its output')
rows = []
for i, line in enumerate(lines):
    h = fnv(line + b'\n')
    if reported.get(i) != h:
        raise SystemExit(f'line {i}: harness hash differs')
    if b'differs' in line:
        raise SystemExit(f'warm and timed calls disagree: {line!r}')
    rows.append({'kernel': line.split(b' ')[0].decode(), 'text': line.decode(), 'fnv1a64': h})
marks = [int(m, 16) for m in re.findall(r'^mark 0x([0-9a-f]+) ', run, re.M)]
expected = {'hash': int(total[1], 16), 'hash_hex': total[1], 'bytes': len(text), 'lines': rows, 'marks': marks}
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
ver = subprocess.run([cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0]
reference = {'date': datetime.now().astimezone().isoformat(timespec='seconds'), 'host': ' '.join(platform.uname()[i] for i in (0, 2, 4)),
             'compiler': ver, 'engine_flags': vflags, 'harness_flags': hflags, 'libc': 'glibc (malloc, libm)',
             'scale': int(scale) if scale.isdigit() else float(scale), 'only': None,
             'js_src_sha256': sha(os.path.join(out, 'js_src.h')), 'qjs_bench_sha256': sha(os.path.join(out, 'qjs_bench'))}
json.dump(expected, open(os.path.join(out, 'expected.json'), 'w'), indent=1)
json.dump(reference, open(os.path.join(out, 'reference.json'), 'w'), indent=1)
print(json.dumps({'hash': total[1], 'bytes': len(text), 'lines': [r['text'] for r in rows]}, indent=1))
PY
echo "$OUT"
