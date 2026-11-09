"""Testing the player model against prop lines.

1. Real lines (data/props/lines.csv, archived from The Odds API): for every archived line with a result,
   compare the model's chance with the market's no-margin chance (Brier score, log loss), and check
   the bets the model would have made (edge >= 4% at the opening price): hit rate, return at the
   prices actually offered, and closing-line value (did the line or price move our way?).
2. Until enough real lines exist, a proxy: the line a book would most likely post (the player's season
   average so far, rounded to .5). When the model disagrees with that line, how often is it right?
"""
import math
from collections import defaultdict

from .effects import norm_cdf
from .players import over_prob, sd_for

MIN_FOR_WEIGHT = 300  # settled lines before the measured market weight replaces 50/50


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def market_weight(rows):
    """How much to trust the model against the posted line's no-margin price, measured on settled lines:
    the log-odds weight w (model) / 1 - w (market) with the lowest log loss. 50/50 until enough lines."""
    if len(rows) < MIN_FOR_WEIGHT:
        return {"w": 0.5, "n": len(rows), "measured": False}
    lg = lambda p: math.log(max(p, 1e-6) / max(1 - p, 1e-6))
    best = None
    for i in range(0, 21):
        w = i / 20
        ll = sum(_ll(1 / (1 + math.exp(-(w * lg(r["model"]) + (1 - w) * lg(r["market"])))), r["y"]) for r in rows) / len(rows)
        if best is None or ll < best[1]:
            best = (w, ll)
    return {"w": best[0], "n": len(rows), "measured": True, "ll": round(best[1], 4)}


def real_lines(first_last, frozen_proj, actual, disp, calib):
    """first_last: {(game_id, player, stat): (open row, close row)}; frozen_proj: {(game_id, player): {stat: proj}};
    actual: {(game_id, player): {stat: value}} (normalised player names)."""
    rows = []
    for (gid, pl, st), (op, cl) in first_last.items():
        pr = (frozen_proj.get((gid, pl)) or {}).get(st)
        a = (actual.get((gid, pl)) or {}).get(st)  # None when not recorded
        if pr is None or a is None or not cl:
            continue
        L = float(cl["line"])
        if a == L:
            continue
        sd = sd_for(st, pr, disp)
        t = (calib.get(st) or {}).get("t", 1.0)
        pm = over_prob(st, L, pr, disp)
        pm = 1 / (1 + math.exp(-t * math.log(max(pm, 1e-6) / max(1 - pm, 1e-6))))
        io, iu = 1 / float(cl["over"]), 1 / float(cl["under"])
        mk = io / (io + iu)
        y = 1.0 if a > L else 0.0
        bet = None
        if op:
            Lo = float(op["line"])
            po = over_prob(st, Lo, pr, disp)
            po = 1 / (1 + math.exp(-t * math.log(max(po, 1e-6) / max(1 - po, 1e-6))))
            for side, p_side, price in (("over", po, float(op["over"])), ("under", 1 - po, float(op["under"]))):
                if p_side * price - 1 >= 0.04:
                    won = (a > Lo) if side == "over" else (a < Lo)
                    push = a == Lo
                    clv = (L - Lo) if side == "over" else (Lo - L)
                    if clv == 0:
                        ic_o, ic_u = 1 / float(cl["over"]), 1 / float(cl["under"])
                        io_o, io_u = 1 / float(op["over"]), 1 / float(op["under"])
                        clv_p = (ic_o / (ic_o + ic_u) - io_o / (io_o + io_u)) * (1 if side == "over" else -1)
                    else:
                        clv_p = None
                    bet = {"side": side, "won": won, "push": push, "price": price, "clv_pts": clv, "clv_p": clv_p}
                    break
        rows.append({"model": pm, "market": mk, "y": y, "stat": st, "bet": bet})
    n = len(rows)
    if not n:
        return {"n": 0}
    out = {"n": n, "blend": market_weight(rows),
           "brier_model": round(sum((r["model"] - r["y"]) ** 2 for r in rows) / n, 4),
           "brier_market": round(sum((r["market"] - r["y"]) ** 2 for r in rows) / n, 4),
           "brier_blend": round(sum((0.5 * r["model"] + 0.5 * r["market"] - r["y"]) ** 2 for r in rows) / n, 4),
           "logloss_model": round(sum(_ll(r["model"], r["y"]) for r in rows) / n, 4),
           "logloss_market": round(sum(_ll(r["market"], r["y"]) for r in rows) / n, 4)}
    bets = [r["bet"] for r in rows if r["bet"] and not r["bet"]["push"]]
    if bets:
        ret = sum((b["price"] - 1) if b["won"] else -1 for b in bets)
        clvs = [b for b in bets if b["clv_pts"] or b["clv_p"] is not None]
        out["bets"] = {"n": len(bets), "won": sum(b["won"] for b in bets), "roi": round(ret / len(bets), 4),
                       "clv_beat": sum(((b["clv_pts"] or 0) > 0) or ((b["clv_p"] or 0) > 0) for b in clvs),
                       "clv_n": len(clvs)}
    by = defaultdict(list)
    for r in rows:
        by[r["stat"]].append(r)
    out["by_stat"] = {st: {"n": len(v), "brier_model": round(sum((r["model"] - r["y"]) ** 2 for r in v) / len(v), 4),
                           "brier_market": round(sum((r["market"] - r["y"]) ** 2 for r in v) / len(v), 4)} for st, v in by.items()}
    return out


def proxy_lines(plogs, byg, games_order, disp, calib, min_gp=5):
    """Model vs a season-average line, walking games in order (season average strictly before each game)."""
    tot = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))  # pid -> stat -> [sum, n]
    res = defaultdict(lambda: {"n": 0, "right": 0, "strong_n": 0, "strong_right": 0})
    for gid in games_order:
        teams = byg.get(gid)
        if not teams:
            continue
        for rows in teams.values():
            for r in rows:
                if r["min"] <= 0:
                    continue
                pid = r["player_id"]
                proj = plogs.get((gid, pid))
                vals = {"pts": r["pts"], "reb": r["reb"], "ast": r["ast"], "tpm": r["tpm"], "pra": r["pts"] + r["reb"] + r["ast"]}
                if proj:
                    for st, a in vals.items():
                        s, n = tot[pid][st]
                        if a is None or n < min_gp or st not in proj:
                            continue
                        L = math.floor(s / n) + 0.5
                        if a == L:
                            continue
                        sd = sd_for(st, proj[st], disp)
                        p_over = 1 - norm_cdf((L - proj[st]) / sd)
                        side_over = p_over >= 0.5
                        conf = max(p_over, 1 - p_over)
                        right = (a > L) == side_over
                        rr = res[st]
                        rr["n"] += 1
                        rr["right"] += right
                        if conf >= 0.6:
                            rr["strong_n"] += 1
                            rr["strong_right"] += right
                for st, a in vals.items():
                    if a is None:
                        continue
                    tot[pid][st][0] += a
                    tot[pid][st][1] += 1
    return {st: {**v, "hit": round(v["right"] / v["n"], 3) if v["n"] else None,
                 "strong_hit": round(v["strong_right"] / v["strong_n"], 3) if v["strong_n"] else None} for st, v in res.items()}
