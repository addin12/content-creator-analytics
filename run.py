#!/usr/bin/env python3
"""Creator Analytics pipeline CLI.

Examples
--------
    python run.py                       # auto mode: live where creds exist, else synthetic
    python run.py --demo                # force synthetic data (zero credentials needed)
    python run.py --live                # force live connectors (errors if creds missing)
    python run.py --platforms youtube,tiktok
    python run.py --config config/creators.yaml --open

Outputs:
    data/raw/*.json            raw per-platform pulls
    data/processed/*.json      normalized daily/posts + aggregated dashboard_data
    dist/dashboard.html        the interactive dashboard (open in any browser)
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from src.pipeline import run

ROOT = Path(__file__).resolve().parent

# Baked-in defaults so `python run.py --demo` works with zero config + zero deps.
DEFAULT_CFG = {
    "profile": {
        "creator": "Maya Rivera",
        "handle": "@mayacreates",
        "niche": "Tech & lifestyle",
    },
    "platforms_enabled": ["youtube", "instagram", "tiktok"],
    "window_days": 365,
    # end_date defaults to yesterday if omitted
    "platforms": {
        "youtube": {}, "instagram": {}, "tiktok": {},
    },
}


def load_config(path: str | None) -> dict:
    cfg = dict(DEFAULT_CFG)
    candidate = Path(path) if path else (ROOT / "config" / "creators.yaml")
    if not candidate.exists():
        return cfg
    try:
        import yaml  # optional dependency
    except ImportError:
        print(f"  note: PyYAML not installed; ignoring {candidate.name}. "
              f"Run `pip install pyyaml` to use a config file.", file=sys.stderr)
        return cfg
    loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    # shallow merge with nested merge for the two dict keys we care about
    merged = {**cfg, **loaded}
    merged["profile"] = {**cfg["profile"], **(loaded.get("profile") or {})}
    merged["platforms"] = {**cfg["platforms"], **(loaded.get("platforms") or {})}
    return merged


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Content creator analytics pipeline")
    ap.add_argument("--config", help="path to creators.yaml")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="force synthetic data")
    g.add_argument("--live", action="store_true", help="force live API connectors")
    ap.add_argument("--platforms", help="comma-separated subset, e.g. youtube,tiktok")
    ap.add_argument("--open", action="store_true", help="open the dashboard when done")
    args = ap.parse_args(argv)

    # Load .env if python-dotenv is available (purely a convenience).
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass

    cfg = load_config(args.config)
    mode = "demo" if args.demo else "live" if args.live else "auto"
    platforms = args.platforms.split(",") if args.platforms else None

    print(f"Running pipeline (mode={mode}) ...")
    out = run(cfg, mode=mode, platforms=platforms)
    print("Done.")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
