"""Synthetic data generator.

Produces realistic, deterministic daily + post records for any platform so the
pipeline runs end-to-end with no API credentials. The statistical models
(growth curves, weekday seasonality, revenue/RPM by platform) mirror how the
three platforms actually behave, so the resulting dashboard is representative
rather than random noise.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from .base import Connector

# Per-platform behavioural profile. Tuned to look like a mid-size tech/lifestyle
# creator and to reproduce the revenue notes in the reference dashboard:
#   YouTube  -> ad RPM (~$2-4 per 1k views)
#   Instagram-> sponsor value approximated from reach (~$9 per 1k reach)
#   TikTok   -> Creativity Program payout (~$0.55 per 1k views)
PROFILES = {
    "youtube": {
        "start_followers": 142000, "daily_net": (90, 380),
        "base_views": 40000, "view_spread": 0.32, "monthly_growth": 0.022,
        "reach_ratio": (1.0, 1.0), "eng_rate": (0.035, 0.066),
        "rpm": (2.0, 4.2), "rev_basis": "views", "watch": True,
        "formats": [("short", 0.62, 1.9), ("long_form", 0.38, 0.7)],
    },
    "instagram": {
        "start_followers": 208000, "daily_net": (40, 320),
        "base_views": 135000, "view_spread": 0.30, "monthly_growth": 0.018,
        "reach_ratio": (0.62, 0.80), "eng_rate": (0.060, 0.115),
        "rpm": (8.0, 10.5), "rev_basis": "reach", "watch": False,
        "formats": [("reel", 0.55, 2.6), ("carousel", 0.20, 0.95),
                    ("image", 0.15, 0.70), ("story", 0.10, 0.40)],
    },
    "tiktok": {
        "start_followers": 96000, "daily_net": (120, 1300),
        "base_views": 200000, "view_spread": 0.42, "monthly_growth": 0.075,
        "reach_ratio": (1.0, 1.0), "eng_rate": (0.078, 0.155),
        "rpm": (0.50, 0.66), "rev_basis": "views", "watch": True,
        "formats": [("video", 1.0, 1.0)],
    },
}

TITLES = [
    "Honest gadget review", "Budget vs premium", "Tier list", "Tutorial",
    "How I edit", "Behind the scenes", "Reacting to comments", "What I bought",
    "Mistakes I made", "Productivity setup", "Trying a viral trend",
    "Morning routine", "Q&A with you", "Day in the life", "Unboxing",
]

# Per-topic performance signal: (views multiplier, engagement multiplier).
# Gives some topics a consistent edge so theme/keyword insights are meaningful
# rather than noise. Topics not listed default to (1.0, 1.0).
THEME_WEIGHT = {
    "Tier list": (1.55, 1.20), "Honest gadget review": (1.45, 1.15),
    "Budget vs premium": (1.40, 1.18), "Trying a viral trend": (1.35, 1.22),
    "Tutorial": (1.20, 0.95), "Reacting to comments": (1.10, 1.10),
    "Productivity setup": (1.05, 1.00), "How I edit": (1.00, 1.00),
    "What I bought": (0.95, 1.05), "Q&A with you": (0.90, 1.08),
    "Mistakes I made": (0.85, 1.05), "Behind the scenes": (0.80, 1.00),
    "Morning routine": (0.70, 0.95), "Unboxing": (0.65, 0.92),
    "Day in the life": (0.60, 0.90),
}

# Posts published per platform over the 12-month window.
POST_COUNT = {"youtube": 147, "instagram": 272, "tiktok": 333}

# Weekday multiplier on engagement rate (Mon=0 .. Sun=6). Mid-week peaks.
WEEKDAY_ENG = [1.03, 1.01, 1.05, 1.02, 1.04, 0.97, 0.95]


class SyntheticConnector(Connector):
    def __init__(self, platform: str, cfg: dict):
        super().__init__(cfg)
        self.platform = platform
        self.p = PROFILES[platform]
        seed = f"{cfg.get('creator', 'creator')}::{platform}"
        self.rng = random.Random(seed)

    def available(self) -> bool:
        return True

    # ------------------------------------------------------------------ daily
    def fetch_daily(self, start: date, end: date) -> list[dict]:
        p = self.p
        rng = self.rng
        rows: list[dict] = []
        followers = p["start_followers"]
        n_days = (end - start).days + 1

        for i in range(n_days):
            d = start + timedelta(days=i)
            month_idx = i / 30.0
            growth = (1 + p["monthly_growth"]) ** month_idx
            weekday = d.weekday()

            # Views: trend * weekday seasonality * lognormal noise, with
            # occasional viral spikes.
            season = 1.0 + 0.10 * math.sin((weekday / 7) * 2 * math.pi)
            noise = math.exp(rng.gauss(0, p["view_spread"]))
            spike = 1.0
            if rng.random() < 0.06:
                spike = rng.uniform(1.6, 2.8)
            views = int(p["base_views"] * growth * season * noise * spike)

            lo, hi = p["reach_ratio"]
            reach = views if lo == 1.0 else int(views * rng.uniform(lo, hi))

            eng_lo, eng_hi = p["eng_rate"]
            er = rng.uniform(eng_lo, eng_hi) * WEEKDAY_ENG[weekday]
            engagements = int(reach * er)
            likes = int(engagements * rng.uniform(0.78, 0.88))
            comments = int(engagements * rng.uniform(0.02, 0.05))
            shares = int(engagements * rng.uniform(0.04, 0.10))
            saves = max(0, engagements - likes - comments - shares)

            gained = int(rng.uniform(*p["daily_net"]) * growth)
            lost = int(gained * rng.uniform(0.08, 0.35))
            followers += gained - lost

            basis = views if p["rev_basis"] == "views" else reach
            rpm = rng.uniform(*p["rpm"])
            revenue = round(basis / 1000 * rpm, 2)

            watch = int(views * rng.uniform(0.6, 2.4)) if p["watch"] else 0

            rows.append({
                "date": d.isoformat(), "platform": self.platform,
                "followers": followers, "followers_gained": gained,
                "followers_lost": lost, "views": views, "reach": reach,
                "likes": likes, "comments": comments, "shares": shares,
                "saves": saves, "watch_time_min": watch, "revenue_usd": revenue,
            })
        return rows

    # ------------------------------------------------------------------ posts
    def fetch_posts(self, start: date, end: date) -> list[dict]:
        p = self.p
        rng = self.rng
        n = POST_COUNT[self.platform]
        span = (end - start).days
        formats = p["formats"]
        fmt_names = [f[0] for f in formats]
        fmt_weights = [f[1] for f in formats]
        fmt_boost = {f[0]: f[2] for f in formats}

        rows = []
        for k in range(n):
            day_off = int((k / n) * span + rng.uniform(-3, 3))
            day_off = max(0, min(span, day_off))
            pub = start + timedelta(days=day_off)
            growth = (1 + p["monthly_growth"]) ** (day_off / 30.0)
            fmt = rng.choices(fmt_names, weights=fmt_weights)[0]
            title = rng.choice(TITLES)
            tw_views, tw_eng = THEME_WEIGHT.get(title, (1.0, 1.0))

            base = p["base_views"] * growth * fmt_boost[fmt] * tw_views
            views = int(base * math.exp(rng.gauss(0, 0.6)))
            eng_lo, eng_hi = p["eng_rate"]
            er = rng.uniform(eng_lo, eng_hi) * WEEKDAY_ENG[pub.weekday()] * tw_eng
            engagements = int(views * er)
            likes = int(engagements * rng.uniform(0.78, 0.88))
            comments = int(engagements * rng.uniform(0.02, 0.05))
            shares = int(engagements * rng.uniform(0.04, 0.10))
            saves = max(0, engagements - likes - comments - shares)

            # Only revenue-bearing formats earn (mirrors reference: IG image/story = $0).
            earns = fmt in ("reel", "video", "short", "long_form", "carousel")
            basis = views
            revenue = round(basis / 1000 * rng.uniform(*p["rpm"]), 2) if earns else 0.0

            prefix = {"youtube": "YT", "instagram": "IG", "tiktok": "TT"}[self.platform]
            rows.append({
                "post_id": f"{prefix}{k:04d}", "platform": self.platform,
                "published": pub.isoformat(), "format": fmt,
                "title": title, "views": views, "likes": likes,
                "comments": comments, "shares": shares, "saves": saves,
                "revenue_usd": revenue,
            })
        return rows
