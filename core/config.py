"""Static configuration: palettes, locations, symbols, feeds, defaults. Edit freely."""
from urllib.parse import quote

PALETTES = {
    "light": {
        "bg": "#FFFFFF", "panel": "#F3F6FA", "card": "#FFFFFF", "text": "#051C2C",
        "muted": "#6B7785", "line": "#DDE3EA", "accent": "#2251FF", "accent2": "#00A9F4",
        "banner": "#051C2C", "banner_text": "#FFFFFF", "sky": "#CAD9FE",
        "up": "#0E9F6E", "down": "#C8102E", "warn": "#B7791F",
        "colorway": ["#2251FF", "#00A9F4", "#051C2C", "#7A8CA3", "#1F40E6", "#0E9F6E"],
    },
    "dark": {
        "bg": "#051C2C", "panel": "#0A2A40", "card": "#0B2F47", "text": "#E8EEF4",
        "muted": "#9FB3C8", "line": "#1D4560", "accent": "#4D7CFF", "accent2": "#00A9F4",
        "banner": "#020E17", "banner_text": "#FFFFFF", "sky": "#CAD9FE",
        "up": "#2DD4A0", "down": "#FF6B7A", "warn": "#F5B94A",
        "colorway": ["#4D7CFF", "#00A9F4", "#CAD9FE", "#9FB3C8", "#2DD4A0", "#F5B94A"],
    },
}

CLOCKS = [
    ("Bergen / Oslo", "Europe/Oslo"), ("Algiers", "Africa/Algiers"),
    ("Calgary", "America/Edmonton"), ("Toronto", "America/Toronto"),
    ("London", "Europe/London"), ("Dubai", "Asia/Dubai"),
    ("Houston", "America/Chicago"), ("Singapore", "Asia/Singapore"),
]

CITIES = {  # name: (lat, lon)
    "Bergen": (60.39, 5.32), "Oslo": (59.91, 10.75), "Stavanger": (58.97, 5.73),
    "Algiers": (36.75, 3.06), "Cherchell": (36.61, 2.19), "Calgary": (51.05, -114.07),
    "Toronto": (43.65, -79.38), "London": (51.51, -0.13), "Dubai": (25.20, 55.27),
    "New York": (40.71, -74.01),
}

# Approximate field-area positions for sea-state (not exact platform coordinates)
OFFSHORE = {
    "Sleipner (North Sea)": (58.37, 1.91),
    "Johan Sverdrup (North Sea)": (58.85, 2.55),
    "Troll (North Sea)": (60.64, 3.72),
    "Åsgard (Norwegian Sea)": (65.10, 6.78),
    "Snøhvit (Barents Sea)": (71.50, 21.10),
}

# Prayer-time cities: label -> (city, country, Aladhan method). 3 = MWL, 19 = Algeria
PRAYER_CITIES = {"Bergen": ("Bergen", "Norway", 3), "Algiers": ("Algiers", "Algeria", 19)}

ENERGY = {
    "Brent": "BZ=F", "WTI": "CL=F", "TTF gas": "TTF=F", "Henry Hub": "NG=F",
    "Carbon (KRBN ETF proxy)": "KRBN",
}
PEERS = {
    "Equinor": "EQNR.OL", "Aker BP": "AKRBP.OL", "Vår Energi": "VAR.OL",
    "Shell": "SHEL.L", "BP": "BP.L", "TotalEnergies": "TTE.PA",
}
ALL_SYMBOLS = {**ENERGY, **PEERS}

# Which alert threshold applies to which series
ALERT_GROUP = {
    "Brent": "oil", "WTI": "oil", "TTF gas": "gas", "Henry Hub": "gas",
    "Equinor": "equity", "Aker BP": "equity", "Vår Energi": "equity",
    "NOK per EUR": "fx", "NOK per USD": "fx",
}

LOOKBACK_DAYS = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731}


def gnews(q: str, when: str = "2d") -> str:
    return ("https://news.google.com/rss/search?q=" + quote(f"{q} when:{when}")
            + "&hl=en&gl=NO&ceid=NO:en")


FEEDS = {
    "World": ["https://feeds.bbci.co.uk/news/world/rss.xml",
              "https://www.aljazeera.com/xml/rss/all.xml"],
    "Sport": ["https://feeds.bbci.co.uk/sport/rss.xml",
              "https://www.espn.com/espn/rss/news"],
    "Upstream NCS": [
        gnews('Norwegian continental shelf OR "NCS" oil gas OR Sleipner OR Johan Sverdrup OR Troll'),
        gnews("Norway offshore oil gas licence OR PDO OR discovery"),
    ],
    "Upstream MENA": [
        gnews("Algeria Sonatrach oil gas"),
        gnews("Middle East OR OPEC upstream oil gas production"),
        gnews("Libya OR Egypt OR Saudi Aramco OR ADNOC upstream"),
    ],
    "Companies": [
        gnews("Equinor"), gnews('"Aker BP"'),
        gnews("Vår Energi OR DNO OR Aker Solutions OR Subsea7 OR TechnipFMC"),
    ],
}
SECTIONS = list(FEEDS)

WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain",
       65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers",
       81: "Showers", 82: "Violent showers", 95: "Thunderstorm", 96: "Thunderstorm",
       99: "Thunderstorm"}

# ESPN public scoreboard league codes (unofficial API, no key). (code, label, importance weight)
# Unknown/out-of-season codes simply return nothing and are skipped.
FOOTBALL_LEAGUES = [
    ("uefa.champions", "Champions League", 10),
    ("fifa.world", "World Cup", 10),
    ("uefa.euro", "Euro", 10),
    ("eng.1", "Premier League", 8),
    ("uefa.europa", "Europa League", 7),
    ("uefa.nations", "Nations League", 7),
    ("caf.nations", "Africa Cup of Nations", 7),
    ("esp.1", "La Liga", 7),
    ("ita.1", "Serie A", 6),
    ("ger.1", "Bundesliga", 6),
    ("fra.1", "Ligue 1", 5),
    ("uefa.europa.conf", "Conference League", 5),
    ("nor.1", "Eliteserien", 5),
    ("fifa.friendly", "International friendly", 4),
]
BIG_TEAMS = [
    "Manchester City", "Manchester United", "Liverpool", "Arsenal", "Chelsea", "Tottenham",
    "Real Madrid", "Barcelona", "Atlético", "Atletico", "Bayern", "Borussia Dortmund",
    "Bayer Leverkusen", "Paris Saint-Germain", "Juventus", "Inter Milan", "AC Milan", "Napoli",
    "Roma", "Benfica", "Porto", "Ajax",
]

DEFAULT_SETTINGS = {
    "followed_teams": ["Norway", "Algeria", "Brann"],
    "football_top": 10,
    "theme": "light",
    "refresh_min": 10,
    "news_n": 10,
    "lookback": "6mo",
    "cities": ["Bergen", "Oslo", "Stavanger", "Algiers", "Calgary", "Toronto"],
    "peers": ["Equinor", "Aker BP", "Vår Energi", "Shell", "BP", "TotalEnergies"],
    "watchlist": ["Sonatrach", "Johan Sverdrup", "Troll", "Hammerfest", "CCS", "geothermal"],
    "alerts": {"oil": 2.0, "gas": 5.0, "equity": 3.0, "fx": 0.8},
    "show_prayer": True,
    "ai_enabled": False,
    "ai_model": "claude-sonnet-5-5",
    "ncs_url": "",
}
