"""Daily parlay builder.

The mathematics, in short:
1. A parlay only pays if every leg wins, and the bookmaker's margin is multiplied with every leg. So a leg
   belongs in a parlay only if it is worth taking on its own: its calibrated chance must beat the price.
   Every leg therefore shows its fair odds (1 / chance) and the minimum price at which it is worth taking.
2. Model chances are calibrated before use: team markets are blended with the market's no-margin price
   (markets are hard to beat; the blend keeps us honest), player props are shrunk towards 50% by a
   factor fitted on past player-games, so an "80%" leg really wins about 80% of the time.
3. Legs from the same game are correlated (a team that scores a lot lifts its scorers and the total).
   Joint chances come from simulating each game 20,000 times; the correlation lift is shown.
4. Psychology enters twice: the team and player spots are already inside the chances, and every leg
   is checked for a psychological spot working against it.
"""
import math

import numpy as np

from .effects import norm_cdf

SIMS = 20000
P_MIN, P_MAX = 0.55, 0.86
PROP_MAX = 0.80          # alternate prop lines beyond this are priced too short to carry value
EDGE_W = 3.0             # how much a measured price edge is worth against chance when ranking tickets
SAFETY = 1.05            # ask 5% more than fair odds before calling a leg worth taking
BETA = {"pts": 1.0, "pra": 0.85, "ast": 0.6, "reb": 0.3, "tpm": 0.8}
STAT_NAME = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "threes", "pra": "pts+reb+ast"}
STD_PRICE = 1.91         # a standard -110 line, for spreads and totals without a price


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


# ------------------------------------------------------------------ calibration of player props
def fit_prop_calibration(plogs, byg, disp):
    """Temperature per stat: p_cal = sigmoid(T * logit(p)), fitted by log loss on past player-games."""
    from .players import sd_for
    actual = {}
    for gid, teams in byg.items():
        for rows in teams.values():
            for r in rows:
                if r["min"] > 0:
                    actual[(gid, r["player_id"])] = {"pts": r["pts"], "reb": r["reb"], "ast": r["ast"], "tpm": r["tpm"],
                                                     "pra": r["pts"] + r["reb"] + r["ast"]}
    out = {}
    for st in ("pts", "reb", "ast", "tpm", "pra"):
        ps, ys = [], []
        for key, pr in plogs.items():
            a = actual.get(key)
            if not a or st not in pr:
                continue
            proj = pr[st]
            sd = sd_for(st, proj, disp)
            for k in (-1.5, -0.75, 0.0, 0.75, 1.5):
                L = math.floor(proj + k * sd) + 0.5
                if L <= 0:
                    continue
                p = 1 - norm_cdf((L - proj) / sd)
                ps.append(p)
                ys.append(1.0 if a[st] > L else 0.0)
        if len(ps) < 500:
            out[st] = {"t": 0.75, "n": len(ps), "fitted": False}
            continue
        lp = np.array([logit(p) for p in ps])
        y = np.array(ys)
        best = None
        for t in np.arange(0.3, 1.31, 0.05):
            q = 1 / (1 + np.exp(-t * lp))
            q = np.clip(q, 1e-6, 1 - 1e-6)
            ll = -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))
            if best is None or ll < best[0]:
                best = (ll, float(t))
        # reliability table at the fitted temperature
        q = 1 / (1 + np.exp(-best[1] * lp))
        bins = []
        for lo in (0.5, 0.6, 0.7, 0.8, 0.9):
            m = ((q >= lo) & (q < lo + 0.1)) | ((1 - q >= lo) & (1 - q < lo + 0.1))
            if m.sum() >= 30:
                pick_over = q[m] >= 0.5
                hit = np.where(pick_over, y[m], 1 - y[m])
                conf = np.where(pick_over, q[m], 1 - q[m])
                bins.append({"p": round(float(conf.mean()), 3), "hit": round(float(hit.mean()), 3), "n": int(m.sum())})
        out[st] = {"t": round(best[1], 2), "n": len(ps), "fitted": True, "bins": bins}
    return out


# ------------------------------------------------------------------ candidate legs
def _leg(game, kind, desc, p_model, p_cal, price=None, **kw):
    fair = 1 / p_cal
    leg = {"game": game["id"], "kind": kind, "desc": desc, "p_model": round(p_model, 3), "p": round(p_cal, 3),
           "fair": round(fair, 2), "min_odds": round(fair * SAFETY, 2), "price": price,
           "edge": round(p_cal * price - 1, 3) if price else None, **kw}
    return leg


def team_legs(game, est, odds, mind_gap):
    """mind_gap: home gauge - away gauge (psychological spots, in points)."""
    H, A = game["home"], game["away"]
    m, sdm, t, sdt = est["margin"], est["sd_margin"], est["total"], est["sd_total"]
    legs = []
    ph = est["win_home"]
    if odds and odds.get("ml_home") and odds.get("ml_away"):
        ih, ia = 1 / odds["ml_home"], 1 / odds["ml_away"]
        mk = ih / (ih + ia)
        pc = sigmoid(0.5 * logit(ph) + 0.5 * logit(mk))
        src = "blended 50/50 with the market's no-margin price"
    else:
        mk, pc = None, sigmoid(0.8 * logit(ph))
        src = "no market price: shrunk 20% towards 50/50"
    for team, p_mod, p_c, price, mg in ((H, ph, pc, (odds or {}).get("ml_home"), mind_gap),
                                         (A, 1 - ph, 1 - pc, (odds or {}).get("ml_away"), -mind_gap)):
        legs.append(_leg(game, "ml", f"{team} to win", p_mod, p_c, price, team=team, market=mk if team == H else (1 - mk if mk else None),
                         note=src, mind=mg, sim=("win", team)))
    if odds and odds.get("spread_home") is not None:
        L = odds["spread_home"]
        p = norm_cdf((m + L) / sdm)
        pc = sigmoid(0.5 * logit(p))
        lab = lambda x: f"{x:+.1f}".replace("+0.0", "0")
        legs.append(_leg(game, "spread", f"{H} {lab(L)}", p, pc, STD_PRICE, team=H, line=L, note="market line, shrunk halfway to 50/50",
                         mind=mind_gap, sim=("cover", H, L)))
        legs.append(_leg(game, "spread", f"{A} {lab(-L)}", 1 - p, 1 - pc, STD_PRICE, team=A, line=-L,
                         note="market line, shrunk halfway to 50/50", mind=-mind_gap, sim=("cover", A, -L)))
    T = odds.get("total") if odds and odds.get("total") else math.floor(t) + 0.5
    for line, base in ((T, True), (T - 6, False), (T + 6, False)):
        po = 1 - norm_cdf((line - t) / sdt)
        shrink = 0.5 if (odds and odds.get("total")) else 0.75
        pc = sigmoid(shrink * logit(po))
        price = STD_PRICE if base and odds and odds.get("total") else None
        if base or pc >= 0.5:
            legs.append(_leg(game, "total", f"Over {line:.1f} points", po, pc, price, line=line, side="over",
                             note="game total", mind=0.0, sim=("total", "over", line)))
        if base or pc < 0.5:
            legs.append(_leg(game, "total", f"Under {line:.1f} points", 1 - po, 1 - pc, price, line=line, side="under",
                             note="game total", mind=0.0, sim=("total", "under", line)))
    return legs


PROP_PRICE = 1.85        # typical price either side of a main player line


def prop_legs(game, players, calib, avg, disp):
    """Player props at the line a bookmaker would most likely post: books anchor main lines on the player's
    season average, so that line is estimated as his average rounded to .5. A leg is a candidate when the
    projection (matchup, minutes, teammates out, psychology) disagrees with that line."""
    from .players import LABEL, sd_for
    legs = []
    for side in ("home", "away"):
        team = game[side]
        for pl in players.get(side, []):
            if pl.get("out") or pl.get("status") or (pl.get("min") or 0) < 24:
                continue
            a = avg.get(pl["id"])
            if not a or a.get("gp", 0) < 3:
                continue
            spots = pl.get("spots") or []
            mind = sum(s["pct"] for s in spots if s.get("layer") == "mind")
            for st in ("pts", "reb", "ast", "tpm", "pra"):
                proj, av = pl.get(st), a.get(st)
                if proj is None or av is None or av != av or av < (1.0 if st == "tpm" else 3):
                    continue
                L = math.floor(av) + 0.5
                # like team legs against the market: blend the projection 50/50 with the line's anchor
                center = 0.5 * proj + 0.5 * av
                sd = sd_for(st, center, disp)
                po = 1 - norm_cdf((L - center) / sd)
                t = (calib.get(st) or {}).get("t", 0.75)
                for sd_, pm in (("over", po), ("under", 1 - po)):
                    pc = sigmoid(t * logit(pm))
                    if 0.5 <= pc <= PROP_MAX:
                        legs.append(_leg(game, "prop", f"{pl['name']} {sd_} {L:.1f} {STAT_NAME[st]}", pm, pc, PROP_PRICE,
                                         team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side=sd_,
                                         proj=proj, avg=round(av, 1), price_est=True,
                                         note=f"projection {proj:.1f} vs season average {av:.1f} {LABEL.get(st, st).lower()} (blended 50/50); line estimated",
                                         mind=mind if sd_ == "over" else -mind, spots=[x["label"] for x in spots],
                                         sim=("prop", side, pl["id"], st, sd_, L)))
    return legs


# ------------------------------------------------------------------ correlated simulation per game
def simulate(game, est, players, disp, rng):
    m = rng.normal(est["margin"], est["sd_margin"], SIMS)
    t = rng.normal(est["total"], est["sd_total"], SIMS)
    hp, ap = (t + m) / 2, (t - m) / 2
    out = {"m": m, "t": t, "home": hp, "away": ap, "players": {}}
    exp = {"home": max(est["home_pts"], 60), "away": max(est["away_pts"], 60)}
    for side in ("home", "away"):
        r = np.clip(out[side] / exp[side], 0.6, 1.5)
        for pl in players.get(side, []):
            if pl.get("out"):
                continue
            sims = {}
            for st in ("pts", "reb", "ast", "tpm"):
                proj = pl.get(st) or 0.0
                var = max(proj, 0.3) * disp.get(st, 1.5)
                shared = proj * (r ** BETA[st])
                var_shared = float(np.var(shared))
                eps = rng.normal(0, math.sqrt(max(var - var_shared, 0.25 * var)), SIMS)
                sims[st] = np.maximum(0, shared + eps)
            sims["pra"] = sims["pts"] + sims["reb"] + sims["ast"]
            out["players"][pl["id"]] = sims
    return out


def outcome(sim, leg, game):
    k = leg["sim"]
    if k[0] == "win":
        return sim["m"] > 0 if k[1] == game["home"] else sim["m"] < 0
    if k[0] == "cover":
        return (sim["m"] + k[2] > 0) if k[1] == game["home"] else (-sim["m"] + k[2] > 0)
    if k[0] == "total":
        return sim["t"] > k[2] if k[1] == "over" else sim["t"] < k[2]
    if k[0] == "prop":
        x = sim["players"].get(k[2], {}).get(k[3])
        if x is None:
            return np.zeros(SIMS, bool)
        return x > k[5] if k[4] == "over" else x < k[5]
    return np.zeros(SIMS, bool)


# ------------------------------------------------------------------ choosing the parlays
def _conflict(a, b):
    if a["game"] != b["game"]:
        return False
    if a.get("player") and a.get("player") == b.get("player"):
        return True
    if a["kind"] in ("ml", "spread") and b["kind"] in ("ml", "spread"):
        return True
    if a["kind"] == "total" and b["kind"] == "total":
        return True
    return False


def joint(legs, sims, games):
    """Calibrated joint chance: product of calibrated chances x the simulated correlation lift per game."""
    by_game = {}
    for l in legs:
        by_game.setdefault(l["game"], []).append(l)
    p_ind, p_joint = 1.0, 1.0
    for gid, ls in by_game.items():
        mask = np.ones(SIMS, bool)
        prod_sim = 1.0
        for l in ls:
            o = l["_o"]
            mask &= o
            prod_sim *= max(o.mean(), 1e-6)
        lift = mask.mean() / prod_sim if prod_sim > 0 else 1.0
        pc = 1.0
        for l in ls:
            pc *= l["p"]
        p_ind *= pc
        p_joint *= min(pc * lift, min(l["p"] for l in ls))
    return p_joint, p_ind


def search(cands, k, sims, games, max_per_game=2, min_games=None, beam=60):
    cands = sorted(cands, key=lambda l: -(math.log(l["p"]) + EDGE_W * (l["edge"] or 0)))[:160]
    states = [((), 1.0)]
    for _ in range(k):
        nxt = {}
        for legs, _ in states:
            used_games = {}
            for l in legs:
                used_games[l["game"]] = used_games.get(l["game"], 0) + 1
            for c in cands:
                if any(c is l for l in legs) or any(_conflict(c, l) for l in legs):
                    continue
                if used_games.get(c["game"], 0) >= max_per_game:
                    continue
                new = tuple(sorted(legs + (c,), key=id))
                key = tuple(id(x) for x in new)
                if key in nxt:
                    continue
                pj, _ = joint(new, sims, games)
                sc = math.log(max(pj, 1e-9)) + EDGE_W * sum(l["edge"] or 0 for l in new)
                nxt[key] = (new, sc)
        states = sorted(nxt.values(), key=lambda s: -s[1])[:beam]
        if not states:
            return None
    if min_games:
        ok = [s for s in states if len({l["game"] for l in s[0]}) >= min_games]
        states = ok or states
    return states[0][0] if states else None


def package(name, why, legs, sims, games):
    pj, pi = joint(legs, sims, games)
    fair = 1 / pj if pj > 0 else None
    return {"name": name, "why": why, "legs": [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in legs],
            "p": round(pj, 4), "p_independent": round(pi, 4), "lift": round(pj / pi, 3) if pi else 1.0,
            "fair": round(fair, 2) if fair else None, "min_odds": round(fair * SAFETY, 2) if fair else None,
            "n_legs": len(legs), "games": len({l["game"] for l in legs})}


def build(slate, disp, calib, avg=None, seed=5):
    """slate: list of (game dict, payload). Returns the day's parlays and the full leg board."""
    rng = np.random.default_rng(seed)
    games, sims, cands = {}, {}, []
    for g, pay in slate:
        game = {"id": str(pay["id"]), "home": pay["home"]["abbr"], "away": pay["away"]["abbr"], "tip": pay["tip"]}
        games[game["id"]] = game
        est = pay["est"]
        players = pay.get("players") or {}
        sims[game["id"]] = simulate(game, est, players, disp, rng)
        gap = (pay.get("gauge") or {}).get("home", 0) - (pay.get("gauge") or {}).get("away", 0)
        legs = team_legs(game, est, g.get("odds"), gap) + prop_legs(game, players, calib, avg or {}, disp)
        for l in legs:
            l["_o"] = outcome(sims[game["id"]], l, game)
            l["matchup"] = f"{game['away']} at {game['home']}"
            l["tip"] = game["tip"]
            l["mind_flag"] = "against" if (l.get("mind") or 0) <= -0.3 else "with" if (l.get("mind") or 0) >= 0.3 else "neutral"
        cands += legs
    # a leg is eligible if its chance is in range, the price (when known) is worth taking, and the mind is not against it
    elig = [l for l in cands if P_MIN <= l["p"] <= P_MAX and (l["edge"] is None or l["edge"] >= 0) and l["mind_flag"] != "against"]
    n_games = len(games)
    out = {"games": n_games, "candidates": len(cands), "eligible": len(elig), "parlays": []}
    if not elig or n_games == 0:
        return out, cands
    six = search(elig, min(6, len(elig)), sims, games, max_per_game=2 if n_games >= 3 else 3, min_games=min(4, n_games))
    if six:
        out["parlays"].append(package("The daily 6", "Six legs balancing the chance of all landing together with measured value against "
                                      "the market: at most two per game, every priced leg worth taking on its own, none with a "
                                      "psychological spot against it.", list(six), sims, games))
        core = search(list(six), min(3, len(six)), sims, games, max_per_game=2)
        if core:
            out["parlays"].append(package("Core 3", "The three strongest legs of the daily 6. Fewer legs, much less bookmaker margin: "
                                          "the mathematically sounder ticket.", list(core), sims, games))
    best_sg = None
    for gid in games:
        gl = [l for l in elig if l["game"] == gid]
        if len(gl) < 3:
            continue
        sg = search(gl, 3, sims, games, max_per_game=3)
        if sg:
            pj, pi = joint(sg, sims, games)
            score = pj * (pj / pi)
            if best_sg is None or score > best_sg[0]:
                best_sg = (score, sg)
    if best_sg:
        out["parlays"].append(package("Same-game 3", "Three legs from one game that tend to land together (positive correlation). "
                                      "Bookmakers reprice same-game combos, so compare their price with the minimum odds.", list(best_sg[1]), sims, games))
    singles = sorted([l for l in cands if l.get("edge") is not None and l["edge"] > 0.02 and l["mind_flag"] != "against"
                      and not l.get("price_est")],
                     key=lambda l: -l["edge"])[:6]
    out["singles"] = [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in singles]
    return out, cands


def board(cands, n=40):
    good = sorted([l for l in cands if P_MIN <= l["p"] <= P_MAX], key=lambda l: -l["p"])[:n]
    return [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in good]


# ------------------------------------------------------------------ scoring after the games
def score_leg(leg, game_row, players_rows):
    """game_row: finished game dict; players_rows: {player_id: row}. Returns 'hit', 'miss' or 'void'."""
    if game_row is None:
        return None
    hp, ap = int(game_row["home_pts"]), int(game_row["away_pts"])
    home = game_row["home"]
    m, t = hp - ap, hp + ap
    k = leg["kind"]
    if k == "ml":
        won = (m > 0) if leg["team"] == home else (m < 0)
        return "hit" if won else "miss"
    if k == "spread":
        v = (m if leg["team"] == home else -m) + leg["line"]
        return "void" if v == 0 else "hit" if v > 0 else "miss"
    if k == "total":
        return "hit" if (t > leg["line"]) == (leg["side"] == "over") else "miss"
    if k == "prop":
        r = players_rows.get(leg["player"])
        if not r or (r.get("min") or 0) <= 0:
            return "void"
        v = r["pts"] + r["reb"] + r["ast"] if leg["stat"] == "pra" else r.get(leg["stat"], 0)
        return "hit" if (v > leg["line"]) == (leg["side"] == "over") else "miss"
    return None
