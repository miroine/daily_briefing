"""Persistence: settings JSON, last-good snapshots, SQLite price history."""
import contextlib
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

import pandas as pd

DATA_DIR = Path(os.environ.get("DASH_DATA", Path(__file__).resolve().parent.parent / "data"))
SNAP_DIR = DATA_DIR / "snapshots"
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "dashboard.db"
for _d in (DATA_DIR, SNAP_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def fmt_local(ts: Optional[dt.datetime], tz: str = "Europe/Oslo") -> str:
    if ts is None:
        return "--:--"
    try:
        from zoneinfo import ZoneInfo
        return ts.astimezone(ZoneInfo(tz)).strftime("%H:%M")
    except Exception:
        return ts.astimezone(dt.timezone(dt.timedelta(hours=1))).strftime("%H:%M")


# ---------------------------------------------------------------- settings
def _merge(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def load_settings(defaults: dict) -> dict:
    s = json.loads(json.dumps(defaults))
    try:
        _merge(s, json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------- snapshots
class Result(NamedTuple):
    data: Any
    status: str                      # "live" | "cached" | "none"
    ts: Optional[dt.datetime]

    def badge_text(self) -> str:
        return f"{self.status} · {fmt_local(self.ts)}"


def _snap_path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:120]
    return SNAP_DIR / f"{safe}.json"


def save_snapshot(key: str, data: Any) -> None:
    try:
        _snap_path(key).write_text(
            json.dumps({"saved": now_utc().isoformat(), "data": data}, default=str, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


def load_snapshot(key: str):
    try:
        obj = json.loads(_snap_path(key).read_text(encoding="utf-8"))
        return obj["data"], dt.datetime.fromisoformat(obj["saved"])
    except Exception:
        return None, None


def _has(data: Any) -> bool:
    if data is None:
        return False
    try:
        return len(data) > 0
    except TypeError:
        return True


def live_or_cached(key: str, fn: Callable[[], Any]) -> Result:
    """Run fn(); on failure/empty fall back to the last good snapshot so panels never go blank."""
    try:
        data = fn()
    except Exception:
        data = None
    if _has(data):
        save_snapshot(key, data)
        return Result(data, "live", now_utc())
    data, ts = load_snapshot(key)
    if data is not None:
        return Result(data, "cached", ts)
    return Result(None, "none", None)


# ------------------------------------------------------------ SQLite series
@contextlib.contextmanager
def _db():
    con = sqlite3.connect(DB_FILE)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS series("
                    "symbol TEXT NOT NULL, date TEXT NOT NULL, value REAL, "
                    "PRIMARY KEY(symbol, date))")
        yield con
        con.commit()
    finally:
        con.close()


def upsert_series(symbol: str, s: pd.Series) -> int:
    rows = []
    for idx, v in s.dropna().items():
        ts = pd.Timestamp(idx)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        rows.append((symbol, ts.strftime("%Y-%m-%d"), float(v)))
    if not rows:
        return 0
    with _db() as con:
        con.executemany("INSERT OR REPLACE INTO series(symbol,date,value) VALUES (?,?,?)", rows)
    return len(rows)


def read_series(symbol: str, start: Optional[dt.date] = None) -> pd.Series:
    q = "SELECT date, value FROM series WHERE symbol=?"
    args: list = [symbol]
    if start is not None:
        q += " AND date>=?"
        args.append(start.strftime("%Y-%m-%d"))
    q += " ORDER BY date"
    with _db() as con:
        rows = con.execute(q, args).fetchall()
    if not rows:
        return pd.Series(dtype=float, name=symbol)
    return pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]), name=symbol)


def last_date(symbol: str) -> Optional[dt.date]:
    with _db() as con:
        row = con.execute("SELECT MAX(date) FROM series WHERE symbol=?", (symbol,)).fetchone()
    return dt.date.fromisoformat(row[0]) if row and row[0] else None
