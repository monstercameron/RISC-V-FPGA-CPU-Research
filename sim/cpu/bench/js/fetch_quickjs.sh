#!/bin/bash
# SPDX-License-Identifier: MIT
# Fetch QuickJS-ng v0.18.0 (MIT, github.com/quickjs-ng/quickjs, tag v0.18.0 = commit
# d7215b0ad3fc2c562e8317fd9bca058fd4863804) from its official GitHub tag archive into the
# ignored build/third-party/quickjs-ng/ (not vendored). The archive's SHA-256 is checked here
# and every source file build_bench.py --benchmark js compiles or includes is checked again
# there (QUICKJS_SHA256). Run on Linux or WSL with curl, sha256sum and tar.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../../../.." && pwd)
OUT=${QUICKJS_DIR:-$ROOT/build/third-party/quickjs-ng}
URL=https://github.com/quickjs-ng/quickjs/archive/refs/tags/v0.18.0.tar.gz
SUM=28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd
if [ -f "$OUT/quickjs.c" ]; then echo "$OUT already present"; exit 0; fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -sSL --max-time 120 -o "$TMP/quickjs-ng-v0.18.0.tar.gz" "$URL"
echo "$SUM  $TMP/quickjs-ng-v0.18.0.tar.gz" | sha256sum -c --quiet -
mkdir -p "$TMP/x"
tar -xzf "$TMP/quickjs-ng-v0.18.0.tar.gz" -C "$TMP/x"
mkdir -p "$(dirname "$OUT")"
mv "$TMP/x/quickjs-0.18.0" "$OUT"
cp "$TMP/quickjs-ng-v0.18.0.tar.gz" "$OUT.tar.gz"
echo "QuickJS-ng v0.18.0 in $OUT (archive SHA-256 $SUM)"
