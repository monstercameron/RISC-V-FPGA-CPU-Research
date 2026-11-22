#!/bin/bash
# Fetch the third-party sources of sim/cpu/sys/sources.lock from their official sites into the ignored
# build/third-party/linux-lab/ (one empty directory per download), check every hash against the lock, and
# extract the tarballs into the work directory. Nothing is copied into the tracked repository. Run in WSL;
# every network or extraction command runs under `timeout 300`.
#   sim/cpu/sys/fetch_sources.sh [WORK_DIR]          (default $HOME/linux-lab)
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
WORK=${1:-$HOME/linux-lab}
mkdir -p "$TP/src" "$TP/dl-linux" "$TP/dl-busybox" "$TP/dl-musl" "$TP/dl-compiler-rt" "$WORK"
lock() { grep "^$1 |" "$HERE/sources.lock" | cut -d'|' -f"$2" | xargs; }
fetch() {   # name, directory, file name
  local url sum
  url=$(lock "$1" 4); sum=$(lock "$1" 5 | sed 's/^sha256 //')
  [ -f "$2/$3" ] || (cd "$2" && timeout 300 curl -sSfLO "$url")
  echo "$sum  $2/$3" | sha256sum -c
}
fetch linux "$TP/dl-linux" linux-6.18.64.tar.xz
fetch busybox "$TP/dl-busybox" busybox-1.37.0.tar.bz2
fetch musl "$TP/dl-musl" musl-1.2.5.tar.gz
fetch compiler-rt "$TP/dl-compiler-rt" compiler-rt-18.1.3.src.tar.xz
clone() {   # name, directory, commit (or tag)
  [ -d "$TP/src/$2" ] || timeout 300 git clone -q "$(lock "$1" 4)" "$TP/src/$2"
  (cd "$TP/src/$2" && git checkout -q "$3" && test "$(git rev-parse HEAD)" = "$(lock "$1" 5 | awk '{print $2}')" \
     && test -z "$(git status --porcelain --ignore-submodules=none)") || { echo "$1: not the locked, clean tree"; exit 1; }
}
clone spike spike 982f078e65ab52d5d9a91248c2178f5399df7783
(cd "$TP/src/spike" && timeout 300 git submodule update --init)
clone opensbi opensbi v1.9
cd "$WORK"
extract() {   # directory, tarball: into a scratch directory first, renamed only when tar succeeded
  [ -d "$1" ] && [ -f "$1/.lab-extracted" ] && return 0
  rm -rf "$1" ".x-$1" && mkdir ".x-$1"
  timeout 300 tar -xf "$2" -C ".x-$1" && mv ".x-$1/$1" "$1" && rmdir ".x-$1" && touch "$1/.lab-extracted"
}
extract linux-6.18.64 "$TP/dl-linux/linux-6.18.64.tar.xz"
extract busybox-1.37.0 "$TP/dl-busybox/busybox-1.37.0.tar.bz2"
extract musl-1.2.5 "$TP/dl-musl/musl-1.2.5.tar.gz"
extract compiler-rt-18.1.3.src "$TP/dl-compiler-rt/compiler-rt-18.1.3.src.tar.xz"
date "+%F %T %z fetch_sources done"
