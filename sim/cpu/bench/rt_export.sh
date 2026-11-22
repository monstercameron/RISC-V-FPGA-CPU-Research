#!/bin/bash
# SPDX-License-Identifier: MIT
# Make the inputs and the native reference of the ray-tracing benchmark (run on
# a Linux or WSL host with clang/clang++; the laptop reference used aarch64 WSL):
#   1. rt_export (TinyBVH from build/third-party/tinybvh at the pinned commit,
#      checked by SHA-256) writes rt_data.c and prints TinyBVH's own checksums;
#   2. rt_native, the benchmark's portable sources plus rt_data.c built for the
#      host with -ffp-contract=off, prints the mailbox words the RV64 build must
#      reproduce bit for bit.
# Usage: rt_export.sh GRID SPHERES IMAGE PT_W PT_H PT_SPP [OUT]
#   scaled (default for build_bench.py --benchmark rt): 16 2 32 16 12 4
#   full laptop workload:                               32 8 256 128 96 16
# Output: OUT (default build/cpu/bench/rt-data/g<G>s<N>i<I>-pt<W>x<H>x<SPP>/):
#   rt_data.c, tinybvh.json, expected.json, export.json (tools, hashes)
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../../.." && pwd)
G=${1:-16}; N=${2:-2}; I=${3:-32}; W=${4:-16}; H=${5:-12}; SPP=${6:-4}
OUT=${7:-$ROOT/build/cpu/bench/rt-data/g${G}s${N}i${I}-pt${W}x${H}x${SPP}}
T=${TINYBVH_DIR:-$ROOT/build/third-party/tinybvh}
CXX=${CXX:-clang++}
CC=${CC:-clang}
# TinyBVH 1.9.2, commit 58439efd892f6738f7ffc4e7fcf3cd50ecb9a3b2 (github.com/jbikker/tinybvh), MIT;
# SHA-256 of the upstream git blobs (LF line endings; a Windows checkout with core.autocrlf=true differs).
sha256sum -c --quiet - <<EOF
3e19ae7e4dd587d6392bf0fe61cc99efac765633ec1e565689a10a494495fdb7  $T/tiny_bvh.h
60b9ae208661f2ec6910049678499cb00abf74fb4c7b9aa7805ff9f83879e187  $T/tiny_bvh_base.h
c6536e678bc12cb66751f77ffc939aac0b15a3fc4826beb6fc29d616fc601a86  $T/tiny_bvh_arm_float.h
941d0682af0c8cddc632b9284311b9b40d2bd83feeee8186059aa2a01a7075e0  $T/tiny_bvh_arm_double.h
568cb93ff178e12a29e3c3be72f818190bb338f612ed08da3992ac1d356c0734  $T/tiny_bvh_x86_float.h
aed9ffa75a06f667ac33dd0d37c6f6f0860395db36c804e334d9e17734a58f5f  $T/tiny_bvh_x86_double.h
EOF
mkdir -p "$OUT"
EXPORT_FLAGS="-O2 -std=c++17 -w -I$T"
$CXX $EXPORT_FLAGS "$B/rt_export.cpp" -o "$OUT/rt_export"
"$OUT/rt_export" --grid "$G" --spheres "$N" --image "$I" --out "$OUT" > "$OUT/tinybvh.json"
REF_FLAGS="-O2 -ffp-contract=off -fno-math-errno -I$B/include-rt -DRT_PT_W=$W -DRT_PT_H=$H -DRT_PT_SPP=$SPP"
objs=()
for s in rt_bench.c rt_trace.c rt_math.c rt_native.c; do
  $CC $REF_FLAGS -std=c11 -Wall -Wextra -Werror -c "$B/$s" -o "$OUT/${s%.c}.o"; objs+=("$OUT/${s%.c}.o")
done
$CC $REF_FLAGS -std=c11 -c "$OUT/rt_data.c" -o "$OUT/rt_data.o"; objs+=("$OUT/rt_data.o")
$CXX $REF_FLAGS -std=c++20 -fno-exceptions -fno-rtti -Wall -Wextra -Wno-dangling-else -c "$B/smallpt_rt.cpp" -o "$OUT/smallpt_rt.o"; objs+=("$OUT/smallpt_rt.o")
$CXX "${objs[@]}" -o "$OUT/rt_native"
"$OUT/rt_native" > "$OUT/expected.json"
{
  echo "{\"date\": \"$(date -Iseconds)\", \"host\": \"$(uname -srm)\","
  echo " \"cxx\": \"$($CXX --version | head -1)\", \"cc\": \"$($CC --version | head -1)\","
  echo " \"export_flags\": \"$EXPORT_FLAGS\", \"reference_flags\": \"$REF_FLAGS\","
  echo " \"args\": {\"grid\": $G, \"spheres\": $N, \"image\": $I, \"pt_w\": $W, \"pt_h\": $H, \"pt_spp\": $SPP},"
  echo " \"rt_data_sha256\": \"$(sha256sum "$OUT/rt_data.c" | cut -d' ' -f1)\"}"
} > "$OUT/export.json"
rm -f "$OUT"/*.o
echo "$OUT"
cat "$OUT/expected.json"
