"""TikTok live connector.

Uses the TikTok for Developers API. Two surfaces are relevant:

  * Display API  (/v2/user/info/, /v2/video/list/) for follower counts and
    per-video stats -- available to most approved apps.
  * Research/Business API for true day-level time series; if you only have the
    Display API, this connector reconstructs a daily series by bucketing
    published-video stats by date (coarser, but works without Research access).

TikTok exposes no revenue field. Revenue is *estimated* from the Creativity
Program payout rate in config (`platforms.tiktok.creativity_rpm`, default
$0.55 per 1k qualified views).

Required config (config/creators.yaml -> platforms.tiktok) or env vars:
    TT_ACCESS_TOKEN       (OAuth user token, scope: user.info.stats, video.list)

Docs: https://developers.tiktok.com/doc/display-api-overview
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timezone

from .base import Connector

API = "https://open.tiktokapis.com/v2"


class TikTokConnector(Connector):
    platform = "tiktok"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        pc = (cfg.get("platforms", {}) or {}).get("tiktok", {})
        self.token = pc.get("access_token") or os.getenv("TT_ACCESS_TOKEN")
        self.creativity_rpm = float(pc.get("creativity_rpm", 0.55))

    def available(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _videos(self, start: date, end: date) -> list[dict]:
        """Page through /video/list/ and keep videos published in range."""
        import requests
        out, cursor, has_more = [], 0, True
        fields = "id,title,create_time,view_count,like_count,comment_count,share_count"
        while has_more:
            r = requests.post(f"{API}/video/list/", headers=self._headers(),
                              params={"fields": fields},
                              json={"cursor": cursor, "max_count": 20}, timeout=60)
            r.raise_for_status()
            data = r.json().get("data", {})
            for v in data.get("videos", []):
                pub = datetime.fromtimestamp(v["create_time"], tz=timezone.utc).date()
                if start <= pub <= end:
                    out.append(v)
            has_more = data.get("has_more", False)
            cursor = data.get("cursor", 0)
            if not has_more:
                break
        return out

    def fetch_daily(self, start: date, end: date) -> list[dict]:
        """Reconstruct a day-level series by bucketing video stats by publish day.

        With Research API access you'd query the day-dimension time series
        directly; this Display-API fallback gives a usable approximation.
        """
        import requests
        videos = self._videos(start, end)
        by_day = defaultdict(lambda: defaultdict(int))
        for v in videos:
            d = datetime.fromtimestamp(v["create_time"], tz=timezone.utc).date().isoformat()
            by_day[d]["views"] += int(v.get("view_count", 0))
            by_day[d]["likes"] += int(v.get("like_count", 0))
            by_day[d]["comments"] += int(v.get("comment_count", 0))
            by_day[d]["shares"] += int(v.get("share_count", 0))

        # Current follower total (single snapshot from Display API).
        followers_now = 0
        try:
            r = requests.get(f"{API}/user/info/", headers=self._headers(),
                             params={"fields": "follower_count"}, timeout=30)
            r.raise_for_status()
            followers_now = int(r.json()["data"]["user"]["follower_count"])
        except Exception:
            pass

        out = []
        for d in sorted(by_day):
            rec = by_day[d]
            views = rec["views"]
            revenue = round(views / 1000 * self.creativity_rpm, 2)
            out.append({
                "date": d, "platform": "tiktok", "followers": followers_now,
                "followers_gained": 0, "followers_lost": 0,
                "views": views, "reach": views, "likes": rec["likes"],
                "comments": rec["comments"], "shares": rec["shares"], "saves": 0,
                "watch_time_min": 0, "revenue_usd": revenue,
            })
        return out

    def fetch_posts(self, start: date, end: date) -> list[dict]:
        videos = self._videos(start, end)
        rows = []
        for v in videos:
            pub = datetime.fromtimestamp(v["create_time"], tz=timezone.utc).date().isoformat()
            views = int(v.get("view_count", 0))
            rows.append({
                "post_id": str(v["id"]), "platform": "tiktok", "published": pub,
                "format": "video", "title": v.get("title") or "Untitled",
                "views": views, "likes": int(v.get("like_count", 0)),
                "comments": int(v.get("comment_count", 0)),
                "shares": int(v.get("share_count", 0)), "saves": 0,
                "revenue_usd": round(views / 1000 * self.creativity_rpm, 2),
            })
        return rows
