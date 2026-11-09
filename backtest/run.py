"""Tune on one season, test once on the next. Writes model/tuned.json and backtest/results.json.

Walk-forward by week: every estimate uses only games played before that week, for the base
ratings AND for the size of every physical and psychological factor.

    python -m backtest.run            (on data/history)
"""
import itertools
import json
import math
from datetime import date, timedelta

import numpy as np

from model import effects, engine
from pipeline.store import ROOT, load_games, load_players, write_json


def evaluate(c, season, lam_eff, stype=None):
    rows = [r for r in c.rows if int(c.meta[r[6]]["season"]) == season
            and (stype is None or int(c.meta[r[6]]["stype"]) in stype)]
    if not rows:
        return None
    rows.sort(key=lambda r: r[5])
    first = date.fromisoformat(rows[0][5])
    out = {k: [] for k in ("win", "win_nomind", "win_base", "win_bl", "m", "m_nomind", "m_base", "m_bl", "t", "t_base", "t_bl", "hw", "am", "at")}
    week = None
    eff = None
    for ctx, am, bm, at, bt, day, gid in rows:
        wk = (date.fromisoformat(day) - first).days // 7
        if wk != week:
            week = wk
            eff = effects.estimate([r[:5] for r in c.rows if r[5] < day], lam_eff)
        g = c.meta[gid]
        b = c.base[gid]
        p = engine.predict(c, g, ctx, {}, eff=eff, base_override=b)
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
        "full": {"brier": brier("win"), "hit": hit("win"), "mae_margin": mae("m", "am"), "mae_total": mae("t", "at")},
        "no_mind": {"brier": brier("win_nomind"), "hit": hit("win_nomind"), "mae_margin": mae("m_nomind", "am")},
        "base_only": {"brier": brier("win_base"), "hit": hit("win_base"), "mae_margin": mae("m_base", "am"), "mae_total": mae("t_base", "at")},
        "plain_average": {"brier": brier("win_bl"), "hit": hit("win_bl"), "mae_margin": mae("m_bl", "am"), "mae_total": mae("t_bl", "at")},
    }


def main():
    games = load_games()
    players = load_players()
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
    tuned, c = best[1], best[2]
    lam_log = []
    for le in (40.0, 150.0, 500.0):
        r = evaluate(c, tune_s, le)
        lam_log.append({"lam_effects": le, "brier": round(r["full"]["brier"], 4), "mae_margin": round(r["full"]["mae_margin"], 3)})
        print(lam_log[-1])
    tuned["lam_effects"] = min(lam_log, key=lambda x: x["mae_margin"])["lam_effects"]
    test = evaluate(c, test_s, tuned["lam_effects"])
    test_reg = evaluate(c, test_s, tuned["lam_effects"], stype={2})
    test_po = evaluate(c, test_s, tuned["lam_effects"], stype={3, 5})
    cur = max(seasons)
    now = evaluate(c, cur, tuned["lam_effects"]) if cur != test_s else None
    eff_all = effects.estimate([r[:5] for r in c.rows if int(c.meta[r[6]]["season"]) <= test_s], tuned["lam_effects"])
    res = {"tune_season": int(tune_s), "test_season": int(test_s), "tuned": tuned, "grid": log, "lam_grid": lam_log,
           "test": test, "test_regular": test_reg, "test_playoffs": test_po, "current_season": now,
           "factors_through_test": eff_all.table()}
    write_json(ROOT / "model" / "tuned.json", tuned, compact=False)
    write_json(ROOT / "backtest" / "results.json", res, compact=False)
    print(json.dumps(test, indent=1))


if __name__ == "__main__":
    main()
