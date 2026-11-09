"""Adjusted plus-minus from game results and minutes (a game-level "RAPM").

Plain plus-minus credits a bench player for his starters' work. Here every game is one equation:
    home margin (per 48 min) = home court + sum(home players' minutes share x rating) - sum(away ...)
solved for all players at once with a ridge penalty (ratings pulled towards 0 until the data says otherwise),
games weighted by recency. Because each player's rating is estimated alongside his teammates' and
opponents', sharing the floor with stars no longer inflates it.

Walk-forward: refitted every REFIT_DAYS on games before that date only.
"""
from collections import defaultdict
from datetime import date

import numpy as np

LAM = 30.0           # ridge, tuned walk-forward on 2024-25 / 2025-26 (100-1500 were worse)
HL_DAYS = 240.0      # recency half-life
SEASON_KEEP = 0.6    # older seasons count less on top of recency
REFIT_DAYS = 7


def _d(s):
    return date.fromisoformat(str(s)[:10])


class RAPM:
    """Recency weights are exponential in the game date, so the weighted sums can be kept up to date
    game by game (each game's weight relative to a fixed reference); a refit is then one solve."""
    CAP = 2048

    def __init__(self, lam=LAM, hl=HL_DAYS):
        self.lam, self.hl = lam, hl
        self.pid = {}                       # player -> column (0 is home court)
        self.A = np.zeros((self.CAP, self.CAP))
        self.b = np.zeros(self.CAP)
        self.sum_k, self.n = 0.0, 0
        self.ref = None                     # (reference date, reference season)
        self.mins = defaultdict(float)
        self.r = {}
        self.hca = 0.0
        self.default = 0.0                  # rating for a player with no minutes yet (what newcomers tend to be)
        self.fit_day = None

    def _col(self, k):
        if k not in self.pid:
            if len(self.pid) + 2 >= len(self.b):  # grow
                n = len(self.b) * 2
                A = np.zeros((n, n)); A[:len(self.b), :len(self.b)] = self.A
                b = np.zeros(n); b[:len(self.b)] = self.b
                self.A, self.b = A, b
            self.pid[k] = len(self.pid) + 1
        return self.pid[k]

    def add(self, g, rows_home, rows_away):
        def shares(rows):
            out = {}
            for r in rows:
                m = float(r.get("min") or 0)
                if m > 0:
                    out[str(r["player_id"])] = m
            return out
        h, a = shares(rows_home), shares(rows_away)
        if not h or not a:
            return
        for k, v in list(h.items()) + list(a.items()):
            self.mins[k] += v
        ot = int(g.get("ot") or 0)
        y = (g["home_pts"] - g["away_pts"]) * 48.0 / (48.0 + 5.0 * ot)
        sh, sa = sum(h.values()), sum(a.values())
        idx = [0] + [self._col(k) for k in h] + [self._col(k) for k in a]
        val = np.array([0.0 if g.get("neutral") else 1.0] + [5 * v / sh for v in h.values()] + [-5 * v / sa for v in a.values()])
        d, s = _d(g["day"]), int(g["season"])
        if self.ref is None:
            self.ref = (d, s)
        k = 2.0 ** ((d - self.ref[0]).days / self.hl) * SEASON_KEEP ** (-(s - self.ref[1]))
        ix = np.array(idx)
        self.A[np.ix_(ix, ix)] += k * np.outer(val, val)
        self.b[ix] += k * y * val
        self.sum_k += k
        self.n += 1

    def fit(self, asof=None):
        if self.n < 400:
            return
        p = len(self.pid) + 1
        A = self.A[:p, :p].copy()
        A[np.arange(1, p), np.arange(1, p)] += self.lam * self.sum_k / self.n
        sol = np.linalg.solve(A + 1e-6 * self.sum_k / self.n * np.eye(p), self.b[:p])
        self.hca = float(sol[0])
        self.r = {k: float(sol[j]) for k, j in self.pid.items()}
        low = [self.r[k] for k, m in self.mins.items() if m < 300]
        if len(low) >= 30:
            self.default = float(np.mean(low))
        self.fit_day = _d(asof) if asof else None

    def maybe_refit(self, day):
        d = _d(day)
        if self.fit_day is None or (d - self.fit_day).days >= REFIT_DAYS:
            self.fit(d)

    def strength(self, players):
        """players: list of (pid, minutes). Minutes-weighted rating sum, scaled to five players on court."""
        if not self.r:
            return None
        tot = sum(m for _, m in players) or 1.0
        return sum(self.r.get(str(pid), self.default) * 5 * m / tot for pid, m in players)
