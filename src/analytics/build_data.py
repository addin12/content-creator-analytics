"""Aggregate canonical daily + post records into the dashboard `DATA` object.

The output dict matches the schema the front-end (src/dashboard/template.html)
expects exactly: profile, data_quality, totals, kpis, daily, monthly,
format_performance, weekday_performance, top_posts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _pct_change(curr: float, prev: float) -> float:
    if not prev:
        return 0.0
    return round((curr - prev) / abs(prev) * 100, 1)


def _window_sum(rows: list[dict], key: str) -> float:
    return sum(r[key] for r in rows)


def build_data(daily: list[dict], posts: list[dict], profile: dict) -> dict:
    platforms = sorted({r["platform"] for r in daily})
    by_pf = {p: [r for r in daily if r["platform"] == p] for p in platforms}
    for p in platforms:
        by_pf[p].sort(key=lambda r: r["date"])

    date_max = max(_d(r["date"]) for r in daily)
    date_min = min(_d(r["date"]) for r in daily)

    def last_n(rows: list[dict], n: int, offset: int = 0) -> list[dict]:
        """Most-recent n days, optionally shifted back by `offset` days."""
        hi = date_max.toordinal() - offset
        lo = hi - n + 1
        return [r for r in rows if lo <= _d(r["date"]).toordinal() <= hi]

    # ---------------------------------------------------------------- kpis
    kpis = {}
    for p in platforms:
        rows = by_pf[p]
        cur = last_n(rows, 30, 0)
        prev = last_n(rows, 30, 30)
        followers = rows[-1]["followers"] if rows else 0
        views_30d = _window_sum(cur, "views")
        eng_30d = _window_sum(cur, "engagements")
        rev_30d = round(_window_sum(cur, "revenue_usd"), 2)
        net_30d = int(_window_sum(cur, "net_follower_change"))
        er = (sum(r["engagement_rate"] for r in cur) / len(cur) * 100) if cur else 0.0
        kpis[p] = {
            "followers": followers,
            "views_30d": int(views_30d),
            "engagements_30d": int(eng_30d),
            "revenue_30d": rev_30d,
            "net_followers_30d": net_30d,
            "eng_rate": round(er, 2),
            "views_chg_pct": _pct_change(views_30d, _window_sum(prev, "views")),
            "engagements_chg_pct": _pct_change(eng_30d, _window_sum(prev, "engagements")),
            "revenue_chg_pct": _pct_change(rev_30d, _window_sum(prev, "revenue_usd")),
            "followers_chg_pct": _pct_change(net_30d, _window_sum(prev, "net_follower_change")),
        }

    # -------------------------------------------------------------- totals
    totals = {
        "followers": sum(kpis[p]["followers"] for p in platforms),
        "views_30d": sum(kpis[p]["views_30d"] for p in platforms),
        "engagements_30d": sum(kpis[p]["engagements_30d"] for p in platforms),
        "revenue_30d": round(sum(kpis[p]["revenue_30d"] for p in platforms), 2),
        "revenue_12mo": round(_window_sum(daily, "revenue_usd"), 2),
    }

    # ------------------------------------------------------------- monthly
    magg = defaultdict(lambda: defaultdict(float))
    mlast = {}
    for r in daily:
        key = (r["platform"], r["date"][:7])
        magg[key]["views"] += r["views"]
        magg[key]["reach"] += r["reach"]
        magg[key]["engagements"] += r["engagements"]
        magg[key]["revenue_usd"] += r["revenue_usd"]
        magg[key]["net_follower_change"] += r["net_follower_change"]
        mlast[key] = r["followers"]  # rows are date-sorted -> last wins
    monthly = []
    for (p, month) in sorted(magg, key=lambda k: (k[0], k[1])):
        a = magg[(p, month)]
        monthly.append({
            "platform": p, "month": month,
            "views": int(a["views"]), "reach": int(a["reach"]),
            "engagements": int(a["engagements"]),
            "revenue_usd": round(a["revenue_usd"], 2),
            "net_follower_change": int(a["net_follower_change"]),
            "followers": int(mlast[(p, month)]),
        })

    # -------------------------------------------------- format_performance
    fagg = defaultdict(lambda: {"posts": 0, "views": 0, "er": 0.0, "rev": 0.0})
    for po in posts:
        k = (po["platform"], po["format"])
        f = fagg[k]
        f["posts"] += 1
        f["views"] += po["views"]
        f["er"] += po["engagement_rate"]
        f["rev"] += po["revenue_usd"]
    format_performance = []
    for (p, fmt) in sorted(fagg):
        f = fagg[(p, fmt)]
        n = f["posts"]
        format_performance.append({
            "platform": p, "format": fmt, "posts": n,
            "avg_views": round(f["views"] / n, 4) if n else 0,
            "avg_eng_rate": round(f["er"] / n, 4) if n else 0,
            "total_revenue": round(f["rev"], 2),
        })

    # ------------------------------------------------- weekday_performance
    wagg = defaultdict(lambda: {"posts": 0, "er": 0.0})
    for po in posts:
        wd = WEEKDAYS[_d(po["published"]).weekday()]
        k = (po["platform"], wd)
        wagg[k]["posts"] += 1
        wagg[k]["er"] += po["engagement_rate"]
    weekday_performance = []
    for (p, wd) in sorted(wagg):
        w = wagg[(p, wd)]
        n = w["posts"]
        weekday_performance.append({
            "platform": p, "weekday": wd, "posts": n,
            "avg_eng_rate": round(w["er"] / n, 4) if n else 0,
        })

    # ------------------------------------------------------------ top_posts
    top = sorted(posts, key=lambda x: x["views"], reverse=True)[:25]
    top_posts = [{
        "post_id": t["post_id"], "platform": t["platform"],
        "published": t["published"], "format": t["format"], "title": t["title"],
        "views": t["views"], "engagements": t["engagements"],
        "engagement_rate": t["engagement_rate"], "revenue_usd": t["revenue_usd"],
    } for t in top]

    return {
        "profile": profile,
        "data_quality": {
            "daily_rows": len(daily), "post_rows": len(posts),
            "date_min": date_min.isoformat(), "date_max": date_max.isoformat(),
            "platforms": platforms,
        },
        "totals": totals,
        "kpis": kpis,
        "daily": daily,
        "monthly": monthly,
        "format_performance": format_performance,
        "weekday_performance": weekday_performance,
        "top_posts": top_posts,
    }
