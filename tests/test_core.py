import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp()
os.environ["DASH_DATA"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core import analysis, brief, calendar_events, config, data, pipeline, storage  # noqa: E402


class FakeResp:
    def __init__(self, js=None, text="", status=200):
        self._js, self.text, self.status_code, self.content = js, text, status, text.encode()

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class TestAnalysis(unittest.TestCase):
    def test_tagging_and_sentiment(self):
        t = "Equinor discovery near Johan Sverdrup boosts production outlook"
        tags = analysis.tag_headline(t)
        self.assertIn("Exploration & projects", tags)
        self.assertIn("Supply & production", tags)
        self.assertGreater(analysis.sentiment_score(t), 0)
        self.assertLess(analysis.sentiment_score("Oil prices plunge as war and fire halt output"), 0)
        self.assertEqual(analysis.tag_headline("As well as the weather"), [])

    def test_alerts(self):
        ch = {"Brent": 2.5, "Equinor": 1.0, "TTF gas": -8.0, "NOK per EUR": 0.2}
        al = analysis.compute_alerts(ch, {"oil": 2.0, "gas": 5.0, "equity": 3.0, "fx": 0.8}, [])
        texts = " ".join(a["text"] for a in al)
        self.assertIn("Brent", texts)
        self.assertIn("TTF gas", texts)
        self.assertNotIn("Equinor", texts)
        self.assertEqual(al[0]["level"], "high")  # -8% >= 1.5*5%

    def test_watchlist_alert_recent_only(self):
        now = dt.datetime.now(dt.timezone.utc)
        items = [{"title": "Sonatrach signs deal", "ts": now.isoformat(), "link": "x"},
                 {"title": "Old Sonatrach news", "ts": (now - dt.timedelta(days=3)).isoformat(), "link": "y"}]
        hits = analysis.watchlist_hits(items, ["sonatrach"])
        self.assertEqual(len(hits), 2)
        al = analysis.compute_alerts({}, {}, hits)
        self.assertEqual(len(al), 1)

    def test_stats_rebase_spread(self):
        s = pd.Series(range(100, 160), index=pd.date_range("2026-01-01", periods=60), dtype=float)
        st = analysis.stats_table({"A": s})
        self.assertAlmostEqual(st.loc["A", "Period %"], 59.0)
        self.assertAlmostEqual(analysis.rebase({"A": s})["A"].iloc[0], 100.0)
        self.assertAlmostEqual(analysis.spread(s, s - 4).iloc[-1], 4.0)

    def test_parse_ncs_csv(self):
        df = pd.DataFrame({"prfYear": [2026, 2026, 2026], "prfMonth": [1, 1, 2],
                           "prfPrdOilNetMillSm3": [1.0, 2.0, 4.0],
                           "prfPrdGasNetBillSm3": [3.0, 3.0, 5.0], "prfPrdNGLNetMillSm3": [9, 9, 9]})
        out = analysis.parse_ncs_csv(df)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out["oil"].iloc[0], 3.0)
        self.assertAlmostEqual(out["gas"].iloc[1], 5.0)
        with self.assertRaises(ValueError):
            analysis.parse_ncs_csv(pd.DataFrame({"a": [1]}))

    def test_topic_counts(self):
        items = analysis.enrich([{"title": "Oil price rally", "link": "#", "src": "s", "ts": None}])
        tc = analysis.topic_counts({"X": items})
        self.assertEqual(tc.loc["Prices & markets", "X"], 1)


class TestStorage(unittest.TestCase):
    def test_live_or_cached(self):
        r1 = storage.live_or_cached("k1", lambda: [1, 2])
        self.assertEqual(r1.status, "live")
        r2 = storage.live_or_cached("k1", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        self.assertEqual((r2.status, r2.data), ("cached", [1, 2]))
        r3 = storage.live_or_cached("never", lambda: [])
        self.assertEqual(r3.status, "none")

    def test_series_roundtrip(self):
        s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2026-10-01", periods=3, tz="Europe/Oslo"))
        storage.upsert_series("T", s)
        storage.upsert_series("T", pd.Series([9.0], index=pd.to_datetime(["2026-10-03"])))
        got = storage.read_series("T", dt.date(2026, 10, 2))
        self.assertEqual(list(got.values), [2.0, 9.0])
        self.assertEqual(storage.last_date("T"), dt.date(2026, 10, 3))
        self.assertIsNone(storage.last_date("missing"))

    def test_settings(self):
        d = {"a": 1, "n": {"x": 1, "y": 2}}
        s = storage.load_settings(d)
        s["n"]["x"] = 5
        storage.save_settings(s)
        again = storage.load_settings(d)
        self.assertEqual(again["n"], {"x": 5, "y": 2})


class TestData(unittest.TestCase):
    def test_sync_fx(self):
        js = {"rates": {"2026-10-29": {"NOK": 11.6, "USD": 1.16}, "2026-10-30": {"NOK": 11.7, "USD": 1.17}}}
        with mock.patch.object(data.requests, "get", return_value=FakeResp(js)):
            data.sync_fx(30)
        s = storage.read_series("FX:NOK per USD")
        self.assertAlmostEqual(s.loc["2026-10-30"], 11.7 / 1.17)

    def test_fx_frame_offline_uses_db(self):
        today = dt.date.today()
        idx = pd.date_range(end=pd.Timestamp(today), periods=5)
        for k in data.FX_KEYS:
            storage.upsert_series(f"FX:{k}", pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx))
        with mock.patch.object(data, "sync_fx", side_effect=RuntimeError("down")):
            df, status = data.fx_frame("2y")
        self.assertEqual(status, "cached")
        self.assertIn("NOK per EUR", df.columns)
        self.assertEqual(len(df), 5)

    def test_fx_frame_empty_is_none(self):
        with mock.patch.dict(os.environ, {"DASH_DATA": TMP}), \
                mock.patch.object(data, "sync_fx", side_effect=RuntimeError("down")), \
                mock.patch.object(storage, "read_series", return_value=pd.Series(dtype=float)):
            df, status = data.fx_frame("1mo")
        self.assertEqual(status, "none")

    def test_prayer_marine_daylight(self):
        timings = {"data": {"timings": {k: "05:10 (CET)" for k in
                                        ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha", "Imsak"]}}}
        with mock.patch.object(data.requests, "get", return_value=FakeResp(timings)):
            self.assertEqual(data.fetch_prayer("Bergen", "Norway", 3)["Fajr"], "05:10")

        def fake_get(url, **kw):
            if "marine" in url:
                return FakeResp({"current": {"wave_height": 3.1, "wave_period": 8, "wave_direction": 200}})
            return FakeResp({"current": {"wind_speed_10m": 12, "wind_gusts_10m": 18}})
        with mock.patch.object(data.requests, "get", side_effect=fake_get):
            m = data.fetch_marine(58.0, 2.0)
        self.assertEqual(m["wave_height"], 3.1)
        self.assertEqual(data.sea_state(3.1), "moderate")
        self.assertEqual(data.sea_state(None), "n/a")

        w = {"daily": {"sunrise": ["2026-10-31T07:32"], "sunset": ["2026-10-31T15:41"]}}
        self.assertEqual(data.daylight(w), {"sunrise": "07:32", "sunset": "15:41", "hours": "8h09"})

    def test_sync_ncs(self):
        csv = "prfYear,prfMonth,prfPrdOilNetMillSm3,prfPrdGasNetBillSm3\n2026,1,1.5,3.5\n2026,2,1.6,3.6\n"
        with mock.patch.object(data.requests, "get", return_value=FakeResp(text=csv)):
            self.assertEqual(data.sync_ncs("http://example/x.csv"), "live")
        f = data.ncs_frame()
        self.assertEqual(len(f), 2)
        self.assertAlmostEqual(f["oil"].iloc[-1], 1.6)
        self.assertEqual(data.sync_ncs(""), "none")

    def test_news_merge_dedupes(self):
        a = [{"title": "Same headline here", "link": "1", "src": "A", "ts": "2026-10-31T10:00:00+00:00"}]
        b = [{"title": "Same headline here", "link": "2", "src": "B", "ts": "2026-10-31T09:00:00+00:00"},
             {"title": "Another one", "link": "3", "src": "B", "ts": "2026-10-31T11:00:00+00:00"}]
        with mock.patch.object(data, "fetch_feed", side_effect=[a, b]):
            out = data._merge_feeds(["u1", "u2"])
        self.assertEqual([i["title"] for i in out], ["Another one", "Same headline here"])

    def test_feed_failure_tolerated(self):
        with mock.patch.object(data, "fetch_feed", side_effect=RuntimeError("x")):
            self.assertEqual(data._merge_feeds(["u"]), [])


class TestCalendarBrief(unittest.TestCase):
    def test_calendar(self):
        up = calendar_events.upcoming(days=7, today=dt.date(2026, 10, 31))
        self.assertEqual(up[0]["date"], dt.date(2026, 11, 5))
        self.assertTrue(any("Equinor" in e["title"] for e in calendar_events.upcoming()))
        calendar_events.add_user_event(dt.date(2026, 11, 2), "OPEC+ meeting", "OPEC+ / policy")
        titles = [e["title"] for e in calendar_events.upcoming(days=3, today=dt.date(2026, 10, 31))]
        self.assertIn("OPEC+ meeting", titles)

    def test_brief_escapes_and_limits(self):
        ctx = {"generated": "Sat", "kpis": [{"label": "Brent", "value": "80.00", "delta": 1.2}],
               "alerts": [{"level": "high", "text": "<script>alert(1)</script>"}],
               "sections": {"World": [{"title": "<b>x</b>", "src": "S", "ago": "1h ago", "link": "http://a"}]},
               "weather": [], "sea": [], "events": [], "ai": None}
        html_doc = brief.build_brief_html(ctx, "light", "Summary <i>text</i>")
        self.assertNotIn("<script>alert", html_doc)
        self.assertIn("&lt;script&gt;", html_doc)
        self.assertIn("Print / Save as PDF", html_doc)
        ctx["sections"]["World"] = [{"title": "headline " * 50, "src": "", "ago": ""}] * 80
        self.assertLessEqual(len(brief.to_text(ctx)), 3800)


class TestPipeline(unittest.TestCase):
    def test_collect_with_mocks(self):
        idx = pd.date_range("2026-10-01", periods=30)
        series = {k: pd.Series(range(100, 130), index=idx, dtype=float) for k in config.ALL_SYMBOLS}
        fx = pd.DataFrame({"NOK per EUR": range(30), "NOK per USD": range(30), "USD per EUR": range(1, 31)},
                          index=idx).astype(float) + 10
        news = {s: storage.Result([{"title": f"{s} Equinor Sonatrach rally", "link": "#", "src": "S",
                                    "ts": dt.datetime.now(dt.timezone.utc).isoformat()}], "live", None)
                for s in config.SECTIONS}
        w = {"current": {"temperature_2m": 5, "weather_code": 3},
             "daily": {"sunrise": ["2026-10-31T07:32"], "sunset": ["2026-10-31T15:41"]}}
        with mock.patch.object(data, "fx_frame", return_value=(fx, "live")), \
                mock.patch.object(data, "price_series", return_value=(series, "live")), \
                mock.patch.object(data, "weather_all",
                                  return_value={"Bergen": storage.Result(w, "live", None)}), \
                mock.patch.object(data, "football_matches", return_value=storage.Result([], "live", None)), \
                mock.patch.object(data, "marine_all", return_value={
                    "Troll": storage.Result({"wave_height": 4.5, "wind": 10, "gust": 14, "wave_period": 9,
                                             "wave_dir": 1}, "live", None)}):
            ctx = pipeline.collect({"cities": ["Bergen"], "watchlist": ["sonatrach"],
                                    "alerts": {"oil": 0.1, "gas": 0.1, "equity": 0.1, "fx": 0.1}},
                                   news=news)
        self.assertGreaterEqual(len(ctx["kpis"]), 4)
        self.assertTrue(any(a["level"] == "info" for a in ctx["alerts"]))
        self.assertEqual(ctx["sea"][0]["state"], "rough")
        self.assertEqual(ctx["weather"][0]["daylight"], "8h09")
        brief.build_brief_html(ctx)


ESPN_SAMPLE = {"events": [
    {"date": "2026-10-31T17:30Z", "status": {"type": {"state": "pre", "shortDetail": "10/31 - 5:30 PM"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "score": "0", "team": {"displayName": "Arsenal"}},
         {"homeAway": "away", "score": "0", "team": {"displayName": "Chelsea"}}]}]},
    {"date": "2026-10-31T19:00Z", "status": {"type": {"state": "in", "shortDetail": "67'"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "score": "2", "team": {"displayName": "Brann"}},
         {"homeAway": "away", "score": "1", "team": {"displayName": "Viking"}}]}]},
    {"date": "2026-10-31T12:00Z", "status": {"type": {"state": "post", "shortDetail": "FT"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "score": "3", "team": {"displayName": "Nobody FC"}},
         {"homeAway": "away", "score": "3", "team": {"displayName": "Other FC"}}]}]},
    {"date": "2026-10-31T23:30Z", "status": {"type": {"state": "pre"}},
     "competitions": [{"competitors": [
         {"homeAway": "home", "team": {"displayName": "Late Home"}},
         {"homeAway": "away", "team": {"displayName": "Late Away"}}]}]},
    {"date": "2026-10-31T10:00Z", "competitions": [{"competitors": []}]},   # malformed: skipped
]}


class TestFootball(unittest.TestCase):
    def _prepared(self):
        ms = data.parse_espn_scoreboard(ESPN_SAMPLE, "Premier League", 8)
        return analysis.prepare_matches(ms, ["brann"])

    def test_fetch_league_requests_one_date_at_a_time(self):
        response = FakeResp({"events": []})
        with mock.patch.object(data.requests, "get", return_value=response) as get:
            matches = data._fetch_league("eng.1", "Premier League", 8,
                                         dt.date(2026, 10, 31), dt.date(2026, 11, 2))
        self.assertEqual(matches, [])
        self.assertEqual([call.kwargs["params"]["dates"] for call in get.call_args_list],
                         ["20261031", "20261101", "20261102"])

    def test_parse_skips_malformed(self):
        ms = data.parse_espn_scoreboard(ESPN_SAMPLE, "PL", 8)
        self.assertEqual(len(ms), 4)
        self.assertEqual((ms[0]["home"], ms[0]["away"], ms[0]["state"]), ("Arsenal", "Chelsea", "pre"))

    def test_oslo_time_and_dates(self):
        p = self._prepared()
        by = {m["home"]: m for m in p}
        self.assertEqual(by["Arsenal"]["time"], "18:30")        # 17:30Z -> CET (UTC+1 after 25 Oct)
        self.assertEqual(by["Late Home"]["time"], "00:30")      # crosses midnight in Oslo
        self.assertEqual(by["Late Home"]["date"], dt.date(2026, 11, 1))
        self.assertEqual(by["Arsenal"]["date"], dt.date(2026, 10, 31))

    def test_ranking_and_day_filter(self):
        p = self._prepared()
        top = analysis.key_matches(p, dt.date(2026, 10, 31), top_n=2)
        self.assertEqual({m["home"] for m in top}, {"Arsenal", "Brann"})   # big clubs + followed beat the rest
        self.assertEqual([m["home"] for m in top], ["Arsenal", "Brann"])   # ordered by kick-off
        self.assertTrue(next(m for m in p if m["home"] == "Brann")["followed"])
        self.assertNotIn("Late Home", [m["home"] for m in analysis.key_matches(p, dt.date(2026, 10, 31), 10)])

    def test_texts(self):
        by = {m["home"]: m for m in self._prepared()}
        self.assertEqual(analysis.score_text(by["Brann"]), "2–1")
        self.assertEqual(analysis.status_text(by["Brann"]), "LIVE 67'")
        self.assertEqual(analysis.score_text(by["Arsenal"]), "v")
        self.assertEqual(analysis.status_text(by["Arsenal"]), "Kick-off 18:30")
        self.assertEqual(analysis.status_text(by["Nobody FC"]), "FT")

    def test_football_matches_fallbacks(self):
        calls = {"n": 0}

        def fake(code, label, weight, d0, d1):
            calls["n"] += 1
            if code == "eng.1":
                return data.parse_espn_scoreboard(ESPN_SAMPLE, label, weight)
            raise RuntimeError("down")
        with mock.patch.object(data, "_fetch_league", side_effect=fake):
            r = data.football_matches()
        self.assertEqual(r.status, "live")
        self.assertEqual(len(r.data), 4)
        self.assertEqual(calls["n"], len(config.FOOTBALL_LEAGUES))
        # everything down -> eng.1 served from same-day snapshot, status cached
        with mock.patch.object(data, "_fetch_league", side_effect=RuntimeError("down")):
            r2 = data.football_matches()
        self.assertEqual((r2.status, len(r2.data)), ("cached", 4))

    def test_all_down_no_snapshot(self):
        with mock.patch.object(config, "FOOTBALL_LEAGUES", [("zzz.unknown", "X", 1)]), \
                mock.patch.object(data, "_fetch_league", side_effect=RuntimeError("down")):
            r = data.football_matches()
        self.assertEqual((r.status, r.data), ("none", None))

    def test_brief_includes_football(self):
        ctx = {"generated": "Sat", "football": [{"time": "18:30", "home": "Arsenal", "away": "Chelsea",
                                                "league": "Premier League", "status": "Kick-off 18:30",
                                                "score": "v", "followed": True}]}
        self.assertIn("Football today", brief.build_brief_html(ctx))
        self.assertIn("18:30 Arsenal v Chelsea", brief.to_text(ctx))


if __name__ == "__main__":
    unittest.main(verbosity=2)
