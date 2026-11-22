#!/bin/bash
# SPDX-License-Identifier: MIT
# Fetch the riscv-tests ISA test sources (riscv-software-src/riscv-tests, BSD-3-Clause, The Regents of
# the University of California) and, for reference only, the riscv-test-env submodule commit it pins
# (riscv/riscv-test-env, same licence) from the official GitHub repositories into the ignored
# build/third-party/riscv-tests-src/ (not vendored; source only, shallow fetch of one commit each).
# Every file the runner reads is checked against sim/cpu/riscv_tests/riscv-tests.lock (SHA-256);
# a mismatch stops here, and sim/cpu/riscv_tests/run_riscv_tests.py checks the lock again before
# each build. The tests are built with the project's own MIT lab environment
# (sim/cpu/riscv_tests/env/), not with riscv-test-env. Run on Linux or WSL with git and sha256sum.
set -euo pipefail
B=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$B/../.." && pwd)
OUT=${RISCV_TESTS_DIR:-$ROOT/build/third-party/riscv-tests-src}
LOCK=$B/riscv_tests/riscv-tests.lock
TESTS_URL=https://github.com/riscv-software-src/riscv-tests
TESTS_COMMIT=3df703cd52d5f0d8224e3c50bf03c6cb70efff98    # master, 2026-10-19 (same commit as the vendored Dhrystone)
ENV_URL=https://github.com/riscv/riscv-test-env
ENV_COMMIT=6de71edb142be36319e380ce782c3d1830c65d68      # the env submodule commit recorded by TESTS_COMMIT

fetch() {   # fetch <dir> <url> <commit>
    local dir=$OUT/$1
    if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$3" ]; then
        return 0
    fi
    rm -rf "$dir"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" remote add origin "$2"
    git -C "$dir" fetch -q --depth 1 origin "$3"
    git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
    [ "$(git -C "$dir" rev-parse HEAD)" = "$3" ] || { echo "error: $1 is not at $3" >&2; exit 1; }
}

mkdir -p "$OUT"
fetch riscv-tests "$TESTS_URL" "$TESTS_COMMIT"
fetch riscv-test-env "$ENV_URL" "$ENV_COMMIT"
[ "$(git -C "$OUT/riscv-tests" ls-tree HEAD env | awk '{print $3}')" = "$ENV_COMMIT" ] || {
    echo "error: riscv-tests $TESTS_COMMIT does not pin riscv-test-env $ENV_COMMIT" >&2; exit 1; }
(cd "$OUT" && grep -v '^#' "$LOCK" | sha256sum -c --quiet -)
echo "riscv-tests $TESTS_COMMIT and riscv-test-env $ENV_COMMIT in $OUT; $(grep -vc '^#' "$LOCK") locked files match"
