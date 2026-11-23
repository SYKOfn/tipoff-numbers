"""Rows for the replay's milestone blend (backtest/tickets.py ALT_BLEND, ALT_ROWS): every bookmaker over price in the
ESPN cache (~/.cache/tipoff_espn, backtest/espn_props.py fetch) with our agreed leg chance at that line and the result.

    python -m backtest.alt_rows 2025      # -> ~/.cache/tipoff_alt/alt_rows_2025.pkl (the 2024-25 ESPN BET rows)

The replay reads only gid, pid, stat, line and imp (the book's implied chance, margin included). Rows need the player's
5th game of the season and a projection. 2022-23 and 2023-24 have main lines only (one line per player and stat,
DraftKings / MGM / Caesars), so their rows would be main-line overs, not X+ rungs; their Ladder is priced with
LADDER_MAIN instead.
"""
import json, sys, pickle, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, ".")
from model import engine, player_engine as PE, players as P, parlay
from pipeline.store import load_games, load_players, load_stints
SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
OUT = Path.home() / ".cache" / "tipoff_alt"
CACHE = Path.home() / ".cache" / "tipoff_espn"
TYPES = {"Total Points": "pts", "Total Rebounds": "reb", "Total Assists": "ast", "Total 3-Point Field Goals": "tpm"}
games, players = load_games(), load_players()
c = engine.build_context(games, players, [], {"half_life": 90, "lam": 3.0, "carry": 0.6, "lam_effects": 40.0}, stints=load_stints())
pt, pe, pdisp, plogs, ptrack, byg = PE.walk(c, players, {}, SEASON)
meta = {str(k): v for k, v in c.meta.items()}
pl = players.copy(); pl["gid"] = pl.game_id.astype(str); pl["pid"] = pl.player_id.astype(str)
pl = pl[pl.gid.map(lambda g: g in meta and int(meta[g]["season"]) == SEASON) & (pl["min"].fillna(0) > 0)].copy()
pl["day"] = pl.gid.map(lambda g: meta[g]["day"]); pl = pl.sort_values(["pid", "day"])
for st in ("pts", "reb", "ast", "tpm"):
    g = pl.groupby("pid")[st]
    pl["avg_" + st] = g.transform(lambda s: s.shift().expanding().mean()); pl["l5_" + st] = g.transform(lambda s: s.shift().rolling(5, min_periods=1).mean())
pl["gp"] = pl.groupby("pid").cumcount()
A = {(r.gid, r.pid): r for r in pl.itertuples()}
dec = lambda x: (float(x) if x and float(x) > 1 else None)
rows = []
for f in sorted(CACHE.glob("*.json")):
    gid = f.stem
    if gid not in meta: continue
    b = c.base.get(gid); m = (b[0] - b[1]) if b else 0.0
    for it in json.loads(f.read_text()).get("items", []):
        st = TYPES.get((it.get("type") or {}).get("name")); o = it.get("odds") or {}
        if not st or not o.get("total"): continue
        cur = it.get("current") or {}
        if "under" in cur: continue                          # overs only: Winamax lists "X+" overs
        price = dec((o.get("decimal") or {}).get("value"))
        if not price: continue
        pid = str(it["athlete"]["$ref"].split("/athletes/")[1].split("?")[0]); k = (gid, pid)
        a, p_ = A.get(k), plogs.get(k)
        if a is None or not p_ or a.gp < 5 or p_.get(st) is None: continue
        L = float(o["total"]["value"]); v = getattr(a, st)
        if v == L: continue
        dp = P.player_disp({"dsp": pt.dsp_log.get(k) or {}}, pdisp)
        voices = [P.over_prob(st, L, max(x, 0.05), dp) for x in (p_[st], getattr(a, "avg_" + st), getattr(a, "l5_" + st))]
        side = "home" if a.team == meta[gid]["home"] else "away"
        pc = parlay.agreed_chance(voices, p_.get("min"), st, L, m if side == "home" else -m)
        rows.append(dict(day=meta[gid]["day"], gid=gid, pid=pid, stat=st, line=L, p=pc, pmin=min(voices), proj=p_[st], imp=1 / price,
                         labelled="over" in cur, y=float(v > L)))
D = pd.DataFrame(rows); OUT.mkdir(exist_ok=True); pickle.dump(D, open(OUT / f"alt_rows_{SEASON}.pkl", "wb"))
print("rows", len(D), "games", D.gid.nunique(), "| one-sided alt overs", (~D.labelled).sum())
z = D[(D.p >= 0.70) & (D.p <= 0.92)]
print("ticket-zone rows (our chance 70-92%):", len(z), "landed", round(z.y.mean(), 3), "our chance", round(z.p.mean(), 3), "book implied", round(z.imp.mean(), 3))
