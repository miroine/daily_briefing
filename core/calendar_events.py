"""Event calendar: bundled events.json (verified dates) + your own events in data/user_events.json.
OPEC+ meeting dates are intentionally not bundled (none confirmed) - add them with the form."""
import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import storage

BUNDLED = Path(__file__).resolve().parent.parent / "events.json"
USER_FILE = storage.DATA_DIR / "user_events.json"
CATEGORIES = ["Central bank", "Company", "OPEC+ / policy", "Licensing", "Personal", "Other"]


def _load(path: Path, tag: str) -> list:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for e in raw:
        try:
            out.append({"date": dt.date.fromisoformat(e["date"]), "title": e["title"],
                        "category": e.get("category", "Other"), "source": e.get("source", ""),
                        "origin": tag})
        except (KeyError, ValueError):
            continue
    return out


def all_events() -> list:
    return sorted(_load(BUNDLED, "bundled") + _load(USER_FILE, "user"), key=lambda e: e["date"])


def upcoming(days: Optional[int] = None, today: Optional[dt.date] = None) -> list:
    today = today or dt.date.today()
    evs = [e for e in all_events() if e["date"] >= today]
    if days is not None:
        evs = [e for e in evs if (e["date"] - today).days <= days]
    return evs


def add_user_event(date: dt.date, title: str, category: str) -> None:
    try:
        existing = json.loads(USER_FILE.read_text(encoding="utf-8"))
    except Exception:
        existing = []
    existing.append({"date": date.isoformat(), "title": title.strip(), "category": category})
    USER_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
