"""Replay the per-game tickets over a past season with the live build rules, then settle them.

Every input is as of before the game: player projections and spreads from player_engine.walk (out-of-sample),
season-to-date and last-5 averages from earlier games only. Differences from live: no real posted prop lines (every
line is the season average, as live does when none is posted), no market odds for winner/handicap/total legs, no
psychology spots on players, players who did not play are left out (live, their legs would be void), and the game
estimate's factor sizes are fitted on the whole history.

    python -m backtest.tickets [SEASON] [FIRST_DAY LAST_DAY]
"""
import json
import math
import sys
import os
from collections import defaultdict

import numpy as np

from model import engine, parlay
from model import player_engine as PE
from model import players as P
from pipeline.store import load_games, load_players, load_stints


def rule(name, ests, plogs):
    """Candidate ticket rules, tested here only: each drops some player legs before the ticket is picked."""
    def keep(l, game):
        if l.get("kind") != "prop":
            return True
        m = ests.get(game["id"], 0.0)
        dog = game["home"] if m < 0 else game["away"]
        pmin = (plogs.get((game["id"], str(l.get("player")))) or {}).get("min") or 0
        if "dog8" in name and abs(m) >= 8 and l.get("team") == dog:
            return False
        if "min35" in name and pmin >= 35:
            return False
        return True
    return None if name in ("base", "nofix", "refit") else keep


def main(season, d0=None, d1=None, rules=("base",)):
    import os
    PE.MIN_CAL = os.environ.get("MIN_CAL") == "1"  # replay with the minutes calibration on
    if os.environ.get("ROT_PBP"):  # replay with the play-by-play rotation inputs on (1) or off (0)
        P.ROT_PBP = os.environ["ROT_PBP"] == "1"
    if os.environ.get("B2B_KEY"):  # replay with the key-player back-to-back input on (1) or off (0)
        P.B2B_KEY = os.environ["B2B_KEY"] == "1"
    for k_ in ("AFTER_BLOW", "LAST_FORM"):  # replay with these inputs on (1) or off (0)
        if os.environ.get(k_):
            setattr(P, k_, os.environ[k_] == "1")
    # LOCK_STATUS=1: leak-free replay. Who is in a projection (player_engine.walk) and in the game model's lineup and
    # "missing" inputs comes from the NBA's injury report at the 16:00 ET lock (data/history/injury_status.csv.gz,
    # backtest/injury_reports.py) instead of who actually got minutes; Out/Doubtful are out, the others carry the
    # live p_play and injury status. LOCK_STATUS=0 computes the same but only records it in the leg details.
    if os.environ.get("MIN_SCALE_HI"):  # most the pre-game list's minutes are scaled up (live 1.15)
        PE.SCALE_HI = float(os.environ["MIN_SCALE_HI"])
    lock_mode = os.environ.get("LOCK_STATUS")
    lock = None
    if lock_mode:
        from backtest import injury_reports
        st_, days_ = injury_reports.load()
        lock = {"st": st_, "days": days_, "season": season, "play": PE.LOCK_PLAY}
        PE.LOCK = (st_, days_)
        print(f"lock statuses ({'used' if lock_mode == '1' else 'recorded only'}): {len(days_)} report days", flush=True)
    games, players = load_games(), load_players()
    c = engine.build_context(games, players, [], {"half_life": 90, "lam": 3.0, "carry": 0.6, "lam_effects": 40.0},
                             stints=load_stints(), lock=lock)
    pt, pe, pdisp, plogs, ptrack, byg = PE.walk(c, players, {}, season)
    lrows = getattr(pt, "lock_rows", {})
    lfeat_lock, plock = {}, {}
    for (gid_, side_), lst_ in lrows.items():
        for r_ in lst_:
            plock[(gid_, r_["id"])] = r_["proj"]
        if side_ == "home" and (gid_, "away") in lrows:
            em_ = lambda lst: [(r_["id"], r_["proj"]["min"] * r_["p_play"]) for r_ in lst]
            lfeat_lock[gid_] = engine.lock_lfeat(c, gid_, em_(lst_), em_(lrows[(gid_, "away")]))
    use_lock = lock_mode == "1"
    if lrows:
        print(f"lock projections: {len(lrows) // 2} games, lineup features {sum(v is not None for v in lfeat_lock.values())}", flush=True)
    day_of = {gid: g["day"] for gid, g in c.meta.items()}
    # REAL_PROPS=close|open: give the ticket builder real posted player lines (ESPN's book, backtest/espn_props.py)
    # the way the live site gets them from The Odds API, with the prop calibration fitted monthly on earlier games
    real_mode = os.environ.get("REAL_PROPS")
    real = None
    if real_mode:
        from backtest import espn_props
        real = espn_props.load(season, real_mode)
        print(f"real prop lines ({real_mode}): {len(real)}", flush=True)
    if os.environ.get("MARKET_W"):
        parlay.MARKET_W["w"] = float(os.environ["MARKET_W"])
    if os.environ.get("ML_MKT_W"):  # market weight when a winner leg meets the book's price (live 0.5)
        parlay.ML_MKT_W = float(os.environ["ML_MKT_W"])
    # REPLAY_ML=1: price winner legs like live. The game's win chance becomes the live model+Pinnacle blend
    # (pipeline/run.py, BLEND_W) and team_legs gets the book's moneyline (Winamax-like prices around the fair
    # chance, parlay.wmx_odds), so the leg is blended again and its edge filter applies. Fair chance: Pinnacle's
    # pre-game price (data/odds/pinnacle_history.csv, 2025-26 on), else ESPN's partner book close
    # (data/odds/espn_ml_{season}.csv, backtest/espn_props.py fetch_ml). REPLAY_ML_SRC=espn|pinnacle forces one.
    ml_fair = {}
    if os.environ.get("REPLAY_ML") == "1":
        import csv as _csv
        from backtest.run import load_pinnacle
        from pipeline.run import BLEND_W
        src = os.environ.get("REPLAY_ML_SRC", "auto")
        ef = os.path.join("data", "odds", f"espn_ml_{season}.csv")
        if src in ("auto", "espn") and os.path.exists(ef):
            for r in _csv.DictReader(open(ef)):
                q = parlay.novig(r["ml_home"], r["ml_away"])
                if q:
                    ml_fair[r["game_id"]] = q
        if src in ("auto", "pinnacle"):
            ml_fair.update(load_pinnacle())
        print(f"moneyline prices on ({src}): {len(ml_fair)} games, leg market weight {parlay.ML_MKT_W}", flush=True)
    calib_cache = {}
    # ALT_BLEND="a,b,c": blend each player leg's chance with the book's milestone price at the same line
    # (rows from the research script alt.py): p' = sigmoid(a logit p + b logit implied + c)
    if os.environ.get("ALT_BLEND"):
        import pickle, math
        wa, wb, wc = map(float, os.environ["ALT_BLEND"].split(","))
        AR = pickle.load(open(os.environ.get("ALT_ROWS", "/tmp/alt_rows.pkl"), "rb"))
        imp = {(r.gid, r.pid, r.stat, float(r.line)): r.imp for r in AR.itertuples()}
        lgt = lambda q: math.log(min(max(q, 1e-4), 1 - 1e-4) / (1 - min(max(q, 1e-4), 1 - 1e-4)))
        def adjust(l):
            if l.get("kind") != "prop":
                return
            i = imp.get((str(l["game"]), str(l.get("player")), l.get("stat"), float(l.get("line") or -1)))
            if i:
                b = 1 / (1 + math.exp(-(wa * lgt(l["p"]) + wb * lgt(i) + wc)))
                mode = os.environ.get("ALT_MODE", "live")
                if mode == "live":             # exactly the live code: lower only, stated at the blend (parlay.alt_lower)
                    parlay.alt_lower(l, i)
                elif mode == "blend":
                    l["p"] = b
                elif mode == "lower":          # only ever lower a leg, never lift it out of the builder's window
                    l["p"] = min(l["p"], b)
                elif mode.startswith("veto"):  # lower only when the book is clearly less sure: veto0.06
                    if b < l["p"] - float(mode[4:] or 0.06):
                        l["p"] = b
        parlay.LEG_ADJUST = adjust
        print(f"milestone blend on: {len(imp)} book prices", flush=True)

    def calib_for(day):
        if not real_mode:
            return {}
        m = day[:7]
        if m not in calib_cache:
            past = {k: v for k, v in plogs.items() if day_of.get(k[0], "9") < m + "-01"}
            calib_cache[m] = parlay.fit_prop_calibration(past, byg, pdisp, pt.dsp_log) if past else {}
        return calib_cache[m]
    pl = players.copy()
    pl["gid"] = pl["game_id"].astype(str)
    pl["day"] = pl["gid"].map(day_of)
    pl["season"] = pl["gid"].map({gid: int(g["season"]) for gid, g in c.meta.items()})
    pl = pl[(pl["season"] == season) & (pl["min"].fillna(0) > 0)].copy()
    pl["pra"] = pl["pts"] + pl["reb"] + pl["ast"]
    pl = pl.sort_values("day")
    days = sorted(d for gid, d in day_of.items() if int(c.meta[gid]["season"]) == season and int(c.meta[gid]["stype"]) == 2
                  and (d0 is None or d >= d0) and (d1 is None or d <= d1))
    tickets, ests = {r: [] for r in rules}, {}
    ladder_days = []
    for day in sorted(set(days)):
        before = pl[pl["day"] < day]
        hist = {pid: d_ for pid, d_ in before.groupby(before["player_id"].astype(str))}
        ests_t = {}
        avg = {}
        for pid, d_ in before.groupby(before["player_id"].astype(str)):
            l5 = d_.tail(5)
            avg[pid] = {"gp": len(d_), **{k: float(d_[k].mean()) for k in ("pts", "reb", "ast", "tpm", "pra")},
                        **{"l5_" + k: float(l5[k].mean()) for k in ("pts", "reb", "ast", "tpm", "pra")}}
        slate = []
        for gid, g in c.meta.items():
            if g["day"] != day or gid not in c.base or gid not in byg:
                continue
            on_l = use_lock and (gid, "home") in lrows
            if on_l:  # the game model's pre-game inputs from the report: share missing and lineup strength
                ctx_ = {**c.ctxs[gid], **{sd: {**c.ctxs[gid][sd], "missing": c.miss_lock.get(gid, {}).get(sd, c.ctxs[gid][sd]["missing"])}
                                         for sd in ("home", "away")}}
                est = engine.predict(c, g, ctx_, {}, eff=c.eff, base_override=c.base[gid], lineup_feat=lfeat_lock.get(gid))
            else:
                est = engine.predict(c, g, c.ctxs[gid], {}, eff=c.eff, base_override=c.base[gid], lineup_feat=c.lfeat.get(gid))
            godds = None
            qf = ml_fair.get(gid)
            if qf:
                lo = lambda x: math.log(max(x, 1e-6) / max(1 - x, 1e-6))
                est["win_home_model"], est["win_home_market"] = est["win_home"], qf
                est["win_home"] = 1 / (1 + math.exp(-(BLEND_W * lo(est["win_home"]) + (1 - BLEND_W) * lo(qf))))
                godds = {"provider": "replay", "ml_home": round(parlay.wmx_odds(qf), 2), "ml_away": round(parlay.wmx_odds(1 - qf), 2)}
            ests[gid] = est["margin"]
            ests_t[gid] = est["total"]
            side_rows = {}
            for side in ("home", "away"):
                rows = []
                if on_l:  # everyone expected at the lock; those who then sit have their legs voided, as on Winamax
                    side_rows[side] = [{"id": r_["id"], "name": r_["name"], "out": False, "p_play": r_["p_play"], "status": r_["status"],
                                        "disp": {k: round(v, 3) for k, v in P.player_disp({"dsp": r_["dsp"]}, pdisp).items()}, **r_["proj"]}
                                       for r_ in lrows[(gid, side)]]
                    continue
                for r in byg[gid].get(g[side], []):
                    pid = str(r["player_id"])
                    pr = plogs.get((gid, pid))
                    if not pr or not r["min"]:
                        continue
                    rows.append({"id": pid, "name": r["name"], "out": False, "p_play": 1.0, "disp": {k: round(v, 3) for k, v in P.player_disp({"dsp": pt.dsp_log.get((gid, pid)) or {}}, pdisp).items()},
                                 **pr})
                side_rows[side] = rows
            pay = {"id": gid, "home": {"abbr": g["home"]}, "away": {"abbr": g["away"]}, "tip": g["date"], "est": est,
                   "players": side_rows, "gauge": {}}
            slate.append(({"odds": godds}, pay))
        if not slate:
            continue
        plg = {**plogs, **plock} if use_lock else plogs
        for rname in rules:
            parlay.TICKET_FILTER = rule(rname, ests, plg)
            w0 = dict(parlay.LEG_W)
            if rname == "nofix":  # the leg chance before the game-script correction
                parlay.LEG_W.update(dog=0.0, min_hi=0.0)
            if rname == "refit":  # game-script weights given in the environment (fitted on another season)
                parlay.LEG_W.update(dog=float(os.environ["LEG_DOG"]), min_hi=float(os.environ["LEG_MINHI"]))
            out, _ = parlay.build(slate, pdisp, calib_for(day), avg, real_props=real)
            lp = out.get("ladder")
            if lp and rname == rules[0]:  # the Ladder's daily 2.00-2.10 single, scored like the live site does
                gid = lp["game"]
                rows = {str(r["player_id"]): r for team in byg.get(gid, {}).values() for r in team}
                ladder_days.append((day, {**lp, "result": parlay.score_leg(lp["leg"], c.meta[gid], rows)}))
            elif rname == rules[0]:
                ladder_days.append((day, None))
            for tk in out.get("game_tickets", []):
                gid = tk["game"]
                rows = {str(r["player_id"]): r for team in byg.get(gid, {}).values() for r in team}
                res = [parlay.score_leg(l, c.meta[gid], rows) for l in tk["legs"]]
                live = [x for x in res if x != "void"]
                gm = c.meta[gid]
                detail = [{"p": l["p"], "res": x, "kind": l.get("kind"), "stat": l.get("stat"), "team": l.get("team"), "line": l.get("line"),
                           "starter": int((rows.get(str(l.get("player"))) or {}).get("starter") or 0),
                           "pmin": (plg.get((gid, str(l.get("player")))) or {}).get("min"), "amin": (rows.get(str(l.get("player"))) or {}).get("min"),
                           "player": l.get("player")}
                          for l, x in zip(tk["legs"], res)]
                for dd, l in zip(detail, tk["legs"]):  # inputs known before the game, for testing new leg factors
                    side = "home" if l.get("team") == gm["home"] else "away"
                    cx, ox = c.ctxs[gid][side], c.ctxs[gid]["away" if side == "home" else "home"]
                    dd.update(home=side == "home", total=ests_t.get(gid), rest=cx.get("rest"), b2b=cx.get("b2b"),
                              t34=cx.get("three_in_four"), km=cx.get("km"), miss=cx.get("missing"), omiss=ox.get("missing"),
                              opp_b2b=ox.get("b2b"), proj=l.get("proj"), avg=l.get("avg"), l5=l.get("last5"),
                              voices=l.get("voices"), sd=(l.get("dist") or {}).get("sd"))
                    if lrows.get((gid, side)) is not None:  # teammates at the lock: expected but sat, and Questionable
                        lst_ = lrows[(gid, side)]
                        sts_ = (PE.LOCK[0].get((day, l.get("team") or gm[side])) or {}).get("st") or {}
                        me = str(l.get("player"))
                        dd.update(lk_st=sts_.get(me),
                                  lk_sur=[(x["proj"]["min"], x["p_play"]) for x in lst_ if x["id"] != me and x["status"] is None
                                          and (rows.get(x["id"]) or {}).get("min", 0) <= 0],
                                  lk_q=[(x["proj"]["min"], (rows.get(x["id"]) or {}).get("min", 0) > 0) for x in lst_
                                        if x["id"] != me and x["status"] == "Questionable"],
                                  lk_out=[pid_ for pid_, s_ in sts_.items() if s_ in ("Out", "Doubtful")])
                    if l.get("kind") == "prop":
                        h = hist.get(str(l.get("player")))
                        if h is not None and len(h):
                            v = h[l["stat"]].tail(10).to_numpy(float)
                            dd.update(l10_over=float((v > l["line"]).mean()), l10_sd=float(v.std()),
                                      min_l3=float(h["min"].tail(3).mean()), min_szn=float(h["min"].mean()),
                                      start_last=int(h["starter"].iloc[-1] or 0) if "starter" in h else None, gp=len(h))
                tickets[rname].append({"day": day, "game": gid, "home": gm["home"], "p": tk["p"], "est": tk.get("winamax_est"),
                                "m_exp": ests.get(gid), "m_act": gm["home_pts"] - gm["away_pts"],
                                "legs": [(l["p"], x, l.get("kind")) for l, x in zip(tk["legs"], res)], "detail": detail,
                                "hit": bool(live) and all(x == "hit" for x in live)})
            parlay.LEG_W.update(w0)
        print(day, {r: len(v) for r, v in tickets.items()}, flush=True)
    parlay.TICKET_FILTER = None
    json.dump(tickets, open(f"/tmp/tickets_{season}{os.environ.get('TAG', '')}.json", "w"), default=float)
    for rname, tk in tickets.items():
        print(f"\n== rule: {rname}")
        report(season, tk)
    from pipeline import ladder
    ls = ladder.state(ladder_days)
    picks = [lp for _, lp in ladder_days if lp]
    lv = [s_["level"] for s_ in ls["steps"] if s_["result"] == "hit"]
    print(f"\nladder: {len(picks)} picks on {len(ladder_days)} days, landed {ls['won']}/{ls['bets']} (stated {ls['expected']:.1f}), "
          f"profit at the estimated odds {ls['profit']:+.1f} units, best climb {ls['best']} ({ls['best_days']}), restarts {ls['restarts']}, "
          f"reached level 3+ {sum(1 for x in lv if x == 3)} times, 5+ {sum(1 for x in lv if x == 5)} times")
    from collections import Counter
    print("ladder picks by kind:", dict(Counter(lp["leg"]["kind"] + "/" + str(lp["leg"].get("stat")) for lp in picks)))
    for t_ in (1, 2, 3, 4):
        pk = [lp for lp in picks if lp.get("tier") == t_ and lp["result"] in ("hit", "miss")]
        if pk:
            print(f"  tier {t_}: {sum(lp['result'] == 'hit' for lp in pk)}/{len(pk)} landed, stated {sum(lp['p'] for lp in pk):.1f}, "
                  f"odds {sum(lp['odds'] for lp in pk) / len(pk):.2f}, profit {sum((lp['odds'] - 1) if lp['result'] == 'hit' else -1 for lp in pk):+.1f}")
    json.dump(ladder_days, open(f"/tmp/ladder_{season}{os.environ.get('TAG', '')}.json", "w"), default=float)


def report(season, tickets):
    n = len(tickets)
    if not n:
        print("no tickets")
        return
    legs = [x for t in tickets for x in t["legs"] if x[1] in ("hit", "miss")]
    print(f"\nseason {season}: {n} tickets, landed {sum(t['hit'] for t in tickets)} (expected {sum(t['p'] for t in tickets):.1f})")
    print(f"legs landed {sum(x[1] == 'hit' for x in legs)}/{len(legs)} (expected {sum(x[0] for x in legs):.1f})")
    print(f"profit, 1 unit a ticket: estimated payout {sum((t['est'] - 1) if t['hit'] else -1 for t in tickets):+.1f}, "
          f"fair odds {sum((1 / t['p'] - 1) if t['hit'] else -1 for t in tickets):+.1f}")
    bands = defaultdict(lambda: [0, 0, 0.0])
    for p, x, _ in legs:
        b = bands[round(min(p, 0.89) * 20) / 20]
        b[0] += 1; b[1] += x == "hit"; b[2] += p
    print("legs by stated chance:", ", ".join(f"{k:.2f}: {v[1]}/{v[0]} ({v[2] / v[0]:.2f} stated)" for k, v in sorted(bands.items())))
    months = defaultdict(lambda: [0, 0, 0.0])
    for t in tickets:
        m = months[t["day"][:7]]
        m[0] += 1; m[1] += t["hit"]; m[2] += t["p"]
    print("by month:", ", ".join(f"{k}: {v[1]}/{v[0]} (exp {v[2]:.1f})" for k, v in sorted(months.items())))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 2026, *(a[1:3] if len(a) >= 3 else (None, None)),
         rules=tuple(a[3].split(",")) if len(a) >= 4 else ("base",))
