"""What does ESPN's play-by-play look like (substitutions, participants, clock)?"""
import json
from pipeline import espn
import pandas as pd
g = pd.read_csv("data/history/games.csv", dtype={"game_id": str})
for gid in [g[g.season == 2026].game_id.iloc[100], g[g.season == 2022].game_id.iloc[100]]:
    d = espn.fetch(f"{espn.BASE}/summary?event={gid}")
    plays = d.get("plays") or []
    print(gid, "plays", len(plays), "keys", list(plays[0].keys()) if plays else None)
    subs = [p for p in plays if "ubstitution" in json.dumps(p.get("type"))]
    print(" subs", len(subs))
    for p in plays[:3] + subs[:3]:
        print(" ", json.dumps(p)[:700])
    print(" last", json.dumps(plays[-1])[:400] if plays else None)
    bp = (d.get("boxscore") or {}).get("players") or []
    print(" box teams", [(t.get("team", {}).get("id"), t.get("team", {}).get("abbreviation")) for t in bp])
    print(" header comp", json.dumps((d.get("header") or {}).get("competitions", [{}])[0].get("competitors", [{}])[0].get("team", {}))[:200])
