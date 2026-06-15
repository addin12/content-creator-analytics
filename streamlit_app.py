"""Streamlit entry point for Streamlit Community Cloud.

Reuses the exact same pipeline as the CLI (acquire -> normalize -> aggregate)
and embeds the existing Chart.js dashboard via an HTML component, so the hosted
app looks identical to `dist/dashboard.html`.

Deploy:
    1. Push this repo to GitHub (already done).
    2. Go to https://share.streamlit.io -> "New app" -> pick this repo,
       branch `main`, main file `streamlit_app.py`.
    3. (Optional) add live API tokens under "Advanced settings -> Secrets"
       using the same names as .env.example; without them it runs the
       synthetic demo.

Local run:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.ingest.base import get_connector
from src.transform.normalize import normalize_daily, normalize_posts
from src.analytics.build_data import build_data
from src.dashboard.build import TEMPLATE, PLACEHOLDER

import json

ROOT = Path(__file__).resolve().parent
PLATFORMS = ["youtube", "instagram", "tiktok"]

st.set_page_config(page_title="Creator Analytics", page_icon="📊", layout="wide")

# Trim Streamlit's default chrome so the embedded dashboard gets full width
# (matters most on mobile, where padding eats the screen).
st.markdown(
    """
    <style>
      .block-container{padding:1.2rem 0.6rem 0;max-width:100%;}
      iframe{width:100% !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _load_secrets_into_env() -> None:
    """Mirror Streamlit secrets into env vars so the live connectors find them."""
    try:
        for k, v in st.secrets.items():
            if isinstance(v, (str, int, float)) and k not in os.environ:
                os.environ[k] = str(v)
    except Exception:
        pass  # no secrets configured -> synthetic demo


@st.cache_data(ttl=3600, show_spinner="Building dashboard data…")
def build_payload(mode: str, platforms: tuple[str, ...],
                  creator: str, handle: str, niche: str) -> dict:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=364)
    cfg = {"creator": creator, "platforms": {p: {} for p in platforms}}

    daily_raw: list[dict] = []
    posts_raw: list[dict] = []
    sources = []
    for p in platforms:
        conn = get_connector(p, cfg, mode)
        kind = "live" if conn.__class__.__name__ != "SyntheticConnector" else "synthetic"
        sources.append(f"{p}:{kind}")
        daily_raw.extend(conn.fetch_daily(start, end))
        posts_raw.extend(conn.fetch_posts(start, end))

    daily = normalize_daily(daily_raw)
    posts = normalize_posts(posts_raw)
    any_live = any(s.endswith(":live") for s in sources)
    profile = {
        "creator": creator, "handle": handle, "niche": niche,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "source_label": "live API data" if all(s.endswith(":live") for s in sources)
        else "synthetic + live where connected" if any_live
        else "synthetic sample data for demonstration",
    }
    return build_data(daily, posts, profile)


def render(data: dict) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = template.replace(PLACEHOLDER, payload)
    # The dashboard auto-grows its own iframe to fit content (responsive on
    # desktop & mobile). `height` is just the initial size; `scrolling` is a
    # fallback if the host sandbox blocks the auto-resize.
    components.html(html, height=900, scrolling=True)


# ----------------------------------------------------------------- sidebar UI
_load_secrets_into_env()

st.sidebar.title("📊 Creator Analytics")
st.sidebar.caption("Cross-platform dashboard · YouTube · Instagram · TikTok")

source = st.sidebar.radio(
    "Data source",
    ["Demo (synthetic)", "Live (from secrets)"],
    help="Live uses API tokens stored in Streamlit secrets. Platforms without "
         "tokens fall back to synthetic automatically.",
)
mode = "demo" if source.startswith("Demo") else "auto"

selected = st.sidebar.multiselect(
    "Platforms", PLATFORMS, default=PLATFORMS,
    format_func=lambda p: p.capitalize(),
) or PLATFORMS

with st.sidebar.expander("Creator profile"):
    creator = st.text_input("Name", "Maya Rivera")
    handle = st.text_input("Handle", "@mayacreates")
    niche = st.text_input("Niche", "Tech & lifestyle")

st.sidebar.markdown(
    "Use the **chips, range selector, and tabs** inside the dashboard to "
    "filter platforms, change the time window, and switch views."
)

data = build_payload(mode, tuple(selected), creator, handle, niche)
render(data)
