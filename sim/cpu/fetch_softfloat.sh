#!/bin/bash
# SPDX-License-Identifier: MIT
# Fetch Berkeley SoftFloat Release 3e and TestFloat Release 3e (John R. Hauser, BSD-3-Clause; the official
# release archives from http://www.jhauser.us/arithmetic/, fetched over HTTPS) into the ignored
# build/third-party/softfloat/ (not vendored). The archives' SHA-256 are locked here; sim/cpu/fp_oracle.py
# builds them and uses TestFloat as an independent oracle for the F/D models and the RTL FPU.
# Run on Linux or WSL with curl, sha256sum and python3.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../.." && pwd)
OUT=${SOFTFLOAT_DIR:-$ROOT/build/third-party/softfloat}
BASE=https://www.jhauser.us/arithmetic
SOFTFLOAT_SUM=21130ce885d35c1fe73fc1e1bf2244178167e05c6747cad5f450cc991714c746   # SoftFloat-3e.zip, 729,637 bytes
TESTFLOAT_SUM=6d4bdf0096b48a653aa59fc203a9e5fe18b5a58d7a1b715107c7146776a0aad6   # TestFloat-3e.zip, 429,806 bytes
if [ -f "$OUT/SoftFloat-3e/source/include/softfloat.h" ] && [ -f "$OUT/TestFloat-3e/source/testfloat_gen.c" ]; then
    echo "$OUT already present"; exit 0
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -sSL --max-time 120 -o "$TMP/SoftFloat-3e.zip" "$BASE/SoftFloat-3e.zip"
curl -sSL --max-time 120 -o "$TMP/TestFloat-3e.zip" "$BASE/TestFloat-3e.zip"
echo "$SOFTFLOAT_SUM  $TMP/SoftFloat-3e.zip" | sha256sum -c --quiet -
echo "$TESTFLOAT_SUM  $TMP/TestFloat-3e.zip" | sha256sum -c --quiet -
mkdir -p "$OUT"
python3 -c "import sys, zipfile; [zipfile.ZipFile(z).extractall(sys.argv[1]) for z in sys.argv[2:]]" \
    "$OUT" "$TMP/SoftFloat-3e.zip" "$TMP/TestFloat-3e.zip"
cp "$TMP/SoftFloat-3e.zip" "$TMP/TestFloat-3e.zip" "$OUT/"
echo "SoftFloat 3e and TestFloat 3e in $OUT (archive SHA-256 $SOFTFLOAT_SUM, $TESTFLOAT_SUM)"
