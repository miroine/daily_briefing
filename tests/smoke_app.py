"""Executes app.py end-to-end against a stub Streamlit/Plotly (no network), to catch
NameErrors, bad f-strings and logic bugs. Run: python tests/smoke_app.py [online|offline]"""
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
os.environ["DASH_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, str(ROOT))

import datetime as dt  # noqa: E402

import pandas as pd  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "offline"
MD = []   # captured markdown/html output


class Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return fake_widget(name)


def fake_widget(name):
    def fn(*a, **k):
        if name in ("markdown", "caption", "write", "info", "warning", "error", "success"):
            MD.append(str(a[0]) if a else "")
            return None
        if name == "columns":
            n = a[0] if isinstance(a[0], int) else len(a[0])
            return [Ctx() for _ in range(n)]
        if name == "tabs":
            return [Ctx() for _ in a[0]]
        if name in ("button", "form_submit_button", "download_button"):
            return False
        if name == "radio":
            return a[1][k.get("index", 0)]
        if name == "select_slider":
            return k.get("value")
        if name == "slider":
            return a[3] if len(a) > 3 else k.get("value")
        if name == "number_input":
            return a[3]
        if name == "multiselect":
            return k.get("default", [])
        if name == "text_area":
            return k.get("value", "")
        if name == "text_input":
            return k.get("value", "")
        if name == "checkbox":
            return k.get("value", False)
        if name == "file_uploader":
            return None
        if name == "date_input":
            return dt.date.today()
        if name == "selectbox":
            return a[1][0]
        if name in ("form", "expander", "spinner"):
            return Ctx()
        return None
    return fn


class StubSt(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.sidebar = Ctx()
        self.secrets = {}
        self.session_state = {}

    def cache_data(self, *a, **k):
        if a and callable(a[0]):
            return a[0]
        def deco(f):
            return f
        return deco

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return fake_widget(name)


class Fig:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: self


go = types.ModuleType("plotly.graph_objects")
for n in ("Figure", "Scatter", "Bar", "Heatmap"):
    setattr(go, n, Fig)
plotly = types.ModuleType("plotly")
plotly.graph_objects = go
st = StubSt()
comp = types.ModuleType("streamlit.components.v1")
comp.html = lambda *a, **k: MD.append("[components.html]")
st.components = types.ModuleType("streamlit.components")
st.components.v1 = comp
sys.modules.update({"streamlit": st, "streamlit.components": st.components, "streamlit.components.v1": comp,
                    "plotly": plotly, "plotly.graph_objects": go})
sys.modules["streamlit_autorefresh"] = None  # ImportError path

from core import config, data, storage  # noqa: E402

if MODE == "online":
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=120)
    import numpy as np
    rng = np.random.default_rng(0)

    def fake_prices(symbols, lb):
        return {k: pd.Series(100 + rng.normal(0, 1, len(idx)).cumsum(), index=idx) for k in symbols}, "live"

    def fake_fx(lb):
        return pd.DataFrame({"NOK per EUR": 11.5 + rng.normal(0, .02, len(idx)).cumsum(),
                             "NOK per USD": 10.0 + rng.normal(0, .02, len(idx)).cumsum(),
                             "USD per EUR": 1.15 + rng.normal(0, .002, len(idx)).cumsum()}, index=idx), "live"

    def feed_items():
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return [{"title": "Equinor discovery lifts Johan Sverdrup production", "link": "http://x", "src": "S", "ts": now},
                {"title": "Oil price falls as war fears ease & <b>tags</b>", "link": "http://y", "src": "S", "ts": now}]

    w = {"current": {"temperature_2m": 6.4, "apparent_temperature": 3, "wind_speed_10m": 20, "wind_gusts_10m": 30,
                     "precipitation": 0.2, "weather_code": 63},
         "daily": {"time": ["2026-10-31", "2026-11-01"], "temperature_2m_max": [8, 9], "temperature_2m_min": [3, 4],
                   "precipitation_sum": [2, 1], "weather_code": [63, 3],
                   "sunrise": ["2026-10-31T07:32", "x"], "sunset": ["2026-10-31T15:41", "x"]}}
    def fb_items():
        kick = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
        def ev(h, a, state="pre", hs="0", as_="0"):
            return {"date": kick, "status": {"type": {"state": state, "shortDetail": "34'"}},
                    "competitions": [{"competitors": [
                        {"homeAway": "home", "score": hs, "team": {"displayName": h}},
                        {"homeAway": "away", "score": as_, "team": {"displayName": a}}]}]}
        return data.parse_espn_scoreboard({"events": [ev("Arsenal", "Chelsea"), ev("Brann", "Viking", "in", "1", "0")]},
                                          "Premier League", 8)

    patches = [
        mock.patch.object(data, "football_matches", lambda back=1, fwd=1: storage.Result(fb_items(), "live", storage.now_utc())),
        mock.patch.object(data, "price_series", fake_prices),
        mock.patch.object(data, "fx_frame", fake_fx),
        mock.patch.object(data, "all_news", lambda: {s: storage.Result(feed_items(), "live", storage.now_utc())
                                                      for s in config.SECTIONS}),
        mock.patch.object(data, "company_info", lambda s: storage.Result(
            {"div_yield": 4.2, "pe": 8.1, "mcap": 8e11, "ccy": "NOK"}, "live", storage.now_utc())),
        mock.patch.object(data, "brent_curve", lambda n=12: storage.Result(
            [["Dec-26", 80.0], ["Jan-27", 79.5], ["Feb-27", 79.0], ["Mar-27", 78.6]], "live", storage.now_utc())),
        mock.patch.object(data, "weather_all", lambda c: {k: storage.Result(w, "live", storage.now_utc()) for k in c}),
        mock.patch.object(data, "marine_all", lambda: {k: storage.Result(
            {"wave_height": 3.0, "wave_period": 8, "wave_dir": 1, "wind": 12, "gust": 17}, "live", storage.now_utc())
            for k in config.OFFSHORE}),
        mock.patch.object(data, "prayer_all", lambda: {k: storage.Result(
            {"Fajr": "05:00", "Sunrise": "06:30", "Dhuhr": "12:00", "Asr": "15:00", "Maghrib": "17:30", "Isha": "19:00"},
            "live", storage.now_utc()) for k in config.PRAYER_CITIES}),
    ]
    for p in patches:
        p.start()
    # seed NCS history so the NCS tab renders charts
    ncs_idx = pd.date_range("2025-01-01", periods=20, freq="MS")
    storage.upsert_series("NCS:oil", pd.Series(range(20), index=ncs_idx, dtype=float) + 5)
    storage.upsert_series("NCS:gas", pd.Series(range(20), index=ncs_idx, dtype=float) + 9)

src = (ROOT / "app.py").read_text(encoding="utf-8")
exec(compile(src, "app.py", "exec"), {"__name__": "__main__"})
joined = "\n".join(MD)
print(f"[{MODE}] app.py executed without exceptions; {len(MD)} markdown/html chunks emitted")
if MODE == "online":
    for needle in ("Daily Briefing", "Johan Sverdrup", "pill", "8h09", "moderate", "Arsenal", "Today (Oslo time)", "LIVE"):
        assert needle in joined, f"missing in output: {needle}"
    assert "<b>tags</b>" not in joined, "headline HTML was not escaped"
    print("[online] key content assertions passed")
else:
    assert "Market data unavailable" in joined or "unavailable" in joined.lower()
    print("[offline] graceful-degradation messages present")
