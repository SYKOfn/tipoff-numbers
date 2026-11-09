"""Before/after test of the player-based strength and pace totals on real data (walk-forward)."""
import json
import math
import sys

import numpy as np

from model import engine, lineup
from model.effects import norm_cdf
from model.player_engine import rows_by_game
from pipeline.store import load_games, load_players, read_json, ROOT


def collect(games, players, tuned):
    c = engine.build_context(games, players, [], tuned)
    byg = rows_by_game(players)
    lt = lineup.LineupTracker()
    out = []
    for g in c.games.to_dict("records"):
        gid = str(g["game_id"])
        rows = byg.get(gid)
        b = c.base.get(gid)
        if rows and b and g["home"] in rows and g["away"] in rows:
            sh = lt.strength([(r["player_id"], None) for r in rows[g["home"]] if r["min"] > 0])
            sa = lt.strength([(r["player_id"], None) for r in rows[g["away"]] if r["min"] > 0])
            pt = lt.pace_total(g["home"], g["away"])
            out.append({"day": g["day"], "season": int(g["season"]), "m": g["home_pts"] - g["away_pts"], "t": g["home_pts"] + g["away_pts"],
                        "bm": b[0] - b[1], "bt": b[0] + b[1], "dgs": sh[0] - sa[0], "dpm": sh[1] - sa[1], "pt": pt,
                        "alt": int(g["home"] in ("DEN", "UTAH")), "neutral": int(g.get("neutral") or 0)})
        lt.post_game(g, rows)
    return out


def ols(X, y):
    X, y = np.asarray(X, float), np.asarray(y, float)
    return np.linalg.lstsq(X, y, rcond=None)[0]


def score(m_hat, m, t_hat, t, sd):
    p = np.array([norm_cdf(x / sd) for x in m_hat])
    y = (np.asarray(m) > 0).astype(float)
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    return {"brier": round(float(np.mean((p - y) ** 2)), 4), "logloss": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 4),
            "winners": round(float(np.mean((p >= 0.5) == (y == 1))), 4), "mae_margin": round(float(np.mean(np.abs(np.asarray(m) - m_hat))), 3),
            "mae_total": round(float(np.mean(np.abs(np.asarray(t) - t_hat))), 3)}


def main(split="2026-01-31"):
    tuned = read_json(ROOT / "model" / "tuned.json", {}) or {}
    rows = [r for r in collect(load_games(), load_players(), tuned) if r["pt"] is not None]
    rows = [r for r in rows if r["day"] >= "2025-11-15"]  # first weeks: no player history yet
    tr = [r for r in rows if r["day"] < split]
    te = [r for r in rows if r["day"] >= split]
    f_m = lambda r: [r["bm"], r["dgs"], r["dpm"], r["alt"], 1.0]
    f_t = lambda r: [r["bt"], r["pt"], 1.0]
    wm = ols([f_m(r) for r in tr], [r["m"] for r in tr])
    wt = ols([f_t(r) for r in tr], [r["t"] for r in tr])
    wm_b = ols([[r["bm"], 1.0] for r in tr], [r["m"] for r in tr])
    sd_new = float(np.std([r["m"] - np.dot(wm, f_m(r)) for r in tr]))
    sd_old = float(np.std([r["m"] - r["bm"] for r in tr]))
    m, t = [r["m"] for r in te], [r["t"] for r in te]
    before = score(np.array([r["bm"] for r in te]), m, np.array([r["bt"] for r in te]), t, sd_old)
    after = score(np.array([np.dot(wm, f_m(r)) for r in te]), m, np.array([np.dot(wt, f_t(r)) for r in te]), t, sd_new)
    res = {"train_games": len(tr), "test_games": len(te), "split": split, "weights_margin": dict(zip(["base", "gamescore", "plusminus", "altitude", "const"], map(float, wm))),
           "weights_total": dict(zip(["base", "pace", "const"], map(float, wt))), "base_recalibrated": list(map(float, wm_b)),
           "before": before, "after": after}
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    main(*sys.argv[1:])
