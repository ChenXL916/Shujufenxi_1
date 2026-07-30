[CmdletBinding()]
param(
    [string]$EntryUrl = 'https://chenxl916.github.io/Shujufenxi_1/',
    [string]$ShortcutName = "$([char]0x76F4)$([char]0x64AD)$([char]0x8FD0)$([char]0x8425)$([char]0x9A7E)$([char]0x9A76)$([char]0x8231)"
)

$ErrorActionPreference = 'Stop'
$entry = [Uri]$EntryUrl
if ($entry.Scheme -ne 'https' -or $entry.Host -ne 'chenxl916.github.io') {
    throw 'Dashboard launcher must use the fixed HTTPS GitHub Pages entry.'
}

$desktopDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
$startupDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$shortcutLines = @(
    '[InternetShortcut]'
    "URL=$($entry.AbsoluteUri)"
    'IconFile=%SystemRoot%\System32\SHELL32.dll'
    'IconIndex=220'
)
$encoding = [Text.UTF8Encoding]::new($false)
$shortcutPaths = @(
    (Join-Path $desktopDirectory "$ShortcutName.url")
    (Join-Path $startupDirectory "$ShortcutName.url")
)

foreach ($shortcutPath in $shortcutPaths) {
    $directory = Split-Path -Parent $shortcutPath
    if (-not (Test-Path -LiteralPath $directory)) {
        throw "Missing Windows shortcut directory: $directory"
    }
    [IO.File]::WriteAllLines($shortcutPath, $shortcutLines, $encoding)
}

$shortcutPaths | ForEach-Object {
    Get-Item -LiteralPath $_ | Select-Object FullName, Length, LastWriteTime
}
