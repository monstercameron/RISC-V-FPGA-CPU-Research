#!/bin/bash
# Build Spike (riscv-isa-sim, BSD-3-Clause; commit in sim/cpu/sys/sources.lock) with clang from the
# checkout made by fetch_sources.sh, in the ignored build/third-party/linux-lab/build/spike. One
# `timeout 300` make slice per call; rerun until it prints MAKE_DONE (a full build takes several slices over
# WSL's /mnt/c). The simulator is build/third-party/linux-lab/build/spike/spike. Run in WSL.
# SPDX-License-Identifier: MIT
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
TP=""
d=$(cd "$HERE/../../.." && pwd)
while [ "$d" != "/" ]; do
  if [ -d "$d/build/third-party/linux-lab/src/opensbi" ]; then TP="$d/build/third-party/linux-lab"; break; fi
  d=$(dirname "$d")
done
[ -n "$TP" ] || TP=$(cd "$HERE/../../.." && pwd)/build/third-party/linux-lab
mkdir -p "$TP/build/spike"
cd "$TP/build/spike"
date "+%F %T %z start slice"
if [ ! -f Makefile ]; then
  CC=clang CXX=clang++ timeout 300 "$TP/src/spike/configure" --prefix="$TP/install/spike" > configure.log 2>&1
  echo configured
fi
timeout 300 make -j"${JOBS:-3}" > "make-$(date +%H%M%S).log" 2>&1 && echo MAKE_DONE || echo "make slice ended rc=$?"
date "+%F %T %z end slice"
