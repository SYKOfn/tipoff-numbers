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
import itertools
import math

import numpy as np

from .effects import norm_cdf

SIMS = 20000
MARKET_W = {"w": 0.5, "measured": False}  # model weight against a posted player line; set from the settled-lines test
P_MIN, P_MAX = 0.55, 0.86
PROP_MAX = 0.80          # alternate prop lines beyond this are priced too short to carry value
PROP_SIDES = ("over",)   # Winamax lists player markets as "over" only (X+ points etc.): no player unders
EDGE_W = 3.0             # how much a measured price edge is worth against chance when ranking tickets
EST_EDGE_W, EST_EDGE_CAP = 1.0, 0.12   # edges against an estimated line count less, and are capped
WINAMAX_PAYOUT = 0.5      # Winamax's combined odds pay about half the fair winnings (Pepe's experience, Nov 2026)
SAFETY = 1.05            # ask 5% more than fair odds before calling a leg worth taking
# player legs without a posted line: the projection blended with the season average, then a confidence per stat.
# Fitted on 2024-25 (115,000 Winamax-line legs, projections made before each game), confirmed on 2025-26: the old
# 50/50 blend with the projection-only confidence understated ticket legs by about 10 points; this setting by about 3.
PROP_CENTER_W = 0.7
# Legs without a real price: the chance starts from the season-average line (where books anchor) and moves only
# EST_K of the way (log-odds) towards the model. On 1,243 settled real lines (Nov 2026), legs picked because the
# projection beat the average were stated 67% and landed 55% (the book said 57%); with EST_K 0.3 the picked
# legs were stated 63% and landed 63%. The model's edge over a posted line is small: it must not be overstated.
EST_K = 0.3
# Ticket legs (Nov 2026 backtest, 2024-25 / 2025-26 / this season, ~20,000 player legs a season): a leg goes into a
# ticket only when every voice agrees it lands at least AGREE_MIN: the model's projection, the season average and
# the last 5 games (plus a real market line when there is one). Its chance is their consensus (mean log-odds).
# Picked that way, the best 2 legs of a night landed 75%/75%/79% (stated 74%); the old pick (biggest gap between
# the model and an estimated price) landed 49%/56%/43%. Ranking by apparent edge picks the model's mistakes
# (the winner's curse); without a real Winamax price an "edge" is not knowable, so tickets rank by honest chance.
AGREE_MIN, AGREE_MAX = 0.70, 0.86
# Long shots: the same agreement rule one step riskier (every voice at least LONG_MIN, consensus below AGREE_MIN).
# Backtest (2024-25, 2025-26), 3 long shots a night with no shared bet: 5 legs stated 14-16% and landed 15-23%
# (fair odds about x6-7); 6 legs stated ~10% and landed 8-17% (about x9-10).
LONG_MIN = 0.55
LONG_SIZES = (5, 7, 9)   # the night's three long shots (Pepe, Nov 2026): about x6, x14 and x30 fair odds
# Value 2 aims at about a coin flip for the whole ticket (fair odds about x2): two agreed legs near 71% each.
VALUE2_BAND = (0.70, 0.745)
# Singles: the night's 5 best values at the odds Winamax is expected to pay, positive value only.
# Winamax's own winner odds against Pinnacle's no-margin price (Nov 2026 log, 232 prices): Winamax pays 0.81 x the
# fair odds on long shots, 0.87 around 30-50%, 0.91 around 50-70% and 0.92-0.93 on favourites (a 12% overround).
WMX_FACTOR = ((0.15, 0.808), (0.40, 0.870), (0.60, 0.909), (0.78, 0.923), (0.90, 0.932))
# Player legs have no Winamax price in the feed (none has ever been observed), so their "Winamax price" below is an
# assumption (halfway between our chance and the season average's) and can't show real value: singles require a
# price actually seen at the book (wmx_real). If Winamax prices players as well as we do, such picks lose ~2-8%.
SINGLES_N = 5
SINGLE_P = (0.50, 0.90)


def wmx_odds(p_fair):
    """Odds Winamax is expected to pay for an outcome whose fair (no-margin) chance is p_fair."""
    xs, ys = zip(*WMX_FACTOR)
    return float(np.interp(p_fair, xs, ys)) / max(p_fair, 1e-3)


def singles_value(l, books):
    """(value, Winamax odds, real?) for a leg: our chance x Winamax's odds (real for winners, else expected) - 1."""
    w = (books or {}).get("winamax_fr") or {}
    k = l["kind"]
    if k == "ml":
        side = "home" if l.get("team") == l.get("home") else "away"
        if w.get(f"ml_{side}"):
            o = float(w[f"ml_{side}"])
            return l["p"] * o - 1, round(o, 2), True
        pf = l.get("market")
        if pf is None:
            return None, None, False
        o = wmx_odds(pf)
    elif k in ("spread", "total"):
        if not l.get("price") or not l.get("book"):
            return None, None, False
        o = wmx_odds(1 / (float(l["price"]) * 1.025))   # Pinnacle's price, its ~2.5% margin removed
    elif k == "prop" and l.get("voices"):
        o = wmx_odds((l["p"] + l["voices"][1]) / 2)
    else:
        return None, None, False
    return l["p"] * o - 1, round(o, 2), False
# The stated chance of an agreed leg (Nov 2026, fitted on 2022-25 legs, the weights were the same in every period
# taken alone, 2025-27 included): the projection counts far more than the season average and the last 5 games
# (0.645 / 0.14 / 0.094 on log-odds); heavy-minute players land more often (+0.018 per projected minute around 30,
# minutes kept within 20-38); "over 1.5 threes" and higher land less often than the count model says (-0.173).
# Held out on 2025-27 the stated chances matched what landed in every band (e.g. 77.7% stated, 77.2% landed).
# Tickets over 2022-27 against the plain consensus + minutes tilt: Core 3 landed 68% (67%), the daily 6 47% (43%),
# the 5-leg long shot 21% (19%). Safe / long is still decided by the voices agreeing (the consensus).
LEG_W = {"b0": 0.284, "model": 0.645, "avg": 0.14, "l5": 0.094, "min": 0.018, "tpm_high": -0.173}


def agreed_chance(voices, minutes, stat, line):
    """voices: over chances from [projection, season average, last 5 (, market)]."""
    lg = lambda v: logit(min(max(v, 1e-4), 1 - 1e-4))
    z = (LEG_W["b0"] + LEG_W["model"] * lg(voices[0]) + LEG_W["avg"] * lg(voices[1]) + LEG_W["l5"] * lg(voices[2])
         + LEG_W["min"] * (min(max(minutes or 30.0, 20.0), 38.0) - 30.0)
         + (LEG_W["tpm_high"] if stat == "tpm" and line >= 1.5 else 0.0))
    if len(voices) > 3:  # a real market line: half the weight
        z = 0.5 * z + 0.5 * lg(voices[3])
    return sigmoid(z)
EST_T = {"pts": 1.05, "reb": 1.1, "ast": 1.1, "tpm": 1.05, "pra": 1.1}
# markets Winamax lets you bet only on their own, never inside a combiné with other legs
SINGLE_ONLY = {"pra"}


def combinable(l):
    return not (l.get("kind") == "prop" and l.get("stat") in SINGLE_ONLY)


WINAMAX_PROP_MARGIN = 1.07  # (kept for reference: the favourite end of winamax_margin below)


def winamax_margin(p_fair):
    """Winamax's margin grows as the odds lengthen (favourite-longshot bias). Measured on its winner prices
    against Pinnacle's no-margin price (Nov 2026): about 7% on strong favourites, 8-9% on favourites and coin
    flips, 11% on underdogs, 20% on big underdogs. Used when Winamax's own price for a leg is not known."""
    return 1.07 if p_fair >= 0.75 else 1.085 if p_fair >= 0.55 else 1.095 if p_fair >= 0.45 else 1.12
BETA = {"pts": 1.0, "pra": 0.85, "ast": 0.6, "reb": 0.3, "tpm": 0.8}
STAT_NAME = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "threes", "pra": "pts+reb+ast"}
STD_PRICE = 1.91         # a standard -110 line, for spreads and totals without a price
# No totals legs when the model's total and the market's main total are this many points apart: a gap that big
# usually means the model is missing something the market knows (injuries, rest). Safety rule, Nov 2026.
TOTAL_GAP_MAX = 5.0


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


# ------------------------------------------------------------------ calibration of player props
def fit_prop_calibration(plogs, byg, disp, dsp_log=None):
    """Temperature per stat: p_cal = sigmoid(T * logit(p)), fitted by log loss on past player-games.
    dsp_log: each player's own spread going into each game (the same spread the legs are priced with)."""
    from .players import sd_for, over_prob, player_disp
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
            dp = player_disp({"dsp": (dsp_log or {}).get(key) or {}}, disp) if dsp_log is not None else disp
            sd = sd_for(st, proj, dp)
            for k in (-1.5, -0.75, 0.0, 0.75, 1.5):
                L = math.floor(proj + k * sd) + 0.5
                if L <= 0:
                    continue
                p = over_prob(st, L, proj, dp)
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
    t_own = est.get("total_model", t)   # the model's own total, before the market blend: used for the gap rule
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
    if odds and odds.get("total") and abs(t_own - odds["total"]) <= TOTAL_GAP_MAX:
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


def prop_legs(game, players, calib, avg, disp_all, real=None):
    """Player props at the line a bookmaker would most likely post: books anchor main lines on the player's
    season average, so that line is estimated as his average rounded to .5. A leg is a candidate when the
    projection (matchup, minutes, teammates out, psychology) disagrees with that line."""
    from .players import LABEL, sd_for, over_prob, ladder, near_lines, mu_for_over
    legs = []
    for side in ("home", "away"):
        team = game[side]
        for pl in players.get(side, []):
            dp = pl.get("disp") or disp_all
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
                if rl:  # a real posted line: carried to Winamax's own lines around it (the only ones that can be bet)
                    L0 = float(rl["line"])
                    t = (calib.get(st) or {}).get("t", 0.75)
                    pm_over0 = novig(rl["over"], rl["under"])
                    mu_mkt = mu_for_over(st, L0, pm_over0, dp)  # the book's view, as a mean
                    on_ladder = L0 in ladder(st)
                    for L in ([L0] if on_ladder else near_lines(st, L0, 1, 1)):
                        sd = sd_for(st, proj, dp)
                        po = over_prob(st, L, proj, dp)
                        mk = pm_over0 if L == L0 else over_prob(st, L, mu_mkt, dp)
                        pc = sigmoid(MARKET_W["w"] * t * logit(po) + (1 - MARKET_W["w"]) * logit(mk))
                        if not (0.5 <= pc <= PROP_MAX):
                            continue
                        exact = L == L0
                        price = float(rl["over"]) if exact else round(1 / (min(mk, 0.97) * winamax_margin(mk)), 2)
                        legs.append(_leg(game, "prop", f"{pl['name']} over {L:.1f} {STAT_NAME[st]}", po, pc, price,
                                         team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side="over",
                                         proj=proj, avg=None if av is None or av != av else round(av, 1), price_est=not exact,
                                         book=rl["book"], market=round(mk, 3),
                                         dist={"mu": round(proj, 2), "sd": round(sd, 2), "d": round(dp.get(st, 1.5), 3), "alone": t, "model": t},
                                         note=(f"projection {proj:.1f}; real {rl['book']} line, blended {round(MARKET_W['w'] * 100)}/{round(100 - MARKET_W['w'] * 100)} with its no-margin price"
                                               if exact else f"projection {proj:.1f}; Winamax line {L:.1f}, market chance carried from the {rl['book']} line {L0:.1f}; price estimated")
                                              + (" (weight measured on settled lines)" if MARKET_W.get("measured") else ""),
                                         mind=mind, spots=[x["label"] for x in spots],
                                         sim=("prop", side, pl["id"], st, "over", L)))
                # (no `continue` here: agreement legs below go on the other ladder lines)
                l5 = a.get("l5_" + st)
                if (st != "pra" and proj is not None and av is not None and av == av and l5 is not None
                        and a.get("gp", 0) >= 5):
                    done = {l["line"] for l in legs if l.get("player") == pl["id"] and l.get("stat") == st}
                    mk_at = None
                    if rl:
                        mu_m = mu_for_over(st, float(rl["line"]), novig(rl["over"], rl["under"]), dp)
                        mk_at = lambda L, mu_m=mu_m: over_prob(st, L, mu_m, dp)
                    for L in ladder(st):
                        if L in done:
                            continue
                        voices = [over_prob(st, L, proj, dp), over_prob(st, L, av, dp), over_prob(st, L, l5, dp)]
                        if mk_at:
                            voices.append(mk_at(L))
                        if min(voices) < LONG_MIN:
                            continue
                        pc = sigmoid(sum(logit(min(max(v, 1e-4), 1 - 1e-4)) for v in voices) / len(voices))
                        level = "safe" if min(voices) >= AGREE_MIN and AGREE_MIN <= pc <= AGREE_MAX else \
                            "long" if pc < AGREE_MIN else None
                        if not level:
                            continue
                        pa_over = min(max(voices[1], 0.03), 0.97)
                        price = round(1 / (pa_over * winamax_margin(pa_over)), 2)
                        cons = pc  # the consensus decides safe / long; the stated chance is agreed_chance (measured weights)
                        pc = agreed_chance(voices, pl.get("min"), st, L)
                        legs.append(_leg(game, "prop", f"{pl['name']} over {L:.1f} {STAT_NAME[st]}", voices[0], pc, price,
                                         consensus=round(cons, 4),
                                         dist={"mu": round(proj, 2), "sd": round(sd_for(st, proj, dp), 2), "d": round(dp.get(st, 1.5), 3), "alone": 1.0, "model": 1.0},
                                         team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side="over",
                                         proj=proj, avg=round(av, 1), last5=round(l5, 1), price_est=True, anchor=round(pa_over, 4), agree=level,
                                         voices=[round(v, 3) for v in voices],
                                         note=(f"all agree: projection {proj:.1f}, season average {av:.1f}, last 5 games {l5:.1f}"
                                               + (f", {rl['book']} line {float(rl['line']):.1f}" if rl else "")
                                               + f" (each at least {round((AGREE_MIN if level == 'safe' else LONG_MIN) * 100)}% over {L:.1f}); Winamax line, price estimated"),
                                         mind=mind, spots=[x["label"] for x in spots],
                                         sim=("prop", side, pl["id"], st, "over", L)))
                if rl:
                    continue
                if proj is None or av is None or av != av or av < (2.0 if st in ("tpm", "ast", "reb") else 3):
                    continue  # one-a-game stats: books post 0.5 or 1.5 with very uneven prices, too unreliable to estimate
                # the projection blended with the season average (the line's anchor), PROP_CENTER_W measured
                center = PROP_CENTER_W * proj + (1 - PROP_CENTER_W) * av
                sd = sd_for(st, center, dp)
                t = EST_T.get(st, 1.0)
                for L in near_lines(st, center, 2, 1):  # Winamax's own lines around the player
                    if any(l.get("player") == pl["id"] and l.get("stat") == st and l.get("line") == L for l in legs):
                        continue
                    po = over_prob(st, L, center, dp)
                    # the price a book would ask: fair on the season-average anchor, plus its margin
                    pa_over = min(max(over_prob(st, L, av, dp), 0.03), 0.97)
                    pc = sigmoid(logit(pa_over) + EST_K * (t * logit(po) - logit(pa_over)))
                    price = round(1 / (pa_over * winamax_margin(pa_over)), 2)
                    if 0.5 <= pc <= PROP_MAX and price >= 1.3:
                        legs.append(_leg(game, "prop", f"{pl['name']} over {L:.1f} {STAT_NAME[st]}", po, pc, price,
                                         dist={"mu": round(center, 2), "sd": round(sd, 2), "d": round(dp.get(st, 1.5), 3), "alone": t, "model": t},
                                         team=team, player=pl["id"], player_name=pl["name"], stat=st, line=L, side="over",
                                         proj=proj, avg=round(av, 1), price_est=True, anchor=round(pa_over, 4),
                                         note=f"projection {proj:.1f} vs season average {av:.1f} {LABEL.get(st, st).lower()} (blended {round(PROP_CENTER_W * 100)}/{round(100 - PROP_CENTER_W * 100)}); Winamax line, price estimated",
                                         mind=mind, spots=[x["label"] for x in spots],
                                         sim=("prop", side, pl["id"], st, "over", L)))
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
    if odds and odds.get("total") is not None and abs(est.get("total_model", t) - odds["total"]) > TOTAL_GAP_MAX:
        offers = [o for o in offers if o["kind"] not in ("total", "team_total")]
    elif odds and odds.get("total") is not None and odds.get("over") and odds.get("under"):
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
        disp_p = pl.get("disp") or disp
        sd = sd_for(st, proj, disp_p)
        tt = (calib.get(st) or {}).get("t", 0.75)
        from .players import over_prob
        po = sigmoid(tt * logit(min(max(over_prob(st, L, proj, disp_p), 1e-4), 1 - 1e-4)))
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
                dist={"mu": round(proj, 2), "sd": round(sd, 2), "d": round(disp_p.get(st, 1.5), 3), "alone": tt, "model": tt})
    return legs


# ------------------------------------------------------------------ correlated simulation per game
def simulate(game, est, players, disp, rng):
    """The game simulated SIMS times (model/sim.py: minutes, blowouts, overtime, teammates sharing points)."""
    from . import sim
    return sim.simulate(game, est, players, disp, rng, sims=SIMS)


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


MAX_TICKETS_PER_BET = 1   # every bet goes into one ticket only: no player and no team result is repeated across the day's tickets (Pepe, Nov 2026)
MAX_PER_TEAM = 2          # at most two legs on the same team within a ticket
MAX_PER_STAT = 2          # at most two player legs on the same stat within a ticket (no all-rebounds tickets)


def exposure(l):
    """What a leg really bets on: a player (any of his stats) or one side of one game."""
    if l.get("kind") == "prop":
        return ("player", str(l.get("player")))
    return ("game", str(l.get("game")), l.get("team") or l.get("side") or l.get("kind"))


def search(cands, k, sims, games, max_per_game=2, min_games=None, beam=60, max_per_team=MAX_PER_TEAM, others=()):
    """others: exposure sets of the day's tickets so far; a new ticket shares at most one bet with each."""
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
                if c.get("team") and sum(1 for l in legs if l.get("team") == c["team"]) >= max_per_team:
                    continue
                if c.get("kind") == "prop" and sum(1 for l in legs if l.get("kind") == "prop" and l.get("stat") == c.get("stat")) >= MAX_PER_STAT:
                    continue
                if others:
                    mine = {exposure(l) for l in legs} | {exposure(c)}
                    if any(len(mine & o) > 1 for o in others):
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


GAME_LEGS, GAME_POOL, GAME_P = 5, 24, 0.60


def scenarios(legs, sim, p_cal):
    """How the ticket fares in different versions of the game: share of simulated games where all legs land,
    scaled to the ticket's calibrated chance. Close = final margin within 6, blowout = 15 or more."""
    mask = np.ones(len(sim["m"]), bool)
    for l in legs:
        mask &= l["_o"]
    raw = mask.mean()
    k = p_cal / raw if raw > 0 else 1.0
    am = np.abs(sim["m"])
    out = {}
    for name, sel in (("close", am <= 6), ("normal", (am > 6) & (am < 15)), ("blowout", am >= 15),
                      ("home_wins", sim["m"] > 0), ("away_wins", sim["m"] < 0), ("overtime", sim["ot"])):
        if sel.mean() >= 0.01:
            out[name] = {"share": round(float(sel.mean()), 3), "lands": round(min(1.0, float(mask[sel].mean()) * k), 3)}
    return out


def package(name, why, legs, sims, games):
    pj, pi = joint(legs, sims, games)
    fair = 1 / pj if pj > 0 else None
    return {"name": name, "why": why, "legs": [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in legs],
            "p": round(pj, 4), "p_independent": round(pi, 4), "lift": round(pj / pi, 3) if pi else 1.0,
            "fair": round(fair, 2) if fair else None, "min_odds": round(fair * SAFETY, 2) if fair else None,
            # what Winamax usually pays for a combiné like this: about half the fair winnings (Pepe, Nov 2026)
            "winamax_est": round(1 + WINAMAX_PAYOUT * (fair - 1), 2) if fair else None,
            "n_legs": len(legs), "games": len({l["game"] for l in legs})}


def build(slate, disp, calib, avg=None, seed=5, real_props=None, book_only=None):
    """slate: list of (game dict, payload). Returns the day's parlays and the full leg board."""
    rng = np.random.default_rng(seed)
    games, sims, cands, books_of = {}, {}, [], {}
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
        books_of[game["id"]] = g.get("odds_books") or {}
        sims[game["id"]] = simulate(game, est, players, disp, rng)
        for l in legs:
            l["_o"] = outcome(sims[game["id"]], l, game)
            l["matchup"] = f"{game['away']} at {game['home']}"
            l["home"] = game["home"]
            l["tip"] = game["tip"]
            l["mind_flag"] = "against" if (l.get("mind") or 0) <= -0.3 else "with" if (l.get("mind") or 0) >= 0.3 else "neutral"
        cands += legs
    # a leg is eligible if its chance is in range, the price (when known) is worth taking, and the mind is not against it
    # an estimated price is a guess, so its "edge" is too: those legs only need the model to lean over the
    # season-average line; whether Winamax's real odds are worth it is decided on the ticket (place / skip box)
    worth = lambda l: (l["p"] >= l["anchor"] + 0.01) if l.get("price_est") and l.get("anchor") is not None else (l["edge"] is None or l["edge"] >= 0)
    elig = [l for l in cands if combinable(l) and P_MIN <= l["p"] <= P_MAX and worth(l) and l["mind_flag"] != "against"
            and (not book_only or (l.get("price") or 0) >= 1.15)]
    n_games = len(games)
    out = {"games": n_games, "candidates": len(cands), "eligible": len(elig), "parlays": [], "book": book_only,
           "not_on_book": out_skip}
    if n_games == 0:
        return out, cands
    # Main picks are short: the bookmaker's margin multiplies with every leg, so two or three legs from
    # different games (where Winamax simply multiplies the odds) keep the most of any edge.
    # spread the day's risk: a player or a team result goes into at most MAX_TICKETS_PER_BET tickets, so one
    # upset or one cold night cannot sink every ticket at once
    from collections import Counter
    uses = Counter()
    free = lambda pool: [l for l in pool if uses[exposure(l)] < MAX_TICKETS_PER_BET]

    tickets = []  # exposure sets of the tickets built so far

    def take(legs):
        for l in legs:
            uses[exposure(l)] += 1
        tickets.append({exposure(l) for l in legs})
        return list(legs)

    # Tickets (Nov 2026 rework, see AGREE_MIN): legs whose every voice agrees, ranked by their honest chance;
    # the best legs go into the shortest ticket, and every bet goes into one ticket only.
    # agreed player legs are safe or long by their consensus; the minutes tilt only moves the stated chance
    in_pool = lambda l, lvl, lo, hi: (l.get("agree") == lvl) if l.get("agree") else (lo <= l["p"] <= hi and (l["kind"] != "prop" or book_only))
    pool = [l for l in cands if combinable(l) and l["mind_flag"] != "against" and in_pool(l, "safe", AGREE_MIN, AGREE_MAX)]
    long_pool = [l for l in cands if combinable(l) and l["mind_flag"] != "against" and in_pool(l, "long", LONG_MIN, AGREE_MIN - 1e-9)]
    v2_extra = [l for l in long_pool if l.get("agree") and l["p"] >= AGREE_MIN]   # agreed legs near 71%: Value 2 only
    long_pool = [l for l in long_pool if l["p"] < AGREE_MIN]  # long shots keep their odds (about x6, x14, x30)
    out["eligible"] = len(pool) + len(long_pool)

    def pick(k, per_game, src=None, band=None):
        chosen = []
        cand = free(pool if src is None else src)
        if band:
            cand = [l for l in cand if band[0] <= l["p"] <= band[1]]
        for l in sorted(cand, key=lambda l: (-l["p"], -(l.get("edge") or 0))):
            if len(chosen) == k:
                break
            if any(_conflict(l, c) or exposure(l) == exposure(c) for c in chosen):
                continue
            if sum(c["game"] == l["game"] for c in chosen) >= per_game:
                continue
            if l.get("team") and sum(c.get("team") == l["team"] for c in chosen) >= MAX_PER_TEAM:
                continue
            if l.get("stat") and sum(c.get("stat") == l["stat"] for c in chosen) >= max(MAX_PER_STAT, k // 2):
                continue
            chosen.append(l)
        return chosen if len(chosen) == k else None

    two = None
    for hi in (VALUE2_BAND[1], 0.77, 0.80, 1.0):  # no pair near 71%: the closest above it rather than no main pick
        two = pick(2, 1 if n_games >= 2 else 2, src=pool + v2_extra, band=(VALUE2_BAND[0], hi))
        if two:
            break
    if two:
        out["parlays"].append(package("Value 2", "The main pick: about a coin flip for double the money. Two legs from two "
                                      "different games, each around 70% and backed by the projection, the season average "
                                      "and the last 5 games together. Two legs keep Winamax's margin small.", take(two), sims, games))
    core = pick(3, 1) if n_games >= 3 else None
    if core:
        out["parlays"].append(package("Core 3", "The next three most likely legs, three different games, none of them "
                                      "used in another ticket.", take(core), sims, games))
    six = pick(6, 1 if n_games >= 6 else 2) if n_games >= 3 else None
    if six:
        out["parlays"].append(package("The daily 6", "The long shot: six more agreed legs, none used in another ticket. "
                                      "It pays the most and lands the least; the bookmaker's margin compounds over six legs.",
                                      take(six), sims, games))
    rare = {5: "about 1 night in 6", 7: "about 1 night in 14", 9: "about 1 night in 30"}
    for i, k in enumerate(LONG_SIZES):
        ls = (pick(k, 1 if n_games >= k else 2, long_pool) or pick(k, 1 if n_games >= k else 2, long_pool + v2_extra)) if n_games >= 3 else None
        if not ls:
            continue
        out["parlays"].append(package(f"Long shot {i + 1}", f"A long shot of {k} legs, each landing more often than not with the "
                                      f"projection, the season average and the last 5 games all agreeing. It lands {rare.get(k, 'rarely')} "
                                      f"and pays far more; none of its bets is in another ticket.", take(ls), sims, games))
    order = {"Value 2": 0, "Core 3": 1, "The daily 6": 2, "Long shot 1": 3, "Long shot 2": 4, "Long shot 3": 5, "Same-game 3": 9}
    out["parlays"].sort(key=lambda pr: order.get(pr["name"], 9))
    # (the old "value singles", ranked by the gap to a posted price, were never backtested and are dropped:
    # ranking by apparent edge picks the model's mistakes, see AGREE_MIN)
    singles = []
    # Singles (Nov 2026, Pepe): every leg (winners, handicaps, totals, player legs) ranked by its value at the odds
    # Winamax is expected to pay: chance x Winamax odds - 1. See WMX_FACTOR and singles_value().
    seen_p, per_g, team_g = set(), Counter(), set()
    for l in cands:
        l["ev"], l["wmx"], l["wmx_real"] = singles_value(l, books_of.get(l["game"]))
    # only a price actually seen at the book can show value; an assumed price would just echo our own chance
    for l in sorted([l for l in cands if l["ev"] is not None and l["ev"] > 0 and l["wmx_real"] and SINGLE_P[0] <= l["p"] <= SINGLE_P[1]
                     and l["mind_flag"] != "against" and (l["kind"] != "prop" or l.get("agree"))], key=lambda l: -l["ev"]):
        if len(singles) >= SINGLES_N:
            break
        if (l.get("player") and l["player"] in seen_p) or per_g[l["game"]] >= 2 or (l["kind"] != "prop" and l["game"] in team_g):
            continue
        singles.append(l)
        if l.get("player"):
            seen_p.add(l["player"])
        else:
            team_g.add(l["game"])
        per_g[l["game"]] += 1
    out["singles"] = [{k: v for k, v in l.items() if not k.startswith("_") and k != "sim"} for l in singles]
    # One ticket per game (Pepe, Nov 2026): the game's 5 legs most likely to land together, priced on the game's
    # 20,000 simulated versions (minutes, blowouts, overtime, teammates sharing points), so legs that win and lose
    # together are counted as such. They may repeat bets from the singles and the other tickets (Pepe, Nov 2026).
    out["game_tickets"] = []
    for gid, game in games.items():
        def best_ticket(pool_g):
            # beam search: grow the ticket one leg at a time, keeping the 40 most likely partial tickets
            states = [((), 1.0)]
            for _ in range(GAME_LEGS):
                nxt = {}
                for legs, _p in states:
                    for c in pool_g:
                        if any(c is l or _conflict(c, l) or exposure(c) == exposure(l) for l in legs):
                            continue
                        new = tuple(sorted(legs + (c,), key=lambda x: x["id"]))
                        key = tuple(x["id"] for x in new)
                        if key not in nxt:
                            nxt[key] = (new, joint(new, sims, games)[0])
                states = sorted(nxt.values(), key=lambda s_: -s_[1])[:40]
                if not states:
                    return None
            return (states[0][1], states[0][0]) if len(states[0][0]) == GAME_LEGS else None
        mine = [l for l in cands if l["game"] == gid and combinable(l) and l["mind_flag"] != "against"]
        strict = sorted([l for l in mine if GAME_P <= l["p"] <= AGREE_MAX and (l["kind"] != "prop" or l.get("agree"))],
                        key=lambda l: -l["p"])[:GAME_POOL]
        best = best_ticket(strict)
        if not best:  # not enough agreed legs: every rated leg of the game from 50% up, so each game gets its ticket
            best = best_ticket(sorted([l for l in mine if 0.50 <= l["p"] <= 0.92], key=lambda l: -l["p"])[:GAME_POOL])
        if not best:
            continue
        pk = package(f"{game['away']} at {game['home']}", "This game's five legs most likely to land together, "
                     "priced on 20,000 simulated versions of the game.", list(best[1]), sims, games)
        pk["game"] = gid
        pk["scenarios"] = scenarios(best[1], sims[gid], pk["p"])
        out["game_tickets"].append(pk)
    out["game_tickets"].sort(key=lambda t: -t["p"])
    return out, cands


def board(cands, n=60):
    """The strongest legs, plus the correlation lift for every same-game pair (for the custom ticket builder)."""
    good = sorted([l for l in cands if combinable(l) and P_MIN <= l["p"] <= P_MAX and l["mind_flag"] != "against"],
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
        return "void" if t == leg["line"] else "hit" if (t > leg["line"]) == (leg["side"] == "over") else "miss"
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


# ---------------------------------------------------------------- after the lock: late news on locked legs
LATE_DROP = 0.07   # flag a locked leg when the model's chance for it falls by this much (absolute)


def _leg_key(l):
    return (str(l.get("game")), l.get("kind"), l.get("team") or l.get("side"), str(l.get("player") or ""), l.get("stat"))


def chance_now(l, cur):
    """Model chance today for locked leg l, at its own locked line, from the matching fresh leg cur."""
    from .players import over_prob
    d = cur.get("dist") or {}
    k = l["kind"]
    if k == "ml":
        return cur.get("p_model")
    if not d.get("sd") or d.get("mu") is None:
        return None
    if k == "spread":
        return norm_cdf((d["mu"] + float(l["line"])) / d["sd"])
    if k == "total":
        p = norm_cdf((d["mu"] - float(l["line"])) / d["sd"])
        return p if l.get("side", "over") == "over" else 1 - p
    if k == "prop":
        return over_prob(l["stat"], float(l["line"]), d["mu"], d.get("d", 1.5))
    return None


def late_check(parlays, cands, players_now, started):
    """Flag locked legs hit by news after the lock and suggest a replacement leg; the tickets themselves stay.
    players_now: {player id: current player block}; started: game ids already under way (left alone)."""
    fresh = {}
    for c in cands:
        fresh.setdefault(_leg_key(c), c)
    used = {l["id"] for pr in parlays for l in pr["legs"]}
    for pr in parlays:
        games_in = {l["game"] for l in pr["legs"]}
        same_game = pr.get("games") == 1
        for l in pr["legs"]:
            for k_ in ("alert", "swap", "p_now"):
                l.pop(k_, None)
            if l["game"] in started:
                continue
            reason = None
            x = players_now.get(str(l.get("player") or "")) if l.get("kind") == "prop" else None
            cur = fresh.get(_leg_key(l))
            if x is not None and (x.get("out") or x.get("status")):
                reason = f"{x.get('status') or 'Out'} since the picks were locked: if he does not play, Winamax voids this leg"
            elif l.get("kind") == "prop" and cur is None and x is not None and (
                    x.get("lineup") == "not in the starting five" or (x.get("min") or 0) < 24 or (x.get("p_play") or 1.0) < 0.6):
                reason = ("not in the starting five tonight" if x.get("lineup") == "not in the starting five"
                          else "expected minutes have dropped since the lock") + ": his line is now less likely to be reached"
            elif cur is not None:
                p_now = chance_now(l, cur)
                if p_now is not None:
                    l["p_now"] = round(p_now, 3)
                    if l.get("p_model") is not None and l["p_model"] - p_now >= LATE_DROP:
                        reason = (f"late news has made this leg less likely: the model now gives it {round(100 * p_now)}% "
                                  f"instead of {round(100 * l['p_model'])}% at the lock")
            if not reason:
                continue
            l["alert"] = reason
            ref_price = l.get("price") or l.get("min_odds") or 1.5
            pool = [c for c in cands if combinable(c) and c["id"] not in used and c["game"] not in started
                    and ((c["game"] == l["game"]) if same_game else (c["game"] not in games_in or c["game"] == l["game"]))
                    and _leg_key(c) != _leg_key(l)
                    and 0.8 * ref_price <= (c.get("price") or c.get("min_odds") or 0) <= 1.25 * ref_price
                    and c.get("p", 0) >= min(l.get("p", 0), 0.9) - 0.02]
            pool = [c for c in pool if not (c.get("kind") == "prop" and (players_now.get(str(c.get("player"))) or {}).get("status"))]
            if pool:
                b = max(pool, key=lambda c: (c.get("edge") or 0) + c.get("p", 0))
                used.add(b["id"])
                l["swap"] = {k_: b.get(k_) for k_ in ("id", "desc", "matchup", "p", "price", "min_odds", "game", "tip")}
    return parlays
