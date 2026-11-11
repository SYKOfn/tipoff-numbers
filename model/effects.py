"""Adjustments on top of the base ratings: physical context and the psychological layer.

Each factor is a number per game from the home team's point of view (home situation minus away
situation). Its size in points is MEASURED, not assumed: a penalised regression of what the base
ratings got wrong (actual margin - base margin) on all factors at once, over every past game.
A factor history says nothing about ends up near 0 and is labelled "no evidence".
"""
import math

import numpy as np

# key: (layer, label, what it means, transform(home_side, away_side, game) -> value)
MARGIN = {
    # ---- physical
    "b2b": ("physical", "Back-to-back", "played the night before", lambda f: f["b2b"]),
    "three_in_four": ("physical", "3 games in 4 nights", "third game in four nights", lambda f: f["three_in_four"]),
    "rest": ("physical", "Rest days", "per day off since the last game (0-3)", lambda f: min(f["rest"], 3)),
    "tz_east": ("physical", "Body clock", "per hour of time zones crossed heading east", lambda f: f["tz_east"]),
    "travel": ("physical", "Travel", "per 1,000 km travelled since the last game", lambda f: f["km"] / 1000),
    "luck": ("physical", "Shooting luck", "per point a game the team (and its opponents) shot threes above or below league average lately; luck does not last",
             lambda f: f.get("luck", 0.0)),
    "missing": ("physical", "Missing players", "if the whole regular rotation's production were missing (scaled by the share out)",
                lambda f: f["missing"]),
    # ---- psychological
    "streak": ("mind", "Streak", "per 5 straight wins (losing streaks count negative)",
               lambda f: max(-10, min(10, f["streak"])) / 5),
    "confidence": ("mind", "Confidence", "per 10 points the last 5 games beat expectations",
                   lambda f: f["confidence"] / 10),
    "bounce": ("mind", "Bounce-back", "lost the previous game by 20 or more", lambda f: f["bounce"]),
    "letdown": ("mind", "Letdown", "beat a top team last time out, now face a weak one", lambda f: f["letdown"]),
    "revenge": ("mind", "Revenge", "lost the last meeting between these teams this season", lambda f: f["revenge"]),
    "lookahead": ("mind", "Look-ahead", "weak opponent now, a top team within two days", lambda f: f["lookahead"]),
    "homecoming": ("mind", "Homecoming", "first home game after a road trip of 4+", lambda f: f["homecoming"]),
    "road_long": ("mind", "Long road trip", "4th or later straight road game", lambda f: f["road_long"]),
    "stakes": ("mind", "Stakes", "late season: in a race for a seed (+1) or nothing left to play for (-1)",
               lambda f: f["stakes"]),
    "elimination": ("mind", "Facing elimination", "playoffs: one more loss ends the season", lambda f: f["elimination"]),
    # ---- style matchups (second-order: does this team's style exploit the opponent's weakness?)
    "orb_match": ("physical", "Rebounding matchup", "offensive rebounding strength against the opponent's defensive rebounding weakness, net of the reverse",
                  lambda f: f.get("style_orb_match", 0.0)),
    "tov_match": ("physical", "Turnover matchup", "ball security against the opponent's ability to force turnovers, net of the reverse",
                  lambda f: f.get("style_tov_match", 0.0)),
    "three_match": ("physical", "Three-point volume matchup", "three-point attempt rate against the opponent's rate allowed, net of the reverse",
                    lambda f: f.get("style_three_match", 0.0)),
    "ft_match": ("physical", "Free-throw matchup", "free-throw rate against the opponent's rate allowed, net of the reverse",
                 lambda f: f.get("style_ft_match", 0.0)),
    "pass_match": ("physical", "Ball movement matchup", "assist rate against the opponent's rate allowed, net of the reverse",
                   lambda f: f.get("style_pass_match", 0.0)),
    "rim_match": ("physical", "Rim protection matchup", "block rate against the opponent's rate allowed, net of the reverse",
                  lambda f: f.get("style_rim_match", 0.0)),
}
TOTAL = {
    "b2b_sum": ("physical", "Tired legs", "teams on a back-to-back", lambda h, a, g: h["b2b"] + a["b2b"]),
    "missing_sum": ("physical", "Missing players", "production unavailable, both teams",
                    lambda h, a, g: h["missing"] + a["missing"]),
    "rivalry": ("mind", "Division rivalry", "division opponents", lambda h, a, g: g["rivalry"]),
    "playoff": ("mind", "Playoff intensity", "playoff game", lambda h, a, g: g["playoff"]),
    "no_stakes": ("mind", "Nothing to play for", "teams with nothing left to play for",
                  lambda h, a, g: int(h["stakes"] < 0) + int(a["stakes"] < 0)),
    "pace_match": ("physical", "Pace matchup", "two fast (or two slow) teams meeting", lambda h, a, g: g.get("style_pace_match", 0.0)),
    "three_volume": ("physical", "Three-point volume", "both teams' combined three-point attempt rate above league average",
                      lambda h, a, g: g.get("style_three_volume", 0.0)),
    "luck_total": ("physical", "Shooting luck (total)", "both teams' recent three-point luck, own and allowed, combined",
                   lambda h, a, g: g.get("style_luck_total", 0.0)),
}


from . import officials as _officials
if _officials.ON:
    TOTAL["refs"] = ("physical", "Referee crew", "points a game this crew's games have finished above (or below) the expected total",
                     lambda h, a, g: g.get("refs_total", 0.0))

from . import lineup as _lineup
if _lineup.PACE_TOTAL_ON:
    TOTAL["pace_corr"] = ("physical", "Possession-based total check", "a pace x efficiency total estimate, against the per-stat rating's total, when the two disagree",
                          lambda h, a, g: g.get("pace_corr", 0.0))


def own(ctx_side):
    """Each margin factor's value for one team (its effect on that team's own margin)."""
    return np.array([f[3](ctx_side) for f in MARGIN.values()], dtype=float)


def vector(spec, ctx):
    if spec is MARGIN:
        return own(ctx["home"]) - own(ctx["away"])
    return np.array([f[3](ctx["home"], ctx["away"], ctx) for f in spec.values()], dtype=float)


def fit(X, y, lam):
    """Ridge without intercept. Returns coef, standard error, active count per column."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, p = X.shape
    scale = np.maximum((X ** 2).mean(axis=0), 1e-4)  # penalty in "typical games of evidence", whatever a column's units
    A = X.T @ X + lam * np.diag(scale)
    coef = np.linalg.solve(A, X.T @ y)
    res = y - X @ coef
    s2 = float(res @ res) / max(n - p, 1)
    try:
        cov = s2 * np.linalg.inv(X.T @ X + 1e-6 * np.eye(p))
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        se = np.full(p, np.nan)
    active = (np.abs(X) > 1e-9).sum(axis=0)
    return coef, se, active, math.sqrt(s2)


def evidence(coef, se):
    if se is None or not np.isfinite(se) or se == 0:
        return "none"
    t = abs(coef / se)
    return "strong" if t >= 3 else "moderate" if t >= 2 else "weak" if t >= 1 else "none"


class Effects:
    def __init__(self, cm, sem, actm, cs, set_, actt, sd_margin, sd_total, n):
        self.cm, self.sem, self.actm = cm, sem, actm
        self.ct, self.set, self.actt = cs, set_, actt
        self.sd_margin, self.sd_total, self.n = sd_margin, sd_total, n
        self.sdm_ab = None  # (a, b): margin spread = (a + b x |expected margin|) / sqrt(2/pi)

    def sd_for(self, margin):
        """Spread of the final margin around this game's estimate. Tested on 2023-24 to this season:
        lopsided games are slightly less uncertain than close ones (better handicap and win chances)."""
        if not self.sdm_ab:
            return self.sd_margin
        a, b = self.sdm_ab
        return float(max(0.7 * self.sd_margin, min(1.3 * self.sd_margin, (a + b * abs(margin)) / np.sqrt(2 / np.pi))))

    def table(self):
        rows = []
        for spec, c, se, act, target in ((MARGIN, self.cm, self.sem, self.actm, "margin"),
                                         (TOTAL, self.ct, self.set, self.actt, "total")):
            for (k, f), ci, si, ai in zip(spec.items(), c, se, act):
                rows.append({"key": k, "target": target, "layer": f[0], "label": f[1], "means": f[2],
                             "pts": round(float(ci), 2), "se": round(float(si), 2) if np.isfinite(si) else None,
                             "n": int(ai), "evidence": evidence(ci, si)})
        return rows

    def to_json(self):
        return {"margin": dict(zip(MARGIN, map(float, self.cm))), "margin_se": dict(zip(MARGIN, map(float, self.sem))),
                "margin_n": dict(zip(MARGIN, map(int, self.actm))),
                "total": dict(zip(TOTAL, map(float, self.ct))), "total_se": dict(zip(TOTAL, map(float, self.set))),
                "total_n": dict(zip(TOTAL, map(int, self.actt))),
                "sd_margin": self.sd_margin, "sd_total": self.sd_total, "n": self.n, "sdm_ab": self.sdm_ab}

    @classmethod
    def from_json(cls, j):
        return cls(np.array([j["margin"].get(k, 0) for k in MARGIN]), np.array([j["margin_se"].get(k, np.nan) for k in MARGIN]),
                   np.array([j["margin_n"].get(k, 0) for k in MARGIN]),
                   np.array([j["total"].get(k, 0) for k in TOTAL]), np.array([j["total_se"].get(k, np.nan) for k in TOTAL]),
                   np.array([j["total_n"].get(k, 0) for k in TOTAL]), j["sd_margin"], j["sd_total"], j["n"])

    @classmethod
    def from_json_full(cls, j):
        e = cls.from_json(j)
        e.sdm_ab = tuple(j["sdm_ab"]) if j.get("sdm_ab") else None
        return e


def estimate(rows, lam=150.0):
    """rows: list of (ctx, actual_margin, base_margin, actual_total, base_total)."""
    if len(rows) < 200:
        p, q = len(MARGIN), len(TOTAL)
        return Effects(np.zeros(p), np.full(p, np.nan), np.zeros(p), np.zeros(q), np.full(q, np.nan), np.zeros(q), 12.5, 18.0, len(rows))
    Xm = np.array([vector(MARGIN, r[0]) for r in rows])
    Xt = np.array([vector(TOTAL, r[0]) for r in rows])
    ym = np.array([r[1] - r[2] for r in rows])
    yt = np.array([r[3] - r[4] for r in rows])
    cm, sem, am, sdm = fit(Xm, ym, lam)
    ct, set_, at, sdt = fit(Xt, yt, lam)
    e = Effects(cm, sem, am, ct, set_, at, sdm, sdt, len(rows))
    pred = np.array([r[2] for r in rows]) + Xm @ cm
    res = np.array([r[1] for r in rows]) - pred
    A = np.c_[np.ones(len(pred)), np.abs(pred)]
    a, b = np.linalg.lstsq(A, np.abs(res), rcond=None)[0]
    e.sdm_ab = (float(a), float(b))
    return e


def contributions(eff, ctx):
    """Per-factor points for one game: each team's own boost on the margin, and effects on the total."""
    oh, oa = own(ctx["home"]), own(ctx["away"])
    out = []
    for (k, f), vh, va, c in zip(MARGIN.items(), oh, oa, eff.cm):
        out.append({"key": k, "target": "margin", "layer": f[0], "label": f[1], "home_value": round(float(vh), 3),
                    "away_value": round(float(va), 3), "home_pts": round(float(vh * c), 2), "away_pts": round(float(va * c), 2),
                    "pts": round(float((vh - va) * c), 2)})
    for (k, f), v, c in zip(TOTAL.items(), vector(TOTAL, ctx), eff.ct):
        out.append({"key": k, "target": "total", "layer": f[0], "label": f[1], "value": round(float(v), 3),
                    "pts": round(float(v * c), 2)})
    return out


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
