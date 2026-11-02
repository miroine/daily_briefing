"""Morning brief: printable HTML, plain-text digest, and optional Claude-written summary."""
import html as h
from typing import Optional

from . import config

_CSS = """
body{font-family:Arial,Helvetica,sans-serif;color:__text__;background:__bg__;margin:0;padding:24px;max-width:900px;margin:auto}
h1,h2{font-family:Georgia,'Times New Roman',serif;color:__text__;margin:0}
.banner{background:__banner__;color:#fff;padding:18px 22px;border-left:6px solid __accent2__;margin-bottom:16px}
.banner h1{color:#fff;font-size:26px}.banner p{margin:4px 0 0;color:__sky__;font-size:13px}
h2{font-size:17px;margin:20px 0 8px;padding-bottom:4px;border-bottom:2px solid __accent__}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.k{border:1px solid __line__;border-top:3px solid __accent__;padding:8px 10px;background:__card__}
.k .l{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:__muted__}
.k .v{font-family:Georgia,serif;font-size:20px}.up{color:__up__;font-weight:bold}.down{color:__down__;font-weight:bold}
ul{margin:6px 0;padding-left:18px}li{margin:4px 0;font-size:13px;line-height:1.35}
.src{color:__muted__;font-size:11px}.a-high{color:__down__;font-weight:bold}.a-medium{color:__warn__;font-weight:bold}
.ai{background:__panel__;border-left:4px solid __accent__;padding:10px 14px;font-size:13px;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid __line__;padding:5px 6px;text-align:left}
.btn{float:right;background:__accent__;color:#fff;border:0;padding:8px 14px;cursor:pointer;font-size:12px}
a{color:__accent__;text-decoration:none}.foot{margin-top:22px;font-size:10px;color:__muted__}
@media print{.btn{display:none}body{padding:0}h2{break-after:avoid}li,.k{break-inside:avoid}}
@media(max-width:600px){.kpis{grid-template-columns:repeat(2,1fr)}}
"""


def _css(theme: str) -> str:
    p = config.PALETTES["light"]   # brief is always print-friendly (light)
    css = _CSS
    for k, v in p.items():
        if isinstance(v, str):
            css = css.replace(f"__{k}__", v)
    return css


def _e(x) -> str:
    return h.escape(str(x))


def build_brief_html(ctx: dict, theme: str = "light", ai: Optional[str] = None) -> str:
    ai = ai or ctx.get("ai")
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>Morning brief</title>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<style>{_css(theme)}</style></head><body>",
             "<button class='btn' onclick='window.print()'>Print / Save as PDF</button>",
             f"<div class='banner'><h1>Morning Brief</h1><p>{_e(ctx.get('generated', ''))}</p></div>"]

    if ai:
        parts.append(f"<h2>Summary</h2><div class='ai'>{_e(ai)}</div>")

    if ctx.get("alerts"):
        parts.append("<h2>Alerts</h2><ul>")
        for a in ctx["alerts"]:
            parts.append(f"<li class='a-{_e(a['level'])}'>{_e(a['text'])}</li>")
        parts.append("</ul>")

    if ctx.get("kpis"):
        parts.append("<h2>Markets</h2><div class='kpis'>")
        for k in ctx["kpis"]:
            d = k.get("delta")
            dh = "" if d is None else (f"<div class='{'up' if d >= 0 else 'down'}'>"
                                       f"{'▲' if d >= 0 else '▼'} {d:+.2f}%</div>")
            parts.append(f"<div class='k'><div class='l'>{_e(k['label'])}</div>"
                         f"<div class='v'>{_e(k['value'])}</div>{dh}</div>")
        parts.append("</div>")

    for sec, items in (ctx.get("sections") or {}).items():
        if not items:
            continue
        parts.append(f"<h2>{_e(sec)}</h2><ul>")
        for it in items:
            link = it.get("link") or "#"
            parts.append(f"<li><a href='{_e(link)}'>{_e(it['title'])}</a> "
                         f"<span class='src'>{_e(it.get('src', ''))} · {_e(it.get('ago', ''))}</span></li>")
        parts.append("</ul>")

    if ctx.get("football"):
        parts.append("<h2>Football today (Oslo time)</h2><table><tr><th>Time</th><th>Match</th>"
                     "<th>Competition</th><th>Status</th></tr>")
        for m in ctx["football"]:
            star = " ★" if m.get("followed") else ""
            parts.append(f"<tr><td><b>{_e(m['time'])}</b></td>"
                         f"<td>{_e(m['home'])} {_e(m['score'])} {_e(m['away'])}{star}</td>"
                         f"<td>{_e(m['league'])}</td><td>{_e(m['status'])}</td></tr>")
        parts.append("</table>")

    if ctx.get("weather"):
        parts.append("<h2>Weather</h2><table><tr><th>City</th><th>Now</th><th>Conditions</th>"
                     "<th>Sunrise</th><th>Sunset</th><th>Daylight</th></tr>")
        for w in ctx["weather"]:
            parts.append(f"<tr><td>{_e(w['city'])}</td><td>{_e(w['temp'])}</td><td>{_e(w['desc'])}</td>"
                         f"<td>{_e(w.get('sunrise', ''))}</td><td>{_e(w.get('sunset', ''))}</td>"
                         f"<td>{_e(w.get('daylight', ''))}</td></tr>")
        parts.append("</table>")

    if ctx.get("sea"):
        parts.append("<h2>Sea state (offshore areas)</h2><table><tr><th>Area</th><th>Hs (m)</th>"
                     "<th>State</th><th>Wind (m/s)</th></tr>")
        for s in ctx["sea"]:
            parts.append(f"<tr><td>{_e(s['name'])}</td><td>{_e(s['hs'])}</td><td>{_e(s['state'])}</td>"
                         f"<td>{_e(s['wind'])}</td></tr>")
        parts.append("</table>")

    if ctx.get("events"):
        parts.append("<h2>Coming up</h2><ul>")
        for e in ctx["events"]:
            parts.append(f"<li><b>{_e(e['date'])}</b> — {_e(e['title'])} "
                         f"<span class='src'>{_e(e.get('category', ''))}</span></li>")
        parts.append("</ul>")

    parts.append("<div class='foot'>Sources: BBC, Al Jazeera, ESPN, Google News RSS, ECB via Frankfurter, "
                 "Yahoo Finance, Open-Meteo. Data may be delayed; not investment advice.</div></body></html>")
    return "".join(parts)


def to_text(ctx: dict, ai: Optional[str] = None, limit: int = 3800) -> str:
    """Plain-text digest (Telegram-sized)."""
    ai = ai or ctx.get("ai")
    L = [f"MORNING BRIEF — {ctx.get('generated', '')}", ""]
    if ai:
        L += [ai.strip(), ""]
    if ctx.get("alerts"):
        L.append("ALERTS")
        L += [f"• {a['text']}" for a in ctx["alerts"]]
        L.append("")
    if ctx.get("kpis"):
        L.append("MARKETS")
        for k in ctx["kpis"]:
            d = k.get("delta")
            L.append(f"• {k['label']}: {k['value']}" + ("" if d is None else f" ({d:+.2f}%)"))
        L.append("")
    for sec, items in (ctx.get("sections") or {}).items():
        if items:
            L.append(sec.upper())
            L += [f"• {it['title']}" for it in items[:4]]
            L.append("")
    if ctx.get("football"):
        L.append("FOOTBALL TODAY (Oslo time)")
        L += [f"• {m['time']} {m['home']} {m['score']} {m['away']} ({m['league']})" for m in ctx["football"]]
        L.append("")
    if ctx.get("events"):
        L.append("COMING UP")
        L += [f"• {e['date']} {e['title']}" for e in ctx["events"][:5]]
    text = "\n".join(L).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _prompt_data(ctx: dict) -> str:
    L = [f"Date: {ctx.get('generated', '')}"]
    L.append("Markets: " + "; ".join(
        f"{k['label']} {k['value']}" + ("" if k.get('delta') is None else f" ({k['delta']:+.2f}% 1d)")
        for k in ctx.get("kpis", [])))
    if ctx.get("alerts"):
        L.append("Alerts: " + " | ".join(a["text"] for a in ctx["alerts"]))
    for sec, items in (ctx.get("sections") or {}).items():
        L.append(f"{sec} headlines:")
        L += [f"- {it['title']} ({it.get('src', '')}, {it.get('ago', '')})" for it in items[:6]]
    if ctx.get("football"):
        L.append("Football today (Oslo time): " + "; ".join(
            f"{m['time']} {m['home']} v {m['away']} ({m['league']})" for m in ctx["football"]))
    if ctx.get("events"):
        L.append("Upcoming: " + "; ".join(f"{e['date']} {e['title']}" for e in ctx["events"][:6]))
    return "\n".join(L)


def ai_summary(ctx: dict, api_key: str, model: str = "claude-sonnet-5-5") -> str:
    """Claude-written 'what changed in the last 24h'. Uses only the supplied data."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        "You write a concise morning briefing for an oil & gas professional in Norway. "
        "Use ONLY the data below; never invent facts, numbers or sources. If a section has no data, say so.\n\n"
        "Format (plain text, no markdown headers, max ~180 words):\n"
        "What matters today: 3 short bullets.\n"
        "Then one line each for: Markets, Upstream NCS, Upstream MENA, World.\n\n"
        f"DATA:\n{_prompt_data(ctx)}"
    )
    msg = client.messages.create(model=model, max_tokens=700,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
