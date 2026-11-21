# SPDX-License-Identifier: MIT
# Build Dhrystone with the installed Windows LLVM, then run and check it on the
# RTL in Ubuntu/WSL. -Record also saves the result to cpu/dhrystone-results.json.
param(
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$LLVMDirectory = 'C:\Program Files\LLVM\bin',
    [ValidateSet(32,64,128,256,512,1024)][int]$RamKiB = 64,
    [switch]$Record
)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
& python -B (Join-Path $PSScriptRoot 'build_bench.py') --benchmark dhrystone --ram-kib $RamKiB `
    --clang (Join-Path $LLVMDirectory 'clang.exe') `
    --objcopy (Join-Path $LLVMDirectory 'llvm-objcopy.exe') `
    --objdump (Join-Path $LLVMDirectory 'llvm-objdump.exe') `
    --nm (Join-Path $LLVMDirectory 'llvm-nm.exe')
if ($LASTEXITCODE -ne 0) { throw 'Dhrystone build failed.' }
$linuxPath = (& wsl -d $Distribution --exec wslpath -u $repoPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path in WSL.' }
$runArgs = @('python3', '-B', 'sim/cpu/bench/run_bench.py', '--benchmark', 'dhrystone')
if ($Record) { $runArgs += '--record' }
& wsl -d $Distribution --cd $linuxPath --exec @runArgs
if ($LASTEXITCODE -ne 0) { throw 'Dhrystone simulation failed.' }
