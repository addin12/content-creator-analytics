"""Canonical data schema for the creator-analytics pipeline.

Every connector (synthetic or live API) must emit two record streams that
conform to the shapes below. Keeping a single canonical schema means the
transform / analytics / dashboard layers never need to know which platform
or which acquisition mode produced the data.

RAW DAILY record (one per platform per day)
-------------------------------------------
    date            : "YYYY-MM-DD"
    platform        : "youtube" | "instagram" | "tiktok"
    followers       : int   cumulative follower/subscriber count at end of day
    followers_gained: int
    followers_lost  : int
    views           : int
    reach           : int   unique accounts reached (== views for YT/TT)
    likes           : int
    comments        : int
    shares          : int
    saves           : int
    watch_time_min  : int   0 for platforms that don't expose it
    revenue_usd     : float

RAW POST record (one per published piece of content)
----------------------------------------------------
    post_id     : str
    platform    : str
    published   : "YYYY-MM-DD"
    format      : str   e.g. reel / video / short / long_form / carousel ...
    title       : str
    views       : int
    likes       : int
    comments    : int
    shares      : int
    saves       : int
    revenue_usd : float

Derived fields (engagements, engagement_rate, net_follower_change) are added
by the transform layer so connectors stay as thin as possible.
"""

from __future__ import annotations

PLATFORMS = ("youtube", "instagram", "tiktok")

# Engagement is the sum of these interaction columns.
INTERACTION_COLS = ("likes", "comments", "shares", "saves")

DAILY_COLS = (
    "date", "platform", "followers", "followers_gained", "followers_lost",
    "net_follower_change", "views", "reach", "likes", "comments", "shares",
    "saves", "engagements", "engagement_rate", "watch_time_min", "revenue_usd",
)

POST_COLS = (
    "post_id", "platform", "published", "format", "title", "views",
    "likes", "comments", "shares", "saves", "engagements",
    "engagement_rate", "revenue_usd",
)


def engagements_of(rec: dict) -> int:
    """Sum the interaction columns of a raw record."""
    return int(sum(rec.get(c, 0) or 0 for c in INTERACTION_COLS))


def safe_rate(numerator: float, denominator: float) -> float:
    """Engagement rate, guarded against divide-by-zero, rounded to 5dp."""
    if not denominator:
        return 0.0
    return round(numerator / denominator, 5)
