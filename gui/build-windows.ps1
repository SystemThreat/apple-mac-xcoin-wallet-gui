# Build the XID Wallet app for Windows: the native keytool (CMake, MSVC), then one folder with the program,
# its pages and the keytool (PyInstaller). Run from a "Developer PowerShell for VS" or anywhere CMake and MSVC
# are on PATH, with Python 3.12:
#
#   powershell -ExecutionPolicy Bypass -File gui\build-windows.ps1
#
# Output: dist\XID Wallet\XID Wallet.exe (and dist\XID-Wallet-windows.zip). Build it on a clean machine or in CI,
# never ship a binary built elsewhere, and publish its SHA-256 next to it.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "== keytool"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release | Out-Host
cmake --build build --config Release | Out-Host
ctest --test-dir build -C Release --output-on-failure | Out-Host
Copy-Item build\Release\xcoin-wallet.exe . -Force

Write-Host "== python packages"
python -m venv gui\.venv-build
& gui\.venv-build\Scripts\python -m pip install --upgrade pip | Out-Host
& gui\.venv-build\Scripts\python -m pip install -r gui\requirements-build.txt | Out-Host

Write-Host "== app"
$ui = Join-Path $root "gui\ui"
& gui\.venv-build\Scripts\pyinstaller --noconfirm --clean --windowed --name "XID Wallet" `
  --icon gui\assets\xid-wallet.ico --paths $root --hidden-import card_seed --hidden-import wallet_cli `
  --add-data "$ui\index.html;ui" --add-data "$ui\app.js;ui" --add-data "$ui\styles.css;ui" --add-data "$ui\fonts.css;ui" `
  --add-data "$ui\identicon.js;ui" --add-data "$ui\fonts;ui\fonts" `
  --add-binary "xcoin-wallet.exe;." `
  --distpath dist --workpath gui\build gui\app.py | Out-Host

$zip = "dist\XID-Wallet-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\XID Wallet\*" -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  XID-Wallet-windows.zip" | Out-File -Encoding ascii "dist\XID-Wallet-windows.zip.sha256"
Write-Host "built dist\XID Wallet\XID Wallet.exe"
Write-Host "      $zip  sha256 $hash"
