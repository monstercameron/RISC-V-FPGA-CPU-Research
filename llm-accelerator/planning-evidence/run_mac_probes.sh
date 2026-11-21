#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
{
  for width in 4 8; do
    iverilog -g2012 -s mac_probe -Pmac_probe.W="$width" -o "build/mac${width}.vvp" mac_probe.sv
    vvp "build/mac${width}.vvp"
  done
} | tee mac-probes.log
