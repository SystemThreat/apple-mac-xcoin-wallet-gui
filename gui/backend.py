"""The XID Wallet app's bridge to the wallet engine.

Every wallet action runs the command-line wallet's own command, in this process, with JSON output:
the same coin selection, fee rules, offline signing and safety checks the CLI's tests cover. The
passphrase reaches the engine through the channel a parent program uses (--passphrase-fd), never
the environment. The seed is decrypted per action and never kept by the app; the passphrase is kept
in memory while the wallet is unlocked and dropped on lock or after the idle timeout.
"""
import contextlib, io, json, os, sys, threading, time
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))   # PyInstaller unpacks beside the program
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import wallet_cli as w   # noqa: E402

IDENTITY_INDEX = 99_999_999          # the XID identity: key number 100,000,000 (AYEDEX uses the same key)
# Funds live at index 0 and up. Every index is its own SHAKE-256 child of the seed, so the identity says nothing
# about any other key; but an xid1 identity does reveal its own key's single-leaf address, so the app never pays
# to, shows, or spends from the identity's index.


def payment_index(index):
    i = int(index)
    if i < 0: raise w.WalletError("an address index is 0 or more")
    if i == IDENTITY_INDEX: raise w.WalletError("index 99,999,999 is your XID identity, never a payment address")
    return str(i)
DEFAULT_EXPLORER = "https://superknet.com"
SETTINGS = Path.home() / ".xcoin" / "gui-settings.json"
IDLE_LOCK_SECONDS = 10 * 60


class Engine:
    """Runs CLI commands in-process, one at a time (the engine keeps a few module-level flags)."""
    def __init__(self):
        self._lock = threading.Lock()
        self.settings = {"theme": "system", "explorer": DEFAULT_EXPLORER, "hrp": "xpa", "file": str(w.default_wallet())}
        try:
            self.settings.update(json.loads(SETTINGS.read_text()))
        except (OSError, ValueError):
            pass
        self._passphrase = None
        self._touched = 0.0

    # ── settings (nothing secret here) ──
    def save_settings(self):
        SETTINGS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(self.settings, indent=1))

    @property
    def file(self): return self.settings["file"]

    # ── running a command ──
    def run(self, *argv, passphrase=None, use_backend=True):
        base = ["--file", self.file, "--json", "--hrp", self.settings["hrp"]]
        if use_backend: base += ["--explorer", self.settings["explorer"]]
        out, err = io.StringIO(), io.StringIO()
        with self._lock:
            given = passphrase if passphrase is not None else self._session_passphrase()
            w.PASSPHRASE_FROM_FD = given
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = w.main([*base, *argv])
            except SystemExit as e:
                rc = e.code
            finally:
                w.PASSPHRASE_FROM_FD = None
        text = out.getvalue().strip()
        if rc not in (0, None):
            msg = err.getvalue().strip() or text or f"the wallet stopped (code {rc})"
            if w.NO_TERMINAL in msg:   # the engine would ask at a terminal: here that means the passphrase was wrong, or none
                raise w.WalletError("That passphrase does not open this wallet." if given else "The wallet is locked.")
            raise w.WalletError(msg[len("error: "):] if msg.startswith("error: ") else msg)
        if text.startswith(("{", "[")):
            return json.loads(text)
        return text

    # ── session ──
    def _session_passphrase(self):
        if self._passphrase is None: return None
        if time.monotonic() - self._touched > IDLE_LOCK_SECONDS:
            self.lock(); return None
        self._touched = time.monotonic()
        return self._passphrase

    def unlock(self, passphrase):
        self.run("receive", "--index", "0", passphrase=passphrase, use_backend=False)   # raises on a wrong passphrase
        self._passphrase, self._touched = passphrase, time.monotonic()

    def lock(self):
        self._passphrase = None

    @property
    def unlocked(self):
        return self._passphrase is not None and time.monotonic() - self._touched <= IDLE_LOCK_SECONDS


def qr_svg(text):
    """A QR code as SVG markup (black modules, no background: the page sets the paper colour)."""
    import qrcode
    from qrcode.image.svg import SvgPathImage
    img = qrcode.make(text, image_factory=SvgPathImage, box_size=10, border=0,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    buf = io.BytesIO(); img.save(buf)
    return buf.getvalue().decode()


class Api:
    """What the page can call (window.pywebview.api.*). Every method returns {"ok": ...} or {"error": "..."}."""
    def __init__(self):
        self.e = Engine()
        self.window = None

    def _wrap(self, fn, *a, **k):
        try:
            return {"ok": fn(*a, **k)}
        except w.WalletError as ex:
            return {"error": str(ex)}
        except Exception as ex:   # never a traceback in the window
            return {"error": f"{type(ex).__name__}: {ex}"}

    # ── state and settings ──
    def state(self):
        def go():
            fmt, card = w._wallet_format(self.e.file)
            return {"file": self.e.file, "exists": Path(self.e.file).exists(), "format": fmt, "card": card,
                    "unlocked": self.e.unlocked, "settings": self.e.settings, "identity_index": IDENTITY_INDEX,
                    "version": "2.0.0-dev", "platform": sys.platform}
        return self._wrap(go)

    def set_setting(self, key, value):
        def go():
            if key not in ("theme", "explorer", "hrp", "file"): raise w.WalletError(f"unknown setting {key}")
            if key == "hrp" and value not in ("xpa", "txa"): raise w.WalletError("network must be xpa (mainnet) or txa (testnet)")
            if key == "theme" and value not in ("system", "light", "dark"): raise w.WalletError("theme must be system, light or dark")
            if key == "file": self.e.lock()
            self.e.settings[key] = value; self.e.save_settings()
            return self.e.settings
        return self._wrap(go)

    def wallets(self):
        def go():
            d = Path.home() / ".xcoin"
            return [str(p) for p in sorted(d.glob("*.mmm"))] if d.exists() else []
        return self._wrap(go)

    def choose_wallet_file(self):
        def go():
            import webview
            picked = self.window.create_file_dialog(webview.OPEN_DIALOG, directory=str(Path.home() / ".xcoin"),
                                                    file_types=("XID wallet (*.mmm)", "All files (*.*)"))
            if not picked: return None
            self.e.lock(); self.e.settings["file"] = picked[0]; self.e.save_settings()
            return picked[0]
        return self._wrap(go)

    # ── wallet lifecycle ──
    def create(self, passphrase, path=None):
        def go():
            if len(passphrase) < 8: raise w.WalletError("use a passphrase of at least 8 characters")
            if path: self.e.settings["file"] = path
            self.e.save_settings()
            made = self.e.run("new", "--offline", passphrase=passphrase, use_backend=False)
            seed = self.e.run("seed", "--yes", passphrase=passphrase, use_backend=False)["seed"]
            self.e.unlock(passphrase)
            return {"file": made["file"], "seed": seed}
        return self._wrap(go)

    def restore(self, seed, passphrase, path=None):
        def go():
            s = "".join(seed.split()).lower()
            if not w._valid_seed(s): raise w.WalletError("that is not a valid seed: 64 hexadecimal characters (0-9, a-f)")
            if len(passphrase) < 8: raise w.WalletError("use a passphrase of at least 8 characters")
            if path: self.e.settings["file"] = path
            self.e.save_settings()
            self.e.run("restore", s, passphrase=passphrase, use_backend=False)
            self.e.unlock(passphrase)
            return {"file": self.e.file}
        return self._wrap(go)

    def unlock(self, passphrase):
        return self._wrap(lambda: (self.e.unlock(passphrase), True)[1])

    def lock(self):
        return self._wrap(lambda: (self.e.lock(), True)[1])

    def reveal_seed(self, passphrase):
        return self._wrap(lambda: self.e.run("seed", "--yes", passphrase=passphrase, use_backend=False)["seed"])

    # ── addresses and identity ──
    def receive(self, index=0):
        def go():
            info = self.e.run("receive", "--index", payment_index(index), use_backend=False)
            info.pop("identity", None)                       # a payment key's handle is not shown: identity lives at its own index
            info["qr"] = qr_svg(info["address"])
            return info
        return self._wrap(go)

    def identity(self):
        def go():
            info = self.e.run("receive", "--index", str(IDENTITY_INDEX), use_backend=False)
            return {"identity": info["identity"], "index": IDENTITY_INDEX}
        return self._wrap(go)

    # ── chain ──
    def balance(self, index=0):
        return self._wrap(lambda: self.e.run("balance", "--index", payment_index(index)))

    def coins(self, index=0):
        """The unspent outputs (what the explorer can list; full history needs a node or the explorer's page)."""
        return self._wrap(lambda: self.e.run("utxos", "--index", payment_index(index)))

    def send_preview(self, destination, amount, index=0):
        return self._wrap(lambda: self.e.run("send", destination.strip(), str(amount).strip(), "--index", payment_index(index), "--dry-run"))

    def send(self, destination, amount, index=0):
        return self._wrap(lambda: self.e.run("send", destination.strip(), str(amount).strip(), "--index", payment_index(index), "--yes"))

    def open_url(self, url):
        """Explorer links open in the system browser; only http(s) links."""
        def go():
            import webbrowser
            if not url.startswith(("https://", "http://")): raise w.WalletError("only web links open from the wallet")
            webbrowser.open(url); return True
        return self._wrap(go)

    def backup(self):
        def go():
            import webview
            picked = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=Path(self.e.file).name)
            if not picked: return None
            dest = picked if isinstance(picked, str) else picked[0]
            return self.e.run("backup", dest, use_backend=False)
        return self._wrap(go)

    def copy(self, text):
        """Clipboard through the engine's own helper (pbcopy / clip / xclip)."""
        return self._wrap(lambda: (w.clipboard_copy(text), True)[1])
