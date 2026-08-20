"""v0.8.68 — self-contained welcome page shown while the frontend comes up.

The main window used to navigate straight to the Next.js URL; if that one
request raced server startup, WKWebView rendered a dead "This page couldn't
load" error with no recovery. Now the window renders this inline splash
(zero network dependencies, paints instantly), which probes the frontend
with no-cors fetches and replaces itself with the app once the server
answers twice in a row. If the frontend is slow it keeps trying forever
with friendly status — there is no terminal error state.

Kept as a template + builder so tests can pin the contract (embedded URL,
no external resources, probe/replace logic) without a webview.
"""

from __future__ import annotations

import json

_SPLASH_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Deeper Notebook</title>
<style>
  :root {
    --bg0: #0d0e1d; --bg1: #181a33; --ink: #eef0ff; --dim: #9aa0c5;
    --a: #6c7bff; --b: #b96cff; --c: #36c9b0;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--ink);
    background: radial-gradient(120% 120% at 20% 10%, var(--bg1), var(--bg0) 70%);
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
    transition: opacity .45s ease;
  }
  body.leaving { opacity: 0; }
  .blob {
    position: fixed; border-radius: 50%; filter: blur(90px); opacity: .35;
    animation: drift 16s ease-in-out infinite alternate;
  }
  .blob.one { width: 46vw; height: 46vw; left: -12vw; top: -14vh;
              background: var(--a); }
  .blob.two { width: 38vw; height: 38vw; right: -10vw; bottom: -16vh;
              background: var(--b); animation-delay: -6s; }
  .blob.three { width: 24vw; height: 24vw; right: 16vw; top: -8vh;
                background: var(--c); animation-delay: -11s; opacity: .22; }
  @keyframes drift {
    from { transform: translate(0, 0) scale(1); }
    to   { transform: translate(5vw, 6vh) scale(1.15); }
  }
  .card {
    position: relative; text-align: center; padding: 56px 64px;
    background: rgba(255,255,255,.045);
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 24px;
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    box-shadow: 0 24px 80px rgba(0,0,0,.45);
    animation: rise .6s cubic-bezier(.2,.8,.25,1) both;
  }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } }
  .logo {
    width: 72px; height: 72px; margin: 0 auto 20px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 20px;
    background: linear-gradient(135deg, var(--a), var(--b));
    box-shadow: 0 10px 32px rgba(108,123,255,.45);
    animation: breathe 2.6s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.06); }
  }
  .logo svg { width: 38px; height: 38px; }
  h1 { font-size: 26px; font-weight: 700; letter-spacing: .2px; }
  h1 .plus { background: linear-gradient(90deg, var(--a), var(--b));
             -webkit-background-clip: text; background-clip: text;
             color: transparent; }
  .tagline { color: var(--dim); margin-top: 6px; font-size: 14px; }
  .bar {
    width: 280px; height: 4px; border-radius: 999px; overflow: hidden;
    background: rgba(255,255,255,.08); margin: 30px auto 14px;
  }
  .bar i {
    display: block; height: 100%; width: 40%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--a), var(--b), var(--c));
    animation: slide 1.4s ease-in-out infinite;
  }
  @keyframes slide {
    0% { transform: translateX(-110%); }
    100% { transform: translateX(760%); }
  }
  #status { color: var(--dim); font-size: 13px; min-height: 20px;
            transition: opacity .3s ease; }
  .privacy {
    position: fixed; bottom: 26px; left: 0; right: 0;
    text-align: center; color: var(--dim); font-size: 12px; opacity: .8;
  }
  .privacy .dot { color: var(--c); }
</style>
</head>
<body>
  <div class="blob one"></div>
  <div class="blob two"></div>
  <div class="blob three"></div>
  <main class="card">
    <div class="logo" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
        <path d="M9 7h7M9 11h5"></path>
      </svg>
    </div>
    <h1>Deeper Notebook</h1>
    <p class="tagline">Think further with every source</p>
    <div class="bar"><i></i></div>
    <p id="status">Waking up your workspace&hellip;</p>
  </main>
  <p class="privacy"><span class="dot">&#9679;</span>
    Everything runs on your Mac &mdash; no cloud required.</p>
<script>
(function () {
  "use strict";
  // v0.8.68 — presentation only. The python handoff controller in
  // desktop/window.py decides when the frontend is genuinely ready and
  // drives the navigation; an in-page no-cors probe cannot see HTTP
  // status, so Next's warm-up 404 (a 200) read as "ready" and the splash
  // navigated onto an error page. TARGET is kept for display/debugging.
  var TARGET = __FRONTEND_URL__;  // eslint-disable-line no-unused-vars
  var statusEl = document.getElementById("status");
  var phrases = [
    "Waking up your workspace\\u2026",
    "Starting local AI models\\u2026",
    "Opening the knowledge graph\\u2026",
    "Preparing your notebooks\\u2026",
    "Almost there\\u2026"
  ];
  var slowPhrase = "Taking a little longer than usual \\u2014 still on it\\u2026";
  var started = Date.now();
  var phraseIdx = 0;

  function setStatus(text) {
    statusEl.style.opacity = 0;
    setTimeout(function () {
      statusEl.textContent = text;
      statusEl.style.opacity = 1;
    }, 280);
  }

  setInterval(function () {
    if (Date.now() - started > 90000) { setStatus(slowPhrase); return; }
    phraseIdx = (phraseIdx + 1) % phrases.length;
    setStatus(phrases[phraseIdx]);
  }, 3200);
})();
</script>
</body>
</html>
"""


def build_splash_html(frontend_url: str) -> str:
    """Return the welcome page with the frontend URL safely embedded.

    json.dumps handles quotes/backslashes but NOT `</script>` — a literal
    one inside a JS string still ends the script element during HTML
    parsing. The URL is launcher-generated (loopback + port), but escape
    angle brackets anyway so the builder is safe for any input.
    """
    embedded = json.dumps(frontend_url).replace("<", "\\u003c").replace(">", "\\u003e")
    return _SPLASH_TEMPLATE.replace("__FRONTEND_URL__", embedded)
