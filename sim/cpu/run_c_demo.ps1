# SPDX-License-Identifier: MIT
param(
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$LLVMDirectory = 'C:\Program Files\LLVM\bin',
    [ValidateRange(1,20)][int]$Repetitions = 5
)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
& python -B (Join-Path $PSScriptRoot 'build_firmware.py') `
    --clang (Join-Path $LLVMDirectory 'clang.exe') `
    --objcopy (Join-Path $LLVMDirectory 'llvm-objcopy.exe') `
    --objdump (Join-Path $LLVMDirectory 'llvm-objdump.exe') `
    --source sim/cpu/c_demo.c --out-dir build/cpu/c-demo
if ($LASTEXITCODE -ne 0) { throw 'C compilation failed.' }
$linuxPath = (& wsl -d $Distribution --exec wslpath -u $repoPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path in WSL.' }
& wsl -d $Distribution --cd $linuxPath --exec python3 -B sim/cpu/run_c_demo.py --repetitions $Repetitions
if ($LASTEXITCODE -ne 0) { throw 'C demo simulation failed.' }
