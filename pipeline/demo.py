"""Simulated league for running the whole pipeline without network access (preview, tests).

It writes the same files as the ESPN collector: three full seasons of games with box scores and player
lines, the next two weeks of schedule, and an injury list. Hidden "true" effects are planted for
some physical and psychological spots and set to zero for others (streaks, confidence), so the
estimation can be checked: it should find the planted ones and call the others "no evidence".
NOTHING here is real: every number is invented.
"""
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from model.features import Tracker
from .store import BOX, GAME_COLS, PLAYER_COLS, STATE, save_games, save_players, write_json
from .teams import TEAMS

TRUE = {"b2b": -2.0, "three_in_four": -0.8, "rest": 0.3, "tz_east": -0.4, "travel": -0.2, "missing": -14.0,
        "streak": 0.0, "confidence": 0.0, "bounce": 1.8, "letdown": -1.2, "revenge": 0.8, "lookahead": -1.0,
        "homecoming": 1.0, "road_long": -0.8, "stakes_race": 1.5, "stakes_none": -3.0, "elimination": 1.5}
TRUE_TOTAL = {"b2b": -1.5, "rivalry": -1.0, "playoff": -4.0, "no_stakes": 3.0}
FIRST = ["Jalen", "Marcus", "Darius", "Tyrese", "Malik", "Andre", "Isaiah", "Jaylen", "Devin", "Cam", "Keegan", "Scottie",
         "Evan", "Josh", "Miles", "Trey", "Bennedict", "Ausar", "Dyson", "Nikola", "Luka", "Kel'el", "Jordan", "Aaron",
         "Zion", "Brandon", "Coby", "Walker", "Ochai", "Bilal", "Amen", "Jabari", "Alperen", "Franz", "Paolo", "Anfernee"]
LAST = ["Holloway", "Pritchard", "Brooks", "Okafor", "Lindqvist", "Varela", "Mensah", "Castellano", "Duarte", "Kowalski",
        "Whitfield", "Abernathy", "Nakamura", "Sorensen", "Achterberg", "Ferreira", "Delacroix", "Osei", "Marchetti",
        "Haverford", "Quintero", "Baptiste", "Rasmussen", "Iwobi", "Calloway", "Strand", "Moreau", "Novak", "Ellison",
        "Petrakis", "Langford", "Odhiambo", "Ruiz", "Thibodeau", "Vance", "Mbeki", "Sutherland", "Kwame", "Lindgren"]
MINS = [35, 33, 31, 29, 27, 24, 21, 18, 13, 9, 0, 0, 0]


def _season_days(season):
    return date(season - 1, 10, 21), date(season, 4, 12)


def _schedule(rng, season, teams):
    start, end = _season_days(season)
    ndays = (end - start).days + 1
    gp = {t: 0 for t in teams}
    homes = {t: 0 for t in teams}
    last = {t: None for t in teams}
    last2 = {t: None for t in teams}
    out = []
    for i in range(ndays):
        d = start + timedelta(days=i)
        left = ndays - i
        avail = []
        for t in teams:
            if gp[t] >= 82:
                continue
            if last[t] == d - timedelta(days=1) and last2[t] == d - timedelta(days=2):
                continue
            need = (82 - gp[t]) / left
            if rng.random() < min(0.95, need * 1.05):
                avail.append(t)
        rng.shuffle(avail)
        for j in range(0, len(avail) - 1, 2):
            a, b = avail[j], avail[j + 1]
            h, aw = (a, b) if (homes[a] - gp[a] / 2) <= (homes[b] - gp[b] / 2) else (b, a)
            out.append((d.isoformat(), h, aw))
            for t in (a, b):
                gp[t] += 1
                last2[t], last[t] = last[t], d
            homes[h] += 1
    return out


class Sim:
    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.np = np.random.default_rng(seed)
        self.teams = sorted(TEAMS)
        self.strength = {t: self.np.normal(0, 4.5) for t in self.teams}
        self.off = {t: self.strength[t] * 0.5 + self.np.normal(0, 1.5) for t in self.teams}
        self.tpr = {t: self.np.normal(0, 1.6) for t in self.teams}   # threes tendency
        self.rbr = {t: self.np.normal(0, 2.0) for t in self.teams}
        self.players = {}
        self.inj = {}
        pid = 1000
        used = set()
        for t in self.teams:
            roster = []
            for k in range(13):
                while True:
                    nm = f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"
                    if nm not in used:
                        used.add(nm)
                        break
                rate = max(0.3, self.np.normal(1.0, 0.18)) * (1.25 if k < 2 else 1.0)
                roster.append({"id": str(pid), "name": nm, "min": MINS[k], "rate": rate, "pos": ["G", "G", "F", "F", "C"][k % 5],
                               "rebw": self.np.uniform(0.5, 1.6) * (1.5 if k % 5 == 4 else 1), "astw": self.np.uniform(0.4, 1.8) * (1.6 if k % 5 < 2 else 1)})
                pid += 1
            self.players[t] = roster
            for p in roster:
                self.inj[p["id"]] = 0

    def new_season(self):
        for t in self.teams:
            s = 0.65 * self.strength[t] + self.np.normal(0, 3.2)
            self.strength[t] = s
            self.off[t] = s * 0.5 + self.np.normal(0, 1.5)
            roster = self.players[t]
            self.rng.shuffle(roster)
            roster.sort(key=lambda p: -p["rate"] * self.np.uniform(0.8, 1.2))
            for k, p in enumerate(roster):
                p["min"] = MINS[k]

    def shares(self, t):
        rot = [p for p in self.players[t] if p["min"] >= 18][:9]
        v = {p["id"]: p["min"] * p["rate"] for p in rot}
        s = sum(v.values()) or 1
        return {k: x / s for k, x in v.items()}

    def available(self, t, b2b):
        out = []
        for p in self.players[t]:
            if self.inj[p["id"]] > 0:
                continue
            if b2b and p["min"] >= 33 and self.rng.random() < 0.18:  # load management
                continue
            out.append(p)
        return out

    def tick_injuries(self):
        for pid in self.inj:
            if self.inj[pid] > 0:
                self.inj[pid] -= 1
            elif self.rng.random() < 0.0055:
                self.inj[pid] = int(self.np.geometric(1 / 9))


def _true_adj(f, other, game):
    e = (TRUE["b2b"] * f["b2b"] + TRUE["three_in_four"] * f["three_in_four"] + TRUE["rest"] * min(f["rest"], 3)
         + TRUE["tz_east"] * f["tz_east"] + TRUE["travel"] * f["km"] / 1000 + TRUE["bounce"] * f["bounce"]
         + TRUE["letdown"] * f["letdown"] + TRUE["revenge"] * f["revenge"] + TRUE["lookahead"] * f["lookahead"]
         + TRUE["homecoming"] * f["homecoming"] + TRUE["road_long"] * f["road_long"] + TRUE["elimination"] * f["elimination"])
    if f["stakes"] > 0:
        e += TRUE["stakes_race"]
    elif f["stakes"] < 0:
        e += TRUE["stakes_none"]
    return e


def generate(today=None, seed=7):
    today = today or datetime.now(timezone.utc).date()
    sim = Sim(seed)
    cur = today.year + 1 if today.month >= 8 else today.year
    seasons = [cur - 3, cur - 2, cur - 1, cur]
    games, players = [], []
    upcoming = []
    gid = 500000000
    tr = Tracker()
    full_sched = {}
    for s in seasons:
        full_sched[s] = _schedule(sim.rng, s, sim.teams)
    allg = [{"day": d, "home": h, "away": a, "game_id": f"{s}{i:05d}", "season": s, "stype": 2}
            for s in seasons for i, (d, h, a) in enumerate(full_sched[s])]
    tr.set_schedule(allg)
    for s in seasons:
        if s != seasons[0]:
            sim.new_season()
        sched = [g for g in allg if g["season"] == s]
        days = sorted(set(g["day"] for g in sched))
        for d in days:
            if date.fromisoformat(d) >= today:
                break
            sim.tick_injuries()
            for g in [x for x in sched if x["day"] == d]:
                gid += 1
                _play(sim, tr, g, str(gid), games, players)
        if date.fromisoformat(days[-1]) < today:
            gid = _playoffs(sim, tr, s, days[-1], gid, games, players)
    # upcoming: the current season's schedule from today on
    for g in allg:
        if g["season"] == cur and today.isoformat() <= g["day"] <= (today + timedelta(days=14)).isoformat():
            hour = sim.rng.choice([23, 23, 0, 0, 0, 1, 2, 3])
            dd = date.fromisoformat(g["day"]) + (timedelta(days=1) if hour < 12 else timedelta())
            tip = datetime(dd.year, dd.month, dd.day, hour, sim.rng.choice([0, 30]), tzinfo=timezone.utc)
            upcoming.append({"game_id": f"9{g['game_id']}", "date": tip.isoformat().replace("+00:00", "Z"), "day": g["day"],
                             "season": cur, "stype": 2, "home": g["home"], "away": g["away"], "home_pts": None,
                             "away_pts": None, "state": "pre", "completed": False, "detail": None, "ot": 0,
                             "neutral": False, "national_tv": sim.rng.random() < 0.15, "venue": None, "note": None})
    # injuries now
    inj = {}
    for t in sim.teams:
        for p in sim.players[t]:
            if sim.inj[p["id"]] > 0 and p["min"] > 0:
                st = "Out" if sim.inj[p["id"]] > 2 else sim.rng.choice(["Questionable", "Day-To-Day", "Out"])
                inj.setdefault(t, []).append({"player_id": p["id"], "name": p["name"], "status": st,
                                              "weight": {"Out": 1.0, "Questionable": 0.4, "Day-To-Day": 0.3}[st],
                                              "detail": sim.rng.choice(["Knee", "Ankle", "Hamstring", "Back", "Illness", "Calf", "Foot"]),
                                              "returns": None})
    gdf = pd.DataFrame(games)
    for c in GAME_COLS:
        if c not in gdf:
            gdf[c] = pd.NA
    # like the live collector: box scores and player lines only for this season and last
    old = gdf["season"] < cur - 1
    gdf.loc[old, [c for c in gdf.columns if c.startswith(("h_", "a_"))]] = pd.NA
    gdf.loc[old, "box"] = 0
    keep_ids = set(gdf.loc[~old, "game_id"])
    save_games(gdf)
    save_players(pd.DataFrame([p for p in players if p["game_id"] in keep_ids], columns=PLAYER_COLS))
    write_json(STATE / "upcoming.json", upcoming)
    write_json(STATE / "injuries.json", {"as_of": datetime.now(timezone.utc).isoformat(), "teams": inj})
    write_json(STATE / "teams_meta.json", {})
    write_json(STATE / "collect.json", {"demo": True, "calls": 0, "errors": []})
    return {"games": len(gdf), "upcoming": len(upcoming)}


def _play(sim, tr, g, gid, games, players, stype=2, neutral=False):
    h, a = g["home"], g["away"]
    g = {**g, "game_id": gid, "stype": stype}
    pre_h = tr.last_day.get(h)
    pre_a = tr.last_day.get(a)
    b2b_h = pre_h == (date.fromisoformat(g["day"]) - timedelta(days=1)).isoformat()
    b2b_a = pre_a == (date.fromisoformat(g["day"]) - timedelta(days=1)).isoformat()
    av = {h: sim.available(h, b2b_h), a: sim.available(a, b2b_a)}
    played = {t: {p["id"] for p in av[t] if p["min"] > 0} for t in (h, a)}
    ctx = tr.pre_game(g, played=played)
    miss = {t: sum(v for k, v in sim.shares(t).items() if k not in played[t]) for t in (h, a)}
    eh = _true_adj(ctx["home"], ctx["away"], ctx) + TRUE["missing"] * miss[h]
    ea = _true_adj(ctx["away"], ctx["home"], ctx) + TRUE["missing"] * miss[a]
    tot_adj = (TRUE_TOTAL["b2b"] * (ctx["home"]["b2b"] + ctx["away"]["b2b"]) + TRUE_TOTAL["rivalry"] * ctx["rivalry"]
               + TRUE_TOTAL["playoff"] * ctx["playoff"]
               + TRUE_TOTAL["no_stakes"] * (int(ctx["home"]["stakes"] < 0) + int(ctx["away"]["stakes"] < 0)))
    st = sim.strength
    hcourt = 0 if neutral else 2.6
    margin_mean = st[h] - st[a] + hcourt + eh - ea
    total_mean = 228 + (sim.off[h] - (st[h] - sim.off[h])) * 0.6 + (sim.off[a] - (st[a] - sim.off[a])) * 0.6 + tot_adj
    pace = sim.np.normal(0, 6.5)
    noise_m = sim.np.normal(0, 12.0)
    hp = round((total_mean + pace * 2 + margin_mean + noise_m) / 2)
    ap = round((total_mean + pace * 2 - margin_mean - noise_m) / 2)
    ot = 0
    while hp == ap:
        ot += 1
        hp += sim.rng.randint(5, 15)
        ap += sim.rng.randint(5, 15)
    row = {"game_id": gid, "date": f"{g['day']}T23:30Z", "day": g["day"], "season": g["season"], "stype": stype,
           "home": h, "away": a, "home_pts": hp, "away_pts": ap, "ot": ot, "neutral": int(neutral),
           "national_tv": int(sim.rng.random() < 0.15), "venue": None, "box": 1}
    box_players = {}
    for side, t, pts in (("h", h, hp), ("a", a, ap)):
        tpm = max(4, round(sim.np.normal(13 + sim.tpr[t], 3.3)))
        reb = max(28, round(sim.np.normal(44 + sim.rbr[t], 5)))
        ast = max(12, round(sim.np.normal(26 + 0.12 * (pts - 114), 4)))
        tpa = max(tpm + 5, round(tpm / sim.np.uniform(0.32, 0.4)))
        fta = max(8, round(sim.np.normal(22, 5)))
        ftm = min(fta, round(fta * sim.np.uniform(0.7, 0.85)))
        fgm = max(25, round((pts - ftm - tpm) / 2))
        fga = max(fgm + 20, round(fgm / sim.np.uniform(0.43, 0.51)))
        vals = {"fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta, "oreb": round(reb * 0.24),
                "reb": reb, "ast": ast, "tov": max(6, round(sim.np.normal(13.5, 3))), "stl": max(2, round(sim.np.normal(7.5, 2))),
                "blk": max(0, round(sim.np.normal(5, 2)))}
        for k in BOX:
            row[f"{side}_{k}"] = vals[k]
        rot = [p for p in av[t] if p["min"] > 0]
        total_min = sum(p["min"] for p in rot) or 1
        scale = (240 + 25 * ot) / total_min
        wts = [p["min"] * p["rate"] for p in rot]
        rw = [p["min"] * p["rebw"] for p in rot]
        aw = [p["min"] * p["astw"] for p in rot]
        bp = {}
        for p, w, r_, a_ in zip(rot, wts, rw, aw):
            mn = min(44, round(p["min"] * scale * sim.np.uniform(0.85, 1.15)))
            pp = round(pts * w / sum(wts) * sim.np.uniform(0.6, 1.4))
            rr = round(reb * r_ / sum(rw) * sim.np.uniform(0.6, 1.4))
            aa = round(ast * a_ / sum(aw) * sim.np.uniform(0.6, 1.4))
            players.append({"game_id": gid, "team": t, "player_id": p["id"], "name": p["name"], "pos": p["pos"],
                            "starter": int(p["min"] >= 27), "min": mn, "pts": pp, "reb": rr, "ast": aa})
            bp[p["id"]] = (mn, pp, rr, aa)
            tr.names[p["id"]] = p["name"]
        box_players[t] = bp
    games.append(row)
    tr.post_game({**g, "home_pts": hp, "away_pts": ap}, base_margin=None, box_players=box_players)
    for t in (h, a):  # small drift in true strength through the season
        sim.strength[t] += sim.np.normal(0, 0.12)


def _playoffs(sim, tr, season, last_day, gid, games, players):
    d = date.fromisoformat(last_day) + timedelta(days=6)
    bracket = {}
    for conf in ("East", "West"):
        tab = [r[0] for r in tr.conf_table(season, conf)]
        bracket[conf] = [tab[0], tab[7], tab[3], tab[4], tab[1], tab[6], tab[2], tab[5]]
    rounds = [bracket["East"], bracket["West"]]
    while True:
        winners_all = []
        day0 = d
        for teams in rounds:
            winners = []
            for i in range(0, len(teams), 2):
                hi, lo = teams[i], teams[i + 1]
                if tr.pct(season, lo, 1) > tr.pct(season, hi, 1):
                    hi, lo = lo, hi
                w = {hi: 0, lo: 0}
                gd = day0
                n = 0
                while max(w.values()) < 4:
                    home = hi if n in (0, 1, 4, 6) else lo
                    away = lo if home == hi else hi
                    gid += 1
                    _play(sim, tr, {"day": gd.isoformat(), "home": home, "away": away, "season": season}, str(gid),
                          games, players, stype=3)
                    last = games[-1]
                    w[home if last["home_pts"] > last["away_pts"] else away] += 1
                    gd += timedelta(days=2)
                    n += 1
                    sim.tick_injuries()
                winners.append(hi if w[hi] == 4 else lo)
                d = max(d, gd)
            winners_all.append(winners)
        if len(winners_all) == 2 and len(winners_all[0]) == 1:
            rounds = [[winners_all[0][0], winners_all[1][0]]]
        elif len(winners_all) == 1:
            break
        else:
            rounds = winners_all
        d += timedelta(days=2)
    return gid
