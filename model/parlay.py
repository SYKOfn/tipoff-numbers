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
PROP_SIDES = ("over",)   # Winamax lists player markets as "over" only (X+ points etc.): no player unders
EDGE_W = 3.0             # how much a measured price edge is worth against chance when ranking tickets
EST_EDGE_W, EST_EDGE_CAP = 1.0, 0.12   # edges against an estimated line count less, and are capped
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
    from .players import sd_for, over_prob
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
            if not a or st not in pr or a.get(st) is None:
                continue
            proj = pr[st]
            sd = sd_for(st, proj, disp)
            for k in (-1.5, -0.75, 0.0, 0.75, 1.5):
                L = math.floor(proj + k * sd) + 0.5
                if L <= 0:
                    continue
                p = over_prob(st, L, proj, disp)
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
    import hashlib
    fair = 1 / p_cal
    leg = {"id": hashlib.md5(f"{game['id']}|{kind}|{desc}".encode()).hexdigest()[:10], "game": game["id"], "kind": kind, "desc": desc, "p_model": round(p_model, 3), "p": round(p_cal, 3),
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
        sp_h, sp_a = odds.get("spread_price_home"), odds.get("spread_price_away")
        pb = novig(sp_h, sp_a)
        pc = sigmoid(0.5 * logit(p) + 0.5 * logit(pb)) if pb else sigmoid(0.5 * logit(p))
        src = odds.get("spread_book") or "market"
        lab = lambda x: f"{x:+.1f}".replace("+0.0", "0")
        legs.append(_leg(game, "spread", f"{H} {lab(L)}", p, pc, sp_h or STD_PRICE, team=H, line=L, book=src if sp_h else None,
                         note=f"{src} main line, blended halfway with the market", mind=mind_gap, sim=("cover", H, L),
                         dist={"mu": round(m, 2), "sd": round(sdm, 2), "alone": 0.5, "model": 1.0}))
        legs.append(_leg(game, "spread", f"{A} {lab(-L)}", 1 - p, 1 - pc, sp_a or STD_PRICE, team=A, line=-L, book=src if sp_a else None,
                         note=f"{src} main line, blended halfway with the market", mind=-mind_gap, sim=("cover", A, -L),
                         dist={"mu": round(-m, 2), "sd": round(sdm, 2), "alone": 0.5, "model": 1.0}))
    if odds and odds.get("total"):
        T = odds["total"]
        po = 1 - norm_cdf((T - t) / sdt)
        pb = novig(odds.get("over"), odds.get("under"))
        pc = sigmoid(0.5 * logit(po) + 0.5 * logit(pb)) if pb else sigmoid(0.5 * logit(po))
        src = odds.get("total_book") or "market"
        for side, pm, pcs, price in (("over", po, pc, odds.get("over")), ("under", 1 - po, 1 - pc, odds.get("under"))):
            legs.append(_leg(game, "total", f"{side.capitalize()} {T:.1f} points", pm, pcs, price or STD_PRICE, line=T, side=side,
                             book=src if price else None, note=f"{src} main total", mind=0.0, sim=("total", side, T),
                             dist={"mu": round(t, 2), "sd": round(sdt, 2), "alone": 0.5, "model": 1.0}))
    return legs




def novig(a, b):
    """No-margin probability of side a from two decimal prices."""
    if not a or not b:
        return None
    ia, ib = 1 / float(a), 1 / float(b)
    return ia / (ia + ib)


def prop_legs(game, players, calib, avg, disp, real=None):
    """Player props at the line a bookmaker would most likely post: books anchor main lines on the player's
    season average, so that line is estimated as his average rounded to .5. A leg is a candidate when the
    projection (matchup, minutes, teammates out, psychology) disagrees with that line."""
    from .players import LABEL, sd_for, over_prob
    legs = []
    for side in ("home", "away"):
        team = game[side]
        for pl in players.get(side, []):
            if pl.get("out") or pl.get("status") or (pl.get("min") or 0) < 24 or (pl.get("p_play") or 1.0) < 0.6 or pl.get("lineup") == "not in the starting five":
                continue
            a = avg.get(pl["id"])
            if not a or a.get("gp", 0) < 3:
                continue
            spots = pl.get("spots") or []
            mind = sum(s["pct"] for s in spots if s.get("layer") == "mind")
            from pipeline.oddsapi import norm_name
            for st in ("pts", "reb", "ast", "tpm", "pra"):
                proj, av = pl.get(st), a.get(st)
                rl = (real or {}).get((game["id"], norm_name(pl["name"]), st))
                if rl:  # a real posted line: test the projection against it and its no-margin price
                    L = float(rl["line"])
                    sd = sd_for(st, proj, disp)
                    po = over_prob(st, L, proj, disp)
                    t = (calib.get(st) or {}).get("t", 0.75)
                    pm_over = novig(rl["over"], rl["under"])
                    for sd_, pm, price, mk in (("over", po, float(rl["over"]), pm_over), ("under", 1 - po, float(rl["under"]), 1 - pm_over)):
                        if sd_ not in PROP_SIDES:
                            continue
                        pc = sigmoid(0.5 * t * logit(pm) + 0.5 * logit(mk))
                        if 0.5 <= pc <= PROP_MAX:
                            legs.append(_leg(game, "prop", f"{pl['name']} {sd_} {L:.1f} {STAT_NAME[st]}", pm, pc, price,
                                             team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side=sd_,
                                             proj=proj, avg=None if av is None or av != av else round(av, 1), price_est=False,
                                             book=rl["book"], market=round(mk, 3),
                                             dist={"mu": round(proj, 2), "sd": round(sd, 2), "d": round(disp.get(st, 1.5), 3), "alone": t, "model": t},
                                             note=f"projection {proj:.1f}; real {rl['book']} line, blended 50/50 with its no-margin price",
                                             mind=mind if sd_ == "over" else -mind, spots=[x["label"] for x in spots],
                                             sim=("prop", side, pl["id"], st, sd_, L)))
                    continue
                if proj is None or av is None or av != av or av < (2.0 if st in ("tpm", "ast", "reb") else 3):
                    continue  # one-a-game stats: books post 0.5 or 1.5 with very uneven prices, too unreliable to estimate
                L = math.floor(av) + 0.5
                # like team legs against the market: blend the projection 50/50 with the line's anchor
                center = 0.5 * proj + 0.5 * av
                sd = sd_for(st, center, disp)
                po = over_prob(st, L, center, disp)
                # the price a book would ask: fair on the season-average anchor, plus a 5% margin. For low counts
                # (threes, assists) this is far from 1.85 - an under 1.5 threes for a one-a-game shooter is short.
                sda = sd_for(st, av, disp)
                pa_over = min(max(over_prob(st, L, av, disp), 0.03), 0.97)
                t = (calib.get(st) or {}).get("t", 0.75)
                for sd_, pm, pa in (("over", po, pa_over), ("under", 1 - po, 1 - pa_over)):
                    if sd_ not in PROP_SIDES:
                        continue
                    pc = sigmoid(t * logit(pm))
                    price = round(1 / (pa * 1.05), 2)
                    if 0.5 <= pc <= PROP_MAX and price >= 1.3:
                        legs.append(_leg(game, "prop", f"{pl['name']} {sd_} {L:.1f} {STAT_NAME[st]}", pm, pc, price,
                                         dist={"mu": round(center, 2), "sd": round(sd, 2), "d": round(disp.get(st, 1.5), 3), "alone": t, "model": t},
                                         team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side=sd_,
                                         proj=proj, avg=round(av, 1), price_est=True,
                                         note=f"projection {proj:.1f} vs season average {av:.1f} {LABEL.get(st, st).lower()} (blended 50/50); line and price estimated",
                                         mind=mind if sd_ == "over" else -mind, spots=[x["label"] for x in spots],
                                         sim=("prop", side, pl["id"], st, sd_, L)))
    return legs


# ------------------------------------------------------------------ legs from the betting book's own menu (Winamax)
BOOK_MARGIN = 1.06       # one-sided prices: assume about this margin to read the book's chance from its price


def _blend(p_model, p_book):
    return sigmoid(0.5 * logit(p_model) + 0.5 * logit(p_book))


def book_legs(game, est, players, odds, offers, calib, disp, mind_gap):
    """Only what the book lists, at its line and its price. Nothing estimated."""
    from pipeline.oddsapi import norm_name
    from .players import sd_for
    H, A = game["home"], game["away"]
    m, sdm, t, sdt = est["margin"], est["sd_margin"], est["total"], est["sd_total"]
    book = (odds or {}).get("provider") or "book"
    legs = []
    note = f"{book} price, blended 50/50 with the book's own chance"

    def add(kind, desc, pm, pb, price, **kw):
        pc = _blend(pm, pb)
        legs.append(_leg(game, kind, desc, pm, pc, round(price, 2), book=book, market=round(pb, 3), note=note, **kw))

    if odds and odds.get("ml_home") and odds.get("ml_away"):
        pb = novig(odds["ml_home"], odds["ml_away"])
        for team, pm, pbt, price, mg in ((H, est["win_home"], pb, odds["ml_home"], mind_gap), (A, 1 - est["win_home"], 1 - pb, odds["ml_away"], -mind_gap)):
            add("ml", f"{team} to win", pm, pbt, price, team=team, mind=mg, sim=("win", team))
    spreads = []
    if odds and odds.get("spread_home") is not None and odds.get("spread_price_home") and odds.get("spread_price_away"):
        L = odds["spread_home"]
        pbh = novig(odds["spread_price_home"], odds["spread_price_away"])
        spreads += [(H, L, odds["spread_price_home"], pbh), (A, -L, odds["spread_price_away"], 1 - pbh)]
    for o in offers:
        if o["kind"] == "spread":
            spreads.append((o["team"], o["point"], o["price"], min(0.97, 1 / (o["price"] * BOOK_MARGIN))))
    seen = set()
    for team, L, price, pb in spreads:
        if (team, L) in seen:
            continue
        seen.add((team, L))
        mt = m if team == H else -m
        pm = norm_cdf((mt + L) / sdm)
        lab = f"{L:+.1f}"
        add("spread", f"{team} {lab}", pm, pb, price, team=team, line=L, mind=mind_gap if team == H else -mind_gap, sim=("cover", team, L),
            dist={"mu": round(mt, 2), "sd": round(sdm, 2), "alone": 0.5, "model": 1.0})
    totals = []
    if odds and odds.get("total") is not None and odds.get("over") and odds.get("under"):
        pbo = novig(odds["over"], odds["under"])
        totals += [("over", odds["total"], odds["over"], pbo), ("under", odds["total"], odds["under"], 1 - pbo)]
    for o in offers:
        if o["kind"] == "total":
            totals.append((o["side"], o["point"], o["price"], min(0.97, 1 / (o["price"] * BOOK_MARGIN))))
    seen = set()
    for side, L, price, pb in totals:
        if (side, L) in seen:
            continue
        seen.add((side, L))
        po = 1 - norm_cdf((L - t) / sdt)
        add("total", f"{side.capitalize()} {L:.1f} points", po if side == "over" else 1 - po, pb, price, line=L, side=side,
            mind=0.0, sim=("total", side, L), dist={"mu": round(t, 2), "sd": round(sdt, 2), "alone": 0.5, "model": 1.0})
    sd_team = math.sqrt((sdt ** 2 + sdm ** 2) / 4)
    for o in offers:
        if o["kind"] == "team_total":
            exp = est["home_pts"] if o["team"] == H else est["away_pts"]
            po = 1 - norm_cdf((o["point"] - exp) / sd_team)
            add("team_total", f"{o['team']} {o['side']} {o['point']:.1f} points", po if o["side"] == "over" else 1 - po,
                min(0.97, 1 / (o["price"] * BOOK_MARGIN)), o["price"], team=o["team"], line=o["point"], side=o["side"], mind=0.0,
                sim=("tt", "home" if o["team"] == H else "away", o["side"], o["point"]))
    # player markets: two-sided main lines give the book's chance without margin; alternates are one-sided
    pairs = {}
    for o in offers:
        if o["kind"] == "prop":
            pairs.setdefault((norm_name(o["player"]), o["stat"], o["point"]), {})[o["side"]] = o["price"]
    by_name = {}
    for side in ("home", "away"):
        for pl in players.get(side, []):
            by_name[norm_name(pl["name"])] = (side, pl)
    for (nm, st, L), sides in pairs.items():
        hit = by_name.get(nm)
        if not hit:
            continue
        side, pl = hit
        if pl.get("out") or pl.get("status") or (pl.get("min") or 0) < 20 or pl.get(st) is None:
            continue
        proj = pl[st]
        sd = sd_for(st, proj, disp)
        tt = (calib.get(st) or {}).get("t", 0.75)
        from .players import over_prob
        po = sigmoid(tt * logit(min(max(over_prob(st, L, proj, disp), 1e-4), 1 - 1e-4)))
        both = novig(sides.get("over"), sides.get("under")) if len(sides) == 2 else None
        spots = pl.get("spots") or []
        mind = sum(x["pct"] for x in spots if x.get("layer") == "mind")
        for sd_, price in sides.items():
            if sd_ not in PROP_SIDES:
                continue
            pb = (both if sd_ == "over" else 1 - both) if both is not None else min(0.97, 1 / (price * BOOK_MARGIN))
            add("prop", f"{pl['name']} {sd_} {L:.1f} {STAT_NAME[st]}", po if sd_ == "over" else 1 - po, pb, price,
                team=game[side], player=pl["id"], player_name=pl["name"], stat=st, line=L, side=sd_, proj=proj,
                mind=mind if sd_ == "over" else -mind, spots=[x["label"] for x in spots], sim=("prop", side, pl["id"], st, sd_, L),
                dist={"mu": round(proj, 2), "sd": round(sd, 2), "d": round(disp.get(st, 1.5), 3), "alone": tt, "model": tt})
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
    if k[0] == "tt":
        x = sim[k[1]]
        return x > k[3] if k[2] == "over" else x < k[3]
    if k[0] == "prop":
        x = sim["players"].get(k[2], {}).get(k[3])
        if x is None:
            return np.zeros(SIMS, bool)
        return x > k[5] if k[4] == "over" else x < k[5]
    return np.zeros(SIMS, bool)


# ------------------------------------------------------------------ choosing the parlays
def edge_score(l):
    e = l.get("edge") or 0.0
    if l.get("price_est"):
        return EST_EDGE_W * min(e, EST_EDGE_CAP)
    return EDGE_W * e


def _conflict(a, b):
    if a["game"] != b["game"]:
        return False
    if a.get("player") and a.get("player") == b.get("player"):
        return True
    if a["kind"] in ("ml", "spread") and b["kind"] in ("ml", "spread"):
        return True
    if a["kind"] == "total" and b["kind"] == "total":
        return True
    if a["kind"] == "team_total" and b["kind"] == "team_total" and a.get("team") == b.get("team"):
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
    cands = sorted(cands, key=lambda l: -(math.log(l["p"]) + edge_score(l)))[:160]
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
                sc = math.log(max(pj, 1e-9)) + sum(edge_score(l) for l in new)
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


def build(slate, disp, calib, avg=None, seed=5, real_props=None, book_only=None):
    """slate: list of (game dict, payload). Returns the day's parlays and the full leg board."""
    rng = np.random.default_rng(seed)
    games, sims, cands = {}, {}, []
    out_skip = []
    for g, pay in slate:
        game = {"id": str(pay["id"]), "home": pay["home"]["abbr"], "away": pay["away"]["abbr"], "tip": pay["tip"]}
        est = pay["est"]
        players = pay.get("players") or {}
        gap = (pay.get("gauge") or {}).get("home", 0) - (pay.get("gauge") or {}).get("away", 0)
        if book_only:
            # only what the betting book lists for this game, at its own lines and prices
            if ((g.get("odds") or {}).get("provider") or "") != book_only:
                out_skip.append(f"{game['away']} at {game['home']}")
                continue
            legs = book_legs(game, est, players, g.get("odds"), (g.get("offers") or {}).get("offers", []), calib, disp, gap)
        else:
            legs = team_legs(game, est, g.get("odds"), gap) + prop_legs(game, players, calib, avg or {}, disp, real_props)
        games[game["id"]] = game
        sims[game["id"]] = simulate(game, est, players, disp, rng)
        for l in legs:
            l["_o"] = outcome(sims[game["id"]], l, game)
            l["matchup"] = f"{game['away']} at {game['home']}"
            l["home"] = game["home"]
            l["tip"] = game["tip"]
            l["mind_flag"] = "against" if (l.get("mind") or 0) <= -0.3 else "with" if (l.get("mind") or 0) >= 0.3 else "neutral"
        cands += legs
    # a leg is eligible if its chance is in range, the price (when known) is worth taking, and the mind is not against it
    elig = [l for l in cands if P_MIN <= l["p"] <= P_MAX and (l["edge"] is None or l["edge"] >= 0) and l["mind_flag"] != "against"
            and (not book_only or (l.get("price") or 0) >= 1.15)]
    n_games = len(games)
    out = {"games": n_games, "candidates": len(cands), "eligible": len(elig), "parlays": [], "book": book_only,
           "not_on_book": out_skip}
    if not elig or n_games == 0:
        return out, cands
    # Main picks are short: the bookmaker's margin multiplies with every leg, so two or three legs from
    # different games (where Winamax simply multiplies the odds) keep the most of any edge.
    priced = [l for l in elig if l.get("edge") is not None and not l.get("price_est") and l["edge"] >= 0.02]
    two = search(priced, 2, sims, games, max_per_game=1) if len(priced) >= 2 else None
    if not two and len(elig) >= 2:
        two = search(elig, 2, sims, games, max_per_game=1, min_games=2 if n_games >= 2 else None)
    if two:
        out["parlays"].append(package("Value 2", "The main pick: two legs from different games, each worth its price on its "
                                      "own where a real price is known. Two legs keep the bookmaker's margin small (about "
                                      "9% at standard prices against about 24% for six).", list(two), sims, games))
    if n_games >= 3:
        core = search(elig, 3, sims, games, max_per_game=1, min_games=3)
        if core:
            out["parlays"].append(package("Core 3", "Three legs from three different games: the strongest combination of "
                                          "chance and value without stacking one game.", list(core), sims, games))
    six = search(elig, min(6, len(elig)), sims, games, max_per_game=2 if n_games >= 3 else 3, min_games=min(4, n_games))
    if six:
        out["parlays"].append(package("The daily 6", "The long shot: six legs, at most two per game. It pays big but lands "
                                      "rarely, and the bookmaker's margin compounds over six legs, so it needs every leg to "
                                      "carry real value. Treat it as the optional extra, not the main bet.", list(six), sims, games))
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
                                      "Winamax's same-game builder already prices in that the legs move together, so the "
                                      "extra chance is mostly paid away: only worth it if Winamax's price beats the minimum odds.", list(best_sg[1]), sims, games))
    singles = sorted([l for l in cands if l.get("edge") is not None and l["edge"] > 0.02 and l["mind_flag"] != "against"
                      and not l.get("price_est") and P_MIN <= l["p"] <= P_MAX],
                     key=lambda l: -l["edge"])[:6]
    out["singles"] = [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in singles]
    return out, cands


def board(cands, n=60):
    """The strongest legs, plus the correlation lift for every same-game pair (for the custom ticket builder)."""
    good = sorted([l for l in cands if P_MIN <= l["p"] <= P_MAX and l["mind_flag"] != "against"],
                  key=lambda l: -(math.log(l["p"]) + edge_score(l)))[:n]
    lifts = {}
    for i, a in enumerate(good):
        for b in good[i + 1:]:
            if a["game"] != b["game"] or _conflict(a, b):
                continue
            pa, pb = a["_o"].mean(), b["_o"].mean()
            if pa > 0 and pb > 0:
                lift = (a["_o"] & b["_o"]).mean() / (pa * pb)
                if abs(lift - 1) >= 0.01:
                    lifts[f"{a['id']}|{b['id']}"] = round(float(lift), 3)
    legs = [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in good]
    return legs, lifts


def market_view(leg, odds, real_props=None):
    """What the market says now about this leg: no-margin chance of our side, our side's line and price."""
    from pipeline.oddsapi import norm_name
    k = leg["kind"]
    if k == "prop":
        rl = (real_props or {}).get((leg["game"], norm_name(leg.get("player_name")), leg["stat"]))
        if not rl:
            return None
        pm = novig(rl["over"], rl["under"])
        return {"line": float(rl["line"]), "p": round(pm if leg["side"] == "over" else 1 - pm, 4),
                "price": float(rl["over"] if leg["side"] == "over" else rl["under"])}
    if not odds:
        return None
    if k == "ml":
        pm = novig(odds.get("ml_home"), odds.get("ml_away"))
        if pm is None:
            return None
        mine = leg["team"] == leg["home"]
        return {"p": round(pm if mine else 1 - pm, 4), "price": odds.get("ml_home") if mine else odds.get("ml_away")}
    if k == "spread" and odds.get("spread_home") is not None:
        mine = leg["team"] == leg["home"]
        return {"line": odds["spread_home"] if mine else -odds["spread_home"]}
    if k == "total" and odds.get("total") is not None:
        return {"line": odds["total"]}
    return None


def clv(leg, open_v, close_v):
    """Closing-line value of a leg: positive = the market moved towards us after we published it.
    Chance points for winners/props at the same line; line points for handicaps, totals and moved prop lines."""
    if not open_v or not close_v:
        return None
    k = leg["kind"]
    if k in ("spread",):
        if open_v.get("line") is None or close_v.get("line") is None:
            return None
        return {"pts": round(open_v["line"] - close_v["line"], 2)}
    if k == "total":
        d = close_v["line"] - open_v["line"]
        return {"pts": round(d if leg["side"] == "over" else -d, 2)}
    if k == "prop" and open_v.get("line") != close_v.get("line"):
        d = close_v["line"] - open_v["line"]
        return {"pts": round(d if leg["side"] == "over" else -d, 2)}
    if open_v.get("p") is not None and close_v.get("p") is not None:
        return {"p": round(close_v["p"] - open_v["p"], 4)}
    return None


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


# ------------------------------------------------------------------ Winamax vs Pinnacle
VALUE_MIN_EDGE = 0.02     # Winamax price beats Pinnacle's fair price by 2%+
VALUE_MAX_DISAGREE = 0.04  # and the model does not rate the side 4+ points lower than Pinnacle does


def value_board(slate, bet_book="winamax_fr", sharp="pinnacle"):
    """Winners where the betting book pays more than the sharp book's fair price (margin removed).
    edge = Winamax odds x Pinnacle fair chance - 1: positive means a long-run profit at that price,
    whatever our model says. The model's view is shown next to it as a second opinion."""
    out = []
    for g, pay in slate:
        books = g.get("odds_books") or {}
        wb, sh = books.get(bet_book) or {}, books.get(sharp) or {}
        fair_h = novig(sh.get("ml_home"), sh.get("ml_away"))
        est = (pay or {}).get("est") or {}
        for side, team in (("home", g["home"]), ("away", g["away"])):
            price = wb.get(f"ml_{side}")
            fair = None if fair_h is None else (fair_h if side == "home" else 1 - fair_h)
            mod = est.get("win_home_model")
            mod = None if mod is None else (mod if side == "home" else 1 - mod)
            if not price:
                continue
            edge = None if fair is None else price * fair - 1
            row = {"game": str(g["game_id"]), "team": team, "opp": g["away"] if side == "home" else g["home"],
                   "side": side, "price": price, "pin_price": sh.get(f"ml_{side}"), "fair_p": None if fair is None else round(fair, 4),
                   "fair_odds": None if not fair else round(1 / fair, 3), "model_p": None if mod is None else round(mod, 4),
                   "edge": None if edge is None else round(edge, 4), "tip": g.get("date")}
            row["agree"] = None if (mod is None or fair is None) else bool(mod >= fair - VALUE_MAX_DISAGREE)
            row["value"] = bool(edge is not None and edge >= VALUE_MIN_EDGE and row["agree"] is not False)
            out.append(row)
    out.sort(key=lambda r: -(r["edge"] if r["edge"] is not None else -9))
    return out
