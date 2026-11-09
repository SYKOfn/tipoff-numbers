"""Play-style matchups and shooting luck, from team box scores (pre-game, recency-weighted).

Ratings already say how good each team is. These ask second-order questions:
- does a strong offensive-rebounding team gain extra against a poor defensive-rebounding one (and the
  same for turnovers forced vs committed, threes taken vs allowed, free throws drawn vs allowed)?
- has a team's recent record been inflated or deflated by three-point shooting luck (its own 3P% and
  what opponents shot against it, versus the league)? Luck should not carry forward.
- for totals: two fast teams together, both teams' three-point volume, recent opponent hot shooting.
Each is measured like every other factor and kept only if it improves out-of-sample tests.
"""
from collections import defaultdict

HL = 20          # games
LUCK_HL = 10     # games
CARRY = 0.5      # weight kept at a new season
MIN_GAMES = 10   # per team before the features switch on

KEYS = ["pace", "tpa", "tpa_alw", "orb", "orb_alw", "tov", "tov_frc", "ftr", "ftr_alw", "luck_own", "luck_opp"]
MARGIN_F = ["orb_match", "tov_match", "three_match", "ft_match", "luck"]
TOTAL_F = ["pace_match", "three_volume", "luck_total"]


def _box(g, side):
    p = "h_" if side == "home" else "a_"
    o = "a_" if side == "home" else "h_"
    try:
        v = {k: float(g[p + k]) for k in ("fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "reb", "tov")}
        w = {k: float(g[o + k]) for k in ("fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "reb", "tov")}
    except (TypeError, ValueError, KeyError):
        return None
    if any(x != x for x in list(v.values()) + list(w.values())) or v["fga"] <= 0 or w["fga"] <= 0:
        return None
    return v, w


class StyleTracker:
    def __init__(self):
        self.s = defaultdict(dict)      # team -> key -> (sum, weight)
        self.n = defaultdict(int)
        self.season = {}
        self.lg = {}                    # league running means

    def _add(self, team, key, val, hl):
        a = 0.5 ** (1 / hl)
        s = self.s[team].get(key, (0.0, 0.0))
        self.s[team][key] = (s[0] * a + val, s[1] * a + 1.0)

    def _get(self, team, key):
        s = self.s[team].get(key)
        return s[0] / s[1] if s and s[1] else None

    def _lg(self, key, val=None):
        if val is not None:
            s = self.lg.get(key, (0.0, 0.0))
            a = 0.5 ** (1 / 600)
            self.lg[key] = (s[0] * a + val, s[1] * a + 1.0)
        s = self.lg.get(key)
        return s[0] / s[1] if s and s[1] else None

    def features(self, g):
        h, a = g["home"], g["away"]
        if self.n[h] < MIN_GAMES or self.n[a] < MIN_GAMES or not self.lg:
            return None
        H = {k: self._get(h, k) for k in KEYS}
        A = {k: self._get(a, k) for k in KEYS}
        L = {k: self._lg(k) for k in KEYS}
        if None in H.values() or None in A.values() or None in L.values():
            return None

        def match(off, dfn, scale):
            # home offence style x away defence weakness, minus the reverse
            return ((H[off] - L[off]) * (A[dfn] - L[dfn]) - (A[off] - L[off]) * (H[dfn] - L[dfn])) * scale

        pace_l = L["pace"]
        return {
            "orb_match": match("orb", "orb_alw", 1000),
            "tov_match": match("tov_frc", "tov", 1000),
            "three_match": match("tpa", "tpa_alw", 1000),
            "ft_match": match("ftr", "ftr_alw", 1000),
            "luck": (H["luck_own"] - H["luck_opp"]) - (A["luck_own"] - A["luck_opp"]),
            "luck_off": H["luck_own"] - A["luck_own"],
            "luck_def": A["luck_opp"] - H["luck_opp"],
            "pace_match": (H["pace"] - pace_l) * (A["pace"] - pace_l) / 10,
            "three_volume": (H["tpa"] + A["tpa"] + H["tpa_alw"] + A["tpa_alw"] - 4 * L["tpa"]) * 10,
            "luck_total": H["luck_own"] + H["luck_opp"] + A["luck_own"] + A["luck_opp"],
        }

    def post_game(self, g):
        for side, team in (("home", g["home"]), ("away", g["away"])):
            b = _box(g, side)
            if b is None:
                continue
            v, w = b
            s = int(g["season"])
            if self.season.get(team) not in (None, s):
                for k, (x, y) in list(self.s[team].items()):
                    self.s[team][k] = (x * CARRY, y * CARRY)
            self.season[team] = s
            poss = v["fga"] - v["oreb"] + v["tov"] + 0.44 * v["fta"]
            opp_poss = w["fga"] - w["oreb"] + w["tov"] + 0.44 * w["fta"]
            dreb_w = w["reb"] - w["oreb"]
            dreb_v = v["reb"] - v["oreb"]
            lg3 = self._lg("p3") or 0.36
            vals = {
                "pace": (poss + opp_poss) / 2,
                "tpa": v["tpa"] / v["fga"], "tpa_alw": w["tpa"] / w["fga"],
                "orb": v["oreb"] / max(v["oreb"] + dreb_w, 1), "orb_alw": w["oreb"] / max(w["oreb"] + dreb_v, 1),
                "tov": v["tov"] / max(poss, 1), "tov_frc": w["tov"] / max(opp_poss, 1),
                "ftr": v["fta"] / v["fga"], "ftr_alw": w["fta"] / w["fga"],
                # points above or below league-average three-point shooting on the same attempts
                "luck_own": 3 * (v["tpm"] - lg3 * v["tpa"]), "luck_opp": 3 * (w["tpm"] - lg3 * w["tpa"]),
            }
            for k, x in vals.items():
                self._add(team, k, x, LUCK_HL if k.startswith("luck") else HL)
                if not k.startswith("luck"):
                    self._lg(k, x)
            self._lg("luck_own", 0.0)
            self._lg("luck_opp", 0.0)
            if v["tpa"] > 0:
                self._lg("p3", v["tpm"] / v["tpa"])
            self.n[team] += 1
