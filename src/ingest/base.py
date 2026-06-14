"""Connector interface + registry.

A Connector knows how to pull raw daily metrics and raw post metrics for a
single platform. Live connectors report `available()` == False until their
credentials are present, which lets the pipeline transparently fall back to
the synthetic generator on a per-platform basis.
"""

from __future__ import annotations

import abc
from datetime import date


class Connector(abc.ABC):
    platform: str = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    @abc.abstractmethod
    def available(self) -> bool:
        """True when this connector has everything it needs to fetch live data."""

    @abc.abstractmethod
    def fetch_daily(self, start: date, end: date) -> list[dict]:
        """Return raw daily records (see src/schema.py) for [start, end]."""

    @abc.abstractmethod
    def fetch_posts(self, start: date, end: date) -> list[dict]:
        """Return raw post records (see src/schema.py) published in [start, end]."""


def get_connector(platform: str, cfg: dict, mode: str = "auto") -> Connector:
    """Resolve a connector for `platform`.

    mode:
        "demo"  -> always synthetic
        "live"  -> always the real API connector (errors later if no creds)
        "auto"  -> real connector if available(), else synthetic
    """
    from .synthetic import SyntheticConnector
    from .youtube import YouTubeConnector
    from .instagram import InstagramConnector
    from .tiktok import TikTokConnector

    live_classes = {
        "youtube": YouTubeConnector,
        "instagram": InstagramConnector,
        "tiktok": TikTokConnector,
    }

    if mode == "demo":
        return SyntheticConnector(platform, cfg)

    live = live_classes[platform](cfg)
    if mode == "live":
        return live
    # auto
    return live if live.available() else SyntheticConnector(platform, cfg)
