#!/bin/bash
# Build the lab-virt Linux kernel (GPL-2.0, from the kernel.org tarball named in sim/cpu/sys/sources.lock)
# out of tree in an untracked directory. Each make call runs under `timeout 300`; rerun the script to
# resume a build that did not finish in one slice. Run in WSL.
#   sim/cpu/sys/build_linux.sh [WORK_DIR]       (default $HOME/linux-lab)
# Inputs: $WORK/linux-6.18.64 (extracted, hash-checked tarball), sim/cpu/sys/linux-lab.config,
#         $WORK/initramfs.list (written by build_userland.sh; optional for a first build).
# Output: $WORK/build-linux/arch/riscv/boot/Image
# SPDX-License-Identifier: MIT
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:-$HOME/linux-lab}
SRC=$WORK/linux-6.18.64
OUT=$WORK/build-linux
JOBS=${JOBS:-3}
MAKE=(make -C "$SRC" O="$OUT" ARCH=riscv LLVM=1 -j"$JOBS")
date "+%F %T %z build_linux start"
mkdir -p "$OUT"
if [ ! -f "$OUT/.config" ]; then
  timeout 300 "${MAKE[@]}" tinyconfig > "$OUT/config.log" 2>&1
  cp "$HERE/linux-lab.config" "$OUT/lab.fragment"
  if [ -f "$WORK/initramfs.list" ]; then
    echo "CONFIG_INITRAMFS_SOURCE=\"$WORK/initramfs.list\"" >> "$OUT/lab.fragment"
  fi
  (cd "$OUT" && timeout 300 "$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" .config lab.fragment >> config.log 2>&1)
  timeout 300 "${MAKE[@]}" olddefconfig >> "$OUT/config.log" 2>&1
  echo configured
fi
if [ -f "$WORK/initramfs.list" ] && ! grep -q "CONFIG_INITRAMFS_SOURCE=\"$WORK/initramfs.list\"" "$OUT/.config"; then
  sed -i "s|^CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE=\"$WORK/initramfs.list\"|" "$OUT/.config"
  timeout 300 "${MAKE[@]}" olddefconfig >> "$OUT/config.log" 2>&1
  echo "initramfs source set"
fi
LOG="$OUT/make-$(date +%H%M%S).log"
rc=0
timeout 300 "${MAKE[@]}" Image > "$LOG" 2>&1 || rc=$?
if [ $rc = 0 ]; then
  echo "BUILD_DONE"
  ls -l "$OUT/arch/riscv/boot/Image"
else
  echo "make slice ended rc=$rc (log $LOG); rerun to resume"
  tail -3 "$LOG"
fi
date "+%F %T %z build_linux end"
exit $rc
