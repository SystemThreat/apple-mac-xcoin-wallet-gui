"""XID Wallet: the desktop wallet for xCoin (XID). Windows first; it also runs on macOS and Linux for development.

    gui/.venv/bin/python gui/app.py        (Windows: gui\\.venv\\Scripts\\python gui\\app.py)

The window is the system's own web view (Edge WebView2 on Windows, WebKit on macOS). The page talks to Python
through pywebview's bridge only: no web server, no open port, nothing fetched from the internet to draw it.
"""
import sys
from pathlib import Path

import webview

from backend import Api, HERE

UI = HERE / "ui" if (HERE / "ui").exists() else Path(__file__).resolve().parent / "ui"


def main():
    api = Api()
    window = webview.create_window("XID Wallet", url=(UI / "index.html").as_uri(), js_api=api,
                                   width=1180, height=800, min_size=(880, 620), background_color="#0b0c08")
    api.window = window
    webview.start(debug="--debug" in sys.argv, http_server=False, private_mode=True)


if __name__ == "__main__":
    main()
