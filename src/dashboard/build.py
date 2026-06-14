"""Render the DATA object into a standalone, shareable dashboard HTML file."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
PLACEHOLDER = "__DATA_JSON__"


def build_dashboard(data: dict, out_path: str | Path) -> Path:
    template = TEMPLATE.read_text(encoding="utf-8")
    # separators keep the payload compact; the placeholder sits inside a JS
    # expression so a plain JSON literal drops straight in.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = template.replace(PLACEHOLDER, payload)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
