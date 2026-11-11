"""Probe / download NBA.com defender matchup data (who guarded whom, and what the scorer produced).

  python -m tools.nba_matchups probe            can GitHub's machines reach stats.nba.com? (writes a small report)
  python -m tools.nba_matchups season 2025-26   all offensive-player x defender totals for a season

stats.nba.com often blocks cloud servers; the probe records exactly what happened so we know before building on it.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9", "x-nba-stats-origin": "stats", "x-nba-stats-token": "true",
}


def get(endpoint, params, timeout=40):
    url = f"https://stats.nba.com/stats/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8")
    return json.loads(body), round(time.time() - t0, 1)


def matchups(season, off_player=None, def_player=None):
    p = {"LeagueID": "00", "PerMode": "Totals", "Season": season, "SeasonType": "Regular Season"}
    if off_player:
        p["OffPlayerID"] = off_player
    if def_player:
        p["DefPlayerID"] = def_player
    return get("leagueseasonmatchups", p)


def probe():
    rep = {}
    for name, fn in (("matchups_jokic_2025-26", lambda: matchups("2025-26", off_player="203999")),
                     ("player_index", lambda: get("playerindex", {"LeagueID": "00", "Season": "2025-26"}))):
        try:
            d, secs = fn()
            rs = (d.get("resultSets") or [{}])[0]
            rep[name] = {"ok": True, "secs": secs, "headers": rs.get("headers"), "rows": len(rs.get("rowSet") or []),
                         "sample": (rs.get("rowSet") or [])[:3]}
        except Exception as e:
            rep[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "nba_matchups_probe.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1)[:3000])


if __name__ == "__main__":
    if sys.argv[1] == "probe":
        probe()
    else:
        d, secs = matchups(sys.argv[2])
        print(secs, len((d.get("resultSets") or [{}])[0].get("rowSet") or []))
