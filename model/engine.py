"""One recipe for every game:  final = base ratings + physical adjustments + psychological adjustments.

build_context(): walks all finished games once (out-of-sample base predictions + the situation
before every game), measures the factor sizes, and leaves a tracker positioned at "now".
predict(): the estimate for one game, with every piece shown.
"""
from collections import defaultdict
from datetime import date

from . import effects, ratings
from .features import Tracker

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


def build_context(games, players, upcoming, tuned=None, effects_until=None):
    tuned = {**DEFAULT, **(tuned or {})}
    fin = games.sort_values(["date", "game_id"]).reset_index(drop=True)
    base = ratings.walk_forward(fin, half_life=tuned["half_life"], lam=tuned["lam"], carry=tuned["carry"])
    pg, names = players_by_game(players)
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
        ctxs[gid] = ctx
        b = base.get(gid)
        margin = g["home_pts"] - g["away_pts"]
        total = g["home_pts"] + g["away_pts"]
        if b:
            rows.append((ctx, margin, b[0] - b[1], total, b[0] + b[1], g["day"], gid))
        tr.post_game(g, base_margin=(b[0] - b[1]) if b else None,
                     box_players={t: dict(v) for t, v in box.items()} if played else None)
        meta[gid] = g
    use = [r for r in rows if effects_until is None or r[5] < effects_until]
    eff = effects.estimate([r[:5] for r in use], tuned["lam_effects"])
    c = Context()
    c.tuned, c.base, c.ctxs, c.rows, c.eff, c.tracker, c.games, c.meta = tuned, base, ctxs, rows, eff, tr, fin, meta
    return c


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


def predict(c, g, ctx, rts, eff=None, base_override=None):
    """g: game dict (home, away, neutral, season). rts: {stat: Rating}. Returns the full estimate."""
    eff = eff or c.eff
    h, a = g["home"], g["away"]
    neutral = bool(g.get("neutral"))
    if base_override is not None:
        bh, ba = base_override
    else:
        bh, ba = ratings.predict_game(rts["pts"], h, a, neutral)
    base_m, base_t = bh - ba, bh + ba
    parts = effects.contributions(eff, ctx)
    phys_m = sum(p["pts"] for p in parts if p["target"] == "margin" and p["layer"] == "physical")
    mind_m = sum(p["pts"] for p in parts if p["target"] == "margin" and p["layer"] == "mind")
    phys_t = sum(p["pts"] for p in parts if p["target"] == "total" and p["layer"] == "physical")
    mind_t = sum(p["pts"] for p in parts if p["target"] == "total" and p["layer"] == "mind")
    m = base_m + phys_m + mind_m
    t = base_t + phys_t + mind_t
    sdm, sdt = eff.sd_margin, eff.sd_total
    win = effects.norm_cdf(m / sdm)
    win_nomind = effects.norm_cdf((m - mind_m) / sdm)
    pf_h, pa_h = baseline(c.games, int(g["season"]), h, g["day"])
    pf_a, pa_a = baseline(c.games, int(g["season"]), a, g["day"])
    bl_m = (pf_h - pa_h) - (pf_a - pa_a) + (0 if neutral else 2.5)
    bl_t = (pf_h + pa_a + pf_a + pa_h) / 2
    out = {
        "home_pts": (t + m) / 2, "away_pts": (t - m) / 2, "margin": m, "total": t, "win_home": win,
        "base": {"home_pts": bh, "away_pts": ba, "margin": base_m, "total": base_t, "win_home": effects.norm_cdf(base_m / sdm)},
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
