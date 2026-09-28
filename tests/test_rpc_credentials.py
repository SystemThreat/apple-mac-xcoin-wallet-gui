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
        rpc = w.RPC(self.args(*argv))
        return rpc.user, rpc.password, rpc.auth_source

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
        d, conf = self.node(f"rpccookiefile={self.root / 'gone.cookie'}\n")
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        msg = self.error("--config", str(conf))
        self.assertIn(str(self.root / "gone.cookie"), msg); self.assertIn("Is the node running", msg)

    def test_conf_rpcuser_rpcpassword_beat_an_autodetected_cookie(self):
        # a node whose conf sets rpcpassword= writes no cookie (src/httprpc.cpp): a .cookie
        # beside that conf is left over from an earlier run, or another node's
        d, conf = self.node("rpcuser=confu\nrpcpassword=confp\n")
        self.write(self.home / "Library" / "Application Support" / "NEX" / ".cookie", "__cookie__:builtin\n")
        self.assertEqual(self.creds("--config", str(conf)), ("confu", "confp", f"rpcuser/rpcpassword in {conf}"))

    def test_conf_rpcpassword_beats_conf_rpccookiefile(self):
        # the node reads rpcpassword= first and then writes no cookie, rpccookiefile= or not
        conf_cookie = self.write(self.root / "conf.cookie", "__cookie__:fromconf\n")
        d, conf = self.node(f"rpccookiefile={conf_cookie}\nrpcuser=confu\nrpcpassword=confp\n")
        self.assertEqual(self.creds("--config", str(conf))[:2], ("confu", "confp"))

    def test_half_a_conf_login_does_not_beat_the_cookie(self):
        # rpcuser= alone: the node writes a cookie, and the env vars stay the last resort
        d, conf = self.node("rpcuser=confu\n")
        os.environ.update(XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf)), ("__cookie__", SECRET, f"the node's cookie {d / '.cookie'}"))

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
    def builtin(self):
        """The node's built-in data directory under the test HOME."""
        return self.home / ("Library/Application Support/NEX" if sys.platform == "darwin" else ".nex")

    def test_datadir_in_conf(self):
        data = self.root / "chaindata"
        self.write(data / ".cookie", "__cookie__:datadir\n")
        d, conf = self.node(f"datadir={data}\n")                    # d/.cookie exists but is not the datadir
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", "datadir"))

    def test_datadir_in_conf_is_the_only_place_looked(self):
        # no cookie in datadir=: another node's cookie beside the conf, in ~/.xcoin or in the
        # built-in data directory is not taken (it would go to this conf's port)
        d, conf = self.node(f"datadir={self.root / 'chaindata'}\n")
        for other in (self.home / ".xcoin", self.builtin()): self.write(other / ".cookie", "__cookie__:othernode\n")
        msg = self.error("--config", str(conf))
        self.assertIn(f"looked at {self.root / 'chaindata' / '.cookie'})", msg)
        self.assertNotIn("othernode", msg)

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

    def test_chain_subdirectory_from_the_port_when_the_conf_names_none(self):
        # a node run with -testnet (or -regtest) on the command line: the conf says nothing,
        # the port in use says which chain's cookie to read
        for conf_text, argv, sub in (("rpcport=19432\n", (), "testneta"), ("server=1\n", ("--rpc-port", "19432"), "testneta"),
                                     ("rpcport=18443\n", (), "regtest"), ("server=1\n", ("--rpc-port", "18443"), "regtest")):
            with self.subTest(conf_text=conf_text, argv=argv):
                d, conf = self.node(conf_text, cookie="__cookie__:mainnet\n")
                self.write(d / sub / ".cookie", f"__cookie__:{sub}\n")
                self.assertEqual(self.creds("--config", str(conf), *argv)[1], sub)

    def test_the_confs_chain_beats_the_port(self):
        d, conf = self.node("chain=main\nrpcport=19432\n")
        self.write(d / "testneta" / ".cookie", "__cookie__:testneta\n")
        self.assertEqual(self.creds("--config", str(conf))[1], SECRET)

    def test_mainnet_conf_never_takes_a_testnet_cookie(self):
        for conf_text in ("server=1\n", "testnet=0\n", "chain=main\n"):
            with self.subTest(conf_text=conf_text):
                d, conf = self.node(conf_text, cookie=None)
                self.write(d / "testneta" / ".cookie", "__cookie__:testnet\n")
                self.write(d / "regtest" / ".cookie", "__cookie__:regtest\n")
                msg = self.error("--config", str(conf))
                self.assertIn(str(d / ".cookie"), msg)

    def test_xcoin_home_only_for_the_default_config(self):
        # ~/.xcoin is the default conf's own directory; any other conf never reads a cookie there
        self.write(self.home / ".xcoin" / ".cookie", "__cookie__:xcoinhome\n")
        msg = self.error("--config", str(self.root / "missing" / "nex.conf"))
        self.assertNotIn(str(self.home / ".xcoin"), msg)
        self.assertIn(str(self.root / "missing" / ".cookie"), msg); self.assertIn(str(self.builtin() / ".cookie"), msg)

    def test_default_config_is_the_xcoin_home(self):
        # no --config at all: the default ~/.xcoin/nex.conf (absent here) leads to ~/.xcoin/.cookie
        self.write(self.home / ".xcoin" / ".cookie", "__cookie__:defaultconf\n")
        user, password, source = self.creds("--config", str(self.home / ".xcoin" / "nex.conf"))
        self.assertEqual(password, "defaultconf"); self.assertIn(str(self.home / ".xcoin" / ".cookie"), source)

    def test_readme_testnet_alias(self):
        # a testnet A node run with -testnet -datadir=~/.xcoin; the mainnet node's cookie in the
        # built-in data directory is never sent to port 19432
        self.write(self.builtin() / ".cookie", "__cookie__:mainnet\n")
        self.write(self.home / ".xcoin" / "testneta" / ".cookie", "__cookie__:testneta\n")
        cookie = self.home / ".xcoin" / "testneta" / ".cookie"
        for argv in (("--config", str(self.home / ".xcoin" / "nex.conf"), "--rpc-port", "19432"),
                     ("--rpc-cookie", "~/.xcoin/testneta/.cookie", "--rpc-port", "19432")):
            with self.subTest(argv=argv):
                user, password, source = self.creds("--config", str(self.home / ".xcoin" / "nex.conf"), *argv)
                self.assertEqual(password, "testneta"); self.assertIn(str(cookie), source)

    def test_the_nodes_built_in_datadir(self):
        # a node started with only -conf=<this conf> keeps its data in the built-in directory
        for platform, where in (("darwin", Path("Library") / "Application Support" / "NEX"), ("linux", Path(".nex"))):
            with self.subTest(platform=platform), mock.patch.object(w.sys, "platform", platform):
                self.write(self.home / where / ".cookie", f"__cookie__:{platform}\n")
                d, conf = self.node(cookie=None)
                self.assertEqual(self.creds("--config", str(conf))[1], platform)
                self.assertEqual(self.creds("--config", str(self.root / "missing" / "nex.conf"))[1], platform)

    def test_conf_directory_before_the_built_in_datadir(self):
        self.write(self.builtin() / ".cookie", "__cookie__:builtin\n")
        d, conf = self.node()
        self.assertEqual(self.creds("--config", str(conf))[1], SECRET)

    def test_cookie_is_read_fresh_every_run(self):
        d, conf = self.node()
        self.assertEqual(w.RPC(self.args("--config", str(conf))).password, SECRET)
        self.write(d / ".cookie", "__cookie__:afterrestart\n")        # the node restarted
        self.assertEqual(w.RPC(self.args("--config", str(conf))).password, "afterrestart")

    def test_unreadable_autodetected_cookie_falls_through_to_env(self):
        if os.geteuid() == 0: self.skipTest("root reads any file")
        d, conf = self.node("rpcuser=confu\n", cookie=COOKIE)
        os.environ.update(XCOIN_RPC_PASSWORD="envp")
        os.chmod(d / ".cookie", 0)
        self.addCleanup(os.chmod, d / ".cookie", 0o600)
        self.assertEqual(self.creds("--config", str(conf))[:2], ("confu", "envp"))

class TestRemote(Creds):
    """A cookie the wallet finds itself is this machine's node login: it goes to a node on
    this machine only. A remote node needs its own login, named explicitly."""
    def setUp(self):
        super().setUp()
        self.seen = []
        def urlopen(req, timeout=60):
            self.seen.append(req)
            return io.BytesIO(json.dumps({"result": {"chain": "main"}, "error": None}).encode())
        p = mock.patch("urllib.request.urlopen", urlopen); p.start(); self.addCleanup(p.stop)
        self.write(self.builtin() / ".cookie", COOKIE)          # this machine's node

    builtin = TestAutoDetect.builtin

    def test_remote_rpcconnect_gets_no_found_cookie(self):
        d, conf = self.node("rpcconnect=203.0.113.5\nrpcport=8332\n")
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            rc = w.main(["--config", str(conf), "info"])
        self.assertEqual(rc, 1); self.assertEqual(self.seen, [])
        msg = err.getvalue()
        self.assertIn("the node at 203.0.113.5 is not on this machine", msg)
        for hint in ("--rpc-cookie", "rpccookiefile=", "rpcuser/rpcpassword", str(conf)): self.assertIn(hint, msg)
        self.assertNotIn(SECRET, msg + out.getvalue())

    def test_remote_rpc_host_gets_no_found_cookie(self):
        d, conf = self.node()
        for host in ("198.51.100.9", "node.example.com", "0.0.0.0", "10.0.0.2"):
            with self.subTest(host=host):
                msg = self.error("--config", str(conf), "--rpc-host", host)
                self.assertIn(f"the node at {host} is not on this machine", msg)
        self.assertEqual(self.seen, [])

    def test_remote_node_with_the_confs_login(self):
        # RUN-YOUR-OWN-NODE section 7: rpcuser/rpcpassword for a node elsewhere
        d, conf = self.node("rpcconnect=203.0.113.5\nrpcport=8332\nrpcuser=u\nrpcpassword=p\n")
        rpc = w.RPC(self.args("--config", str(conf)))
        rpc.call("getblockchaininfo")
        self.assertEqual(self.seen[0].full_url, "http://203.0.113.5:8332/")
        self.assertEqual(self.seen[0].get_header("Authorization"), "Basic " + base64.b64encode(b"u:p").decode())

    def test_remote_node_with_a_named_cookie(self):
        copy = self.write(self.root / "remote.cookie", "__cookie__:remote\n")
        d, conf = self.node(f"rpcconnect=203.0.113.5\nrpccookiefile={copy}\n")
        self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", "remote"))
        self.assertEqual(self.creds("--config", str(conf), "--rpc-host", "198.51.100.9", "--rpc-cookie", str(copy))[:2],
                         ("__cookie__", "remote"))

    def test_remote_node_with_env_login(self):
        d, conf = self.node("rpcconnect=203.0.113.5\n")
        os.environ.update(XCOIN_RPC_USER="envu", XCOIN_RPC_PASSWORD="envp")
        self.assertEqual(self.creds("--config", str(conf)), ("envu", "envp", "XCOIN_RPC_USER/XCOIN_RPC_PASSWORD"))

    def test_this_machine_by_any_name(self):
        for host in ("127.0.0.1", "127.0.0.2", "localhost", "LOCALHOST", "::1", "[::1]"):
            with self.subTest(host=host):
                d, conf = self.node(f"rpcconnect={host}\nrpcport=8332\n")
                self.assertEqual(self.creds("--config", str(conf))[:2], ("__cookie__", SECRET))

class TestErrors(Creds):
    def test_missing_names_every_place_tried_and_what_to_do(self):
        d, conf = self.node(cookie=None)
        msg = self.error("--config", str(conf))
        self.assertIn("RPC credentials missing", msg)
        builtin = self.home / ("Library/Application Support/NEX" if sys.platform == "darwin" else ".nex")
        for p in (d / ".cookie", builtin / ".cookie"): self.assertIn(str(p), msg)
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
        os.environ.update(XCOIN_RPC_PASSWORD="envp")                # a remote node gets no cookie found here
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

    def test_leftover_cookie_is_not_sent_for_a_password_conf(self):
        # the node reads rpcpassword= and writes no cookie: a .cookie beside its conf is from an
        # earlier crash; the conf's login goes out, and a refusal points at it, not at a cookie
        seen = self.fake(401)
        d, conf = self.node(f"rpcport=8332\nrpcuser=u\nrpcpassword={SECRET}\n")
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf))).call("getblockchaininfo")
        self.assertEqual(seen[0].get_header("Authorization"), "Basic " + base64.b64encode(f"u:{SECRET}".encode()).decode())
        self.assertIn(f"refused the RPC login from rpcuser/rpcpassword in {conf}", str(cm.exception))
        self.assertIn("check it matches the node's rpcuser/rpcpassword", str(cm.exception))
        self.assertNotIn("cookie", str(cm.exception)); self.assertNotIn(SECRET, str(cm.exception))

    def test_default_port_is_the_nodes_for_the_confs_chain(self):
        # src/chainparamsbase.cpp: 8332 mainnet, 19432 testnet A, 18443 regtest
        for conf_text, port in (("server=1\n", 8332), ("chain=main\n", 8332), ("testnet=1\n", 19432),
                                ("chain=test\n", 19432), ("regtest=1\n", 18443), ("testnet=1\nrpcport=19555\n", 19555)):
            with self.subTest(conf_text=conf_text):
                d, conf = self.node(conf_text)
                self.write(d / "testneta" / ".cookie", COOKIE); self.write(d / "regtest" / ".cookie", COOKIE)
                self.assertEqual(w.RPC(self.args("--config", str(conf))).port, port)
        self.assertEqual(w.RPC(self.args("--config", str(conf), "--rpc-port", "8332")).port, 8332)

    def test_wrong_default_port_is_explained(self):
        def urlopen(req, timeout=60): raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        p = mock.patch("urllib.request.urlopen", urlopen); p.start(); self.addCleanup(p.stop)
        d, conf = self.node("server=1\n")                          # no rpcport=
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf))).call("getblockchaininfo")
        self.assertIn("127.0.0.1:8332", str(cm.exception)); self.assertIn("pass the node's --rpc-port", str(cm.exception))
        self.assertIn("default port for mainnet", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))
        d, conf = self.node("testnet=1\n", sub="testneta")
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf))).call("getblockchaininfo")
        self.assertIn("127.0.0.1:19432", str(cm.exception)); self.assertIn("default port for testnet A", str(cm.exception))
        with self.assertRaises(w.WalletError) as cm: w.RPC(self.args("--config", str(conf), "--rpc-port", "8332")).call("getblockchaininfo")
        self.assertNotIn("--rpc-port", str(cm.exception))

    def test_missing_credentials_through_main(self):
        d, conf = self.node("rpcuser=confu\n", cookie=None)
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = w.main(["--config", str(conf), "info"])
        self.assertEqual(rc, 1); self.assertTrue(err.getvalue().startswith("error: RPC credentials missing"), err.getvalue()[:300])
        self.assertNotIn("Traceback", err.getvalue())

    def test_explorer_needs_no_login(self):
        a = w.parser().parse_args(["--explorer", "https://superknet.example", "--config", str(self.root / "none.conf"), "info"])
        self.assertTrue(getattr(w.make_backend(a), "is_explorer", False))

if __name__ == "__main__":
    unittest.main()
