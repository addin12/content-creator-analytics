"""End-to-end pipeline orchestration.

    acquire (per-platform connector)  ->  data/raw/*.json
       -> normalize                   ->  data/processed/{daily,posts}.json
       -> aggregate                   ->  data/processed/dashboard_data.json
       -> render                      ->  dist/dashboard.html

Each platform resolves its own connector via the mode flag, so you can run a
fully synthetic demo, a fully live pull, or "auto" (live where credentials
exist, synthetic everywhere else) without changing any other layer.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .ingest.base import get_connector
from .transform.normalize import normalize_daily, normalize_posts
from .analytics.build_data import build_data
from .dashboard.build import build_dashboard

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
DIST = ROOT / "dist"


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_window(cfg: dict) -> tuple[date, date]:
    end_s = cfg.get("end_date")
    end = datetime.strptime(end_s, "%Y-%m-%d").date() if end_s else date.today() - timedelta(days=1)
    days = int(cfg.get("window_days", 365))
    start_s = cfg.get("start_date")
    start = datetime.strptime(start_s, "%Y-%m-%d").date() if start_s else end - timedelta(days=days - 1)
    return start, end


def run(cfg: dict, mode: str = "auto", platforms: list[str] | None = None) -> Path:
    platforms = platforms or cfg.get("platforms_enabled", ["youtube", "instagram", "tiktok"])
    start, end = _resolve_window(cfg)

    all_daily_raw: list[dict] = []
    all_posts_raw: list[dict] = []
    source_labels = []

    for p in platforms:
        conn = get_connector(p, cfg, mode)
        kind = "live" if conn.__class__.__name__ != "SyntheticConnector" else "synthetic"
        source_labels.append(f"{p}:{kind}")
        print(f"  [{p}] connector={conn.__class__.__name__} ({kind})")

        daily_raw = conn.fetch_daily(start, end)
        posts_raw = conn.fetch_posts(start, end)
        _write_json(RAW / f"{p}_daily.json", daily_raw)
        _write_json(RAW / f"{p}_posts.json", posts_raw)
        all_daily_raw.extend(daily_raw)
        all_posts_raw.extend(posts_raw)
        print(f"        {len(daily_raw)} daily rows, {len(posts_raw)} posts")

    daily = normalize_daily(all_daily_raw)
    posts = normalize_posts(all_posts_raw)
    _write_json(PROC / "daily.json", daily)
    _write_json(PROC / "posts.json", posts)

    profile = dict(cfg.get("profile", {}))
    profile.setdefault("creator", "Creator")
    profile.setdefault("handle", "@creator")
    profile.setdefault("niche", "Content")
    profile["start_date"] = start.isoformat()
    profile["end_date"] = end.isoformat()
    all_live = all(s.endswith(":live") for s in source_labels)
    profile["source_label"] = (
        "live API data" if all_live else "synthetic + live where connected · sample for demonstration"
        if any(s.endswith(":live") for s in source_labels) else "synthetic sample data for demonstration"
    )

    data = build_data(daily, posts, profile)
    _write_json(PROC / "dashboard_data.json", data)

    out = build_dashboard(data, DIST / "dashboard.html")
    print(f"  dashboard -> {out}")
    return out
