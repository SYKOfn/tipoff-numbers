"""Walk every stored player-game once: pre-game projections (to measure the player effects and keep a
track record), then project every rotation player for upcoming games."""
import math
from collections import defaultdict

from . import players as P
from pipeline.store import PLAYER_STATS

STORY = {
    "former_team": "Faces the {opp}, a former team.",
    "returning": "Among his first games back after a long absence.",
    "contract_year": "Playing for his next contract (final year).",
}


def rows_by_game(df):
    out = defaultdict(lambda: defaultdict(list))
    if df is None or not len(df):
        return out
    cols = ["game_id", "team", "player_id", "name", "pos", "jersey", "starter", "dnp_reason"] + PLAYER_STATS
    cols = [c for c in cols if c in df.columns]
    for r in df[cols].to_dict("records"):
        for k in PLAYER_STATS:
            v = r.get(k)
            missing = v is None or (isinstance(v, float) and math.isnan(v))
            # minutes/points/rebounds/assists are always there; the rest was not stored in the first runs:
            # keep those as None so they are never read as zeros
            r[k] = (0.0 if k in ("min", "pts", "reb", "ast") else None) if missing else float(v)
        r["player_id"] = str(r["player_id"])
        out[str(r["game_id"])][r["team"]].append(r)
    return out


MIN_TEAM = 240.0


MAX_MIN = 40.0  # no regular-season projection above this: stars rarely play more, even with teammates out


def capped_factors(mins, k, cap=MAX_MIN, caps=None):
    """Per-player scale factors bringing the team towards its 240 minutes with factor k, never lifting a player
    above `cap`; minutes a capped player cannot take go to the others (two passes)."""
    f = [k] * len(mins)
    if k <= 1.0:
        return f
    target = sum(m * k for m in mins)
    capped = set()
    for _ in range(3):
        cap_of = lambda i: min(cap, (caps or {}).get(i, cap))
        new = {i for i, m in enumerate(mins) if i not in capped and m * f[i] > cap_of(i) + 1e-9}
        if not new:
            break
        capped |= new
        for i in capped:
            f[i] = min(max(1.0, cap / mins[i]), max(cap_of(i) / mins[i], 0.0)) if mins[i] > 0 else 1.0
        free = [i for i in range(len(mins)) if i not in capped]
        base = sum(mins[i] for i in free)
        if not free or base <= 0:
            break
        kk = min((target - sum(mins[i] * f[i] for i in capped)) / base, 1.15)
        for i in free:
            f[i] = kk
    return f


def team_minutes_scale(total, lo=0.85, hi=1.15):
    """Factor that brings a team's projected minutes to the 240 available."""
    return max(lo, min(hi, MIN_TEAM / total)) if total > 0 else 1.0


def walk(c, players_df, notes, cur, use_mm=True, ev=None, opp_mode="team", norm=True):
    """ev: optional dict filled with out-of-sample errors per season and stat (for model tests)."""
    pt = P.PlayerTracker()
    pt.use_mm = use_mm
    pt.opp_mode = opp_mode
    byg = rows_by_game(players_df)
    rows_eff, logs = [], {}
    sq = defaultdict(float)
    sp = defaultdict(float)
    acc = defaultdict(float)
    season_sum = defaultdict(lambda: [0.0, 0])
    for g in c.games.to_dict("records"):
        gid = str(g["game_id"])
        rows = byg.get(gid)
        if not rows:
            pt.post_game(g, {})
            continue
        ctx = c.ctxs.get(gid)
        b = c.base.get(gid)
        em = (b[0] - b[1]) if b else None
        done, mrows, wo_upd, dsp_upd = [], [], [], []
        for team, opp, side in ((g["home"], g["away"], "home"), (g["away"], g["home"], "away")):
            trs = rows.get(team, [])
            played = {r["player_id"] for r in trs if r["min"] > 0}
            absent = set(pt.rotation(team)) - played
            team_proj = []
            for r in trs:
                pid = r["player_id"]
                if r["min"] <= 0 or pid not in pt.p or pt.p[pid]["gp"] < 3:
                    continue
                if ev is not None and "pg" in ev:  # research: the inputs each projection saw, recorded before it
                    q_ = pt.p[pid]
                    ev.setdefault("pgx", {})[(gid, pid)] = {
                        "of": {st_: pt.opp_raw(opp, st_) for st_ in ("pts", "reb", "ast", "tpm")},
                        "back_left": q_["back_left"], "gap": pt.team_games[team] - q_["last_team_game"].get(team, pt.team_games[team]),
                        "gp": q_["gp"], "exp_tp": (b[0] if side == "home" else b[1]) if b else None,
                        "exp_op": (b[1] if side == "home" else b[0]) if b else None, "pos": q_["pos"]}
                proj, x = pt.project(pid, team, opp, side == "home", ctx[side]["b2b"] if ctx else 0, absent,
                                     ctx[side]["missing"] if ctx else 0.0, notes.get(pid), exp_margin=em)
                if ev is not None and "pgx" in ev:
                    ev["pgx"][(gid, pid)]["ret"] = x["returning"]
                team_proj.append((r, pid, proj, x, pt.last_mf))
            if norm:  # scale the team's projected minutes to the 240 available (newcomers counted at 12)
                k = team_minutes_scale(sum(t[2]["min"] for t in team_proj) + 12.0 * (len(played) - len(team_proj)))
                fs = capped_factors([t[2]["min"] for t in team_proj], k)
                team_proj = [(r, pid, {kk: v * f_ for kk, v in proj.items()}, x, mf) for (r, pid, proj, x, mf), f_ in zip(team_proj, fs)]
            keys_out = pt.key_absent(team, absent)
            for r, pid, proj, x, mf in team_proj:
                mrows.append((mf, r["min"]))
                if keys_out:
                    wo_upd.append((pid, keys_out, r["pts"], proj["pts"], r["min"], proj["min"]))
                if ev is not None:
                    for st in ("min", "pts", "reb", "ast", "tpm", "pra"):
                        a = (r["pts"] + r["reb"] + r["ast"]) if st == "pra" else r[st]
                        if a is None:
                            continue
                        e = ev.setdefault((int(g["season"]), st), [0, 0.0, 0.0])
                        e[0] += 1
                        e[1] += abs(a - proj[st])
                        e[2] += (a - proj[st]) ** 2
                rows_eff.append((x, {st: (r[st] if st != "min" else r["min"], proj[st]) for st in P.EFFECT_STATS}))
                dsp_upd.append((pid, r, proj))
                if ev is not None:
                    ev.setdefault("rows", []).append(int(g["season"]))
                    if "pg" in ev:  # player-games with their out-of-sample projection (simulation research)
                        ev["pg"].append((int(g["season"]), gid, team, side, pid, int(r.get("starter") or 0),
                                         {st: r[st] for st in ("min", "pts", "reb", "ast", "tpm")},
                                         {st: proj[st] for st in ("min", "pts", "reb", "ast", "tpm")}))
                act_pra = r["pts"] + r["reb"] + r["ast"]
                for st in P.SHOW + ["pra"]:
                    a = act_pra if st == "pra" else r[st]
                    if a is None:
                        continue
                    sq[st] += (a - proj[st]) ** 2
                    sp[st] += proj[st]
                if int(g["season"]) == cur:
                    logs[(gid, pid)] = {k: round(v, 1) for k, v in proj.items() if k in ("min", "pts", "reb", "ast", "tpm", "pra")}
                    pt.dsp_log[(gid, pid)] = dict(pt.p[pid].get("dsp") or {})  # his own spread before the game
                    key = (cur, pid)
                    if season_sum[key][1] >= 1:
                        acc["n"] += 1
                        acc["mae"] += abs(r["pts"] - proj["pts"])
                        acc["mae_base"] += abs(r["pts"] - season_sum[key][0] / season_sum[key][1])
                done.append((pid, r["pts"], proj["pts"], opp))
        for team in (g["home"], g["away"]):
            for r in rows.get(team, []):
                if r["min"] > 0:
                    s = season_sum[(int(g["season"]), r["player_id"])]
                    s[0] += r["pts"]
                    s[1] += 1
        pt.post_game(g, rows)
        for pid, a, prj in dsp_upd:
            P.note_disp(pt.p[pid], a, prj)
        for f, y in mrows:
            pt.mm.add(f, y)
        for u in wo_upd:
            pt.note_without(*u)
        for pid, a, p, o in done:
            pt.note_result(pid, a, p, o)
    pe = P.estimate_effects(rows_eff)
    if ev is not None:
        ev["rows_eff"] = rows_eff
    disp = {st: (sq[st] / sp[st]) if sp[st] else 1.5 for st in sp}
    track = None
    if acc["n"]:
        track = {"n": int(acc["n"]), "mae_pts": round(acc["mae"] / acc["n"], 2), "mae_pts_base": round(acc["mae_base"] / acc["n"], 2)}
    return pt, pe, disp, logs, track, byg


def match_injury(pt, team, injured):
    """{pid: injury dict} for a team's injury list, matched by id, then by name."""
    out = {}
    by_name = {(q["name"] or "").lower(): pid for pid, q in pt.p.items() if q["team"] == team}
    for inj in injured or []:
        pid = str(inj.get("player_id") or "")
        if pid not in pt.p:
            pid = by_name.get((inj.get("name") or "").lower())
        if pid:
            out[pid] = inj
    return out


def project_game(pt, pe, disp, g, ctx, injuries, notes, news=True, exp_margin=None, signals=None):
    """signals: news facts for tonight by normalized player name (pipeline/news.py). Applied: "rest" (he sits) and
    "min_cap" (minutes limit; teammates absorb the rest). Others ("start", "bench", "returning") are shown and
    logged, and only change projections once their effect has been measured."""
    from pipeline.oddsapi import norm_name
    sig_of = lambda name: (signals or {}).get(norm_name(name or ""))
    out = {}
    for team, opp, side in ((g["home"], g["away"], "home"), (g["away"], g["home"], "away")):
        rot = pt.rotation(team)
        inj = match_injury(pt, team, (injuries or {}).get(team)) if news else {}
        # out when he is more likely to miss than to play (measured rates once the injury log has enough cases)
        absent = {pid for pid, i in inj.items() if (i.get("weight") or 0) >= 0.5}
        rested = {pid for pid in rot if (sig_of(pt.p[pid]["name"]) or {}).get("rest")}
        absent |= rested
        five = set(((g.get("starters") or {}).get(team)) or [])
        if five:  # starting five posted: a starter plays whatever the report said
            absent -= five
            inj = {k: {**v, "weight": 0.0, "play": 1.0, "min_ratio": None} if k in five else v for k, v in inj.items()}
        lst = []
        for pid in sorted(rot, key=lambda k: -rot[k]):
            q = pt.p[pid]
            status = inj.get(pid)
            sg = sig_of(q["name"]) or {}
            if pid in absent and pid not in five:
                st_ = status or {}
                lst.append({"id": pid, "name": q["name"], "pos": q["pos"], "out": True,
                            "status": st_.get("status") or ("Resting (news)" if pid in rested else None),
                            "detail": st_.get("detail") or (sg.get("quote") if pid in rested else None), "news": sg or None})
                continue
            proj, x = pt.project(pid, team, opp, side == "home", ctx[side]["b2b"], absent - {pid}, ctx[side]["missing"],
                                 notes.get(pid), pe, exp_margin=exp_margin)
            ratio = (status or {}).get("min_ratio")
            if ratio:  # listed but playing: measured minutes for that status
                proj = {k: v * ratio for k, v in proj.items()}
            if sg.get("min_cap") and proj["min"] > float(sg["min_cap"]):  # minutes limit from the news
                r_ = float(sg["min_cap"]) / proj["min"]
                proj = {k: v * r_ for k, v in proj.items()}
            if proj["min"] < 6:
                continue
            spots = []
            for k, v in x.items():
                if not v or k in ("home",):
                    continue
                c = pe.get("pts", {}).get("coef", {}).get(k, 0.0) if ("pts" in pe and P.usable(pe["pts"], k) and k in P.APPLY) else 0.0
                if k == "hot" and abs(v) < 1.5:
                    continue
                if k == "usage" and v < 0.5:
                    continue
                if k == "vs_opp" and abs(v) < 1.0:
                    continue
                if k == "without_min" or (k == "without" and abs(v) < 1.0):
                    continue
                txt = STORY.get(k, "").format(opp=opp) if k in STORY else (
                    ("Hot: last 5 games " if v > 0 else "Cold: last 5 games ") + f"{abs(v) * 10:.0f}% {'above' if v > 0 else 'below'} projection." if k == "hot"
                    else f"Teammates out: {v * 10:.0f}% of the team's production missing." if k == "usage"
                    else f"Against the {opp} he has scored {abs(v) * 10:.0f}% {'more' if v > 0 else 'less'} than projected (shrunk for sample size)." if k == "vs_opp"
                    else f"Without today's missing teammates he has scored {abs(v) * 10:.0f}% {'more' if v > 0 else 'less'} than projected (shrunk for sample size)." if k == "without"
                    else "Second night of a back-to-back." if k == "b2b" else "")
                se = pe.get("pts", {}).get("se", {}).get(k)
                label = ("Hot hand" if v > 0 else "Cold hand") if k == "hot" else P.FACTORS[k][1]
                spots.append({"key": k, "layer": P.FACTORS[k][0], "label": label, "text": txt,
                              "pct": round(100 * c * v, 1), "evidence": P.eff_mod.evidence(c, se) if se else "none"})
            if five:
                if pid in five:
                    row_lineup = "starting"
                elif q.get("started"):
                    row_lineup = "not in the starting five"
                    if not status:  # a regular starter left out with no report: may be a late scratch
                        proj = {k: v * 0.5 for k, v in proj.items()}
                else:
                    row_lineup = None
            else:
                row_lineup = None
            of = pt.opp_factor(opp, "pts")
            matchup = "soft" if of >= 1.03 else "tough" if of <= 0.97 else None
            wo_names = [pt.p[b]["name"] for b in pt.key_absent(team, absent - {pid}) if (pt.p[pid].get("wo") or {}).get(b)]
            row = {"id": pid, "name": q["name"], "pos": q["pos"], "out": False, "lineup": row_lineup,
                   "matchup": matchup, "without_names": wo_names[:2], "started": int(bool(q.get("started"))),
                   "status": status.get("status") if status else None, "detail": status.get("detail") if status else None,
                   "play": status.get("play") if status else None, "spots": spots, "news": sg or None}
            for st in ("min", "pts", "reb", "ast", "tpm", "stl", "blk", "tov", "pra", "fga", "fta"):
                row[st] = round(proj[st], 1)
            recent = list(pt.team_hist[team])[-5:]
            seen = (sum(pid in s_ for s_ in recent) / len(recent)) if recent else 1.0
            # chance he plays: recent participation (fringe players rarely do) x the injury report
            row["p_play"] = round(max(0.05, seen if pid not in five else 1.0) * (row["play"] if row["play"] is not None else 1.0), 3)
            lst.append(row)
        # the team has 240 minutes: scale projections so expected minutes add up (tested: better on every stat)
        k = team_minutes_scale(sum(r["min"] * r["p_play"] for r in lst if not r["out"]))
        live = [r for r in lst if not r["out"]]
        caps = {i: float(r["news"]["min_cap"]) for i, r in enumerate(live) if (r.get("news") or {}).get("min_cap")}
        for r, kp in zip(live, capped_factors([r["min"] for r in live], k, caps=caps)):
            for st in ("min", "pts", "reb", "ast", "tpm", "stl", "blk", "tov", "pra", "fga", "fta"):
                r[st] = round(r[st] * kp, 1)
        for r in lst:
            if r["out"]:
                continue
            r["disp"] = {k: round(v, 3) for k, v in P.player_disp(pt.p[r["id"]], disp).items()}
            r["lines"] = {st: P.lines_for(st, r[st], r["disp"]) for st in ("pts", "reb", "ast", "tpm", "pra")}
        out[side] = lst
    return out
