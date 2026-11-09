"""Fetch -> rebuild context -> predict -> freeze/score -> write the website's data.

python -m pipeline.run           live (ESPN)
python -m pipeline.run --demo    simulated league, no network (preview and tests)
"""
import argparse
import math
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from model import effects, engine, explain, ratings
from model.features import Tracker
from . import espn
from .store import (OVR, PRED, ROOT, SITE, STATE, load_games, load_players, read_json, write_json)
from .teams import TEAMS, info

STAT_NAMES = {"tpm": "Threes made", "reb": "Rebounds", "ast": "Assists"}


def r1(x, d=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), d)


def season_label(s):
    return f"{s - 1}-{str(s)[2:]}"


def lines_around(center, sd, step, n=2):
    base = math.floor(center / step) * step + step / 2
    out = []
    for k in range(-n, n + 1):
        L = base + k * step
        out.append({"line": L, "over": round(1 - effects.norm_cdf((L - center) / sd), 3)})
    return out


def main(demo=False, now=None, collect_data=True):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(espn.ET).date()
    if not collect_data:
        pass
    elif demo:
        from . import demo as demo_mod
        print("demo:", demo_mod.generate(today))
    else:
        from . import collect
        print("collect:", collect.collect(today))

    games = load_games()
    players = load_players()
    upcoming = [g for g in (read_json(STATE / "upcoming.json", []) or [])]
    inj_raw = read_json(STATE / "injuries.json", {}) or {}
    injuries = inj_raw.get("teams", {}) or {}
    meta_logos = read_json(STATE / "teams_meta.json", {}) or {}
    tuned = read_json(ROOT / "model" / "tuned.json", {}) or {}
    analyst = (read_json(OVR / "analyst.json", {}) or {}).get("games", {})

    cur = espn.season_of(today.isoformat())
    c = engine.build_context(games, players, upcoming, tuned)
    rts = engine.fit_all(games, today.isoformat(), c.tuned)
    season_start = games[games["season"] == cur]["day"].min() if (games["season"] == cur).any() else today.isoformat()
    prev_rows = [r[:5] for r in c.rows if r[5] < season_start]
    eff_prev = effects.estimate(prev_rows, c.tuned["lam_effects"]) if len(prev_rows) >= 200 else c.eff
    eff_table = c.eff.table()
    tr = c.tracker

    teams = {}
    for ab in TEAMS:
        t = info(ab)
        t["logo"] = (meta_logos.get(ab) or {}).get("logo")
        teams[ab] = t

    # ------------------------------------------------------------ standings & ratings
    standings = {}
    seed_of = {}
    rt = rts["pts"]
    net = {ab: rt.net(ab) if rt else 0.0 for ab in TEAMS}
    off = {ab: (rt.att[ratings.IDX[ab]] if rt else 0.0) for ab in TEAMS}
    dfn = {ab: (rt.dfn[ratings.IDX[ab]] if rt else 0.0) for ab in TEAMS}
    rank = lambda d: {ab: i + 1 for i, ab in enumerate(sorted(d, key=lambda k: -d[k]))}
    net_rank, off_rank, def_rank = rank(net), rank(off), rank(dfn)
    reg = games[(games["season"] == cur) & (games["stype"] == 2)]
    for conf in ("East", "West"):
        tab = tr.conf_table(cur, conf)
        rows = []
        lead = tab[0] if tab else None
        for i, (ab, w, l, p) in enumerate(tab):
            m = reg[(reg["home"] == ab) | (reg["away"] == ab)]
            hm = m[m["home"] == ab]
            aw = m[m["away"] == ab]
            hw = int((hm["home_pts"] > hm["away_pts"]).sum())
            awn = int((aw["away_pts"] > aw["home_pts"]).sum())
            cm = m[[TEAMS[x][3] == conf and TEAMS[y][3] == conf for x, y in zip(m["home"], m["away"])]]
            cw = int(sum((h == ab and hp > ap) or (a == ab and ap > hp)
                         for h, a, hp, ap in zip(cm["home"], cm["away"], cm["home_pts"], cm["away_pts"])))
            pdiff = [(hp - ap) if h == ab else (ap - hp) for h, hp, ap in zip(m["home"], m["home_pts"], m["away_pts"])]
            res = tr.season_res[cur][ab]
            l10 = [r for r in res if True][-10:]
            f = tr.side({"day": today.isoformat(), "season": cur, "stype": 2, "home": ab, "game_id": "x"}, ab, ab, True)
            rows.append({"abbr": ab, "seed": i + 1, "w": w, "l": l, "pct": r1(p, 3),
                         "gb": ((lead[1] - w) + (l - lead[2])) / 2 if lead else 0,
                         "home": f"{hw}-{len(hm) - hw}", "away": f"{awn}-{len(aw) - awn}", "conf": f"{cw}-{len(cm) - cw}",
                         "l10": f"{sum(r['win'] for r in l10)}-{sum(not r['win'] for r in l10)}",
                         "streak": (("W" if f["streak"] > 0 else "L") + str(abs(f["streak"]))) if f["streak"] else "-",
                         "pd": r1(sum(pdiff) / len(pdiff)) if pdiff else 0.0, "net": r1(net[ab]),
                         "zone": "top" if i < 6 else "playin" if i < 10 else "out",
                         "confidence": f["confidence"]})
            seed_of[ab] = i + 1
        standings[conf] = rows

    # ------------------------------------------------------------ helpers for game payloads
    def team_block(ab, f, injured_list=None):
        t = teams[ab]
        return {"abbr": ab, "name": t["name"], "short": t["short"], "color": t["color"], "alt": t["alt"], "logo": t["logo"],
                "record": f.get("record"), "seed": seed_of.get(ab), "conf": t["conf"], "net": r1(net[ab]),
                "net_rank": net_rank[ab], "rest": f["rest"], "b2b": f["b2b"], "km": f["km"], "streak": f["streak"],
                "confidence": f["confidence"], "form": f["form"], "missing": r1(f["missing"], 3),
                "missing_list": f["missing_list"], "injuries": injured_list or [], "series": f.get("series")}

    def est_block(est):
        sdm, sdt = est["sd_margin"], est["sd_total"]
        ev = {(r["target"], r["key"]): r for r in eff_table}
        parts = []
        for p in est["parts"]:
            e = ev.get((p["target"], p["key"]), {})
            parts.append({**p, "evidence": e.get("evidence", "none"), "per": e.get("pts"), "n": e.get("n", 0),
                          "means": e.get("means")})
        m = est["margin"]
        out = {"win_home": r1(est["win_home"], 3), "margin": r1(m), "total": r1(est["total"]),
               "home_pts": r1(est["home_pts"]), "away_pts": r1(est["away_pts"]), "sd_margin": r1(sdm), "sd_total": r1(sdt),
               "base": {k: r1(v, 3 if k == "win_home" else 1) for k, v in est["base"].items()},
               "physical": {k: r1(v, 2) for k, v in est["physical"].items()},
               "mind": {k: r1(v, 2) for k, v in est["mind"].items()},
               "win_home_nomind": r1(est["win_home_nomind"], 3), "margin_nomind": r1(est["margin_nomind"]),
               "baseline": {k: r1(v, 3 if k == "win_home" else 1) for k, v in est["baseline"].items()},
               "parts": parts,
               "total_lines": lines_around(est["total"], sdt, 5.0),
               "spread_lines": [{"line": L, "home_cover": round(effects.norm_cdf((m - L) / sdm), 3)}
                                for L in sorted({math.floor(m) + 0.5 + k * 3 for k in (-2, -1, 0, 1, 2)})],
               "others": {}}
        for st, o in (est.get("others") or {}).items():
            out["others"][st] = {"label": STAT_NAMES[st], "home": r1(o["home"]), "away": r1(o["away"]), "total": r1(o["total"]),
                                 "lines": lines_around(o["total"], o["sd_total"], 2.0 if st == "tpm" else 3.0)}
        return out

    def game_payload(g, ctx, est, kind, injured=None):
        h, a = g["home"], g["away"]
        sd = explain.sides(est, ctx, h, a, eff_table)
        payload = {
            "id": str(g["game_id"]), "tip": g.get("date"), "day": g["day"], "season": int(g["season"]), "stype": int(g["stype"]),
            "venue": g.get("venue"), "national_tv": bool(g.get("national_tv")), "neutral": bool(g.get("neutral")),
            "note": g.get("note"), "rivalry": ctx["rivalry"], "kind": kind,
            "home": team_block(h, ctx["home"], (injured or {}).get(h)), "away": team_block(a, ctx["away"], (injured or {}).get(a)),
            "est": est_block(est), "sides": sd,
            "gauge": {"home": explain.gauge(sd["home"]["mind"]), "away": explain.gauge(sd["away"]["mind"])},
            "reasoning": explain.reasoning(est, ctx, h, a, sd, (net[h], net[a]) if kind == "estimate" else None),
        }
        return payload

    def card(p, result=None, live=None):
        e = p["est"]
        tags = []
        for side in ("home", "away"):
            for x in p["sides"][side]["mind"][:2]:
                if abs(x["pts"]) >= 0.25 or x["evidence"] in ("strong", "moderate"):
                    tags.append({"team": p[side]["abbr"], "label": x["label"], "pts": x["pts"]})
        c_ = {"id": p["id"], "tip": p["tip"], "day": p["day"], "stype": p["stype"], "kind": p["kind"],
              "home": p["home"]["abbr"], "away": p["away"]["abbr"],
              "home_rec": p["home"]["record"], "away_rec": p["away"]["record"],
              "win_home": e["win_home"], "margin": e["margin"], "total": e["total"], "mind": e["mind"]["margin"],
              "tags": tags[:3], "tv": p["national_tv"]}
        if result:
            c_.update(result)
        if live:
            c_["live"] = live
        return c_

    # ------------------------------------------------------------ upcoming
    PRED.mkdir(parents=True, exist_ok=True)
    trc = tr.clone()
    upcoming_payloads = {}
    seen = set()
    for g in sorted(upcoming, key=lambda x: (x["date"], x["game_id"])):
        gid = str(g["game_id"])
        ahead = (date.fromisoformat(g["day"]) - today).days
        news = ahead <= 3
        ctx = trc.pre_game(g, injuries=injuries if news else None)
        for side in ("home", "away"):  # last-result spots only apply to a team's next game
            if g[side] in seen:
                ctx[side]["bounce"] = ctx[side]["letdown"] = 0
            seen.add(g[side])
        trc.advance_schedule_only(g)
        tip = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        path = PRED / str(g["season"]) / f"{gid}.json"
        old = read_json(path)
        if old and old.get("frozen"):
            upcoming_payloads[gid] = (g, old["payload"], g.get("state"))
            continue
        if now >= tip:
            if old:
                old["frozen"] = True
                write_json(path, old)
                upcoming_payloads[gid] = (g, old["payload"], g.get("state"))
            continue
        est = engine.predict(c, g, ctx, rts)
        payload = game_payload(g, ctx, est, "estimate", {t: injuries.get(t, []) for t in (g["home"], g["away"])} if news else None)
        payload["news"] = news
        payload["made_at"] = now.isoformat()
        if gid in analyst:
            payload["analyst"] = analyst[gid]
        write_json(path, {"game_id": gid, "tip": g["date"], "made_at": now.isoformat(), "frozen": False,
                          "home": g["home"], "away": g["away"], "season": int(g["season"]), "payload": payload})
        upcoming_payloads[gid] = (g, payload, g.get("state"))

    # ------------------------------------------------------------ score frozen predictions
    fin_by_id = {str(k): v for k, v in c.meta.items()}
    live_scored = []
    for path in sorted(PRED.glob("*/*.json")):
        pj = read_json(path)
        gid = pj["game_id"]
        if gid in fin_by_id and not pj.get("result"):
            gg = fin_by_id[gid]
            pj["frozen"] = True
            pj["result"] = {"home_pts": int(gg["home_pts"]), "away_pts": int(gg["away_pts"])}
            write_json(path, pj)
        if pj.get("result") and pj.get("frozen"):
            live_scored.append(pj)

    # ------------------------------------------------------------ recent results (model checks where no frozen estimate)
    frozen_ids = {p["game_id"]: p for p in live_scored}
    recent_from = (today - timedelta(days=21)).isoformat()
    pg, _ = engine.players_by_game(players)
    result_payloads = {}
    checks = []
    for g in c.games.to_dict("records"):
        gid = str(g["game_id"])
        if int(g["season"]) != cur or gid not in c.base:
            continue
        if gid in frozen_ids:
            payload = frozen_ids[gid]["payload"]
            payload["kind"] = "frozen"
        else:
            est = engine.predict(c, g, c.ctxs[gid], {}, eff=eff_prev, base_override=c.base[gid])
            payload = game_payload(g, c.ctxs[gid], est, "check")
        checks.append((g, payload))
        if g["day"] >= recent_from:
            result_payloads[gid] = (g, payload)

    def result_block(g):
        gid = str(g["game_id"])
        box = {}
        for side, ab in (("home", g["home"]), ("away", g["away"])):
            pref = "h_" if side == "home" else "a_"
            box[side] = {k: (None if g.get(pref + k) is None or (isinstance(g.get(pref + k), float) and math.isnan(g.get(pref + k)))
                             else int(g.get(pref + k))) for k in ("fgm", "fga", "tpm", "tpa", "ftm", "fta", "reb", "oreb", "ast", "tov", "stl", "blk")}
        tops = {}
        for side, ab in (("home", g["home"]), ("away", g["away"])):
            rows = sorted(((v[1], v[0], v[2], v[3], pid) for pid, v in (pg.get(gid, {}).get(ab, {}) or {}).items() if v[0] > 0),
                          reverse=True)[:5]
            tops[side] = [{"name": tr.names.get(pid, pid), "pts": int(pts), "min": int(mn), "reb": int(rb), "ast": int(asn)}
                          for pts, mn, rb, asn, pid in rows]
        return {"home_pts": int(g["home_pts"]), "away_pts": int(g["away_pts"]), "ot": int(g.get("ot") or 0), "box": box, "top": tops}

    # ------------------------------------------------------------ write site data
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "game").mkdir(parents=True, exist_ok=True)
    (SITE / "team").mkdir(parents=True, exist_ok=True)

    cards_up, cards_res = [], []
    for gid, (g, payload, state) in upcoming_payloads.items():
        out = dict(payload)
        out["state"] = state
        out["detail"] = g.get("detail")
        if state == "in":
            out["live"] = {"home_pts": g.get("home_pts"), "away_pts": g.get("away_pts"), "detail": g.get("detail")}
        write_json(SITE / "game" / f"{gid}.json", out)
        cards_up.append(card(payload, live=out.get("live")))
    for gid, (g, payload) in result_payloads.items():
        out = dict(payload)
        out["state"] = "post"
        out["result"] = result_block(g)
        hm = out["result"]["home_pts"] - out["result"]["away_pts"]
        e = payload["est"]
        out["scored"] = {"hit": (e["win_home"] >= 0.5) == (hm > 0), "err_margin": r1(hm - e["margin"]),
                         "err_total": r1(out["result"]["home_pts"] + out["result"]["away_pts"] - e["total"])}
        write_json(SITE / "game" / f"{gid}.json", out)
        cards_res.append(card(payload, result={"home_pts": out["result"]["home_pts"], "away_pts": out["result"]["away_pts"],
                                               "ot": out["result"]["ot"], "hit": out["scored"]["hit"]}))
    cards_up.sort(key=lambda x: (x["tip"] or "", x["id"]))
    cards_res.sort(key=lambda x: (x["day"], x["id"]), reverse=True)

    # accuracy
    def summarise(items):
        """items: list of (payload_est, home_pts, away_pts)."""
        if not items:
            return None
        n = len(items)
        acc = defaultdict(float)
        bins = defaultdict(lambda: [0, 0.0, 0])
        for e, hp, ap in items:
            hw = 1.0 if hp > ap else 0.0
            m, t = hp - ap, hp + ap
            acc["hit"] += ((e["win_home"] >= 0.5) == (hw == 1))
            acc["brier"] += (e["win_home"] - hw) ** 2
            acc["brier_nomind"] += (e["win_home_nomind"] - hw) ** 2
            acc["brier_base"] += (e["baseline"]["win_home"] - hw) ** 2
            acc["mae_m"] += abs(m - e["margin"])
            acc["mae_m_nomind"] += abs(m - e["margin_nomind"])
            acc["mae_m_base"] += abs(m - e["baseline"]["margin"])
            acc["mae_t"] += abs(t - e["total"])
            acc["mae_t_base"] += abs(t - e["baseline"]["total"])
            fav = max(e["win_home"], 1 - e["win_home"])
            b = min(9, int((fav - 0.5) * 20))
            bins[b][0] += 1
            bins[b][1] += fav
            bins[b][2] += int((e["win_home"] >= 0.5) == (hw == 1))
        out = {k: round(v / n, 4) for k, v in acc.items()}
        out["n"] = n
        out["calibration"] = [{"p": round(v[1] / v[0], 3), "hit": round(v[2] / v[0], 3), "n": v[0]} for k, v in sorted(bins.items())]
        return out

    live_items = [(p["payload"]["est"], p["result"]["home_pts"], p["result"]["away_pts"]) for p in live_scored]
    check_items = [(p["est"], int(g["home_pts"]), int(g["away_pts"])) for g, p in checks if p["kind"] == "check"]
    recent_scored = []
    for p in sorted(live_scored, key=lambda x: x["tip"], reverse=True)[:40]:
        e = p["payload"]["est"]
        recent_scored.append({"id": p["game_id"], "day": p["payload"]["day"], "home": p["home"], "away": p["away"],
                              "win_home": e["win_home"], "margin": e["margin"], "total": e["total"], **p["result"]})
    write_json(SITE / "accuracy.json", {
        "live": summarise(live_items), "checks": summarise(check_items), "recent": recent_scored,
        "backtest": read_json(ROOT / "backtest" / "results.json"), "factors": eff_table,
        "effects_games": c.eff.n, "sd_margin": r1(c.eff.sd_margin), "sd_total": r1(c.eff.sd_total)})

    # teams
    team_list = []
    for ab, t in teams.items():
        f = tr.side({"day": today.isoformat(), "season": cur, "stype": 2, "home": ab, "game_id": "x"}, ab, ab, True)
        team_list.append({"abbr": ab, "name": t["name"], "short": t["short"], "conf": t["conf"], "div": t["div"],
                          "color": t["color"], "alt": t["alt"], "logo": t["logo"], "record": f["record"],
                          "seed": seed_of.get(ab), "net": r1(net[ab]), "net_rank": net_rank[ab]})
        write_json(SITE / "team" / f"{ab}.json", team_page(ab, t, f, tr, c, cur, net, off, dfn, net_rank, off_rank, def_rank,
                                                         seed_of, cards_up, cards_res, injuries, players, eff_table))
    write_json(SITE / "teams.json", team_list)
    write_json(SITE / "standings.json", {"season": season_label(cur), "East": standings["East"], "West": standings["West"]})
    write_json(SITE / "schedule.json", {"upcoming": cards_up, "results": cards_res})
    spots = []
    for cd in cards_up[:40]:
        for tg in cd["tags"]:
            spots.append({**tg, "game": cd["id"], "tip": cd["tip"], "home": cd["home"], "away": cd["away"]})
    spots.sort(key=lambda x: -abs(x["pts"]))
    write_json(SITE / "home.json", {"spots": spots[:10]})
    cs = read_json(STATE / "collect.json", {}) or {}
    write_json(SITE / "meta.json", {"updated": now.isoformat(), "mode": "demo" if demo else "live", "season": season_label(cur),
                                    "games": int(len(games)), "box_games": int(games["box"].sum()) if len(games) else 0,
                                    "injuries_as_of": inj_raw.get("as_of"), "errors": len(cs.get("errors") or []),
                                    "tuned": c.tuned})
    print(f"site: {len(cards_up)} upcoming, {len(cards_res)} recent results, {len(live_scored)} scored, "
          f"{len(check_items)} model checks")


def team_page(ab, t, f, tr, c, cur, net, off, dfn, net_rank, off_rank, def_rank, seed_of, cards_up, cards_res, injuries,
              players, eff_table):
    res = tr.season_res[cur][ab]
    allres = [r for s in sorted(tr.season_res) for r in tr.season_res[s][ab]]

    def profile(pred):
        rs = [r for r in pred if r.get("resid") is not None]
        if not rs:
            return None
        return {"n": len(rs), "vs_exp": round(sum(r["resid"] for r in rs) / len(rs), 1),
                "win": round(sum(r["win"] for r in rs) / len(rs), 3)}
    after_loss, after_win, after_blowout, close = [], [], [], []
    for prev, r in zip(allres, allres[1:]):
        (after_loss if not prev["win"] else after_win).append(r)
        if not prev["win"] and prev["margin"] <= -20:
            after_blowout.append(r)
    close = [r for r in allres if abs(r["margin"]) <= 5]
    # b2b and revenge from context
    b2b, rev, road4 = [], [], []
    for gid, ctx in c.ctxs.items():
        g = c.meta[gid]
        if ab not in (g["home"], g["away"]) or gid not in c.base:
            continue
        side = "home" if g["home"] == ab else "away"
        b = c.base[gid]
        resid = ((g["home_pts"] - g["away_pts"]) - (b[0] - b[1])) * (1 if side == "home" else -1)
        win = (g["home_pts"] > g["away_pts"]) == (side == "home")
        r = {"resid": resid, "win": win}
        if ctx[side]["b2b"]:
            b2b.append(r)
        if ctx[side]["revenge"]:
            rev.append(r)
        if ctx[side]["road_long"]:
            road4.append(r)
    regs = tr.regulars(ab)
    pl = players[players["team"] == ab] if len(players) else players
    roster = []
    if len(pl):
        cur_ids = set(c.games[(c.games["season"] == cur)]["game_id"].astype(str))
        plc = pl[pl["game_id"].astype(str).isin(cur_ids) & (pl["min"] > 0)]
        if len(plc):
            agg = plc.groupby(["player_id", "name"]).agg(gp=("min", "size"), mpg=("min", "mean"), ppg=("pts", "mean"),
                                                         rpg=("reb", "mean"), apg=("ast", "mean")).reset_index()
            agg = agg.sort_values("mpg", ascending=False).head(12)
            for row in agg.to_dict("records"):
                roster.append({"name": row["name"], "gp": int(row["gp"]), "mpg": round(row["mpg"], 1), "ppg": round(row["ppg"], 1),
                               "rpg": round(row["rpg"], 1), "apg": round(row["apg"], 1),
                               "share": round(regs.get(str(row["player_id"]), 0), 3)})
    return {
        "abbr": ab, "name": t["name"], "short": t["short"], "conf": t["conf"], "div": t["div"], "color": t["color"], "alt": t["alt"],
        "logo": t["logo"], "record": f["record"], "seed": seed_of.get(ab), "streak": f["streak"], "confidence": f["confidence"],
        "net": round(net[ab], 1), "off": round(off[ab], 1), "def": round(dfn[ab], 1),
        "net_rank": net_rank[ab], "off_rank": off_rank[ab], "def_rank": def_rank[ab],
        "form": [{"day": r["day"], "opp": r["opp"], "home": r["home"], "margin": r["margin"], "win": r["win"],
                  "vs_exp": None if r.get("resid") is None else round(r["resid"], 1)} for r in res[-12:]],
        "mind": {"after_loss": profile(after_loss), "after_win": profile(after_win), "after_blowout": profile(after_blowout),
                 "b2b": profile(b2b), "revenge": profile(rev), "road_long": profile(road4),
                 "close": {"n": len(close), "w": sum(r["win"] for r in close)}},
        "upcoming": [x for x in cards_up if ab in (x["home"], x["away"])][:8],
        "results": [x for x in cards_res if ab in (x["home"], x["away"])][:8],
        "injuries": injuries.get(ab, []), "roster": roster,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="simulated league, no network")
    ap.add_argument("--no-collect", action="store_true", help="rebuild from the stored data only")
    a = ap.parse_args()
    main(demo=a.demo, collect_data=not a.no_collect)
