# Esmée Fairbairn Foundation — Benefits Benchmark

A single-page benefits benchmark report, gated by passphrase and served from GitHub Pages.

**Live:** https://twentysixconsulting.github.io/esmee-benefits/
**Credentials:** held outside this repository. Ask the consultant who owns the engagement.
Send them to the client separately from the link, never in the same email.

> This repository is **public**, because GitHub Pages needs it to be. The passphrase must
> never be written down here, in the README, in a commit message, or as a default in
> `build/encrypt.py`. Publishing it alongside the ciphertext it protects would make the gate
> decorative.

Esmée's 16 benefits, benchmarked against two comparator groups: **grant-making foundations**
as the close peer group and the **wider third sector** as the broad market.

## How to change something

```bash
python3 build/build.py       # market.json + template -> _source/report.html
python3 build/verify.py      # structural checks; --browser drives it in Chromium
EFB_USER=... EFB_PASS=... python3 build/encrypt.py   # -> index.html (the gated file)
git commit -am "..." && git push
```

Every figure lives in **`_source/data/market.json`**. Change it there and rebuild. Do not edit
`_source/report.html` or `index.html` by hand: both are generated and your edit will be lost
on the next build.

## Why it is built this way

The template states every quartile **twice**, once in the `HA_Q` object the charts read and
once in the visible table markup. Editing by hand guarantees those drift apart and the report
contradicts itself on screen. Generating both from one JSON file makes that impossible, and
`verify.py` fails the build if they ever disagree.

## What is committed, and what must never be

`index.html` is safe to publish: the entire report body is AES-256-GCM ciphertext, keyed by
PBKDF2-HMAC-SHA256 over `<username>:<passphrase>` at 200,000 iterations. Only the stylesheet
and the login card ship in the clear.

**`_source/` is the same content unencrypted and is gitignored.** Committing any of it would
defeat the gate. There is no server and no key escrow: lose the passphrase and the content is
unrecoverable, which is the point.

## Where the numbers come from

| Comparator | Basis |
|---|---|
| Grant-making foundations | ACF *Salary and Benefits Benchmarking Survey 2023*, n=147, of which 18 are in Esmée's 30-100+ FTE band. Supplemented by the published benefits of nine named UK funders. |
| Wider third sector | Published benefits of named UK charities (Mind, Shelter, Age UK, Barnardo's, MS Trust, Comic Relief), with ONS Table P10 for pension. |

Full workings, including every source URL and the per-benefit positioning rationale, are in
`_source/data/foundations-acf.md` and `_source/data/foundations-matrix.md`.

The ACF 2024 and 2025 editions are member-only, so 2023 is the most recent publicly available
data. The report says so. Prevalence denominators are **foundations that publish a figure**,
never the whole sector: a blank is "not published", never "not provided".

## Open queries for the client

1. **Sabbatical after 7 years** appears on Esmée's careers page but was not in the benefit list
   supplied. It is deliberately **not** in the report pending confirmation.
2. **Life assurance multiple** is not stated. Comparable schemes run 2x to 4x salary, so the
   benefit is shown as present but cannot be positioned on level.
3. **Private medical**: confirm the employer pays nothing toward the premium. This drives its
   below-market position.
4. **Pension**: confirm whether the 5% employee contribution is mandatory or a minimum.
5. **Sick pay year 4** reads 16 weeks full and 6 half, while years 5 and 6 jump to 20/20 and
   24/24. The half-pay column holding at 6 weeks for three years then tripling looks deliberate
   but is worth confirming.
