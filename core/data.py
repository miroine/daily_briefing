"""Network fetchers. Every public fetcher degrades gracefully (last-good snapshot / SQLite)."""
import calendar
import datetime as dt
import io
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pandas as pd
import requests

from . import analysis, config, storage

UA = {"User-Agent": "Mozilla/5.0 (DailyBriefingDashboard)"}


# -------------------------------------------------------------------- news
def fetch_feed(url: str, limit: int = 40) -> list:
    import feedparser
    r = requests.get(url, timeout=10, headers=UA)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries[:limit]:
        src_obj = e.get("source") or {}
        src = src_obj.get("title") or feed.feed.get("title", "")
        title = (e.get("title") or "").strip()
        suffix = f" - {src_obj.get('title')}" if src_obj.get("title") else ""
        if suffix and title.endswith(suffix):
            title = title[: -len(suffix)]
        t = e.get("published_parsed") or e.get("updated_parsed")
        ts = dt.datetime(*t[:6], tzinfo=dt.timezone.utc).isoformat() if t else None
        out.append({"title": title, "link": e.get("link", "#"), "src": src, "ts": ts})
    return out


def _safe_feed(url: str) -> list:
    try:
        return fetch_feed(url)
    except Exception:
        return []


def _merge_feeds(urls: list, keep: int = 60) -> list:
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_safe_feed, urls))
    merged, seen = [], set()
    for item in sorted((i for r in results for i in r), key=lambda x: x["ts"] or "", reverse=True):
        key = item["title"].lower()[:70]
        if key and key not in seen:
            seen.add(key)
            merged.append(item)
    return merged[:keep]


def news_section(name: str) -> storage.Result:
    return storage.live_or_cached(f"news_{name}", lambda: _merge_feeds(config.FEEDS[name]))


def all_news() -> dict:
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(news_section, config.SECTIONS))
    return dict(zip(config.SECTIONS, res))


# ---------------------------------------------------------------------- FX
FX_BASES = ["https://api.frankfurter.dev/v1", "https://api.frankfurter.app"]
FX_KEYS = ["NOK per EUR", "USD per EUR", "NOK per USD"]


def sync_fx(days: int = 731) -> None:
    last = storage.last_date("FX:NOK per EUR")
    today = dt.date.today()
    need = days if last is None else min(days, max(10, (today - last).days + 5))
    start = today - dt.timedelta(days=need)
    err = None
    for base in FX_BASES:
        try:
            r = requests.get(f"{base}/{start}..{today}", params={"from": "EUR", "to": "USD,NOK"},
                             timeout=12, headers=UA)
            r.raise_for_status()
            df = pd.DataFrame(r.json()["rates"]).T
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            storage.upsert_series("FX:NOK per EUR", df["NOK"])
            storage.upsert_series("FX:USD per EUR", df["USD"])
            storage.upsert_series("FX:NOK per USD", df["NOK"] / df["USD"])
            return
        except Exception as e:  # try next base
            err = e
    raise RuntimeError(f"FX fetch failed: {err}")


def fx_frame(lookback: str = "6mo") -> tuple:
    status = "live"
    try:
        sync_fx()
    except Exception:
        status = "cached"
    start = dt.date.today() - dt.timedelta(days=config.LOOKBACK_DAYS[lookback])
    df = pd.DataFrame({k: storage.read_series(f"FX:{k}", start) for k in FX_KEYS})
    if df.empty:
        status = "none"
    return df, status


# ------------------------------------------------------------------ prices
def sync_symbol(sym: str) -> None:
    import yfinance as yf
    last = storage.last_date(sym)
    age = (dt.date.today() - last).days if last else None
    period = "2y" if age is None or age > 150 else "6mo" if age > 25 else "1mo"
    h = yf.Ticker(sym).history(period=period, auto_adjust=True)["Close"].dropna()
    if len(h) == 0:
        raise RuntimeError(f"no data for {sym}")
    storage.upsert_series(sym, h)


def price_series(symbols: dict, lookback: str = "6mo") -> tuple:
    """symbols: label -> yahoo symbol. History accumulates in SQLite; only deltas are fetched."""
    def one(item):
        try:
            sync_symbol(item[1])
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=4) as ex:
        oks = list(ex.map(one, symbols.items()))
    start = dt.date.today() - dt.timedelta(days=config.LOOKBACK_DAYS[lookback])
    out = {}
    for label, sym in symbols.items():
        s = storage.read_series(sym, start)
        if len(s) > 2:
            out[label] = s
    status = "none" if not out else "live" if all(oks) else "cached"
    return out, status


def company_info(sym: str) -> storage.Result:
    def fn():
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        rate = info.get("dividendRate")
        return {
            "div_yield": (rate / price * 100) if rate and price else None,
            "pe": info.get("trailingPE"),
            "mcap": info.get("marketCap"),
            "ccy": info.get("currency"),
        }
    return storage.live_or_cached(f"info_{sym}", fn)


MONTH_CODES = "FGHJKMNQUVXZ"


def brent_curve(n: int = 12) -> storage.Result:
    """Best-effort Brent futures strip from Yahoo contract symbols (BZ<month><yy>.NYM)."""
    def fn():
        import yfinance as yf
        today = dt.date.today()
        items = []
        for i in range(1, n + 3):
            idx = today.month - 1 + i
            mm, yy = idx % 12, today.year + idx // 12
            items.append((f"{calendar.month_abbr[mm + 1]}-{yy % 100:02d}",
                          f"BZ{MONTH_CODES[mm]}{yy % 100:02d}.NYM"))

        def one(item):
            try:
                h = yf.Ticker(item[1]).history(period="5d")["Close"].dropna()
                return [item[0], float(h.iloc[-1])] if len(h) else None
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=6) as ex:
            return [r for r in ex.map(one, items) if r]
    return storage.live_or_cached("brent_curve", fn)


# ----------------------------------------------------------------- weather
def describe_wmo(code) -> str:
    return config.WMO.get(int(code), "—") if code is not None else "—"


def fetch_weather(lat: float, lon: float) -> dict:
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=12, headers=UA, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 5,
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,"
                   "precipitation,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,"
                 "sunrise,sunset",
    })
    r.raise_for_status()
    return r.json()


def weather_all(cities: dict) -> dict:
    def one(item):
        name, (lat, lon) = item
        return name, storage.live_or_cached(f"wx_{name}", lambda: fetch_weather(lat, lon))
    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(ex.map(one, cities.items()))


def daylight(w: dict) -> Optional[dict]:
    """Sunrise/sunset/daylight for today from an Open-Meteo payload."""
    try:
        sr = dt.datetime.fromisoformat(w["daily"]["sunrise"][0])
        ss = dt.datetime.fromisoformat(w["daily"]["sunset"][0])
    except Exception:
        return None
    mins = int((ss - sr).total_seconds() // 60)
    return {"sunrise": sr.strftime("%H:%M"), "sunset": ss.strftime("%H:%M"),
            "hours": f"{mins // 60}h{mins % 60:02d}"}


def fetch_marine(lat: float, lon: float) -> dict:
    m = requests.get("https://marine-api.open-meteo.com/v1/marine", timeout=12, headers=UA, params={
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "current": "wave_height,wave_period,wave_direction"})
    m.raise_for_status()
    w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=12, headers=UA, params={
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "current": "wind_speed_10m,wind_gusts_10m", "wind_speed_unit": "ms"})
    w.raise_for_status()
    mc, wc = m.json()["current"], w.json()["current"]
    return {"wave_height": mc.get("wave_height"), "wave_period": mc.get("wave_period"),
            "wave_dir": mc.get("wave_direction"), "wind": wc.get("wind_speed_10m"),
            "gust": wc.get("wind_gusts_10m")}


def marine_all() -> dict:
    def one(item):
        name, (lat, lon) = item
        return name, storage.live_or_cached(f"sea_{name}", lambda: fetch_marine(lat, lon))
    with ThreadPoolExecutor(max_workers=5) as ex:
        return dict(ex.map(one, config.OFFSHORE.items()))


def sea_state(hs: Optional[float]) -> str:
    """Generic indicator only (not an operational criterion)."""
    if hs is None:
        return "n/a"
    return "calm" if hs < 2.5 else "moderate" if hs < 4 else "rough"


def fetch_prayer(city: str, country: str, method: int) -> dict:
    r = requests.get("https://api.aladhan.com/v1/timingsByCity", timeout=12, headers=UA,
                     params={"city": city, "country": country, "method": method})
    r.raise_for_status()
    t = r.json()["data"]["timings"]
    return {k: t[k].split(" ")[0] for k in ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]}


def prayer_all() -> dict:
    def one(item):
        label, (city, country, method) = item
        return label, storage.live_or_cached(
            f"prayer_{label}_{dt.date.today()}", lambda: fetch_prayer(city, country, method))
    with ThreadPoolExecutor(max_workers=2) as ex:
        return dict(ex.map(one, config.PRAYER_CITIES.items()))


# ---------------------------------------------------------------------- NCS
def ingest_ncs(df: pd.DataFrame) -> pd.DataFrame:
    parsed = analysis.parse_ncs_csv(df)
    for col in parsed.columns:
        storage.upsert_series(f"NCS:{col}", parsed[col])
    return parsed


def sync_ncs(url: str) -> str:
    """Fetch a Sodir production CSV export from `url` (paste it in Settings). Returns status."""
    if not url:
        return "none"
    try:
        r = requests.get(url, timeout=30, headers=UA)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), sep=None, engine="python")
        ingest_ncs(df)
        return "live"
    except Exception:
        return "cached"


def ncs_frame() -> pd.DataFrame:
    oil, gas = storage.read_series("NCS:oil"), storage.read_series("NCS:gas")
    df = pd.DataFrame({"oil": oil, "gas": gas}).dropna(how="all")
    return df


# ----------------------------------------------------------------- football
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"


def parse_espn_scoreboard(js: dict, label: str, weight: int) -> list:
    out = []
    for ev in js.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        home = next((t for t in teams if t.get("homeAway") == "home"), None)
        away = next((t for t in teams if t.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        stype = (ev.get("status") or {}).get("type") or {}
        out.append({
            "league": label, "weight": weight, "kickoff": ev.get("date"),
            "home": (home.get("team") or {}).get("displayName", "?"),
            "away": (away.get("team") or {}).get("displayName", "?"),
            "home_score": home.get("score"), "away_score": away.get("score"),
            "state": stype.get("state"),                      # pre | in | post
            "detail": stype.get("shortDetail") or stype.get("detail"),
        })
    return out


def _fetch_league(code: str, label: str, weight: int, d0: dt.date, d1: dt.date) -> list:
    matches = []
    errors = []
    day = d0
    while day <= d1:
        try:
            r = requests.get(ESPN_SCOREBOARD.format(code=code), timeout=10, headers=UA,
                             params={"dates": f"{day:%Y%m%d}", "limit": 300})
            r.raise_for_status()
            matches.extend(parse_espn_scoreboard(r.json(), label, weight))
        except requests.RequestException as e:
            errors.append(e)
        day += dt.timedelta(days=1)
    if errors and not matches:
        raise RuntimeError(f"ESPN scoreboard failed for {label}: {errors[-1]}") from errors[-1]
    return matches


def football_matches(back: int = 1, fwd: int = 1) -> storage.Result:
    """Matches from yesterday..tomorrow across the configured leagues (filter by Oslo date later).
    Per-league failures fall back to that league's same-day snapshot."""
    today = dt.date.today()
    d0, d1 = today - dt.timedelta(days=back), today + dt.timedelta(days=fwd)

    def one(lg):
        code, label, weight = lg
        key = f"fb_{code}_{today}"
        try:
            items = _fetch_league(code, label, weight, d0, d1)
            storage.save_snapshot(key, items)
            return items, "live"
        except Exception:
            items, _ = storage.load_snapshot(key)
            return (items or []), ("cached" if items else "error")

    with ThreadPoolExecutor(max_workers=7) as ex:
        res = list(ex.map(one, config.FOOTBALL_LEAGUES))
    statuses = [s for _, s in res]
    matches, seen = [], set()
    for items, _ in res:
        for m in items:
            k = (m["home"], m["away"], m["kickoff"])
            if k not in seen:
                seen.add(k)
                matches.append(m)
    if "live" in statuses:
        return storage.Result(matches, "live", storage.now_utc())
    if "cached" in statuses:
        return storage.Result(matches, "cached", storage.now_utc())
    return storage.Result(None, "none", None)
