"""Render the DATA object into a standalone, shareable dashboard HTML file."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
PLACEHOLDER = "__DATA_JSON__"
LANG_PLACEHOLDER = "__INIT_LANG__"


def render_html(data: dict, lang: str = "id") -> str:
    """Return the dashboard HTML with data + initial language injected."""
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (template
            .replace(PLACEHOLDER, payload)
            .replace(LANG_PLACEHOLDER, lang if lang in ("id", "en") else "id"))


def build_dashboard(data: dict, out_path: str | Path, lang: str = "id") -> Path:
    html = render_html(data, lang)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
