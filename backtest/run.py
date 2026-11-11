"""Tune on one season, test once on the next. Writes model/tuned.json and backtest/results.json.

Walk-forward by week: every estimate uses only games played before that week, for the base
ratings AND for the size of every physical and psychological factor.

    python -m backtest.run            (on data/history)
"""
import itertools
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from model import effects, engine
from model.parlay import novig
from pipeline.store import ROOT, load_games, load_players, load_stints, write_json

PINNACLE = Path("data/odds/pinnacle_history.csv")
BLEND_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def load_pinnacle():
    """{game_id: fair home-win probability} from Pinnacle's pre-game price (tools/market_history.py).
    One snapshot per game day, 30 min before that day's first tip -- stale for games tipping later
    that day, so this is a lower bound on how sharp Pinnacle's actual closing price is."""
    if not PINNACLE.exists():
        return {}
    df = pd.read_csv(PINNACLE, dtype={"game_id": str})
    df = df.sort_values("snapshot").drop_duplicates("game_id", keep="last")
    out = {}
    for gid, h, a in zip(df["game_id"], df["ml_home"], df["ml_away"]):
        p = novig(h, a)
        if p is not None:
            out[gid] = p
    return out


def _blend(model_p, market_p, w):
    lo = lambda x: math.log(max(x, 1e-6) / max(1 - x, 1e-6))
    return 1 / (1 + math.exp(-(w * lo(model_p) + (1 - w) * lo(market_p))))


def market_check(mkt):
    """mkt: [(model_p, market_p, actual)]. Model vs. Pinnacle's pre-game price vs. the best blend --
    the real "do we beat the market" bar, not just "do we beat a plain average."""
    if len(mkt) < 100:
        return None
    n = len(mkt)
    brier_model = sum((a - y) ** 2 for a, b, y in mkt) / n
    brier_market = sum((b - y) ** 2 for a, b, y in mkt) / n
    grid = [{"w": w, "brier": sum((_blend(a, b, w) - y) ** 2 for a, b, y in mkt) / n} for w in BLEND_GRID]
    best = min(grid, key=lambda r: r["brier"])
    return {"n": n, "brier_model": round(brier_model, 4), "brier_market": round(brier_market, 4),
            "best_blend_w": best["w"], "brier_best_blend": round(best["brier"], 4),
            "brier_blend_040": round(next(r["brier"] for r in grid if r["w"] == 0.4), 4)}


def evaluate(c, season, lam_eff, stype=None, pinnacle=None):
    rows = [r for r in c.rows if int(c.meta[r[6]]["season"]) == season
            and (stype is None or int(c.meta[r[6]]["stype"]) in stype)]
    if not rows:
        return None
    rows.sort(key=lambda r: r[5])
    first = date.fromisoformat(rows[0][5])
    out = {k: [] for k in ("win", "win_nomind", "win_base", "win_bl", "m", "m_nomind", "m_base", "m_bl", "t", "t_base", "t_bl", "hw", "am", "at")}
    week = None
    eff = stack = None
    mkt = []
    for ctx, am, bm, at, bt, day, gid in rows:
        wk = (date.fromisoformat(day) - first).days // 7
        if wk != week:
            week = wk
            # the shipped model: player-strength stack and factor sizes both refitted on games before this week only
            prev = [r for r in c.rows_raw if r[5] < day]
            stack = engine.fit_stack(prev, c.lfeat)
            if stack is not None:
                prev = [(r[0], r[1], engine.stacked(stack, r[2], c.lfeat.get(r[6])), r[3], r[4]) for r in prev]
            eff = effects.estimate([r[:5] for r in prev], lam_eff)
        g = c.meta[gid]
        b = c.base[gid]
        p = engine.predict(c, g, ctx, {}, eff=eff, base_override=b, lineup_feat=c.lfeat.get(gid), stack=stack)
        if pinnacle and gid in pinnacle:
            mkt.append((p["win_home"], pinnacle[gid], 1.0 if am > 0 else 0.0))
        out["win"].append(p["win_home"])
        out["win_nomind"].append(p["win_home_nomind"])
        out["win_base"].append(p["base"]["win_home"])
        out["win_bl"].append(p["baseline"]["win_home"])
        out["m"].append(p["margin"])
        out["m_nomind"].append(p["margin_nomind"])
        out["m_base"].append(p["base"]["margin"])
        out["m_bl"].append(p["baseline"]["margin"])
        out["t"].append(p["total"])
        out["t_base"].append(p["base"]["total"])
        out["t_bl"].append(p["baseline"]["total"])
        out["hw"].append(1.0 if am > 0 else 0.0)
        out["am"].append(am)
        out["at"].append(at)
    a = {k: np.array(v) for k, v in out.items()}
    brier = lambda w: float(np.mean((a[w] - a["hw"]) ** 2))
    mae = lambda m, y: float(np.mean(np.abs(a[m] - a[y])))
    hit = lambda w: float(np.mean((a[w] >= 0.5) == (a["hw"] == 1)))
    return {
        "n": len(rows),
        "market": market_check(mkt),
        "full": {"brier": brier("win"), "hit": hit("win"), "mae_margin": mae("m", "am"), "mae_total": mae("t", "at")},
        "no_mind": {"brier": brier("win_nomind"), "hit": hit("win_nomind"), "mae_margin": mae("m_nomind", "am")},
        "base_only": {"brier": brier("win_base"), "hit": hit("win_base"), "mae_margin": mae("m_base", "am"), "mae_total": mae("t_base", "at")},
        "plain_average": {"brier": brier("win_bl"), "hit": hit("win_bl"), "mae_margin": mae("m_bl", "am"), "mae_total": mae("t_bl", "at")},
    }


def main():
    games = load_games()
    players = load_players()
    pinnacle = load_pinnacle()
    seasons = sorted(games["season"].unique())
    full = [s for s in seasons if (games["season"] == s).sum() > 1100]
    if len(full) < 2:
        print("need two complete seasons")
        return
    tune_s, test_s = full[-2], full[-1]
    print("tune on", tune_s, "test on", test_s)
    best = None
    log = []
    for hl, lam, carry in itertools.product([45, 90, 180], [3.0, 8.0], [0.3, 0.6, 1.0]):
        tuned = {"half_life": hl, "lam": lam, "carry": carry, "lam_effects": 150.0}
        c = engine.build_context(games, players, [], tuned)
        rows = [r for r in c.rows if int(c.meta[r[6]]["season"]) == tune_s]
        mae_m = float(np.mean([abs(r[1] - r[2]) for r in rows]))
        mae_t = float(np.mean([abs(r[3] - r[4]) for r in rows]))
        score = mae_m + 0.5 * mae_t
        log.append({"half_life": hl, "lam": lam, "carry": carry, "mae_margin": round(mae_m, 3), "mae_total": round(mae_t, 3)})
        print(log[-1])
        if best is None or score < best[0]:
            best = (score, tuned, c)
    tuned = best[1]
    # score the model production ships: the grid above only tunes the base ratings, so rebuild once with
    # stint ratings, without which player_features() returns None and the player stack never runs
    c = engine.build_context(games, players, [], tuned, stints=load_stints())
    print('player-stack games:', len(c.lfeat))
    lam_log = []
    for le in (40.0, 150.0, 500.0):
        r = evaluate(c, tune_s, le)
        lam_log.append({"lam_effects": le, "brier": round(r["full"]["brier"], 4), "mae_margin": round(r["full"]["mae_margin"], 3)})
        print(lam_log[-1])
    tuned["lam_effects"] = min(lam_log, key=lambda x: x["mae_margin"])["lam_effects"]
    test = evaluate(c, test_s, tuned["lam_effects"], pinnacle=pinnacle)
    test_reg = evaluate(c, test_s, tuned["lam_effects"], stype={2}, pinnacle=pinnacle)
    test_po = evaluate(c, test_s, tuned["lam_effects"], stype={3, 5}, pinnacle=pinnacle)
    cur = max(seasons)
    now = evaluate(c, cur, tuned["lam_effects"], pinnacle=pinnacle) if cur != test_s else None
    eff_all = effects.estimate([r[:5] for r in c.rows if int(c.meta[r[6]]["season"]) <= test_s], tuned["lam_effects"])
    res = {"tune_season": int(tune_s), "test_season": int(test_s), "tuned": tuned, "grid": log, "lam_grid": lam_log,
           "test": test, "test_regular": test_reg, "test_playoffs": test_po, "current_season": now,
           "factors_through_test": eff_all.table()}
    write_json(ROOT / "model" / "tuned.json", tuned, compact=False)
    write_json(ROOT / "backtest" / "results.json", res, compact=False)
    print(json.dumps(test, indent=1))


if __name__ == "__main__":
    main()
