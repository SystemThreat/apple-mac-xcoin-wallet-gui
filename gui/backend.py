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
        self.pub = None          # public data of index 0 and the identity, derived at unlock (no seed kept)

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
            lines = [l for l in err.getvalue().splitlines() if l.strip()]
            errs = [l for l in lines if l.startswith("error: ")]
            msg = (errs[-1] if errs else (lines[-1] if lines else "")) or text or f"the wallet stopped (code {rc})"
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
        """Open the wallet once (one passphrase check, or one card tap) and keep only public data: the
        index-0 addresses and scripts and the identity. Balances need nothing more; signing opens it again."""
        hrp = self.settings["hrp"]
        err = io.StringIO()
        with self._lock:
            w.PASSPHRASE_FROM_FD = passphrase
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    seed = w.read_seed(self.file)
                    try:
                        zero = w.derive_offline(seed, 0, hrp)
                        ident = w.derive_offline(seed, IDENTITY_INDEX, hrp)
                    finally:
                        seed = None
            except w.WalletError as e:
                if w.NO_TERMINAL in str(e): raise w.WalletError("That passphrase does not open this wallet.")
                raise
            except Exception as e:
                line = w.card_error_line(e, "unlock")
                if line is None: raise
                raise w.WalletError(line)
            finally:
                w.PASSPHRASE_FROM_FD = None
        self.pub = {"address": zero["address"], "scriptPubKey": zero["scriptPubKey"],
                    "carried_address": zero["carried_address"], "carried_scriptPubKey": zero["carried_scriptPubKey"],
                    "identity": ident["identity"], "hrp": hrp}
        self._passphrase, self._touched = passphrase, time.monotonic()

    def lock(self):
        self._passphrase = None
        self.pub = None

    def scan(self):
        """UTXOs of index 0 (both script forms) through the explorer, from the public scripts alone."""
        if not self.unlocked or not self.pub: raise w.WalletError("The wallet is locked.")
        self._touched = time.monotonic()
        rpc = w.ExplorerRPC(self.settings["explorer"], self.settings["hrp"])
        kinds = {self.pub["scriptPubKey"]: "two_leaf", self.pub["carried_scriptPubKey"]: "carried"}
        result = w.tag_kinds(w.scan(rpc, list(kinds)), kinds)
        mature, immature = w.classify_utxos(result)
        return result, mature, immature

    @property
    def unlocked(self):
        if self._passphrase is not None and time.monotonic() - self._touched > IDLE_LOCK_SECONDS: self.lock()
        return self._passphrase is not None


VERSION = "2.0.0-test1"
_SELFTEST = None


def keytool_selftest():
    """The keytool replays the node's witness v3 golden vectors once per run: a build that fails them must not sign."""
    global _SELFTEST
    if _SELFTEST is None:
        import subprocess
        tool = w.keytool_path()
        if not tool:
            _SELFTEST = "the keytool (xcoin-wallet) is missing next to the wallet engine"
        else:
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                r = subprocess.run([str(tool), "_v3vectors"], capture_output=True, timeout=60, creationflags=flags)
                _SELFTEST = "ok" if r.returncode == 0 else f"the keytool failed its self-test: {r.stderr.decode(errors='replace').strip()[:300]}"
            except Exception as e:
                _SELFTEST = f"the keytool could not run: {e}"
    return _SELFTEST


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
                    "version": VERSION, "platform": sys.platform, "card_software": w.card_modules_missing() is None,
                    "selftest": keytool_selftest()}
        return self._wrap(go)

    def set_setting(self, key, value):
        def go():
            if key not in ("theme", "explorer", "hrp", "file"): raise w.WalletError(f"unknown setting {key}")
            if key == "hrp" and value not in ("xpa", "txa"): raise w.WalletError("network must be xpa (mainnet) or txa (testnet)")
            if key == "theme" and value not in ("system", "light", "dark"): raise w.WalletError("theme must be system, light or dark")
            if key in ("file", "hrp"): self.e.lock()
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
            picked = self.window.create_file_dialog(webview.FileDialog.OPEN, directory=str(Path.home() / ".xcoin"),
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
            payment_index(index)
            if not self.e.unlocked or not self.e.pub: raise w.WalletError("The wallet is locked.")
            p = self.e.pub
            return {"address": p["address"], "carried_address": p["carried_address"], "index": 0, "qr": qr_svg(p["address"])}
        return self._wrap(go)

    def identity(self):
        def go():
            if not self.e.unlocked or not self.e.pub: raise w.WalletError("The wallet is locked.")
            return {"identity": self.e.pub["identity"], "index": IDENTITY_INDEX}
        return self._wrap(go)

    # ── chain ──
    def balance(self, index=0):
        def go():
            payment_index(index)
            result, mature, immature = self.e.scan()
            sp = sum((u["amount"] for u in mature), w.Decimal(0)); im = sum((u["amount"] for u in immature), w.Decimal(0))
            return {"address": self.e.pub["address"], "spendable": w.fmt8(sp), "immature": w.fmt8(im), "total": w.fmt8(sp + im),
                    "utxos": len(mature) + len(immature), "height": result.get("height")}
        return self._wrap(go)

    def coins(self, index=0):
        """The unspent outputs (what the explorer can list; full history needs a node or the explorer's page)."""
        def go():
            payment_index(index)
            _, mature, immature = self.e.scan()
            return [{"txid": u["txid"], "vout": u["vout"], "amount": w.fmt8(u["amount"]), "kind": u["kind"], "height": u.get("height"),
                     "confirmations": u["confirmations"], "coinbase": bool(u.get("coinbase")), "spendable": u not in immature,
                     **({"blocks_to_maturity": u["blocks_to_maturity"]} if u in immature else {})} for u in mature + immature]
        return self._wrap(go)

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
            picked = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename=Path(self.e.file).name)
            if not picked: return None
            dest = picked if isinstance(picked, str) else picked[0]
            return self.e.run("backup", dest, use_backend=False)
        return self._wrap(go)

    # ── NTAG 424 DNA card wallets ──
    def card_create(self, passphrase, label="primary", permanent=False, path=None):
        """A one-file card wallet: the card's keys live in the .mmm under the passphrase. Resettable unless
        `permanent` (a sealed card can never be reset or reused). Needs the card on the reader."""
        def go():
            if len(passphrase) < 8: raise w.WalletError("use a passphrase of at least 8 characters")
            before = self.e.settings["file"]
            if path: self.e.settings["file"] = path
            elif Path(self.e.file).exists():
                d = Path(self.e.file).parent
                self.e.settings["file"] = str(next(d / f"card-wallet-{i}.mmm" for i in range(1, 1000) if not (d / f"card-wallet-{i}.mmm").exists()))
            argv = ["new", "--card", "--one-file", "--offline", "--label", (label or "primary")[:32]]
            if not permanent: argv.append("--resettable")
            try:
                made = self.e.run(*argv, passphrase=passphrase, use_backend=False)
            except Exception:
                self.e.settings["file"] = before   # nothing was made: keep the wallet that was open
                raise
            self.e.save_settings()
            return made
        return self._wrap(go)

    def card_test(self):
        return self._wrap(lambda: self.e.run("card-test", use_backend=False))

    def card_status(self):
        return self._wrap(lambda: self.e.run("card-status", use_backend=False))

    def card_reset(self):
        def go():
            out = self.e.run("card-reset", "--yes", use_backend=False)
            self.e.lock()
            return out
        return self._wrap(go)

    def copy(self, text):
        """Clipboard through the engine's own helper (pbcopy / clip / xclip)."""
        return self._wrap(lambda: (w.clipboard_copy(text), True)[1])
