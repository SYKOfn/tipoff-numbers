"""One recipe for every game:  final = base ratings + physical adjustments + psychological adjustments.

build_context(): walks all finished games once (out-of-sample base predictions + the situation
before every game), measures the factor sizes, and leaves a tracker positioned at "now".
predict(): the estimate for one game, with every piece shown.
"""
from collections import defaultdict
from datetime import date

import os

import numpy as np

from . import effects, ratings
from .features import Tracker
from .lineup import LineupTracker
from .style import StyleTracker, MARGIN_F, TOTAL_F
from .rapm import RAPM, StintRAPM
from .officials import OfficialsTracker

STACK_LAM = 50.0   # ridge on the player-strength weights (tested walk-forward on 2025-26 and 2026-27)

DEFAULT = {"half_life": 90.0, "lam": 6.0, "carry": 0.6, "lam_effects": 150.0}


def players_by_game(players):
    out = defaultdict(lambda: defaultdict(dict))
    names = {}
    if players is None or not len(players):
        return out, names
    for gid, team, pid, nm, mn, pts, reb, ast in zip(players["game_id"].astype(str), players["team"], players["player_id"].astype(str),
                                                     players["name"], players["min"], players["pts"], players["reb"], players["ast"]):
        out[gid][team][pid] = (float(mn or 0), float(pts or 0), float(reb or 0), float(ast or 0))
        names[pid] = nm
    return out, names


class Context:
    pass


SRAPM_MODE = os.environ.get("SRAPM_MODE", "add")  # stint ratings: "off", "add" (a fourth player feature), "replace"


def build_context(games, players, upcoming, tuned=None, effects_until=None, stints=None):
    tuned = {**DEFAULT, **(tuned or {})}
    fin = games.sort_values(["date", "game_id"]).reset_index(drop=True)
    base = ratings.walk_forward(fin, half_life=tuned["half_life"], lam=tuned["lam"], carry=tuned["carry"])
    pg, names = players_by_game(players)
    from .player_engine import rows_by_game
    byg = rows_by_game(players)
    lt = LineupTracker()
    sty = StyleTracker()
    rp = RAPM()
    sr, byst = None, {}
    if stints is not None and len(stints) and SRAPM_MODE != "off":
        sr = StintRAPM()
        byst = {gid: [(r.dur, r.h_pts, r.a_pts, tuple(r.home_ids.split(";")), tuple(r.away_ids.split(";"))) for r in d.itertuples()]
                for gid, d in stints.groupby(stints["game_id"].astype(str))}
    otr = OfficialsTracker()
    lfeat = {}
    tr = Tracker()
    tr.names.update(names)
    tr.set_schedule([{"day": d, "home": h, "away": a, "game_id": gid}
                     for d, h, a, gid in zip(fin["day"], fin["home"], fin["away"], fin["game_id"])]
                    + [{"day": g["day"], "home": g["home"], "away": g["away"], "game_id": g["game_id"]} for g in upcoming])
    ctxs, rows, meta = {}, [], {}
    for g in fin.to_dict("records"):
        gid = str(g["game_id"])
        box = pg.get(gid)
        played = None
        if box and g["home"] in box and g["away"] in box:
            played = {t: {pid for pid, v in box[t].items() if v[0] > 0} for t in (g["home"], g["away"])}
        ctx = tr.pre_game(g, played=played)
        for side in ("home", "away"):
            ctx[side]["luck"] = round(sty.team_luck(g[side]), 3)
        sf = sty.features(g) or {}
        for k in MARGIN_F:  # already a single home-vs-away value; park it on "home", 0 on "away" so own(h)-own(a) passes it through
            if k == "luck":
                continue
            ctx["home"][f"style_{k}"] = round(sf.get(k, 0.0), 3)
            ctx["away"][f"style_{k}"] = 0.0
        for k in TOTAL_F:
            ctx[f"style_{k}"] = round(sf.get(k, 0.0), 3)
        sty.post_game(g)
        ctxs[gid] = ctx
        b = base.get(gid)
        rows_ = byg.get(gid)
        if rows_ and g["home"] in rows_ and g["away"] in rows_:
            sh = lt.strength([(r["player_id"], None) for r in rows_[g["home"]] if r["min"] > 0])
            sa = lt.strength([(r["player_id"], None) for r in rows_[g["away"]] if r["min"] > 0])
            rp.maybe_refit(g["day"])
            rh = rp.strength([(r["player_id"], lt.exp_minutes(r["player_id"])) for r in rows_[g["home"]] if r["min"] > 0])
            ra = rp.strength([(r["player_id"], lt.exp_minutes(r["player_id"])) for r in rows_[g["away"]] if r["min"] > 0])
            srh = sra = None
            if sr is not None:
                sr.maybe_refit(g["day"])
                srh = sr.strength([(r["player_id"], lt.exp_minutes(r["player_id"])) for r in rows_[g["home"]] if r["min"] > 0])
                sra = sr.strength([(r["player_id"], lt.exp_minutes(r["player_id"])) for r in rows_[g["away"]] if r["min"] > 0])
            if sh and sa and rh is not None and ra is not None:
                f = player_features((sh[0] - sa[0], sh[1] - sa[1], rh - ra),
                                    None if sr is None or srh is None or sra is None else srh - sra)
                if f is not None:
                    lfeat[gid] = f
            rp.add(g, rows_[g["home"]], rows_[g["away"]])
        if sr is not None and gid in byst:
            sr.add_stints(g, byst[gid])
        pt = lt.pace_total(g["home"], g["away"])  # pre-game: a second, possession-based total estimate
        ctx["pace_corr"] = round(pt - (b[0] + b[1]), 3) if (pt is not None and b) else 0.0
        lt.post_game(g, rows_)
        margin = g["home_pts"] - g["away_pts"]
        total = g["home_pts"] + g["away_pts"]
        ctx["refs_total"] = round(otr.crew(g.get("refs")), 3)
        if b:
            otr.post_game(g.get("refs"), total - (b[0] + b[1]))
        if b:
            rows.append((ctx, margin, b[0] - b[1], total, b[0] + b[1], g["day"], gid))
        tr.post_game(g, base_margin=(b[0] - b[1]) if b else None,
                     box_players={t: dict(v) for t, v in box.items()} if played else None)
        meta[gid] = g
    rows_raw = list(rows)
    stack = fit_stack([r for r in rows if effects_until is None or r[5] < effects_until], lfeat)
    if stack is not None:  # effects are measured on what the player-strength base still misses
        rows = [(r[0], r[1], stacked(stack, r[2], lfeat.get(r[6])), r[3], r[4], r[5], r[6]) for r in rows]
    use = [r for r in rows if effects_until is None or r[5] < effects_until]
    eff = effects.estimate([r[:5] for r in use], tuned["lam_effects"])
    c = Context()
    c.tuned, c.base, c.ctxs, c.rows, c.eff, c.tracker, c.games, c.meta = tuned, base, ctxs, rows, eff, tr, fin, meta
    rp.fit(fin["day"].max() if len(fin) else date.today().isoformat())  # latest ratings for upcoming games
    if sr is not None:
        sr.fit(fin["day"].max())
    c.lineup, c.lfeat, c.stack, c.rows_raw, c.style, c.rapm, c.officials = lt, lfeat, stack, rows_raw, sty, rp, otr
    c.srapm = sr
    c.stints = stints  # play-by-play lineups, also read by player_engine.walk (rotation habits)
    return c


def player_features(base3, stint_gap):
    """(gamescore gap, plus-minus gap, adjusted plus-minus gap) plus the stint-rating gap per SRAPM_MODE."""
    if SRAPM_MODE == "off":
        return base3
    if stint_gap is None:
        return base3 if SRAPM_MODE == "replace" else None
    if SRAPM_MODE == "replace":
        return (base3[0], base3[1], stint_gap)
    return base3 + (stint_gap,)


def fit_stack(rows, lfeat, min_rows=300):
    """margin = a*base + b*gamescore gap + c*plus-minus gap + e*adjusted plus-minus gap + d, ridge on b, c, e."""
    X, y = [], []
    for r in rows:
        f = lfeat.get(r[6])
        if f is None:
            continue
        X.append([r[2], *f, 1.0])
        y.append(r[1])
    if len(X) < min_rows:
        return None
    X, y = np.array(X), np.array(y)
    lam = np.diag([0.0] + [STACK_LAM] * (X.shape[1] - 2) + [0.0])
    w = np.linalg.solve(X.T @ X + lam, X.T @ y)
    return {"w": [float(v) for v in w], "n": len(y)}


def stacked(stack, base_margin, feat):
    if stack is None or feat is None:
        return base_margin
    w = stack["w"]
    if len(feat) != len(w) - 2:
        return base_margin
    return w[0] * base_margin + sum(wi * fi for wi, fi in zip(w[1:-1], feat)) + w[-1]


def baseline(games, season, team, before):
    """Plain averages: points for/against per game this season before the game (last season early on)."""
    games = games[games["day"] < before]
    g = games[(games["season"] == season) & (games["stype"] == 2)]
    m = g[(g["home"] == team) | (g["away"] == team)]
    if len(m) < 5:
        g = games[(games["season"] == season - 1) & (games["stype"] == 2)]
        m = g[(g["home"] == team) | (g["away"] == team)]
    if not len(m):
        return 114.0, 114.0
    pf = [h if ht == team else a for ht, h, a in zip(m["home"], m["home_pts"], m["away_pts"])]
    pa = [a if ht == team else h for ht, h, a in zip(m["home"], m["home_pts"], m["away_pts"])]
    return sum(pf) / len(pf), sum(pa) / len(pa)


# shrink 50 (was 150): a league-wide scoring change is picked up sooner. This season's totals ran 2.4 points
# high with 150; 50 cuts that to ~1.6 and does not hurt total error in 2023-24 to 2025-26 (Nov 2026 test).
LEVEL_N, LEVEL_SHRINK, LEVEL_CAP = 200, 50, 6.0


def total_level(c, season, before):
    """League scoring level this season: mean of (actual - base total) over the last LEVEL_N regulation games
    before `before`, shrunk towards 0 while few games are in. Ratings adapt slowly when the whole league
    scores more or less than last year; this catches it in a few weeks (walk-forward: better total error
    in four of five seasons, 2023-24 by 0.4 points)."""
    cache = c.__dict__.setdefault("_lvl", {})
    key = (int(season), str(before)[:10])
    if key not in cache:
        res = []
        for r in getattr(c, "rows_raw", []):
            if r[5] >= key[1]:
                break
            mg = c.meta.get(r[6]) or {}
            if int(mg.get("season") or 0) == key[0] and not int(mg.get("ot") or 0):
                res.append(r[3] - r[4])
        res = res[-LEVEL_N:]
        lv = sum(res) / (len(res) + LEVEL_SHRINK) if res else 0.0
        cache[key] = max(-LEVEL_CAP, min(LEVEL_CAP, lv))
    return cache[key]


def predict(c, g, ctx, rts, eff=None, base_override=None, lineup_feat=None, stack="default"):
    """g: game dict (home, away, neutral, season). rts: {stat: Rating}. Returns the full estimate."""
    eff = eff or c.eff
    h, a = g["home"], g["away"]
    neutral = bool(g.get("neutral"))
    if base_override is not None:
        bh, ba = base_override
    else:
        bh, ba = ratings.predict_game(rts["pts"], h, a, neutral)
    base_m, base_t = bh - ba, bh + ba
    results_only_m = base_m
    st_ = getattr(c, "stack", None) if stack == "default" else stack
    if lineup_feat is not None and st_:
        base_m = stacked(st_, base_m, lineup_feat)
        bh, ba = (base_t + base_m) / 2, (base_t - base_m) / 2
    parts = effects.contributions(eff, ctx)
    phys_m = sum(p["pts"] for p in parts if p["target"] == "margin" and p["layer"] == "physical")
    mind_m = sum(p["pts"] for p in parts if p["target"] == "margin" and p["layer"] == "mind")
    phys_t = sum(p["pts"] for p in parts if p["target"] == "total" and p["layer"] == "physical")
    mind_t = sum(p["pts"] for p in parts if p["target"] == "total" and p["layer"] == "mind")
    m = base_m + phys_m + mind_m
    lvl = total_level(c, g["season"], g["day"]) if getattr(c, "rows_raw", None) else 0.0
    t = base_t + phys_t + mind_t + lvl
    sdm, sdt = (eff.sd_for(m) if hasattr(eff, "sd_for") else eff.sd_margin), eff.sd_total
    win = effects.norm_cdf(m / sdm)
    win_nomind = effects.norm_cdf((m - mind_m) / sdm)
    pf_h, pa_h = baseline(c.games, int(g["season"]), h, g["day"])
    pf_a, pa_a = baseline(c.games, int(g["season"]), a, g["day"])
    bl_m = (pf_h - pa_h) - (pf_a - pa_a) + (0 if neutral else 2.5)
    bl_t = (pf_h + pa_a + pf_a + pa_h) / 2
    out = {
        "home_pts": (t + m) / 2, "away_pts": (t - m) / 2, "margin": m, "total": t, "win_home": win,
        "base": {"home_pts": bh, "away_pts": ba, "margin": base_m, "total": base_t, "win_home": effects.norm_cdf(base_m / sdm),
                 "results_margin": results_only_m, "lineup": lineup_feat is not None and bool(st_)},
        "level_total": round(lvl, 2),
        "physical": {"margin": phys_m, "total": phys_t}, "mind": {"margin": mind_m, "total": mind_t},
        "win_home_nomind": win_nomind, "margin_nomind": m - mind_m, "total_nomind": t - mind_t,
        "baseline": {"margin": bl_m, "total": bl_t, "win_home": effects.norm_cdf(bl_m / sdm)},
        "sd_margin": sdm, "sd_total": sdt, "parts": parts,
    }
    others = {}
    for st in ("tpm", "reb", "ast"):
        rt = rts.get(st)
        if rt is None:
            continue
        xh, xa = ratings.predict_game(rt, h, a, neutral)
        others[st] = {"home": xh, "away": xa, "total": xh + xa, "sd_total": rt.sd * 1.35}
    out["others"] = others
    return out


def fit_all(games, asof, tuned):
    return {st: ratings.fit(games, st, asof=asof, half_life=tuned["half_life"], lam=tuned["lam"], carry=tuned["carry"])
            for st in ratings.STATS}


def today_iso(now):
    return now.date().isoformat() if hasattr(now, "date") else date.today().isoformat()


def lineup_test(c, cur):
    """Out-of-sample check of the player-strength upgrade: weights fitted before this season, scored on it."""
    def sc(pred, ys, sd):
        p = np.array([effects.norm_cdf(x / sd) for x in pred])
        y = np.array([1.0 if v > 0 else 0.0 for v in ys])
        pc = np.clip(p, 1e-6, 1 - 1e-6)
        return {"brier": round(float(np.mean((p - y) ** 2)), 4),
                "logloss": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 4),
                "winners": round(float(np.mean((p >= 0.5) == (y == 1))), 4),
                "mae_margin": round(float(np.mean(np.abs(np.array(ys) - np.array(pred)))), 3)}
    start = c.games.loc[c.games["season"] == cur, "day"].min() if (c.games["season"] == cur).any() else None
    if start is None:
        return None
    raw = [(gid, g) for gid, g in c.meta.items() if gid in c.base and gid in c.lfeat]
    tr = [(c.base[gid][0] - c.base[gid][1], c.lfeat[gid], g["home_pts"] - g["away_pts"]) for gid, g in raw if g["day"] < start]
    te = [(c.base[gid][0] - c.base[gid][1], c.lfeat[gid], g["home_pts"] - g["away_pts"]) for gid, g in raw if g["day"] >= start]
    if len(tr) < 300 or not te:
        return None
    X = np.array([[b, *f, 1.0] for b, f, _ in tr])
    y = np.array([m for _, _, m in tr])
    w = np.linalg.solve(X.T @ X + np.diag([0] + [STACK_LAM] * (X.shape[1] - 2) + [0]), X.T @ y)
    sd_new = float(np.std(y - X @ w))
    sd_old = float(np.std(y - X[:, 0]))
    before = sc([b for b, _, _ in te], [m for _, _, m in te], sd_old)
    after = sc([w[0] * b + sum(wi * fi for wi, fi in zip(w[1:-1], f)) + w[-1] for b, f, _ in te], [m for _, _, m in te], sd_new)
    return {"games": len(te), "before": before, "after": after}
