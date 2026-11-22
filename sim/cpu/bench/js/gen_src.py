# SPDX-License-Identifier: MIT
"""Write js_src.h: kernels.js as a C string, with SCALE (and optionally ONLY) prepended.

Used by build_bench.py --benchmark js (bare metal) and js_native.sh (the native reference), so
both machines run byte-identical script text. Usage: gen_src.py kernels.js js_src.h SCALE [ONLY]
"""
import sys


def header(source_text, scale, only=None):
    text = f'var SCALE = {scale};\n' + (f'var ONLY = {only};\n' if only is not None else '') + source_text
    # Octal escapes for anything outside printable ASCII and for ", \ and ? (no trigraphs).
    body = ''.join('\\%03o' % b if (b < 32 or b > 126 or b in (34, 92, 63)) else chr(b) for b in text.encode())
    chunks, cur, i = [], '', 0
    while i < len(body):  # never split an escape across string pieces
        step = 4 if body[i] == '\\' else 1
        cur += body[i:i + step]
        i += step
        if len(cur) >= 120:
            chunks.append(cur)
            cur = ''
    chunks.append(cur)
    return 'static const char js_src[] =\n' + '\n'.join('"%s"' % c for c in chunks) + ';\n'


if __name__ == '__main__':
    src, out, scale = sys.argv[1], sys.argv[2], sys.argv[3]
    only = sys.argv[4] if len(sys.argv) > 4 else None
    with open(src, encoding='utf-8') as f:
        text = f.read()
    with open(out, 'w', encoding='ascii', newline='\n') as f:
        f.write(header(text, scale, only))
