$ErrorActionPreference = 'Stop'
$linuxPath = & wsl.exe -d Ubuntu-24.04 -- wslpath -a $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path in Ubuntu.' }
& wsl.exe -d Ubuntu-24.04 -- bash ($linuxPath.TrimEnd() + '/run.sh')
if ($LASTEXITCODE -ne 0) { throw 'CPU simulation failed. Inspect the output above.' }
