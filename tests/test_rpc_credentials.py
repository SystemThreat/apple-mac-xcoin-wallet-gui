#!/usr/bin/env python3
"""The node RPC login: which source wins, where the node's .cookie is found, and that no
error ever shows a cookie or a password. Offline: temp directories, fake cookies, and a
faked urlopen; nothing reaches a node."""

import base64, io, json, os, sys, tempfile, unittest, urllib.error
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wallet_cli as w

SECRET = "c0ffee5ecret" * 4            # stands for any cookie password; must never be printed
COOKIE = f"__cookie__:{SECRET}\n"

class Creds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"; self.home.mkdir()
        env = {k: v for k, v in os.environ.items()
               if k not in ("XCOIN_RPC_USER", "XCOIN_RPC_PASSWORD", "XCOIN_EXPLORER", "XCOIN_WALLET_PASSPHRASE")}
        env["HOME"] = str(self.home)       # ~/.xcoin and the node's default datadir live here
        p = mock.patch.dict(os.environ, env, clear=True); p.start(); self.addCleanup(p.stop)

    def write(self, path, text, mode=0o600):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text); os.chmod(path, mode); return path

    def node(self, conf_text="server=1\nrpcport=8332\n", cookie=COOKIE, sub=""):
        """A node data directory with its own conf and (unless None) a cookie in `sub`."""
        d = self.root / "node"
        conf = self.write(d / "mainnet.conf", conf_text)
        if cookie is not None: self.write(d / sub / ".cookie", cookie)
        return d, conf

    def args(self, *argv):
        return w.parser().parse_args([*argv, "info"])

    def creds(self, *argv):
        a = self.args(*argv)
        return w.rpc_credentials(a, w.parse_conf(a.config))

    def error(self, *argv):
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args(*argv))
        msg = str(cm.exception)
        self.assertNotIn(SECRET, msg)
        return msg

class TestOrder(Creds):
    def test_the_reported_case_node_conf_without_rpc_cookie(self):
        # --config ~/xcoin-mainnet/mainnet.conf: the node's own conf ([main] section, no rpcuser), cookie beside it
        d, conf = self.node("server=1\n[main]\nlisten=1\nrpcport=8332  # mainnet\nrpcbind=127.0.0.1\n")
        rpc = w.RPC(self.args("--config", str(conf)))
        self.assertEqual((rpc.user, rpc.password), ("__cookie__", SECRET))
        self.assertEqual(rpc.port, 8332)
        self.assertEqual(rpc.auth_source, f"the node's cookie {d / '.cookie'}")

    def test_command_line_login_wins(self):
        d, conf = self.node("rpcuser=confu\nrpcpassword=confp\n")
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        other = self.write(self.root / "other.cookie", "__cookie__:other\n")
        self.assertEqual(self.creds("--config", str(conf), "--rpc-cookie", str(other), "--rpc-user", "u", "--rpc-password", "p"),
                         ("u", "p", "--rpc-user/--rpc-password"))

    def test_one_command_line_half_is_completed_from_conf_then_env(self):
        d, conf = self.node("rpcuser=confu\n")
        os.environ.update(XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf), "--rpc-user", "u")[:2], ("u", "envp"))
        self.assertEqual(self.creds("--config", str(conf), "--rpc-password", "p")[:2], ("confu", "p"))

    def test_one_command_line_half_alone_is_an_error_not_a_cookie(self):
        d, conf = self.node()
        msg = self.error("--config", str(conf), "--rpc-user", "u")
        self.assertIn("give --rpc-password too", msg)
        msg = self.error("--config", str(conf), "--rpc-password", SECRET)
        self.assertIn("give --rpc-user too", msg)

    def test_rpc_cookie_beats_conf_cookie_autodetect_and_passwords(self):
        explicit = self.write(self.root / "elsewhere" / "my.cookie", "__cookie__:explicit\n")
        conf_cookie = self.write(self.root / "conf.cookie", "__cookie__:fromconf\n")
        d, conf = self.node(f"rpccookiefile={conf_cookie}\nrpcuser=confu\nrpcpassword=confp\n")
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf), "--rpc-cookie", str(explicit)),
                         ("__cookie__", "explicit", f"the cookie {explicit}"))

    def test_rpc_cookie_expands_tilde(self):
        self.write(self.home / "nodedata" / ".cookie", "__cookie__:tilde\n")
        self.assertEqual(self.creds("--config", str(self.root / "none.conf"), "--rpc-cookie", "~/nodedata/.cookie")[:2],
                         ("__cookie__", "tilde"))

    def test_conf_rpccookiefile_beats_autodetect(self):
        conf_cookie = self.write(self.root / "conf.cookie", "__cookie__:fromconf\n")
        d, conf = self.node(f"rpccookiefile={conf_cookie}\n")      # d/.cookie exists too
        user, password, source = self.creds("--config", str(conf))
        self.assertEqual((user, password), ("__cookie__", "fromconf"))
        self.assertIn(f"rpccookiefile= in {conf}", source)

    def test_conf_rpccookiefile_relative_is_under_the_chain_datadir(self):
        # the node reads a relative -rpccookiefile under its chain's data directory
        d, conf = self.node("testnet=1\nrpccookiefile=auth/rpc.cookie\n", cookie=None)
        self.write(d / "testneta" / "auth" / "rpc.cookie", "__cookie__:relative\n")
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", "relative"))

    def test_conf_rpccookiefile_missing_is_an_error(self):
        d, conf = self.node(f"rpccookiefile={self.root / 'gone.cookie'}\nrpcuser=confu\nrpcpassword=confp\n")
        msg = self.error("--config", str(conf))
        self.assertIn(str(self.root / "gone.cookie"), msg); self.assertIn("Is the node running", msg)

    def test_autodetected_cookie_beats_conf_rpcuser(self):
        d, conf = self.node("rpcuser=confu\nrpcpassword=confp\n")
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", SECRET))

    def test_conf_rpcuser_when_no_cookie_and_beats_env(self):
        d, conf = self.node("rpcuser=confu\nrpcpassword=confp\n", cookie=None)
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf)), ("confu", "confp", f"rpcuser/rpcpassword in {conf}"))

    def test_env_is_the_last_resort(self):
        d, conf = self.node(cookie=None)
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf)), ("envu", "envp", "XCOIN_RPC_USER/XCOIN_RPC_PASSWORD"))

    def test_conf_and_env_halves_combine_as_before(self):
        d, conf = self.node("rpcuser=confu\n", cookie=None)
        os.environ.update(XCOIN_RPC_PASSWORD="envp")
        user, password, source = self.creds("--config", str(conf))
        self.assertEqual((user, password), ("confu", "envp")); self.assertIn("XCOIN_RPC_PASSWORD", source)

class TestAutoDetect(Creds):
    def test_datadir_in_conf(self):
        data = self.root / "chaindata"
        self.write(data / ".cookie", "__cookie__:datadir\n")
        d, conf = self.node(f"datadir={data}\n")                    # d/.cookie exists but is not the datadir
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", "datadir"))

    def test_relative_datadir_is_beside_the_conf(self):
        d, conf = self.node("datadir=chain\n", cookie=None)
        self.write(d / "chain" / ".cookie", "__cookie__:reldatadir\n")
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", "reldatadir"))

    def test_chain_subdirectories(self):
        for conf_text, sub in (("testnet=1\n", "testneta"), ("chain=test\n", "testneta"), ("testnet=\n", "testneta"),
                               ("regtest=1\n", "regtest"), ("chain=regtest\n", "regtest")):
            with self.subTest(conf_text=conf_text):
                d, conf = self.node(conf_text, cookie="__cookie__:mainnet\n")
                self.write(d / sub / ".cookie", f"__cookie__:{sub}\n")
                self.assertEqual(self.creds("--config", str(conf))[1], sub)

    def test_mainnet_conf_never_takes_a_testnet_cookie(self):
        for conf_text in ("server=1\n", "testnet=0\n", "chain=main\n"):
            with self.subTest(conf_text=conf_text):
                d, conf = self.node(conf_text, cookie=None)
                self.write(d / "testneta" / ".cookie", "__cookie__:testnet\n")
                self.write(d / "regtest" / ".cookie", "__cookie__:regtest\n")
                msg = self.error("--config", str(conf))
                self.assertIn(str(d / ".cookie"), msg)

    def test_default_xcoin_home(self):
        self.write(self.home / ".xcoin" / ".cookie", "__cookie__:xcoinhome\n")
        user, password, source = self.creds("--config", str(self.root / "missing" / "nex.conf"))
        self.assertEqual(password, "xcoinhome"); self.assertIn(str(self.home / ".xcoin" / ".cookie"), source)

    def test_default_config_is_the_xcoin_home(self):
        # no --config at all: the default ~/.xcoin/nex.conf (absent here) leads to ~/.xcoin/.cookie
        self.write(self.home / ".xcoin" / ".cookie", "__cookie__:defaultconf\n")
        a = w.parser().parse_args(["--config", str(self.home / ".xcoin" / "nex.conf"), "info"])
        self.assertEqual(w.rpc_credentials(a, {})[1], "defaultconf")

    def test_the_nodes_built_in_datadir(self):
        for platform, where in (("darwin", Path("Library") / "Application Support" / "NEX"), ("linux", Path(".nex"))):
            with self.subTest(platform=platform), mock.patch.object(w.sys, "platform", platform):
                self.write(self.home / where / ".cookie", f"__cookie__:{platform}\n")
                self.assertEqual(self.creds("--config", str(self.root / "missing" / "nex.conf"))[1], platform)

    def test_conf_directory_before_the_defaults(self):
        self.write(self.home / ".xcoin" / ".cookie", "__cookie__:xcoinhome\n")
        d, conf = self.node()
        self.assertEqual(self.creds("--config", str(conf))[1], SECRET)

    def test_cookie_is_read_fresh_every_run(self):
        d, conf = self.node()
        self.assertEqual(w.RPC(self.args("--config", str(conf))).password, SECRET)
        self.write(d / ".cookie", "__cookie__:afterrestart\n")        # the node restarted
        self.assertEqual(w.RPC(self.args("--config", str(conf))).password, "afterrestart")

    def test_unreadable_autodetected_cookie_falls_through_to_conf_login(self):
        if os.geteuid() == 0: self.skipTest("root reads any file")
        d, conf = self.node("rpcuser=confu\nrpcpassword=confp\n", cookie=COOKIE)
        os.chmod(d / ".cookie", 0)
        self.addCleanup(os.chmod, d / ".cookie", 0o600)
        self.assertEqual(self.creds("--config", str(conf))[:2], ("confu", "confp"))

class TestErrors(Creds):
    def test_missing_names_every_place_tried_and_what_to_do(self):
        d, conf = self.node(cookie=None)
        msg = self.error("--config", str(conf))
        self.assertIn("RPC credentials missing", msg)
        for p in (d / ".cookie", self.home / ".xcoin" / ".cookie"): self.assertIn(str(p), msg)
        for hint in ("--config <the node's conf>", "--rpc-cookie", "--explorer https://superknet.com", "testneta/"):
            self.assertIn(hint, msg)
        self.assertNotIn("no such file", msg)

    def test_missing_conf_file_is_named(self):
        msg = self.error("--config", str(self.root / "typo.conf"))
        self.assertIn(f"{self.root / 'typo.conf'} (no such file)", msg)

    def test_explicit_cookie_missing(self):
        msg = self.error("--rpc-cookie", str(self.root / "nope" / ".cookie"))
        self.assertIn(str(self.root / "nope" / ".cookie"), msg); self.assertIn("Is the node running", msg)

    def test_explicit_cookie_is_a_directory(self):
        d, conf = self.node()
        msg = self.error("--rpc-cookie", str(d))
        self.assertIn("is a directory", msg); self.assertIn(str(d / ".cookie"), msg)

    def test_explicit_cookie_permission_denied(self):
        if os.geteuid() == 0: self.skipTest("root reads any file")
        d, conf = self.node()
        os.chmod(d / ".cookie", 0); self.addCleanup(os.chmod, d / ".cookie", 0o600)
        msg = self.error("--rpc-cookie", str(d / ".cookie"))
        self.assertIn("permission denied", msg); self.assertIn("-rpccookieperms=group", msg)

    def test_unreadable_autodetected_cookie_is_reported(self):
        if os.geteuid() == 0: self.skipTest("root reads any file")
        d, conf = self.node()
        os.chmod(d / ".cookie", 0); self.addCleanup(os.chmod, d / ".cookie", 0o600)
        msg = self.error("--config", str(conf))
        self.assertIn("permission denied", msg); self.assertIn("RPC credentials missing", msg)

    def test_malformed_cookie_never_shown(self):
        for bad in (SECRET, f"{SECRET}:", f":{SECRET}", f"__cookie__:{SECRET}\nsecond:{SECRET}", "", SECRET * 200,
                    "\xff\xfe" + SECRET):
            with self.subTest(bad=bad[:20]):
                p = self.root / "bad.cookie"
                p.write_bytes(bad.encode("latin-1") if bad.startswith("\xff") else bad.encode())
                msg = self.error("--rpc-cookie", str(p))
                self.assertIn("is not a node RPC cookie", msg)

    def test_malformed_conf_cookie_never_shown(self):
        bad = self.write(self.root / "bad.cookie", SECRET)
        d, conf = self.node(f"rpccookiefile={bad}\n")
        self.assertIn("is not a node RPC cookie", self.error("--config", str(conf)))

    def test_unreadable_conf_is_an_error_not_a_traceback(self):
        if os.geteuid() == 0: self.skipTest("root reads any file")
        d, conf = self.node(f"rpcpassword={SECRET}\n")
        os.chmod(conf, 0); self.addCleanup(os.chmod, conf, 0o600)
        msg = self.error("--config", str(conf))
        self.assertIn("cannot read the config", msg)

class TestConf(Creds):
    """The conf is read as the node reads it."""
    def test_comments_anywhere_on_a_line(self):
        d, conf = self.node("# a node conf\nrpcport=19432   # testnet A\nrpcconnect=10.0.0.2#lan\n[main] # section\nrpcuser=u # me\n")
        self.assertEqual(w.parse_conf(conf), {"rpcport": "19432", "rpcconnect": "10.0.0.2", "rpcuser": "u"})
        rpc = w.RPC(self.args("--config", str(conf)))
        self.assertEqual((rpc.host, rpc.port), ("10.0.0.2", 19432))

    def test_rpcpassword_is_read_whole(self):
        d, conf = self.node("rpcuser=u\nrpcpassword=a#b c \n", cookie=None)
        self.assertEqual(self.creds("--config", str(conf))[:2], ("u", "a#b c"))

    def test_bad_rpcport_is_an_error_not_a_traceback(self):
        d, conf = self.node("rpcport=eighty\n")
        self.assertIn(f"rpcport= in {conf} is not a port number", self.error("--config", str(conf)))

class TestWire(Creds):
    """The login reaches the node as HTTP Basic auth; a refusal names its source, never the secret."""
    def fake(self, status=200):
        seen = []
        def urlopen(req, timeout=60):
            seen.append(req)
            if status != 200: raise urllib.error.HTTPError(req.full_url, status, "Unauthorized", {}, io.BytesIO(b""))
            return io.BytesIO(json.dumps({"result": {"chain": "main"}, "error": None}).encode())
        p = mock.patch("urllib.request.urlopen", urlopen); p.start(); self.addCleanup(p.stop)
        return seen

    def test_cookie_sent_as_basic_auth(self):
        seen = self.fake()
        d, conf = self.node()
        self.assertEqual(w.RPC(self.args("--config", str(conf))).call("getblockchaininfo"), {"chain": "main"})
        self.assertEqual(seen[0].full_url, "http://127.0.0.1:8332/")
        self.assertEqual(seen[0].get_header("Authorization"),
                         "Basic " + base64.b64encode(f"__cookie__:{SECRET}".encode()).decode())

    def test_refused_cookie_names_the_file_not_the_secret(self):
        self.fake(401)
        d, conf = self.node()
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = w.main(["--config", str(conf), "info"])
        self.assertEqual(rc, 1)
        self.assertIn(f"refused the RPC login from the node's cookie {d / '.cookie'} (HTTP 401)", err.getvalue())
        self.assertIn("stale", err.getvalue())
        self.assertNotIn(SECRET, err.getvalue() + out.getvalue())

    def test_refused_password_says_so(self):
        self.fake(401)
        d, conf = self.node(f"rpcuser=confu\nrpcpassword={SECRET}\n", cookie=None)
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf))).call("getblockchaininfo")
        self.assertIn(f"rpcuser/rpcpassword in {conf}", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))

    def test_wrong_default_port_is_explained(self):
        def urlopen(req, timeout=60): raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        p = mock.patch("urllib.request.urlopen", urlopen); p.start(); self.addCleanup(p.stop)
        d, conf = self.node("server=1\n")                          # no rpcport=
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf))).call("getblockchaininfo")
        self.assertIn("127.0.0.1:9432", str(cm.exception)); self.assertIn("pass the node's --rpc-port", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf), "--rpc-port", "8332")).call("getblockchaininfo")
        self.assertNotIn("--rpc-port", str(cm.exception))

    def test_missing_credentials_through_main(self):
        d, conf = self.node("rpcuser=confu\n", cookie=None)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = w.main(["--config", str(conf), "info"])
        self.assertEqual(rc, 1); self.assertTrue(err.getvalue().startswith("error: RPC credentials missing"))
        self.assertNotIn("Traceback", err.getvalue())

    def test_explorer_needs_no_login(self):
        a = w.parser().parse_args(["--explorer", "https://superknet.example", "--config", str(self.root / "none.conf"), "info"])
        self.assertTrue(getattr(w.make_backend(a), "is_explorer", False))

if __name__ == "__main__":
    unittest.main()
