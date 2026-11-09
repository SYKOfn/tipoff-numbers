"""Team extras: advanced stats, quarter/half estimates, head-to-head, playoff chances, mind ranking."""
import math

import numpy as np

from . import effects
from pipeline.teams import TEAMS

ABBRS = sorted(TEAMS)


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ advanced team stats
def advanced(games, season):
    g = games[(games["season"] == season) & (games["box"] == 1)]
    acc = {t: {k: 0.0 for k in ("gp", "pts", "opp", "poss", "oposs", "fgm", "fga", "tpm", "fta", "ftm", "oreb", "dreb", "tov",
                                  "o_fgm", "o_fga", "o_tpm", "o_fta", "o_ftm", "o_oreb", "o_dreb", "o_tov", "ast", "o_ast")} for t in ABBRS}
    for r in g.to_dict("records"):
        for me, op, pm, po in (("h", "a", r["home_pts"], r["away_pts"]), ("a", "h", r["away_pts"], r["home_pts"])):
            t = r["home"] if me == "h" else r["away"]
            v = {k: _num(r.get(f"{me}_{k}")) for k in ("fgm", "fga", "tpm", "fta", "ftm", "oreb", "reb", "tov", "ast")}
            o = {k: _num(r.get(f"{op}_{k}")) for k in ("fgm", "fga", "tpm", "fta", "ftm", "oreb", "reb", "tov", "ast")}
            if None in v.values() or None in o.values():
                continue
            a = acc[t]
            a["gp"] += 1
            a["pts"] += pm
            a["opp"] += po
            a["poss"] += v["fga"] - v["oreb"] + v["tov"] + 0.44 * v["fta"]
            a["oposs"] += o["fga"] - o["oreb"] + o["tov"] + 0.44 * o["fta"]
            for k in ("fgm", "fga", "tpm", "fta", "ftm", "oreb", "tov", "ast"):
                a[k] += v[k]
                a["o_" + k] += o[k]
            a["dreb"] += v["reb"] - v["oreb"]
            a["o_dreb"] += o["reb"] - o["oreb"]
    out = {}
    for t, a in acc.items():
        if not a["gp"] or not a["poss"]:
            out[t] = None
            continue
        poss = (a["poss"] + a["oposs"]) / 2
        out[t] = {
            "gp": int(a["gp"]), "pace": round(poss / a["gp"], 1),
            "ortg": round(100 * a["pts"] / poss, 1), "drtg": round(100 * a["opp"] / poss, 1),
            "nrtg": round(100 * (a["pts"] - a["opp"]) / poss, 1),
            "efg": round((a["fgm"] + 0.5 * a["tpm"]) / a["fga"], 3), "o_efg": round((a["o_fgm"] + 0.5 * a["o_tpm"]) / a["o_fga"], 3),
            "tov": round(a["tov"] / a["poss"], 3), "o_tov": round(a["o_tov"] / a["oposs"], 3),
            "orb": round(a["oreb"] / (a["oreb"] + a["o_dreb"]), 3), "drb": round(a["dreb"] / (a["dreb"] + a["o_oreb"]), 3),
            "ftr": round(a["fta"] / a["fga"], 3), "o_ftr": round(a["o_fta"] / a["o_fga"], 3),
            "tpar": None, "ast_rate": round(a["ast"] / a["fgm"], 3),
        }
    for key, hi in (("pace", True), ("ortg", True), ("drtg", False), ("nrtg", True), ("efg", True), ("o_efg", False),
                    ("tov", False), ("o_tov", True), ("orb", True), ("drb", True), ("ftr", True), ("o_ftr", False)):
        vals = sorted([t for t in out if out[t]], key=lambda t: out[t][key], reverse=hi)
        for i, t in enumerate(vals):
            out[t][key + "_rank"] = i + 1
    return out


# ------------------------------------------------------------------ quarters
def quarter_shares(games, k=40.0):
    g = games[(games["q"] == 1) & (games["stype"] == 2) & (games["ot"].fillna(0) == 0)]
    lg = np.zeros(4)
    team = {t: [np.zeros(4), 0.0] for t in ABBRS}
    for r in g.to_dict("records"):
        for me, t, tot in (("h", r["home"], r["home_pts"]), ("a", r["away"], r["away_pts"])):
            q = np.array([_num(r.get(f"{me}_q{i}")) or 0 for i in range(1, 5)])
            if q.sum() <= 0:
                continue
            lg += q / q.sum()
            team[t][0] += q / q.sum()
            team[t][1] += 1
    n = len(g) * 2
    if not n:
        return None
    lg /= n
    out = {"league": lg.round(4).tolist()}
    for t, (s, c) in team.items():
        out[t] = ((s + lg * k) / (c + k)).round(4).tolist()
    return out


def quarters(est, shares, home, away):
    if not shares:
        return None
    hs, as_ = np.array(shares[home]), np.array(shares[away])
    hq = est["home_pts"] * hs
    aq = est["away_pts"] * as_
    sdm, sdt = est["sd_margin"], est["sd_total"]
    rows = []
    for name, idx, f in (("1st quarter", [0], 0.5), ("2nd quarter", [1], 0.5), ("3rd quarter", [2], 0.5),
                         ("4th quarter", [3], 0.5), ("1st half", [0, 1], 0.71), ("2nd half", [2, 3], 0.71)):
        h_, a_ = float(hq[idx].sum()), float(aq[idx].sum())
        m, t = h_ - a_, h_ + a_
        sm, st = sdm * f, sdt * f
        base = math.floor(t) + 0.5
        rows.append({"name": name, "home": round(h_, 1), "away": round(a_, 1), "margin": round(m, 1), "total": round(t, 1),
                     "win_home": round(effects.norm_cdf(m / sm), 3),
                     "lines": [{"line": L, "over": round(1 - effects.norm_cdf((L - t) / st), 3)} for L in (base - 4, base, base + 4)]})
    return rows


# ------------------------------------------------------------------ head to head
def h2h(games, a, b, n=10):
    g = games[((games["home"] == a) & (games["away"] == b)) | ((games["home"] == b) & (games["away"] == a))]
    g = g.sort_values("day", ascending=False).head(n)
    return [{"id": str(r["game_id"]), "day": r["day"], "season": int(r["season"]), "stype": int(r["stype"]), "home": r["home"],
             "away": r["away"], "home_pts": int(r["home_pts"]), "away_pts": int(r["away_pts"])} for r in g.to_dict("records")]


# ------------------------------------------------------------------ playoff chances
def playoff_odds(wl, remaining, net, home_edge, sd, sims=4000, seed=11):
    """wl: {team: [w, l]} now. remaining: list of (home, away). net: rating per team."""
    rng = np.random.default_rng(seed)
    idx = {t: i for i, t in enumerate(ABBRS)}
    n = len(ABBRS)
    w0 = np.array([wl[t][0] for t in ABBRS], float)
    if remaining:
        hi = np.array([idx[h] for h, a in remaining])
        ai = np.array([idx[a] for h, a in remaining])
    strength = np.array([net[t] for t in ABBRS])
    wins = np.tile(w0, (sims, 1))
    shift = rng.normal(0, 2.0, (sims, n))  # the ratings themselves are uncertain
    if remaining:
        s = strength[None, :] + shift
        mu = s[:, hi] - s[:, ai] + home_edge
        hw = (mu + rng.normal(0, sd, mu.shape)) > 0
        np.add.at(wins, (np.arange(sims)[:, None], hi[None, :].repeat(sims, 0)), hw)
        np.add.at(wins, (np.arange(sims)[:, None], ai[None, :].repeat(sims, 0)), ~hw)
    res = {t: {"top6": 0, "playin": 0, "playoffs": 0, "seed1": 0, "wins": 0.0} for t in ABBRS}
    confs = {c: [idx[t] for t in ABBRS if TEAMS[t][3] == c] for c in ("East", "West")}
    tieb = rng.random((sims, n)) * 1e-3
    for si in range(sims):
        for c, members in confs.items():
            order = sorted(members, key=lambda i: -(wins[si, i] + tieb[si, i]))
            for k, i in enumerate(order[:6]):
                res[ABBRS[i]]["top6"] += 1
                res[ABBRS[i]]["playoffs"] += 1
            res[ABBRS[order[0]]]["seed1"] += 1
            s7, s8, s9, s10 = order[6:10]
            for i in (s7, s8, s9, s10):
                res[ABBRS[i]]["playin"] += 1

            def game(x, y):  # x is the higher seed, at home
                p = effects.norm_cdf((strength[x] + shift[si, x] - strength[y] - shift[si, y] + home_edge) / sd)
                return (x, y) if rng.random() < p else (y, x)
            w78, l78 = game(s7, s8)
            w910, _ = game(s9, s10)
            w8, _ = game(l78, w910)
            res[ABBRS[w78]]["playoffs"] += 1
            res[ABBRS[w8]]["playoffs"] += 1
    for t in ABBRS:
        for k in ("top6", "playin", "playoffs", "seed1"):
            res[t][k] = round(res[t][k] / sims, 3)
        res[t]["wins"] = round(float(wins[:, idx[t]].mean()), 1)
    return res


# ------------------------------------------------------------------ mind ranking
def mood(f, eff, upcoming_edge, l10, missing):
    """Descriptive state of mind (momentum) + category + reasons. Momentum mixes the streak, the last ten
    games and how far recent results beat expectations; it is a description, not a prediction: the
    predictive value of these spots is what the measured effects say (see `edge`)."""
    w10 = int(l10.split("-")[0]) if l10 and "-" in l10 else 5
    n10 = sum(int(x) for x in l10.split("-")) if l10 and "-" in l10 else 0
    streak = max(-6, min(6, f["streak"]))
    momentum = 0.35 * f["confidence"] + 0.5 * streak + (0.6 * (w10 - n10 / 2) if n10 else 0.0)
    reasons = []
    if f["streak"] >= 3:
        reasons.append(f"won {f['streak']} straight")
    if f["streak"] <= -3:
        reasons.append(f"lost {-f['streak']} straight")
    if n10 >= 6:
        reasons.append(f"{l10} in the last {n10}")
    if abs(f["confidence"]) >= 3:
        reasons.append(f"{f['confidence']:+.1f} pts a game vs expectation over the last 5")
    if f["stakes"] and f.get("stakes_why"):
        reasons.append(f["stakes_why"])
    if missing >= 0.15:
        reasons.append(f"{round(missing * 100)}% of regular production out")
    if f["stakes"] < 0:
        cat = "Coasting"
    elif f["stakes"] > 0 or missing >= 0.25:
        cat = "Under pressure"
    elif momentum >= 2.5:
        cat = "Hot"
    elif momentum <= -2.5:
        cat = "Cold"
    else:
        cat = "Steady"
    return round(momentum, 2), cat, reasons
