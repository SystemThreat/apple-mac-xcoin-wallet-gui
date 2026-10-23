# XID Wallet for Mac: how the app is built

The graphical wallet for xCoin (XID) on macOS, in the acid lime brutalist look with a day (light) and a night (dark) mode. Build and install instructions for users are in the [repository README](../README.md).

## How it is built

| Part | What it is |
|---|---|
| `app.py` | Opens the window. pywebview draws it with macOS's own WebKit. The page talks to Python through pywebview's bridge only: there is no web server, no open port, and nothing is fetched from the internet to draw the app. |
| `backend.py` | Runs the wallet engine's own commands (`wallet_cli.py`) in-process, with JSON output. Coin selection, fees, offline signing with the keytool, and every safety check are the same code the 370 tests cover; nothing about money is written twice. |
| `ui/` | The screens: `index.html`, `styles.css` (color tokens, light and dark), `app.js`, the bundled fonts (Big Shoulders Display and IBM Plex, OFL), and `identicon.js`, the xCoin tetromino identicon used by MMM, superknet.com and the forum. |
| `ui/preview.html`, `ui/dev-mock.js`, `ui/dev-sample.js` | Development only, never packaged. The real screens with a stand-in backend and sample data, so any browser can show every screen: `?screen=welcome\|unlock\|overview\|receive\|send\|coins\|identity\|settings&theme=light\|dark`. |
| `build-mac.sh` | Builds and checks the keytool, packages `dist/XID Wallet.app` with PyInstaller (pyscard included for card wallets), sets the bundle's name, version and category, signs it ad hoc; `--install` puts it in `/Applications` and refreshes the Dock. |
| `assets/make_mac_icon.py` | Draws the squircle icon (below) and packs `xid-wallet.icns`. |

**Keys and the identity**
- **Funds live at index 0.** Receive, Overview, Send and Coins all use it.
- **The XID identity is key index 99,999,999**, the 100-millionth key, and AYEDEX uses the same key. It is a public name: nothing can be paid to it.
- **Nobody can trace the identity to your balance.** Every key index is its own SHAKE-256 child of the seed, so the identity says nothing about index 0.
- An xid1 identity does reveal the simplest (single-leaf) address of its own key. So the app refuses to receive at, show, or spend from index 99,999,999.

**The passphrase**
- It reaches the engine the way a parent program hands it over (the `--passphrase-fd` channel), never through the environment.
- The app keeps it in memory only while the wallet is unlocked: it is dropped when you lock, and after 10 minutes without use.
- The seed is decrypted for each action and never kept.

## Forum sign-in (MineDifferent)

Identity, **Sign in to MineDifferent**:
1. The app asks minedifferent.com for a challenge (`POST /api/challenge/new`).
2. It signs the challenge's four-line message with the XID identity (key 99,999,999) through the engine's `signmessage`, on this Mac.
3. It also signs the challenge with key 101 of the same wallet, adding a line that names the new identity (`carry-to: xid1…`). Key 101 is the key NerdMiner and MMM signed in with, so the forum moves an account that key holds to the XID identity, once (name, threads, posts, chat, role).
4. It posts the identity, its public key and the signature, plus key 101's (`POST /api/challenge/<id>/solve`).
5. It opens the one-time sign-in link the forum returns in the browser.

Only public data leaves the computer. The forum account is the `xid1…` of key 99,999,999.

## The icon

`assets/make_mac_icon.py` draws the official xCoin mark (the black XID glyph, 1024-unit outline of xcoin.svg) on an acid lime squircle, on Apple's icon grid: a 1024 px canvas, an 824 px body with continuous superellipse corners (exponent 5), and a soft shadow. Google Chrome draws it, then `sips` makes every size from 16 to 1024 px and `iconutil` packs `xid-wallet.icns`. The corners are transparent, so the Dock shows the squircle alone.

```bash
python3 gui/assets/make_mac_icon.py      # after changing the drawing; then gui/build-mac.sh --install
```

## Run it while developing

```bash
python3 -m venv gui/.venv && gui/.venv/bin/pip install -r gui/requirements.txt pyscard
./build.sh                    # the keytool, next to wallet_cli.py
gui/.venv/bin/python gui/app.py
```

Settings are kept in `~/.xcoin/gui-settings.json` and are not secret: the theme, the network, the explorer, and which wallet file is open. Wallet files are the CLI's `.mmm` files, so the app and the CLI open the same wallet.

## Not in this version yet

| Feature | Status |
|---|---|
| A download for other Macs | Needs an Apple Developer ID signature and notarization; the ad hoc signature works only on the Mac that built the app. |
| Intel Macs | The keytool is built for `arm64` only. |
| Full payment history | The explorer has no history API, so the app lists the coins you hold and links to the explorer's address page. With your own node, the CLI's `history` works. |
| A local node | The CLI already talks to a node by RPC. The app uses the explorer for now. |
