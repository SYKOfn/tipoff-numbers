"""Which European/UK bookmakers carry NBA player props in The Odds API? One event, one market: ~2 credits."""
import json
import urllib.parse
import urllib.request

from pipeline import oddsapi

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"


def get(path, **q):
    q["apiKey"] = oddsapi.key()
    with urllib.request.urlopen(f"{BASE}{path}?{urllib.parse.urlencode(q)}", timeout=60) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-last"), r.headers.get("x-requests-remaining")


events, cost, left = get("/events")  # free
print("events", len(events), "cost", cost, "left", left)
ev = sorted(events, key=lambda e: e["commence_time"])[0]
print("event", ev["away_team"], "at", ev["home_team"], ev["commence_time"])
data, cost, left = get(f"/events/{ev['id']}/odds", regions="eu,uk", markets="player_points", oddsFormat="decimal")
print("cost", cost, "left", left)
for bk in data.get("bookmakers", []):
    n = sum(len(m.get("outcomes", [])) for m in bk.get("markets", []))
    print("BOOK", bk["key"], bk.get("title"), "outcomes", n,
          [(o.get("description"), o.get("name"), o.get("point"), o.get("price")) for m in bk.get("markets", []) for o in m.get("outcomes", [])][:4])
