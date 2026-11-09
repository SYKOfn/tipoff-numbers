"""Pinnacle's pre-game moneyline for past games (The Odds API historical snapshots), to test the market blend.

One snapshot per game day, 30 minutes before that day's first tip-off: 10 credits a day.
Resumable: days already stored are skipped.
Usage: python -m tools.market_history MAX_CREDITS SEASON [SEASON ...]
It never spends more than MAX_CREDITS (and never more than the site's ODDS_API_DAILY cap, if set).
"""
import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from pipeline import oddsapi

OUT = Path("data/odds/pinnacle_history.csv")
URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"


def snap(ts):
    q = {"apiKey": oddsapi.key(), "regions": "eu", "markets": "h2h", "bookmakers": "pinnacle",
         "oddsFormat": "decimal", "date": ts}
    with urllib.request.urlopen(f"{URL}?{urllib.parse.urlencode(q)}", timeout=60) as r:
        return json.loads(r.read().decode()), r.headers.get("x-requests-remaining")


def main(max_credits, seasons):
    cap = oddsapi.env("ODDS_API_DAILY", "")
    if cap:
        max_credits = min(max_credits, int(float(cap)))
    spent = 0
    g = pd.read_csv("data/history/games.csv", dtype={"game_id": str})
    g = g[g["season"].isin(seasons) & g["home_pts"].notna()]
    have = set()
    if OUT.exists():
        have = set(pd.read_csv(OUT, dtype={"game_id": str})["game_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new = not OUT.exists()
    f = open(OUT, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(["game_id", "snapshot", "ml_home", "ml_away"])
    left = None
    for day, d in g.groupby("day"):
        d = d[~d["game_id"].isin(have)]
        if not len(d):
            continue
        first = min(datetime.fromisoformat(x.replace("Z", "+00:00")) for x in d["date"])
        ts = (first - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if spent + 10 > max_credits:
            print(f"stopping: credit limit {max_credits} reached")
            break
        try:
            spent += 10
            data, left = snap(ts)
        except Exception as e:
            print(day, "error", e)
            continue
        found = 0
        for ev in data.get("data") or []:
            h, a = oddsapi.team_of(ev.get("home_team")), oddsapi.team_of(ev.get("away_team"))
            row = d[(d["home"] == h) & (d["away"] == a)]
            if not len(row):
                continue
            m = oddsapi.parse_game_markets(ev, h, a).get("pinnacle") or {}
            if m.get("ml_home") and m.get("ml_away"):
                w.writerow([row["game_id"].iloc[0], data.get("timestamp"), m["ml_home"], m["ml_away"]])
                found += 1
        f.flush()
        print(day, ts, "games", len(d), "priced", found, "credits left", left)
        if left is not None and float(left) < 3000:
            print("stopping: keeping 3000 credits for the live site")
            break
    f.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python -m tools.market_history MAX_CREDITS SEASON [SEASON ...]")
    main(int(sys.argv[1]), [int(x) for x in sys.argv[2:]])
