"""Out-of-sample test of the referee-crew factor on totals: fit on earlier seasons, score the next one.
Usage: python -m tools.test_refs   (needs the referee backfill in data/history/games.csv)"""
import numpy as np

from model import effects, engine
from pipeline.store import load_games, load_players


def main():
    games = load_games(); players = load_players()
    games = games[games.home_pts.notna()]
    have = games["refs"].notna() & (games["refs"].astype(str) != "-")
    print("games with crews:", int(have.sum()), "of", len(games), games[have].groupby("season").size().to_dict())
    c = engine.build_context(games, players, [])
    lam = c.tuned["lam_effects"]
    for S in sorted(set(int(s) for s in c.games.season))[2:]:
        start = c.games[c.games.season == S].day.min()
        end = c.games[c.games.season == S + 1].day.min() if (c.games.season == S + 1).any() else "9999"
        tr = [r for r in c.rows if r[5] < start]
        te = [r for r in c.rows if start <= r[5] < end and r[0].get("refs_total")]
        if len(tr) < 500 or len(te) < 100:
            continue
        res = {}
        for tag, extra in (("without", False), ("with", True)):
            X = lambda rows: np.array([np.r_[effects.vector(effects.TOTAL, r[0]), [r[0].get("refs_total", 0.0)] if extra else []] for r in rows])
            y = np.array([r[3] - r[4] for r in tr])
            coef, se, _, sd = effects.fit(X(tr), y, lam)
            pt = np.array([r[4] for r in te]) + X(te) @ coef
            at = np.array([r[3] for r in te])
            res[tag] = round(float(np.mean(np.abs(pt - at))), 3)
            if extra:
                res["coef"] = (round(float(coef[-1]), 3), round(float(coef[-1] / se[-1]), 1))
        print(S, len(te), "totals MAE without", res["without"], "with", res["with"], "crew coef, t:", res["coef"])


if __name__ == "__main__":
    main()
