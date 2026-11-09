"""Player-based team strength and pace.

Every player carries two per-minute ratings, recency-weighted and pulled towards average until he has
played enough minutes:
  - game score per minute (points, shooting efficiency, rebounds, assists, steals, blocks, fouls, turnovers),
    measured against the league average;
  - on-court plus-minus per minute.
A team's strength for a game is the sum over the players who actually play (or are projected to play)
of expected minutes x rating. Because it follows players, it moves with injuries, rest days and trades
the moment they happen - the results-based ratings only notice weeks later.

Pace and efficiency per team (possessions per game, points per 100 possessions for and against) give a
second, possession-based estimate of the total.
"""
from collections import defaultdict

GS_HL, PM_HL, MIN_HL, TEAM_HL = 25, 40, 8, 25
K_GS, K_PM = 80.0, 600.0        # minutes of evidence before a player's own number counts as much as average
SEASON_KEEP = 0.5               # last season's per-minute numbers count half once a new season starts


def gamescore(r):
    v = lambda k: float(r.get(k) or 0)
    if r.get("fga") is None:
        return None
    dreb = v("reb") - v("oreb")
    return (v("pts") + 0.4 * v("fgm") - 0.7 * v("fga") - 0.4 * (v("fta") - v("ftm")) + 0.7 * v("oreb") + 0.3 * dreb
            + v("stl") + 0.7 * v("ast") + 0.7 * v("blk") - 0.4 * v("pf") - v("tov"))


def _decay(state, key, value, weight, hl):
    a = 0.5 ** (1 / hl)
    s = state.get(key, (0.0, 0.0))
    state[key] = (s[0] * a + value, s[1] * a + weight)


class LineupTracker:
    def __init__(self):
        self.p = defaultdict(dict)        # pid -> {"gs": (sum, min), "pm": (sum, min), "min": (sum, n), "season": s}
        self.lg = {}                      # league game score per minute
        self.team = defaultdict(dict)     # team -> {"poss", "ortg", "drtg"}
        self.lg_team = {}

    # ---------------------------------------------------------------- ratings
    def rating(self, pid):
        q = self.p.get(pid)
        lg = (self.lg["gs"][0] / self.lg["gs"][1]) if self.lg.get("gs") and self.lg["gs"][1] else 0.0
        if not q:
            return 0.0, 0.0
        gs, gm = q.get("gs", (0.0, 0.0))
        pm, pmm = q.get("pm", (0.0, 0.0))
        r_gs = (gs - lg * gm) / (gm + K_GS)        # shrunk towards league average (0)
        r_pm = pm / (pmm + K_PM)
        return r_gs, r_pm

    def exp_minutes(self, pid):
        q = self.p.get(pid)
        if not q or not q.get("min") or not q["min"][1]:
            return 12.0
        return q["min"][0] / q["min"][1]

    def strength(self, players):
        """players: [(pid, minutes or None)]. Minutes are normalised to 240. Returns (gs, pm) strength."""
        if not players:
            return None
        mins = [(pid, m if m is not None else self.exp_minutes(pid)) for pid, m in players]
        tot = sum(m for _, m in mins) or 1.0
        s_gs = s_pm = 0.0
        for pid, m in mins:
            m = m * 240.0 / tot
            r_gs, r_pm = self.rating(pid)
            s_gs += m * r_gs
            s_pm += m * r_pm
        return s_gs, s_pm

    # ---------------------------------------------------------------- pace and efficiency
    def pace_total(self, home, away):
        th, ta = self.team.get(home), self.team.get(away)
        lg = self.lg_team
        if not th or not ta or not lg.get("poss"):
            return None
        g = lambda d, k: d[k][0] / d[k][1] if d.get(k) and d[k][1] else None
        ph, pa, lp = g(th, "poss"), g(ta, "poss"), g(lg, "poss")
        oh, dh, oa, da, lo = g(th, "ortg"), g(th, "drtg"), g(ta, "ortg"), g(ta, "drtg"), g(lg, "ortg")
        if None in (ph, pa, lp, oh, dh, oa, da, lo):
            return None
        poss = ph + pa - lp                       # both teams' tempo against the league's
        ppp_h = (oh + da - lo) / 100
        ppp_a = (oa + dh - lo) / 100
        return poss * (ppp_h + ppp_a)

    # ---------------------------------------------------------------- record a game
    def post_game(self, g, rows_by_team):
        season = int(g["season"])
        for team, rows in (rows_by_team or {}).items():
            for r in rows:
                mn = float(r.get("min") or 0)
                if mn <= 0:
                    continue
                q = self.p[str(r["player_id"])]
                if q.get("season") not in (None, season):
                    for k in ("gs", "pm"):
                        if k in q:
                            q[k] = (q[k][0] * SEASON_KEEP, q[k][1] * SEASON_KEEP)
                q["season"] = season
                gs = gamescore(r)
                if gs is not None:
                    _decay(q, "gs", gs, mn, GS_HL)
                    _decay(self.lg, "gs", gs, mn, 400)
                if r.get("pm") is not None:
                    _decay(q, "pm", float(r["pm"]), mn, PM_HL)
                _decay(q, "min", mn, 1.0, MIN_HL)
        # team pace and efficiency from the box score
        def poss(side):
            v = [g.get(f"{side}_{k}") for k in ("fga", "oreb", "tov", "fta")]
            try:
                fga, oreb, tov, fta = (float(x) for x in v)
            except (TypeError, ValueError):
                return None
            if fga != fga:
                return None
            return fga - oreb + tov + 0.44 * fta
        ph, pa = poss("h"), poss("a")
        if ph and pa:
            p_ = (ph + pa) / 2
            for team, pf, pa_ in ((g["home"], g["home_pts"], g["away_pts"]), (g["away"], g["away_pts"], g["home_pts"])):
                d = self.team[team]
                if d.get("season") not in (None, season):
                    for k in ("poss", "ortg", "drtg"):
                        if k in d:
                            d[k] = (d[k][0] * 0.3, d[k][1] * 0.3)
                d["season"] = season
                _decay(d, "poss", p_, 1.0, TEAM_HL)
                _decay(d, "ortg", 100 * pf / p_, 1.0, TEAM_HL)
                _decay(d, "drtg", 100 * pa_ / p_, 1.0, TEAM_HL)
            _decay(self.lg_team, "poss", p_, 1.0, 400)
            _decay(self.lg_team, "ortg", 100 * (g["home_pts"] + g["away_pts"]) / (2 * p_), 1.0, 400)
