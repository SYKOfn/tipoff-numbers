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


def walk(c, players_df, notes, cur):
    pt = P.PlayerTracker()
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
        done = []
        for team, opp, side in ((g["home"], g["away"], "home"), (g["away"], g["home"], "away")):
            trs = rows.get(team, [])
            played = {r["player_id"] for r in trs if r["min"] > 0}
            absent = set(pt.rotation(team)) - played
            for r in trs:
                pid = r["player_id"]
                if r["min"] <= 0 or pid not in pt.p or pt.p[pid]["gp"] < 3:
                    continue
                proj, x = pt.project(pid, team, opp, side == "home", ctx[side]["b2b"] if ctx else 0, absent,
                                     ctx[side]["missing"] if ctx else 0.0, notes.get(pid))
                rows_eff.append((x, {st: (r[st] if st != "min" else r["min"], proj[st]) for st in P.EFFECT_STATS}))
                act_pra = r["pts"] + r["reb"] + r["ast"]
                for st in P.SHOW + ["pra"]:
                    a = act_pra if st == "pra" else r[st]
                    if a is None:
                        continue
                    sq[st] += (a - proj[st]) ** 2
                    sp[st] += proj[st]
                if int(g["season"]) == cur:
                    logs[(gid, pid)] = {k: round(v, 1) for k, v in proj.items() if k in ("min", "pts", "reb", "ast", "tpm", "pra")}
                    key = (cur, pid)
                    if season_sum[key][1] >= 1:
                        acc["n"] += 1
                        acc["mae"] += abs(r["pts"] - proj["pts"])
                        acc["mae_base"] += abs(r["pts"] - season_sum[key][0] / season_sum[key][1])
                done.append((pid, r["pts"], proj["pts"]))
        for team in (g["home"], g["away"]):
            for r in rows.get(team, []):
                if r["min"] > 0:
                    s = season_sum[(int(g["season"]), r["player_id"])]
                    s[0] += r["pts"]
                    s[1] += 1
        pt.post_game(g, rows)
        for pid, a, p in done:
            pt.note_result(pid, a, p)
    pe = P.estimate_effects(rows_eff)
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


def project_game(pt, pe, disp, g, ctx, injuries, notes, news=True):
    out = {}
    for team, opp, side in ((g["home"], g["away"], "home"), (g["away"], g["home"], "away")):
        rot = pt.rotation(team)
        inj = match_injury(pt, team, (injuries or {}).get(team)) if news else {}
        absent = {pid for pid, i in inj.items() if (i.get("weight") or 0) >= 0.75}
        lst = []
        for pid in sorted(rot, key=lambda k: -rot[k]):
            q = pt.p[pid]
            status = inj.get(pid)
            if pid in absent:
                lst.append({"id": pid, "name": q["name"], "pos": q["pos"], "out": True, "status": status.get("status"),
                            "detail": status.get("detail")})
                continue
            proj, x = pt.project(pid, team, opp, side == "home", ctx[side]["b2b"], absent - {pid}, ctx[side]["missing"],
                                 notes.get(pid), pe)
            if proj["min"] < 6:
                continue
            spots = []
            for k, v in x.items():
                if not v or k in ("home",):
                    continue
                c = pe.get("pts", {}).get("coef", {}).get(k, 0.0) if ("pts" in pe and P.usable(pe["pts"], k)) else 0.0
                if k == "hot" and abs(v) < 1.5:
                    continue
                if k == "usage" and v < 0.5:
                    continue
                txt = STORY.get(k, "").format(opp=opp) if k in STORY else (
                    ("Hot: last 5 games " if v > 0 else "Cold: last 5 games ") + f"{abs(v) * 10:.0f}% {'above' if v > 0 else 'below'} projection." if k == "hot"
                    else f"Teammates out: {v * 10:.0f}% of the team's production missing." if k == "usage"
                    else "Second night of a back-to-back." if k == "b2b" else "")
                se = pe.get("pts", {}).get("se", {}).get(k)
                label = ("Hot hand" if v > 0 else "Cold hand") if k == "hot" else P.FACTORS[k][1]
                spots.append({"key": k, "layer": P.FACTORS[k][0], "label": label, "text": txt,
                              "pct": round(100 * c * v, 1), "evidence": P.eff_mod.evidence(c, se) if se else "none"})
            row = {"id": pid, "name": q["name"], "pos": q["pos"], "out": False,
                   "status": status.get("status") if status else None, "detail": status.get("detail") if status else None,
                   "spots": spots}
            for st in ("min", "pts", "reb", "ast", "tpm", "stl", "blk", "tov", "pra", "fga", "fta"):
                row[st] = round(proj[st], 1)
            row["lines"] = {st: P.lines_for(st, proj[st], disp) for st in ("pts", "reb", "ast", "tpm", "pra")}
            lst.append(row)
        out[side] = lst
    return out
