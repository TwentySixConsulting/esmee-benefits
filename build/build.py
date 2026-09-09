#!/usr/bin/env python3
"""
Build the Esmée Fairbairn benefits report from the Zigbert template.

    python3 build/build.py

Reads  _source/report-template.html   (an unmodified copy of the demo2 Benefits tab)
       _source/data/market.json       (every client and market figure)
Writes _source/report.html            (plaintext; NEVER committed, see .gitignore)

Why a build script rather than hand-editing. The template is 5,949 lines and states each
quartile TWICE, once in the HA_Q object that the charts read and once in the market table
markup that the reader sees. Editing by hand guarantees those two drift apart, and the
report then contradicts itself on screen. Generating both from one JSON file makes that
impossible, and makes the next client a data change rather than a fortnight of find and
replace.
"""

import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "_source"
TEMPLATE = SRC / "report-template.html"
DATA = SRC / "data" / "market.json"
OUT = SRC / "report.html"

CLIENT = "Esmée Fairbairn Foundation"
CLIENT_SHORT = "Esmée Fairbairn"
FLAG = "Esmée"  # the position-bar marker; must be short or it overflows the track

CATEGORIES = [
    ("core", "Core Benefits", "shield", "Traditional Core Benefits"),
    ("working-time", "Working Time", "clock", "Working Time &amp; Time Off Arrangements"),
    ("health", "Health &amp; Wellbeing", "heart", "Health &amp; Well-Being"),
    ("financial", "Financial Support", "wallet", "Financial Support"),
    ("esg", "ESG &amp; DEI", "leaf", "Environmental, Social &amp; Governance / Diversity, Equity &amp; Inclusion"),
    ("learning", "Learning &amp; Development", "grad", "Learning &amp; Personal Development"),
]
CAT_ICON_PATH = {
    "core": "M12 3l7 3v6c0 4-3 6.5-7 9-4-2.5-7-5-7-9V6z",
    "working-time": "M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z",
    "health": "M12 20s-7-4.3-7-9a4 4 0 017-2 4 4 0 017 2c0 4.7-7 9-7 9z",
    "financial": "M3 7h16a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z M3 7l0-1a2 2 0 012-2h11 M17 13h.01",
    "esg": "M5 21c0-9 5-14 14-14 0 9-5 14-14 14z M5 21c3-6 7-9 11-10",
    "learning": "M22 10L12 5 2 10l10 5 10-5z M6 12v4c0 1 3 3 6 3s6-2 6-3v-4",
}
BADGE_CLASS = {"above": "above", "at": "green", "watch": "amber", "below": "below"}
BADGE_WORD = {"above": "Above market", "at": "At market", "watch": "Worth a look", "below": "Below market"}

# The report's own section-level commentary. Written per category from the evidence in
# _source/data/, not inherited from the template, which was written for a technology client.
SECTOR_NOTE = {
    "core": "Foundations lead the wider third sector clearly on pension and hold a similar line on "
            "leave. The ONS puts the average voluntary-sector employer contribution at 5.8%, while a "
            "third of foundations contribute 10% or more. On leave the pattern reverses. Charities "
            "start at a similar 25 days but build in far more service accrual, with large charities reaching "
            "30 days after seven years and one adding five paid wellbeing days on top.",
    "working-time": "Flexible and hybrid working is close to universal in both groups, so neither is a "
            "differentiator any longer. What separates employers is how the policy is written, and "
            "whether it names the options rather than leaving each request to be weighed case by case.",
    "health": "Foundations are more likely than charities to fund private medical cover, but only a "
            "third of larger foundations do. Charities more often fund a health cash plan instead, "
            "which costs a fraction as much per head and reaches everyone. Life assurance multiples "
            "run higher in the wider sector, at 4 times salary in several published schemes.",
    "financial": "Season ticket loans and cycle schemes are the two financial benefits that larger "
            "foundations genuinely provide at scale, at 72% and 56%. Beyond those, provision thins "
            "quickly, with only 22% running any staff discount scheme.",
    "esg": "Payroll giving and volunteering leave are the two areas where a grant-maker's own values "
            "are most visible in its employment package. Neither is counted by ACF, and both are more "
            "established in the wider third sector than among foundations.",
    "learning": "Development budgets are where the foundation market is widest. There is no counted "
            "benchmark, and published figures range from nothing named at all to £2,000 a year with "
            "six paid development days.",
}

CALLOUT = {
    "core": ["A Christmas closure period, which several foundations use to add days without moving the "
             "headline entitlement. Esmée already does this.",
             "Service-based leave accrual, standard across the wider third sector and absent from most "
             "foundation schemes, including Esmée's.",
             "A four day week, reported by one ACF respondent in the 6 to 29 employee band."],
    "working-time": ["Paid wellbeing time and a wellbeing allowance, described by foundations in the "
             "largest size band. One lets staff claim back half the cost of wellbeing activities.",
             "A climate perks policy, giving additional leave for travelling by rail rather than flying.",
             "Birthday leave, and an unpaid sabbatical of two to six months after five years."],
    "health": ["Health cash plans giving every employee base cover "
             "for dental, optical and physiotherapy costs at a fraction of the cost of private medical.",
             "A private GP service and personal health reviews, offered alongside rather than "
             "instead of an employee assistance programme.",
             "Free eye tests for display screen users, cheap and named on several foundation careers pages."],
    "financial": ["Low-cost employee loans and savings accounts, offered alongside the season ticket "
             "loan rather than on their own.",
             "Electric vehicle salary sacrifice, now appearing in ACF free-text answers across all three "
             "size bands.",
             "A contribution towards removal expenses for new staff, reported by one foundation at up to "
             "15% of initial salary."],
    "esg": ["An employer match on payroll giving, which is what separates Esmée's scheme from a plain "
             "Give As You Earn arrangement.",
             "Ethical or ESG pension fund options, an obvious fit for a foundation whose endowment is "
             "already screened.",
             "Paid volunteering days, offered by 39% of larger foundations and by comparable funders "
             "at two days a year."],
    "learning": ["Paid development days as well as a budget. One foundation offers up to six a year, "
             "which removes the time barrier that a cash allowance alone does not.",
             "Reimbursement of professional subscriptions, named separately from the development budget "
             "by several foundations.",
             "Study leave for funded qualifications, more common in larger charities than in foundations."],
}


# Appended to the report's last <style> block, so it wins over the template without editing
# 2,200 lines of inherited CSS in place.
STYLE_FIXES = """
/* ── Quartile graphics: one language across the whole report ──────────────────
   The Overview and market pages drew position on a smooth cream-to-slate blend, while
   Your Benefits used a hard-stepped three-band bar. Two graphics for one idea, and the
   smooth one reads as decorative rather than as three quartiles. The stepped bar is the
   correct one: the bands ARE the quartiles, so a marker's band tells you the answer
   without reading the axis. This makes the Overview match. */
.bx-posbar-band {
  background: linear-gradient(90deg,
    #e8e7e3 0%, #d4d3cf 33.33%,
    #d4b860 33.33%, #C9785A 66.66%,
    #2c3a8c 66.66%, #1a1a2e 100%) !important;
}
/* Quartile value cards, matched to .rb-q-cell on Your Benefits. */
.bx-qcell { background: var(--bg-app); border-color: var(--line); }
.bx-qcell::before { height: 2px; border-radius: 8px 8px 0 0; }
.bx-qcell-lq::before  { background: #b8b7b3; }
.bx-qcell-med::before { background: var(--gold); }
.bx-qcell-uq::before  { background: var(--navy); }
.bx-qcell-med { box-shadow: 0 0 0 1px rgba(201,120,90,0.3); }
.bx-qlbl { color: var(--text-soft); }
.bx-qcell-med .bx-qlbl { color: var(--gold-deep); }
.bx-qcell-uq  .bx-qlbl { color: var(--navy); }
.bx-qval { color: var(--text); }

/* ── Compare the market: this is data, so it reads at full contrast ────────── */
.bx-sec-name { color: var(--text); font-weight: 600; }
.bx-sec-val  { color: var(--text); }
.bx-mt-sub   { color: var(--text-soft); }

/* ── "What this page is" panels ───────────────────────────────────────────── */
.efb-intro {
  background: linear-gradient(180deg, #ffffff 0%, var(--bg-app) 100%);
  border: 1px solid var(--line); border-left: 3px solid var(--gold);
  border-radius: var(--radius-lg); padding: 22px 26px; margin: 0 0 20px;
}
.efb-intro-eyebrow {
  font-size: 9.5px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--gold-deep); margin-bottom: 8px;
}
.efb-intro h2 {
  font-family: var(--font-serif); font-size: 20px; font-weight: 600; color: var(--text);
  margin: 0 0 10px; line-height: 1.25;
}
.efb-intro p { font-size: 13.5px; color: var(--text-mid); line-height: 1.65; margin: 0 0 10px; }
.efb-intro p:last-child { margin-bottom: 0; }
.efb-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 16px; }
@media (max-width: 800px) { .efb-steps { grid-template-columns: 1fr; } }
.efb-step {
  background: #fff; border: 1px solid var(--line); border-radius: var(--radius);
  padding: 13px 15px;
}
.efb-step-n {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 999px;
  background: var(--gold); color: #fff; font-size: 11px; font-weight: 700; margin-bottom: 7px;
}
.efb-step-h { font-size: 12.5px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
.efb-step-b { font-size: 12px; color: var(--text-mid); line-height: 1.5; }
.efb-key { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 16px; }
.efb-key-item { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text-mid); }
.efb-key-swatch { width: 22px; height: 8px; border-radius: 999px; flex: 0 0 auto; }


/* ── "What we did", collapsed on the Overview ─────────────────────────────── */
.efb-meth { margin-top: 16px; }
.efb-meth summary {
  cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; font-weight: 700; color: var(--gold-deep);
  background: var(--pink-wash); border: 1px solid var(--pink-soft);
  border-radius: 999px; padding: 7px 15px;
}
.efb-meth summary::-webkit-details-marker { display: none; }
.efb-meth summary::before { content: "＋"; font-weight: 700; }
.efb-meth[open] summary::before { content: "－"; }
.efb-meth[open] summary { margin-bottom: 12px; }
.efb-meth-body { background: #fff; border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; }
.efb-meth-intro, .efb-meth-also { font-size: 13px !important; color: var(--text) !important; margin: 0 0 12px; }
.efb-meth-also { margin: 12px 0 0; padding-top: 12px; border-top: 1px solid var(--line-soft); color: var(--text-mid) !important; }
.efb-meth-item { display: flex; gap: 12px; padding: 10px 0; border-top: 1px solid var(--line-soft); }
.efb-meth-item:first-of-type { border-top: 0; padding-top: 0; }
.efb-meth-n {
  flex: 0 0 auto; width: 22px; height: 22px; border-radius: 999px; background: var(--gold); color: #fff;
  font-size: 11.5px; font-weight: 700; display: flex; align-items: center; justify-content: center;
}
.efb-meth-h { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
.efb-meth-item p { font-size: 12.5px !important; color: var(--text) !important; line-height: 1.6; margin: 0; }
.efb-meth-item ul { margin: 7px 0 0; padding-left: 18px; }
.efb-meth-item li { font-size: 12.5px; color: var(--text-mid); line-height: 1.65; }

/* ── Our read of the position, opening Your Benefits ─────────────────────── */
.efb-pos {
  background: var(--cream); border: 1px solid var(--line); border-left: 3px solid var(--slate);
  border-radius: var(--radius-lg); padding: 22px 26px; margin: 0 0 20px; box-shadow: var(--shadow-sm);
}
.efb-pos-eyebrow {
  font-size: 9.5px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--slate-deep); margin-bottom: 8px;
}
.efb-pos-title {
  font-family: var(--font-serif); font-size: 20px; font-weight: 600; color: var(--text);
  margin: 0 0 12px; line-height: 1.25;
}
.efb-pos p { font-size: 14px; color: var(--text); line-height: 1.7; margin: 0 0 11px; }
.efb-pos p:last-child { margin-bottom: 0; }

/* ── Smaller items, and the themes ───────────────────────────────────────── */

.efb-aon { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 4px 0 18px; }
@media (max-width: 820px) { .efb-aon { grid-template-columns: 1fr; } }
.efb-aon-col { background: var(--slate-soft); border: 1px solid rgba(107,122,153,0.22); border-radius: var(--radius); padding: 15px 18px; }
.efb-aon-h { font-size: 12.5px; font-weight: 700; color: var(--slate-deep); margin-bottom: 8px; }
.efb-aon-col ol { margin: 0; padding-left: 19px; }
.efb-aon-col li { font-size: 13px; color: var(--text); line-height: 1.65; margin-bottom: 4px; }
.efb-th-striking {
  font-size: 13.5px; color: var(--text); line-height: 1.7; margin: 0 0 18px;
  padding-left: 14px; border-left: 3px solid var(--gold);
}
.efb-th-hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; margin-bottom: 12px; }
.efb-th-all {
  flex: 0 0 auto; border: 1px solid var(--line); background: #fff; border-radius: 8px;
  font-family: inherit; font-size: 12px; font-weight: 600; color: var(--text-mid);
  padding: 7px 13px; cursor: pointer;
}
.efb-th-all:hover { color: var(--gold-deep); border-color: var(--pink-soft); }
.efb-th-stack {
  border: 1px solid var(--line); border-radius: var(--radius-lg); overflow: hidden;
  background: #fff; position: relative;
}
.efb-th { border-top: 1px solid var(--line-soft); }
.efb-th:first-of-type { border-top: 0; }
.efb-th > summary {
  cursor: pointer; list-style: none; display: flex; align-items: flex-start; gap: 11px;
  padding: 14px 18px;
}
.efb-th > summary::-webkit-details-marker { display: none; }
.efb-th > summary:hover { background: var(--bg-app); }
.efb-th-chev { flex: 0 0 auto; color: var(--gold); margin-top: 1px; transition: transform .15s ease; }
.efb-th-chev svg { width: 15px; height: 15px; display: block; }
.efb-th[open] > summary { background: var(--bg-app); }
.efb-th[open] .efb-th-chev { transform: rotate(90deg); }
.efb-th-txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.efb-th-h { font-family: var(--font-serif); font-size: 14.5px; font-weight: 600; color: var(--text); }
.efb-th-sum { font-size: 12.5px; color: var(--text-mid); line-height: 1.5; }
.efb-th-body { padding: 2px 18px 18px 68px; }
.efb-th-body p { font-size: 13px; color: var(--text); line-height: 1.7; margin: 0 0 9px; }
.efb-th-body p:last-child { margin-bottom: 0; }
.efb-th-body ul { margin: 0 0 9px; padding-left: 19px; }
.efb-th-body li { font-size: 13px; color: var(--text); line-height: 1.65; margin-bottom: 5px; }
@media (max-width: 700px) { .efb-th-body { padding-left: 18px; } }
/* Printing must not hide content behind a closed summary. */
@media print { .efb-th-body { display: block !important; } .efb-th-hd .efb-th-all { display: none; } }

/* ── Example packages, and the wellbeing strategy ────────────────────────── */

.efb-wb { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.efb-wb-item { background: var(--bg-app); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px; }
.efb-wb-h { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.efb-wb-item p { font-size: 12.5px; color: var(--text); line-height: 1.6; margin: 0; }

/* ── "You might also consider": the benefit, then the reasoning ──────────── */
.efb-toc { margin: 12px 0 0; padding-left: 20px; }
.efb-toc li { font-size: 13px; color: var(--text-mid); line-height: 1.6; margin-bottom: 5px; }
.efb-toc b { color: var(--text); }
.efb-th-n {
  flex: 0 0 auto; width: 21px; height: 21px; border-radius: 999px; margin-top: 1px;
  background: var(--slate-soft); color: var(--slate-deep);
  font-family: var(--font-sans); font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.efb-th[open] .efb-th-n { background: var(--gold); color: #fff; }
.efb-cn-count {
  float: right; font-family: var(--font-sans); font-size: 9.5px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-soft);
}
.efb-cn-group { margin-bottom: 20px; }
.efb-cn-gh {
  font-size: 10.5px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--gold-deep); padding-bottom: 7px; margin-bottom: 4px;
  border-bottom: 1px solid var(--line);
}
.efb-cn-row {
  display: grid; grid-template-columns: 260px 1fr; gap: 18px;
  padding: 12px 0; border-top: 1px solid var(--line-soft);
}
.efb-cn-row:first-of-type { border-top: 0; }
@media (max-width: 860px) { .efb-cn-row { grid-template-columns: 1fr; gap: 4px; } }
.efb-cn-b {
  font-family: var(--font-serif); font-size: 14px; font-weight: 600; color: var(--text);
  line-height: 1.4;
  /* Column, not inline: trailing the tag after the text left it hanging off the end of a
     wrapped name on some rows and sitting neatly under others. */
  display: flex; flex-direction: column; align-items: flex-start; gap: 5px;
}
.efb-cn-r { font-size: 13px; color: var(--text); line-height: 1.65; }
.efb-cn-tag, .efb-cn-have {
  display: inline-block;
  font-family: var(--font-sans); font-size: 9.5px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase;
  border-radius: 999px; padding: 3px 8px; white-space: nowrap;
}
.efb-cn-tag { background: var(--pink-wash); color: var(--gold-deep); border: 1px solid var(--pink-soft); }
.efb-cn-have { background: var(--sage-wash); color: var(--sage-deep); border: 1px solid var(--sage-soft); }
.efb-cn-row--have .efb-cn-b, .efb-cn-row--have .efb-cn-r { color: var(--text-mid); }

.bx-yp-cur {
  font-size: 12.5px; color: var(--text); line-height: 1.55;
  margin: 2px 0 8px; padding: 7px 10px;
  background: var(--bg-app); border-left: 2px solid var(--gold); border-radius: 0 6px 6px 0;
}
.bx-yp-cur b { color: var(--text); font-weight: 700; }

/* ── "Where you sit": clearer separation and a firmer benefit name ────────── */
.bx-market-top .bx-yp { padding: 15px 0 14px; }
.bx-market-top .bx-yp:first-of-type { padding-top: 6px; }
.bx-market-top .bx-yp:last-of-type { padding-bottom: 2px; }
.bx-market-top .bx-yp-top { margin-bottom: 7px; }
.bx-market-top .bx-yp-name {
  font-family: var(--font-serif); font-size: 14px; font-weight: 700; color: var(--text);
  letter-spacing: -0.005em;
}

/* ── Section export: PNG and Word ──────────────────────────────────── */
.efb-xp {
  position: absolute; top: 12px; right: 14px; z-index: 5;
  display: flex; gap: 4px;
  opacity: 0; transition: opacity .14s ease;
}
/* Reserve the corner so a heading never runs underneath the control. Permanent, not
   hover-only, or the text would reflow the moment the control appeared. */
[data-export] > h2,
[data-export] .bx-verdict,
[data-export] .efb-pos-title,
[data-export] .yb-overview-title,
[data-export] .bx-mt-h,
[data-export] > .efb-tr-sec:first-child { padding-right: 124px; }
/* Grid and stack containers have no padding of their own, so there is no corner to sit in.
   Float the control just above the top edge instead; each of these follows a short intro
   line, so there is nothing there to collide with. */
.efb-xp-out { margin-top: 34px; }
.efb-xp-out > .efb-xp { top: -30px; right: 0; }
[data-export]:hover > .efb-xp,
[data-export]:focus-within > .efb-xp { opacity: 1; }
/* Touch and keyboard users never hover, so never reveal it. */
@media (hover: none) { .efb-xp { opacity: 1; } }
.efb-xp-b {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--font-sans); font-size: 11px; font-weight: 600; color: var(--text-mid);
  background: rgba(255,255,255,0.94); border: 1px solid var(--line);
  border-radius: 7px; padding: 5px 9px; cursor: pointer;
  box-shadow: 0 1px 3px rgba(18,28,43,0.08); backdrop-filter: blur(3px);
}
.efb-xp-b:hover { color: var(--gold-deep); border-color: var(--pink-soft); background: #fff; }
.efb-xp-b:disabled { opacity: .55; cursor: progress; }
.efb-xp-b svg { width: 13px; height: 13px; flex: 0 0 auto; }
/* On a narrow screen the three labels crowd the heading they sit beside. */
@media (max-width: 700px) { .efb-xp-b span { display: none; } .efb-xp-b { padding: 6px; } }

@media print { .efb-xp { display: none !important; } }

/* ── Per-page help, at the foot of every page ─────────────────────────────── */
.efb-help { margin: 26px 0 8px; border-top: 1px solid var(--line-soft); padding-top: 18px; }
.efb-help summary {
  cursor: pointer; list-style: none; display: inline-flex; align-items: center; gap: 8px;
  font-size: 12.5px; font-weight: 600; color: var(--slate-deep);
  background: var(--slate-soft); border: 1px solid rgba(107,122,153,0.22);
  border-radius: 999px; padding: 7px 14px;
}
.efb-help summary::-webkit-details-marker { display: none; }
.efb-help summary:hover { background: #dde3ee; }
.efb-help[open] summary { margin-bottom: 12px; }
.efb-help-body {
  background: var(--bg-app); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 16px 18px;
}
.efb-help-body ul { margin: 0; padding-left: 18px; }
.efb-help-body li { font-size: 12.5px; color: var(--text-mid); line-height: 1.6; margin-bottom: 7px; }
.efb-help-body li:last-child { margin-bottom: 0; }
.efb-help-body b { color: var(--text); }
.efb-help-tour {
  margin-top: 12px; border: 0; background: var(--gold); color: #fff;
  font-family: inherit; font-size: 12px; font-weight: 600;
  border-radius: 8px; padding: 8px 14px; cursor: pointer;
}
.efb-help-tour:hover { background: var(--gold-deep); }
@media print { .efb-help { display: none !important; } }

/* ── Start here: read at full contrast ────────────────────────────────────── */
.efb-intro p { font-size: 14.5px; color: var(--text); }
.efb-intro .efb-step-b { font-size: 13px; color: var(--text); }
.efb-intro-note { font-size: 13.5px !important; color: var(--text) !important; }

/* ── Trends ──────────────────────────────────────────────────────────────── */
.efb-tr-sec {
  font-family: var(--font-serif); font-size: 17px; font-weight: 600; color: var(--text);
  margin: 30px 0 4px;
}
.efb-tr-sec-sub { font-size: 13px; color: var(--text-mid); line-height: 1.6; margin: 0 0 16px; max-width: 78ch; }


/* Condensed list on the Action Plan, which is the page people download. */
.efb-ap-consider { margin-top: 30px; padding-top: 22px; border-top: 1px solid var(--line); }
.efb-ap-row { border-top: 1px solid var(--line-soft); padding: 12px 0; }
.efb-ap-row:first-of-type { border-top: 0; }
.efb-ap-name { font-family: var(--font-serif); font-size: 14px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 10px; }
.efb-ap-name .efb-tr-eff { margin-left: 0; }
.efb-ap-market { font-size: 11.5px; font-weight: 600; color: var(--gold-deep); margin: 3px 0 4px; }
.efb-ap-why { font-size: 12.5px; color: var(--text); line-height: 1.6; }
"""


EXPORT_SCRIPT = """
<script>
/* Section export: pop out, PNG, Word.
   One control, attached to every block carrying data-export="slug|Title". Blocks the build
   generates are tagged in the markup; blocks the template owns, and the two market cards the
   template injects at runtime, are tagged from the AUTO list below. */
(function () {
  /* sel: what to find. spec: slug|Title. up: climb to this ancestor, because some ids sit
     on a heading rather than on the block it belongs to. out: the block is a grid or flex
     container with no padding of its own, so the control floats above its top edge instead
     of inside a corner that does not exist. */
  var AUTO = [
    { sel: '[data-page="overview"] .efb-intro',    spec: 'what-this-report-is|What this report is' },
    { sel: '#bx-verdict',   spec: 'headline-position|Headline position', up: '.bx-card' },
    { sel: '#bx-scorecard', spec: 'category-scorecard|Category scorecard', out: true },
    { sel: '[data-page="provision"] .yb-overview', spec: 'benefits-summary|Your benefits in summary' },
    { sel: '#bx-plan-summary', spec: 'plan-summary|Action plan summary', out: true },
    { sel: '#bx-plan',         spec: 'plan-priorities|Your priorities',  out: true },
  ];

  function tag(el, spec, out) {
    if (!el || el.getAttribute('data-export')) return;
    el.setAttribute('data-export', spec);
    if (out) el.classList.add('efb-xp-out');
  }
  function tagAuto(root) {
    AUTO.forEach(function (a) {
      (root || document).querySelectorAll(a.sel).forEach(function (el) {
        var target = a.up ? (el.closest(a.up) || el.parentElement) : el;
        tag(target, a.spec, a.out);
      });
    });
    // The two market cards are built by the template after load, so they cannot be tagged in
    // the source. Name them from the heading they already carry.
    document.querySelectorAll('.bx-market-top > .bx-card').forEach(function (card, i) {
      var h = card.querySelector('.bx-mt-h');
      if (!h) return;
      var page = card.closest('.page');
      var slug = (page ? page.dataset.page : 'section') + '-' + (i === 0 ? 'where-you-sit' : 'compare-market');
      tag(card, slug + '|' + h.textContent.trim());
    });
  }

  var ICON = {
    png:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>',
    doc:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>',
    doc2: ''
  };

  function fileStem(slug) { return 'esmee-fairbairn-' + slug; }

  /* A copy of the block with the furniture taken out: the export control itself, any other
     buttons, and the SVG icons, which Word renders as empty boxes. */
  function cleanClone(node) {
    var c = node.cloneNode(true);
    c.querySelectorAll('.efb-xp, .no-print, button, .rb-png-btn, .exp-toolbar').forEach(function (e) { e.remove(); });
    return c;
  }

  function toPng(node, slug, done) {
    if (!window.htmlToImage) { done('Image library unavailable'); return; }
    var hide = node.querySelector('.efb-xp');
    if (hide) hide.style.visibility = 'hidden';
    window.htmlToImage.toPng(node, { backgroundColor: '#FFFFFF', pixelRatio: 2 })
      .then(function (url) {
        var a = document.createElement('a');
        a.href = url; a.download = fileStem(slug) + '.png';
        document.body.appendChild(a); a.click(); a.remove();
        done();
      })
      .catch(function (e) { console.error(e); done('Could not create the image'); })
      .finally(function () { if (hide) hide.style.visibility = ''; });
  }

  /* Word opens an HTML document with the Office namespaces declared, so a .doc can be built
     here with no library. Styles have to be inline-ish and simple: Word ignores most modern
     CSS, so this restates the few things that carry meaning. */
  function toWord(node, slug, title, done) {
    try {
      var body = cleanClone(node).innerHTML;
      var css = 'body{font-family:Calibri,"Segoe UI",sans-serif;font-size:11pt;color:#121C2B;line-height:1.5}'
        + 'h1,h2,h3,h4{font-family:Calibri,sans-serif;color:#121C2B;margin:14pt 0 6pt}'
        + 'h1{font-size:18pt}h2{font-size:15pt}h3{font-size:13pt}h4{font-size:11.5pt}'
        + 'table{border-collapse:collapse;width:100%}td,th{border:0.5pt solid #DEE1E6;padding:5pt 7pt;'
        + 'font-size:10pt;vertical-align:top;text-align:left}th{background:#EEF1F6;font-weight:bold}'
        + 'ul,ol{margin:6pt 0 6pt 18pt}li{margin-bottom:3pt}'
        + '.efb-cn-b,.bx-sec-name,.rb-q-lbl,.bx-qlbl{font-weight:bold}'
        + '.efb-cn-row,.bx-sec-row{margin-bottom:8pt}'
        + 'svg,img{display:none}'
        + '.hdr{border-bottom:1pt solid #C9785A;padding-bottom:6pt;margin-bottom:12pt}'
        + '.hdr .b{font-size:8.5pt;letter-spacing:1pt;text-transform:uppercase;color:#7285A5}';
      var head = '<html xmlns:o="urn:schemas-microsoft-com:office:office" '
        + 'xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">'
        + '<head><meta charset="utf-8"><title>' + title + '</title>'
        + '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->'
        + '<style>' + css + '</style></head><body>';
      var hdr = '<div class="hdr"><div class="b">TwentySix &middot; Esm&eacute;e Fairbairn Foundation '
        + '&middot; Benefits Benchmark</div><h1>' + title + '</h1></div>';
      var blob = new Blob(['﻿', head + hdr + body + '</body></html>'],
                          { type: 'application/msword' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = fileStem(slug) + '.doc';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      done();
    } catch (e) { console.error(e); done('Could not create the document'); }
  }

  function run(btn, act, node, slug, title) {
    var label = btn.querySelector('span');
    var orig = label ? label.textContent : '';
    btn.disabled = true;
    if (label) label.textContent = 'Working';
    var finish = function (err) {
      btn.disabled = false;
      if (label) label.textContent = err ? 'Failed' : orig;
      if (err) { console.error(err); setTimeout(function () { if (label) label.textContent = orig; }, 2500); }
    };
    if (act === 'png') toPng(node, slug, finish);
    else toWord(node, slug, title, finish);
  }

  function attach(el) {
    if (el.querySelector(':scope > .efb-xp')) return;
    var spec = (el.getAttribute('data-export') || '').split('|');
    var slug = spec[0] || 'section';
    var title = spec[1] || 'Section';
    var bar = document.createElement('div');
    bar.className = 'efb-xp no-print';
    bar.innerHTML =
      '<button type="button" class="efb-xp-b" data-act="png" title="Download as PNG">' + ICON.png + '<span>PNG</span></button>'
      + '<button type="button" class="efb-xp-b" data-act="word" title="Download for Word">' + ICON.doc + '<span>Word</span></button>';
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]');
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      run(b, b.dataset.act, el, slug, title);
    });
    if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
    el.appendChild(bar);
    if (!el.classList.contains('efb-xp-out')) avoidCollision(el, bar);
  }

  /* Some corners are already taken: the headline card has a status chip there. Rather than
     keep a list of exceptions, measure once and move the control above the block if
     something is genuinely under it.

     Measure TEXT rects, not element boxes. A block-level eyebrow or heading spans the full
     width even when its words stop well short of the corner, so element boxes report a
     collision for almost everything and the control ends up floating above blocks that had
     room for it. Range.getClientRects gives the glyph boxes. */
  function avoidCollision(el, bar) {
    var prev = bar.style.opacity;
    bar.style.opacity = '1';
    var br = bar.getBoundingClientRect();
    var clash = false;
    if (br.width) {
      var walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      var n, rg = document.createRange();
      while (!clash && (n = walk.nextNode())) {
        if (!n.nodeValue.trim() || bar.contains(n)) continue;
        rg.selectNodeContents(n);
        var rects = rg.getClientRects();
        for (var i = 0; i < rects.length; i++) {
          var r = rects[i];
          if (!(r.right < br.left + 1 || r.left > br.right - 1 ||
                r.bottom < br.top + 1 || r.top > br.bottom - 1)) { clash = true; break; }
        }
      }
    }
    bar.style.opacity = prev;
    if (clash) el.classList.add('efb-xp-out');
  }

  function sweep() {
    tagAuto();
    document.querySelectorAll('[data-export]').forEach(attach);
  }

  // Expand all / Collapse all for the themes accordion.
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.efb-th-all');
    if (!b) return;
    var open = b.dataset.all === 'open';
    var stack = b.closest('.efb-th-hd').nextElementSibling;
    if (!stack) return;
    stack.querySelectorAll('details.efb-th').forEach(function (d) { d.open = open; });
    b.dataset.all = open ? 'close' : 'open';
    b.textContent = open ? 'Collapse all' : 'Expand all';
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sweep);
  else sweep();
  // The market cards are injected when a category page is first opened, so re-sweep on
  // navigation rather than assuming everything exists at load.
  window.addEventListener('hashchange', function () { setTimeout(sweep, 350); });
  setTimeout(sweep, 1200);
})();
</script>
"""


def esc(s):
    return html.escape(s, quote=False)


def icon_svg(cat, size=18, sw="1.6"):
    segs = CAT_ICON_PATH[cat].split(" M")
    paths = "".join(
        f'<path stroke-linecap="round" stroke-linejoin="round" d="{("M" + s) if i else s}"/>'
        for i, s in enumerate(segs)
    )
    return (f'<svg width="{size}" height="{size}" fill="none" viewBox="0 0 24 24" '
            f'stroke-width="{sw}" stroke="currentColor">{paths}</svg>')


def load():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data["_meta"], data["benefits"], data["trends"], data["narrative"]


# ────────────────────────────────────────────────────────────── markup generators

def gen_market_rows(benefits, cat):
    """The visible quartile table for one category page."""
    out = []
    for slug, b in benefits.items():
        if b["category"] != cat or b.get("noMarket"):
            continue
        out.append(f'''          <tr class="brow haq-row" data-slug="{slug}">
            <td class="haq-name">
              <button class="exp-toggle" aria-expanded="false" aria-label="Expand">
                <svg viewBox="0 0 24 24" fill="none" stroke-width="2.4" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5"/></svg>
              </button>
              <span class="haq-name-text">{b["label"]}</span>
            </td>
            <td class="haq-cell haq-cell-lq"><span class="haq-val">{esc(b["lq"])}</span></td>
            <td class="haq-cell haq-cell-med"><span class="haq-val">{esc(b["m"])}</span></td>
            <td class="haq-cell haq-cell-uq"><span class="haq-val">{esc(b["uq"])}</span></td>
          </tr>
          <tr class="brow-detail" data-slug-detail="{slug}" hidden>
            <td colspan="4">
              <div class="quartile-detail">
                <div class="qd-panels">
                  <div class="qd-panel qd-panel-lq">
                    <div class="qd-panel-head">Lower Quartile</div>
                    <div class="qd-panel-value">{esc(b["lq"])}</div>
                    <div class="qd-panel-body"><ul class="qd-panel-points"><li>{b["lqDetail"]}</li></ul></div>
                  </div>
                  <div class="qd-panel qd-panel-med">
                    <div class="qd-panel-head">Median <span class="qd-star">&#9733;</span></div>
                    <div class="qd-panel-value">{esc(b["m"])}</div>
                    <div class="qd-panel-body"><ul class="qd-panel-points"><li>{b["mDetail"]}</li></ul></div>
                  </div>
                  <div class="qd-panel qd-panel-uq">
                    <div class="qd-panel-head">Upper Quartile</div>
                    <div class="qd-panel-value">{esc(b["uq"])}</div>
                    <div class="qd-panel-body"><ul class="qd-panel-points"><li>{b["uqDetail"]}</li></ul></div>
                  </div>
                </div>
              </div>
            </td>
          </tr>''')
    return "\n".join(out)


def gen_rb_panels(benefits):
    """One provision card per benefit the client actually holds."""
    out = []
    for slug, b in benefits.items():
        e = b.get("esmee")
        if not e:
            continue
        cat = b["category"]
        badge = BADGE_CLASS[e["badge"]]
        badge_txt = f'{BADGE_WORD[e["badge"]]} &middot; {esc(e["current"])}'
        if b.get("noMarket"):
            market_col = ('<div class="rb-col-head"><span class="rb-dot rb-dot-ha"></span>'
                          'Grant-making foundations <span class="rb-col-star">&#9733;</span> Primary Comparator</div>'
                          '<div class="rb-penge-body">No market comparator. This is universal good practice '
                          'rather than a benchmarked benefit, so it is reported without a position.</div>')
            pos_line = (f'<span>{CLIENT_SHORT} provides <strong>{esc(e["current"])}</strong>. '
                        f'Reported for completeness; not benchmarked.</span>')
        else:
            market_col = f'''<div class="rb-col-head"><span class="rb-dot rb-dot-ha"></span>Grant-making foundations <span class="rb-col-star">&#9733;</span> Primary Comparator</div>
              <div class="rb-pos-bar">
                <div class="rb-pos-track"></div>
                <div class="rb-pos-tick" style="left:0%"></div>
                <div class="rb-pos-tick" style="left:50%"></div>
                <div class="rb-pos-tick" style="left:100%"></div>
                <div class="rb-pos-lbl rb-pos-lbl-lq">LQ</div>
                <div class="rb-pos-lbl rb-pos-lbl-med">Median</div>
                <div class="rb-pos-lbl rb-pos-lbl-uq">UQ</div>
                <div class="rb-pos-penge" style="left:{e["posIdx"]}%"><span class="rb-pos-penge-flag">{FLAG}</span></div>
              </div>
              <div class="rb-q-cards">
                <div class="rb-q-cell rb-q-cell-lq"><div class="rb-q-lbl">Lower Quartile</div><div class="rb-q-val">{esc(b["lq"])}</div></div>
                <div class="rb-q-cell rb-q-cell-med"><div class="rb-q-lbl">Median <span class="qcard-star">&#9733;</span></div><div class="rb-q-val">{esc(b["m"])}</div></div>
                <div class="rb-q-cell rb-q-cell-uq"><div class="rb-q-lbl">Upper Quartile</div><div class="rb-q-val">{esc(b["uq"])}</div></div>
              </div>'''
            where = {"above": "sits above the foundation upper quartile",
                     "at": "sits at the foundation median",
                     "watch": "sits below the foundation median and is worth a look",
                     "below": "sits below the foundation lower quartile"}[e["badge"]]
            pos_line = (f'<span>{CLIENT_SHORT} provides <strong>{esc(e["current"])}</strong>, {where}</span>')

        out.append(f'''      <div class="rb-panel" data-badge="{badge}" data-slug="{slug}" id="rb-panel-{slug}">
        <div class="rb-header">
          <div class="rb-header-icon">{icon_svg(cat, 24)}</div>
          <div class="rb-header-text">
            <div class="rb-eyebrow">{CLIENT_SHORT}&apos;s provision</div>
            <h3 class="rb-title">{b["label"]}</h3>
          </div>
          <div class="rb-badge rb-badge-{badge}">{badge_txt}</div>
          <button class="rb-png-btn" type="button" data-png-target="rb-panel-{slug}" aria-label="Download as PNG">
            <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16"/></svg>
            <span>PNG</span>
          </button>
        </div>
        <div class="rb-penge-pos"><span class="rb-penge-pos-dot"></span>{pos_line}</div>
        <div class="rb-grid">
          <div class="rb-col rb-col-penge">
            <div class="rb-col-head"><span class="rb-dot rb-dot-penge"></span>{CLIENT_SHORT}</div>
            <div class="rb-penge-val">{esc(e["current"])}</div>
          </div>
          <div class="rb-col rb-col-ha">
            {market_col}
          </div>
        </div>
      </div>''')
    return "\n\n".join(out)


def gen_sector_footer(cat):
    return f'''<div class="sector-footer">
              <div class="sector-footer-card sector-footer-sp">
                <div class="sector-footer-head"><span class="sector-footer-dot"></span>Wider third sector, typical practice</div>
                <p>{SECTOR_NOTE[cat]}</p>
              </div>
            </div>'''


def gen_callout(cat):
    items = "\n".join(f"        <li>{i}</li>" for i in CALLOUT[cat])
    return f'''<div class="callout">
      <div class="callout-hd"><svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18"/></svg><h4>Less Common Benefits &amp; Ideas Worth Noting</h4></div>
      <ul>
{items}
      </ul>
    </div>'''


def gen_overview(by_badge, counts):
    """The 'where you stand today' narrative, written from the badges rather than by hand."""
    strengths = "\n".join(
        f"            <li><strong>{lbl}</strong>, {cur}.</li>" for lbl, cur in by_badge["above"])
    watch = "\n".join(
        f"            <li><strong>{lbl}</strong>, {cur}.</li>"
        for lbl, cur in by_badge["watch"] + by_badge["below"])
    n_strong, n_watch = counts["above"], counts["watch"] + counts["below"]
    n_ok = counts["above"] + counts["at"]
    n_total = sum(counts.values())
    return f'''<div class="yb-overview">
      <div class="yb-overview-head">
        <div class="yb-overview-eyebrow">Your benefits in summary</div>
        <h3 class="yb-overview-title">Where {CLIENT} stands today</h3>
      </div>
      <p class="yb-overview-body">{n_ok} of {n_total} benefits sit at or above the foundation median, and none
        falls below the lower quartile. The 12.5% employer pension contribution is top-decile among UK
        foundations, the sick pay scheme reaches a full year of support, and the matched payroll giving is
        something few funders offer. The {n_watch} areas worth attention are ceilings rather than
        gaps. Esm&eacute;e is competitive on both, without leading on either.</p>
      <div class="yb-overview-grid">
        <div class="yb-overview-card yb-overview-card-strength">
          <div class="yb-overview-card-head">Headline strengths</div>
          <ul>
{strengths}
          </ul>
        </div>
        <div class="yb-overview-card yb-overview-card-watch">
          <div class="yb-overview-card-head">Areas to watch</div>
          <ul>
{watch}
          </ul>
        </div>
      </div>
    </div>'''


def gen_overview_intro(n_total, n_ok):
    """First thing on the page, for a reader who has never seen this dashboard."""
    return f'''<div class="efb-intro" data-tour="intro" data-export="what-this-report-is|What this report is">
      <div class="efb-intro-eyebrow">Start here</div>
      <h2>What this report is</h2>
      <p>We took the {n_total} benefits {CLIENT_SHORT} provides and compared each one against two
        groups: <b>grant-making foundations</b>, which is the closest comparison to Esm&eacute;e
        and the one used throughout, and the <b>wider third sector</b>, which shows how the
        funding world as a whole differs from charities generally.</p>
      <p>For every benefit we worked out whether Esm&eacute;e sits at the bottom of the market
        (the lower quartile), in the middle (the median) or at the top (the upper quartile).
        {n_ok} of the {n_total} are at or above the median. Nothing sits below the lower quartile.</p>
      <div class="efb-steps">
        <div class="efb-step">
          <div class="efb-step-n">1</div>
          <div class="efb-step-h">See where you stand</div>
          <div class="efb-step-b">This page gives the headline and a score for each of the six
            benefit categories. <b>Your Benefits</b> shows all {n_total} side by side with the market.</div>
        </div>
        <div class="efb-step">
          <div class="efb-step-n">2</div>
          <div class="efb-step-h">Understand the market</div>
          <div class="efb-step-b">The six category pages set out what employers at each level
            actually provide, so a number has some meaning behind it.</div>
        </div>
        <div class="efb-step">
          <div class="efb-step-n">3</div>
          <div class="efb-step-h">Decide what to do</div>
          <div class="efb-step-b"><b>Action Plan</b> turns the findings into a prioritised list
            with a target for each. <b>Trends</b> looks outward, at benefits comparable funders
            offer that Esm&eacute;e does not.</div>
        </div>
      </div>
      <div class="efb-key">
        <div class="efb-key-item"><span class="efb-key-swatch" style="background:linear-gradient(90deg,#e8e7e3,#d4d3cf)"></span>Lower quartile, the bottom of the market</div>
        <div class="efb-key-item"><span class="efb-key-swatch" style="background:linear-gradient(90deg,#d4b860,#C9785A)"></span>Median, typical practice</div>
        <div class="efb-key-item"><span class="efb-key-swatch" style="background:linear-gradient(90deg,#2c3a8c,#1a1a2e)"></span>Upper quartile, the top of the market</div>
      </div>
      <p class="efb-intro-note" style="margin-top:14px">Every bar in this report
        uses those three bands, and the marker on it is you. If something is not clear,
        There is a <b>Need a hand with this page?</b> panel at the foot of every page, and
        <b>Tour this page</b> in the top right walks you through whichever page you are on.</p>
    </div>'''


PLAN_INTRO = '''<div class="efb-intro" data-tour="plan-intro" data-export="how-to-use-the-plan|What to change, and in what order">
            <div class="efb-intro-eyebrow">How to use this page</div>
            <h2>What to change, and in what order</h2>
            <p>If you were going to change something about the benefits package, this page says
              what it should be and in what order. Everything here comes from the benchmarking,
              so nothing on the list is a matter of taste.</p>
            <p>Set the <b>ambition</b> first. <b>Match the market</b> targets the median, which is
              the cost of no longer being behind comparable foundations. <b>Lead the market</b>
              targets the upper quartile, which is the cost of being a destination employer.
              Then use <b>focus</b> to narrow the list to a single category, which is useful when
              a budget is already earmarked.</p>
            <p>Each priority shows where Esm&eacute;e sits today, the market target, and a
              recommended next step. Items tagged <b>quick win</b> cost little and can usually be
              done inside a year; <b>strategic</b> items need a budget decision. Take the whole
              thing away with <b>Download report</b> or <b>CSV</b>.</p>
          </div>'''

TRENDS_NAV = """<button class="navlink" data-page="trends">
        <span class="navlink-icon"><svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.5 4.5L21.75 7.5M21.75 7.5h-5.25m5.25 0v5.25"/></svg></span>
        <span class="navlink-label">Trends</span>
      </button>"""


# One panel per page, at the foot, phrased for someone reading their first benefits benchmark.
HELP = {
    "overview": [
        "<b>The headline</b> counts how many of the sixteen benefits sit at or above the median for grant-making foundations. It is a summary, not a score out of ten.",
        "<b>The category scorecard</b> shows the six benefit groups. Click any card to open that category and see the market detail behind it.",
        "<b>What needs attention</b> lists the benefits furthest from the market, worst first. These are the same items the Action Plan prioritises.",
    ],
    "provision": [
        "<b>Every card is one benefit.</b> Your provision sits on the left, the foundation market on the right.",
        "<b>The marker on the bar is Esm&eacute;e.</b> Which of the three bands it lands in tells you the position: grey is the lower quartile, gold to clay is around the median, navy is the upper quartile.",
        "<b>The five counts at the top are filters.</b> Click <b>Above market</b> to see only the strengths, or <b>Worth a look</b> for the areas behind comparable funders. Click again to clear.",
        "<b>PNG</b> on any card saves it as an image for a board paper or a slide.",
    ],
    "core": [
        "<b>The three columns are the market, not Esm&eacute;e.</b> They show what foundations at the bottom, middle and top of the market provide for each benefit.",
        "<b>Click any row</b> to open a fuller description of each level, including why employers sit where they do.",
        "<b>Where you sit</b> at the top of the page places Esm&eacute;e against these ranges. <b>Compare the market</b> beside it switches to the wider third sector.",
        "<b>Less common benefits</b> at the foot lists things a minority of funders offer, which is where ideas usually come from.",
    ],
    "trends": [
        "<b>This page is our own write-up</b>, not a market table. It covers where benefits provision is heading across the sector rather than where Esm&eacute;e sits today.",
        "<b>The two lists at the top</b> are Aon's summary of what employers are putting more emphasis on, and what employees are increasingly expecting. They are not the same list.",
        "<b>You might also consider</b> names every initiative the research turned up, grouped by theme, with the reasoning behind each. Items Esm&eacute;e already provides are marked <b>Already in place</b>.",
        "<b>None of it is a shopping list.</b> It is there to give a flavour of the external market, as the overview on Your Benefits says.",
    ],
    "action-plan": [
        "<b>Start with the ambition toggle.</b> It changes every target on the page, and therefore the order of the list.",
        "<b>Priorities are ranked by distance from the target</b>, so the item at the top is the one furthest behind, not necessarily the most expensive.",
        "<b>Strengths to protect</b> matters as much as the gaps. These are the benefits already ahead of the market, and they are the ones to keep when budgets are tight.",
        "<b>Download report</b> prints the plan; <b>CSV</b> gives you the same rows in a spreadsheet.",
    ],
}
# The five remaining market pages read the same way as Core, so they share its guidance.
for _p in ("working-time", "health", "financial", "esg", "learning"):
    HELP[_p] = HELP["core"]


def gen_help(page):
    items = "\n".join(f"          <li>{i}</li>" for i in HELP[page])
    return f'''<details class="efb-help no-print">
        <summary>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
          Need a hand with this page?
        </summary>
        <div class="efb-help-body">
          <ul>
{items}
          </ul>
          <button class="efb-help-tour" type="button" data-ts-tour-start>Walk me through this page</button>
        </div>
      </details>'''


CAT_LABEL = {s: html.unescape(l) for s, l, _, _ in CATEGORIES}


def gen_method(method):
    """What we did. This research sits behind the benchmarking and was not stated anywhere."""
    strands = []
    for i, st in enumerate(method["strands"], 1):
        lst = ("<ul>" + "".join(f"<li>{x}</li>" for x in st["list"]) + "</ul>") if st.get("list") else ""
        strands.append(f'''          <div class="efb-meth-item">
            <div class="efb-meth-n">{i}</div>
            <div>
              <div class="efb-meth-h">{st["h"]}</div>
              <p>{st["b"]}</p>
              {lst}
            </div>
          </div>''')
    nl = "\n"
    return f'''<details class="efb-meth">
        <summary>What we did</summary>
        <div class="efb-meth-body">
          <p class="efb-meth-intro">{method["intro"]}</p>
{nl.join(strands)}
          <p class="efb-meth-also">{method["also"]}</p>
        </div>
      </details>'''


def gen_position_overview(po):
    """Word for word from the consultant's own write-up. Opens Your Benefits."""
    paras = "".join(f"<p>{x}</p>" for x in po["paras"])
    return f'''<div class="efb-pos" data-export="market-position|Overview of market position">
      <div class="efb-pos-eyebrow">Our read</div>
      <h2 class="efb-pos-title">{po["title"]}</h2>
      {paras}
    </div>'''


def gen_trends(benefits, trends, narrative):
    """
    Trends & Themes. Entirely the consultant's own write-up: Aon's summary of where the
    market is moving, the six themes, then every initiative that write-up names with the
    reasoning that accompanies it. The market-derived suggestions live on the Action Plan.
    """
    th = narrative["themes"]

    aon = "".join(f'''          <div class="efb-aon-col">
            <div class="efb-aon-h">{c["h"]}</div>
            <ol>{"".join(f"<li>{i}</li>" for i in c["items"])}</ol>
          </div>''' for c in th["aon"])

    def theme_block(sec, n):
        """
        Collapsible, the same way the market tables expand a row. The write-up is long prose;
        closed it becomes a scannable list of six themes, open it is unchanged.
        """
        out = []
        for para in sec.get("paras", []):
            out.append(f"<p>{para}</p>")
        if sec.get("list"):
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in sec["list"]) + "</ul>")
        for para in sec.get("after", []):
            out.append(f"<p>{para}</p>")
        return f'''        <details class="efb-th">
          <summary>
            <span class="efb-th-n">{n}</span>
            <span class="efb-th-chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg></span>
            <span class="efb-th-txt"><span class="efb-th-h">{sec["h"]}</span><span class="efb-th-sum">{sec["summary"]}</span></span>
          </summary>
          <div class="efb-th-body">{"".join(out)}</div>
        </details>'''

    themes = "\n".join(theme_block(sec, i) for i, sec in enumerate(th["sections"], 1))

    groups = []
    for g in th["consider"]:
        rows = []
        for it in g["items"]:
            have = it.get("have")
            tag = ('<span class="efb-cn-have">Already in place</span>' if have
                   else '<span class="efb-cn-tag">Consider</span>')
            rows.append(f'''            <div class="efb-cn-row{' efb-cn-row--have' if have else ''}">
              <div class="efb-cn-b">{it["b"]}{tag}</div>
              <div class="efb-cn-r">{it["r"]}</div>
            </div>''')
        nl2 = "\n"
        n_new = sum(1 for i in g["items"] if not i.get("have"))
        groups.append(f'''          <div class="efb-cn-group">
            <div class="efb-cn-gh">{g["theme"]}<span class="efb-cn-count">{n_new} to consider</span></div>
{nl2.join(rows)}
          </div>''')

    wb = narrative["wellbeing"]
    wb_items = "".join(
        f'''<div class="efb-wb-item"><div class="efb-wb-h">{i["h"]}</div><p>{i["b"]}</p></div>'''
        for i in wb["items"])

    nl = "\n"
    return f'''      <!-- PAGE: Trends -->
      <section class="page" data-page="trends">
        <section class="bench-section" id="trends">
          <div class="sec-hd">
            <div class="sec-label-row"><span class="sec-num-badge">7</span><span class="sec-eyebrow">Looking Outward</span></div>
            <h2 class="sec-title">Trends &amp; Themes</h2>
          </div>

          <div class="page-overview">
            <div class="page-overview-eyebrow">On this page</div>
            <h3 class="page-overview-title">Where the market is moving</h3>
            <p>{th["intro"]}</p>
            <ol class="efb-toc">
              <li><b>The headline themes</b>, as every survey we reviewed agreed on them</li>
              <li><b>Each theme in turn</b>, six collapsible sections</li>
              <li><b>You might also consider</b>, every initiative named, with its reasoning</li>
              <li><b>A well-being strategy</b>, an example of the joined-up approach</li>
            </ol>
          </div>

          <h3 class="efb-tr-sec" style="margin-top:26px">The headline themes</h3>
          <p class="efb-tr-sec-sub">Summarised by Aon&rsquo;s research.</p>
          <div class="efb-aon efb-xp-out" data-export="market-emphasis|Where the market is moving">
{aon}
          </div>
          <p class="efb-th-striking">{th["striking"]}</p>
          <div class="efb-th-hd">
            <p class="efb-tr-sec-sub" style="margin:0">{th["lead"]}</p>
            <button type="button" class="efb-th-all no-print" data-all="open">Expand all</button>
          </div>
          <div class="efb-th-stack efb-xp-out" data-export="market-themes|Benefits trends and themes">
{themes}
          </div>

          <h3 class="efb-tr-sec">You might also consider</h3>
          <p class="efb-tr-sec-sub">{th["considerIntro"]}</p>
          <div class="efb-cn efb-xp-out" data-export="also-consider|You might also consider">
{nl.join(groups)}
          </div>

          <h3 class="efb-tr-sec">{wb["title"]}</h3>
          <p class="efb-tr-sec-sub">{wb["intro"]}</p>
          <div class="efb-wb efb-xp-out" data-export="wellbeing-strategy|An example of a well-being strategy">{wb_items}</div>
        </section>
      </section>

'''


def gen_consider_appendix(benefits):
    """A condensed version for the Action Plan, which is the page people download."""
    rows = []
    for slug, b in benefits.items():
        # Minor items are listed on Trends but not carried into the downloadable plan; they
        # are the sort of thing an organisation often already has without listing it.
        if b.get("esmee") or b.get("excludeFromConsider") or b.get("minor"):
            continue
        quick = b.get("effort") == "quick"
        rows.append(f'''            <div class="efb-ap-row">
              <div class="efb-ap-name">{b["label"]}
                <span class="efb-tr-eff efb-tr-eff-{'quick' if quick else 'strategic'}">{'Quick win' if quick else 'Strategic'}</span>
              </div>
              <div class="efb-ap-market">Typical practice: {esc(b["m"])}</div>
              <div class="efb-ap-why">{b.get("why") or b["mDetail"]}</div>
            </div>''')
    nl = "\n"
    return f'''          <div class="efb-ap-consider" data-export="other-benefits-to-consider|Other benefits to consider">
            <h3 class="efb-tr-sec" style="margin-top:0">Other benefits to consider</h3>
            <p class="efb-tr-sec-sub">These are benefits comparable funders provide that are not currently part of
              Esm&eacute;e&rsquo;s package. None of them is a gap, so they sit outside the priorities above. <span class="no-print">The
              <b>Trends</b> page carries the full detail and the evidence behind each one.</span></p>
{nl.join(rows)}
          </div>'''


def gen_prov_stats(counts, total):
    return f'''<div class="prov-summary prov-summary-v9">
      <button class="prov-stat prov-stat-total" data-filter="all" type="button">
        <div class="prov-stat-num">{total}</div>
        <div class="prov-stat-lbl">Benefits in&nbsp;place</div>
      </button>
      <button class="prov-stat prov-stat-below" data-filter="below" type="button">
        <div class="prov-stat-num">{counts["below"]}</div>
        <div class="prov-stat-lbl">Below market</div>
      </button>
      <button class="prov-stat prov-stat-mixed" data-filter="amber" type="button">
        <div class="prov-stat-num">{counts["watch"]}</div>
        <div class="prov-stat-lbl">Worth a&nbsp;look</div>
      </button>
      <button class="prov-stat prov-stat-at" data-filter="green" type="button">
        <div class="prov-stat-num">{counts["at"]}</div>
        <div class="prov-stat-lbl">At&nbsp;market</div>
      </button>
      <button class="prov-stat prov-stat-above" data-filter="above" type="button">
        <div class="prov-stat-num">{counts["above"]}</div>
        <div class="prov-stat-lbl">Above market</div>
      </button>
    </div>'''


def gen_js_data(meta, benefits):
    """The single source of truth the report's own scripts read."""
    WHERE = {"above": "sits above the foundation upper quartile",
             "at": "sits at the foundation median",
             "watch": "sits below the foundation median and is worth a look",
             "below": "sits below the foundation lower quartile"}
    haq, market_cat, blist, labels = {}, {}, [], {}
    for slug, b in benefits.items():
        labels[slug] = b["label"]
        if not b.get("noMarket"):
            haq[slug] = {"lq": b["lq"], "m": b["m"], "uq": b["uq"], "sp": b["sp"]}
            market_cat[slug] = b["category"]
        e = b.get("esmee")
        if e:
            row = {"slug": slug, "label": b["label"], "category": b["category"],
                   "badge": e["badge"], "posIdx": e["posIdx"],
                   "current": e["current"], "effort": e["effort"],
                   # Restated on the category pages, so a reader does not have to infer
                   # provision from where a marker sits on the bar.
                   "sits": WHERE[e["badge"]]}
            if b.get("noMarket"):
                row["noMarket"] = True
            blist.append(row)

    cats = [{"slug": s, "label": html.unescape(l), "icon": i} for s, l, i, _ in CATEGORIES]
    j = lambda o: json.dumps(o, ensure_ascii=False)
    return (
        f"  var HA_Q = {j(haq)};\n"
        f"  try {{ window.__HAQ = HA_Q; }} catch (e) {{}}\n"
        # Proper display names per slug. Without this the report titleizes the slug, which
        # turns "pension-employer" into "Pension Employer" and "holiday-buy-sell" into
        # "Holiday Buy Sell" in the compare-the-market rows and the search results.
        f"  var MARKET_LABEL = {j(labels)};\n"
        f"  try {{ window.MARKET_LABEL = MARKET_LABEL; }} catch (e) {{}}\n",
        f"  var BENEFITS = {j(blist)};\n",
        f"  var CATEGORIES = {j(cats)};\n",
        f"  var MARKET_CAT = {j(market_cat)};\n",
        f"  var SECTORS = [['m','Grant-making foundations'],['sp','Wider third sector']];\n",
        len(blist),
    )


# ────────────────────────────────────────────────────────────── surgery helpers

def replace_between(text, start_marker, end_marker, new, what):
    i = text.find(start_marker)
    if i < 0:
        sys.exit(f"BUILD FAILED: could not find start of {what}")
    j = text.find(end_marker, i + len(start_marker))
    if j < 0:
        sys.exit(f"BUILD FAILED: could not find end of {what}")
    return text[:i] + new + text[j + len(end_marker):]


def page_span(text, page):
    """Character range of one <section class="page" data-page="X"> block."""
    # The overview carries class="page active", so match the class list loosely.
    m = re.search(rf'<section class="page[^"]*" data-page="{page}">', text)
    if not m:
        sys.exit(f"BUILD FAILED: no page section for {page}")
    nxt = re.search(r'<section class="page[^"]*" data-page="', text[m.end():])
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def main():
    meta, benefits, trends, narrative = load()
    t = TEMPLATE.read_text(encoding="utf-8")
    orig_len = len(t)

    # 1. Provision cards ------------------------------------------------------
    t = replace_between(
        t, '<div class="rb-stack">', '\n    </div>\n  </section>',
        '<div class="rb-stack">\n' + gen_rb_panels(benefits) + '\n    </div>\n  </section>',
        "rb-stack")

    # 2. Per-category market tables, sector footers and callouts --------------
    for cat, _, _, _ in CATEGORIES:
        lo, hi = page_span(t, cat)
        block = t[lo:hi]

        block = re.sub(r'<tbody>.*?</tbody>',
                       lambda _: "<tbody>\n" + gen_market_rows(benefits, cat) + "\n        </tbody>",
                       block, count=1, flags=re.S)
        block = re.sub(r'<div class="sector-footer">.*?</div>\s*</div>',
                       lambda _: gen_sector_footer(cat), block, count=1, flags=re.S)
        if '<div class="callout">' in block:
            block = re.sub(r'<div class="callout">.*?</ul>\s*</div>',
                           lambda _: gen_callout(cat), block, count=1, flags=re.S)
        else:  # the learning page ships without one
            block = block.replace('</section>\n      </section>',
                                  gen_callout(cat) + '\n\n  </section>\n      </section>', 1)
        t = t[:lo] + block + t[hi:]

    # 3. The JS data layer ----------------------------------------------------
    haq_js, ben_js, cat_js, mc_js, sec_js, n_benefits = gen_js_data(meta, benefits)

    # PENGE is dead code named after a different client, and HA_Q's key is "HA" for
    # housing associations. Both go; only HA_Q's *shape* is kept, because the report's
    # own chart code reads it.
    t = replace_between(t, "  var PENGE = {", "try { window.__HAQ = HA_Q; window.__PENGE = PENGE; } catch (e) {}\n",
                        haq_js, "PENGE/HA_Q block")
    t = replace_between(t, "  var BENEFITS = [", "];\n", ben_js, "BENEFITS")
    t = replace_between(t, "  var CATEGORIES = [", "];\n", cat_js, "CATEGORIES")
    t = replace_between(t, "  var MARKET_CAT = ", ";\n", mc_js, "MARKET_CAT")
    t = replace_between(t, "  var SECTORS = [", "];\n", sec_js, "SECTORS")

    # 4. The narrative and the counts, both derived so they cannot contradict the data
    counts = {"above": 0, "at": 0, "watch": 0, "below": 0}
    by_badge = {"above": [], "at": [], "watch": [], "below": []}
    for slug, b in benefits.items():
        e = b.get("esmee")
        if e:
            counts[e["badge"]] += 1
            by_badge[e["badge"]].append((b["label"], e["current"]))

    t = replace_between(t, '<div class="yb-overview">', '\n    </div>\n\n    <div class="prov-summary',
                        gen_overview(by_badge, counts) + '\n\n    <div class="prov-summary',
                        "yb-overview")
    t = replace_between(t, '<div class="prov-summary prov-summary-v9">', '</div>\n\n    <div class="rb-stack">',
                        gen_prov_stats(counts, n_benefits) + '\n\n    <div class="rb-stack">',
                        "prov-summary")

    # 5. Global rebrand -------------------------------------------------------
    subs = [
        ("Brighton Technologies&apos;s", f"{CLIENT_SHORT}&apos;s"),
        ("Brighton Technologies's", f"{CLIENT_SHORT}'s"),
        ("Brighton Technologies", CLIENT),
        ("brighton-technologies", "esmee-fairbairn"),
        (">Brighton<", f">{FLAG}<"),
        ("Brighton", FLAG),
        ("Technology companies", "Grant-making foundations"),
        ("technology companies", "grant-making foundations"),
        ("Technology sector", "Foundation sector"),
        ("technology sector", "foundation sector"),
        ("Technology market", "foundation market"),
        ("the Technology", "the foundation"),
        ("Small Private Sector", "Wider third sector"),
        ("Small Private", "Wider third sector"),
        ("Large Private Sector", "Wider third sector"),
        ("Large Private", "Wider third sector"),
        ("Q2 2026", meta["period"]),
        ("Data as at May 2026", f'Data as at {meta["dataAsAt"]}'),
        ("May 2026", meta["dataAsAt"]),
        ("14 benefits reviewed", f'{n_benefits} benefits reviewed'),
        ("3 markets analysed", "2 comparator groups"),
        ("BCS", "professional body"),
    ]
    for a, b in subs:
        t = t.replace(a, b)

    # 5b. Use real benefit names, not titleized slugs -------------------------
    # titleize() turns "pension-employer" into "Pension Employer" and "holiday-buy-sell"
    # into "Holiday Buy Sell". Fine as a fallback, wrong as the label a client reads.
    for old, new_js, what in (
        ("BX.titleize(s)", "((window.MARKET_LABEL||{})[s]||BX.titleize(s))", "compare-the-market row labels"),
        ("label:titleize(sl)", "label:((window.MARKET_LABEL||{})[sl]||titleize(sl))", "search index entries"),
    ):
        if old not in t:
            sys.exit(f"BUILD FAILED: could not patch {what}")
        t = t.replace(old, new_js, 1)

    # 6. Fix the bug inherited from the template ------------------------------
    # tableToCsv reads columns 1-3 of a .haq-tbl row, which are LQ/Median/UQ. The header
    # claimed sector columns, a leftover from an older four-column sector table.
    t = re.sub(r'"Benefit","[^"]*\(Median\)","[^"]*","[^"]*"',
               '"Benefit","Lower Quartile","Median","Upper Quartile"', t)

    # 7. Purge the previous client's name from the CSS and JS identifiers -----
    # These are invisible to a reader but they are all over the source of a document we are
    # handing to a client, and they name a different client. Prefixes are consistent, so the
    # rename is safe: rb-penge-*, rb-col-penge, rb-dot-penge, rb-pos-penge, prp-pos-penge.
    t = t.replace("penge", "client").replace("Penge", "Client")
    # pc_unlock was the old gate's sessionStorage key; the real gate sets its own.
    t = t.replace("pc_unlock", "efb_unlock")

    # 8. Delete the dead panel code -------------------------------------------
    # openRichPanel/closeRichPanel are driven by .prov-card elements that exist only in the
    # stylesheet; there has never been one in the markup. The functions also read PENGE,
    # which this build deletes, so leaving them in means a ReferenceError waiting for anyone
    # who wires up a .prov-card later. The working provision filter is the separate handler
    # that operates on .rb-panel.
    t = replace_between(
        t,
        "  function openRichPanel(card) {",
        "\n  function closeRichPanel() {",
        "  // openRichPanel/closeRichPanel removed: they were driven by .prov-card elements\n"
        "  // that exist only in CSS, and read the client-provision object this build deletes.\n"
        "  function closeRichPanel() {",
        "openRichPanel")

    # 9. Remove the demo-only "illustrative sample data" pill -----------------
    # The template carries a badge saying the figures are not the reader's real benchmarks,
    # with a comment telling you to remove it for a live deployment. Esmée's figures are
    # real, so leaving it would tell the client their own benefits data is made up.
    before = len(t)
    t = re.sub(r'\s*<!-- Sample-data badge[^>]*-->\s*<span title="These figures are illustrative[^>]*>.*?</span>',
               "", t, flags=re.S)
    if len(t) == before:
        sys.exit("BUILD FAILED: could not remove the sample-data badge")

    # 10. Remove the inherited localStorage auth gate -------------------------
    # In the demo2 app this report sits behind a React login that writes a localStorage key,
    # and this blocking IIFE redirects to the platform root when the key is absent. Standalone
    # there is no platform root, so it redirects every visitor to a 404 before the page paints.
    # The AES gate in build/encrypt.py is the real access control here.
    t = replace_between(
        t,
        "<!-- TwentySix shell &mdash; auth gate",
        "</script>\n",
        "<!-- Access control is the AES gate wrapped around this document by build/encrypt.py.\n"
        "     The template's localStorage check was removed: it redirects to a platform root\n"
        "     that does not exist in a standalone deployment. -->\n",
        "auth gate") if "<!-- TwentySix shell &mdash; auth gate" in t else t
    if "isAuthed" in t:
        t = replace_between(
            t, "<!-- TwentySix shell", "</script>\n",
            "<!-- Access control is the AES gate wrapped around this document by build/encrypt.py.\n"
            "     The template's localStorage check was removed: it redirects to a platform root\n"
            "     that does not exist in a standalone deployment. -->\n",
            "auth gate")
    if "isAuthed" in t:
        sys.exit("BUILD FAILED: inherited auth gate still present")

    # 11w. Explain the dashboard to a first-time reader -----------------------
    # The Overview opened straight onto a verdict. Someone who has never seen this had no
    # way to know what it was compared against, what a quartile is, or where to go next.
    lo, hi = page_span(t, "overview")
    block = t[lo:hi]
    anchor = '<div class="print-only"'
    if anchor not in block:
        sys.exit("BUILD FAILED: no anchor for the overview intro")
    block = block.replace(anchor, gen_overview_intro(n_benefits, counts["above"] + counts["at"])
                          + "\n          " + anchor, 1)
    t = t[:lo] + block + t[hi:]

    # The Action Plan's controls change every target on the page, and nothing said so.
    lo, hi = page_span(t, "action-plan")
    block = t[lo:hi]
    block = block.replace('<!-- Ambition + focus controls -->',
                          PLAN_INTRO + '\n\n          <!-- Ambition + focus controls -->', 1)
    block = block.replace('<div class="bx-dist-lbl" style="margin-bottom:8px">Ambition</div>',
                          '<div class="bx-dist-lbl" style="margin-bottom:8px" data-tour="plan-ambition">Ambition</div>', 1)
    block = block.replace('<div class="bx-dist-lbl" style="margin-bottom:8px">Focus</div>',
                          '<div class="bx-dist-lbl" style="margin-bottom:8px" data-tour="plan-focus">Focus</div>', 1)
    t = t[:lo] + block + t[hi:]

    # 11u. What we did, and our read of the position --------------------------
    # The method note goes on the Overview, collapsed, so it is available without pushing
    # the findings down the page. The position overview opens Your Benefits, which is where
    # the consultant's read belongs: immediately before the benefit-by-benefit detail.
    lo, hi = page_span(t, "overview")
    block = t[lo:hi]
    anchor_m = '<p class="efb-intro-note"'
    assert anchor_m in block, "no anchor for the method note"
    block = block.replace(anchor_m, gen_method(narrative["method"]) + "\n      " + anchor_m, 1)
    t = t[:lo] + block + t[hi:]

    lo, hi = page_span(t, "provision")
    block = t[lo:hi]
    anchor_p = '<div class="yb-overview">'
    assert anchor_p in block, "no anchor for the position overview"
    block = block.replace(anchor_p, gen_position_overview(narrative["positionOverview"])
                          + "\n\n    " + anchor_p, 1)
    t = t[:lo] + block + t[hi:]

    # 11v. New Trends page ----------------------------------------------------
    anchor = '      <!-- \u2500\u2500 PAGE: Action Plan'
    if anchor not in t:
        anchor = '      <section class="page" data-page="action-plan">'
    if anchor not in t:
        sys.exit("BUILD FAILED: no anchor for the Trends page")
    t = t.replace(anchor, gen_trends(benefits, trends, narrative) + anchor, 1)

    nav = '<button class="navlink" data-page="action-plan">'
    if nav not in t:
        sys.exit("BUILD FAILED: no anchor for the Trends nav link")
    t = t.replace(nav, TRENDS_NAV + "\n      " + nav, 1)

    # And a condensed copy on the Action Plan, because that is the page people download.
    lo, hi = page_span(t, "action-plan")
    block = t[lo:hi]
    idx = block.rfind("</section>")
    block = block[:idx] + gen_consider_appendix(benefits) + "\n      " + block[idx:]
    t = t[:lo] + block + t[hi:]

    # 11x. A help panel at the foot of every page -----------------------------
    for page in ("overview", "provision", "core", "working-time", "health",
                 "financial", "esg", "learning", "trends", "action-plan"):
        lo, hi = page_span(t, page)
        block = t[lo:hi]
        # Close the last wrapper on the page, whichever it is, and sit inside it.
        idx = block.rfind("</section>")
        if idx < 0:
            idx = block.rfind("</div>")
        if idx < 0:
            sys.exit(f"BUILD FAILED: nowhere to put the help panel on {page}")
        block = block[:idx] + gen_help(page) + "\n      " + block[idx:]
        t = t[:lo] + block + t[hi:]

    # 11y. Scroll position on navigation --------------------------------------
    # goTo() called window.scrollTo, but the document does not scroll: .main is the scroll
    # container, so switching pages left the reader wherever they had scrolled to on the
    # previous one, halfway down a table. Scroll the real container, and remember each
    # page's position so returning to a page you have already read puts you back.
    t = replace_between(
        t,
        "      // scroll main to top\n",
        "window.scrollTo({ top: 0, behavior: 'instant' });\n",
        """      // Restore where the reader was on this page, or start at the top if the page is
      // new to them. The original code called window.scrollTo, which does nothing here:
      // `body` carries overflow-y:auto and a fixed height, so BODY is the scroll container,
      // not the window and not .main. Find it by asking what actually overflows rather than
      // naming it, so this survives a change to the shell's layout.
      const scroller = [document.body, document.scrollingElement, document.querySelector('.main')]
        .find(el => el && el.scrollHeight - el.clientHeight > 20) || document.body;
      if (lastSlug && lastSlug !== slug) scrollMemory[lastSlug] = scroller.scrollTop;
      const back = Object.prototype.hasOwnProperty.call(scrollMemory, slug) ? scrollMemory[slug] : 0;
      lastSlug = slug;
      // Two frames: the page only becomes visible after the class toggle above, so its
      // scrollHeight is still the previous page's until layout has settled.
      requestAnimationFrame(() => requestAnimationFrame(() => { scroller.scrollTop = back; }));
""",
        "scroll reset")
    t = t.replace("    function goTo(slug, push = true) {",
                  "    const scrollMemory = {};\n    let lastSlug = null;\n\n"
                  "    function goTo(slug, push = true) {", 1)

    # 11y2. Section export: pop out / PNG / Word ------------------------------
    if "</body>" not in t:
        sys.exit("BUILD FAILED: no </body> to attach the export script to")
    t = t.replace("</body>", EXPORT_SCRIPT + "\n</body>", 1)

    # 11y3. Restate provision on the category pages ---------------------------
    # "Where you sit in X" drew a marker on a bar and left the reader to work out what
    # Esmee actually provides, or to go back to Your Benefits for it. Say it in a sentence.
    old_yp = ("        return '<div class=\"bx-yp\"><div class=\"bx-yp-top\"><span class=\"bx-yp-name\">'+b.label+'</span>'\n"
              "          + '<span class=\"bx-chip bx-bg-'+st+'\" style=\"margin:0\">'+BX.svg(st==='good'?'check':'alert',12)+tag+'</span></div>'\n"
              "          + BX.posBar(b.posIdx) + BX.qCards(b.slug) + '</div>';")
    new_yp = ("        return '<div class=\"bx-yp\"><div class=\"bx-yp-top\"><span class=\"bx-yp-name\">'+b.label+'</span>'\n"
              "          + '<span class=\"bx-chip bx-bg-'+st+'\" style=\"margin:0\">'+BX.svg(st==='good'?'check':'alert',12)+tag+'</span></div>'\n"
              "          + '<div class=\"bx-yp-cur\">Esm\\u00e9e Fairbairn provides <b>'+b.current+'</b>, which '+(b.sits||'')+'.</div>'\n"
              "          + BX.posBar(b.posIdx) + BX.qCards(b.slug) + '</div>';")
    if old_yp not in t:
        sys.exit("BUILD FAILED: could not patch the Where-you-sit renderer")
    t = t.replace(old_yp, new_yp, 1)

    # 11z. Styling corrections ------------------------------------------------
    if "</style>\n</head>" not in t:
        sys.exit("BUILD FAILED: could not find the end of the final style block")
    t = t.replace("</style>\n</head>", STYLE_FIXES + "</style>\n</head>", 1)

    # 11a. Trim the platform nav ----------------------------------------------
    # The template's header advertises six areas of the full Zigbert platform. This is a
    # benefits-only deployment, so five of those six links lead nowhere. The brand block,
    # the tour button and the org pill stay; the tab strip goes.
    t = replace_between(
        t, '<nav class="ts-shell__tabs" aria-label="Sections">', "</nav>\n",
        '<nav class="ts-shell__tabs" aria-label="Sections">\n'
        '      <span class="ts-shell__tab" data-ts-shell-tab="benefits" aria-current="page">Benefits Benchmark</span>\n'
        '    </nav>\n',
        "shell tab strip")
    # The brand block linked back to the platform root, which does not exist here.
    t = t.replace('<a class="ts-shell__brand" href="../" aria-label="Zigbert, Home">',
                  '<span class="ts-shell__brand" aria-label="Zigbert">')
    t = re.sub(r'(</span>\s*)</a>(\s*<nav class="ts-shell__tabs")', r'\1</span>\2', t, count=1)

    # 11b. "On this page" must list the rows the page actually has -------------
    for cat, _, _, _ in CATEGORIES:
        lo, hi = page_span(t, cat)
        block = t[lo:hi]
        names = [b["label"] for s, b in benefits.items()
                 if b["category"] == cat and not b.get("noMarket")]
        listed = ", ".join(names[:-1]) + (" and " + names[-1] if len(names) > 1 else names[0])
        block = re.sub(
            r'(<p class="page-overview-body">This page covers[^<]*<strong>)[^<]*(</strong>)',
            lambda m: m.group(1) + html.escape(listed, quote=False) + m.group(2),
            block, count=1)
        t = t[:lo] + block + t[hi:]

    # 10z. TwentySix branding only --------------------------------------------
    # This is a TwentySix deliverable, so the Zigbert product brand comes out entirely: the
    # header wordmark, the two print letterheads, and the tour's own identifiers. The
    # identifiers are invisible to a reader, but they name the wrong product all the way
    # through the source of a file we hand to a client.
    t = t.replace('src="./shell/zigbert-logo.png" alt="Zigbert"',
                  'src="./shell/twentysix-logo.png" alt="TwentySix"')
    t = t.replace('aria-label="Zigbert"', 'aria-label="TwentySix"')
    t = t.replace("data-zigbert-tour-start", "data-ts-tour-start")
    t = t.replace("data-zigbert-tour-checklist", "data-ts-tour-checklist")
    t = t.replace("ZigbertTour", "TwentySixTour")
    t = t.replace("zigbert:tour", "ts26:tour")
    t = t.replace("ztour-", "tstour-")
    t = t.replace("Zigbert", "TwentySix").replace("zigbert", "twentysix")
    if "zigbert" in t.lower():
        sys.exit("BUILD FAILED: Zigbert branding still present")

    # 11. Retarget the shell assets -------------------------------------------
    # In demo2 the report lives at /benefits/ with the shell one level up. Here it is the
    # site root, so ../shell/ would climb above the GitHub Pages base and 404.
    n_paths = t.count("../shell/")
    t = t.replace("../shell/", "./shell/")
    if n_paths == 0:
        sys.exit("BUILD FAILED: no ../shell/ references found to retarget")

    leftovers = {k: t.lower().count(k) for k in ("brighton", "penge", "technolog", "hsf", "perkbox")}
    bad = {k: v for k, v in leftovers.items() if v}
    if bad:
        print(f"  WARNING leftover template strings: {bad}")

    OUT.write_text(t, encoding="utf-8")
    print(f"built {OUT.relative_to(ROOT)}")
    print(f"  {n_benefits} client benefits, {len([b for b in benefits.values() if not b.get('noMarket')])} market benefits")
    print(f"  position: above {counts['above']} · at {counts['at']} · watch {counts['watch']} · below {counts['below']}")
    print(f"  {orig_len:,} chars in -> {len(t):,} chars out")


if __name__ == "__main__":
    main()
