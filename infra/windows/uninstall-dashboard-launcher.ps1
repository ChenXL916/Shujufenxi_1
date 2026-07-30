[CmdletBinding()]
param(
    [string]$ShortcutName = "$([char]0x76F4)$([char]0x64AD)$([char]0x8FD0)$([char]0x8425)$([char]0x9A7E)$([char]0x9A76)$([char]0x8231)"
)

$ErrorActionPreference = 'Stop'
$shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)) "$ShortcutName.url")
    (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)) "$ShortcutName.url")
)

foreach ($shortcutPath in $shortcutPaths) {
    Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
}

Write-Output "Removed dashboard launchers: $ShortcutName"
