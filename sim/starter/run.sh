#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
iverilog -g2012 -Wall -s tb_cpu -o build/cpu.vvp vendor/picorv32.v tb_cpu.v
cd build
vvp cpu.vvp | tee simulation.log
