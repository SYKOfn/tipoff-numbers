"""Our player projections against the sharpest bookmaker's, every night, in the open.

For every player line Pinnacle posted (closing snapshot) on a game whose projections were frozen at tip-off,
compare our pre-game projection with Pinnacle's line once the game is played:
  - which one missed the actual stat by less,
  - when they disagree, how often our side of Pinnacle's line won (about 52.4% breaks even at standard prices).
Shown on the Model accuracy page. Players in the same game move together, so the result means little until
there are about 150 games behind it (TARGET_GAMES).
"""
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .oddsapi import norm_name
from .store import PRED, ROOT

LINES = ROOT / "data" / "props" / "lines.csv"
TARGET_GAMES = 150
BREAK_EVEN = 0.524


def summary(players_df, season):
    if not LINES.exists():
        return None
    proj = {}
    for f in sorted((PRED / str(season)).glob("*.json")):
        d = json.loads(f.read_text())
        if not d.get("frozen"):
            continue
        for side in ("home", "away"):
            for p in ((d.get("payload") or {}).get("players") or {}).get(side, []):
                if not p.get("out"):
                    proj[(str(d["game_id"]), norm_name(p["name"]))] = p
    if not proj:
        return None
    pl = players_df[players_df["game_id"].astype(str).isin({g for g, _ in proj})]
    act = {(str(r.game_id), str(r.player_id)): r for r in pl.itertuples()}
    L = pd.read_csv(LINES, dtype={"game_id": str})
    L = L[(L.book == "pinnacle") & (L.phase == "close") & L.over.notna() & L.under.notna()].sort_values("fetched_at")
    L = L.drop_duplicates(["game_id", "player", "stat"], keep="last")
    n = 0; ours = line = 0.0; lean = wins = big = big_wins = 0
    games, days = set(), set()
    by_stat = defaultdict(lambda: [0, 0.0, 0.0, 0, 0])
    for r in L.itertuples():
        p = proj.get((r.game_id, norm_name(r.player)))
        if not p or p.get(r.stat) is None:
            continue
        a = act.get((r.game_id, str(p.get("id"))))
        if a is None or not a.min:
            continue
        v = (a.pts + a.reb + a.ast) if r.stat == "pra" else getattr(a, r.stat, None)
        if v is None or pd.isna(v) or v == r.line:
            continue
        pr = float(p[r.stat]); n += 1; games.add(r.game_id); days.add(r.day)
        ours += abs(v - pr); line += abs(v - r.line)
        s = by_stat[r.stat]; s[0] += 1; s[1] += abs(v - pr); s[2] += abs(v - r.line)
        if pr != r.line:
            won = (pr > r.line) == (v > r.line)
            lean += 1; wins += won; s[3] += 1; s[4] += won
            if abs(pr - r.line) >= 2:
                big += 1; big_wins += won
    if not n:
        return None
    return {"n": n, "games": len(games), "days": len(days), "since": min(days), "target_games": TARGET_GAMES, "break_even": BREAK_EVEN,
            "mae_ours": round(ours / n, 3), "mae_line": round(line / n, 3),
            "lean": lean, "lean_wins": wins, "big": big, "big_wins": big_wins,
            "by_stat": {k: {"n": s[0], "mae_ours": round(s[1] / s[0], 3), "mae_line": round(s[2] / s[0], 3),
                            "lean": s[3], "lean_wins": s[4]} for k, s in sorted(by_stat.items())}}
