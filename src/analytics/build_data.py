"""Aggregate canonical daily + post records into the dashboard `DATA` object.

Output keys: profile, data_quality, totals, kpis, daily, monthly,
format_performance, weekday_performance, top_posts, and the prescriptive
additions theme_performance, top_keywords, forecast, insights.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]
PF_NAME = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _pct_change(curr: float, prev: float) -> float:
    if not prev:
        return 0.0
    return round((curr - prev) / abs(prev) * 100, 1)


def _window_sum(rows: list[dict], key: str) -> float:
    return sum(r[key] for r in rows)


def _fmt_int(n: float) -> str:
    n = float(n)
    if abs(n) >= 1e6:
        return f"{n/1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"{n/1e3:.1f}K"
    return f"{int(round(n)):,}"


def _fmt_pct(n: float) -> str:
    return f"{'+' if n >= 0 else ''}{n:.1f}%"


def _linreg(ys: list[float]) -> tuple[float, float]:
    """Least-squares slope & intercept over x = 0..n-1."""
    n = len(ys)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den
    return slope, my - slope * mx


def _next_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += 1
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"


def _month_label(ym: str) -> str:
    return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")


def build_data(daily: list[dict], posts: list[dict], profile: dict) -> dict:
    platforms = sorted({r["platform"] for r in daily})
    by_pf = {p: [r for r in daily if r["platform"] == p] for p in platforms}
    for p in platforms:
        by_pf[p].sort(key=lambda r: r["date"])

    date_max = max(_d(r["date"]) for r in daily)
    date_min = min(_d(r["date"]) for r in daily)

    def last_n(rows: list[dict], n: int, offset: int = 0) -> list[dict]:
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
        views = views_30d or 1
        kpis[p] = {
            "followers": followers,
            "views_30d": int(views_30d),
            "engagements_30d": int(eng_30d),
            "revenue_30d": rev_30d,
            "net_followers_30d": net_30d,
            "eng_rate": round(er, 2),
            "rpm": round(rev_30d / views * 1000, 2),
            "views_chg_pct": _pct_change(views_30d, _window_sum(prev, "views")),
            "engagements_chg_pct": _pct_change(eng_30d, _window_sum(prev, "engagements")),
            "revenue_chg_pct": _pct_change(rev_30d, _window_sum(prev, "revenue_usd")),
            "followers_chg_pct": _pct_change(net_30d, _window_sum(prev, "net_follower_change")),
        }

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
        mlast[key] = r["followers"]
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
        f = fagg[(po["platform"], po["format"])]
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
        w = wagg[(po["platform"], wd)]
        w["posts"] += 1
        w["er"] += po["engagement_rate"]
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

    # -------------------------------------- theme_performance + top_keywords
    # "Theme" = the content topic (post title). Doubles as the keyword view:
    # which topics drive the best engagement/views and land in the top posts.
    tagg = defaultdict(lambda: {"posts": 0, "views": 0, "er": 0.0, "rev": 0.0})
    for po in posts:
        t = tagg[(po["platform"], po["title"])]
        t["posts"] += 1
        t["views"] += po["views"]
        t["er"] += po["engagement_rate"]
        t["rev"] += po["revenue_usd"]
    theme_performance = []
    for (p, theme) in sorted(tagg):
        t = tagg[(p, theme)]
        n = t["posts"]
        theme_performance.append({
            "platform": p, "theme": theme, "posts": n,
            "avg_views": round(t["views"] / n, 2) if n else 0,
            "avg_eng_rate": round(t["er"] / n, 4) if n else 0,
            "total_revenue": round(t["rev"], 2),
        })

    # overall theme rollup (across platforms)
    overall = defaultdict(lambda: {"posts": 0, "views": 0, "er_w": 0.0, "rev": 0.0})
    for po in posts:
        o = overall[po["title"]]
        o["posts"] += 1
        o["views"] += po["views"]
        o["er_w"] += po["engagement_rate"]
        o["rev"] += po["revenue_usd"]
    # keywords appearing in the global top-10 posts by views
    top10 = sorted(posts, key=lambda x: x["views"], reverse=True)[:10]
    top10_count = defaultdict(int)
    for po in top10:
        top10_count[po["title"]] += 1
    top_keywords = []
    for theme, o in overall.items():
        n = o["posts"]
        top_keywords.append({
            "theme": theme, "posts": n,
            "avg_views": round(o["views"] / n, 2) if n else 0,
            "avg_eng_rate": round(o["er_w"] / n, 4) if n else 0,
            "total_revenue": round(o["rev"], 2),
            "in_top10": top10_count.get(theme, 0),
        })
    top_keywords.sort(key=lambda x: x["avg_views"], reverse=True)

    # ------------------------------------------------------------- forecast
    months_sorted = sorted({m["month"] for m in monthly})
    # the last month is partial (incomplete) when date_max is NOT its last day,
    # i.e. the next day is still the same month.
    partial = (date_max + timedelta(days=1)).month == date_max.month
    fit_months = months_sorted[:-1] if (partial and len(months_sorted) > 2) else months_sorted
    fit_months = fit_months[-6:]  # recent trend only
    last_actual = months_sorted[-1] if months_sorted else None
    fcast_labels = []
    if last_actual:
        m = last_actual
        for _ in range(3):
            m = _next_month(m)
            fcast_labels.append(m)
    start_x = len(fit_months) if not partial else len(fit_months) + 1

    forecast = {"months": fcast_labels, "labels": [_month_label(m) for m in fcast_labels],
                "platforms": {}}
    for p in platforms:
        mp = {m["month"]: m for m in monthly if m["platform"] == p}
        series = lambda key: [mp[m][key] for m in fit_months if m in mp]
        out = {}
        for key in ("views", "revenue_usd", "followers"):
            ys = series(key)
            if len(ys) >= 2:
                slope, intc = _linreg(ys)
                proj = [max(0, round(slope * (start_x + i) + intc, 2)) for i in range(3)]
            else:
                proj = [ys[-1] if ys else 0] * 3
            out[key] = proj
        forecast["platforms"][p] = out

    # ------------------------------------------------------------- insights
    insights = build_insights(kpis, totals, platforms, top_keywords,
                              format_performance, weekday_performance,
                              forecast, monthly)

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
        "theme_performance": theme_performance,
        "top_keywords": top_keywords,
        "forecast": forecast,
        "insights": insights,
    }


def build_insights(kpis, totals, platforms, top_keywords, format_performance,
                   weekday_performance, forecast, monthly) -> list[dict]:
    """Rules-based, numbers-backed takeaways. kind: win | watch | tip | forecast."""
    out = []
    name = lambda p: PF_NAME.get(p, p.title())

    # 1) growth engine — most net new followers in 30d
    if platforms:
        g = max(platforms, key=lambda p: kpis[p]["net_followers_30d"])
        k = kpis[g]
        out.append({"kind": "win", "title": "Growth engine",
                    "text": f"{name(g)} added {_fmt_int(k['net_followers_30d'])} followers in the "
                            f"last 30 days — your fastest grower. Keep feeding it."})

    # 2) decelerating growth — biggest negative follower momentum
    dec = [p for p in platforms if kpis[p]["followers_chg_pct"] < -5]
    if dec:
        w = min(dec, key=lambda p: kpis[p]["followers_chg_pct"])
        out.append({"kind": "watch", "title": "Losing momentum",
                    "text": f"{name(w)} follower growth slowed {_fmt_pct(kpis[w]['followers_chg_pct'])} "
                            f"vs the prior 30 days. Revisit what worked there earlier and post more often."})

    # 3) best engagement platform -> repurpose
    if len(platforms) > 1:
        e = max(platforms, key=lambda p: kpis[p]["eng_rate"])
        out.append({"kind": "tip", "title": "Repurpose to your strongest format",
                    "text": f"{name(e)} engages best ({kpis[e]['eng_rate']:.1f}% avg). Repurpose your "
                            f"top ideas from other platforms into {name(e)} first."})

    # 4) best content theme (>=3 posts) -> do more
    elig = [t for t in top_keywords if t["posts"] >= 3]
    if elig:
        best = max(elig, key=lambda t: t["avg_views"])
        out.append({"kind": "win", "title": "Your best topic",
                    "text": f"“{best['theme']}” averages {_fmt_int(best['avg_views'])} views and "
                            f"{best['avg_eng_rate']*100:.1f}% engagement — your strongest topic"
                            + (f" ({best['in_top10']} in your top 10)." if best['in_top10'] else ".")
                            + " Make more of it."})
        worst = min(elig, key=lambda t: t["avg_views"])
        if worst["theme"] != best["theme"]:
            out.append({"kind": "watch", "title": "Underperforming topic",
                        "text": f"“{worst['theme']}” averages only {_fmt_int(worst['avg_views'])} views. "
                                f"Rework the hook/format or post it less."})

    # 5) best day to post (across platforms, weighted by posts)
    wd = defaultdict(lambda: [0.0, 0])
    for r in weekday_performance:
        wd[r["weekday"]][0] += r["avg_eng_rate"] * r["posts"]
        wd[r["weekday"]][1] += r["posts"]
    wd_avg = {k: v[0] / v[1] for k, v in wd.items() if v[1]}
    if wd_avg:
        bestday = max(wd_avg, key=wd_avg.get)
        out.append({"kind": "tip", "title": "Best day to post",
                    "text": f"{bestday} posts engage best ({wd_avg[bestday]*100:.1f}% avg). "
                            f"Schedule your most important content then."})

    # 6) monetization — best earner + RPM context
    if platforms:
        m = max(platforms, key=lambda p: kpis[p]["revenue_30d"])
        out.append({"kind": "tip", "title": "Where the money is",
                    "text": f"{name(m)} earned {('$'+_fmt_int(kpis[m]['revenue_30d']))} in 30 days "
                            f"(${kpis[m]['rpm']:.2f} per 1K views). Lean into its monetization while "
                            f"growing the others."})

    # 7) forecast headline — projected total followers at the 3rd month
    fl = forecast.get("labels") or []
    if fl and forecast.get("platforms"):
        now = sum(kpis[p]["followers"] for p in platforms)
        proj = sum(forecast["platforms"][p]["followers"][-1] for p in platforms
                   if p in forecast["platforms"])
        if proj > 0:
            chg = _pct_change(proj, now)
            out.append({"kind": "forecast", "title": "Projection",
                        "text": f"On current trend you’re on track for ~{_fmt_int(proj)} total "
                                f"followers by {fl[-1]} ({_fmt_pct(chg)} vs today)."})

    return out
