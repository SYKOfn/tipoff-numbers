"""Today's referee crews from the NBA's official assignments page (posted around 9 a.m. US Eastern)."""
import html as html_mod
import re
import urllib.request

from .teams import TEAMS

URL = "https://official.nba.com/referee-assignments/"
ALIASES = {"la lakers": "LAL", "l.a. lakers": "LAL", "la clippers": "LAC", "l.a. clippers": "LAC",
           "new york": "NY", "new orleans": "NO", "golden state": "GS", "san antonio": "SA", "oklahoma city": "OKC",
           "utah": "UTAH", "washington": "WSH", "brooklyn": "BKN", "phoenix": "PHX"}


def team_of(name):
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    if n in ALIASES:
        return ALIASES[n]
    for ab, t in TEAMS.items():
        full = t[1].lower()
        if full.startswith(n) or n == t[2].lower() or n in full:
            return ab
    return None


def parse(page):
    """{(away, home): [names]} from the assignments table (crew chief, referee, umpire)."""
    out = {}
    for row in re.findall(r"<tr>(.*?)</tr>", page, flags=re.S):
        cells = [re.sub(r"<[^>]+>", " ", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        cells = [re.sub(r"\s+", " ", html_mod.unescape(c)).strip() for c in cells]
        if len(cells) < 4 or "@" not in cells[0]:
            continue
        away, home = [team_of(x) for x in cells[0].split("@", 1)]
        names = [re.sub(r"\s*\(#\d+\)", "", c).strip() for c in cells[1:4] if c]
        if away and home and names:
            out[(away, home)] = names
    return out


def today_crews():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (tipoff-numbers)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse(r.read().decode("utf-8", "ignore"))
