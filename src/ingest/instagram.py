"""Instagram live connector.

Uses the Instagram Graph API (requires a Business/Creator account linked to a
Facebook Page and a long-lived access token). Pulls account insights
(reach / views / follower_count) day by day and per-media insights for posts.

Note: Instagram does not expose ad/sponsor revenue via the API. Revenue here
is *estimated* sponsor value from reach using the rate in config
(`platforms.instagram.sponsor_rpm`, default $9 per 1k reach) -- exactly the
approximation described in the reference dashboard's footnote.

Required config (config/creators.yaml -> platforms.instagram) or env vars:
    IG_USER_ID            (Instagram Business account id, numeric)
    IG_ACCESS_TOKEN       (long-lived token)

Docs: https://developers.facebook.com/docs/instagram-api/guides/insights
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from .base import Connector

GRAPH = "https://graph.facebook.com/v19.0"


class InstagramConnector(Connector):
    platform = "instagram"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        pc = (cfg.get("platforms", {}) or {}).get("instagram", {})
        self.user_id = pc.get("user_id") or os.getenv("IG_USER_ID")
        self.token = pc.get("access_token") or os.getenv("IG_ACCESS_TOKEN")
        self.sponsor_rpm = float(pc.get("sponsor_rpm", 9.0))

    def available(self) -> bool:
        return bool(self.user_id and self.token)

    def fetch_daily(self, start: date, end: date) -> list[dict]:
        import requests
        rows_by_date: dict[str, dict] = {}

        # Insights API caps each call to ~30 days; window through the range.
        cur = start
        while cur <= end:
            chunk_end = min(cur + timedelta(days=29), end)
            params = {
                "metric": "reach,impressions",
                "period": "day",
                "since": int(_epoch(cur)),
                "until": int(_epoch(chunk_end + timedelta(days=1))),
                "access_token": self.token,
            }
            r = requests.get(f"{GRAPH}/{self.user_id}/insights", params=params, timeout=60)
            r.raise_for_status()
            for metric in r.json().get("data", []):
                name = metric["name"]
                for v in metric.get("values", []):
                    d = v["end_time"][:10]
                    rows_by_date.setdefault(d, {})[name] = v.get("value", 0)
            cur = chunk_end + timedelta(days=1)

        # follower_count is a separate day-period metric.
        follower_series = self._follower_series(start, end)

        out = []
        for d in sorted(rows_by_date):
            rec = rows_by_date[d]
            reach = int(rec.get("reach", 0))
            views = int(rec.get("impressions", reach))
            gained = int(follower_series.get(d, {}).get("gained", 0))
            followers = int(follower_series.get(d, {}).get("count", 0))
            # Engagement at the account/day level is not directly returned;
            # it is aggregated from media in fetch_posts. Leave 0 here and let
            # the transform layer reconcile if media-level daily rollups exist.
            revenue = round(reach / 1000 * self.sponsor_rpm, 2)
            out.append({
                "date": d, "platform": "instagram", "followers": followers,
                "followers_gained": gained, "followers_lost": 0,
                "views": views, "reach": reach, "likes": 0, "comments": 0,
                "shares": 0, "saves": 0, "watch_time_min": 0,
                "revenue_usd": revenue,
            })
        return out

    def _follower_series(self, start: date, end: date) -> dict:
        import requests
        out: dict[str, dict] = {}
        cur = start
        while cur <= end:
            chunk_end = min(cur + timedelta(days=29), end)
            try:
                r = requests.get(f"{GRAPH}/{self.user_id}/insights", params={
                    "metric": "follower_count", "period": "day",
                    "since": int(_epoch(cur)),
                    "until": int(_epoch(chunk_end + timedelta(days=1))),
                    "access_token": self.token,
                }, timeout=60)
                r.raise_for_status()
                for metric in r.json().get("data", []):
                    for v in metric.get("values", []):
                        out[v["end_time"][:10]] = {"gained": int(v.get("value", 0))}
            except Exception:
                pass
            cur = chunk_end + timedelta(days=1)
        return out

    def fetch_posts(self, start: date, end: date) -> list[dict]:
        import requests
        out = []
        url = f"{GRAPH}/{self.user_id}/media"
        params = {
            "fields": "id,caption,media_type,media_product_type,timestamp,"
                      "like_count,comments_count",
            "limit": 50, "access_token": self.token,
        }
        while url:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            for m in data.get("data", []):
                pub = m.get("timestamp", "")[:10]
                if not (start.isoformat() <= pub <= end.isoformat()):
                    continue
                fmt = _ig_format(m)
                ins = self._media_insights(m["id"], fmt)
                fmt_l = fmt
                earns = fmt_l in ("reel", "carousel")
                views = ins.get("views", 0)
                rev = round(ins.get("reach", views) / 1000 * self.sponsor_rpm, 2) if earns else 0.0
                out.append({
                    "post_id": m["id"], "platform": "instagram", "published": pub,
                    "format": fmt, "title": (m.get("caption") or "")[:60] or "Untitled",
                    "views": views, "likes": int(m.get("like_count", 0)),
                    "comments": int(m.get("comments_count", 0)),
                    "shares": ins.get("shares", 0), "saves": ins.get("saved", 0),
                    "revenue_usd": rev,
                })
            url = data.get("paging", {}).get("next")
            params = {}  # `next` already carries the query string
        return out

    def _media_insights(self, media_id: str, fmt: str) -> dict:
        import requests
        metrics = "reach,saved,shares,views" if fmt == "reel" else "reach,saved"
        try:
            r = requests.get(f"{GRAPH}/{media_id}/insights",
                             params={"metric": metrics, "access_token": self.token}, timeout=30)
            r.raise_for_status()
            return {m["name"]: m["values"][0]["value"] for m in r.json().get("data", [])}
        except Exception:
            return {}


def _ig_format(m: dict) -> str:
    mpt = (m.get("media_product_type") or "").upper()
    if mpt == "REELS":
        return "reel"
    if mpt == "STORY":
        return "story"
    mt = (m.get("media_type") or "").upper()
    if mt == "CAROUSEL_ALBUM":
        return "carousel"
    if mt == "VIDEO":
        return "reel"
    return "image"


def _epoch(d: date) -> float:
    from datetime import datetime, timezone
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()
