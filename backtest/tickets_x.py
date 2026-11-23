"""The ticket replay (backtest/tickets.py) plus what it does not score: the day's cross-game tickets (out["parlays"]:
Value 2, Core 3, the daily 6, long shots), the per-game tickets at other sizes, and the cross-game tickets built
again with no price in any ranking (EDGE_W = EST_EDGE_W = 0). backtest/tickets.py runs unchanged and writes its own
files; legs are settled with the same parlay.score_leg calls, on the box scores it settles its game tickets with.

    X_SIZES=3,4 X_EDGE0=1 TAG=_x LOCK_STATUS=1 python -m backtest.tickets_x SEASON [FIRST_DAY LAST_DAY]

Writes /tmp/xtickets_{season}{TAG}.json: {set: [{day, name, n, p, hit, legs: [[p, result, kind, game, id]]}]} for
the sets par (cross-game, live weights), par0 (cross-game, EDGE_W 0), g5 (game tickets, live) and g3/g4 (X_SIZES).
"""
import json
import os
import sys

from model import parlay
from backtest import tickets as T


def main(season, d0=None, d1=None):
    sizes = tuple(int(x) for x in os.environ.get("X_SIZES", "").split(",") if x)
    edge0 = os.environ.get("X_EDGE0") == "1"
    ctx, stash = {}, []
    _build, _score = parlay.build, parlay.score_leg

    def score(l, meta, rows):  # the replay's own settling call: keep each game's box score for the extra tickets
        ctx[str(l["game"])] = (meta, rows)
        return _score(l, meta, rows)

    def build(slate, *a, **k):
        parlay.GAME_SIZES = sizes
        try:
            out, cands = _build(slate, *a, **k)
        finally:
            parlay.GAME_SIZES = ()
        sets = {"par": out["parlays"], "g5": out["game_tickets"],
                **{f"g{n}": v for n, v in (out.pop("game_tickets_n", None) or {}).items()}}
        if edge0:
            w = parlay.EDGE_W, parlay.EST_EDGE_W
            parlay.EDGE_W = parlay.EST_EDGE_W = 0.0
            try:
                o0, _ = _build(slate, *a, **k)
            finally:
                parlay.EDGE_W, parlay.EST_EDGE_W = w
            sets["par0"] = o0["parlays"]
        stash.append((str(slate[0][1]["tip"])[:10] if slate else None, sets))
        return out, cands

    parlay.build, parlay.score_leg = build, score
    try:
        T.main(season, d0, d1)
    finally:
        parlay.build, parlay.score_leg = _build, _score
    res, unsettled = {}, 0
    for day, sets in stash:
        for name, tks in sets.items():
            for tk in tks:
                legs = []
                for l in tk["legs"]:
                    c = ctx.get(str(l["game"]))
                    x = _score(l, *c) if c else "unsettled"
                    unsettled += c is None
                    legs.append([l["p"], x, l.get("kind"), str(l["game"]), l.get("id")])
                live = [x[1] for x in legs if x[1] != "void"]
                # "unsettled": a leg from a game with no game ticket that day (no box score captured; about 1% of
                # cross-game tickets): leave those tickets out of any count
                res.setdefault(name, []).append({"day": day, "name": tk.get("name"), "n": len(legs), "p": tk["p"],
                                                 "hit": bool(live) and all(x == "hit" for x in live), "legs": legs,
                                                 "settled": all(x[1] != "unsettled" for x in legs)})
    path = f"/tmp/xtickets_{season}{os.environ.get('TAG', '')}.json"
    json.dump(res, open(path, "w"), default=float)
    print(f"\nxtickets: {path}, legs without a box score {unsettled}")
    for name, tks in sorted(res.items()):
        print(f"  {name}: {len(tks)} tickets, landed {sum(t['hit'] for t in tks)} (stated {sum(t['p'] for t in tks):.1f})")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 2026, *(a[1:3] if len(a) >= 3 else (None, None)))
