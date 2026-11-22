# SPDX-License-Identifier: MIT
param([string]$Distribution = 'Ubuntu-24.04')
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$linuxPath = (& wsl -d $Distribution --exec wslpath -u $repoPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path in WSL.' }
& wsl -d $Distribution --cd $linuxPath --exec python3 -B sim/cpu/test_cpu.py
if ($LASTEXITCODE -ne 0) { throw 'CPU simulation failed.' }
