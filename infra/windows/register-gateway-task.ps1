[CmdletBinding()]
param(
    [string]$TaskName = 'LiveOps-Gateway'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root 'apps\api\.venv\Scripts\python.exe'
$serviceScript = Join-Path $root 'scripts\gateway_service.py'
$cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

foreach ($requiredPath in @($python, $serviceScript, $cloudflared)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Missing gateway runtime file: $requiredPath"
    }
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI is required to publish the current Quick Tunnel origin.'
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
    -Description 'Live Ops FastAPI and Cloudflare gateway with automatic runtime-origin publication.' `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State, Author, Description
