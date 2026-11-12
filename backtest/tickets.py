"""Replay the per-game tickets over a past season with the live build rules, then settle them.

Every input is as of before the game: player projections and spreads from player_engine.walk (out-of-sample),
season-to-date and last-5 averages from earlier games only. Differences from live: no real posted prop lines (every
line is the season average, as live does when none is posted), no market odds for winner/handicap/total legs, no
psychology spots on players, players who did not play are left out (live, their legs would be void), and the game
estimate's factor sizes are fitted on the whole history.

    python -m backtest.tickets [SEASON] [FIRST_DAY LAST_DAY]
"""
import json
import sys
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
    return None if name in ("base", "nofix") else keep


def main(season, d0=None, d1=None, rules=("base",)):
    games, players = load_games(), load_players()
    c = engine.build_context(games, players, [], {"half_life": 90, "lam": 3.0, "carry": 0.6, "lam_effects": 40.0},
                             stints=load_stints())
    pt, pe, pdisp, plogs, ptrack, byg = PE.walk(c, players, {}, season)
    day_of = {gid: g["day"] for gid, g in c.meta.items()}
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
            est = engine.predict(c, g, c.ctxs[gid], {}, eff=c.eff, base_override=c.base[gid], lineup_feat=c.lfeat.get(gid))
            ests[gid] = est["margin"]
            ests_t[gid] = est["total"]
            side_rows = {}
            for side in ("home", "away"):
                rows = []
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
            slate.append(({"odds": None}, pay))
        if not slate:
            continue
        for rname in rules:
            parlay.TICKET_FILTER = rule(rname, ests, plogs)
            w0 = dict(parlay.LEG_W)
            if rname == "nofix":  # the leg chance before the game-script correction
                parlay.LEG_W.update(dog=0.0, min_hi=0.0)
            out, _ = parlay.build(slate, pdisp, {}, avg)
            for tk in out.get("game_tickets", []):
                gid = tk["game"]
                rows = {str(r["player_id"]): r for team in byg.get(gid, {}).values() for r in team}
                res = [parlay.score_leg(l, c.meta[gid], rows) for l in tk["legs"]]
                live = [x for x in res if x != "void"]
                gm = c.meta[gid]
                detail = [{"p": l["p"], "res": x, "kind": l.get("kind"), "stat": l.get("stat"), "team": l.get("team"), "line": l.get("line"),
                           "starter": int((rows.get(str(l.get("player"))) or {}).get("starter") or 0),
                           "pmin": (plogs.get((gid, str(l.get("player")))) or {}).get("min"), "amin": (rows.get(str(l.get("player"))) or {}).get("min")}
                          for l, x in zip(tk["legs"], res)]
                for dd, l in zip(detail, tk["legs"]):  # inputs known before the game, for testing new leg factors
                    side = "home" if l.get("team") == gm["home"] else "away"
                    cx, ox = c.ctxs[gid][side], c.ctxs[gid]["away" if side == "home" else "home"]
                    dd.update(home=side == "home", total=ests_t.get(gid), rest=cx.get("rest"), b2b=cx.get("b2b"),
                              t34=cx.get("three_in_four"), km=cx.get("km"), miss=cx.get("missing"), omiss=ox.get("missing"),
                              opp_b2b=ox.get("b2b"), proj=l.get("proj"), avg=l.get("avg"), l5=l.get("last5"),
                              voices=l.get("voices"), sd=(l.get("dist") or {}).get("sd"))
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
    json.dump(tickets, open(f"/tmp/tickets_{season}.json", "w"), default=float)
    for rname, tk in tickets.items():
        print(f"\n== rule: {rname}")
        report(season, tk)


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
