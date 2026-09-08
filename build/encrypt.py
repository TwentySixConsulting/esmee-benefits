#!/usr/bin/env python3
"""
Wrap the report in a client-side passphrase gate and write the publishable index.html.

    python3 build/encrypt.py                     # uses the standard credentials
    python3 build/encrypt.py --user X --pass Y   # override

Reads  _source/report.html   (plaintext, gitignored)
Writes index.html            (the ONLY html committed; ciphertext plus the gate)

The whole <body> is encrypted with AES-256-GCM under a key derived by PBKDF2-HMAC-SHA256,
200,000 iterations, over "<username>:<passphrase>". Nothing but the stylesheet and the
gate itself ships in the clear, so a public GitHub Pages repo never exposes the client's
benefits data. There is no server and no key escrow: lose the passphrase and the content
is gone, which is the point.

This script exists because the original Penge gate was built ad hoc and the script did not
survive. Every future edit is now: edit the data, run build.py, run this, commit.
"""

import argparse
import base64
import json
import os
import pathlib
import re
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "_source" / "report.html"
OUT = ROOT / "index.html"

# No credentials in this file. It is committed to a PUBLIC repository, so a default
# passphrase here would be published alongside the ciphertext it protects.
# Supply them per run:  EFB_USER=... EFB_PASS=... python3 build/encrypt.py
# or:                   python3 build/encrypt.py --user ... --password ...
ITERATIONS = 200_000

# Overrides the template's #gate styles, which set a 420px frame and a 28px title. The
# Foundation's name wrapped onto two lines there, which is the first thing a client sees and
# reads as unfinished. Wider frame, slightly smaller title, and the fussy italic subtitle
# replaced by a plain uppercase eyebrow.
GATE_STYLE = """<style>
  #gate .gate-frame { max-width: 480px; }
  #gate .gate-card { padding: 38px 44px 34px; border-radius: 14px; }
  #gate .gate-title {
    font-size: 25px; letter-spacing: -0.02em; margin: 0 0 7px;
    white-space: nowrap;
  }
  #gate .gate-kicker {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase;
    color: #7285A5; margin: 0 0 18px;
  }
  #gate .gate-divider { margin: 0 0 20px; }
  #gate .gate-sub { font-size: 12.5px; color: #5a6478; margin: 0 0 22px; }
  #gate label { margin-top: 2px; }
  #gate .gate-hint {
    font-size: 11.5px; color: #8A93A2; margin-top: 16px; text-align: center; line-height: 1.5;
  }
  /* Below the card width the name has to be allowed to wrap, or it overflows the viewport. */
  @media (max-width: 520px) {
    #gate .gate-card { padding: 30px 24px 26px; }
    #gate .gate-title { white-space: normal; font-size: 22px; }
  }
</style>"""

GATE_BODY = """<div id="gate">
    <div class="gate-frame">
      <div class="gate-eyebrow">TwentySix</div>
      <div class="gate-card">
        <h1 class="gate-title">Esm&eacute;e Fairbairn Foundation</h1>
        <div class="gate-kicker">Benefits Benchmark Report &middot; Q3 2026</div>
        <div class="gate-divider"></div>
        <div class="gate-sub">This report sets out the Foundation&rsquo;s benefits alongside
          those of comparable grant-makers and the wider third sector. It is confidential.
          Please sign in with the details sent to you separately.</div>
        <form id="gate-form" autocomplete="off">
          <label for="gate-user">Username</label>
          <input id="gate-user" type="text" autocomplete="username" spellcheck="false" placeholder="Username" />
          <label for="gate-pass">Password</label>
          <input id="gate-pass" type="password" autocomplete="current-password" placeholder="Password" />
          <button type="submit">
            <svg fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"/></svg>
            Open report
          </button>
          <div class="gate-err" id="gate-err" hidden>Those details were not recognised. Please check and try again.</div>
        </form>
        <div class="gate-hint">Any trouble getting in, contact your TwentySix consultant.</div>
      </div>
      <div class="gate-foot">Prepared by TwentySix &middot; Confidential</div>
    </div>
  </div>
  <div id="report-root"></div>"""

GATE_SCRIPT = """<script>
(function () {
  var BUNDLE = __BUNDLE__;
  var STORE = "efb_unlock";

  function b64(s) {
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function deriveKey(secret) {
    var material = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(secret), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt: b64(BUNDLE.salt), iterations: BUNDLE.iterations, hash: "SHA-256" },
      material, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
  }

  async function tryUnlock(u, p) {
    var key = await deriveKey(u + ":" + p);
    var plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64(BUNDLE.iv) }, key, b64(BUNDLE.ct));
    return new TextDecoder().decode(plain);
  }

  function inject(htmlText) {
    var root = document.getElementById("report-root");
    root.innerHTML = htmlText;
    // innerHTML never executes scripts. Re-create every one of them, in order, so the
    // report's own code runs; without this the page renders as an inert skeleton.
    var scripts = root.querySelectorAll("script");
    for (var i = 0; i < scripts.length; i++) {
      var old = scripts[i];
      var s = document.createElement("script");
      for (var j = 0; j < old.attributes.length; j++) {
        s.setAttribute(old.attributes[j].name, old.attributes[j].value);
      }
      s.textContent = old.textContent;
      old.parentNode.replaceChild(s, old);
    }
    var gate = document.getElementById("gate");
    if (gate) gate.remove();
    document.body.classList.add("unlocked");
  }

  function fail() {
    var err = document.getElementById("gate-err");
    if (err) err.hidden = false;
    try { sessionStorage.removeItem(STORE); } catch (e) {}
  }

  // Re-unlock silently on reload so a refresh does not ask again in the same session.
  (async function () {
    var saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(STORE) || "null"); } catch (e) {}
    if (!saved) return;
    try { inject(await tryUnlock(saved.u, saved.p)); } catch (e) { fail(); }
  })();

  document.addEventListener("submit", async function (ev) {
    if (!ev.target || ev.target.id !== "gate-form") return;
    ev.preventDefault();
    var u = document.getElementById("gate-user").value.trim();
    var p = document.getElementById("gate-pass").value;
    var err = document.getElementById("gate-err");
    if (err) err.hidden = true;
    try {
      var html = await tryUnlock(u, p);
      try { sessionStorage.setItem(STORE, JSON.stringify({ u: u, p: p })); } catch (e) {}
      inject(html);
    } catch (e) {
      fail();
    }
  });
})();
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get("EFB_USER"))
    ap.add_argument("--password", default=os.environ.get("EFB_PASS"))
    args = ap.parse_args()
    if not args.user or not args.password:
        sys.exit("no credentials. Pass --user/--password, or set EFB_USER and EFB_PASS.\n"
                 "They are deliberately not stored in this repository, which is public.")

    if not REPORT.exists():
        sys.exit("no _source/report.html; run build/build.py first")
    doc = REPORT.read_text(encoding="utf-8")

    m = re.search(r"(.*?<body[^>]*>)(.*)(</body>.*)", doc, re.S)
    if not m:
        sys.exit("could not split the report into head and body")
    head, body, tail = m.group(1), m.group(2), m.group(3)

    secret = f"{args.user}:{args.password}".encode("utf-8")
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITERATIONS).derive(secret)
    ct = AESGCM(key).encrypt(iv, body.encode("utf-8"), None)

    bundle = {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
        "iterations": ITERATIONS,
    }
    script = GATE_SCRIPT.replace("__BUNDLE__", json.dumps(bundle))
    OUT.write_text(head.replace("</head>", GATE_STYLE + "\n</head>")
                   + "\n  " + GATE_BODY + "\n" + script + "\n" + tail, encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  username {args.user} · password {'*' * len(args.password)}")
    print(f"  {len(body):,} chars of report encrypted -> {len(bundle['ct']):,} chars of ciphertext")
    print(f"  AES-256-GCM, PBKDF2-SHA256 x{ITERATIONS:,}, fresh salt and iv")


if __name__ == "__main__":
    main()
