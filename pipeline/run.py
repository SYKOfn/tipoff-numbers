"""Fetch -> rebuild context -> predict -> freeze/score -> write the website's data.

python -m pipeline.run           live (ESPN)
python -m pipeline.run --demo    simulated league, no network (preview and tests)
"""
import argparse
import math
import os
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from model import effects, engine, explain, extras, parlay, prop_test, ratings
from model import player_engine as PE
from model import players as PM
from model.features import Tracker
from . import player_pages
from . import espn
from .store import (OVR, PRED, ROOT, SITE, STATE, load_games, load_players, load_stints, read_json, write_json)
from .teams import TEAMS, info

STAT_NAMES = {"tpm": "Threes made", "reb": "Rebounds", "ast": "Assists"}


def r1(x, d=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), d)


def season_label(s):
    return f"{s - 1}-{str(s)[2:]}"


BLEND_W = 0.4  # model weight in the Pinnacle blend (log-odds), from the 1,368-game test


MODEL_HIST = int(os.environ.get("MODEL_HIST", "5"))  # full seasons before the current one used by the model
LOCK_HOURS = float(os.environ.get("LOCK_HOURS", "3"))  # the day's tickets are chosen this long before the first tip


def card_story(p):
    """One plain line for a game card: who is missing, who is tired."""
    bits = []
    for side in ("away", "home"):
        t = p.get(side) or {}
        miss = [m["name"] for m in (t.get("missing_list") or [])][:2]
        if miss and (t.get("missing") or 0) >= 0.06:
            bits.append(f"{t['short']} without {' and '.join(miss)}")
    for side in ("away", "home"):
        t = p.get(side) or {}
        if t.get("b2b") and len(bits) < 2:
            bits.append(f"{t['short']} on a back-to-back")
    return ("; ".join(bits[:2]) + ".") if bits else None


def status_info(now, upcoming, cs):
    """For the status line: odds credits today, the next refresh, collector errors."""
    from . import oddsapi, should_run
    st = read_json(STATE / "oddsapi.json", {}) or {}
    oa = cs.get("odds_api") or {}
    nxt = should_run.next_run(now, upcoming)
    return {"odds_on": bool(oa.get("enabled")), "odds_spent_today": st.get("spent") if st.get("day") == now.date().isoformat() else 0,
            "odds_cap": oddsapi.env("ODDS_API_DAILY", "15"), "odds_left": oa.get("remaining"),
            "next_refresh": nxt.isoformat() if nxt else None, "collector_errors": (cs.get("errors") or [])[-3:]}


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
    # seasons the model learns from (older archived seasons are kept for research until a test says they help)
    cur_s = int(games["season"].max()) if len(games) else espn.season_of(today.isoformat())
    games = games[games["season"] >= cur_s - MODEL_HIST].reset_index(drop=True)
    players = load_players()
    players = players[players["game_id"].astype(str).isin(set(games["game_id"].astype(str)))].reset_index(drop=True)
    upcoming = [g for g in (read_json(STATE / "upcoming.json", []) or [])]
    inj_raw = read_json(STATE / "injuries.json", {}) or {}
    injuries = inj_raw.get("teams", {}) or {}
    from . import injury_log
    if collect_data and not demo:
        injury_log.update(upcoming, injuries, now)
    inj_cal = injury_log.calibrate(players, games)
    from model import rest
    next_day = {}
    for g in sorted(upcoming, key=lambda x: x["date"]):
        for t in (g["home"], g["away"]):
            next_day.setdefault(t, g["day"])
    injuries = injury_log.apply(injuries, inj_cal, next_day)
    meta_logos = read_json(STATE / "teams_meta.json", {}) or {}
    tuned = read_json(ROOT / "model" / "tuned.json", {}) or {}
    analyst = (read_json(OVR / "analyst.json", {}) or {}).get("games", {})

    cur = espn.season_of(today.isoformat())
    stints = load_stints(min_season=cur_s - 1) if engine.SRAPM_MODE != "off" else None
    c = engine.build_context(games, players, upcoming, tuned, stints=stints)
    rest_table = rest.measure(games, players, c.ctxs)
    rts = engine.fit_all(games, today.isoformat(), c.tuned)
    season_start = games[games["season"] == cur]["day"].min() if (games["season"] == cur).any() else today.isoformat()
    prev_rows = [r[:5] for r in c.rows if r[5] < season_start]
    eff_prev = effects.estimate(prev_rows, c.tuned["lam_effects"]) if len(prev_rows) >= 200 else c.eff
    stack_prev = engine.fit_stack([r for r in c.rows_raw if r[5] < season_start], c.lfeat)
    eff_table = c.eff.table()
    tr = c.tracker

    # ------------------------------------------------------------ players
    raw_notes = {**((read_json(STATE / "demo_player_notes.json", {}) or {}) if demo else {}),
                 **((read_json(OVR / "players.json", {}) or {}).get("players", {}) or {})}
    pt, pe, pdisp, plogs, ptrack, byg = PE.walk(c, players, raw_notes, cur)
    by_name = {(q["name"] or "").lower(): pid for pid, q in pt.p.items()}
    notes = {}
    for k, v in raw_notes.items():
        pid = k if k in pt.p else by_name.get(str(k).lower())
        if pid:
            notes[pid] = v
    if notes != raw_notes:
        pt, pe, pdisp, plogs, ptrack, byg = PE.walk(c, players, notes, cur)
    calib = parlay.fit_prop_calibration(plogs, byg, pdisp)
    qshares = extras.quarter_shares(games)
    adv = extras.advanced(games, cur)
    if not any(adv.values()):
        adv = extras.advanced(games, cur - 1)

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
               "base": {k: (v if isinstance(v, bool) else r1(v, 3 if k == "win_home" else 1)) for k, v in est["base"].items()},
               "physical": {k: r1(v, 2) for k, v in est["physical"].items()},
               "mind": {k: r1(v, 2) for k, v in est["mind"].items()},
               "win_home_nomind": r1(est["win_home_nomind"], 3), "margin_nomind": r1(est["margin_nomind"]),
               "win_home_model": r1(est.get("win_home_model"), 3), "win_home_market": r1(est.get("win_home_market"), 3),
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
            "quarters": extras.quarters(est, qshares, h, a),
            "h2h": extras.h2h(c.games[c.games["day"] < g["day"]], h, a),
        }
        return payload

    def card(p, result=None, live=None):
        e = p["est"]
        tags = []
        for side in ("home", "away"):
            for x in p["sides"][side]["mind"][:2]:
                if abs(x["pts"]) >= 0.25 or x["evidence"] in ("strong", "moderate"):
                    tags.append({"team": p[side]["abbr"], "label": x["label"], "pts": x["pts"], "ev": x["evidence"]})
        c_ = {"id": p["id"], "tip": p["tip"], "day": p["day"], "stype": p["stype"], "kind": p["kind"],
              "home": p["home"]["abbr"], "away": p["away"]["abbr"],
              "home_rec": p["home"]["record"], "away_rec": p["away"]["record"],
              "win_home": e["win_home"], "margin": e["margin"], "total": e["total"], "mind": e["mind"]["margin"],
              "tags": tags[:3], "tv": p["national_tv"], "story": card_story(p)}
        if result:
            c_.update(result)
        if live:
            c_["live"] = live
        return c_

    # ------------------------------------------------------------ upcoming
    PRED.mkdir(parents=True, exist_ok=True)
    # the Pinnacle blend switches itself on only once frozen games show it beats the model alone
    blend_items = []
    for path in sorted(PRED.glob("*/*.json")):
        pj = read_json(path) or {}
        e = ((pj.get("payload") or {}).get("est") or {})
        gg = c.meta.get(pj.get("game_id"))
        if pj.get("frozen") and gg is not None and e.get("win_home_model") is not None and e.get("win_home_market") is not None:
            blend_items.append((e["win_home_model"], e["win_home_market"], 1.0 if gg["home_pts"] > gg["away_pts"] else 0.0))
    def _bl(a, b):
        lo = lambda x: math.log(max(x, 1e-6) / max(1 - x, 1e-6))
        return 1 / (1 + math.exp(-(BLEND_W * lo(a) + (1 - BLEND_W) * lo(b))))
    blend_stats = None
    if blend_items:
        n_ = len(blend_items)
        blend_stats = {"n": n_, "brier_model": round(sum((a - y) ** 2 for a, b, y in blend_items) / n_, 4),
                       "brier_market": round(sum((b - y) ** 2 for a, b, y in blend_items) / n_, 4),
                       "brier_blend": round(sum((_bl(a, b) - y) ** 2 for a, b, y in blend_items) / n_, 4)}
    # Tested on 1,368 past games with Pinnacle's price 30 min before the day's first tip (2025-26 and this season):
    # 40% model / 60% market (log-odds) beat both alone on Brier and log loss and kept the model's extra winners.
    # It stays on unless this season's frozen games show the blend doing worse than the model alone.
    market_blend_on = not (blend_stats and blend_stats["n"] >= 150 and blend_stats["brier_blend"] > blend_stats["brier_model"])
    trc = tr.clone()
    upcoming_payloads = {}
    seen = set()
    for g in sorted(upcoming, key=lambda x: (x["date"], x["game_id"])):
        gid = str(g["game_id"])
        ahead = (date.fromisoformat(g["day"]) - today).days
        news = ahead <= 3
        ctx = trc.pre_game(g, injuries=injuries if news else None)
        for side in ("home", "away"):
            ctx[side]["luck"] = round(c.style.team_luck(g[side]), 3)
        ctx["refs_total"] = round(c.officials.crew(g.get("refs")), 3)
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
        em = engine.predict(c, g, ctx, rts)["base"]["margin"]  # results-only margin: blowout risk for minutes
        proj_players = PE.project_game(pt, pe, pdisp, g, ctx, injuries, notes, news, exp_margin=em)
        lf = None
        # far from tip-off, key players not on the injury report may still sit (measured rates)
        hours = (tip - now).total_seconds() / 3600
        if hours > rest.NEWS_HOURS and rest_table:
            for side in ("home", "away"):
                p_sit = rest.chance_sits(rest_table, ctx[side]["b2b"], int(g["day"][5:7]), int(g.get("stype") or 2) == 3)
                for x in proj_players.get(side, []):
                    if not x.get("out") and not x.get("status") and x["min"] >= rest.KEY_MIN and p_sit:
                        x["sit"] = round(p_sit, 3)
        em_ = lambda x: x["min"] * x.get("p_play", 1.0) * (1 - x.get("sit", 0.0))  # expected minutes
        sh_ = c.lineup.strength([(x["id"], em_(x)) for x in proj_players.get("home", []) if not x.get("out")])
        sa_ = c.lineup.strength([(x["id"], em_(x)) for x in proj_players.get("away", []) if not x.get("out")])
        rh_ = c.rapm.strength([(x["id"], em_(x)) for x in proj_players.get("home", []) if not x.get("out")])
        ra_ = c.rapm.strength([(x["id"], em_(x)) for x in proj_players.get("away", []) if not x.get("out")])
        if sh_ and sa_ and rh_ is not None and ra_ is not None:
            sg_ = None
            if c.srapm is not None:
                s1 = c.srapm.strength([(x["id"], em_(x)) for x in proj_players.get("home", []) if not x.get("out")])
                s2 = c.srapm.strength([(x["id"], em_(x)) for x in proj_players.get("away", []) if not x.get("out")])
                sg_ = None if s1 is None or s2 is None else s1 - s2
            lf = engine.player_features((sh_[0] - sa_[0], sh_[1] - sa_[1], rh_ - ra_), sg_)
        est = engine.predict(c, g, ctx, rts, lineup_feat=lf)
        pin = ((g.get("odds_books") or {}).get("pinnacle") or {})
        p_mkt = parlay.novig(pin.get("ml_home"), pin.get("ml_away"))
        est["win_home_model"] = est["win_home"]
        est["win_home_market"] = p_mkt
        if p_mkt is not None and market_blend_on:
            lo = lambda x: math.log(max(x, 1e-6) / max(1 - x, 1e-6))
            est["win_home"] = 1 / (1 + math.exp(-(BLEND_W * lo(est["win_home"]) + (1 - BLEND_W) * lo(p_mkt))))
        payload = game_payload(g, ctx, est, "estimate", {t: injuries.get(t, []) for t in (g["home"], g["away"])} if news else None)
        payload["news"] = news
        payload["refs"] = g.get("refs")
        payload["style"] = {side: {"pace": c.style.pace_word(g[side])} for side in ("home", "away")}
        payload["made_at"] = now.isoformat()
        payload["players"] = proj_players
        if gid in analyst:
            payload["analyst"] = analyst[gid]
        payload["odds"] = g.get("odds")
        payload["odds_books"] = g.get("odds_books")
        odds_first = (old or {}).get("odds_first") or g.get("odds")
        books_first = (old or {}).get("books_first") or g.get("odds_books")
        write_json(path, {"game_id": gid, "tip": g["date"], "made_at": now.isoformat(), "frozen": False,
                          "home": g["home"], "away": g["away"], "season": int(g["season"]), "payload": payload,
                          "odds_first": odds_first, "odds_last": g.get("odds"),
                          "books_first": books_first, "books_last": g.get("odds_books"),
                          "first_made_at": (old or {}).get("first_made_at") or now.isoformat()})
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
            est = engine.predict(c, g, c.ctxs[gid], {}, eff=eff_prev, base_override=c.base[gid],
                                 lineup_feat=c.lfeat.get(gid), stack=stack_prev)
            payload = game_payload(g, c.ctxs[gid], est, "check")
        checks.append((g, payload))
        if True:  # every game of the season gets its page; only the last three weeks get cards
            if not payload.get("players"):
                pl = {}
                for side, ab in (("home", g["home"]), ("away", g["away"])):
                    rows = sorted([r for r in byg.get(gid, {}).get(ab, []) if r["min"] > 0], key=lambda r: -r["min"])
                    pl[side] = [{"id": r["player_id"], "name": r["name"], "pos": r["pos"], "min": int(r["min"]), "pts": int(r["pts"]),
                                 "reb": int(r["reb"]), "ast": int(r["ast"]), "tpm": None if r["tpm"] is None else int(r["tpm"]),
                                 "stl": None if r["stl"] is None else int(r["stl"]), "blk": None if r["blk"] is None else int(r["blk"]),
                                 "tov": None if r["tov"] is None else int(r["tov"]), "pm": None if r["pm"] is None else int(r["pm"]),
                                 "proj": plogs.get((gid, r["player_id"]))} for r in rows]
                payload = {**payload, "players_actual": pl}
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
    (SITE / "player").mkdir(parents=True, exist_ok=True)

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
        recent = g["day"] >= recent_from
        out = dict(payload)
        out["state"] = "post"
        out["result"] = result_block(g)
        hm = out["result"]["home_pts"] - out["result"]["away_pts"]
        e = payload["est"]
        out["scored"] = {"hit": (e["win_home"] >= 0.5) == (hm > 0), "err_margin": r1(hm - e["margin"]),
                         "err_total": r1(out["result"]["home_pts"] + out["result"]["away_pts"] - e["total"])}
        write_json(SITE / "game" / f"{gid}.json", out)
        if recent:
            cards_res.append(card(payload, result={"home_pts": out["result"]["home_pts"], "away_pts": out["result"]["away_pts"],
                                               "ot": out["result"]["ot"], "hit": out["scored"]["hit"]}))
    cards_up.sort(key=lambda x: (x["tip"] or "", x["id"]))
    cards_res.sort(key=lambda x: (x["day"], x["id"]), reverse=True)

    # player model against prop lines: real archived lines, and the season-average proxy
    from .oddsapi import first_last_props, norm_name
    frozen_proj, actual_n = {}, {}
    for path in sorted(PRED.glob("*/*.json")):
        pj = read_json(path) or {}
        if not pj.get("frozen"):
            continue
        for side_rows in ((pj.get("payload") or {}).get("players") or {}).values():
            for r in side_rows:
                if not r.get("out"):
                    frozen_proj[(pj["game_id"], norm_name(r["name"]))] = {k: r.get(k) for k in ("pts", "reb", "ast", "tpm", "pra")}
    for gid, teams_ in byg.items():
        for rows in teams_.values():
            for r in rows:
                if r["min"] > 0:
                    actual_n[(gid, norm_name(r["name"]))] = {"pts": r["pts"], "reb": r["reb"], "ast": r["ast"], "tpm": r["tpm"],
                                                              "pra": r["pts"] + r["reb"] + r["ast"]}
    lines_test = {"real": prop_test.real_lines(first_last_props(), frozen_proj, actual_n, pdisp, calib),
                  "proxy": prop_test.proxy_lines(plogs, byg, [str(x) for x in c.games.loc[c.games["season"] == cur, "game_id"]],
                                                 pdisp, calib)}
    blend = (lines_test["real"] or {}).get("blend") or {}
    if blend.get("measured"):
        parlay.MARKET_W.update(w=blend["w"], measured=True)

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
        "upgrade": engine.lineup_test(c, cur), "market_blend": {**(blend_stats or {}), "on": market_blend_on},
        "players": {"track": ptrack, "factors": PM.effects_table(pe), "dispersion": {k: round(v, 2) for k, v in pdisp.items()},
                    "lines_test": lines_test, "minutes_model": pt.mm.table(), "injury_status": inj_cal,
                    "rest": rest_table},
        "effects_games": c.eff.n, "sd_margin": r1(c.eff.sd_margin), "sd_total": r1(c.eff.sd_total)})

    # ------------------------------------------------------------ the daily parlay
    PAR = ROOT / "data" / "parlays"
    PAR.mkdir(parents=True, exist_ok=True)
    days_up = sorted({g["day"] for g, _, _ in upcoming_payloads.values()})
    today_parlay = None
    if days_up:
        sday = days_up[0]
        path = PAR / f"{sday}.json"
        old = read_json(path)
        slate = [(g, pay) for g, pay, st in upcoming_payloads.values() if g["day"] == sday]
        first_tip = min(datetime.fromisoformat(g["date"].replace("Z", "+00:00")) for g, _ in slate)
        if old and (old.get("frozen") or now >= first_tip):
            if not old.get("frozen"):
                # freeze: closing-line value of every published leg = last market view before tip vs first
                fs, ls = old.get("first_seen", {}), old.get("last_seen", {})
                for l in [l for pr in old.get("parlays", []) for l in pr["legs"]] + old.get("board", []) + old.get("singles", []):
                    l["clv"] = parlay.clv(l, fs.get(l["id"]), ls.get(l["id"]))
                old["frozen"] = True
                old.setdefault("locked", True)
                old["locked"] = True
                write_json(path, old)
            today_parlay = old
        else:
            pre = [(g, pay) for g, pay in slate if g.get("state") != "in"]
            pc_ = players[players["game_id"].astype(str).isin(set(c.games.loc[c.games["season"] == cur, "game_id"].astype(str)))
                          & (players["min"].fillna(0) > 0)].copy()
            avg = {}
            if len(pc_):
                pc_["pra"] = pc_["pts"] + pc_["reb"] + pc_["ast"]
                for pid, d_ in pc_.groupby(pc_["player_id"].astype(str)):
                    avg[pid] = {"gp": len(d_), **{k: float(d_[k].mean()) for k in ("pts", "reb", "ast", "tpm", "pra")}}
            from . import oddsapi
            real = oddsapi.latest_props()
            # winners at the betting book's price (Winamax); handicap and total at the sharp book's main line and price
            # (Pinnacle) when the betting book's own lines are not in the feed. Tickets use the book-only mode for a
            # game only when its full menu came through.
            pre2 = []
            for g, pay in pre:
                g = dict(g)
                books_ = g.get("odds_books") or {}
                if g.get("odds"):
                    od = dict(g["odds"])
                    for bk in ("pinnacle",) + tuple(b for b in books_ if b != "pinnacle"):
                        b = books_.get(bk) or {}
                        if od.get("spread_price_home") is None and b.get("spread_price_home"):
                            od.update({"spread_home": b["spread_home"], "spread_price_home": b["spread_price_home"],
                                       "spread_price_away": b.get("spread_price_away"), "spread_book": bk})
                        if od.get("over") is None and b.get("over"):
                            od.update({"total": b["total"], "over": b["over"], "under": b.get("under"), "total_book": bk})
                    g["odds"] = od
                pre2.append((g, pay))
            full_menu = any((g.get("offers") or {}).get("offers") for g, _ in pre2)
            bet_book = oddsapi.env("ODDS_API_BET_BOOK", "winamax_fr") if (oddsapi.key() and full_menu) else None
            built, cands = parlay.build(pre2, pdisp, calib, avg, real_props=real, book_only=bet_book)
            from model import story
            story.annotate(built["parlays"], built.get("singles"), pre2)  # why each ticket, in plain words
            bl, lifts = parlay.board(cands)
            odds_by_game = {str(g["game_id"]): g.get("odds") for g, _ in slate}
            first_seen = dict((old or {}).get("first_seen", {}))
            last_seen = {}
            for l in [l for pr in built["parlays"] for l in pr["legs"]] + bl + built.get("singles", []):
                v = parlay.market_view(l, odds_by_game.get(l["game"]), real)
                if v:
                    v = {**v, "at": now.isoformat()}
                    last_seen[l["id"]] = v
                    first_seen.setdefault(l["id"], v)
                    l["open"] = first_seen[l["id"]]
            today_parlay = {"day": sday, "made_at": now.isoformat(), "first_tip": first_tip.isoformat(), "frozen": False,
                            **built, "board": bl, "lifts": lifts, "first_seen": first_seen, "last_seen": last_seen,
                            "value": parlay.value_board(pre2),
                            "odds_source": sorted({(o or {}).get("provider") or "none" for o in odds_by_game.values()})}
            # The day's tickets are chosen once, LOCK_HOURS before the first tip-off (after the main injury
            # reports), then never change. Until then they are not shown.
            lock_at = first_tip - timedelta(hours=LOCK_HOURS)
            today_parlay["lock_at"] = lock_at.isoformat()
            if old and old.get("locked"):
                for k in ("parlays", "singles", "locked_at", "games", "candidates", "eligible", "book", "not_on_book"):
                    if k in old:
                        today_parlay[k] = old[k]
                today_parlay["locked"] = True
                # news after the lock: flag legs whose player is now out or doubtful (the ticket itself stays)
                now_pl = {}
                for g_, pay_ in slate:
                    for side_ in ("home", "away"):
                        for x in (pay_.get("players") or {}).get(side_, []):
                            now_pl[str(x["id"])] = x
                for pr in today_parlay["parlays"]:
                    for l in pr["legs"]:
                        x = now_pl.get(str(l.get("player") or ""))
                        l.pop("alert", None)
                        if x is not None and (x.get("out") or x.get("status")):
                            l["alert"] = f"{x.get('status') or 'Out'} since the picks were locked: if he does not play, Winamax voids this leg"
            elif now >= lock_at:
                today_parlay["locked"] = True
                today_parlay["locked_at"] = now.isoformat()
            else:
                today_parlay["locked"] = False
            write_json(path, today_parlay)
    # score finished slates
    fin_rows = {str(k): v for k, v in c.meta.items()}
    history = []
    for path in sorted(PAR.glob("*.json")):
        pj = read_json(path)
        if not pj or not pj.get("parlays"):
            continue
        if not pj.get("scored"):
            gids = {l["game"] for pr in pj["parlays"] for l in pr["legs"]} | {l["game"] for l in pj.get("singles", [])}
            if gids and all(gid in fin_rows for gid in gids):
                for pr in pj["parlays"]:
                    for l in pr["legs"] + ([] if pr is not pj["parlays"][0] else []):
                        pass
                def sc(l):
                    rows = {r["player_id"]: r for team in byg.get(l["game"], {}).values() for r in team}
                    l["result"] = parlay.score_leg(l, fin_rows.get(l["game"]), rows)
                for pr in pj["parlays"]:
                    for l in pr["legs"]:
                        sc(l)
                    live_legs = [l for l in pr["legs"] if l["result"] != "void"]
                    pr["result"] = "hit" if live_legs and all(l["result"] == "hit" for l in live_legs) else "miss"
                for l in pj.get("singles", []) + pj.get("board", []):
                    if l["game"] in fin_rows:
                        sc(l)
                for v in pj.get("value", []):  # Winamax vs Pinnacle: result, and Pinnacle's closing view
                    gr = fin_rows.get(v["game"])
                    if gr is None:
                        continue
                    hw = gr["home_pts"] > gr["away_pts"]
                    v["won"] = bool(hw if v["side"] == "home" else not hw)
                    pf = read_json(PRED / str(gr["season"]) / f"{v['game']}.json") or {}
                    pc = ((pf.get("books_last") or {}).get("pinnacle") or {})
                    fc = parlay.novig(pc.get("ml_home"), pc.get("ml_away"))
                    if fc is not None:
                        fc = fc if v["side"] == "home" else 1 - fc
                        v["close_fair_p"] = round(fc, 4)
                        v["clv"] = round(v["price"] * fc - 1, 4)  # the Winamax price vs Pinnacle's closing fair price
                pj["scored"] = True
                pj["frozen"] = True
                write_json(path, pj)
        if pj.get("scored"):
            history.append(pj)
    vb = [v for h_ in history for v in h_.get("value", []) if v.get("value") and "won" in v]
    value_record = {"n": len(vb), "won": sum(v["won"] for v in vb),
                    "profit": round(sum((v["price"] - 1) if v["won"] else -1 for v in vb), 2),
                    "expected_won": round(sum(v["fair_p"] for v in vb if v.get("fair_p")), 1),
                    "clv_n": sum(1 for v in vb if v.get("clv") is not None),
                    "clv_beat": sum(1 for v in vb if (v.get("clv") or 0) > 0),
                    "clv_avg": round(sum(v["clv"] for v in vb if v.get("clv") is not None) / max(1, sum(1 for v in vb if v.get("clv") is not None)), 4)} if vb else None
    rec = {}
    for pr_name in ("Value 2", "Core 3", "Same-game 3", "The daily 6"):
        items = [pr for h_ in history for pr in h_["parlays"] if pr["name"] == pr_name]
        if items:
            legs = [l for pr in items for l in pr["legs"] if l.get("result") in ("hit", "miss")]
            rec[pr_name] = {"n": len(items), "hits": sum(pr.get("result") == "hit" for pr in items),
                            "expected": round(sum(pr["p"] for pr in items), 2),
                            "legs": len(legs), "leg_hits": sum(l["result"] == "hit" for l in legs),
                            "leg_expected": round(sum(l["p"] for l in legs), 1)}
    clv_legs = [l["clv"] for h_ in history for l in [l for pr in h_["parlays"] for l in pr["legs"]] + h_.get("singles", [])
                if l.get("clv")]
    clv_all = [l["clv"] for path in sorted(PAR.glob("*.json")) for pj in [read_json(path) or {}] if pj.get("frozen")
               for l in [l for pr in pj.get("parlays", []) for l in pr["legs"]] + pj.get("board", []) + pj.get("singles", []) if l.get("clv")]

    def clv_summary(items):
        pp = [x["p"] for x in items if "p" in x]
        pts = [x["pts"] for x in items if "pts" in x]
        moved = [v for v in pp + pts if v != 0]
        return {"n": len(items), "beat": sum(v > 0 for v in moved), "moved": len(moved),
                "avg_p": round(sum(pp) / len(pp), 4) if pp else None, "avg_pts": round(sum(pts) / len(pts), 2) if pts else None}
    # the model against the market's movement, every game with an opening and closing price
    mvm = []
    for path in sorted(PRED.glob("*/*.json")):
        pj = read_json(path) or {}
        o1, o2 = pj.get("odds_first") or {}, pj.get("odds_last") or {}
        f1, f2 = parlay.novig(o1.get("ml_home"), o1.get("ml_away")), parlay.novig(o2.get("ml_home"), o2.get("ml_away"))
        est = (pj.get("payload") or {}).get("est") or {}
        if f1 is None or f2 is None or est.get("win_home") is None or not pj.get("frozen"):
            continue
        lean = est["win_home"] - f1
        if abs(lean) >= 0.02 and abs(f2 - f1) >= 0.002:
            mvm.append({"lean": round(lean, 3), "move": round(f2 - f1, 4), "with": (lean > 0) == (f2 > f1)})
    model_clv = {"n": len(mvm), "with": sum(x["with"] for x in mvm),
                 "avg_move_our_way": round(sum((x["move"] if x["lean"] > 0 else -x["move"]) for x in mvm) / len(mvm), 4) if mvm else None}
    leg_results, leg_close = {}, {}
    for path in sorted(PAR.glob("*.json"))[-45:]:
        pj = read_json(path) or {}
        for l in [l for pr in pj.get("parlays", []) for l in pr["legs"]] + pj.get("board", []) + pj.get("singles", []):
            if l.get("result"):
                leg_results[l["id"]] = l["result"]
        if pj.get("frozen"):
            leg_close.update(pj.get("last_seen", {}))
            # winners: Pinnacle's closing fair chance, the sharpest yardstick for any price you took
            for l in [l for pr in pj.get("parlays", []) for l in pr["legs"]] + pj.get("board", []) + pj.get("singles", []):
                if l.get("kind") != "ml" or l["id"] not in leg_close:
                    continue
                gr = c.meta.get(l["game"])
                pf = read_json(PRED / str(gr["season"]) / f"{l['game']}.json") if gr is not None else None
                pc = (((pf or {}).get("books_last") or {}).get("pinnacle") or {})
                fh = parlay.novig(pc.get("ml_home"), pc.get("ml_away"))
                if fh is not None:
                    leg_close[l["id"]] = {**leg_close[l["id"]], "pin_fair": round(fh if l.get("team") == gr["home"] else 1 - fh, 4)}
    write_json(SITE / "parlay.json", {"today": today_parlay, "calibration": calib, "record": rec,
                                      "leg_results": leg_results, "leg_close": leg_close,
                                      "odds_api": (read_json(STATE / "collect.json", {}) or {}).get("odds_api"),
                                      "clv": {"tickets": clv_summary(clv_legs), "all_legs": clv_summary(clv_all), "model": model_clv},
                                      "value_record": value_record,
                                      "history": [{"day": h_["day"], "parlays": [{"name": pr["name"], "p": pr["p"], "fair": pr["fair"],
                                                                                   "result": pr.get("result"),
                                                                                   "legs": [{"desc": l["desc"], "p": l["p"], "result": l.get("result"),
                                                                                             "kind": l["kind"], "team": l.get("team"), "clv": l.get("clv")}
                                                                                            for l in pr["legs"]]}
                                                                                  for pr in h_["parlays"]]} for h_ in history[-30:][::-1]]})

    # players: next-game projection per player, pages, index
    next_proj = {}
    team_next = {}
    for gid, (g, payload, state) in sorted(upcoming_payloads.items(), key=lambda kv: kv[1][0]["date"]):
        if state == "in":
            continue
        for side, ab, opp in (("home", g["home"], g["away"]), ("away", g["away"], g["home"])):
            team_next.setdefault(ab, []).append((payload["gauge"][side], payload[side]["missing"] or 0.0))
            for pl in (payload.get("players") or {}).get(side, []):
                if pl["id"] in next_proj:
                    continue
                next_proj[pl["id"]] = {"game": gid, "tip": g["date"], "opp": opp, "home": side == "home", "out": pl.get("out"),
                                       "status": pl.get("status"), "detail": pl.get("detail"),
                                       "proj": {k: pl.get(k) for k in ("min", "pts", "reb", "ast", "tpm", "stl", "blk", "tov", "pra")},
                                       "lines": pl.get("lines"), "spots": pl.get("spots", [])}
    pindex, ppages = player_pages.build(players, games, cur, plogs, next_proj, pt, notes, c.ctxs)
    (SITE / "player").mkdir(parents=True, exist_ok=True)
    for pid, page in ppages.items():
        write_json(SITE / "player" / f"{pid}.json", page)
    write_json(SITE / "players.json", pindex)

    # playoff chances from the rest of the regular season
    rest = [(g["home"], g["away"]) for g in upcoming if int(g.get("stype", 2)) == 2 and g.get("state") != "post"]
    rest += [(g["home"], g["away"]) for g in (read_json(STATE / "season_rest.json", []) or [])]
    wl = {ab: list(tr.wl[cur][ab]) for ab in TEAMS}
    odds = extras.playoff_odds(wl, rest, net, rt.home if rt else 2.5, c.eff.sd_margin) if sum(map(sum, wl.values())) else {}
    for conf in standings:
        for row in standings[conf]:
            row["odds"] = odds.get(row["abbr"])

    # mind ranking
    mind_rows = []
    lookup_rows = {r["abbr"]: r for conf in standings for r in standings[conf]}
    for ab in TEAMS:
        f = tr.side({"day": today.isoformat(), "season": cur, "stype": 2, "home": ab, "game_id": "x"}, ab, ab, True)
        nx = team_next.get(ab, [])[:3]
        edge = sum(x[0] for x in nx) / len(nx) if nx else 0.0
        miss = nx[0][1] if nx else 0.0
        score, cat, why = extras.mood(f, c.eff, edge, lookup_rows.get(ab, {}).get("l10"), miss)
        mind_rows.append({"abbr": ab, "score": score, "cat": cat, "why": why, "streak": f["streak"], "confidence": f["confidence"],
                          "l10": lookup_rows.get(ab, {}).get("l10"), "record": f["record"], "edge": round(edge, 2),
                          "stakes": f["stakes"], "missing": round(miss, 3), "form": f["form"][-10:]})
    mind_rows.sort(key=lambda x: -x["score"])
    for i, r in enumerate(mind_rows):
        r["rank"] = i + 1
    write_json(SITE / "mind.json", mind_rows)
    mood_of = {r["abbr"]: r for r in mind_rows}

    # teams
    team_list = []
    for ab, t in teams.items():
        f = tr.side({"day": today.isoformat(), "season": cur, "stype": 2, "home": ab, "game_id": "x"}, ab, ab, True)
        team_list.append({"abbr": ab, "name": t["name"], "short": t["short"], "conf": t["conf"], "div": t["div"],
                          "color": t["color"], "alt": t["alt"], "logo": t["logo"], "record": f["record"],
                          "seed": seed_of.get(ab), "net": r1(net[ab]), "net_rank": net_rank[ab]})
        tp = team_page(ab, t, f, tr, c, cur, net, off, dfn, net_rank, off_rank, def_rank,
                       seed_of, cards_up, cards_res, injuries, players, eff_table)
        tp["advanced"] = adv.get(ab)
        tp["odds"] = odds.get(ab)
        tp["mood"] = mood_of.get(ab)
        tp["players"] = [x for x in pindex if x["team"] == ab]
        tp["h2h_season"] = []
        write_json(SITE / "team" / f"{ab}.json", tp)
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
                                    "tuned": c.tuned, "status": status_info(now, upcoming, cs)})
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
