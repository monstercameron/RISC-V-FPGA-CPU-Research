#!/bin/bash
# SPDX-License-Identifier: MIT
# Laptop reference of the mm benchmark (aarch64 WSL): build mm_laptop.c with the same kernels and data as
# the RV64 build, then run it N times pinned to one vCPU and print each run's JSON lines.
# Usage: mm_laptop.sh PROFILE [RUNS=7] [CPU=19]   (PROFILE data from mm_export.sh)
# Build flags: clang -O2, auto-vectoriser off, -ffp-contract=off (the same scalar C; no NEON/SVE kernels).
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../../../.." && pwd)
PROFILE=${1:?usage: mm_laptop.sh small|full [RUNS] [CPU]}
RUNS=${2:-7}
CPU=${3:-19}
D=$ROOT/build/cpu/bench/mm-data/$PROFILE
case "$PROFILE" in
  small) DEFS="-DMM_V1_ROWS=256 -DMM_V3_ROWS=128 -DMM_V4_ROWS=256 -DMM_V1B_ROWS=0" ;;
  full)  DEFS="-DMM_V1_ROWS=2048 -DMM_V3_ROWS=2048 -DMM_V4_ROWS=1024 -DMM_V1B_ROWS=4096" ;;
  *) echo "profile must be small or full" >&2; exit 2 ;;
esac
CC=${CC:-clang}
OUT=$ROOT/build/cpu/bench/mm-laptop
mkdir -p "$OUT"
$CC -O2 -fno-vectorize -fno-slp-vectorize -ffp-contract=off -fno-math-errno -D_GNU_SOURCE -std=gnu11 -Wall -Wextra \
    $DEFS -I"$B" "$B/mm_bench.c" "$B/mm_kernels.c" "$B/mm_laptop.c" -x assembler-with-cpp -I"$D" "$D/mm_data.S" \
    -o "$OUT/mm_laptop-$PROFILE"
$CC --version | head -1 > "$OUT/mm_laptop-$PROFILE.compiler"
for i in $(seq 1 "$RUNS"); do
  echo "# run $i $(date -Iseconds) load: $(cut -d' ' -f1-3 /proc/loadavg)"
  taskset -c "$CPU" "$OUT/mm_laptop-$PROFILE"
done
