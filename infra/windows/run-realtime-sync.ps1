[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root 'apps\api\.venv\Scripts\python.exe'
$serviceScript = Join-Path $root 'scripts\realtime_sync_service.py'

foreach ($requiredPath in @($python, $serviceScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing realtime sync runtime file: $requiredPath"
    }
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
& $python $serviceScript
exit $LASTEXITCODE
