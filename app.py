"""
Daily Briefing Dashboard
Streamlit + Plotly (JavaScript charts) + live JS clocks. McKinsey-inspired theme (light/dark).

Run:  streamlit run app.py
"""
import datetime as dt
import html as _h
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from core import analysis, brief, calendar_events, config, data, notify, pipeline, storage

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

st.set_page_config(page_title="Daily Briefing", page_icon="◼", layout="wide")

# =============================================================================
# 1. SETTINGS (persisted to data/settings.json)
# =============================================================================
S = storage.load_settings(config.DEFAULT_SETTINGS)


def _opt(v, options, default):
    return v if v in options else default


REFRESH_OPTS = [0, 5, 10, 15, 30]
with st.sidebar:
    st.markdown("### Settings")
    theme = st.radio("Theme", ["light", "dark"], index=0 if S["theme"] == "light" else 1, horizontal=True)
    refresh_min = st.select_slider("Auto-refresh (minutes, 0 = off)", REFRESH_OPTS,
                                   value=_opt(S["refresh_min"], REFRESH_OPTS, 10))
    news_n = st.slider("Headlines per section", 5, 25, int(S["news_n"]))
    lookback = st.select_slider("Market lookback", list(config.LOOKBACK_DAYS),
                                value=_opt(S["lookback"], list(config.LOOKBACK_DAYS), "6mo"))
    cities_sel = st.multiselect("Weather cities", list(config.CITIES),
                                default=[c for c in S["cities"] if c in config.CITIES])
    peers_sel = st.multiselect("Peer companies", list(config.PEERS),
                               default=[p for p in S["peers"] if p in config.PEERS])
    wl_text = st.text_area("Watchlist keywords (one per line)", value="\n".join(S["watchlist"]), height=110)
    st.markdown("**Alert thresholds (1-day move, %)**")
    c1, c2 = st.columns(2)
    thr_oil = c1.number_input("Oil", 0.1, 20.0, float(S["alerts"]["oil"]), 0.1)
    thr_gas = c2.number_input("Gas", 0.1, 30.0, float(S["alerts"]["gas"]), 0.1)
    thr_eq = c1.number_input("Equity", 0.1, 20.0, float(S["alerts"]["equity"]), 0.1)
    thr_fx = c2.number_input("FX", 0.1, 10.0, float(S["alerts"]["fx"]), 0.1)
    followed_text = st.text_area("Followed football teams (one per line)",
                                 value="\n".join(S["followed_teams"]), height=90)
    football_top = st.slider("Key football matches per day", 5, 20, int(S["football_top"]))
    show_prayer = st.checkbox("Show prayer times (Weather tab)", value=bool(S["show_prayer"]))
    ai_enabled = st.checkbox("Enable AI summary (Claude)", value=bool(S["ai_enabled"]))
    ai_model = st.text_input("AI model", value=S["ai_model"])
    key_input = st.text_input("Anthropic API key (this session only)", type="password")
    ncs_url = st.text_input("NCS production CSV URL (optional)", value=S["ncs_url"],
                            help="Paste a CSV export link from Sodir Factpages, or upload a CSV in the NCS tab.")
    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()

NEW = {
    "theme": theme, "refresh_min": refresh_min, "news_n": news_n, "lookback": lookback,
    "cities": cities_sel, "peers": peers_sel,
    "watchlist": [w.strip() for w in wl_text.splitlines() if w.strip()],
    "alerts": {"oil": thr_oil, "gas": thr_gas, "equity": thr_eq, "fx": thr_fx},
    "followed_teams": [t.strip() for t in followed_text.splitlines() if t.strip()],
    "football_top": football_top,
    "show_prayer": show_prayer, "ai_enabled": ai_enabled, "ai_model": ai_model, "ncs_url": ncs_url,
}
if NEW != {k: S.get(k) for k in NEW}:
    storage.save_settings({**S, **NEW})

if refresh_min and st_autorefresh:
    st_autorefresh(interval=refresh_min * 60 * 1000, key="auto")

P = config.PALETTES[theme]

# =============================================================================
# 2. THEME CSS
# =============================================================================
_CSS = """
<style>
html, body, [class*="css"] { font-family: Arial, Helvetica, sans-serif; }
.stApp, .stApp p, .stApp label, .stApp li, .stApp span, .stApp div { color: __text__; }
.stApp { background: __bg__; }
[data-testid="stSidebar"] { background: __panel__; }
.stApp input, .stApp textarea { background: __card__ !important; color: __text__ !important; }
.block-container { padding-top: 1.2rem; max-width: 1500px; }
h1,h2,h3,h4 { font-family: Georgia, 'Times New Roman', serif !important; color: __text__ !important; letter-spacing:-0.3px; }
.banner { background:__banner__; padding:20px 26px; border-radius:4px; border-left:6px solid __accent2__; margin-bottom:12px; }
.banner h1, .banner p, .banner span { color:#FFFFFF !important; margin:0; }
.banner h1 { font-size:2rem; }
.banner p { color:__sky__ !important; margin-top:4px; font-size:0.92rem; }
.pill { display:inline-block; padding:5px 11px; margin:0 6px 6px 0; border-radius:3px; font-size:0.82rem; font-weight:bold; color:#fff !important; }
.pill a, .pill span { color:#fff !important; text-decoration:none; }
.kpi { background:__card__; border:1px solid __line__; border-top:3px solid __accent__; padding:11px 13px; border-radius:3px; height:100%; }
.kpi .l { font-size:0.7rem; text-transform:uppercase; letter-spacing:1px; color:__muted__ !important; }
.kpi .v { font-family:Georgia,serif; font-size:1.5rem; margin:2px 0; }
.kpi .d { font-size:0.8rem; font-weight:bold; }
.news { background:__card__; border:1px solid __line__; border-left:3px solid __accent2__; padding:9px 13px; margin-bottom:7px; border-radius:3px; }
.news a { text-decoration:none; font-weight:600; font-size:0.93rem; color:__text__ !important; }
.news a:hover { color:__accent__ !important; }
.news .m { color:__muted__ !important; font-size:0.74rem; margin-top:3px; }
.chip { display:inline-block; font-size:0.66rem; padding:1px 7px; margin-left:4px; border-radius:9px; border:1px solid __accent__; color:__accent__ !important; }
.card { background:__card__; border:1px solid __line__; border-radius:3px; padding:11px 14px; margin-bottom:8px; }
.card .c { font-family:Georgia,serif; font-size:1.05rem; }
.card .t { font-size:1.8rem; font-family:Georgia,serif; color:__accent__ !important; }
.card .s { color:__muted__ !important; font-size:0.8rem; }
.tbl { border-collapse:collapse; width:100%; font-size:0.85rem; }
.tbl th { text-align:left; color:__muted__ !important; font-weight:600; border-bottom:2px solid __accent__; padding:6px 8px; font-size:0.72rem; text-transform:uppercase; letter-spacing:.5px; }
.tbl td { border-bottom:1px solid __line__; padding:6px 8px; }
.dot { font-size:0.7rem; }
.stTabs [data-baseweb="tab"] { font-weight:bold; }
.stTabs [aria-selected="true"] { color:__accent__ !important; }
</style>
"""
_css = _CSS
for _k, _v in P.items():
    if isinstance(_v, str):
        _css = _css.replace(f"__{_k}__", _v)
st.markdown(_css, unsafe_allow_html=True)


# =============================================================================
# 3. CACHED DATA ACCESS (UI wrappers around core.data)
# =============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def c_news():
    return data.all_news()


@st.cache_data(ttl=600, show_spinner=False)
def c_fx(lb):
    return data.fx_frame(lb)


@st.cache_data(ttl=600, show_spinner=False)
def c_prices(lb):
    return data.price_series(config.ALL_SYMBOLS, lb)


@st.cache_data(ttl=21600, show_spinner=False)
def c_info(sym):
    return data.company_info(sym)


@st.cache_data(ttl=3600, show_spinner=False)
def c_curve():
    return data.brent_curve()


@st.cache_data(ttl=900, show_spinner=False)
def c_weather(cities):
    return data.weather_all({c: config.CITIES[c] for c in cities})


@st.cache_data(ttl=900, show_spinner=False)
def c_marine():
    return data.marine_all()


@st.cache_data(ttl=3600, show_spinner=False)
def c_prayer(day):
    return data.prayer_all()


@st.cache_data(ttl=1800, show_spinner=False)
def c_ncs_sync(url):
    return data.sync_ncs(url)


@st.cache_data(ttl=120, show_spinner=False)
def c_football():
    return data.football_matches()


@st.cache_data(ttl=600, show_spinner=False)
def c_ctx(settings_json):
    return pipeline.collect(json.loads(settings_json))


# =============================================================================
# 4. UI HELPERS
# =============================================================================
def esc(x):
    return _h.escape(str(x))


def badge(status, ts=None):
    col = {"live": P["up"], "cached": P["warn"]}.get(status, P["muted"])
    label = status if ts is None else f"{status} · {storage.fmt_local(ts)}"
    return f"<span class='dot' style='color:{col}'>● {esc(label)}</span>"


def heading(text, res=None, status=None, ts=None):
    b = ""
    if res is not None:
        b = " " + badge(res.status, res.ts)
    elif status is not None:
        b = " " + badge(status, ts)
    st.markdown(f"#### {esc(text)}{b}", unsafe_allow_html=True)


def pc(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    col = P["up"] if v >= 0 else P["down"]
    return f"<span style='color:{col};font-weight:bold'>{v:+.2f}%</span>"


def kpi(label, value, delta, sub=""):
    if delta is None:
        d = f"<span style='color:{P['muted']}'>{esc(sub)}</span>"
    else:
        col = P["up"] if delta >= 0 else P["down"]
        arrow = "▲" if delta >= 0 else "▼"
        d = f"<span style='color:{col}'>{arrow} {delta:+.2f}%</span> <span style='color:{P['muted']}'>{esc(sub)}</span>"
    return (f"<div class='kpi'><div class='l'>{esc(label)}</div><div class='v'>{esc(value)}</div>"
            f"<div class='d'>{d}</div></div>")


def html_table(rows):
    """rows: list of dicts whose values are already-safe HTML strings."""
    if not rows:
        return ""
    cols = list(rows[0])
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{r[c]}</td>" for c in cols) + "</tr>" for r in rows)
    return f"<table class='tbl'><tr>{head}</tr>{body}</table>"


def style_fig(fig, h=340, title=""):
    fig.update_layout(
        height=h + 70, title=dict(text=title, x=0, xanchor="left",
                                 font=dict(family="Georgia", size=16, color=P["text"])),
        colorway=P["colorway"], plot_bgcolor=P["card"], paper_bgcolor=P["card"],
        font=dict(family="Arial", size=12, color=P["text"]),
        margin=dict(l=10, r=10, t=60, b=80, autoexpand=True), hovermode="x unified",
        legend=dict(orientation="h", yref="container", y=0, yanchor="bottom",
                    x=0, xanchor="left"),
    )
    fig.update_xaxes(showgrid=False, linecolor=P["line"], automargin=True)
    fig.update_yaxes(gridcolor=P["line"], zeroline=False)
    return fig


def show(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def line_chart(series_map, title, h=340, width=2.4):
    fig = go.Figure()
    for name, s in series_map.items():
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode="lines", line=dict(width=width)))
    return style_fig(fig, h, title)


def render_news(items, limit):
    if not items:
        st.info("No headlines available (feed unreachable and no cached copy).")
        return
    dot = {"positive": P["up"], "negative": P["down"], "neutral": P["muted"]}
    for it in items[:limit]:
        chips = "".join(f"<span class='chip'>{esc(t)}</span>" for t in it.get("tags", [])[:2])
        hit = ""
        if it.get("hit"):
            hit = f"<span class='chip' style='background:{P['accent']};color:#fff !important'>★ {esc(', '.join(it['hit']))}</span>"
        st.markdown(
            f"<div class='news'><a href='{esc(it['link'])}' target='_blank'>{esc(it['title'])}</a>"
            f"<div class='m'><span style='color:{dot[it['sent']]}'>●</span> {esc(it['src'])} · {esc(it['ago'])} {chips}{hit}</div></div>",
            unsafe_allow_html=True)


def live_clocks():
    cards = "".join(
        f"<div class='c'><div class='n'>{n}</div><div class='t' data-tz='{tz}'>--:--:--</div>"
        f"<div class='d' data-dz='{tz}'></div></div>" for n, tz in config.CLOCKS)
    page = """
<style>
 body{margin:0;font-family:Arial,sans-serif;background:transparent}
 .w{display:grid;grid-template-columns:repeat(__N__,1fr);gap:8px}
 .c{background:__banner__;color:#fff;padding:10px 12px;border-radius:3px;border-bottom:3px solid __accent2__}
 .n{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:__sky__}
 .t{font-family:Georgia,serif;font-size:24px;margin:2px 0}
 .d{font-size:11px;color:__sky__}
 @media(max-width:900px){.w{grid-template-columns:repeat(2,1fr)}}
</style>
<div class="w">__CARDS__</div>
<script>
 function tick(){
  const now=new Date();
  document.querySelectorAll('[data-tz]').forEach(e=>{
    e.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:e.dataset.tz,hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
  });
  document.querySelectorAll('[data-dz]').forEach(e=>{
    e.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:e.dataset.dz,weekday:'short',day:'2-digit',month:'short'}).format(now);
  });
 }
 tick(); setInterval(tick,1000);
</script>"""
    page = (page.replace("__N__", str(len(config.CLOCKS))).replace("__CARDS__", cards)
            .replace("__banner__", P["banner"]).replace("__accent2__", P["accent2"])
            .replace("__sky__", P["sky"]))
    components.html(page, height=105)


def fx_fmt(label, v):
    return f"{v:.4f}" if label == "USD per EUR" else f"{v:.3f}"


# =============================================================================
# 5. LOAD DATA
# =============================================================================
news = c_news()
fx, fx_status = c_fx(lookback)
prices, px_status = c_prices(lookback)

enriched = {sec: analysis.enrich(res.data or []) for sec, res in news.items()}
all_items = [it for items in enriched.values() for it in items]
hits = analysis.watchlist_hits(all_items, NEW["watchlist"])

changes = {}
for key in ["NOK per EUR", "NOK per USD"]:
    if key in fx and fx[key].dropna().size > 1:
        changes[key] = analysis.pct_change_1d(fx[key].dropna())
for label, s in prices.items():
    changes[label] = analysis.pct_change_1d(s)
alerts = analysis.compute_alerts(changes, NEW["alerts"], hits)

oslo_today = pipeline._oslo_now().date()
fb = c_football()
fb_all = analysis.prepare_matches(fb.data or [], NEW["followed_teams"])

wx_cities = tuple(dict.fromkeys(["Bergen", "Algiers"] + list(cities_sel)))
wx = c_weather(wx_cities)

today_s = dt.date.today().isoformat()
ai_text = storage.load_snapshot(f"ai_{today_s}")[0] if ai_enabled else None
api_key = key_input or notify.get_secret("ANTHROPIC_API_KEY")

# =============================================================================
# 6. HEADER: banner, alerts, AI summary, clocks, daylight, KPIs
# =============================================================================
now_no = pipeline._oslo_now()
st.markdown(
    f"<div class='banner'><h1>Daily Briefing</h1><p>World · Sport · Upstream (NCS &amp; MENA) · FX · "
    f"Energy · Equities · Weather &nbsp;|&nbsp; {now_no:%A %d %B %Y}</p></div>", unsafe_allow_html=True)

if alerts:
    lvl_col = {"high": P["down"], "medium": P["warn"], "info": P["accent"]}
    pills = ""
    for a in alerts:
        inner = esc(a["text"])
        if a.get("link"):
            inner = f"<a href='{esc(a['link'])}' target='_blank'>{inner}</a>"
        pills += f"<span class='pill' style='background:{lvl_col[a['level']]}'>{inner}</span>"
    st.markdown(pills, unsafe_allow_html=True)
else:
    st.markdown(f"<span class='pill' style='background:{P['up']}'>No alerts — all moves within thresholds</span>",
                unsafe_allow_html=True)

if ai_enabled and ai_text:
    with st.expander("AI summary — what matters today", expanded=True):
        st.markdown(ai_text)

live_clocks()

sun_bits = []
for city in ("Bergen", "Algiers"):
    w = wx.get(city)
    dl = data.daylight(w.data) if w and w.data else None
    if dl:
        sun_bits.append(f"<b>{city}</b> ☀ {dl['sunrise']}–{dl['sunset']} ({dl['hours']} daylight)")
if sun_bits:
    st.markdown(f"<div class='card s' style='margin-top:8px'>{' &nbsp;·&nbsp; '.join(sun_bits)}</div>",
                unsafe_allow_html=True)

_upcoming = [m for m in analysis.key_matches(fb_all, oslo_today, NEW["football_top"]) if m["state"] != "post"]
if _upcoming:
    bits = []
    for m in _upcoming[:4]:
        tag = "🔴 LIVE" if m["state"] == "in" else m["time"]
        bits.append(f"<b>{esc(tag)}</b> {esc(m['home'])}–{esc(m['away'])}")
    st.markdown(f"<div class='card s' style='margin-top:8px'>⚽ Today (Oslo time): {' &nbsp;·&nbsp; '.join(bits)}</div>",
                unsafe_allow_html=True)

kcols = st.columns(6)
kitems = []
for key in ["NOK per EUR", "NOK per USD"]:
    if key in fx and fx[key].dropna().size > 1:
        kitems.append((key, fx_fmt(key, fx[key].dropna().iloc[-1]), changes.get(key), "1d"))
for label in ["Brent", "TTF gas", "Equinor", "Aker BP"]:
    s = prices.get(label)
    if s is not None and len(s) > 1:
        kitems.append((label, f"{s.iloc[-1]:,.2f}", changes.get(label), "1d"))
for col, item in zip(kcols, kitems):
    col.markdown(kpi(*item), unsafe_allow_html=True)
if not kitems:
    st.warning("Market data unavailable (offline or rate-limited) and no history stored yet.")

st.write("")
tabs = st.tabs(["Markets", "Energy", "News", "Football", "NCS", "Weather & Sea", "Calendar", "Brief & AI"])
t_mkt, t_en, t_news, t_fb, t_ncs, t_wx, t_cal, t_brief = tabs

# =============================================================================
# 7. MARKETS
# =============================================================================
with t_mkt:
    heading("FX — NOK vs EUR and USD", status=fx_status)
    if not fx.empty:
        base = fx[["NOK per EUR", "NOK per USD", "USD per EUR"]].dropna(how="all")
        a, b = st.columns(2)
        with a:
            show(line_chart({k: base[k].dropna() for k in ["NOK per EUR", "NOK per USD"]}, "NOK per EUR and per USD", 330, 2.6))
        with b:
            show(line_chart({k: base[k].dropna() / base[k].dropna().iloc[0] * 100 for k in base.columns},
                            "Rebased to 100", 330, 2.2))
    else:
        st.info("FX data unavailable.")

    heading("Equities — Equinor, Aker BP and peers (rebased to 100)", status=px_status)
    eq_names = [n for n in dict.fromkeys(["Equinor", "Aker BP"] + peers_sel) if n in prices]
    if eq_names:
        reb = analysis.rebase({n: prices[n] for n in eq_names})
        show(line_chart({c: reb[c].dropna() for c in reb.columns}, "Total return index (local currency)", 360))
        rows = []
        for n in eq_names:
            st_row = analysis.stats_table({n: prices[n]})
            if st_row.empty:
                continue
            r = st_row.iloc[0]
            info = (c_info(config.PEERS[n]).data or {}) if n in config.PEERS else {}
            dy, pe, mc = info.get("div_yield"), info.get("pe"), info.get("mcap")
            rows.append({
                "Company": esc(n), "Last": f"{r['Last']:,.2f} {esc(info.get('ccy') or '')}",
                "1d": pc(r["1d %"]), "1m": pc(r["1m %"]), "Period": pc(r["Period %"]),
                "Vol (ann.)": f"{r['Vol % (ann.)']:.1f}%",
                "Div yield": "–" if dy is None else f"{dy:.1f}%",
                "P/E": "–" if pe is None else f"{pe:.1f}",
                "Mkt cap (bn)": "–" if mc is None else f"{mc / 1e9:,.0f}",
            })
        st.markdown(html_table(rows), unsafe_allow_html=True)

        corr_series = {n: prices[n] for n in eq_names}
        if "Brent" in prices:
            corr_series["Brent"] = prices["Brent"]
        rets = pd.DataFrame({k: v.pct_change() for k, v in corr_series.items()}).dropna(how="all")
        if rets.shape[1] > 1 and len(rets) > 10:
            cm = rets.corr()
            fig = go.Figure(go.Heatmap(z=cm.values, x=list(cm.columns), y=list(cm.index), zmin=-1, zmax=1,
                                       colorscale=[[0, P["down"]], [0.5, P["card"]], [1, P["accent"]]],
                                       text=cm.round(2).values, texttemplate="%{text}"))
            fig.update_layout(hovermode="closest")
            show(style_fig(fig, 340, "Daily-return correlation"))
    else:
        st.info("Equity data unavailable (needs `yfinance` and network).")

# =============================================================================
# 8. ENERGY
# =============================================================================
with t_en:
    heading("Energy prices", status=px_status)
    ecols = st.columns(5)
    for col, label in zip(ecols, config.ENERGY):
        s = prices.get(label)
        if s is not None and len(s) > 1:
            col.markdown(kpi(label, f"{s.iloc[-1]:,.2f}", changes.get(label), "1d"), unsafe_allow_html=True)
        else:
            col.markdown(kpi(label, "n/a", None, "no data"), unsafe_allow_html=True)
    st.caption("TTF = EUR/MWh, Henry Hub = USD/MMBtu, Brent/WTI = USD/bbl. Carbon is an ETF proxy (KRBN), not the EUA futures price. NBP is not included (no free source).")

    a, b = st.columns(2)
    with a:
        oil = {k: prices[k] for k in ("Brent", "WTI") if k in prices}
        if oil:
            show(line_chart(oil, "Brent and WTI (USD/bbl)", 330))
    with b:
        if "Brent" in prices and "WTI" in prices:
            spr = analysis.spread(prices["Brent"], prices["WTI"])
            fig = go.Figure(go.Scatter(x=spr.index, y=spr.values, mode="lines", fill="tozeroy",
                                       line=dict(color=P["accent2"], width=2.4), name="Brent − WTI"))
            show(style_fig(fig, 330, "Brent − WTI spread (USD/bbl)"))

    a, b = st.columns(2)
    with a:
        if "TTF gas" in prices and "Henry Hub" in prices:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=prices["TTF gas"].index, y=prices["TTF gas"].values, name="TTF (EUR/MWh)",
                                     line=dict(width=2.4)))
            fig.add_trace(go.Scatter(x=prices["Henry Hub"].index, y=prices["Henry Hub"].values,
                                     name="Henry Hub (USD/MMBtu)", yaxis="y2", line=dict(width=2.4)))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
            show(style_fig(fig, 330, "European vs US gas"))
    with b:
        cp = prices.get("Carbon (KRBN ETF proxy)")
        if cp is not None:
            show(line_chart({"KRBN": cp}, "Carbon proxy (KRBN ETF, USD)", 330))

    curve = c_curve()
    heading("Brent futures curve (best effort)", res=curve)
    if curve.data and len(curve.data) >= 3:
        labels, vals = [c[0] for c in curve.data], [c[1] for c in curve.data]
        fig = go.Figure(go.Scatter(x=labels, y=vals, mode="lines+markers", line=dict(color=P["accent"], width=3),
                                   name="Settlement/last"))
        fig.update_layout(hovermode="closest")
        show(style_fig(fig, 320, "Brent forward curve (USD/bbl)"))
        front, back = vals[0], vals[-1]
        st.caption(f"Curve shape: {'backwardation' if front > back else 'contango'} "
                   f"({front:.1f} → {back:.1f} USD/bbl across {len(vals)} contracts).")
    else:
        st.info("Forward curve not available from the free source right now; it is retried hourly.")

# =============================================================================
# 9. NEWS
# =============================================================================
with t_news:
    sub = st.tabs(["Watchlist & topics", "Upstream NCS", "Upstream MENA", "Companies", "World", "Sport"])
    with sub[0]:
        st.markdown("#### Watchlist hits")
        st.caption("Keywords: " + (", ".join(NEW["watchlist"]) or "none — add some in the sidebar"))
        render_news(hits, 15) if hits else st.info("No headlines match your watchlist right now.")

        tc = analysis.topic_counts({s: v for s, v in enriched.items() if s not in ("World", "Sport")})
        if not tc.empty and tc.values.sum() > 0:
            fig = go.Figure()
            for sec in tc.columns:
                fig.add_trace(go.Bar(y=tc.index, x=tc[sec], name=sec, orientation="h"))
            fig.update_layout(barmode="stack", hovermode="closest")
            show(style_fig(fig, 360, "Upstream headlines by topic"))

        rows = {}
        for sec, items in enriched.items():
            rows[sec] = {s: sum(1 for i in items if i["sent"] == s) for s in ("positive", "neutral", "negative")}
        if rows:
            sent = pd.DataFrame(rows).T
            fig = go.Figure()
            colmap = {"positive": P["up"], "neutral": P["muted"], "negative": P["down"]}
            for s in ("positive", "neutral", "negative"):
                fig.add_trace(go.Bar(x=sent.index, y=sent[s], name=s, marker_color=colmap[s]))
            fig.update_layout(barmode="stack", hovermode="closest")
            show(style_fig(fig, 300, "Headline tone by section (keyword-based, indicative only)"))
    for tab, sec in zip(sub[1:], ["Upstream NCS", "Upstream MENA", "Companies", "World", "Sport"]):
        with tab:
            heading(sec, res=news[sec])
            items =[{**i, "hit": next((h["hit"] for h in hits if h["title"] == i["title"]), None)}
                     for i in enriched[sec]]
            render_news(items, news_n)

# =============================================================================
# 9b. FOOTBALL
# =============================================================================
def match_row(m):
    if m["state"] == "in":
        col = P["down"]
    elif m["followed"]:
        col = P["accent"]
    else:
        col = P["accent2"]
    star = f"<span class='chip' style='background:{P['accent']};color:#fff !important'>★ followed</span>" if m["followed"] else ""
    return (f"<div class='news' style='border-left-color:{col}'>"
            f"<b style='font-family:Georgia,serif;font-size:1.05rem'>{esc(m['time'])}</b> &nbsp; "
            f"{esc(m['home'])} <b>{esc(analysis.score_text(m))}</b> {esc(m['away'])} "
            f"<span class='chip'>{esc(m['league'])}</span>{star}"
            f"<div class='m' style='color:{col} !important'>{esc(analysis.status_text(m))}</div></div>")


with t_fb:
    heading("Football — key matches (kick-off in Oslo time)", res=fb)
    if fb.data is None:
        st.info("Fixtures unavailable (offline or the ESPN feed is down). Try Refresh now.")
    else:
        live_now = sorted([m for m in fb_all if m["state"] == "in"], key=lambda m: -m["importance"])
        if live_now:
            st.markdown("##### 🔴 Live now")
            for m in live_now[:8]:
                st.markdown(match_row(m), unsafe_allow_html=True)

        today_key = analysis.key_matches(fb_all, oslo_today, NEW["football_top"])
        st.markdown(f"##### Today — {oslo_today:%A %d %B}")
        if today_key:
            for m in today_key:
                st.markdown(match_row(m), unsafe_allow_html=True)
        else:
            st.info("No matches in the tracked competitions today.")

        tomorrow = oslo_today + dt.timedelta(days=1)
        tom_key = analysis.key_matches(fb_all, tomorrow, min(8, NEW["football_top"]))
        if tom_key:
            st.markdown(f"##### Tomorrow — {tomorrow:%A %d %B}")
            for m in tom_key:
                st.markdown(match_row(m), unsafe_allow_html=True)

        with st.expander("All of today's matches in tracked competitions"):
            rows = [{"Time": esc(m["time"]), "Match": f"{esc(m['home'])} {esc(analysis.score_text(m))} {esc(m['away'])}",
                     "Competition": esc(m["league"]), "Status": esc(analysis.status_text(m))}
                    for m in fb_all if m["date"] == oslo_today]
            st.markdown(html_table(rows) if rows else "No matches.", unsafe_allow_html=True)
        st.caption("Source: ESPN public scoreboard (unofficial). Competitions are set in core/config.py; "
                   "★ = teams you follow (sidebar). Scores refresh every ~2 minutes; use Refresh now for live updates.")

# =============================================================================
# 10. NCS
# =============================================================================
with t_ncs:
    sync_status = c_ncs_sync(ncs_url) if ncs_url else "none"
    heading("Norwegian Continental Shelf — monthly production", status=sync_status if ncs_url else None)
    st.markdown("Source: Sodir (Norwegian Offshore Directorate) — "
                "[Factpages](https://factpages.sodir.no/) · [Production statistics](https://www.sodir.no/en/facts/production/)")
    up = st.file_uploader("Upload a Sodir production CSV (monthly, year/month + oil/gas columns)", type=["csv"])
    if up is not None:
        try:
            parsed = data.ingest_ncs(pd.read_csv(up, sep=None, engine="python"))
            st.success(f"Loaded {len(parsed)} months into the local history database.")
        except Exception as e:
            st.error(f"Could not read that CSV: {e}")
    ncs = data.ncs_frame()
    if ncs.empty:
        st.info("No NCS production data yet. Upload a Sodir CSV above (or paste an export URL in the sidebar). "
                "Data is stored locally and persists between sessions.")
    else:
        last = ncs.iloc[-1]
        cols = st.columns(4)
        for col, key, lab in ((cols[0], "oil", "Oil (latest month)"), (cols[1], "gas", "Gas (latest month)")):
            if key in ncs and pd.notna(last.get(key)):
                yoy = None
                if len(ncs) > 12 and pd.notna(ncs[key].iloc[-13]) and ncs[key].iloc[-13]:
                    yoy = (ncs[key].iloc[-1] / ncs[key].iloc[-13] - 1) * 100
                col.markdown(kpi(lab, f"{last[key]:,.2f}", yoy, "YoY"), unsafe_allow_html=True)
        cols[2].markdown(kpi("Latest month", ncs.index[-1].strftime("%b %Y"), None, "in dataset"), unsafe_allow_html=True)
        for key, title, colr in (("oil", "Oil production (as reported in file, e.g. mill Sm³)", P["accent"]),
                                 ("gas", "Gas production (as reported in file, e.g. bill Sm³)", P["accent2"])):
            if key in ncs and ncs[key].notna().any():
                s = ncs[key].dropna()
                fig = go.Figure()
                fig.add_trace(go.Bar(x=s.index, y=s.values, name="Monthly", marker_color=colr, opacity=0.55))
                fig.add_trace(go.Scatter(x=s.index, y=s.rolling(12).mean(), name="12-month avg",
                                         line=dict(color=P["text"], width=2.6)))
                show(style_fig(fig, 320, title))

# =============================================================================
# 11. WEATHER & SEA
# =============================================================================
with t_wx:
    heading("City weather and daylight")
    grid = st.columns(3)
    shown = 0
    for city in cities_sel:
        res = wx.get(city)
        if not res or not res.data:
            continue
        w = res.data
        cur, dl = w["current"], data.daylight(w)
        dl_txt = f" · ☀ {dl['sunrise']}–{dl['sunset']} ({dl['hours']})" if dl else ""
        grid[shown % 3].markdown(
            f"<div class='card'><div class='c'>{esc(city)} {badge(res.status, res.ts)}</div>"
            f"<div class='t'>{cur['temperature_2m']:.0f}°C</div>"
            f"<div class='s'>{esc(data.describe_wmo(cur.get('weather_code')))} · feels {cur['apparent_temperature']:.0f}° · "
            f"wind {cur['wind_speed_10m']:.0f} km/h · precip {cur['precipitation']} mm{dl_txt}</div></div>",
            unsafe_allow_html=True)
        shown += 1
    if not shown:
        st.info("No weather data available (offline and nothing cached).")

    bergen = wx.get("Bergen")
    if bergen and bergen.data:
        d = pd.DataFrame(bergen.data["daily"])
        fig = go.Figure()
        fig.add_bar(x=d["time"], y=d["precipitation_sum"], name="Rain (mm)", marker_color=P["sky"], yaxis="y2")
        fig.add_scatter(x=d["time"], y=d["temperature_2m_max"], name="Max °C", line=dict(color=P["accent"], width=3))
        fig.add_scatter(x=d["time"], y=d["temperature_2m_min"], name="Min °C", line=dict(color=P["accent2"], width=3))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, title="mm"))
        show(style_fig(fig, 320, "Bergen — 5-day outlook"))

    sea = c_marine()
    heading("Offshore sea state (approximate field areas)")
    state_col = {"calm": P["up"], "moderate": P["warn"], "rough": P["down"], "n/a": P["muted"]}
    scols = st.columns(len(config.OFFSHORE))
    for col, (name, res) in zip(scols, sea.items()):
        m = res.data
        if not m:
            col.markdown(kpi(name, "n/a", None, "no data"), unsafe_allow_html=True)
            continue
        hs = m.get("wave_height")
        stt = data.sea_state(hs)
        col.markdown(
            f"<div class='kpi' style='border-top-color:{state_col[stt]}'><div class='l'>{esc(name)}</div>"
            f"<div class='v'>{'n/a' if hs is None else f'{hs:.1f} m'}</div>"
            f"<div class='d' style='color:{state_col[stt]}'>{esc(stt)}</div>"
            f"<div class='s'>wind {m.get('wind') if m.get('wind') is not None else 'n/a'} m/s · "
            f"gust {m.get('gust') if m.get('gust') is not None else 'n/a'} m/s · "
            f"T {m.get('wave_period') if m.get('wave_period') is not None else 'n/a'} s</div></div>",
            unsafe_allow_html=True)
    st.caption("Significant wave height (Hs) from Open-Meteo Marine. Generic indicator only (calm <2.5 m, rough ≥4 m) — not an operational limit.")

    if show_prayer:
        pr = c_prayer(today_s)
        heading("Prayer times")
        pcols = st.columns(len(pr))
        for col, (label, res) in zip(pcols, pr.items()):
            if not res.data:
                col.markdown(kpi(label, "n/a", None, "no data"), unsafe_allow_html=True)
                continue
            line = " · ".join(f"{k} {v}" for k, v in res.data.items())
            col.markdown(f"<div class='card'><div class='c'>{esc(label)} {badge(res.status, res.ts)}</div>"
                         f"<div class='s'>{esc(line)}</div></div>", unsafe_allow_html=True)

# =============================================================================
# 12. CALENDAR
# =============================================================================
with t_cal:
    nxt = calendar_events.upcoming(days=7)
    heading("Next 7 days")
    if nxt:
        for e in nxt:
            days = (e["date"] - dt.date.today()).days
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
            st.markdown(f"<div class='news'><b>{e['date']:%a %d %b}</b> ({when}) — {esc(e['title'])} "
                        f"<span class='chip'>{esc(e['category'])}</span></div>", unsafe_allow_html=True)
    else:
        st.info("Nothing scheduled in the next 7 days.")

    heading("Upcoming")
    rows = []
    for e in calendar_events.upcoming()[:25]:
        src = f"<a href='{esc(e['source'])}' target='_blank'>source</a>" if e.get("source") else "your event"
        rows.append({"Date": f"{e['date']:%a %d %b %Y}", "Event": esc(e["title"]),
                     "Category": esc(e["category"]), "Link": src})
    st.markdown(html_table(rows), unsafe_allow_html=True)
    st.caption("Bundled: Norges Bank decisions and Equinor results (checked against the official calendars). "
               "OPEC+ meetings are not bundled — add them below when announced.")
    with st.form("add_event", clear_on_submit=True):
        d = st.date_input("Date")
        t = st.text_input("Title")
        cat = st.selectbox("Category", calendar_events.CATEGORIES)
        if st.form_submit_button("Add event") and t.strip():
            calendar_events.add_user_event(d, t, cat)
            st.success("Added. It appears in the lists on the next refresh.")

# =============================================================================
# 13. BRIEF & AI
# =============================================================================
with t_brief:
    heading("Morning brief (printable) and AI summary")
    ctx = c_ctx(json.dumps({k: NEW[k] for k in ("lookback", "cities", "watchlist", "alerts")}, sort_keys=True))

    if ai_enabled:
        if not api_key:
            st.info("Add your Anthropic API key in the sidebar (session only) or set ANTHROPIC_API_KEY as an env var/secret.")
        elif st.button("Generate / refresh AI summary"):
            with st.spinner("Writing summary…"):
                try:
                    ai_text = brief.ai_summary(ctx, api_key, NEW["ai_model"])
                    storage.save_snapshot(f"ai_{today_s}", ai_text)
                except Exception as e:
                    st.error(f"AI summary failed: {e}")
        if ai_text:
            st.markdown(ai_text)
    else:
        st.caption("Enable “AI summary” in the sidebar to add a Claude-written paragraph to the brief.")

    brief_html = brief.build_brief_html(ctx, theme, ai_text if ai_enabled else None)
    components.html(brief_html, height=820, scrolling=True)
    st.download_button("Download brief (HTML — open and print to PDF)", brief_html,
                       file_name=f"morning_brief_{today_s}.html", mime="text/html")

    heading("Digest delivery")
    sent_any = False
    if notify.email_configured():
        sent_any = True
        if st.button("Email the brief now"):
            try:
                notify.send_email(f"Morning brief {today_s}", brief_html, brief.to_text(ctx, ai_text))
                st.success("Email sent.")
            except Exception as e:
                st.error(f"Email failed: {e}")
    if notify.telegram_configured():
        sent_any = True
        if st.button("Send to Telegram now"):
            try:
                notify.send_telegram(brief.to_text(ctx, ai_text), brief_html, f"morning_brief_{today_s}.html")
                st.success("Sent to Telegram.")
            except Exception as e:
                st.error(f"Telegram failed: {e}")
    if not sent_any:
        st.caption("Set SMTP_* and/or TELEGRAM_* secrets to enable sending. For an automatic 07:00 digest, "
                   "use digest.py with the included GitHub Actions workflow (see README).")

st.caption("Sources: BBC, Al Jazeera, ESPN, Google News RSS, ECB via Frankfurter, Yahoo Finance, Open-Meteo, Aladhan, Sodir. "
           "Data is delayed and may be cached when a feed is down (● cached). Not investment advice.")
