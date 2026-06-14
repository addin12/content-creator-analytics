"""Normalize raw connector output into the canonical daily / post schema.

Adds the derived columns (net_follower_change, engagements, engagement_rate)
and enforces column order / types so downstream layers are platform-agnostic.
"""

from __future__ import annotations

from ..schema import DAILY_COLS, POST_COLS, engagements_of, safe_rate


def normalize_daily(raw_rows: list[dict]) -> list[dict]:
    out = []
    for r in raw_rows:
        gained = int(r.get("followers_gained", 0) or 0)
        lost = int(r.get("followers_lost", 0) or 0)
        eng = engagements_of(r)
        # Engagement rate uses reach as the denominator (reach == views on
        # YouTube/TikTok), matching how each platform reports it.
        reach = int(r.get("reach", r.get("views", 0)) or 0)
        rec = {
            "date": r["date"],
            "platform": r["platform"],
            "followers": int(r.get("followers", 0) or 0),
            "followers_gained": gained,
            "followers_lost": lost,
            "net_follower_change": gained - lost,
            "views": int(r.get("views", 0) or 0),
            "reach": reach,
            "likes": int(r.get("likes", 0) or 0),
            "comments": int(r.get("comments", 0) or 0),
            "shares": int(r.get("shares", 0) or 0),
            "saves": int(r.get("saves", 0) or 0),
            "engagements": eng,
            "engagement_rate": safe_rate(eng, reach),
            "watch_time_min": int(r.get("watch_time_min", 0) or 0),
            "revenue_usd": round(float(r.get("revenue_usd", 0.0) or 0.0), 2),
        }
        out.append({k: rec[k] for k in DAILY_COLS})
    out.sort(key=lambda x: (x["platform"], x["date"]))
    return out


def normalize_posts(raw_rows: list[dict]) -> list[dict]:
    out = []
    for r in raw_rows:
        eng = engagements_of(r)
        views = int(r.get("views", 0) or 0)
        rec = {
            "post_id": r["post_id"],
            "platform": r["platform"],
            "published": r["published"],
            "format": r["format"],
            "title": r.get("title") or "Untitled",
            "views": views,
            "likes": int(r.get("likes", 0) or 0),
            "comments": int(r.get("comments", 0) or 0),
            "shares": int(r.get("shares", 0) or 0),
            "saves": int(r.get("saves", 0) or 0),
            "engagements": eng,
            "engagement_rate": safe_rate(eng, views),
            "revenue_usd": round(float(r.get("revenue_usd", 0.0) or 0.0), 2),
        }
        out.append({k: rec[k] for k in POST_COLS})
    out.sort(key=lambda x: x["published"])
    return out
