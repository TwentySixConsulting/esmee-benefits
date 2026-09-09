/* TwentySix — per-area guided tours.
 * Framework-agnostic: loaded on the React app AND the static Pay/Benefits pages.
 *
 * Five short, self-contained tours (3–5 steps, ~40 seconds), one per area. A tour
 * NEVER leaves its own page, so there is no navigation mid-tour. Each is offered
 * once, on first arrival at that area, so the explanation lands where the feature
 * is rather than minutes before the user gets there.
 *
 * Tours are never chained. Each one ends where it started, and the user is nudged
 * about the next area only when they navigate there themselves. The sole exception
 * is the Home checklist, where picking an area is an explicit request to go and
 * tour it; progress persists in localStorage so that survives the full-page load
 * between the three apps.
 *
 * Exposes window.TwentySixTour = {start, startTour, stop, resume}.
 */
(function () {
  "use strict";
  if (window.TwentySixTour) return; // already loaded

  var KEY = "ts26:tour";              // { active, tour, step } — in-flight position
  var DONE = "ts26:tour-done";        // { home: ts, pay: ts, … } — tours completed
  var OFFERED = "ts26:tour-offered";  // { home: ts, … } — first-run prompt already shown
  var LEGACY = "ts26:tour-seen";      // pre-split single flag, migrated on first load
  var CL_OFF = "ts26:tour-checklist-off";

  // ── state ────────────────────────────────────────────────────
  function getState() {
    try { var r = localStorage.getItem(KEY); return r ? JSON.parse(r) : { active: false }; }
    catch (e) { return { active: false }; }
  }
  function setState(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  function clearState() { try { localStorage.removeItem(KEY); } catch (e) {} }

  function getMap(k) {
    try { var r = localStorage.getItem(k); var v = r ? JSON.parse(r) : null; return (v && typeof v === "object") ? v : {}; }
    catch (e) { return {}; }
  }
  function mark(k, tour) {
    try { var m = getMap(k); m[tour] = Date.now(); localStorage.setItem(k, JSON.stringify(m)); } catch (e) {}
  }
  function isDone(tour) { return !!getMap(DONE)[tour]; }
  function wasOffered(tour) { return !!getMap(OFFERED)[tour]; }

  // Anyone who saw the old single 28-step tour shouldn't be prompted again on Home,
  // but should still be offered the new short tours for the other areas.
  function migrateLegacy() {
    try {
      if (!localStorage.getItem(LEGACY)) return;
      var m = getMap(OFFERED);
      if (m.home) return;
      mark(OFFERED, "home");
    } catch (e) {}
  }

  function authed() {
    // This file ships inside the encrypted payload, so it only ever runs after the gate has
    // been passed. Checking a login key that no longer exists would disable every prompt.
    return true;
  }
  function authedLegacyUnused() {
    try {
      if (localStorage.getItem("demo-client-dashboard:temp-auth")) return true;
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf("sb-") === 0 && k.indexOf("-auth-token") !== -1) return true;
      }
    } catch (e) {}
    return false;
  }

  // ── the tours ────────────────────────────────────────────────
  // This is a standalone, benefits-only report: one HTML document with a hash router,
  // not the multi-app TwentySix platform. So there is one tour per REPORT PAGE, keyed by the
  // page's data-page slug, and every step's anchor lives on that page. No tour navigates.
  var TOURS = {
    overview: {
      label: "Overview", secs: 40, page: "overview",
      steps: [
        { selector: "[data-tour='intro']", placement: "bottom",
          title: "Start here",
          html: "What this report is, who you have been compared against, and how to read it. Worth a minute before anything else." },
        { selector: "#bx-verdict", placement: "bottom",
          title: "Your headline position",
          html: "One sentence for the whole package, with the four numbers behind it underneath: how many benefits were reviewed, how many are at or above the market, and how many need a look." },
        { selector: "#bx-search", placement: "bottom",
          title: "Jump to any benefit",
          html: "Type a benefit name, for example <b>pension</b> or <b>sick pay</b>, to go straight to it." },
        { selector: "#bx-scorecard", placement: "top",
          title: "The six categories",
          html: "Your position in each of the six benefit categories. Click any card to open that category's market detail." },
        { selector: ".navlink[data-page='action-plan']", placement: "right",
          title: "Where to go next",
          html: "<b>Your Benefits</b> shows all sixteen benefits side by side with the market. <b>Action Plan</b> turns the gaps into a prioritised list." },
      ],
    },

    provision: {
      label: "Your Benefits", secs: 40, page: "provision",
      steps: [
        { selector: ".yb-overview", placement: "bottom",
          title: "The summary first",
          html: "Your strengths and the areas worth attention, drawn from the benchmarking rather than written by hand." },
        { selector: ".prov-summary", placement: "bottom",
          title: "Filter by position",
          html: "Five counts across your benefits. <b>Click any one of them</b> to show only those benefits, and click again to clear it." },
        { selector: ".rb-panel", placement: "bottom",
          title: "One card per benefit",
          html: "Your provision on the left, the foundation market on the right. The marker on the bar is you; the three cards beneath it are the lower quartile, median and upper quartile." },
        { selector: ".rb-png-btn", placement: "left",
          title: "Take any card away",
          html: "<b>PNG</b> saves that single card as an image, ready to drop into a board paper or a slide." },
      ],
    },

    core: catTour("core", "Core Benefits"),
    "working-time": catTour("working-time", "Working Time"),
    health: catTour("health", "Health & Wellbeing"),
    financial: catTour("financial", "Financial Support"),
    esg: catTour("esg", "ESG & DEI"),
    learning: catTour("learning", "Learning & Development"),

    trends: {
      label: "Trends", secs: 35, page: "trends",
      steps: [
        { selector: "[data-page='trends'] .efb-aon", placement: "bottom",
          title: "Where the market is moving",
          html: "The themes every benefits survey we reviewed agreed on, summarised by Aon. Note how few of them are traditional benefits at all." },
        { selector: "[data-page='trends'] .efb-th", placement: "bottom",
          title: "Each theme in turn",
          html: "What is actually happening in each area, and the forms the provision typically takes." },
        { selector: "[data-page='trends'] .efb-cn", placement: "top",
          title: "You might also consider",
          html: "Every initiative named in the research, grouped by theme, with the reasoning behind each one. Anything Esm&eacute;e already provides is marked as such." },
        { selector: "[data-page='trends'] .efb-wb", placement: "top",
          title: "Pulling it together",
          html: "The current thinking is that well-being should be a strategy rather than a set of separate initiatives. This is one organisation's version of that." },
      ],
    },

    "action-plan": {
      label: "Action Plan", secs: 40, page: "action-plan",
      steps: [
        { selector: "[data-tour='plan-intro']", placement: "bottom",
          title: "What this page is for",
          html: "A prioritised shortlist, built from the benchmarking. It answers one question: if you were going to change something, what should it be and in what order." },
        { selector: "[data-tour='plan-ambition']", placement: "bottom",
          title: "Set the ambition",
          html: "<b>Match the market</b> targets the median, which is the cost of no longer being behind. <b>Lead the market</b> targets the upper quartile, which is the cost of being a destination employer. Switch between them to see how the list and the targets change." },
        { selector: "[data-tour='plan-focus']", placement: "bottom",
          title: "Narrow it down",
          html: "Limit the plan to one benefit category, for example if this year's budget is only for family leave." },
        { selector: "#bx-plan-summary", placement: "bottom",
          title: "The shape of the plan",
          html: "Priorities to act on, quick wins that cost little, and the strengths worth protecting because they are already ahead." },
        { selector: "#bx-plan", placement: "top",
          title: "Each priority in turn",
          html: "Most urgent first. Each row shows where you sit, the market target, and a recommended next step. <b>Download report</b> or <b>CSV</b> takes the plan away with you." },
      ],
    },
  };

  // The six market pages are identical in shape, so their tours are too. Writing them out
  // six times would guarantee they drift apart the first time one of them is edited.
  function catTour(slug, label) {
    return {
      label: label, secs: 35, page: slug,
      steps: [
        { selector: "[data-page='" + slug + "'] .page-overview", placement: "bottom",
          title: "What this page covers",
          html: "Typical market practice for the " + label.toLowerCase() + " benefits, and which of them this page includes." },
        { selector: "[data-page='" + slug + "'] .bx-market-top", placement: "bottom",
          title: "You against the market",
          html: "On the left, where your own provision sits in this category. On the right, the same benefits for the wider third sector, so you can switch comparator." },
        { selector: "[data-page='" + slug + "'] .haq-tbl", placement: "top",
          title: "The quartile table",
          html: "Lower quartile, median and upper quartile for each benefit. <b>Click any row</b> to open the full description of what employers at each level actually provide." },
        { selector: "[data-page='" + slug + "'] .exp-toolbar", placement: "bottom",
          title: "Search and export",
          html: "Filter the table, expand every row at once, or take the page away as Excel or PDF." },
      ],
    };
  }

  var ORDER = ["overview", "provision", "core", "working-time", "health",
               "financial", "esg", "learning", "trends", "action-plan"];

  // ── which page are we on ─────────────────────────────────────
  // The original version matched the URL PATH for "/benefits". That silently broke here:
  // this report is served from "/esmee-benefits/", where the literal "/benefits" never
  // appears, so every page fell through to the Home tour and "Tour this page" ran a tour
  // whose anchors do not exist. findTarget polls for ~4s per step and renders nothing, so
  // the button looked dead rather than wrong. Pages are hash routes here, so read the hash.
  function currentPage() {
    var h = (location.hash || "").replace(/^#/, "").trim();
    return TOURS[h] ? h : "overview";
  }
  function tourHere() { return currentPage(); }
  function isHere(key) { return tourHere() === key; }
  // Nothing to navigate to: every tour lives on the page it belongs to.
  function urlFor(key) { return "#" + key; }
  function siteRoot() { return location.pathname; }

  // ── DOM ──────────────────────────────────────────────────────
  var root = null, hole = null, card = null, catcher = null;
  var reposition = null, findTimer = null, navigating = false;

  function build() {
    if (root) return;
    root = document.createElement("div");
    root.className = "tstour-root";
    root.innerHTML =
      '<div class="tstour-catch"></div>' +
      '<div class="tstour-hole"></div>' +
      '<div class="tstour-card" role="dialog" aria-modal="true" aria-labelledby="tstour-title">' +
        '<button class="tstour-close" aria-label="Close tour">×</button>' +
        '<div class="tstour-progress"><span class="tstour-bar"></span></div>' +
        '<div class="tstour-count"></div>' +
        '<h3 class="tstour-title" id="tstour-title"></h3>' +
        '<div class="tstour-body"></div>' +
        '<div class="tstour-foot">' +
          '<button class="tstour-skip" type="button">Skip</button>' +
          '<div class="tstour-nav">' +
            '<button class="tstour-back" type="button">Back</button>' +
            '<button class="tstour-next tstour-primary" type="button">Next</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(root);
    hole = root.querySelector(".tstour-hole");
    card = root.querySelector(".tstour-card");
    catcher = root.querySelector(".tstour-catch");

    catcher.addEventListener("click", stop);
    root.querySelector(".tstour-close").addEventListener("click", stop);
    root.querySelector(".tstour-skip").addEventListener("click", stop);
    root.querySelector(".tstour-back").addEventListener("click", back);
    root.querySelector(".tstour-next").addEventListener("click", onNext);
    card.addEventListener("click", function (e) { e.stopPropagation(); });
    document.addEventListener("keydown", onKey, true);
  }

  function teardown() {
    if (reposition) { window.removeEventListener("scroll", reposition, true); window.removeEventListener("resize", reposition); reposition = null; }
    if (findTimer) { clearInterval(findTimer); findTimer = null; }
    document.removeEventListener("keydown", onKey, true);
    if (root && root.parentNode) root.parentNode.removeChild(root);
    root = hole = card = catcher = null;
  }

  function onKey(e) {
    if (!root) return;
    if (e.key === "Escape") { e.preventDefault(); stop(); }
    else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); onNext(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); back(); }
  }

  // ── positioning ──────────────────────────────────────────────
  function findTarget(sel, cb) {
    if (findTimer) { clearInterval(findTimer); findTimer = null; }
    var el = sel ? document.querySelector(sel) : null;
    if (el || !sel) { cb(el); return; }
    var tries = 0;
    findTimer = setInterval(function () {
      tries++;
      var found = document.querySelector(sel);
      if (found || tries > 40) { clearInterval(findTimer); findTimer = null; cb(found || null); }
    }, 100); // up to ~4s for late-rendered targets
  }

  function place(el) {
    if (reposition) { window.removeEventListener("scroll", reposition, true); window.removeEventListener("resize", reposition); }
    reposition = function () { position(el); };
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    position(el);
  }

  function position(el) {
    if (!root) return;
    var vw = window.innerWidth, vh = window.innerHeight, pad = 8, gap = 14;
    if (!el) {
      hole.style.display = "none";
      card.style.left = Math.round((vw - card.offsetWidth) / 2) + "px";
      card.style.top = Math.round((vh - card.offsetHeight) / 2) + "px";
      return;
    }
    var r = el.getBoundingClientRect();
    hole.style.display = "block";
    hole.style.left = (r.left - pad) + "px";
    hole.style.top = (r.top - pad) + "px";
    hole.style.width = (r.width + pad * 2) + "px";
    hole.style.height = (r.height + pad * 2) + "px";

    var cw = card.offsetWidth, ch = card.offsetHeight;
    var pref = card.getAttribute("data-place") || "bottom";
    var spot = { bottom: vh - r.bottom, top: r.top, right: vw - r.right, left: r.left };
    var order = [pref, "bottom", "top", "right", "left"];
    var chosen = "bottom";
    for (var i = 0; i < order.length; i++) {
      var p = order[i];
      if ((p === "bottom" || p === "top") && spot[p] >= ch + gap + pad) { chosen = p; break; }
      if ((p === "left" || p === "right") && spot[p] >= cw + gap + pad) { chosen = p; break; }
    }
    var left, top;
    if (chosen === "bottom" || chosen === "top") {
      left = r.left + r.width / 2 - cw / 2;
      top = chosen === "bottom" ? r.bottom + gap : r.top - ch - gap;
    } else {
      top = r.top + r.height / 2 - ch / 2;
      left = chosen === "right" ? r.right + gap : r.left - cw - gap;
    }
    left = Math.max(pad, Math.min(left, vw - cw - pad));
    top = Math.max(pad, Math.min(top, vh - ch - pad));
    card.style.left = Math.round(left) + "px";
    card.style.top = Math.round(top) + "px";
  }

  // ── rendering a step ─────────────────────────────────────────
  function showStep(key, i) {
    var tour = TOURS[key], steps = tour.steps, step = steps[i], last = i === steps.length - 1;
    build();

    // Reaching the final card counts as completing the tour, however it's closed.
    if (last) { mark(DONE, key); renderChecklist(); }

    card.setAttribute("data-place", step.placement || "bottom");
    root.querySelector(".tstour-title").innerHTML = step.title;
    root.querySelector(".tstour-body").innerHTML = step.html;
    root.querySelector(".tstour-count").textContent = tour.label + " · " + (i + 1) + " of " + steps.length;
    root.querySelector(".tstour-bar").style.width = Math.round(((i + 1) / steps.length) * 100) + "%";
    root.querySelector(".tstour-back").style.visibility = i === 0 ? "hidden" : "visible";

    // Every tour ends where it started. The next area is never chained on; the
    // user gets nudged when they navigate there themselves (see maybeOffer).
    var skipBtn = root.querySelector(".tstour-skip");
    var nextBtn = root.querySelector(".tstour-next");
    skipBtn.style.display = last ? "none" : "";
    if (!last) skipBtn.textContent = "Skip";
    nextBtn.textContent = last ? "Done" : "Next";
    nextBtn.setAttribute("data-last", last ? "1" : "");

    findTarget(step.selector, function (el) {
      if (!root) return;
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "center", behavior: "smooth" });
      setTimeout(function () { place(el); root.classList.add("tstour-in"); }, el ? 260 : 0);
    });
  }

  // show the current step, or navigate to the tour that owns it
  function render() {
    var s = getState();
    if (!s.active || !TOURS[s.tour]) { teardown(); return; }
    var tour = TOURS[s.tour];
    var i = Math.max(0, Math.min(s.step || 0, tour.steps.length - 1));

    if (isHere(s.tour)) {
      navigating = false;
      try { sessionStorage.removeItem("tstour-nav"); } catch (e) {}
      showStep(s.tour, i);
      return;
    }
    if (navigating) return;

    // Loop guard: if we just navigated here for this same tour and landed
    // somewhere else, give up quietly rather than ping-pong.
    var g = null;
    try { g = JSON.parse(sessionStorage.getItem("tstour-nav") || "null"); } catch (e) {}
    if (g && g.tour === s.tour && (Date.now() - g.t) < 5000) { stop(); return; }
    try { sessionStorage.setItem("tstour-nav", JSON.stringify({ tour: s.tour, t: Date.now() })); } catch (e) {}
    navigating = true;
    window.location.href = urlFor(s.tour);
  }

  function go(delta) {
    var s = getState();
    if (!s.active || !TOURS[s.tour]) return;
    var n = TOURS[s.tour].steps.length;
    var i = Math.max(0, Math.min((s.step || 0) + delta, n - 1));
    setState({ active: true, tour: s.tour, step: i });
    render();
  }
  function back() { go(-1); }

  function onNext() {
    var btn = root && root.querySelector(".tstour-next");
    if (btn && btn.getAttribute("data-last")) { stop(); return; }
    go(1);
  }

  function startTour(key) {
    if (!TOURS[key]) return;
    mark(OFFERED, key);
    dismissPrompt();
    setState({ active: true, tour: key, step: 0 });
    navigating = false;
    teardown();
    render();
  }
  // "Tour this page" — whatever page the user is standing on
  function start() {
    var key = tourHere();
    if (key) startTour(key);
  }
  function stop() {
    clearState();
    teardown();
    renderChecklist();
  }
  function resume() { render(); }

  // ── first-run prompt, once per area ──────────────────────────
  var prompt = null;
  function dismissPrompt() {
    if (prompt && prompt.parentNode) prompt.parentNode.removeChild(prompt);
    prompt = null;
  }
  function maybeOffer() {
    if (!authed() || getState().active || prompt) return;
    var key = tourHere();
    if (!key || wasOffered(key) || isDone(key)) return;
    var t = TOURS[key];
    var first = key === "overview";

    prompt = document.createElement("div");
    prompt.className = "tstour-welcome";
    prompt.innerHTML =
      '<div class="tstour-welcome-title">' +
        (first ? "New to this report?" : t.label + ", in brief") +
      '</div>' +
      '<div class="tstour-welcome-body">' +
        (first
          ? "A " + t.secs + "-second look around. Every page has a short tour of its own, and you can bring it back any time with Tour this page."
          : "A " + t.secs + "-second tour of what's here and how to use it.") +
      '</div>' +
      '<div class="tstour-welcome-foot">' +
        '<button class="tstour-welcome-later" type="button">Not now</button>' +
        '<button class="tstour-welcome-start tstour-primary" type="button">Show me</button>' +
      '</div>';
    document.body.appendChild(prompt);
    var p = prompt;
    requestAnimationFrame(function () { p.classList.add("tstour-in"); });

    p.querySelector(".tstour-welcome-later").addEventListener("click", function () {
      mark(OFFERED, key); dismissPrompt(); renderChecklist();
    });
    p.querySelector(".tstour-welcome-start").addEventListener("click", function () { startTour(key); });
  }

  // ── Home checklist: [data-ts-tour-checklist] ────────────
  function checklistOff() { try { return !!localStorage.getItem(CL_OFF); } catch (e) { return false; } }
  function renderChecklist() {
    var mount = document.querySelector("[data-ts-tour-checklist]");
    if (!mount) return;
    var done = getMap(DONE);
    var count = 0;
    for (var i = 0; i < ORDER.length; i++) if (done[ORDER[i]]) count++;

    // gone once every area is toured, or once dismissed
    if (checklistOff() || count === ORDER.length) { mount.innerHTML = ""; return; }

    var rows = ORDER.map(function (k) {
      var t = TOURS[k], ok = !!done[k];
      return '<button type="button" class="tstour-cl-row' + (ok ? " is-done" : "") + '" data-tstour-go="' + k + '">' +
          '<span class="tstour-cl-tick" aria-hidden>' + (ok ? "✓" : "") + '</span>' +
          '<span class="tstour-cl-label">' + t.label + '</span>' +
          (ok ? '<span class="tstour-cl-meta">Toured</span>'
              : '<span class="tstour-cl-meta">' + t.secs + "s</span><span class=\"tstour-cl-go\" aria-hidden>▸</span>") +
        '</button>';
    }).join("");

    mount.innerHTML =
      '<div class="tstour-cl">' +
        '<div class="tstour-cl-head">' +
          '<span class="tstour-cl-title">Getting started</span>' +
          '<span class="tstour-cl-count">' + count + " of " + ORDER.length + " areas</span>" +
        '</div>' +
        '<div class="tstour-cl-track"><span class="tstour-cl-fill" style="width:' + Math.round((count / ORDER.length) * 100) + '%"></span></div>' +
        '<div class="tstour-cl-rows">' + rows + '</div>' +
        '<button type="button" class="tstour-cl-dismiss">Dismiss</button>' +
      '</div>';

    mount.querySelector(".tstour-cl-dismiss").addEventListener("click", function () {
      try { localStorage.setItem(CL_OFF, "1"); } catch (e) {}
      mount.innerHTML = "";
    });
  }

  // ── delegated clicks: launchers + checklist rows ─────────────
  document.addEventListener("click", function (e) {
    var t = e.target;
    while (t && t !== document.body) {
      if (t.getAttribute) {
        var go = t.getAttribute("data-tstour-go");
        if (go) { e.preventDefault(); startTour(go); return; }
        var launch = t.getAttribute("data-ts-tour-start");
        if (launch !== null) {
          e.preventDefault();
          // Only treat the value as a tour name if it actually names one. React
          // renders the valueless JSX attribute as "true", and the static shells
          // use a bare attribute (""), so anything unrecognised means "this page".
          if (TOURS[launch]) startTour(launch); else start();
          return;
        }
      }
      t = t.parentNode;
    }
  });

  window.TwentySixTour = { start: start, startTour: startTour, stop: stop, resume: resume, tours: TOURS };

  function init() {
    migrateLegacy();
    // This script is `defer`red, so on the React app it runs before Home mounts.
    // Poll briefly for the checklist mount rather than guessing at a delay.
    renderChecklist();
    if (!document.querySelector("[data-ts-tour-checklist]")) {
      var tries = 0;
      var clTimer = setInterval(function () {
        tries++;
        if (document.querySelector("[data-ts-tour-checklist]")) { clearInterval(clTimer); renderChecklist(); }
        else if (tries > 40) clearInterval(clTimer);
      }, 100);
    }
    if (getState().active) { navigating = false; render(); }
    else setTimeout(maybeOffer, 900);

    // Pages are hash routes, so arriving at one is a hashchange rather than a page load.
    // Without this, only the first page ever offered a tour and an active tour kept pointing
    // at anchors on the page the user had just left.
    var lastPage = currentPage();
    window.addEventListener("hashchange", function () {
      var now = currentPage();
      if (now === lastPage) return;
      lastPage = now;
      if (getState().active) stop();
      dismissPrompt();
      setTimeout(maybeOffer, 650);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
