"""The 30 NBA teams: conference, division, arena location, time zone and colours.

Keyed by ESPN's abbreviation. ESPN sometimes uses alternative abbreviations
(GSW, NOP, NYK, SAS, UTA, WAS); ALIASES maps them back.
"""
from math import radians, sin, cos, asin, sqrt

# abbr: (espn_id, full name, short, conf, division, lat, lon, utc offset (standard), primary, secondary)
TEAMS = {
    "ATL": (1, "Atlanta Hawks", "Hawks", "East", "Southeast", 33.757, -84.396, -5, "#E03A3E", "#C1D32F"),
    "BOS": (2, "Boston Celtics", "Celtics", "East", "Atlantic", 42.366, -71.062, -5, "#007A33", "#BA9653"),
    "BKN": (17, "Brooklyn Nets", "Nets", "East", "Atlantic", 40.683, -73.975, -5, "#000000", "#777D84"),
    "CHA": (30, "Charlotte Hornets", "Hornets", "East", "Southeast", 35.225, -80.839, -5, "#1D1160", "#00788C"),
    "CHI": (4, "Chicago Bulls", "Bulls", "East", "Central", 41.881, -87.674, -6, "#CE1141", "#000000"),
    "CLE": (5, "Cleveland Cavaliers", "Cavaliers", "East", "Central", 41.496, -81.688, -5, "#860038", "#FDBB30"),
    "DAL": (6, "Dallas Mavericks", "Mavericks", "West", "Southwest", 32.790, -96.810, -6, "#00538C", "#B8C4CA"),
    "DEN": (7, "Denver Nuggets", "Nuggets", "West", "Northwest", 39.749, -105.008, -7, "#0E2240", "#FEC524"),
    "DET": (8, "Detroit Pistons", "Pistons", "East", "Central", 42.341, -83.055, -5, "#C8102E", "#1D42BA"),
    "GS": (9, "Golden State Warriors", "Warriors", "West", "Pacific", 37.768, -122.388, -8, "#1D428A", "#FFC72C"),
    "HOU": (10, "Houston Rockets", "Rockets", "West", "Southwest", 29.751, -95.362, -6, "#CE1141", "#000000"),
    "IND": (11, "Indiana Pacers", "Pacers", "East", "Central", 39.764, -86.155, -5, "#002D62", "#FDBB30"),
    "LAC": (12, "LA Clippers", "Clippers", "West", "Pacific", 33.945, -118.341, -8, "#C8102E", "#1D428A"),
    "LAL": (13, "Los Angeles Lakers", "Lakers", "West", "Pacific", 34.043, -118.267, -8, "#552583", "#FDB927"),
    "MEM": (29, "Memphis Grizzlies", "Grizzlies", "West", "Southwest", 35.138, -90.051, -6, "#5D76A9", "#12173F"),
    "MIA": (14, "Miami Heat", "Heat", "East", "Southeast", 25.781, -80.188, -5, "#98002E", "#F9A01B"),
    "MIL": (15, "Milwaukee Bucks", "Bucks", "East", "Central", 43.045, -87.917, -6, "#00471B", "#EEE1C6"),
    "MIN": (16, "Minnesota Timberwolves", "Timberwolves", "West", "Northwest", 44.979, -93.276, -6, "#0C2340", "#78BE20"),
    "NO": (3, "New Orleans Pelicans", "Pelicans", "West", "Southwest", 29.949, -90.082, -6, "#0C2340", "#C8102E"),
    "NY": (18, "New York Knicks", "Knicks", "East", "Atlantic", 40.751, -73.993, -5, "#006BB6", "#F58426"),
    "OKC": (25, "Oklahoma City Thunder", "Thunder", "West", "Northwest", 35.463, -97.515, -6, "#007AC1", "#EF3B24"),
    "ORL": (19, "Orlando Magic", "Magic", "East", "Southeast", 28.539, -81.384, -5, "#0077C0", "#C4CED4"),
    "PHI": (20, "Philadelphia 76ers", "76ers", "East", "Atlantic", 39.901, -75.172, -5, "#006BB6", "#ED174C"),
    "PHX": (21, "Phoenix Suns", "Suns", "West", "Pacific", 33.446, -112.071, -7, "#1D1160", "#E56020"),
    "POR": (22, "Portland Trail Blazers", "Trail Blazers", "West", "Northwest", 45.532, -122.667, -8, "#E03A3E", "#000000"),
    "SAC": (23, "Sacramento Kings", "Kings", "West", "Pacific", 38.580, -121.500, -8, "#5A2D81", "#63727A"),
    "SA": (24, "San Antonio Spurs", "Spurs", "West", "Southwest", 29.427, -98.438, -6, "#000000", "#C4CED4"),
    "TOR": (28, "Toronto Raptors", "Raptors", "East", "Atlantic", 43.643, -79.379, -5, "#CE1141", "#000000"),
    "UTAH": (26, "Utah Jazz", "Jazz", "West", "Northwest", 40.768, -111.901, -7, "#002B5C", "#F9A01B"),
    "WSH": (27, "Washington Wizards", "Wizards", "East", "Southeast", 38.898, -77.021, -5, "#002B5C", "#E31837"),
}
ALIASES = {"GSW": "GS", "NOP": "NO", "NOR": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH", "BRK": "BKN",
           "PHO": "PHX", "CHO": "CHA", "CHH": "CHA"}
BY_ESPN_ID = {str(v[0]): k for k, v in TEAMS.items()}


def canon(abbr=None, espn_id=None):
    """Canonical abbreviation from an ESPN abbreviation or team id; None for non-NBA teams (All-Star, exhibition)."""
    if espn_id is not None and str(espn_id) in BY_ESPN_ID:
        return BY_ESPN_ID[str(espn_id)]
    if abbr:
        a = str(abbr).upper()
        a = ALIASES.get(a, a)
        if a in TEAMS:
            return a
    return None


def info(abbr):
    t = TEAMS[abbr]
    return {"abbr": abbr, "espn_id": t[0], "name": t[1], "short": t[2], "conf": t[3], "div": t[4],
            "lat": t[5], "lon": t[6], "tz": t[7], "color": t[8], "alt": t[9]}


def km(a, b):
    """Great-circle distance between two teams' arenas in km."""
    if a == b:
        return 0.0
    la1, lo1, la2, lo2 = map(radians, (TEAMS[a][5], TEAMS[a][6], TEAMS[b][5], TEAMS[b][6]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def same_division(a, b):
    return TEAMS[a][4] == TEAMS[b][4]


def same_conf(a, b):
    return TEAMS[a][3] == TEAMS[b][3]
