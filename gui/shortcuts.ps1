# XID Wallet: put an "XID Wallet" shortcut, with the xCoin icon, on the desktop and in the Start menu.
# Run by the app (Settings, Shortcuts). The shortcuts point at XID Wallet.exe where the folder is now:
# after moving the folder, run it again. ASCII only (Windows PowerShell 5 reads it as ANSI).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)      # this file is <root>\app\gui\shortcuts.ps1
$exe = Join-Path $root "XID Wallet.exe"
if (-not (Test-Path $exe)) { throw "missing $exe : keep everything in the XID Wallet folder together" }

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in [Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs")) {
    $path = Join-Path $dir "XID Wallet.lnk"
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $exe + ",0"
    $lnk.Description = "XID Wallet for xCoin"
    $lnk.Save()
    "made $path"
}
