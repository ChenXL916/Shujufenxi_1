[CmdletBinding()]
param(
    [string]$TaskName = 'LiveOps-Realtime-Sync'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root 'apps\api\.venv\Scripts\python.exe'
$serviceScript = Join-Path $root 'scripts\realtime_sync_service.py'
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

foreach ($requiredPath in @($python, $serviceScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing realtime sync runtime file: $requiredPath"
    }
}

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$serviceScript`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Live Ops dashboard realtime Feishu sync and alert evaluation.' `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State, Author, Description
