"""The desktop app's bridge (gui/backend.py): the arguments it hands the engine for money-moving actions.
These pin what the app relies on: a preview never broadcasts, a send always does, and the identity's index is
never used for payments. (The engine itself is covered by the other test files.)"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "gui"))
import wallet_cli as w  # noqa: E402
_engine_can_prompt = w.can_prompt
import backend  # noqa: E402   (the app switches terminal prompts off for its process)
_app_can_prompt = w.can_prompt
w.can_prompt = _engine_can_prompt   # every other test in this run checks the engine's own behaviour

DEST = "xpa1rvs4usq5kpscw9rjp9fr2udan4qgyjkeydm3d5gvq5pcl2gege3sqhktaxh"


class TestSendArguments(unittest.TestCase):
    def setUp(self):
        self.api = backend.Api()
        self.calls = []
        self.api._e.run = lambda *argv, **k: self.calls.append(argv) or {"txid": "00" * 32, "fee": "0.00002960"}
        self.api._e.balance_view = lambda: {"balance": backend.w.Decimal("1"), "confirming": backend.w.Decimal(0)}
        self.api._e.record_send = lambda *a: None

    def test_preview_signs_without_asking_and_never_broadcasts(self):
        self.assertIn("ok", self.api.send_preview(DEST, "0.1"))
        argv = self.calls[-1]
        self.assertEqual(argv[:3], ("send", DEST, "0.1"))
        self.assertIn("--dry-run", argv)   # what keeps the preview from broadcasting
        self.assertIn("--yes", argv)       # JSON mode refuses the interactive "Type SEND" question

    def test_send_broadcasts(self):
        self.assertIn("ok", self.api.send(DEST, "0.1"))
        argv = self.calls[-1]
        self.assertIn("--yes", argv)
        self.assertNotIn("--dry-run", argv)

    def test_identity_index_is_never_a_payment_index(self):
        for call in (lambda: self.api.send_preview(DEST, "0.1", backend.IDENTITY_INDEX),
                     lambda: self.api.send(DEST, "0.1", backend.IDENTITY_INDEX)):
            self.assertIn("99,999,999", call()["error"])
        self.assertEqual(self.calls, [])

    def test_the_app_never_prompts_at_a_terminal(self):
        self.assertFalse(_app_can_prompt())


if __name__ == "__main__":
    unittest.main()


class TestBackup(unittest.TestCase):
    """The backup copy keeps the wallet's extension, even when the name typed in the save dialog has none."""
    def setUp(self):
        self.api = backend.Api()
        self.calls, self.picked = [], None
        self.api._e.run = lambda *argv, **k: self.calls.append(argv) or {"backup": argv[1]}
        self.api._window = type("Window", (), {"create_file_dialog": lambda w, *a, **k: self.picked})()
        self.api._e.settings = {**self.api._e.settings, "file": str(Path("/w") / "wallet.mmm")}

    def test_the_extension_is_there_exactly_once(self):
        for typed, saved in (("wallet001", "wallet001.mmm"), ("wallet001.mmm", "wallet001.mmm"),
                             ("wallet-001", "wallet-001.mmm"), ("Wallet.MMM", "Wallet.MMM"), ("copy.v2", "copy.v2.mmm"),
                             ("wallet001.", "wallet001.mmm"), ("wallet001.mmm.", "wallet001.mmm"),
                             ("wallet001 ", "wallet001.mmm"), ("wallet001.mmm ", "wallet001.mmm"),
                             ("my wallet 001", "my wallet 001.mmm")):
            with self.subTest(typed=typed):
                self.picked = (str(Path("/backups") / typed),)
                self.api.backup()
                self.assertEqual(self.calls[-1][:2], ("backup", str(Path("/backups") / saved)))

    def test_cancelled_dialog_copies_nothing(self):
        self.picked = None
        self.assertEqual(self.api.backup(), {"ok": None}); self.assertEqual(self.calls, [])


class TestBalanceArithmetic(unittest.TestCase):
    """The balance right after a send is plain subtraction (before - sent - fee), not 'everything went out'
    until the change confirms; and it is the same number after the block."""
    D = backend.w.Decimal
    COIN = {"txid": "aa" * 32, "vout": 0, "amount": D("0.33"), "kind": "two_leaf", "coinbase": False, "height": 8058, "confirmations": 3}
    TXID = "bb" * 32

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.saved = backend.PENDING; backend.PENDING = Path(self.tmp.name) / "pending.json"
        self.addCleanup(setattr, backend, "PENDING", self.saved)
        self.e = backend.Engine.__new__(backend.Engine)
        self.e.settings = {"file": str(Path(self.tmp.name) / "wallet.mmm"), "hrp": "xpa", "explorer": "x", "theme": "system"}
        self.view = (8060, [dict(self.COIN)], [], set())
        self.e.explorer_view = lambda: (self.view[0], [dict(u) for u in self.view[1]], list(self.view[2]), set(self.view[3]))

    def send(self, amount="0.321", fee="0.00002960", change="0.00897040"):
        sent = {"txid": self.TXID, "broadcast": True, "fee": fee, "spent": [f'{"aa" * 32}:0'],
                "change_outputs": [{"txid": self.TXID, "vout": 1, "amount": change}] if self.D(change) > 0 else []}
        self.e.record_send(sent, amount, "xpa1rdest", self.e.balance_view()["balance"])

    def test_before_and_right_after_a_send(self):
        self.assertEqual(self.e.balance_view()["balance"], self.D("0.33"))
        self.send()
        self.view = (8060, [], [], {f'{"aa" * 32}:0'})            # the explorer hides the coin a waiting send spends
        v = self.e.balance_view()
        self.assertEqual(v["balance"], self.D("0.00897040"))        # 0.33 - 0.321 - 0.0000296
        self.assertEqual((v["spendable"], v["confirming"]), (0, self.D("0.00897040")))
        (p,) = v["pending"]
        self.assertEqual((p["before"], p["amount"], p["fee"], p["after"]), ("0.33000000", "0.32100000", "0.00002960", "0.00897040"))

    def test_a_stale_scan_never_counts_the_spent_coin_twice(self):
        self.send()
        self.view = (8061, [dict(self.COIN)], [], set())             # mined, but the explorer's cached scan still lists the coin
        self.assertEqual(self.e.balance_view()["balance"], self.D("0.00897040"))

    def test_after_the_block_the_same_number_and_nothing_pending(self):
        self.send()
        change = dict(self.COIN, txid=self.TXID, vout=1, amount=self.D("0.00897040"), height=8061, confirmations=1)
        self.view = (8061, [change], [], set())
        v = self.e.balance_view()
        self.assertEqual((v["balance"], v["spendable"], v["confirming"], v["pending"]), (self.D("0.00897040"), self.D("0.00897040"), 0, []))
        self.assertEqual(self.e.pending_sends(), [])

    def test_an_exact_spend_resolves_when_its_coin_is_gone(self):
        self.send(amount="0.32997040", change="0")
        self.view = (8060, [], [], {f'{"aa" * 32}:0'})
        self.assertEqual(self.e.balance_view()["balance"], 0)
        self.view = (8061, [], [], set())
        v = self.e.balance_view()
        self.assertEqual((v["balance"], v["pending"]), (0, []))

    def test_a_send_that_never_confirms_gives_the_coins_back_after_an_hour(self):
        self.send()
        self.view = (8062, [dict(self.COIN)], [], set())             # back, unspent, out of the mempool
        self.assertEqual(self.e.balance_view()["balance"], self.D("0.00897040"))   # within the hour: still the send's arithmetic
        items = self.e.pending_sends(); items[0]["at"] -= backend.PENDING_DROP_SECONDS + 1; self.e._save_pending(items)
        v = self.e.balance_view()
        self.assertEqual((v["balance"], len(v["dropped"]), v["pending"]), (self.D("0.33"), 1, []))
