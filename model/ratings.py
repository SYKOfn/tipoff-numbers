"""Base ratings: a time-weighted, penalised regression per stat.

For every team-game:  stat_for = league avg + home edge * is_home + attack[team] - defence[opponent]
Older games count less (half-life in days, and last season's games are discounted again); attack and defence are pulled towards 0 (ridge), so a
team needs evidence to sit far from average. One fit per stat: points, threes made, rebounds, assists.
"""
from datetime import date

import numpy as np

from pipeline.teams import TEAMS

ABBRS = sorted(TEAMS)
IDX = {a: i for i, a in enumerate(ABBRS)}
N = len(ABBRS)
STATS = {"pts": ("home_pts", "away_pts"), "tpm": ("h_tpm", "a_tpm"), "reb": ("h_reb", "a_reb"), "ast": ("h_ast", "a_ast")}


class Rating:
    def __init__(self, mu, home, att, dfn, n, sd):
        self.mu, self.home, self.att, self.dfn, self.n, self.sd = mu, home, att, dfn, n, sd

    def expect(self, team, opp, is_home=True, neutral=False):
        h = 0.0 if neutral else (0.5 * self.home if is_home else -0.5 * self.home)
        return self.mu + h + self.att[IDX[team]] - self.dfn[IDX[opp]]

    def net(self, team):
        """Points better than an average team per game, on a neutral floor."""
        return self.att[IDX[team]] + self.dfn[IDX[team]]


def fit(games, stat="pts", asof=None, half_life=90.0, lam=6.0, carry=0.6):
    """games: DataFrame of finished games before `asof` (ISO day). Returns a Rating or None."""
    hc, ac = STATS[stat]
    g = games
    if asof is not None:
        g = g[g["day"] < asof]
    g = g[g[hc].notna() & g[ac].notna()]
    if len(g) < 30:
        return None
    ref = date.fromisoformat(asof) if asof else date.fromisoformat(g["day"].max())
    ages = np.array([(ref - date.fromisoformat(d)).days for d in g["day"]], dtype=float)
    w = 0.5 ** (ages / half_life)
    # a new season resets rosters: last season's games count `carry` times as much on top of the decay
    s_now = (ref.year + 1) if ref.month >= 8 else ref.year
    w = w * carry ** (s_now - g["season"].astype(int).to_numpy())
    keep = w > 0.01
    g, w = g[keep], w[keep]
    m = len(g)
    hi = g["home"].map(IDX).to_numpy()
    ai = g["away"].map(IDX).to_numpy()
    neu = g["neutral"].fillna(0).astype(float).to_numpy()
    yh = g[hc].astype(float).to_numpy()
    ya = g[ac].astype(float).to_numpy()
    # rows: home scoring then away scoring.  columns: mu, home, att[N], def[N]
    P = 2 + 2 * N
    X = np.zeros((2 * m, P))
    X[:, 0] = 1
    X[:m, 1] = 0.5 * (1 - neu)
    X[m:, 1] = -0.5 * (1 - neu)
    r = np.arange(m)
    X[r, 2 + hi] = 1
    X[r, 2 + N + ai] = -1
    X[m + r, 2 + ai] = 1
    X[m + r, 2 + N + hi] = -1
    y = np.concatenate([yh, ya])
    ww = np.concatenate([w, w])
    XtW = X.T * ww
    A = XtW @ X
    pen = np.zeros(P)
    pen[2:] = lam
    A[np.diag_indices(P)] += pen
    beta = np.linalg.solve(A, XtW @ y)
    res = y - X @ beta
    sd = float(np.sqrt(np.sum(ww * res ** 2) / np.sum(ww)))
    return Rating(beta[0], beta[1], beta[2:2 + N], beta[2 + N:], m, sd)


def predict_game(rt, home, away, neutral=False):
    hp = rt.expect(home, away, True, neutral)
    ap = rt.expect(away, home, False, neutral)
    return hp, ap


def walk_forward(games, start_after_days=20, half_life=90.0, lam=6.0, step=7, carry=0.6):
    """Out-of-sample base prediction for every finished game: refit weekly on everything before it.
    Returns {game_id: (home_pts, away_pts)}."""
    games = games.sort_values("day")
    if not len(games):
        return {}
    first = date.fromisoformat(games["day"].min())
    days = sorted(set(games["day"]))
    out = {}
    i = 0
    cut = None
    while i < len(days):
        d0 = date.fromisoformat(days[i])
        if (d0 - first).days < start_after_days:
            i += 1
            continue
        cut = days[i]
        end = date.fromordinal(d0.toordinal() + step).isoformat()
        rt = fit(games, "pts", asof=cut, half_life=half_life, lam=lam, carry=carry)
        chunk = games[(games["day"] >= cut) & (games["day"] < end)]
        if rt is not None:
            for gid, h, a, n in zip(chunk["game_id"], chunk["home"], chunk["away"], chunk["neutral"].fillna(0)):
                out[str(gid)] = predict_game(rt, h, a, bool(n))
        while i < len(days) and days[i] < end:
            i += 1
    return out
