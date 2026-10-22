// XID Wallet screens. Every action goes through window.pywebview.api (gui/backend.py), which runs the wallet
// engine's own commands; this file only draws and asks. No network access from the page itself.
(function () {
  "use strict";
  const $app = document.getElementById("app");
  const $toast = document.getElementById("toast");
  const EXPLORER_TX = (base, txid) => `${base.replace(/\/$/, "")}/tx/${txid}`;
  let api = null, S = null, view = "overview", me = null, toastTimer = 0;

  // ── helpers ──
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const short = (s, a = 10, b = 8) => (s && s.length > a + b + 1 ? `${s.slice(0, a)}…${s.slice(-b)}` : s || "");
  const h = (html) => { $app.className = ""; $app.innerHTML = html; };
  function toast(msg, kind = "") {
    $toast.textContent = msg; $toast.className = `show ${kind}`;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => ($toast.className = ""), kind === "error" ? 7000 : 3500);
  }
  async function call(name, ...args) {
    const r = await api[name](...args);
    if (r && r.error) throw new Error(r.error);
    return r ? r.ok : null;
  }
  async function busy(btn, fn) {
    const label = btn.innerHTML; btn.disabled = true; btn.innerHTML = "Working…";
    try { return await fn(); } catch (e) { toast(e.message, "error"); } finally { btn.disabled = false; btn.innerHTML = label; }
  }
  const XID_MARK = '<svg viewBox="0 0 1024 1024" aria-hidden="true"><rect width="1024" height="1024" fill="#c7ff2e"/><path d="M763 782H631.5L511.8 595.2 391.7 782H261L422.7 535.2H322.5v-68.5h101.3L278.3 242h127.4L514 415.5 620.1 242h126.4L602.4 466.7h99.9v68.5H599.1Z" fill="#0b0b0b"/></svg>';

  // ── theme ──
  function applyTheme(pref) {
    if (pref === "light" || pref === "dark") document.documentElement.dataset.theme = pref;
    else delete document.documentElement.dataset.theme;
  }
  const isNight = () => document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;

  // ── boot ──
  async function boot() {
    api = window.pywebview.api;
    S = await call("state");
    applyTheme(S.settings.theme);
    if (!S.exists) return welcome();
    if (!S.unlocked) return unlock();
    return shell();
  }
  window.addEventListener("pywebviewready", () => boot().catch((e) => toast(e.message, "error")));

  // ── welcome: no wallet yet ──
  function welcome() {
    h(`<div class="welcome">
      <section class="welcome-art">
        <span class="label">xCoin · XID</span>
        <div><h1 class="display">XID<br>Wallet</h1><p style="margin-top:18px">Post-quantum money. Your keys are made here and never leave this computer.</p></div>
        <div class="facts"><span>ML-DSA-65 signatures</span><span>100,000,000 XID cap</span><span>No premine</span></div>
      </section>
      <section class="welcome-side">
        <h2 class="display">Get started</h2>
        <button class="choice box lime" data-go="create"><b>Create a new wallet</b><span>A fresh seed, encrypted with your passphrase.</span></button>
        <button class="choice box" data-go="restore"><b>Restore from a seed</b><span>You have the 64-character seed written down.</span></button>
        <button class="choice box" data-go="open"><b>Open a wallet file</b><span>A .mmm file from the command-line wallet or a backup.</span></button>
        <button class="choice box" disabled><b>Card wallet</b><span>NTAG 424 DNA cards: coming in a later version of this app.</span></button>
      </section></div>`);
    $app.querySelector('[data-go="create"]').onclick = createWallet;
    $app.querySelector('[data-go="restore"]').onclick = restoreWallet;
    $app.querySelector('[data-go="open"]').onclick = async () => { try { if (await call("choose_wallet_file")) { S = await call("state"); unlock(); } } catch (e) { toast(e.message, "error"); } };
  }

  function passFields() {
    return `<label class="field"><span>Passphrase</span><input type="password" name="pw" autocomplete="new-password" minlength="8" required>
      <span class="hint">At least 8 characters. It encrypts the wallet file on this computer; the seed is still your backup.</span></label>
      <label class="field"><span>Confirm passphrase</span><input type="password" name="pw2" autocomplete="new-password" required></label>`;
  }
  function checkPass(f) {
    if (f.pw.value.length < 8) { toast("Use a passphrase of at least 8 characters.", "error"); return false; }
    if (f.pw.value !== f.pw2.value) { toast("The two passphrases are different.", "error"); return false; }
    return true;
  }

  function createWallet() {
    h(`<div class="welcome"><section class="welcome-art"><span class="label">New wallet</span><div><h1 class="display">A new<br>seed</h1>
      <p style="margin-top:18px">The seed is made on this computer from the system's random source and saved encrypted. Next you write it down.</p></div><span></span></section>
      <section class="welcome-side"><button class="link back">← Back</button><h2 class="display">Choose a passphrase</h2>
      <form class="stack" autocomplete="off">${passFields()}<button class="btn primary" type="submit">Create wallet →</button></form></section></div>`);
    $app.querySelector(".back").onclick = welcome;
    const f = $app.querySelector("form");
    f.onsubmit = (ev) => { ev.preventDefault(); if (!checkPass(f)) return;
      busy(f.querySelector("button"), async () => { const r = await call("create", f.pw.value); f.reset(); S = await call("state"); backupSeed(r.seed); }); };
    f.pw.focus();
  }

  // the seed, shown once, then two of its groups typed back
  function backupSeed(seed) {
    const groups = seed.match(/.{8}/g);
    const ask = [2, 5].map((i) => i + Math.floor(Math.random() * 2));
    h(`<div class="page" style="max-width:860px;margin:0 auto;overflow-y:auto;height:100%">
      <div class="page-head"><h1 class="display">Write down your seed</h1></div>
      <p class="warn">This seed is the only way to get your XID back if this computer or the passphrase is lost. Write it on paper or metal, keep it offline, and never type it into a website or a chat.</p>
      <div class="seed-grid selectable">${groups.map((g, i) => `<div><i>${String(i + 1).padStart(2, "0")}</i><b>${g}</b></div>`).join("")}</div>
      <form class="box stack" style="padding:20px" autocomplete="off">
        <p>Type groups <b>${ask[0] + 1}</b> and <b>${ask[1] + 1}</b> from your copy to show you wrote it down.</p>
        <div class="row"><label class="field" style="flex:1"><span>Group ${ask[0] + 1}</span><input name="a" maxlength="8" spellcheck="false"></label>
          <label class="field" style="flex:1"><span>Group ${ask[1] + 1}</span><input name="b" maxlength="8" spellcheck="false"></label></div>
        <label class="check"><input type="checkbox" name="ok"> I wrote the seed down offline and I understand nobody can recover it for me.</label>
        <button class="btn primary" type="submit">Open my wallet →</button></form></div>`);
    const f = $app.querySelector("form");
    f.onsubmit = (ev) => { ev.preventDefault();
      if (f.a.value.trim().toLowerCase() !== groups[ask[0]] || f.b.value.trim().toLowerCase() !== groups[ask[1]]) return toast("Those groups do not match the seed. Check your copy.", "error");
      if (!f.ok.checked) return toast("Tick the box once the seed is written down.", "error");
      shell(); };
  }

  function restoreWallet() {
    h(`<div class="welcome"><section class="welcome-art"><span class="label">Restore</span><div><h1 class="display">Bring your<br>XID back</h1>
      <p style="margin-top:18px">Your seed recreates every address and the XID identity. The new wallet file is encrypted with the passphrase you choose.</p></div><span></span></section>
      <section class="welcome-side"><button class="link back">← Back</button><h2 class="display">Your seed</h2>
      <form class="stack" autocomplete="off"><label class="field"><span>Seed (64 characters, 0-9 and a-f)</span><textarea name="seed" spellcheck="false" autocomplete="off"></textarea>
      <span class="hint">Spaces and line breaks are ignored.</span></label>${passFields()}<button class="btn primary" type="submit">Restore wallet →</button></form></section></div>`);
    $app.querySelector(".back").onclick = welcome;
    const f = $app.querySelector("form");
    f.onsubmit = (ev) => { ev.preventDefault(); if (!checkPass(f)) return;
      busy(f.querySelector("button"), async () => { await call("restore", f.seed.value, f.pw.value); f.reset(); S = await call("state"); toast("Wallet restored.", "ok"); shell(); }); };
  }

  function unlock() {
    h(`<div class="welcome"><section class="welcome-art"><span class="label">Locked</span><div><h1 class="display">XID<br>Wallet</h1>
      <p style="margin-top:18px">Unlock to see your balance and send. The wallet locks itself after ten minutes without use.</p></div>
      <div class="facts"><span>${esc(S.settings.hrp === "xpa" ? "Mainnet" : "Testnet")}</span><span>${esc(S.settings.explorer.replace(/^https?:\/\//, ""))}</span></div></section>
      <section class="welcome-side"><h2 class="display">Unlock</h2>
      <form class="stack" autocomplete="off"><p class="note selectable mono" style="word-break:break-all">${esc(S.file)}</p>
      <label class="field"><span>Passphrase</span><input type="password" name="pw" autocomplete="current-password" required></label>
      <button class="btn primary" type="submit">Unlock →</button></form>
      <div class="row"><button class="link" data-act="other">Open another wallet file</button><button class="link" data-act="new">New or restored wallet</button></div></section></div>`);
    const f = $app.querySelector("form");
    f.onsubmit = (ev) => { ev.preventDefault(); busy(f.querySelector("button"), async () => { await call("unlock", f.pw.value); f.reset(); S = await call("state"); shell(); }); };
    $app.querySelector('[data-act="other"]').onclick = async () => { try { if (await call("choose_wallet_file")) { S = await call("state"); unlock(); } } catch (e) { toast(e.message, "error"); } };
    $app.querySelector('[data-act="new"]').onclick = async () => {
      const p = await call("set_setting", "file", S.file.replace(/[^\\/]+$/, `wallet-${Date.now().toString(36)}.mmm`)); S = await call("state"); welcome(); };
    f.pw.focus();
  }

  // ── the wallet ──
  const NAV = [["overview", "Overview"], ["receive", "Receive"], ["send", "Send"], ["coins", "Coins"], ["identity", "Identity"], ["settings", "Settings"]];
  async function shell() {
    h(`<div class="shell"><aside class="side">
        <div class="brand">${XID_MARK}<div><b>XID Wallet</b><span class="net">${S.settings.hrp === "xpa" ? "Mainnet" : "Testnet"} · v${esc(S.version)}</span></div></div>
        <nav class="nav">${NAV.map(([k, t]) => `<button data-v="${k}">${t}</button>`).join("")}</nav>
        <div class="side-foot">
          <button class="me" data-v="identity" title="Your XID identity"><span class="ic"></span><span><small>XID identity</small><code>…</code></span></button>
          <button class="mode" title="Day or night"><span data-m="day">Day</span><span data-m="night">Night</span></button>
          <button class="btn small" data-act="lock">Lock wallet</button>
        </div></aside><main class="main"><div class="page" id="page"></div></main></div>`);
    $app.querySelectorAll("[data-v]").forEach((b) => (b.onclick = () => go(b.dataset.v)));
    $app.querySelector('[data-act="lock"]').onclick = async () => { await call("lock"); S = await call("state"); unlock(); };
    const mode = $app.querySelector(".mode");
    const paintMode = () => { mode.querySelector('[data-m="day"]').classList.toggle("on", !isNight()); mode.querySelector('[data-m="night"]').classList.toggle("on", isNight()); };
    mode.onclick = async () => { const next = isNight() ? "light" : "dark"; applyTheme(next); paintMode(); try { S.settings = await call("set_setting", "theme", next); } catch (e) { toast(e.message, "error"); } };
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paintMode);
    paintMode();
    loadIdentity();
    go(view);
  }
  async function loadIdentity() {
    try {
      me = await call("identity");
      const el = $app.querySelector(".me"); if (!el) return;
      el.querySelector("code").textContent = short(me.identity, 9, 6);
      el.querySelector(".ic").innerHTML = await identiconSvg(me.identity, 40);
    } catch (e) { relock(e); }
  }
  function relock(e) {
    if (/locked/i.test(e.message)) { call("state").then((s) => { S = s; unlock(); toast("The wallet locked itself. Unlock to continue."); }); return true; }
    toast(e.message, "error"); return false;
  }
  function go(v) {
    view = v;
    $app.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    ({ overview, receive, send, coins, identity, settings }[v] || overview)();
  }
  const page = (html) => { const p = document.getElementById("page"); p.innerHTML = html; p.parentElement.scrollTop = 0; return p; };
  const head = (title, right = "") => `<div class="page-head"><h1 class="display">${title}</h1><div class="row">${right}</div></div>`;

  async function overview() {
    const p = page(`${head("Overview", '<button class="btn small" data-act="refresh">Refresh</button>')}
      <section class="box balance"><div class="balance-main"><span class="label">Spendable</span><div class="amt"><b>…</b><span>XID</span></div></div>
      <dl class="stats"><div><dt>Immature</dt><dd data-k="immature">…</dd></div><div><dt>Total</dt><dd data-k="total">…</dd></div><div><dt>Block height</dt><dd data-k="height">…</dd></div></dl></section>
      <section class="box addr-strip"><span class="label">Address</span><span class="addr" data-k="address">…</span><button class="btn small" data-act="copy">Copy</button></section>
      <p class="note">Mined coins become spendable after 1,000 blocks, about three and a half days. Balances come from ${esc(S.settings.explorer.replace(/^https?:\/\//, ""))}; your keys and signing stay on this computer.</p>`);
    p.querySelector('[data-act="refresh"]').onclick = overview;
    try {
      const b = await call("balance", 0);
      p.querySelector(".amt b").textContent = b.spendable;
      p.querySelector('[data-k="immature"]').textContent = b.immature;
      p.querySelector('[data-k="total"]').textContent = b.total;
      p.querySelector('[data-k="height"]').textContent = b.height != null ? Number(b.height).toLocaleString() : "–";
      p.querySelector('[data-k="address"]').textContent = b.address;
      p.querySelector('[data-act="copy"]').onclick = () => copy(b.address, "Address copied.");
    } catch (e) {
      if (relock(e)) return;
      p.querySelector(".balance").outerHTML = `<div class="error-panel"><b>Balance unavailable</b><p>${esc(e.message)}</p><div><button class="btn small" data-act="retry">Try again</button></div></div>`;
      p.querySelector('[data-act="retry"]').onclick = overview;
    }
  }
  async function copy(text, done) { try { await call("copy", text); toast(done, "ok"); } catch (e) { toast(e.message, "error"); } }

  async function receive() {
    const p = page(`${head("Receive")}<section class="box receive"><div class="qr">…</div><div class="receive-info">
      <span class="label">Your XID address</span><p class="addr selectable">…</p><div class="row"><button class="btn primary" data-act="copy">Copy address</button></div>
      <p class="note">Share this address to receive XID. It is a witness v3 address: payments to it are protected by ML-DSA-65, with an SLH-DSA-SHA2-128s fallback key.</p>
      <details class="more"><summary>Older single-leaf form</summary><p class="note">Coins sent to the single-leaf form of the same key are also yours and show in your balance:</p><p class="addr selectable" data-k="carried"></p></details>
      </div></section>`);
    try {
      const r = await call("receive", 0);
      p.querySelector(".qr").innerHTML = r.qr;
      p.querySelector(".receive-info .addr").textContent = r.address;
      p.querySelector('[data-k="carried"]').textContent = r.carried_address;
      p.querySelector('[data-act="copy"]').onclick = () => copy(r.address, "Address copied.");
    } catch (e) { relock(e); }
  }

  function send() {
    const p = page(`${head("Send")}<div class="send"><form class="box" autocomplete="off">
        <label class="field"><span>To (XID address)</span><input name="to" spellcheck="false" placeholder="${S.settings.hrp}1r…" required></label>
        <label class="field"><span>Amount</span><div class="amount-wrap"><input name="amount" inputmode="decimal" placeholder="0.00000000" required><b>XID</b></div></label>
        <button class="btn primary" type="submit">Review →</button>
        <p class="note">Review signs the transaction on this computer and checks it with the network. Nothing is sent until you press Send.</p>
      </form><section class="box review" id="review" hidden></section></div>`);
    const f = p.querySelector("form"), rv = p.querySelector("#review");
    f.onsubmit = (ev) => { ev.preventDefault();
      busy(f.querySelector("button"), async () => {
        const to = f.to.value.trim(), amount = f.amount.value.trim();
        const d = await call("send_preview", to, amount, 0);
        rv.hidden = false; rv.classList.remove("sent");
        rv.innerHTML = `<h3>Check before sending</h3><dl>
          <div><dt>To</dt><dd class="selectable">${esc(to)}</dd></div><div><dt>Amount</dt><dd>${esc(amount)} XID</dd></div>
          <div><dt>Network fee</dt><dd>${esc(d.fee)} XID</dd></div><div><dt>Change back to you</dt><dd>${esc(d.change)} XID</dd></div>
          <div><dt>Size</dt><dd>${esc(d.vsize)} vB · ${esc(d.inputs)} input${d.inputs === 1 ? "" : "s"}</dd></div>
          <div class="total"><dt>Total leaving</dt><dd>${(Number(amount) + Number(d.fee)).toFixed(8)} XID</dd></div></dl>
          <div class="actions">${d.mempool_accept === false ? `<p class="warn">The network would refuse this transaction: ${esc(d.reject_reason || "unknown reason")}</p>` : ""}
          <label class="check"><input type="checkbox" name="sure"> Send ${esc(amount)} XID to this address. Sent XID cannot be called back.</label>
          <button class="btn danger" data-act="send">Send now</button></div>`;
        rv.querySelector('[data-act="send"]').onclick = (e2) => {
          if (!rv.querySelector('[name="sure"]').checked) return toast("Tick the box to confirm.", "error");
          busy(e2.currentTarget, async () => {
            const s = await call("send", to, amount, 0);
            rv.classList.add("sent");
            rv.innerHTML = `<h3>Sent</h3><dl><div><dt>Amount</dt><dd>${esc(amount)} XID</dd></div><div><dt>Fee</dt><dd>${esc(s.fee)} XID</dd></div>
              <div><dt>Transaction</dt><dd class="selectable">${esc(s.txid)}</dd></div></dl>
              <div class="actions"><button class="btn" data-act="view">View on the explorer</button></div>`;
            rv.querySelector('[data-act="view"]').onclick = () => call("open_url", EXPLORER_TX(S.settings.explorer, s.txid)).catch((e) => toast(e.message, "error"));
            f.reset(); toast("Sent. It confirms in the next blocks.", "ok");
          });
        };
      }).catch(() => {});
    };
  }

  async function coins() {
    const p = page(`${head("Coins", '<button class="btn small" data-act="explorer">Full history on the explorer</button>')}<div id="coins">Loading…</div>
      <p class="note">These are the coins your address holds right now. The full list of past payments is on the explorer's address page.</p>`);
    try {
      const rows = await call("coins", 0);
      const r0 = await call("receive", 0);
      p.querySelector('[data-act="explorer"]').onclick = () => call("open_url", `${S.settings.explorer.replace(/\/$/, "")}/address/${r0.address}`).catch((e) => toast(e.message, "error"));
      p.querySelector("#coins").innerHTML = rows.length ? `<table class="coins"><thead><tr><th>Transaction</th><th>Height</th><th>Confirmations</th><th>Kind</th><th style="text-align:right">Amount</th></tr></thead><tbody>
        ${rows.map((u) => `<tr><td class="selectable">${esc(short(u.txid, 12, 6))}:${u.vout}</td><td>${esc(u.height ?? "–")}</td><td>${esc(u.confirmations)}</td>
          <td>${u.coinbase ? '<span class="chip">Mined</span> ' : ""}${u.spendable ? '<span class="chip lime">Spendable</span>' : `<span class="chip">${esc(u.blocks_to_maturity)} blocks to go</span>`}</td>
          <td class="num">${esc(u.amount)}</td></tr>`).join("")}</tbody></table>` : '<div class="box empty"><p>No coins yet. Share your address from Receive.</p></div>';
    } catch (e) { relock(e); }
  }

  async function identity() {
    const p = page(`${head("Identity")}<section class="box identity"><div class="ic-big"></div><div class="identity-info">
      <span class="label">Your XID identity</span><h3>Key number 100,000,000</h3><p class="addr selectable">…</p>
      <div class="row"><button class="btn primary" data-act="copy">Copy identity</button></div>
      <p class="note">This is your public name on xCoin: for chat, AYEDEX and signing messages. It comes from key index 99,999,999 of your seed and nothing can be paid to it. It cannot be traced to your balance: your funds are on index 0, and every key is derived from the seed on its own.</p>
      <p class="note">The mark on the left is drawn from the identity itself, the same mark MMM, superknet.com and the forum show.</p></div></section>`);
    try {
      me = me || await call("identity");
      p.querySelector(".identity-info .addr").textContent = me.identity;
      p.querySelector(".ic-big").innerHTML = await identiconSvg(me.identity, 240);
      p.querySelector('[data-act="copy"]').onclick = () => copy(me.identity, "Identity copied.");
    } catch (e) { relock(e); }
  }

  function settings() {
    const st = S.settings;
    const seg = (key, opts) => `<div class="seg" data-key="${key}">${opts.map(([v, t]) => `<button data-val="${v}" class="${st[key] === v ? "on" : ""}">${t}</button>`).join("")}</div>`;
    const p = page(`${head("Settings")}<section class="box settings">
      <div class="set-row"><h3>Look</h3><div class="stack">${seg("theme", [["system", "System"], ["light", "Day"], ["dark", "Night"]])}<p class="note">System follows Windows' light or dark setting.</p></div></div>
      <div class="set-row"><h3>Network</h3><div class="stack">${seg("hrp", [["xpa", "Mainnet"], ["txa", "Testnet"]])}<p class="note">Mainnet addresses start xpa1r, testnet txa1r.</p></div></div>
      <div class="set-row"><h3>Explorer</h3><form class="stack" data-f="explorer"><label class="field"><span>Balances, fees and sending go through</span><input name="url" value="${esc(st.explorer)}" spellcheck="false"></label>
        <div><button class="btn small" type="submit">Save</button></div><p class="note">The explorer only reports the chain and passes on signed transactions. It never sees your keys.</p></form></div>
      <div class="set-row"><h3>Wallet file</h3><div class="stack"><p class="addr selectable">${esc(S.file)}</p><div class="row"><button class="btn small" data-act="backup">Back up the file</button><button class="btn small" data-act="other">Open another</button></div>
        <p class="note">The file is encrypted with your passphrase. Keep a copy on a USB stick; your written seed is the backup that needs no passphrase.</p></div></div>
      <div class="set-row"><h3>Seed</h3><form class="stack" data-f="seed" autocomplete="off"><label class="field"><span>Passphrase, to show the seed</span><input type="password" name="pw" autocomplete="current-password"></label>
        <div><button class="btn small danger" type="submit">Show seed</button></div><div class="seed-reveal"></div></form></div>
      <div class="set-row"><h3>About</h3><p class="note">XID Wallet ${esc(S.version)}. Open source, MIT licence. The wallet engine is the xcoin-wallet command-line wallet; signatures are ML-DSA-65 (FIPS 204) with an SLH-DSA-SHA2-128s (FIPS 205) fallback.</p></div>
    </section>`);
    p.querySelectorAll(".seg").forEach((g) => g.querySelectorAll("button").forEach((b) => (b.onclick = async () => {
      try {
        S.settings = await call("set_setting", g.dataset.key, b.dataset.val);
        if (g.dataset.key === "theme") applyTheme(b.dataset.val);
        if (g.dataset.key === "hrp") { me = null; S = await call("state"); return shell(); }
        settings();
      } catch (e) { toast(e.message, "error"); }
    })));
    p.querySelector('[data-f="explorer"]').onsubmit = async (ev) => { ev.preventDefault();
      try { S.settings = await call("set_setting", "explorer", ev.target.url.value.trim()); toast("Explorer saved.", "ok"); } catch (e) { toast(e.message, "error"); } };
    p.querySelector('[data-act="backup"]').onclick = async () => { try { const r = await call("backup"); if (r) toast(`Backed up to ${r.backup}`, "ok"); } catch (e) { toast(e.message, "error"); } };
    p.querySelector('[data-act="other"]').onclick = async () => { try { if (await call("choose_wallet_file")) { S = await call("state"); unlock(); } } catch (e) { toast(e.message, "error"); } };
    const sf = p.querySelector('[data-f="seed"]');
    sf.onsubmit = (ev) => { ev.preventDefault();
      busy(sf.querySelector("button"), async () => {
        const seed = await call("reveal_seed", sf.pw.value); sf.pw.value = "";
        const box = sf.querySelector(".seed-reveal");
        box.innerHTML = `<div class="seed-grid selectable">${seed.match(/.{8}/g).map((g, i) => `<div><i>${String(i + 1).padStart(2, "0")}</i><b>${g}</b></div>`).join("")}</div><p class="note" style="margin-top:8px">Hidden again in 60 seconds.</p>`;
        setTimeout(() => (box.innerHTML = ""), 60000);
      });
    };
  }
})();
