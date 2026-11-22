#!/bin/sh
# SPDX-License-Identifier: MIT
# /init of the lab-virt initramfs (our own text, MIT). Prints the boot markers, runs a shell command, then
# reads console input for up to 1 s of simulated time: if a line arrives (rv_iss's scripted UART file), it
# runs it and continues as an interactive shell on the console until EOF or `exit`. Then it powers off
# through SBI SRST, which OpenSBI's syscon-poweroff driver turns into a write of 0x5555 to the SiFive test
# finisher. Without input (as in the Spike comparison) the boot ends by itself.
mount -t proc proc /proc
mount -t sysfs sysfs /sys
echo "LAB-VIRT-MARKER: busybox init reached"
uname -a
sh -c 'echo "LAB-VIRT-MARKER: shell ran a command on $(uname -m)"'
if read -t 1 first; then
  eval "$first"
  sh
fi
echo "LAB-VIRT-MARKER: powering off"
poweroff -f
