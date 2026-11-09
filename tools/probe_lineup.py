"""Check what ESPN's summary holds before tip-off (starting lineups?) for the next games."""
import json
from pipeline import espn
from pipeline.store import STATE, read_json
up = sorted(read_json(STATE / "upcoming.json", []) or [], key=lambda g: g["date"])[:2]
for g in up:
    d = espn.fetch(f"{espn.BASE}/summary?event={g['game_id']}")
    print(g["game_id"], g["date"], "keys", list(d.keys()))
    for k in ("rosters", "boxscore", "gameInfo", "injuries"):
        print(" ", k, json.dumps(d.get(k))[:1200])
