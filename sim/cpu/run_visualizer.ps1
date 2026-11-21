# SPDX-License-Identifier: MIT
param([int]$Port = 0, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
& python -B (Join-Path $PSScriptRoot 'build_programs.py') --check-library
if ($LASTEXITCODE -ne 0) {
    & python -B (Join-Path $PSScriptRoot 'build_programs.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the CPU study programs.' }
}
$serverArgs = @('-B', (Join-Path $PSScriptRoot 'serve_visualizer.py'), '--port', $Port)
if ($NoOpen) { $serverArgs += '--no-open' }
& python @serverArgs
