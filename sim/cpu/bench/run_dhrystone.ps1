# SPDX-License-Identifier: MIT
# Build Dhrystone with the installed Windows LLVM, then run and check it on the
# RTL in Ubuntu/WSL. Every run writes its result, rubric scorecard and profile to
# devlog/devlog-<commit>.md and indexes it in DEVLOG.md (AGENTS.md requires it);
# -NoDevlog skips that for throwaway runs. -Isa rv64im_zifencei builds with the
# M extension (architecture 0.4.0 and later). -Record also saves the result to
# cpu/dhrystone-results.json (cpu/dhrystone-rv64im-results.json for rv64im).
param(
    [string]$Distribution = 'Ubuntu-24.04',
    [string]$LLVMDirectory = 'C:\Program Files\LLVM\bin',
    [ValidateSet(32,64,128,256,512,1024)][int]$RamKiB = 64,
    [ValidateSet('rv64i_zifencei','rv64im_zifencei')][string]$Isa = 'rv64i_zifencei',
    [switch]$Record,
    [switch]$NoDevlog
)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$outDir = if ($Isa -eq 'rv64i_zifencei') { 'build/cpu/bench/dhrystone' } else { 'build/cpu/bench/dhrystone-' + $Isa.Split('_')[0] }
& python -B (Join-Path $PSScriptRoot 'build_bench.py') --benchmark dhrystone --ram-kib $RamKiB --isa $Isa --out-dir $outDir `
    --clang (Join-Path $LLVMDirectory 'clang.exe') `
    --objcopy (Join-Path $LLVMDirectory 'llvm-objcopy.exe') `
    --objdump (Join-Path $LLVMDirectory 'llvm-objdump.exe') `
    --nm (Join-Path $LLVMDirectory 'llvm-nm.exe')
if ($LASTEXITCODE -ne 0) { throw 'Dhrystone build failed.' }
$linuxPath = (& wsl -d $Distribution --exec wslpath -u $repoPath).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path in WSL.' }
$runArgs = @('python3', '-B', 'sim/cpu/bench/run_bench.py', '--benchmark', 'dhrystone', '--out-dir', $outDir)
if ($Record) { $runArgs += '--record' }
if (-not $NoDevlog) { $runArgs += '--devlog' }
& wsl -d $Distribution --cd $linuxPath --exec @runArgs
if ($LASTEXITCODE -ne 0) { throw 'Dhrystone simulation failed.' }
