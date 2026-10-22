#!/bin/bash
# Build the PORTABLE Windows XID Wallet on a Mac: a folder that runs from a USB stick on 64-bit Windows 10/11 with
# nothing installed. It holds the official embeddable Python (signature verified), the Windows builds of the app's
# libraries, the keytool cross-compiled for Windows with zig, the wallet engine and the app.
#
#   gui/build-portable.sh            (needs: zig, python3; downloads from python.org and PyPI)
#
# Output: dist/XID Wallet/ and dist/XID-Wallet-Windows-portable-<version>.zip (+ .sha256). People extract the
# zip and double-click "XID Wallet.exe" (gui/launcher), which runs the app with the bundled Python.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
PYVER=3.12.10
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' gui/backend.py)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/xid-portable.XXXXXX"); trap 'rm -rf "$WORK"' EXIT
OUT="$ROOT/dist/XID Wallet"
command -v zig >/dev/null || { echo "needs zig (brew install zig)"; exit 1; }

echo "== keytool for Windows (zig, x86_64-windows-gnu, static)"
PQ=pqcrypto; T=x86_64-windows-gnu; mkdir -p "$WORK/o/c" "$WORK/o/m" "$WORK/o/s"
for f in $PQ/common/fips202.c $PQ/common/sha2.c $PQ/common/cleanse.c randombytes.c; do zig cc -target $T -O2 -std=c99 -c -I$PQ/common "$f" -o "$WORK/o/c/$(basename "${f%.c}").o"; done
for f in $PQ/ml-dsa-65/*.c; do zig cc -target $T -O2 -std=c99 -c -I$PQ/common -I$PQ/ml-dsa-65 "$f" -o "$WORK/o/m/$(basename "${f%.c}").o"; done
for f in $PQ/slh-dsa-sha2-128s/*.c; do zig cc -target $T -O2 -std=c99 -c -I$PQ/common -I$PQ/slh-dsa-sha2-128s "$f" -o "$WORK/o/s/$(basename "${f%.c}").o"; done
zig c++ -target $T -O2 -std=c++17 -I$PQ/common xcoin-wallet.cpp "$WORK"/o/c/*.o "$WORK"/o/m/*.o "$WORK"/o/s/*.o -lbcrypt -static -o "$WORK/xcoin-wallet.exe"

echo "== XID Wallet.exe (zig, with the xCoin icon, version and manifest)"
NUM=$(echo "$VERSION" | sed -E 's/^([0-9]+)\.([0-9]+)\.([0-9]+)(-[a-z]+([0-9]+))?.*/\1,\2,\3,\5/; s/,$/,0/')
sed -e "s/@VERSION@/$VERSION/" -e "s/@VERSION_NUM@/$NUM/" gui/launcher/xid-wallet.rc > gui/launcher/.build.rc
(cd gui/launcher && zig build-exe xid-wallet.c .build.rc -target $T -lc -lshell32 -luser32 -O ReleaseSmall --subsystem windows \
  -fstrip --name xid-wallet -femit-bin="$WORK/XID Wallet.exe") ; rm -f gui/launcher/.build.rc
test -f "$WORK/XID Wallet.exe"

echo "== embeddable Python $PYVER (python.org, Sigstore-verified)"
Z="python-$PYVER-embed-amd64.zip"
curl -fsS -o "$WORK/$Z" "https://www.python.org/ftp/python/$PYVER/$Z"
curl -fsS -o "$WORK/$Z.sigstore" "https://www.python.org/ftp/python/$PYVER/$Z.sigstore"
python3 -m venv "$WORK/sig" && "$WORK/sig/bin/pip" install -q sigstore
"$WORK/sig/bin/python" -m sigstore verify identity --bundle "$WORK/$Z.sigstore" --cert-identity thomas@python.org \
  --cert-oidc-issuer https://accounts.google.com "$WORK/$Z"

echo "== Windows libraries (cp312, win_amd64)"
python3 -m venv "$WORK/pip" && "$WORK/pip/bin/pip" install -q --upgrade pip
"$WORK/pip/bin/pip" install -q --target "$WORK/site" --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 \
  --only-binary=:all: --no-deps pywebview bottle typing_extensions pythonnet clr_loader cffi pycparser qrcode colorama cryptography pyscard truststore
"$WORK/pip/bin/pip" install -q --target "$WORK/site" --no-deps proxy_tools   # pure Python, published as source only

echo "== assemble"
rm -rf "$OUT"; mkdir -p "$OUT/runtime" "$OUT/app/gui/ui/fonts" "$OUT/app/gui/assets"
(cd "$OUT/runtime" && unzip -q "$WORK/$Z")
printf 'python312.zip\r\n.\r\nLib\\site-packages\r\n..\\app\r\n..\\app\\gui\r\nimport site\r\n' > "$OUT/runtime/python312._pth"
mkdir -p "$OUT/runtime/Lib"; cp -R "$WORK/site" "$OUT/runtime/Lib/site-packages"
find "$OUT/runtime/Lib/site-packages" -name "__pycache__" -type d -prune -exec rm -rf {} +
cp wallet_cli.py card_seed.py LICENSE "$OUT/app/"; cp "$WORK/xcoin-wallet.exe" "$OUT/app/"; cp "$WORK/XID Wallet.exe" "$OUT/"
cp gui/app.py gui/backend.py gui/shortcuts.ps1 "$OUT/app/gui/"; cp gui/assets/xid-wallet.png gui/assets/xid-wallet.ico "$OUT/app/gui/assets/"
for f in index.html app.js styles.css fonts.css identicon.js; do cp "gui/ui/$f" "$OUT/app/gui/ui/"; done
cp gui/ui/fonts/*.woff2 "$OUT/app/gui/ui/fonts/"
printf '@echo off\r\necho XID Wallet (debug): errors show in this window.\r\n"%%~dp0..\\runtime\\python.exe" "%%~dp0gui\\app.py" --debug %%*\r\npause\r\n' > "$OUT/app/XID Wallet (debug).cmd"
sed "s/@VERSION@/$VERSION/" gui/PORTABLE-README.txt | sed 's/$/\r/' > "$OUT/README.txt"

echo "== zip"
NAME="XID-Wallet-Windows-portable-$VERSION.zip"
rm -f "dist/$NAME" "dist/$NAME.sha256"
(cd dist && zip -qr -X "$NAME" "XID Wallet")
(cd dist && shasum -a 256 "$NAME" > "$NAME.sha256")
echo "built dist/$NAME ($(du -h "dist/$NAME" | cut -f1)), sha256 $(cut -d' ' -f1 "dist/$NAME.sha256")"
