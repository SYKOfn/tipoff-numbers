"""One-off check: do past box-score summaries carry the injury report from game time?"""
import pandas as pd
from pipeline import espn
g = pd.read_csv("data/history/games.csv", dtype={"game_id": str})
for s in sorted(g.season.unique()):
    for gid in g[g.season == s].game_id.head(2):
        sm = espn.summary(gid)
        inj = (sm or {}).get("injuries") or {}
        print(s, gid, {k: [(i.get("name"), i.get("status"), (i.get("date") or "")[:10]) for i in v][:4] for k, v in inj.items()})
