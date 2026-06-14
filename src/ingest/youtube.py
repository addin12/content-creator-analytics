"""YouTube live connector.

Uses the YouTube Data API v3 (channel statistics, video list) and the
YouTube Analytics API v2 (day-level views / watch time / subscriber deltas /
estimated revenue). Activates when an OAuth token or API key is configured.

Required config (config/creators.yaml -> platforms.youtube) or env vars:
    YT_CHANNEL_ID
    YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   (for Analytics + revenue)
  or
    YT_API_KEY                                          (public Data API only)

Revenue (estimatedRevenue) requires the monetary scope
`yt-analytics-monetary.readonly` and ownership of the channel.

Docs:
    https://developers.google.com/youtube/analytics/reference/reports/query
    https://developers.google.com/youtube/v3/docs/videos/list
"""

from __future__ import annotations

import os
from datetime import date

from .base import Connector


class YouTubeConnector(Connector):
    platform = "youtube"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        pc = (cfg.get("platforms", {}) or {}).get("youtube", {})
        self.channel_id = pc.get("channel_id") or os.getenv("YT_CHANNEL_ID")
        self.client_id = pc.get("client_id") or os.getenv("YT_CLIENT_ID")
        self.client_secret = pc.get("client_secret") or os.getenv("YT_CLIENT_SECRET")
        self.refresh_token = pc.get("refresh_token") or os.getenv("YT_REFRESH_TOKEN")
        self.api_key = pc.get("api_key") or os.getenv("YT_API_KEY")

    def available(self) -> bool:
        has_oauth = all([self.channel_id, self.client_id, self.client_secret, self.refresh_token])
        return bool(has_oauth or (self.channel_id and self.api_key))

    # --- auth ---------------------------------------------------------------
    def _access_token(self) -> str:
        import requests
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        r.raise_for_status()
        return r.json()["access_token"]

    # --- daily --------------------------------------------------------------
    def fetch_daily(self, start: date, end: date) -> list[dict]:
        import requests
        token = self._access_token()
        # One Analytics query returns the full day-level matrix.
        params = {
            "ids": f"channel=={self.channel_id}",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": "day",
            "metrics": ("views,estimatedMinutesWatched,likes,comments,shares,"
                        "subscribersGained,subscribersLost,estimatedRevenue"),
            "sort": "day",
        }
        r = requests.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params=params, headers={"Authorization": f"Bearer {token}"}, timeout=60,
        )
        r.raise_for_status()
        payload = r.json()
        cols = [h["name"] for h in payload.get("columnHeaders", [])]

        # Subscriber count is cumulative; seed it from channel statistics and
        # walk forward with the daily gained/lost deltas.
        followers = self._current_subscribers(token)
        deltas = []
        rows_out = []
        for row in payload.get("rows", []):
            rec = dict(zip(cols, row))
            deltas.append(int(rec.get("subscribersGained", 0)) - int(rec.get("subscribersLost", 0)))
        total_delta = sum(deltas)
        running = followers - total_delta
        for row in payload.get("rows", []):
            rec = dict(zip(cols, row))
            gained = int(rec.get("subscribersGained", 0))
            lost = int(rec.get("subscribersLost", 0))
            running += gained - lost
            views = int(rec.get("views", 0))
            rows_out.append({
                "date": rec["day"], "platform": "youtube", "followers": running,
                "followers_gained": gained, "followers_lost": lost,
                "views": views, "reach": views,
                "likes": int(rec.get("likes", 0)), "comments": int(rec.get("comments", 0)),
                "shares": int(rec.get("shares", 0)), "saves": 0,
                "watch_time_min": int(rec.get("estimatedMinutesWatched", 0)),
                "revenue_usd": float(rec.get("estimatedRevenue", 0.0)),
            })
        return rows_out

    def _current_subscribers(self, token: str) -> int:
        import requests
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "statistics", "id": self.channel_id},
            headers={"Authorization": f"Bearer {token}"}, timeout=30,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        return int(items[0]["statistics"]["subscriberCount"]) if items else 0

    # --- posts --------------------------------------------------------------
    def fetch_posts(self, start: date, end: date) -> list[dict]:
        import requests
        token = self._access_token()
        out: list[dict] = []
        page = None
        while True:
            params = {
                "part": "snippet", "channelId": self.channel_id, "type": "video",
                "order": "date", "maxResults": 50,
                "publishedAfter": f"{start.isoformat()}T00:00:00Z",
                "publishedBefore": f"{end.isoformat()}T23:59:59Z",
            }
            if page:
                params["pageToken"] = page
            r = requests.get("https://www.googleapis.com/youtube/v3/search",
                             params=params, headers={"Authorization": f"Bearer {token}"}, timeout=60)
            r.raise_for_status()
            data = r.json()
            ids = [it["id"]["videoId"] for it in data.get("items", []) if it["id"].get("videoId")]
            out.extend(self._video_stats(token, ids))
            page = data.get("nextPageToken")
            if not page:
                break
        return out

    def _video_stats(self, token: str, ids: list[str]) -> list[dict]:
        import requests
        if not ids:
            return []
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "snippet,statistics,contentDetails", "id": ",".join(ids)},
                         headers={"Authorization": f"Bearer {token}"}, timeout=60)
        r.raise_for_status()
        rows = []
        for it in r.json().get("items", []):
            stats = it.get("statistics", {})
            dur = it.get("contentDetails", {}).get("duration", "")
            fmt = "short" if ("M" not in dur and "H" not in dur) else "long_form"
            rows.append({
                "post_id": it["id"], "platform": "youtube",
                "published": it["snippet"]["publishedAt"][:10], "format": fmt,
                "title": it["snippet"]["title"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "shares": 0, "saves": 0, "revenue_usd": 0.0,
            })
        return rows
