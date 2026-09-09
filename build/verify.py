#!/usr/bin/env python3
"""
Checks that must pass before the report goes to a client.

    python3 build/verify.py            # structural checks on _source/report.html
    python3 build/verify.py --browser  # also drive the page in headless Chromium

Two classes of check. The structural ones catch the failure this template invites: the
same quartile stated in two places, drifting apart. The browser ones catch the failure a
grep cannot see, which is a page that builds fine and then throws on load.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "_source" / "report.html"
DATA = ROOT / "_source" / "data" / "market.json"

fails, warns = [], []


def check(ok, msg):
    (fails if not ok else []).append(msg) if not ok else None
    print(("  ok   " if ok else "  FAIL ") + msg)


def warn(ok, msg):
    if not ok:
        warns.append(msg)
    print(("  ok   " if ok else "  warn ") + msg)


def js_object(text, name):
    """Pull `var NAME = <json>;` out of the report and parse it."""
    m = re.search(rf"var {name} = (.+?);\n", text, re.S)
    if not m:
        sys.exit(f"could not find var {name}")
    return json.loads(m.group(1))


def main():
    t = REPORT.read_text(encoding="utf-8")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    benefits = data["benefits"]

    print("\nData integrity")
    haq = js_object(t, "HA_Q")
    blist = js_object(t, "BENEFITS")
    mcat = js_object(t, "MARKET_CAT")

    market_slugs = {s for s, b in benefits.items() if not b.get("noMarket")}
    check(set(haq) == market_slugs, f"HA_Q holds exactly the {len(market_slugs)} market benefits")
    check(set(mcat) == market_slugs, "MARKET_CAT keys match HA_Q keys")

    missing = [b["slug"] for b in blist if not b.get("noMarket") and b["slug"] not in haq]
    check(not missing, f"every benefit with a market position has an HA_Q entry {missing or ''}")

    # The trap this build exists to close: the table markup and HA_Q must agree.
    drift = []
    for slug, q in haq.items():
        row = re.search(rf'<tr class="brow haq-row" data-slug="{slug}">(.*?)</tr>', t, re.S)
        if not row:
            drift.append(f"{slug}: no table row")
            continue
        vals = re.findall(r'<span class="haq-val">(.*?)</span>', row.group(1))
        want = [q["lq"], q["m"], q["uq"]]
        import html as _h
        if [_h.unescape(v) for v in vals] != want:
            drift.append(f"{slug}: table {vals} vs HA_Q {want}")
    check(not drift, "every market table row matches its HA_Q entry")
    for d in drift:
        print("         " + d)

    print("\nCounts shown to the reader")
    counts = {"above": 0, "at": 0, "watch": 0, "below": 0}
    for b in benefits.values():
        if b.get("esmee"):
            counts[b["esmee"]["badge"]] += 1
    total = sum(counts.values())
    stats = dict(zip(
        re.findall(r'prov-stat prov-stat-(\w+)"', t),
        [int(x) for x in re.findall(r'<div class="prov-stat-num">(\d+)</div>', t)]))
    check(stats.get("total") == total, f"stat tile total is {total}")
    check(stats.get("above") == counts["above"], f"stat tile above is {counts['above']}")
    check(stats.get("at") == counts["at"], f"stat tile at market is {counts['at']}")
    check(stats.get("mixed") == counts["watch"], f"stat tile worth a look is {counts['watch']}")
    check(stats.get("below") == counts["below"], f"stat tile below is {counts['below']}")
    check(len(re.findall(r'class="rb-panel"', t)) == total, f"{total} provision cards rendered")

    print("\nNo previous client left in the file")
    # "perkbox" is no longer a marker: the Wellcome Trust example package legitimately names
    # it as one of their published benefits. Test the template's own phrasing instead.
    for term in ("brighton", "penge", "technolog", "hsf", "housing association", "bcs",
                 "hsf + perkbox", "zigbert"):
        check(term not in t.lower(), f'no "{term}"')

    print("\nNo peer organisation named in client-facing copy")
    # Another TwentySix client's package must never appear in this report, and the user
    # asked that comparable funders be referred to generically rather than by name.
    import re as _re
    visible = _re.sub(r"<[^>]+>", " ", _re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t))
    for org in ("Wellcome", "Joseph Rowntree", "Paul Hamlyn", "Nuffield", "City Bridge",
                "Comic Relief", "Health Foundation", "Shelter", "Barnardo", "MS Trust",
                "Age UK", "National Lottery", "Virgin", "Guy", "GSTF", "St Thomas"):
        hits = _re.findall(r"(?<![A-Za-z])" + _re.escape(org) + r"(?![A-Za-z])", visible)
        check(not hits, f'"{org}" is not named')

    print("\nComparators")
    check("Large Private" not in t and "Small Private" not in t, "private-sector columns removed")
    check(t.count("Grant-making foundations") > 5, "foundations named as primary comparator")
    check("Wider third sector" in t, "wider third sector named as secondary comparator")
    check(len(re.findall(r'class="sector-footer-card', t)) == 6,
          "one third-sector footer card per category page")

    print("\nHouse style")
    # Strip scripts, styles and HTML comments: none of the three reach the reader, and
    # the template's own comments legitimately use em dashes.
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    ems = body.count("—")
    warn(ems == 0, f"no em dashes in reader-visible copy (found {ems})")

    print("\nNo demo artefacts")
    check("illustrative sample data" not in t.lower(), "sample-data badge removed")
    check("Sample data" not in t, "no sample-data wording anywhere")

    print("\nCSV export header")
    check('"Benefit","Lower Quartile","Median","Upper Quartile"' in t,
          "CSV header names the columns tableToCsv actually writes")

    if "--browser" in sys.argv:
        browser_checks()
    if "--gate" in sys.argv:
        gate_checks()

    print()
    if fails:
        print(f"{len(fails)} CHECK(S) FAILED")
        sys.exit(1)
    print(f"all checks passed{f', {len(warns)} warning(s)' if warns else ''}")


def browser_checks():
    from playwright.sync_api import sync_playwright
    print("\nBrowser")
    # The report resolves ./shell/* relative to itself, and ships at the site root, so it
    # has to be served from the repo root to test it as deployed. Gitignored, removed after.
    preview = ROOT / "_preview.html"
    preview.write_text(REPORT.read_text(encoding="utf-8"), encoding="utf-8")
    pages = ["overview", "provision", "core", "working-time", "health",
             "financial", "esg", "learning", "trends", "action-plan"]
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(preview.as_uri())
        pg.wait_for_timeout(700)
        check(not errors, f"no JavaScript errors on load {errors[:2] or ''}")

        for name in pages:
            pg.evaluate(f"location.hash = '{name}'")
            pg.wait_for_timeout(160)
            vis = pg.eval_on_selector(
                f'.page[data-page="{name}"]',
                "el => el.classList.contains('active') && el.offsetHeight > 200")
            check(vis, f"page renders: {name}")

        pg.evaluate("location.hash = 'overview'")
        pg.wait_for_timeout(200)
        for sel, label in (("#bx-verdict", "verdict headline"),
                           ("#bx-kpis", "KPI row"),
                           ("#bx-scorecard", "category scorecard"),
                           ("#bx-search", "benefit search"),
                           ('.navlink[data-page="action-plan"]', "action plan nav link"),
                           (".sidebar-nav", "sidebar")):
            check(pg.eval_on_selector(sel, "el => el.innerHTML.length > 0 || el.tagName === 'INPUT'"),
                  f"tour anchor present and populated: {label}")

        # The action plan is generated, so an empty one is a silent failure.
        pg.evaluate("location.hash = 'action-plan'")
        pg.wait_for_timeout(400)
        rows = pg.eval_on_selector("#bx-plan", "el => el.children.length")
        check(rows > 0, f"action plan generated {rows} rows")

        pg.evaluate("location.hash = 'provision'")
        pg.wait_for_timeout(250)
        data = json.loads(DATA.read_text(encoding="utf-8"))["benefits"]
        held = [b for b in data.values() if b.get("esmee")]
        shown = pg.eval_on_selector_all(".rb-panel", "els => els.filter(e => e.offsetHeight > 0).length")
        check(shown == len(held), f"all {len(held)} provision cards visible (saw {shown})")

        # Expected counts come from the data, so the filters stay tested as positions change.
        for filt, badge in (("above", "above"), ("green", "at"), ("amber", "watch")):
            want = sum(1 for b in held if b["esmee"]["badge"] == badge)
            if not want:
                continue
            pg.click(f'.prov-stat[data-filter="{filt}"]')
            pg.wait_for_timeout(250)
            got = pg.eval_on_selector_all(".rb-panel", "els => els.filter(e => e.offsetHeight > 0).length")
            check(got == want, f"{badge} filter narrows to {want} cards (saw {got})")

        # ── Tours ──────────────────────────────────────────────────────────────
        # A tour step whose anchor is missing does NOT fail loudly: findTarget polls for
        # about four seconds and renders nothing, so the button just looks broken. Audit
        # every anchor rather than trusting that the tours open.
        anchors = pg.evaluate("""() => {
          const T = window.TwentySixTour.tours, out = [];
          for (const key of Object.keys(T)) {
            location.hash = key;
            for (const [i, st] of T[key].steps.entries()) {
              let el = null;
              try { el = document.querySelector(st.selector); } catch (e) {}
              out.push({tour: key, step: i + 1, sel: st.selector, ok: !!el});
            }
          }
          return out;
        }""")
        missing = [a for a in anchors if not a["ok"]]
        check(not missing, f"all {len(anchors)} tour anchors resolve across "
                           f"{len(set(a['tour'] for a in anchors))} tours")
        for a in missing:
            print(f"         MISSING {a['tour']} step {a['step']}: {a['sel']}")

        # The original tour matched the URL path for "/benefits", which never appears in
        # "/esmee-benefits/", so every page silently ran the Home tour instead.
        for name in pages:
            pg.evaluate(f"location.hash = '{name}'")
            pg.wait_for_timeout(320)
            if pg.eval_on_selector_all(".tstour-welcome-later", "e => e.length"):
                pg.click(".tstour-welcome-later")
                pg.wait_for_timeout(150)
            pg.click(".ts-shell__tour")
            pg.wait_for_timeout(900)
            shown = pg.eval_on_selector_all(".tstour-card", "e => e.filter(x => x.offsetHeight > 0).length")
            check(shown == 1, f"Tour this page opens a coachmark on {name}")
            pg.evaluate("window.TwentySixTour.stop()")
            pg.wait_for_timeout(120)

        # ── Per-page help ─────────────────────────────────────────────────────
        for name in pages:
            n = pg.eval_on_selector_all(f'.page[data-page="{name}"] details.efb-help', "e => e.length")
            check(n == 1, f"help panel present on {name}")

        # ── Scroll behaviour ──────────────────────────────────────────────────
        # goTo() called window.scrollTo, but BODY carries overflow-y:auto, so nothing moved
        # and switching pages left the reader halfway down the previous one.
        def scroll_top():
            return pg.evaluate("document.body.scrollTop")
        # Reload first: the tour loop above visited every page and scrolled each one to its
        # step anchors, so those positions are legitimately remembered by now. Scroll memory
        # is per session, so a fresh load is what an unread page actually looks like.
        pg.goto(preview.as_uri()); pg.wait_for_timeout(1400)
        if pg.eval_on_selector_all(".tstour-welcome-later", "e => e.length"):
            pg.click(".tstour-welcome-later"); pg.wait_for_timeout(200)
        pg.evaluate("location.hash = 'core'"); pg.wait_for_timeout(500)
        pg.evaluate("document.body.scrollTop = 800"); pg.wait_for_timeout(250)
        moved = scroll_top()
        check(moved > 400, f"the page actually scrolls (body scrollTop {moved})")
        pg.click('.navlink[data-page="health"]'); pg.wait_for_timeout(600)
        check(scroll_top() == 0, "an unread page opens at the top")
        pg.click('.navlink[data-page="core"]'); pg.wait_for_timeout(600)
        check(scroll_top() == moved, f"a page already read is restored to where you left it ({moved})")

        # ── Labels, not titleized slugs ───────────────────────────────────────
        pg.evaluate("location.hash = 'core'"); pg.wait_for_timeout(700)
        names = pg.eval_on_selector_all(".bx-sec-name", "e => e.map(x => x.textContent)")
        check(len(names) > 5, f"compare-the-market rows render ({len(names)})")
        for wrong in ("Pension Employer", "Holiday Buy Sell", "Phi", "Eap"):
            check(wrong not in names, f'compare-the-market avoids the titleized slug "{wrong}"')

        # ── Explanatory copy ──────────────────────────────────────────────────
        check(pg.eval_on_selector_all('[data-tour="intro"]', "e => e.length") == 1,
              "overview carries the what-this-report-is intro")
        check(pg.eval_on_selector_all('[data-tour="plan-intro"]', "e => e.length") == 1,
              "action plan carries the how-to-use-it intro")

        # ── Trends ────────────────────────────────────────────────────────────
        pg.evaluate("location.hash = 'trends'"); pg.wait_for_timeout(450)
        data = json.loads(DATA.read_text(encoding="utf-8"))
        bens = data["benefits"]
        want = [b["label"] for b in bens.values()
                if not b.get("esmee") and not b.get("excludeFromConsider") and not b.get("minor")]
        # Esmee publishes a sabbatical, so suggesting one would tell the client to adopt
        # something they already offer. It is held as a query instead.
        appendix_names = pg.eval_on_selector_all('.efb-ap-name', "e => e.map(x => x.textContent)")
        check(pg.eval_on_selector_all('.efb-tr-query', "e => e.length") == 0,
              "Trends does not air the open query to the client")
        check(pg.eval_on_selector_all('.efb-aon-col', "e => e.length") == 2,
              "Trends carries both Aon emphasis columns")
        check(pg.eval_on_selector_all('.efb-th', "e => e.length") == len(data["narrative"]["themes"]["sections"]),
              f"Trends carries all {len(data['narrative']['themes']['sections'])} theme sections")
        # Trends is now the consultant's write-up only. The market-derived suggestions moved
        # to the Action Plan, so none of those blocks should still be on this page.
        for cls in (".efb-tr-card", ".efb-idea", ".efb-minor", ".efb-pk"):
            check(pg.eval_on_selector_all(cls, "e => e.length") == 0,
                  f"Trends no longer carries {cls}")
        con = data["narrative"]["themes"]["consider"]
        check(pg.eval_on_selector_all('.efb-cn-group', "e => e.length") == len(con),
              f"Trends groups the initiatives into all {len(con)} themes")
        want_rows = sum(len(g["items"]) for g in con)
        check(pg.eval_on_selector_all('.efb-cn-row', "e => e.length") == want_rows,
              f"Trends lists all {want_rows} initiatives with their reasoning")
        have = sum(1 for g in con for i in g["items"] if i.get("have"))
        check(pg.eval_on_selector_all('.efb-cn-have', "e => e.length") == have,
              f"the {have} initiatives Esmee already provides are marked, not suggested")
        check(pg.eval_on_selector_all('.efb-wb-item', "e => e.length") == len(data["narrative"]["wellbeing"]["items"]),
              "Trends carries the wellbeing strategy example")

        # Our read of the position opens Your Benefits, and the method note is on Overview.
        pg.evaluate("location.hash = 'provision'"); pg.wait_for_timeout(400)
        check(pg.eval_on_selector_all('.efb-pos', "e => e.length") == 1,
              "Your Benefits opens with our read of the market position")
        first = pg.eval_on_selector('.page[data-page="provision"] .bx-wrap > *, .page[data-page="provision"] > * > *',
                                    "e => e.className")
        pg.evaluate("location.hash = 'overview'"); pg.wait_for_timeout(400)
        check(pg.eval_on_selector_all('.efb-meth', "e => e.length") == 1,
              "Overview carries the what-we-did note")
        surveys = pg.eval_on_selector('.efb-meth', "e => e.textContent")
        for survey in ("Alan Jones Associates", "CIPD Reward Management Survey",
                       "Reward & Employee Benefits Association", "ThanksBen", "Drewberry",
                       "Great Places to Work", "careers pages",
                       # Folded in from the separate sources block, which is gone.
                       "Association of Charitable Foundations", "147 responding foundations",
                       "Office for National Statistics", "employers that publish a figure"):
            check(survey in surveys, f'what-we-did names "{survey}"')
        check(pg.eval_on_selector_all('.efb-sources', "e => e.length") == 0,
              "the separate where-these-figures-come-from block is gone")

        # Compare the market renders the sp field, so every market benefit needs one.
        missing_sp = [s for s, x in bens.items()
                      if not x.get("noMarket") and not (x.get("sp") or "").strip()]
        check(not missing_sp, f"every market benefit has a wider-sector value ({len(bens)-1-len(missing_sp)})")
        for s2 in missing_sp:
            print(f"         MISSING sp: {s2}")
        check("trends" in pg.eval_on_selector_all('.navlink', "e => e.map(x => x.dataset.page)"),
              "Trends has a sidebar nav link")
        order = pg.eval_on_selector_all('.navlink', "e => e.map(x => x.dataset.page)")
        check(order.index("trends") == order.index("learning") + 1
              and order.index("action-plan") == order.index("trends") + 1,
              "Trends sits between Learning & Development and Action Plan")
        # "Other benefits to consider" must also reach the downloadable report.
        pg.evaluate("location.hash = 'action-plan'"); pg.wait_for_timeout(400)
        check(pg.eval_on_selector_all('.efb-ap-consider', "e => e.length") == 1,
              "Action Plan carries the other-benefits-to-consider appendix")
        ap_rows = pg.eval_on_selector_all('.efb-ap-row', "e => e.length")
        check(ap_rows == len(want), f"the appendix lists the same {len(want)} benefits")

        br.close()
    preview.unlink(missing_ok=True)


def gate_checks():
    """
    The published index.html must reveal nothing until the passphrase is correct.

    Credentials come from the environment, never from this file: it is committed to a public
    repository, so a hardcoded passphrase would be published next to the ciphertext.
        EFB_USER=... EFB_PASS=... python3 build/verify.py --gate
    """
    import os
    from playwright.sync_api import sync_playwright
    user, pw = os.environ.get("EFB_USER"), os.environ.get("EFB_PASS")
    if not (user and pw):
        print("\nGate\n  skipped: set EFB_USER and EFB_PASS to run the gate checks")
        return
    idx = ROOT / "index.html"
    print("\nGate")
    body = idx.read_text(encoding="utf-8")
    # CSS class names still appear as selectors in the unencrypted stylesheet, which leaks
    # nothing. Test for the rendered markup and the data, not for the selector.
    for term in ("12.5%", "Joseph Rowntree", "HA_Q", 'class="rb-panel"', "Give As You Earn",
                 "Barrow Cadbury", "26 weeks", "Christmas closure"):
        check(term not in body, f'ciphertext hides "{term}" from the published file')

    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(idx.as_uri()); pg.wait_for_timeout(600)
        check(pg.is_visible("#gate"), "gate shown on arrival")
        check(pg.eval_on_selector_all(".page", "e => e.length") == 0, "no report content before unlock")

        pg.fill("#gate-user", user); pg.fill("#gate-pass", "definitely-not-the-passphrase")
        pg.click("#gate-form button"); pg.wait_for_timeout(1500)
        check(pg.is_visible("#gate-err"), "wrong passphrase rejected")
        check(pg.eval_on_selector_all(".page", "e => e.length") == 0, "wrong passphrase reveals nothing")

        pg.fill("#gate-pass", pw); pg.click("#gate-form button"); pg.wait_for_timeout(2500)
        check(pg.eval_on_selector_all("#gate", "e => e.length") == 0, "gate removed after unlock")
        check(pg.eval_on_selector_all(".page", "e => e.length") == 10, "all 10 pages injected")
        # innerHTML does not run scripts; if the re-creation step regressed, this is what catches it.
        check(pg.eval_on_selector_all(".rb-panel", "e => e.length") == 16,
              "injected scripts executed and rendered 16 cards")
        check("at or above market" in (pg.text_content("#bx-verdict") or ""), "verdict rendered")

        # The Foundation's name wrapped onto two lines in the login card, which is the
        # first thing the client sees.
        pg.reload(); pg.wait_for_timeout(600)
        if pg.eval_on_selector_all("#gate .gate-title", "e => e.length"):
            lines = pg.eval_on_selector(".gate-title", "e => e.getClientRects().length")
            check(lines == 1, f"login title sits on one line (got {lines})")

        pg.wait_for_timeout(1600)
        check(pg.eval_on_selector_all(".page", "e => e.length") == 10, "reload auto-unlocks in the same session")
        check(not errs, f"no JavaScript errors through the gate {errs[:2] or ''}")
        br.close()


if __name__ == "__main__":
    main()
