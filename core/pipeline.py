"""Collects everything into one context dict for the brief / digest (no Streamlit needed)."""
import datetime as dt
from typing import Optional

from . import analysis, calendar_events, config, data, storage


def _oslo_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Oslo"))
    except Exception:
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=1)))


def _fmt(label: str, v: float) -> str:
    dec = 4 if label == "USD per EUR" else 3 if label.startswith(("NOK", "USD")) else 2
    return f"{v:,.{dec}f}"


def collect(settings: dict, news: Optional[dict] = None, top_n: int = 5) -> dict:
    now = _oslo_now()
    ctx: dict = {"generated": now.strftime("%A %d %B %Y, %H:%M (Oslo)"), "ai": None}

    # markets
    fx, _ = data.fx_frame(settings.get("lookback", "6mo"))
    prices, _ = data.price_series(config.ALL_SYMBOLS, settings.get("lookback", "6mo"))
    changes, kpis = {}, []
    for key in ["NOK per EUR", "NOK per USD"]:
        if key in fx and fx[key].dropna().size > 1:
            ch = analysis.pct_change_1d(fx[key])
            changes[key] = ch
            kpis.append({"label": key, "value": _fmt(key, fx[key].dropna().iloc[-1]), "delta": ch})
    for label in ["Brent", "TTF gas", "Equinor", "Aker BP"]:
        s = prices.get(label)
        if s is not None and len(s) > 1:
            ch = analysis.pct_change_1d(s)
            changes[label] = ch
            kpis.append({"label": label, "value": _fmt(label, s.iloc[-1]), "delta": ch})
    for label in ["WTI", "Henry Hub", "Vår Energi"]:   # alerts only
        if label in prices:
            changes[label] = analysis.pct_change_1d(prices[label])
    ctx["kpis"] = kpis

    # news
    news = news or data.all_news()
    sections, all_items = {}, []
    for sec, res in news.items():
        items = analysis.enrich((res.data or [])[:40])
        all_items += items
        sections[sec] = items[:top_n]
    ctx["sections"] = sections
    hits = analysis.watchlist_hits(all_items, settings.get("watchlist", []))
    ctx["alerts"] = analysis.compute_alerts(changes, settings.get("alerts", {}), hits)

    # weather + daylight
    wx = data.weather_all({c: config.CITIES[c] for c in settings.get("cities", []) if c in config.CITIES})
    rows = []
    for city, res in wx.items():
        w = res.data
        if not w:
            continue
        cur, dl = w["current"], data.daylight(w) or {}
        rows.append({"city": city, "temp": f"{cur['temperature_2m']:.0f}°C",
                     "desc": data.describe_wmo(cur.get("weather_code")),
                     "sunrise": dl.get("sunrise", ""), "sunset": dl.get("sunset", ""),
                     "daylight": dl.get("hours", "")})
    ctx["weather"] = rows

    sea = []
    for name, res in data.marine_all().items():
        m = res.data
        if m:
            sea.append({"name": name, "hs": "n/a" if m["wave_height"] is None else f"{m['wave_height']:.1f}",
                        "state": data.sea_state(m["wave_height"]),
                        "wind": "n/a" if m["wind"] is None else f"{m['wind']:.0f}"})
    ctx["sea"] = sea

    fb = data.football_matches()
    prepared = analysis.prepare_matches(fb.data or [], settings.get("followed_teams", []))
    today = now.date()
    ctx["football"] = [
        {"time": m["time"], "home": m["home"], "away": m["away"], "league": m["league"],
         "status": analysis.status_text(m), "score": analysis.score_text(m), "followed": m["followed"]}
        for m in analysis.key_matches(prepared, today, min(8, int(settings.get("football_top", 10))))]

    ctx["events"] = [{"date": e["date"].isoformat(), "title": e["title"], "category": e["category"]}
                     for e in calendar_events.upcoming(days=21)][:8]
    return ctx
