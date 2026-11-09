"""Player projections for every player, and the player-level psychology.

projection = expected minutes x per-minute rate x opponent factor x (1 + measured player effects)

- Minutes: recent minutes (recency-weighted over games played), plus a share of the minutes left by
  teammates who are out.
- Rates: per-minute production, recency-weighted, pulled towards the average for the position
  until the player has enough minutes.
- Opponent: what the opponent has allowed per game in that stat versus the league (half-shrunk).
- Player effects, measured on every past player-game (what the projection missed, regressed on all
  of them at once, penalised towards 0): facing a former team, first games back from a long absence,
  hot/cold form, final contract year (from the notes file), teammates out (usage), back-to-backs, home.
"""
import math
from collections import defaultdict, deque

import numpy as np

from . import effects as eff_mod

STATS = ["pts", "reb", "ast", "tpm", "stl", "blk", "tov", "fgm", "fga", "ftm", "fta"]
SHOW = ["pts", "reb", "ast", "tpm", "stl", "blk", "tov"]
LABEL = {"pts": "Points", "reb": "Rebounds", "ast": "Assists", "tpm": "Threes", "stl": "Steals", "blk": "Blocks",
         "tov": "Turnovers", "pra": "Pts+Reb+Ast", "min": "Minutes"}
MIN_HL = 8          # games, minutes
RATE_HL = 30        # games, per-minute rates
K_PRIOR = 150.0     # minutes of prior on rates
BACK_GAP = 8        # team games missed = a long absence
BACK_GAMES = 3      # first games back count as "returning"

FACTORS = {
    "former_team": ("mind", "Former team", "facing a team he played for in the stored seasons"),
    "returning": ("physical", "Back from absence", "first 3 games after missing 8+ team games"),
    "hot": ("mind", "Hot / cold hand", "per 10% his last 5 games beat (or missed) the projection"),
    "contract_year": ("mind", "Contract year", "final year of his contract (from the notes file)"),
    "usage": ("physical", "Teammates out", "per 10% of the team's regular production missing"),
    "vs_opp": ("mind", "Matchup history", "per 10% he beat (or missed) his projection in past games against this opponent"),
    "without": ("physical", "Without a key teammate", "per 10% he has beaten (or missed) his projection in past games without the teammates who are out today"),
    "without_min": ("physical", "Minutes without a key teammate", "per 10% more (or fewer) minutes than projected in past games without those teammates"),
    "b2b": ("physical", "Back-to-back", "second night of a back-to-back"),
    "home": ("physical", "Home floor", "home game"),
}
EFFECT_STATS = ["min", "pts", "reb", "ast"]
# Applied only where out-of-sample tests (fit on earlier seasons, scored on the next) showed a gain.
# "Teammates out" and "home" are still measured and shown, but the minutes model already covers the first,
# and applying either made projections worse. The overall bias term helps points only.
APPLY = {"hot", "vs_opp", "returning", "former_team", "contract_year", "b2b", "without", "without_min"}
ONLY_FOR = {"without": {"pts", "min"}, "without_min": {"pts", "min"}}  # tested: helped points and minutes, not rebounds/assists
KEY_TEAMMATE_MIN = 26.0  # a teammate whose absence is tracked
WO_K = 4.0               # shrinkage: games of evidence needed for half weight
BIAS_STATS = {"pts"}


MIN_FEATS = ["const", "m8", "m3", "season", "last", "started", "gain_same", "gain_other", "blowout", "b2b",
             "returning", "new", "crowd", "early_m8", "early_season"]
MIN_LAM = 50.0
MIN_REFIT = 150     # refit after this many new player-games


def pos_group(pos):
    p = (pos or "").upper()
    return "C" if "C" in p else "G" if "G" in p else "F"


class MinutesModel:
    """Expected minutes for a player who plays: a ridge regression on pre-game facts, fitted online on
    every past player-game only (walk-forward, so it never sees the game it predicts)."""

    def __init__(self):
        k = len(MIN_FEATS)
        self.xtx = np.zeros((k, k))
        self.xty = np.zeros(k)
        self.n = 0
        self.since = 0
        self.w = None

    def add(self, f, y):
        x = np.asarray(f, float)
        self.xtx += np.outer(x, x)
        self.xty += x * y
        self.n += 1
        self.since += 1
        if self.n >= 3000 and (self.w is None or self.since >= MIN_REFIT):
            lam = np.eye(len(x)) * MIN_LAM
            lam[0, 0] = 0.0
            self.w = np.linalg.solve(self.xtx + lam, self.xty)
            self.since = 0

    def predict(self, f):
        return None if self.w is None else float(np.dot(self.w, f))

    def table(self):
        return None if self.w is None else {k: round(float(v), 3) for k, v in zip(MIN_FEATS, self.w)}


def ew_add(state, key, value, hl):
    a = 0.5 ** (1 / hl)
    s = state.get(key, (0.0, 0.0))
    state[key] = (s[0] * a + value, s[1] * a + 1.0)


def ew_get(state, key):
    s = state.get(key)
    return None if not s or s[1] == 0 else s[0] / s[1]


class PlayerTracker:
    def __init__(self):
        self.p = {}                                   # pid -> dict
        self.team_games = defaultdict(int)            # team -> games played
        self.team_hist = defaultdict(lambda: deque(maxlen=12))  # team -> deque of set(pids who played)
        self.allowed = defaultdict(dict)              # team -> ew state of what opponents produced per stat
        self.league = {}                              # ew of team production per stat
        self.pos_rate = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # pos -> stat -> [sum, min]
        self.allowed_pos = defaultdict(dict)          # team -> (pos group, stat) -> (sum, minutes), recency-weighted
        self.league_pos = {}
        self.opp_mode = "team"                        # "team": team allowed only; "pos": by position group, blended
        self.mm = MinutesModel()
        self.use_mm = True
        self.last_mf = None

    # ------------------------------------------------------------ player state
    def get(self, pid, name=None, pos=None):
        if pid not in self.p:
            self.p[pid] = {"name": name, "pos": pos, "team": None, "teams": [], "ew_min": {}, "rate": {},
                           "last_team_game": {}, "missed": 0, "back_left": 0, "recent": deque(maxlen=5), "gp": 0,
                           "ew3": {}, "last_min": None, "started": 0, "smin": [0.0, 0]}
        q = self.p[pid]
        if name:
            q["name"] = name
        if pos:
            q["pos"] = pos
        return q

    def prior(self, pos, stat):
        s = self.pos_rate[pos or "?"][stat]
        if s[1] < 500:
            s = self.pos_rate["ALL"][stat]
        return s[0] / s[1] if s[1] else 0.0

    def rate(self, q, stat):
        num, den = q["rate"].get(stat, (0.0, 0.0))
        mins = q["rate"].get("_min_" + stat, q["rate"].get("_min", (0.0, 0.0)))[0]
        pr = self.prior(q["pos"], stat)
        return (num + pr * K_PRIOR) / (mins + K_PRIOR) if (mins + K_PRIOR) else pr

    def opp_factor(self, opp, stat):
        lg = ew_get(self.league, stat)
        al = ew_get(self.allowed[opp], stat)
        if not lg or al is None:
            return 1.0
        return 1.0 + 0.5 * (al / lg - 1.0)

    def opp_factor_pos(self, opp, pos, stat):
        """What players at this position have produced per minute against this team, versus the league."""
        g = pos_group(pos)
        a = self.allowed_pos[opp].get((g, stat))
        l = self.league_pos.get((g, stat))
        if not a or not l or a[1] < 400 or l[1] <= 0 or l[0] <= 0:
            return None
        return 1.0 + 0.5 * ((a[0] / a[1]) / (l[0] / l[1]) - 1.0)

    def rotation(self, team):
        """Players currently on the team with recent minutes."""
        out = {}
        for pid, q in self.p.items():
            if q["team"] != team:
                continue
            m = ew_get(q["ew_min"], "m")
            if m is None:
                continue
            gap = self.team_games[team] - q["last_team_game"].get(team, -99)
            if gap <= 15 and m >= 4:
                out[pid] = m
        return out

    # ------------------------------------------------------------ projection
    def min_features(self, pid, team, rot, absent, avail_of, exp_margin, b2b, returning):
        q = self.p[pid]
        m8 = ew_get(q["ew_min"], "m") or 0.0
        m3 = ew_get(q["ew3"], "m") or m8
        sm = q["smin"][0] / q["smin"][1] if q["smin"][1] else m8
        early = max(0.0, 1.0 - q["smin"][1] / 10.0)  # first games of a season: last season counts less
        last = q["last_min"] if q["last_min"] is not None else m8
        g = pos_group(q["pos"])
        gain = {"same": 0.0, "other": 0.0}
        for kind in ("same", "other"):
            same = lambda k: (pos_group(self.p[k]["pos"]) == g) == (kind == "same")
            lost = sum(v * avail_of(k) for k, v in rot.items() if k in absent and same(k))
            here = sum(v * avail_of(k) for k, v in rot.items() if k not in absent and same(k)) or 1.0
            gain[kind] = lost * m8 / here
        here_all = sum(v * avail_of(k) for k, v in rot.items() if k not in absent)
        heavy = m8 / 30.0
        return [1.0, m8, m3, sm, last, float(q["started"]), gain["same"], gain["other"],
                abs(exp_margin or 0.0) / 10.0 * heavy, float(b2b) * heavy, float(returning),
                float(q["gp"] < 10), (here_all / 240.0 - 1.0) * m8, early * m8, early * sm]

    def project(self, pid, team, opp, is_home, b2b, absent=(), missing_share=0.0, notes=None, eff=None, extra_min=None,
                exp_margin=None):
        """absent: pids of teammates out. Returns dict of projections and the factor values."""
        q = self.p[pid]
        m = ew_get(q["ew_min"], "m") or 0.0
        rot = self.rotation(team)
        # only minutes the team has actually been getting from the absent players are up for grabs
        recent = list(self.team_hist[team])[-5:]
        avail_of = lambda k: (sum(k in s for s in recent) / len(recent)) if recent else 1.0
        miss_min = sum(v * avail_of(k) for k, v in rot.items() if k in absent)
        avail = {k: v for k, v in rot.items() if k not in absent}
        tot = sum(avail.values()) or 1.0
        if extra_min is None:
            # no hand-made redistribution: the measured "teammates out" effect below does that job
            # (a fixed rule over-projected minutes by ~2.5 a game on real data)
            extra_min = 0.0
        mins = min(42.0, m + extra_min)
        gap0 = self.team_games[team] - q["last_team_game"].get(team, self.team_games[team])
        returning = int(q["back_left"] > 0 or (gap0 >= BACK_GAP and q["gp"] > 5))
        self.last_mf = self.min_features(pid, team, rot, set(absent), avail_of, exp_margin, b2b, returning)
        pm = self.mm.predict(self.last_mf) if self.use_mm else None
        if pm is not None:
            mins = max(0.0, min(44.0, pm))
        recent = list(q["recent"])
        hot = 0.0
        if len(recent) >= 3:
            a = sum(r[0] for r in recent)
            p = sum(r[1] for r in recent)
            hot = max(-0.6, min(0.6, (a / p - 1.0))) if p > 5 else 0.0
        former = int(opp in q["teams"] and opp != team)
        gap = self.team_games[team] - q["last_team_game"].get(team, self.team_games[team])
        x = {"former_team": former, "returning": int(q["back_left"] > 0 or (gap >= BACK_GAP and q["gp"] > 5)), "hot": hot / 0.1,
             "contract_year": int(bool((notes or {}).get("contract_year"))), "usage": missing_share / 0.1,
             "vs_opp": self.vs_opp(q, opp), "without": 0.0, "without_min": 0.0, "b2b": int(b2b), "home": int(is_home)}
        wo = self.without_feats(pid, absent)
        x["without"], x["without_min"] = wo
        mult = {}
        for st in EFFECT_STATS:
            mult[st] = 1.0
            if eff and st in eff:
                mult[st] = max(0.5, min(1.6, 1.0 + (eff[st].get("bias", 0.0) if st in BIAS_STATS else 0.0)
                                        + sum(eff[st]["coef"][k] * v for k, v in x.items() if k in APPLY and st in ONLY_FOR.get(k, {st}) and usable(eff[st], k))))
        use = {"min": "min", "pts": "pts", "reb": "reb", "ast": "ast", "tpm": "pts", "fgm": "pts", "fga": "pts",
               "ftm": "pts", "fta": "pts", "stl": "min", "blk": "min", "tov": "min"}
        proj = {"min": mins * mult["min"]}
        for st in STATS:
            key_ = st if st in ("pts", "reb", "ast", "tpm") else "_"
            of = self.opp_factor(opp, key_)
            if self.opp_mode == "pos" and key_ != "_":
                fp = self.opp_factor_pos(opp, q["pos"], st)
                if fp is not None:
                    of = 0.5 * of + 0.5 * fp
            r = self.rate(q, st) * mins * of
            proj[st] = max(0.0, r * mult[use[st]])
        proj["pra"] = proj["pts"] + proj["reb"] + proj["ast"]
        return proj, x

    # ------------------------------------------------------------ record a game
    def post_game(self, g, rows_by_team, team_box=None):
        """rows_by_team: {team: [row dicts with player_id, name, pos, min, stats...]}"""
        h, a = g["home"], g["away"]
        for team in (h, a):
            self.team_games[team] += 1
            rows = rows_by_team.get(team) or []
            played = set()
            for r in rows:
                pid = str(r["player_id"])
                q = self.get(pid, r.get("name"), r.get("pos"))
                mn = float(r.get("min") or 0)
                if mn > 0 and q.get("season") != int(g["season"]):
                    # new season: roles change, so last season's numbers count much less
                    if q.get("season") is not None:
                        for stt in (q["ew_min"], q["rate"]):
                            for k, (a_, b_) in list(stt.items()):
                                stt[k] = (a_ * 0.2, b_ * 0.2)
                    q["season"] = int(g["season"])
                    q["smin"] = [0.0, 0]
                if q["team"] != team:
                    if q["team"] and q["team"] not in q["teams"]:
                        q["teams"].append(q["team"])
                    q["team"] = team
                if mn <= 0:
                    continue
                played.add(pid)
                gap = self.team_games[team] - 1 - q["last_team_game"].get(team, self.team_games[team] - 1)
                if gap >= BACK_GAP and q["gp"] > 5:
                    q["back_left"] = BACK_GAMES - 1
                elif q["back_left"] > 0:
                    q["back_left"] -= 1
                q["last_team_game"][team] = self.team_games[team]
                q["gp"] += 1
                ew_add(q["ew_min"], "m", mn, MIN_HL)
                ew_add(q["ew3"], "m", mn, 3)
                q["last_min"] = mn
                q["started"] = int(r.get("starter") == 1 or r.get("starter") is True)
                q["smin"][0] += mn
                q["smin"][1] += 1
                al = 0.5 ** (1 / RATE_HL)
                for k_ in list(q["rate"]):  # every stat's history decays once per game played
                    a_, b_ = q["rate"][k_]
                    q["rate"][k_] = (a_ * al, b_ * al)
                for st in STATS:
                    v = r.get(st)
                    if v is None:  # not recorded for this game: no information, not a zero
                        continue
                    s = q["rate"].get(st, (0.0, 0.0))
                    q["rate"][st] = (s[0] + float(v), s[1] + 1.0)
                    m_ = q["rate"].get("_min_" + st, (0.0, 0.0))
                    q["rate"]["_min_" + st] = (m_[0] + mn, m_[1] + 1.0)
                    for pos in (q["pos"] or "?", "ALL"):
                        acc = self.pos_rate[pos][st]
                        acc[0] += float(v)
                        acc[1] += mn
                s = q["rate"].get("_min", (0.0, 0.0))
                q["rate"]["_min"] = (s[0] + mn, s[1] + 1.0)
            self.team_hist[team].append(played)
        for team, opp in ((h, a), (a, h)):
            rows = [r for r in (rows_by_team.get(team) or []) if float(r.get("min") or 0) > 0]
            if not rows:
                continue
            dec = 0.5 ** (1 / 20)
            for k_, (a_, b_) in list(self.allowed_pos[opp].items()):
                self.allowed_pos[opp][k_] = (a_ * dec, b_ * dec)
            ld = 0.5 ** (1 / 300)  # league: per team-game
            for k_, (a_, b_) in list(self.league_pos.items()):
                self.league_pos[k_] = (a_ * ld, b_ * ld)
            for st in ("pts", "reb", "ast", "tpm"):
                if any(r.get(st) is None for r in rows):
                    continue
                for r in rows:
                    gk = (pos_group(r.get("pos")), st)
                    v_, m_ = float(r.get(st) or 0), float(r.get("min") or 0)
                    a_ = self.allowed_pos[opp].get(gk, (0.0, 0.0))
                    self.allowed_pos[opp][gk] = (a_[0] + v_, a_[1] + m_)
                    l_ = self.league_pos.get(gk, (0.0, 0.0))
                    self.league_pos[gk] = (l_[0] + v_, l_[1] + m_)
                v = sum(float(r.get(st) or 0) for r in rows)
                ew_add(self.allowed[opp], st, v, 20)
                ew_add(self.league, st, v, 300)

    def note_result(self, pid, actual_pts, proj_pts, opp=None):
        q = self.p[pid]
        q["recent"].append((actual_pts, proj_pts))
        if opp and proj_pts > 3:
            v = q.setdefault("vs", {}).get(opp, (0.0, 0.0))
            q["vs"][opp] = (v[0] + actual_pts, v[1] + proj_pts)

    def key_absent(self, team, absent):
        """Absent teammates who matter (26+ recent minutes)."""
        return [b for b in absent if b in self.p and (ew_get(self.p[b]["ew_min"], "m") or 0) >= KEY_TEAMMATE_MIN]

    def without_feats(self, pid, absent):
        """Shrunk ratio of actual to projected (points, minutes) in his past games without these teammates."""
        q = self.p.get(pid)
        if not q or not absent:
            return 0.0, 0.0
        tot = [0.0, 0.0, 0.0, 0.0, 0.0]
        for b in absent:
            w = (q.get("wo") or {}).get(b)
            if w:
                for i in range(5):
                    tot[i] += w[i]
        ap, pp, am, pm, n = tot
        if n <= 0 or pp <= 0 or pm <= 0:
            return 0.0, 0.0
        sh = n / (n + WO_K)
        return (max(-0.6, min(0.6, ap / pp - 1)) * sh / 0.1, max(-0.6, min(0.6, am / pm - 1)) * sh / 0.1)

    def note_without(self, pid, absent_keys, act_pts, proj_pts, act_min, proj_min):
        q = self.p[pid]
        wo = q.setdefault("wo", {})
        for b in absent_keys:
            w = wo.get(b, (0.0, 0.0, 0.0, 0.0, 0))
            wo[b] = (w[0] + act_pts, w[1] + proj_pts, w[2] + act_min, w[3] + proj_min, w[4] + 1)

    @staticmethod
    def vs_opp(q, opp):
        """Past points vs this opponent over what was projected, shrunk towards 0 (per 10%)."""
        v = (q.get("vs") or {}).get(opp)
        if not v or v[1] <= 0:
            return 0.0
        n = v[1] / 15.0  # roughly games
        return max(-0.5, min(0.5, v[0] / v[1] - 1.0)) * n / (n + 5) / 0.1


def usable(e, k):
    """Apply a player effect only with real support: 100+ games and at least moderate evidence."""
    se = e["se"].get(k)
    return bool(se) and e["n"].get(k, 0) >= 100 and abs(e["coef"][k] / se) >= 2


def sd_for(stat, proj, disp):
    return max(0.6, math.sqrt(max(proj, 0.3) * disp.get(stat, 1.5)))


def over_prob(stat, line, mu, disp):
    """P(count > line) with a negative binomial of mean mu and variance mu x dispersion (Poisson when the
    dispersion is ~1). Tested against the bell curve on 2024-25, 2025-26 and this season: lower log loss and
    Brier for points, rebounds and assists in every season, most on low lines."""
    mu = max(float(mu), 0.05)
    d = max(disp.get(stat, 1.5) if isinstance(disp, dict) else float(disp), 1.02)
    k_max = int(math.floor(line))
    if k_max < 0:
        return 1.0
    r = mu / (d - 1.0)
    q = 1.0 / d                    # success probability (scipy's p)
    pk = math.exp(r * math.log(q))  # P(X = 0)
    cdf = pk
    for k in range(k_max):
        pk *= (k + r) / (k + 1) * (1 - q)
        cdf += pk
    return max(0.0, min(1.0, 1.0 - cdf))


# The lines Winamax lists for NBA player markets ("X+" = over X - 0.5). Every player line on the site and in the
# tickets is one of these, so every leg can be placed as shown.
WINAMAX_LADDER = {
    "pts": [4.5 + 5 * k for k in range(12)],            # 4.5, 9.5, 14.5 ... 59.5
    "reb": [2.5, 4.5, 6.5, 9.5, 12.5, 14.5],
    "ast": [2.5, 4.5, 6.5, 9.5, 12.5, 14.5],
    "pra": [9.5 + 5 * k for k in range(12)],            # 9.5, 14.5, 19.5 ... 64.5
    "tpm": [0.5 + k for k in range(9)],                 # 0.5, 1.5 ... 8.5
}


def ladder(stat):
    return WINAMAX_LADDER.get(stat, [])


def near_lines(stat, center, below=2, above=2):
    """The Winamax lines around a projection: up to `below` under it and `above` over it."""
    lad = ladder(stat)
    lo = [L for L in lad if L < center][-below:] if below else []
    hi = [L for L in lad if L >= center][:above] if above else []
    return lo + hi


def lines_for(stat, proj, disp):
    out = []
    for L in near_lines(stat, proj, 2, 2):
        out.append({"line": L, "over": round(over_prob(stat, L, proj, disp), 3)})
    return out


def mu_for_over(stat, line, p_over, disp, lo=0.05, hi=120.0):
    """The mean at which P(count > line) equals p_over (to carry a book's chance at its own line to another line)."""
    p_over = min(max(p_over, 0.01), 0.99)
    for _ in range(50):
        mid = (lo + hi) / 2
        if over_prob(stat, line, mid, disp) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def estimate_effects(rows, lam=300.0):
    """rows: list of (x dict, {stat: (actual, proj)}). Relative effects: (actual - proj) / proj."""
    keys = list(FACTORS)
    out = {}
    for st in EFFECT_STATS:
        X, y, w = [], [], []
        for x, res in rows:
            if st not in res:
                continue
            act, pr = res[st]
            floor = 10.0 if st == "min" else 3.0
            if pr < floor:
                continue
            X.append([x[k] for k in keys] + [1.0])
            y.append((act - pr) / pr)
            w.append(math.sqrt(pr))
        if len(X) < 300:
            out[st] = {"coef": {k: 0.0 for k in keys}, "se": {k: None for k in keys}, "n": {k: 0 for k in keys}}
            continue
        X, y, w = np.array(X, float), np.array(y), np.array(w)
        Xw, yw = X * w[:, None], y * w
        coef, se, act, _ = eff_mod.fit(Xw, yw, lam)  # last column: overall bias, measured but not applied
        out[st] = {"coef": {k: float(c) for k, c in zip(keys, coef)},
                   "se": {k: (float(s) if np.isfinite(s) else None) for k, s in zip(keys, se)},
                   "n": {k: int(n) for k, n in zip(keys, (np.abs(X) > 1e-9).sum(axis=0))}, "bias": float(coef[-1])}
    return out


def effects_table(pe):
    rows = []
    for st, d in pe.items():
        for k, (layer, label, means) in FACTORS.items():
            c, s = d["coef"][k], d["se"][k]
            rows.append({"stat": st, "key": k, "layer": layer, "label": label, "means": means,
                         "pct": round(100 * c, 1), "se": None if s is None else round(100 * s, 1), "n": d["n"][k],
                         "evidence": eff_mod.evidence(c, s) if s else "none", "applied": k in APPLY and st in ONLY_FOR.get(k, {st}) and usable(d, k)})
    return rows
