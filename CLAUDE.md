# CLAUDE.md

Guidance for AI assistants (Claude Code) working in this repository.

## Working agreement (always follow)

1. **State a verification plan before you start.** Before doing any work, say *how you will prove it works* — the exact command(s), check(s), or observation(s) you'll use to confirm success. If something can't be verified, say so up front.
2. **Verify when you finish, and report results.** After completing the work, actually run that verification and report the outcome plainly — what you ran, what you saw, pass or fail. Never claim "done" or "fixed" without having run the check. If a step was skipped or a test failed, say so with the output.
3. **Reason before changing code, and state the blast radius.** Before editing code, briefly explain *why* the change is correct and *what it could affect* — which files, callers, behaviors, platforms, or users are downstream of it, and how you'll contain the risk. Prefer the smallest change that fixes the root cause.

These apply to every change, large or small. Don't skip them because a change "looks like a one-liner."

## How to verify in this project

The verification plan (rule 1/2) should use these where relevant:

- **Pipeline runs end-to-end:** `python run.py --demo` — should print per-platform row/post counts and write `dist/dashboard.html` with no errors.
- **Dashboard data is sane:** inspect `data/processed/dashboard_data.json` (keys: `kpis`, `monthly`, `forecast`, `insights`, `theme_performance`, `top_keywords`, `top_posts`). Spot-check numbers are plausible (e.g. forecasts trend the same direction as history).
- **Dashboard renders with no JS errors:** load `dist/dashboard.html` in headless Chrome (`scripts/shoot.mjs` pattern) and capture `pageerror`/console errors — must be **none**. Check the relevant tab actually renders (charts not blank/cut off).
- **Responsive + embed:** verify at a **mobile** viewport (~390px) *and* **desktop** (~1366px); for the Streamlit embed, confirm the iframe auto-sizes and `section.stMain` scrolls (don't trust a `fullPage` screenshot — it lies on Streamlit's fixed-viewport layout; scroll the real container).
- **Streamlit app boots:** `streamlit run streamlit_app.py` (or headless on a port) → `/_stcore/health` returns `200`, no tracebacks in the log.

## Project overview

End-to-end content-creator analytics: acquire (YouTube/Instagram/TikTok) → normalize → aggregate → interactive dashboard. Runs fully synthetic with zero credentials; live API connectors activate when configured.

```
src/ingest/      per-platform connectors (synthetic.py + youtube/instagram/tiktok); base.py resolves live-or-synthetic
src/transform/   raw -> canonical records (engagements, rates, net follower change)
src/analytics/   canonical -> DATA object (KPIs, monthly, forecast, insights, themes, top posts)
src/dashboard/   template.html (Chart.js, self-contained) + build.py (injects DATA)
streamlit_app.py reuses the pipeline and embeds the dashboard for hosting
scripts/         shoot.mjs (screenshots) + record.mjs (demo GIF) via puppeteer-core + installed Chrome
run.py           CLI (--demo / --live / auto, --platforms, --config, --open)
```

## Conventions & gotchas

- The **synthetic core pipeline uses only the Python stdlib** — keep `python run.py --demo` dependency-free. `requests`/`pyyaml`/`dotenv`/`streamlit` are only for live/hosting.
- `dist/*.html` and `data/**/*.json` are generated artifacts (gitignored) — don't commit them.
- The dashboard template embeds data at the `__DATA_JSON__` placeholder; never leave it unreplaced.
- Chart.js: charts built in a hidden (`display:none`) tab render cut off until re-rendered when shown — `renderAll()` runs on tab switch to handle this.
- Streamlit embed auto-height: set **only** the iframe height (`fitFrame`); do **not** force ancestor heights (clips desktop) or use a body `ResizeObserver` (freezes mobile).
- Puppeteer: pass `captureBeyondViewport:false` with `clip`; `deviceScaleFactor:2` can break Chart.js lines; use `waitUntil:"domcontentloaded"` for Streamlit (websocket never goes idle).

## Git

Commit/push only when asked. Branch off `main` if needed. End commit messages with the required `Co-Authored-By` trailer.
