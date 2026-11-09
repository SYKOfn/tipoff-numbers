"""Season lines, advanced stats, splits and game logs for every player (site data)."""
import math

import numpy as np
import pandas as pd

from .teams import TEAMS


def _r(x, d=1):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else round(x, d)
    except (TypeError, ValueError):
        return None


def enrich(players, games):
    """Player rows (who played) joined with game info and team totals."""
    if not len(players):
        return pd.DataFrame()
    p = players[players["min"].fillna(0) > 0].copy()
    g = games[["game_id", "day", "season", "stype", "home", "away", "home_pts", "away_pts", "ot",
               "h_fga", "h_fta", "h_tov", "a_fga", "a_fta", "a_tov", "h_reb", "a_reb", "h_oreb", "a_oreb", "h_fgm", "a_fgm"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    p["game_id"] = p["game_id"].astype(str)
    p = p.merge(g, on="game_id", how="inner")
    home = p["team"] == p["home"]
    p["is_home"] = home
    p["opp"] = np.where(home, p["away"], p["home"])
    p["tm_pts"] = np.where(home, p["home_pts"], p["away_pts"])
    p["op_pts"] = np.where(home, p["away_pts"], p["home_pts"])
    p["win"] = p["tm_pts"] > p["op_pts"]
    for k in ("fga", "fta", "tov", "reb", "oreb", "fgm"):
        p[f"tm_{k}"] = np.where(home, p[f"h_{k}"], p[f"a_{k}"])
        p[f"op_{k}"] = np.where(home, p[f"a_{k}"], p[f"h_{k}"])
    p["tm_min"] = 240 + 25 * p["ot"].fillna(0)
    for c in ("fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "stl", "blk", "tov", "pf", "pm"):
        p[c] = pd.to_numeric(p[c], errors="coerce")
    return p


def line(df):
    """Per-game and advanced numbers for a set of player-games."""
    n = len(df)
    if not n:
        return None
    s = df[["min", "pts", "reb", "ast", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "stl", "blk", "tov", "pm"]].sum(min_count=1)
    mins = s["min"] or 0
    tsa = (s["fga"] or 0) + 0.44 * (s["fta"] or 0)
    usage_num = ((df["fga"] + 0.44 * df["fta"] + df["tov"]) * df["tm_min"] / 5).sum(min_count=1)
    usage_den = (df["min"] * (df["tm_fga"] + 0.44 * df["tm_fta"] + df["tm_tov"])).sum(min_count=1)
    reb_den = (df["min"] / (df["tm_min"] / 5) * (df["tm_reb"] + df["op_reb"])).sum(min_count=1)
    ast_den = ((df["min"] / (df["tm_min"] / 5)) * df["tm_fgm"] - df["fgm"]).sum(min_count=1)
    return {
        "gp": int(n), "gs": int(df["starter"].fillna(0).sum()), "mpg": _r(mins / n), "ppg": _r(s["pts"] / n), "rpg": _r(s["reb"] / n),
        "apg": _r(s["ast"] / n), "tpm": _r(s["tpm"] / n), "spg": _r(s["stl"] / n), "bpg": _r(s["blk"] / n), "topg": _r(s["tov"] / n),
        "fg": _r(s["fgm"] / s["fga"], 3) if s["fga"] else None, "tp": _r(s["tpm"] / s["tpa"], 3) if s["tpa"] else None,
        "ft": _r(s["ftm"] / s["fta"], 3) if s["fta"] else None,
        "ts": _r(s["pts"] / (2 * tsa), 3) if tsa else None, "efg": _r((s["fgm"] + 0.5 * s["tpm"]) / s["fga"], 3) if s["fga"] else None,
        "usg": _r(100 * usage_num / usage_den) if usage_den else None,
        "reb_pct": _r(100 * s["reb"] / reb_den) if reb_den else None,
        "ast_pct": _r(100 * s["ast"] / ast_den) if ast_den and ast_den > 0 else None,
        "ast_tov": _r(s["ast"] / s["tov"], 2) if s["tov"] else None,
        "p36": _r(36 * s["pts"] / mins) if mins else None, "r36": _r(36 * s["reb"] / mins) if mins else None,
        "a36": _r(36 * s["ast"] / mins) if mins else None, "pm": _r(s["pm"] / n) if pd.notna(s["pm"]) else None,
    }


def build(players, games, cur, logs, next_proj, pt, notes, ctxs):
    """Returns (index list, {pid: page})."""
    ep = enrich(players, games)
    if not len(ep):
        return [], {}
    ep["pid"] = ep["player_id"].astype(str)
    b2b = {}
    for gid, ctx in ctxs.items():
        b2b[(gid, "home")] = ctx["home"]["b2b"]
        b2b[(gid, "away")] = ctx["away"]["b2b"]
    ep["b2b"] = [b2b.get((g, "home" if h else "away"), 0) for g, h in zip(ep["game_id"], ep["is_home"])]
    cur_rows = ep[ep["season"] == cur]
    active = set(cur_rows["pid"]) | set(next_proj)
    index, pages = [], {}
    for pid, df in ep[ep["pid"].isin(active)].groupby("pid"):
        df = df.sort_values("day")
        last = df.iloc[-1]
        q = pt.p.get(pid, {})
        team = q.get("team") or last["team"]
        seasons = []
        for (s, tm), d in df.groupby(["season", "team"]):
            ln = line(d)
            seasons.append({"season": int(s), "team": tm, **ln})
        seasons.sort(key=lambda x: (x["season"], x["gp"]))
        dc = df[df["season"] == cur]
        reg = dc[dc["stype"] == 2]
        cur_line = line(dc) if len(dc) else None
        splits = []
        if len(dc):
            for name, mask in (("Home", dc["is_home"]), ("Away", ~dc["is_home"]), ("Wins", dc["win"]), ("Losses", ~dc["win"]),
                               ("Back-to-back", dc["b2b"] == 1), ("Last 5", dc.index.isin(dc.tail(5).index)),
                               ("Last 10", dc.index.isin(dc.tail(10).index))):
                d = dc[mask]
                if len(d):
                    ln = line(d)
                    splits.append({"name": name, "gp": ln["gp"], "mpg": ln["mpg"], "ppg": ln["ppg"], "rpg": ln["rpg"],
                                   "apg": ln["apg"], "tpm": ln["tpm"], "ts": ln["ts"]})
        vs = []
        if len(dc):
            for opp, d in df[df["season"] >= cur - 1].groupby("opp"):
                ln = line(d)
                vs.append({"opp": opp, "gp": ln["gp"], "ppg": ln["ppg"], "rpg": ln["rpg"], "apg": ln["apg"]})
            vs.sort(key=lambda x: -x["gp"])
        log_src = dc if len(dc) else df[df["season"] == df["season"].max()]
        glog = []
        for r in log_src.sort_values("day", ascending=False).to_dict("records"):
            pr = logs.get((r["game_id"], pid))
            glog.append({"id": r["game_id"], "day": r["day"], "opp": r["opp"], "home": bool(r["is_home"]), "win": bool(r["win"]),
                         "score": f"{int(r['tm_pts'])}-{int(r['op_pts'])}", "min": int(r["min"]), "pts": int(r["pts"]),
                         "reb": int(r["reb"]), "ast": int(r["ast"]), "tpm": _r(r["tpm"], 0), "stl": _r(r["stl"], 0),
                         "blk": _r(r["blk"], 0), "tov": _r(r["tov"], 0),
                         "fg": f"{int(r['fgm'])}-{int(r['fga'])}" if pd.notna(r["fgm"]) else None,
                         "tp": f"{int(r['tpm'])}-{int(r['tpa'])}" if pd.notna(r["tpm"]) else None,
                         "ft": f"{int(r['ftm'])}-{int(r['fta'])}" if pd.notna(r["ftm"]) else None,
                         "pm": _r(r["pm"], 0), "proj": pr})
        nt = notes.get(pid) or {}
        former = [t for t in q.get("teams", []) if t != team]
        story = []
        if former:
            story.append(f"Former team{'s' if len(former) > 1 else ''}: " + ", ".join(TEAMS[t][2] for t in former if t in TEAMS) + ".")
        if nt.get("contract_year"):
            story.append(nt.get("note") or "Final year of his contract.")
        elif nt.get("note"):
            story.append(nt["note"])
        if q.get("back_left"):
            story.append("Recently back from a long absence.")
        nxt = next_proj.get(pid)
        page = {"id": pid, "name": q.get("name") or last["name"], "pos": q.get("pos") or last["pos"],
                "jersey": None if pd.isna(last.get("jersey")) else str(last.get("jersey")).split(".")[0],
                "team": team, "seasons": seasons, "current": cur_line, "splits": splits, "vs": vs[:12], "log": glog[:82],
                "next": nxt, "story": story, "former": former, "contract_year": bool(nt.get("contract_year"))}
        pages[pid] = page
        cl = cur_line or {}
        index.append({"id": pid, "name": page["name"], "team": team, "pos": page["pos"], "gp": cl.get("gp", 0), "mpg": cl.get("mpg"),
                      "ppg": cl.get("ppg"), "rpg": cl.get("rpg"), "apg": cl.get("apg"), "tpm": cl.get("tpm"), "spg": cl.get("spg"),
                      "bpg": cl.get("bpg"), "ts": cl.get("ts"), "usg": cl.get("usg"), "pm": cl.get("pm"),
                      "l5": next((s["ppg"] for s in splits if s["name"] == "Last 5"), None),
                      "next_pts": nxt["proj"]["pts"] if nxt and not nxt.get("out") else None,
                      "next_game": nxt["game"] if nxt else None, "status": nxt.get("status") if nxt else None,
                      "out": bool(nxt and nxt.get("out")), "former": bool(former), "contract_year": page["contract_year"]})
    index.sort(key=lambda x: -(x["ppg"] or 0))
    return index, pages
