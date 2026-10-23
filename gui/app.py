"""XID Wallet for Mac: the desktop wallet for xCoin (XID).

    gui/.venv/bin/python gui/app.py        (packaged as XID Wallet.app by gui/build-mac.sh)

The window is macOS's own WebKit web view. The page talks to Python
through pywebview's bridge only: no web server, no open port, nothing fetched from the internet to draw it.
"""
import sys
from pathlib import Path

try:   # verify HTTPS with the macOS keychain's certificate checks instead of a bundled list
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import webview

from backend import Api, HERE

UI = HERE / "ui" if (HERE / "ui").exists() else Path(__file__).resolve().parent / "ui"


def main():
    api = Api()
    window = webview.create_window("XID Wallet", url=(UI / "index.html").as_uri(), js_api=api,
                                   width=1180, height=800, min_size=(880, 620), background_color="#0b0c08")
    api._window = window   # private: pywebview neither walks nor exposes underscore names
    webview.start(debug="--debug" in sys.argv, http_server=False, private_mode=True)   # the Dock icon comes from the app bundle


if __name__ == "__main__":
    main()
