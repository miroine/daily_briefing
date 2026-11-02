"""Pure analysis helpers (no network, no Streamlit): tagging, sentiment, alerts, stats."""
import datetime as dt
import re
from typing import Optional

import pandas as pd

from . import config

TOPICS = {
    "Supply & production": ["production", "output", "outage", "shut", "opec", "quota", "barrel",
                            "exports", "supply", "capacity"],
    "Prices & markets": ["price", "brent", "wti", "ttf", "futures", "rally", "slump", "surge",
                         "benchmark", "demand"],
    "Policy & regulation": ["tax", "licence", "license", "regulator", "ministry", "government",
                            "sanctions", "tariff", "parliament", "apa", "award"],
    "M&A & deals": ["acquire", "acquisition", "merger", "deal", "stake", "divest", "takeover",
                    "agreement", "contract"],
    "Safety & incidents": ["accident", "leak", "fire", "explosion", "incident", "strike", "spill",
                           "fatal", "safety", "evacuat"],
    "Low-carbon & CCS": ["ccs", "carbon capture", "hydrogen", "wind", "solar", "geothermal",
                         "net zero", "emission", "low-carbon", "decarbon"],
    "Exploration & projects": ["discovery", "drilling", "wells", "fid", "pdo", "start-up",
                               "startup", "first oil", "tie-back", "appraisal"],
    "Geopolitics": ["war", "attack", "iran", "israel", "gaza", "russia", "ukraine", "houthi",
                    "red sea", "ceasefire", "libya"],
}

POS_STEMS = ("surge", "gain", "growth", "record", "beat", "strong", "boost", "upgrade", "profit",
             "discover", "approv", "success", "rally", "recover", "expand", "increas", "rise",
             "rises", "jump")
NEG_STEMS = ("fall", "drop", "slump", "plunge", "loss", "outage", "leak", "accident", "explos",
             "strike", "attack", "sanction", "downgrade", "delay", "shut", "halt", "declin",
             "crisis", "spill", "fatal", "warn", "cuts", "tumble")
NEG_EXACT = {"war", "cut", "fire", "miss", "hit"}


def _kw_regex(k: str) -> re.Pattern:
    k = k.lower()
    if len(k) <= 4:
        return re.compile(r"\b" + re.escape(k) + r"\b")
    return re.compile(r"\b" + re.escape(k) + r"\w*")


_TOPIC_RX = {t: [_kw_regex(k) for k in kws] for t, kws in TOPICS.items()}


def tag_headline(title: str) -> list:
    low = title.lower()
    return [t for t, rxs in _TOPIC_RX.items() if any(rx.search(low) for rx in rxs)]


def sentiment_score(title: str) -> int:
    toks = re.findall(r"[a-z]+", title.lower())
    pos = sum(1 for t in toks if t.startswith(POS_STEMS))
    neg = sum(1 for t in toks if t.startswith(NEG_STEMS) or t in NEG_EXACT)
    return pos - neg


def sentiment_label(score: int) -> str:
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"


def parse_ts(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def ago(ts: Optional[str], now: Optional[dt.datetime] = None) -> str:
    d = parse_ts(ts)
    if d is None:
        return ""
    now = now or dt.datetime.now(dt.timezone.utc)
    h = int((now - d).total_seconds() // 3600)
    if h >= 24:
        return f"{h // 24}d ago"
    return f"{h}h ago" if h >= 1 else "just now"


def enrich(items: list) -> list:
    out = []
    for it in items or []:
        sc = sentiment_score(it["title"])
        out.append({**it, "tags": tag_headline(it["title"]), "score": sc,
                    "sent": sentiment_label(sc), "ago": ago(it.get("ts"))})
    return out


def topic_counts(by_section: dict) -> pd.DataFrame:
    rows = {}
    for sec, items in by_section.items():
        counts = {t: 0 for t in TOPICS}
        for it in items:
            for t in it.get("tags", []):
                counts[t] += 1
        rows[sec] = counts
    return pd.DataFrame(rows)


def watchlist_hits(items: list, keywords: list) -> list:
    kws = [k.strip().lower() for k in keywords if k and k.strip()]
    hits = []
    for it in items:
        low = it["title"].lower()
        found = [k for k in kws if k in low]
        if found:
            hits.append({**it, "hit": found})
    return hits


# ----------------------------------------------------------------- numbers
def pct_change_1d(s: pd.Series) -> Optional[float]:
    s = s.dropna()
    if len(s) < 2 or s.iloc[-2] == 0:
        return None
    return float((s.iloc[-1] / s.iloc[-2] - 1) * 100)


def stats_table(series: dict) -> pd.DataFrame:
    rows = {}
    for k, v in series.items():
        v = v.dropna()
        if len(v) < 3:
            continue
        rows[k] = {
            "Last": v.iloc[-1],
            "1d %": (v.iloc[-1] / v.iloc[-2] - 1) * 100,
            "1m %": (v.iloc[-1] / v.iloc[max(0, len(v) - 22)] - 1) * 100,
            "Period %": (v.iloc[-1] / v.iloc[0] - 1) * 100,
            "Vol % (ann.)": v.pct_change().std() * (252 ** 0.5) * 100,
        }
    return pd.DataFrame(rows).T if rows else pd.DataFrame()


def rebase(series: dict) -> pd.DataFrame:
    cols = {k: v / v.dropna().iloc[0] * 100 for k, v in series.items() if len(v.dropna()) > 1}
    return pd.DataFrame(cols)


def spread(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).dropna()


# ------------------------------------------------------------------ alerts
def compute_alerts(changes: dict, thresholds: dict, hits: list, now: Optional[dt.datetime] = None) -> list:
    """changes: label -> 1-day % move. Returns list of {level, text}. Levels: high, medium, info."""
    alerts = []
    for label, pct in changes.items():
        grp = config.ALERT_GROUP.get(label)
        thr = thresholds.get(grp) if grp else None
        if pct is None or not thr:
            continue
        if abs(pct) >= thr:
            lvl = "high" if abs(pct) >= thr * 1.5 else "medium"
            alerts.append({"level": lvl, "text": f"{label} {pct:+.2f}% (threshold ±{thr:g}%)"})
    now = now or dt.datetime.now(dt.timezone.utc)
    seen = set()
    for h in hits:
        d = parse_ts(h.get("ts"))
        if d is not None and (now - d) > dt.timedelta(hours=24):
            continue
        key = h["title"].lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        alerts.append({"level": "info", "text": f"Watchlist [{', '.join(h['hit'])}]: {h['title']}",
                       "link": h.get("link")})
        if len(seen) >= 5:
            break
    order = {"high": 0, "medium": 1, "info": 2}
    return sorted(alerts, key=lambda a: order[a["level"]])


# --------------------------------------------------------------- NCS (Sodir)
def parse_ncs_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Turn a Sodir production export (flexible column names) into monthly oil/gas totals."""
    low = {c: str(c).lower() for c in df.columns}
    ycol = next((c for c, l in low.items() if "year" in l), None)
    mcol = next((c for c, l in low.items() if "month" in l), None)

    def pick(*needles):
        for c, l in low.items():
            if all(n in l for n in needles):
                return c
        return None

    oil = pick("oil", "net") or pick("oil")
    gas = pick("gas", "net") or pick("gas")
    if not (ycol and mcol and (oil or gas)):
        raise ValueError("Could not find year/month and oil/gas columns in the CSV")
    d = pd.DataFrame({"date": pd.to_datetime({"year": pd.to_numeric(df[ycol], errors="coerce"),
                                              "month": pd.to_numeric(df[mcol], errors="coerce"),
                                              "day": 1}, errors="coerce")})
    if oil:
        d["oil"] = pd.to_numeric(df[oil], errors="coerce")
    if gas:
        d["gas"] = pd.to_numeric(df[gas], errors="coerce")
    d = d.dropna(subset=["date"]).groupby("date").sum(min_count=1).sort_index()
    return d


# ------------------------------------------------------------------ football
def oslo_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Oslo")
    except Exception:
        return dt.timezone(dt.timedelta(hours=1))


def prepare_matches(matches: list, followed=(), tz=None) -> list:
    """Add Oslo-local date/time and an importance score; return sorted by kick-off."""
    tz = tz or oslo_tz()
    big = [b.lower() for b in config.BIG_TEAMS]
    fol = [f.strip().lower() for f in followed if f and f.strip()]
    out = []
    for m in matches or []:
        k = parse_ts(m.get("kickoff"))
        if k is None:
            continue
        loc = k.astimezone(tz)
        h, a = m["home"].lower(), m["away"].lower()
        is_fol = any(f in h or f in a for f in fol)
        n_big = sum(1 for t in (h, a) if any(b in t for b in big))
        score = (m.get("weight", 0) + (10 if is_fol else 0)
                 + (4 if n_big == 2 else 2 if n_big == 1 else 0) + (1 if m.get("state") == "in" else 0))
        out.append({**m, "local_dt": loc, "date": loc.date(), "time": loc.strftime("%H:%M"),
                    "followed": is_fol, "importance": score})
    return sorted(out, key=lambda x: x["local_dt"])


def key_matches(prepared: list, day: dt.date, top_n: int = 10) -> list:
    todays = [m for m in prepared if m["date"] == day]
    top = sorted(todays, key=lambda m: (-m["importance"], m["local_dt"]))[:top_n]
    return sorted(top, key=lambda m: m["local_dt"])


def score_text(m: dict) -> str:
    if m.get("state") in ("in", "post") and m.get("home_score") not in (None, "") \
            and m.get("away_score") not in (None, ""):
        return f"{m['home_score']}–{m['away_score']}"
    return "v"


def status_text(m: dict) -> str:
    state = m.get("state")
    if state == "in":
        return f"LIVE {m.get('detail') or ''}".strip()
    if state == "post":
        return m.get("detail") or "FT"
    if state == "pre":
        return f"Kick-off {m['time']}"
    return m.get("detail") or m["time"]
