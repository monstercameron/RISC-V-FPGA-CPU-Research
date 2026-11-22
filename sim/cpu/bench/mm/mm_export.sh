#!/bin/bash
# SPDX-License-Identifier: MIT
# Make the inputs and the native reference of the mm benchmark (run on a Linux or WSL host with clang;
# the laptop reference used aarch64 WSL):
#   1. mm_gen writes the fixed-seed input files and mm_data.S (labels with .incbin);
#   2. mm_native, mm_bench.c + mm_kernels.c + mm_data.S built for the host with -ffp-contract=off,
#      runs its self-checks and prints the mailbox words the RV64 build must reproduce bit for bit.
# Usage: mm_export.sh PROFILE [OUT]
#   small  GEMMs 64^3; V1 256 rows x 2048, V3 128 rows x 2048, V4 256 rows x 1024; no V1b (fits a full-mode run)
#   full   GEMMs 64^3; V1 2048 x 2048, V3 2048 x 2048, V4 1024 x 1024, V1b 4096 x 2048 (sampled mode)
# Output: OUT (default build/cpu/bench/mm-data/PROFILE/): the .bin inputs, mm_data.S, expected.json, export.json
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../../../.." && pwd)
PROFILE=${1:?usage: mm_export.sh small|full [OUT]}
case "$PROFILE" in
  small) V1=256;  V3=128;  V4=256;  V1B=0 ;;
  full)  V1=2048; V3=2048; V4=1024; V1B=4096 ;;
  *) echo "profile must be small or full" >&2; exit 2 ;;
esac
OUT=${2:-$ROOT/build/cpu/bench/mm-data/$PROFILE}
CC=${CC:-clang}
mkdir -p "$OUT"
DEFS="-DMM_V1_ROWS=$V1 -DMM_V3_ROWS=$V3 -DMM_V4_ROWS=$V4 -DMM_V1B_ROWS=$V1B"
REF_FLAGS="-O2 -ffp-contract=off -fno-math-errno $DEFS -I$B"
$CC -O2 -std=c11 -Wall -Wextra -Werror -I"$B" "$B/mm_gen.c" "$B/mm_kernels.c" -o "$OUT/mm_gen"
"$OUT/mm_gen" "$OUT" $V1 $V3 $V4 $V1B
$CC $REF_FLAGS -std=c11 -Wall -Wextra -Werror "$B/mm_bench.c" "$B/mm_kernels.c" "$B/mm_native.c" \
    -x assembler-with-cpp -I"$OUT" "$OUT/mm_data.S" -o "$OUT/mm_native"
"$OUT/mm_native" > "$OUT/expected.json"
{
  echo "{\"date\": \"$(date -Iseconds)\", \"host\": \"$(uname -srm)\", \"cc\": \"$($CC --version | head -1)\","
  echo " \"reference_flags\": \"$REF_FLAGS\", \"profile\": \"$PROFILE\","
  echo " \"rows\": {\"v1\": $V1, \"v3\": $V3, \"v4\": $V4, \"v1b\": $V1B},"
  echo " \"data_sha256\": {"
  first=1
  for f in "$OUT"/*.bin "$OUT/mm_data.S"; do
    [ $first = 1 ] || echo ","
    first=0
    printf '  "%s": "%s"' "$(basename "$f")" "$(sha256sum "$f" | cut -d' ' -f1)"
  done
  echo "}}"
} > "$OUT/export.json"
rm -f "$OUT/mm_gen" "$OUT/mm_native"
echo "$OUT"
cat "$OUT/expected.json"
