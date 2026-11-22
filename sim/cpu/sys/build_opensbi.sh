#!/bin/bash
# Build OpenSBI (BSD-2-Clause, pinned tag in sim/cpu/sys/sources.lock) for the lab-virt platform with LLVM,
# and the device tree blob. Run in WSL; each make runs under `timeout 300`.
#   sim/cpu/sys/build_opensbi.sh OPENSBI_SRC [PAYLOAD_IMAGE] [WORK_DIR]
# OpenSBI links fw_payload.elf as a position-independent ET_DYN at 0; Spike and rv_iss both load an ET_DYN
# ELF at DRAM base + its addresses (Spike's rule), and OpenSBI relocates itself.
# Without PAYLOAD_IMAGE, fw_payload carries OpenSBI's own test payload.
# Outputs: $WORK/build-opensbi/platform/generic/firmware/fw_payload.{elf,bin}, $WORK/lab-virt.dtb
# SPDX-License-Identifier: MIT
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$1
PAYLOAD=$2
WORK=${3:-$HOME/linux-lab}
OUT=$WORK/build-opensbi${PAYLOAD:+-linux}
date "+%F %T %z build_opensbi start"
mkdir -p "$OUT"
timeout 300 dtc -I dts -O dtb -o "$WORK/lab-virt.dtb" "$HERE/lab-virt.dts"
ARGS="PLATFORM=generic LLVM=1 PLATFORM_RISCV_ISA=rv64imafdc_zicsr_zifencei PLATFORM_RISCV_ABI=lp64d O=$OUT"
[ -n "$PAYLOAD" ] && ARGS="$ARGS FW_PAYLOAD_PATH=$PAYLOAD"
timeout 300 make -C "$SRC" $ARGS -j${JOBS:-2} > "$OUT/make.log" 2>&1 || { echo "make failed"; tail -20 "$OUT/make.log"; exit 1; }
ls -l "$OUT/platform/generic/firmware/fw_payload.elf" "$OUT/platform/generic/firmware/fw_payload.bin" "$WORK/lab-virt.dtb"
date "+%F %T %z build_opensbi end"
