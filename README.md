# Creator Analytics Pipeline

End-to-end analytics for content creators: **acquire** social data (YouTube,
Instagram, TikTok) → **normalize** → **aggregate** → **interactive dashboard**.

It runs two ways:

- **Demo mode** — a synthetic generator produces a full year of realistic data
  with **zero credentials and zero dependencies** (Python stdlib only). One
  command gives you a working dashboard.
- **Live mode** — real API connectors activate automatically for any platform
  whose credentials you've supplied. Anything not connected falls back to
  synthetic, so the pipeline never half-breaks.

```
acquire ──► data/raw/*.json ──► normalize ──► data/processed/{daily,posts}.json
        └─ per-platform connector                       │
                                                        ▼
                              aggregate ──► data/processed/dashboard_data.json
                                                        │
                                                        ▼
                                  render ──► dist/dashboard.html  (open in browser)
```

## Quick start

```bash
python run.py --demo --open
```

That generates synthetic data for all three platforms and opens
`dist/dashboard.html`. No `pip install` required.

For live data and config files:

```bash
pip install -r requirements.txt
cp .env.example .env          # add your tokens
python run.py --open          # auto: live where connected, synthetic elsewhere
```

## CLI

```bash
python run.py                       # auto mode
python run.py --demo                # force synthetic (no creds)
python run.py --live                # force live (errors if creds missing)
python run.py --platforms youtube,tiktok
python run.py --config config/creators.yaml
python run.py --open                # open dashboard when done
```

## The dashboard

Self-contained single HTML file (Chart.js from CDN). Four tabs:

| Tab | What it shows |
|-----|----------------|
| **Cross-platform Overview** | Views & engagement over time, audience share, engagement rate by platform |
| **Content Performance** | Engagement rate by format, best day to post, sortable top-content table |
| **Audience Growth** | Cumulative follower growth, net new followers/month, growth summary |
| **Monetization** | Estimated revenue over time, revenue mix, RPM & rev/follower efficiency |

Interactive: toggle platforms, switch the time range (30/90/180/365 days), and
sort the content table by any column. Everything recomputes client-side.

## Architecture

```
src/
  schema.py            Canonical record shapes + shared helpers
  ingest/
    base.py            Connector interface + mode-aware resolver (demo/live/auto)
    synthetic.py       Statistical data generator (growth, seasonality, RPM models)
    youtube.py         YouTube Data API v3 + Analytics API v2
    instagram.py       Instagram Graph API (insights + media)
    tiktok.py          TikTok for Developers (Display/Research API)
  transform/
    normalize.py       Raw → canonical (adds engagements, rates, net follower change)
  analytics/
    build_data.py      Canonical → the dashboard DATA object (KPIs, monthly,
                       format/weekday performance, top posts)
  dashboard/
    template.html      Dashboard shell with a __DATA_JSON__ injection point
    build.py           Renders DATA into a standalone HTML file
  pipeline.py          Orchestrates the four stages
run.py                 CLI
config/creators.yaml   Per-client config (optional)
```

Adding a platform = write one `Connector` subclass that emits the canonical
record shapes in `schema.py`. Nothing else changes.

## Getting live credentials

| Platform | Needs | Notes |
|----------|-------|-------|
| **YouTube** | OAuth client + refresh token, or API key | Analytics & `estimatedRevenue` require the `yt-analytics-monetary.readonly` scope and channel ownership. |
| **Instagram** | Business/Creator account, Graph API long-lived token | No revenue field — sponsor value is **estimated from reach** (`sponsor_rpm`). |
| **TikTok** | TikTok for Developers app, OAuth user token | No revenue field — **estimated from Creativity Program payout** (`creativity_rpm`). Day-level series needs Research API; Display API is approximated by bucketing video stats. |

Put values in `config/creators.yaml` or `.env` (see `.env.example`). A platform
with missing/invalid credentials silently uses synthetic data in `auto` mode.

## Notes on the numbers

- **Engagement rate** uses *reach* as the denominator (reach == views on
  YouTube/TikTok), matching how each platform reports it.
- **Revenue** is real for YouTube (ad RPM) and *estimated* for Instagram
  (sponsor value from reach) and TikTok (Creativity payout) — the model and
  rates are configurable and labelled as estimates in the dashboard footer.
- Synthetic data is **seeded deterministically** per creator+platform, so demo
  runs are reproducible.
