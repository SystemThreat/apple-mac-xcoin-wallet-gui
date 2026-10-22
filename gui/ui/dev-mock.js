// A stand-in for the Python bridge, so the screens can be reviewed in a normal browser (preview.html).
// Development only: never loaded by the app, never packaged. ?screen=welcome|unlock|overview|... picks a start.
(function () {
  const q = new URLSearchParams(location.search), D = window.DEV_SAMPLE;
  const t = q.get("theme"); if (t) document.documentElement.dataset.theme = t;
  const startScreen = q.get("screen") || "overview";
  const st = { theme: t || "system", explorer: "https://superknet.com", hrp: "xpa", file: "C:\\Users\\you\\.xcoin\\wallet.mmm" };
  const ok = (v) => Promise.resolve({ ok: v });
  const api = {
    state: () => ok({ file: st.file, exists: startScreen !== "welcome", format: "mmm1", card: false, unlocked: !["welcome", "unlock"].includes(startScreen), settings: st, identity_index: 99999999, version: "2.0.0-dev", platform: "win32" }),
    set_setting: (k, v) => { st[k] = v; return ok(st); }, wallets: () => ok([]), choose_wallet_file: () => ok(null),
    create: () => ok({ file: st.file, seed: "3f9a1c07e2b84d56a90c1e7f5b2d8a4c6e0f3b9d7a1c5e8f2b4d6a0c9e7f1b3d" }),
    restore: () => ok({ file: st.file }), unlock: () => ok(true), lock: () => ok(true),
    reveal_seed: () => ok("3f9a1c07e2b84d56a90c1e7f5b2d8a4c6e0f3b9d7a1c5e8f2b4d6a0c9e7f1b3d"),
    receive: () => ok({ address: D.address, carried_address: D.carried_address, index: 0, qr: D.qr }),
    identity: () => ok({ identity: D.identity, index: 99999999 }),
    balance: () => ok({ address: D.address, spendable: "1248.33000000", immature: "50.00000000", total: "1298.33000000", height: 8021, utxos: 4 }),
    coins: () => ok([
      { txid: "9b1f04c3e7a2d58f6b0c1e9a7d3f5b2c4e6a8d0f1b3c5e7a9d2f4b6c8e0a1d3f", vout: 0, amount: "1000.00000000", height: 7711, confirmations: 311, coinbase: false, spendable: true },
      { txid: "4e7a9d2f4b6c8e0a1d3f9b1f04c3e7a2d58f6b0c1e9a7d3f5b2c4e6a8d0f1b3c", vout: 1, amount: "198.33000000", height: 6120, confirmations: 1902, coinbase: true, spendable: true },
      { txid: "c5e7a9d2f4b6c8e0a1d3f9b1f04c3e7a2d58f6b0c1e9a7d3f5b2c4e6a8d0f1b3", vout: 0, amount: "50.00000000", height: 8001, confirmations: 21, coinbase: true, spendable: false, blocks_to_maturity: 979 }]),
    send_preview: () => ok({ txid: "ab12", fee: "0.00002960", change: "1148.32997040", vsize: 1460, inputs: 1, mempool_accept: true }),
    send: () => ok({ txid: "f1e2d3c4b5a69788796a5b4c3d2e1f00112233445566778899aabbccddeeff00", fee: "0.00002960" }),
    backup: () => ok(null), copy: () => ok(true), open_url: () => ok(true),
  };
  window.pywebview = { api };
  window.addEventListener("load", () => {
    window.dispatchEvent(new Event("pywebviewready"));
    const go = { receive: 1, send: 1, coins: 1, identity: 1, settings: 1 }[startScreen];
    if (go) setTimeout(() => document.querySelector(`.nav [data-v="${startScreen}"]`)?.click(), 150);
  });
})();
