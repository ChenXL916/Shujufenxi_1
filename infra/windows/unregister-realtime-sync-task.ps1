[CmdletBinding()]
param(
    [string]$TaskName = 'LiveOps-Realtime-Sync'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$serviceScript = Join-Path $root 'scripts\realtime_sync_service.py'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$serviceProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq 'python.exe' -and
        $_.CommandLine -like "*$serviceScript*"
    }
foreach ($process in $serviceProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Output "Removed scheduled task: $TaskName"
