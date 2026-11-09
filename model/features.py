"""Game context, computed strictly from what was known before tip-off.

Tracker walks the games in date order. pre_game() returns each team's situation going into a game
(rest, travel, availability, and the psychological spots); post_game() records the result.
The same object serves history (to measure what each spot has been worth) and upcoming games.
"""
import copy
from collections import defaultdict, deque
from datetime import date

from pipeline.teams import TEAMS, km, same_division

REG_MIN = 18          # minutes per game (when playing) to count as a rotation regular
REG_GP = 4            # ...and played at least this many of the team's last 10 games
VALUE_WINDOW = 15


def _day(s):
    return date.fromisoformat(s[:10])


def player_value(pts, reb, ast):
    return pts + 0.5 * reb + 1.0 * ast


class Tracker:
    def __init__(self):
        self.last_day = {}
        self.last_loc = {}
        self.recent_days = defaultdict(lambda: deque(maxlen=3))
        self.away_run = defaultdict(int)       # consecutive away games just played
        self.results = defaultdict(list)       # (season, stype) -> per team list of dicts
        self.season_res = defaultdict(lambda: defaultdict(list))  # season -> team -> results
        self.wl = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # season -> team -> [w, l] (regular season)
        self.meet = {}                          # (season, frozenset) -> last meeting dict
        self.series = {}                        # (season, frozenset) -> {team: wins}
        self.rot = defaultdict(lambda: deque(maxlen=VALUE_WINDOW))  # team -> deque of {pid: (min,pts,reb,ast)}
        self.names = {}
        self.schedule = defaultdict(list)       # team -> sorted [(day, game_id, opp)]

    # ---------------------------------------------------------------- schedule (for look-ahead)
    def set_schedule(self, games):
        sch = defaultdict(list)
        for g in games:
            sch[g["home"]].append((g["day"], str(g["game_id"]), g["away"]))
            sch[g["away"]].append((g["day"], str(g["game_id"]), g["home"]))
        self.schedule = {t: sorted(v) for t, v in sch.items()}

    def next_game(self, team, game_id, day):
        lst = self.schedule.get(team, [])
        for d, gid, opp in lst:
            if d > day:
                return d, opp
        return None

    # ---------------------------------------------------------------- standings helpers
    def pct(self, season, team, min_gp=10):
        w, l = self.wl[season][team]
        return (w / (w + l)) if (w + l) >= min_gp else None

    def record(self, season, team):
        w, l = self.wl[season][team]
        return f"{w}-{l}"

    def conf_table(self, season, conf):
        rows = []
        for t, v in TEAMS.items():
            if v[3] != conf:
                continue
            w, l = self.wl[season][t]
            rows.append((t, w, l, w / (w + l) if w + l else 0.0))
        rows.sort(key=lambda r: (-r[3], -r[1], r[0]))
        return rows

    def stakes(self, season, team):
        """+1 in a race for a seed line, -1 nothing left to play for, 0 otherwise (only late in the season)."""
        w, l = self.wl[season][team]
        gp = w + l
        if gp < 55:
            return 0, None
        tab = self.conf_table(season, TEAMS[team][3])
        idx = [r[0] for r in tab].index(team)
        seed = idx + 1
        left = 82 - gp

        def gb(a, b):  # games team a is ahead of team b
            return ((tab[a][1] - tab[b][1]) + (tab[b][2] - tab[a][2])) / 2
        if seed >= 11 and gb(9, idx) > max(6, left * 0.4):
            return -1, f"{gb(9, idx):.0f} games behind the play-in with {left} left"
        if seed <= 6 and left <= 12:
            ahead_below = gb(idx, idx + 1)
            behind_above = gb(idx - 1, idx) if idx > 0 else 99
            if ahead_below > left * 0.6 and behind_above > left * 0.6:
                return -1, f"seed {seed} all but settled with {left} left"
        for line in (6, 10):  # 6/7 = playoff spot vs play-in, 10/11 = play-in vs out
            above, below = line - 1, line
            if seed <= line and gb(idx, below) <= 3:
                return 1, f"seed {seed}, {gb(idx, below):.1f} games clear of seed {line + 1}"
            if seed > line and gb(above, idx) <= 3:
                return 1, f"seed {seed}, {gb(above, idx):.1f} games behind seed {line}"
        return 0, None

    # ---------------------------------------------------------------- availability
    def regulars(self, team):
        """Rotation regulars and their share of the team's production (last 15 games)."""
        hist = list(self.rot[team])
        if len(hist) < 3:
            return {}
        last10 = hist[-10:]
        stats = defaultdict(lambda: [0, 0.0, 0.0])  # gp, minutes, value
        for g in hist:
            for pid, (mn, pts, reb, ast) in g.items():
                if mn > 0:
                    s = stats[pid]
                    s[0] += 1
                    s[1] += mn
                    s[2] += player_value(pts, reb, ast)
        regs = {}
        for pid, (gp, mn, val) in stats.items():
            gp10 = sum(1 for g in last10 if g.get(pid, (0,))[0] > 0)
            if gp10 >= REG_GP and mn / gp >= REG_MIN:
                regs[pid] = val / gp
        top = dict(sorted(regs.items(), key=lambda kv: -kv[1])[:9])
        tot = sum(top.values()) or 1.0
        return {pid: v / tot for pid, v in top.items()}

    def missing(self, team, played=None, injured=None):
        """Share of the team's regular production that is unavailable.
        played: set of player ids who played (finished games). injured: list of {player_id, name, weight}."""
        regs = self.regulars(team)
        out, lst = 0.0, []
        if played is not None:
            for pid, share in regs.items():
                if pid not in played:
                    out += share
                    lst.append({"name": self.names.get(pid, pid), "share": round(share, 3), "weight": 1.0})
        elif injured:
            by_name = {self.names.get(p, "").lower(): p for p in regs}
            for inj in injured:
                pid = inj.get("player_id")
                if pid not in regs:
                    pid = by_name.get((inj.get("name") or "").lower())
                if pid in regs and inj.get("weight", 0) > 0:
                    out += regs[pid] * inj["weight"]
                    lst.append({"name": inj.get("name") or self.names.get(pid), "share": round(regs[pid], 3),
                                "weight": inj["weight"], "status": inj.get("status"), "detail": inj.get("detail")})
        return min(out, 1.0), sorted(lst, key=lambda x: -x["share"] * x["weight"])

    # ---------------------------------------------------------------- the situation before a game
    def side(self, g, team, opp, is_home, played=None, injured=None):
        d = g["day"]
        season, stype = int(g["season"]), int(g["stype"])
        loc = g["home"]
        f = {}
        last = self.last_day.get(team)
        if last and (_day(d) - _day(last)).days < 60:
            rest = (_day(d) - _day(last)).days - 1
        else:
            rest = 5
        f["rest"] = max(rest, 0)
        f["b2b"] = int(rest == 0)
        rd = [x for x in self.recent_days[team] if (_day(d) - _day(x)).days <= 3]
        f["three_in_four"] = int(len(rd) >= 2)
        prev = self.last_loc.get(team) if last and (_day(d) - _day(last)).days < 60 else None
        f["km"] = round(km(prev, loc)) if prev else 0
        f["tz_east"] = max(0, TEAMS[loc][7] - TEAMS[prev][7]) if prev else 0
        run = self.away_run[team]
        f["road_game_no"] = (run + 1) if not is_home else 0
        f["road_long"] = int((not is_home) and run + 1 >= 4)
        f["homecoming"] = int(is_home and run >= 4)
        res = self.season_res[season][team]
        f["streak"] = 0
        for r in reversed(res):
            if f["streak"] == 0:
                f["streak"] = 1 if r["win"] else -1
            elif (r["win"] and f["streak"] > 0) or (not r["win"] and f["streak"] < 0):
                f["streak"] += 1 if f["streak"] > 0 else -1
            else:
                break
        resid = [r["resid"] for r in res[-5:] if r.get("resid") is not None]
        f["confidence"] = round(sum(resid) / len(resid), 2) if len(resid) >= 3 else 0.0
        f["form"] = [("W" if r["win"] else "L", r["margin"], r["opp"]) for r in res[-10:]]
        lastr = res[-1] if res else None
        f["bounce"] = int(bool(lastr) and not lastr["win"] and lastr["margin"] <= -20)
        f["last_margin"] = lastr["margin"] if lastr else None
        f["last_opp"] = lastr["opp"] if lastr else None
        opp_pct = self.pct(season, opp)
        f["letdown"] = 0
        if lastr and lastr["win"] and (lastr.get("opp_pct") or 0) >= 0.6 and opp_pct is not None and opp_pct < 0.45:
            f["letdown"] = 1
        key = (season, frozenset((team, opp)))
        m = self.meet.get(key)
        f["revenge"] = int(bool(m) and m["loser"] == team)
        f["revenge_margin"] = m["margin"] if f["revenge"] else 0
        f["lookahead"] = 0
        f["lookahead_opp"] = None
        nxt = self.next_game(team, g["game_id"], d)
        if nxt and (_day(nxt[0]) - _day(d)).days <= 2 and stype == 2:
            np_ = self.pct(season, nxt[1])
            if np_ is not None and np_ >= 0.62 and opp_pct is not None and opp_pct < 0.45:
                f["lookahead"], f["lookahead_opp"] = 1, nxt[1]
        f["stakes"], f["stakes_why"] = (self.stakes(season, team) if stype == 2 else (0, None))
        f["elimination"] = 0
        if stype == 3:
            s = self.series.get(key, {})
            f["series"] = f"{s.get(team, 0)}-{s.get(opp, 0)}"
            f["elimination"] = int(s.get(opp, 0) == 3)
        f["missing"], f["missing_list"] = self.missing(team, played, injured)
        f["record"] = self.record(season, team)
        f["pct"] = self.pct(season, team, 1)
        f["gp"] = sum(self.wl[season][team])
        return f

    def pre_game(self, g, played=None, injuries=None):
        h, a = g["home"], g["away"]
        ph = (played or {}).get(h) if played is not None else None
        pa = (played or {}).get(a) if played is not None else None
        fh = self.side(g, h, a, True, ph, (injuries or {}).get(h))
        fa = self.side(g, a, h, False, pa, (injuries or {}).get(a))
        return {"home": fh, "away": fa, "rivalry": int(same_division(h, a)), "playoff": int(int(g["stype"]) == 3)}

    # ---------------------------------------------------------------- record a result
    def post_game(self, g, base_margin=None, box_players=None):
        h, a = g["home"], g["away"]
        d, season, stype = g["day"], int(g["season"]), int(g["stype"])
        margin = int(g["home_pts"]) - int(g["away_pts"])
        hp, ap = self.pct(season, h), self.pct(season, a)
        for team, opp, m, home, opct in ((h, a, margin, True, ap), (a, h, -margin, False, hp)):
            resid = None
            if base_margin is not None:
                resid = (margin - base_margin) * (1 if home else -1)
            self.season_res[season][team].append({"day": d, "opp": opp, "margin": m, "win": m > 0, "home": home,
                                                  "resid": resid, "opp_pct": opct})
            if stype == 2:
                self.wl[season][team][0 if m > 0 else 1] += 1
            self.recent_days[team].append(d)
            self.last_day[team] = d
            self.last_loc[team] = h
            self.away_run[team] = 0 if home else self.away_run[team] + 1
        key = (season, frozenset((h, a)))
        loser = a if margin > 0 else h
        self.meet[key] = {"day": d, "loser": loser, "margin": abs(margin)}
        if stype == 3:
            s = self.series.setdefault(key, {h: 0, a: 0})
            s[h if margin > 0 else a] = s.get(h if margin > 0 else a, 0) + 1
        if box_players is not None:
            for team in (h, a):
                rows = box_players.get(team) or {}
                self.rot[team].append(rows)

    def advance_schedule_only(self, g):
        """For chained upcoming games: move the clock and location without a result."""
        h, a = g["home"], g["away"]
        for team, home in ((h, True), (a, False)):
            self.recent_days[team].append(g["day"])
            self.last_day[team] = g["day"]
            self.last_loc[team] = h
            self.away_run[team] = 0 if home else self.away_run[team] + 1

    def clone(self):
        return copy.deepcopy(self)
