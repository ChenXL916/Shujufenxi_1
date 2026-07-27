[CmdletBinding()]
param(
    [string]$TaskName = 'LiveOps-Gateway'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$serviceScript = Join-Path $root 'scripts\gateway_service.py'
$apiDirectory = Join-Path $root 'apps\api'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$serviceProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        ($_.Name -eq 'python.exe' -and $_.CommandLine -like "*$serviceScript*") -or
        ($_.Name -eq 'python.exe' -and $_.CommandLine -like "*uvicorn*app.main:app*$apiDirectory*") -or
        ($_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like '*--url http://127.0.0.1:8000*')
    }
foreach ($process in $serviceProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Output "Removed scheduled task: $TaskName"
