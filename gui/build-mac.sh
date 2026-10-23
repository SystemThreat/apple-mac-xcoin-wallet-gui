#!/bin/bash
# Build XID Wallet.app for macOS (Apple Silicon) and, with --install, put it in /Applications.
#
#   gui/build-mac.sh             → dist/XID Wallet.app
#   gui/build-mac.sh --install   → also quits a running copy, installs to /Applications and opens it
#
# The same app as the Windows build (gui/app.py, gui/backend.py, gui/ui): pywebview draws the window with macOS's own
# WebKit, the wallet engine is wallet_cli.py, and the offline signer is the native keytool built by ./build.sh.
# The icon is the macOS squircle from gui/assets/make_mac_icon.py. The app is ad-hoc signed: it runs on the Mac
# that built it; a download for other Macs needs a Developer ID signature and notarization.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' gui/backend.py)"
APP="dist/XID Wallet.app"

echo "== keytool (arm64)"
./build.sh >/dev/null
./xcoin-wallet _v3vectors >/dev/null 2>&1 || { echo "keytool failed its witness v3 golden vectors"; exit 1; }

echo "== icon"
[ -f gui/assets/xid-wallet.icns ] || (cd gui/assets && python3 make_mac_icon.py)

echo "== build environment"
VENV=gui/.venv-mac-build
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r gui/requirements.txt "pyinstaller>=6.16"

echo "== app $VERSION"
UI=gui/ui
rm -rf build "$APP"
"$VENV/bin/pyinstaller" --noconfirm --clean --windowed --log-level WARN --name "XID Wallet" \
  --icon gui/assets/xid-wallet.icns --osx-bundle-identifier com.distributedledgertechnologies.xidwallet \
  --paths "$ROOT" --hidden-import card_seed --hidden-import wallet_cli \
  --add-data "$UI/index.html:ui" --add-data "$UI/app.js:ui" --add-data "$UI/styles.css:ui" --add-data "$UI/fonts.css:ui" \
  --add-data "$UI/identicon.js:ui" --add-data "$UI/fonts:ui/fonts" \
  --add-binary "xcoin-wallet:." \
  gui/app.py

echo "== Info.plist"
"$VENV/bin/python" - "$APP/Contents/Info.plist" "$VERSION" <<'PY'
import plistlib, sys
p, v = sys.argv[1], sys.argv[2]
d = plistlib.load(open(p, "rb"))
d.update({"CFBundleDisplayName": "XID Wallet", "CFBundleName": "XID Wallet", "CFBundleShortVersionString": v.split("-")[0],
          "CFBundleVersion": v, "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
          "LSApplicationCategoryType": "public.app-category.finance", "NSHumanReadableCopyright": "Distributed Ledger Technologies"})
plistlib.dump(d, open(p, "wb"))
PY
codesign --force --deep -s - "$APP" >/dev/null 2>&1
codesign --verify --deep "$APP" && echo "signed (ad-hoc)"
[ -x "$APP/Contents/Frameworks/xcoin-wallet" ] || [ -x "$APP/Contents/Resources/xcoin-wallet" ] || { echo "keytool missing from the app"; exit 1; }
du -sh "$APP" | sed 's/^/size: /'

if [ "${1:-}" = "--install" ]; then
  echo "== install"
  osascript -e 'tell application "XID Wallet" to quit' >/dev/null 2>&1 || true
  sleep 1
  rm -rf "/Applications/XID Wallet.app"
  ditto "$APP" "/Applications/XID Wallet.app"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "/Applications/XID Wallet.app" || true
  touch "/Applications/XID Wallet.app"
  killall Dock 2>/dev/null || true       # the Dock reads the new icon
  open "/Applications/XID Wallet.app"
  echo "installed: /Applications/XID Wallet.app"
fi
