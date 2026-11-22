#!/bin/bash
# Build the whole lab-virt software stack (userland, kernel, OpenSBI with the kernel as payload, DTB) from
# the sources in sim/cpu/sys/sources.lock and copy the results to build/third-party/linux-lab/out/ with
# their SHA-256 in out/manifest.txt. Each make call runs under `timeout 300` inside the sub-scripts; rerun
# this script to resume after a slice ends. Run in WSL.
#   sim/cpu/sys/build_all.sh [WORK_DIR]          (default $HOME/linux-lab)
# SPDX-License-Identifier: MIT
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
TP=""
d=$(cd "$HERE/../../.." && pwd)
while [ "$d" != "/" ]; do
  if [ -d "$d/build/third-party/linux-lab/src/opensbi" ]; then TP="$d/build/third-party/linux-lab"; break; fi
  d=$(dirname "$d")
done
[ -n "$TP" ] || TP=$(cd "$HERE/../../.." && pwd)/build/third-party/linux-lab
WORK=${1:-$HOME/linux-lab}
bash "$HERE/build_userland.sh" "$WORK"
bash "$HERE/build_linux.sh" "$WORK" || { echo "kernel not finished: rerun"; exit 2; }
bash "$HERE/build_opensbi.sh" "$TP/src/opensbi" "$WORK/build-linux/arch/riscv/boot/Image" "$WORK"
mkdir -p "$TP/out"
cp "$WORK/build-opensbi-linux/platform/generic/firmware/fw_payload.elf" "$TP/out/fw_payload.elf"
cp "$WORK/lab-virt.dtb" "$TP/out/lab-virt.dtb"
cp "$WORK/build-linux/arch/riscv/boot/Image" "$TP/out/Image"
cp "$WORK/build-busybox/busybox" "$TP/out/busybox"
(cd "$TP/out" && sha256sum fw_payload.elf lab-virt.dtb Image busybox > manifest.txt && cat manifest.txt)
date "+%F %T %z build_all done"
