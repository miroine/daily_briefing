# Daily Briefing Dashboard

Streamlit + Plotly (JavaScript charts) + live JS world clocks, McKinsey-style light/dark theme.

Chart legends sit below the plot, with expandable margins for wrapped labels on narrower screens.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Tabs
| Tab | What you get |
|---|---|
| Markets | NOK/EUR, NOK/USD, EUR/USD; Equinor, Aker BP + peers (Vår Energi, Shell, BP, TotalEnergies): rebased chart, stats, dividend yield, P/E, correlation heatmap |
| Energy | Brent, WTI, Brent−WTI spread, TTF, Henry Hub, carbon (ETF proxy), Brent forward curve (best effort) |
| News | Watchlist hits, topic chart, tone chart, then NCS / MENA / Companies / World / Sport |
| Football | Today's key matches with kick-off in Oslo time, live scores/results, tomorrow's picks, full list of tracked competitions. Teams you follow (sidebar) are starred and ranked first |
| NCS | Monthly oil & gas production from a Sodir CSV (upload or URL), 12-month average, YoY |
| Weather & Sea | Cities + daylight, Bergen 5-day, offshore sea state (Hs, wind), prayer times (toggle) |
| Calendar | Next 7 days + upcoming: Norges Bank, Equinor results, plus your own events |
| Brief & AI | Printable brief (HTML → PDF), Claude summary, send by email/Telegram |

Always on top: alert strip (price moves over your thresholds + watchlist headlines), live clocks, Bergen/Algiers daylight, KPI row.

## Reliability
- Every panel keeps a last-good snapshot (`data/snapshots`). If a feed fails you see old data marked `● cached` instead of a blank panel.
- Price and FX history accumulate in SQLite (`data/dashboard.db`); only new days are downloaded, so the app opens fast and history grows beyond the lookback window.
- Settings (theme, cities, watchlist, thresholds) persist in `data/settings.json`.

## Secrets (all optional)
Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, or set the same names as environment variables.
`ANTHROPIC_API_KEY` enables the AI summary; `SMTP_*` / `TELEGRAM_*` enable delivery.

## Automatic 07:00 digest
```bash
python digest.py --dry-run     # builds out/brief.html only
python digest.py --ai          # sends via configured channels, with Claude summary
```
Schedule it with the included GitHub Actions workflow (`.github/workflows/digest.yml`): add the secrets in the repo settings. The cron is 06:00 UTC (07:00 Oslo in winter; change to `0 5` in summer). Alternatively use cron/Task Scheduler locally.

## Notes and limits
- NCS: Sodir does not offer a documented stable CSV URL I could verify. Upload a Factpages export in the NCS tab (or paste its URL in the sidebar); the parser auto-detects year/month and oil/gas columns.
- Calendar: Norges Bank and Equinor dates were taken from their official calendars. OPEC+ dates are not bundled; add them in the Calendar tab. Extra events can also be edited in `events.json`.
- Brent curve and carbon use free Yahoo symbols and can be missing or delayed. NBP gas is not included.
- Headline tags and tone are keyword-based and indicative only.
- Sea-state colours are a generic indicator, not an operational limit.
- Prayer times use the Aladhan API (Bergen: MWL method, Algiers: Algerian ministry method); turn off in the sidebar if not needed.

## Football notes
- Source: ESPN's public scoreboard JSON (unofficial, no key). The scoreboard accepts one date per request, so the app fetches each day in its yesterday-to-tomorrow window separately. Competitions are listed in `core/config.py` (`FOOTBALL_LEAGUES`); out-of-season or unknown codes are skipped silently. Add or remove leagues there.
- "Key" matches are ranked by competition weight, +10 if a followed team plays, +2/+4 if one/both clubs are in `BIG_TEAMS`. Defaults for followed teams are Norway, Algeria and Brann; change them in the sidebar.
- Kick-off times are converted to Europe/Oslo. Scores cache for ~2 minutes; press "Refresh now" for the latest.
- Today's key matches also appear in the header strip, the morning brief and the Telegram/email digest.

## Customise
`core/config.py`: clocks, cities, offshore points, symbols, feeds, defaults. `core/analysis.py`: topic keywords and tone words.

## Deploy
Streamlit Community Cloud: push to GitHub, point to `app.py`, add secrets in the app settings. Note that its disk is ephemeral, so stored history resets on restart; for persistent history run it on your own machine/VM.
