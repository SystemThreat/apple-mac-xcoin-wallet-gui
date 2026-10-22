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
