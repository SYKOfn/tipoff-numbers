"""Incremental collection from ESPN: results, schedule, box scores, injuries.

First run backfills three full seasons plus the current one (box scores fill over a few runs,
MAX_SUMMARIES per run, newest first). Later runs re-read the last few days and the next two weeks.
"""
import os
from datetime import date, timedelta

import pandas as pd

from . import espn
from .store import (BOX, STATE, load_games, load_players, read_json, save_games, save_players, write_json)

MAX_SUMMARIES = int(os.environ.get("MAX_SUMMARIES", "700"))
AHEAD_DAYS = 14


def _d(s):
    return date.fromisoformat(s)


def collect(today=None):
    today = today or espn.now_utc().astimezone(espn.ET).date()
    games = load_games()
    players = load_players()
    if len(games):
        start = _d(games["day"].max()) - timedelta(days=3)
    else:
        start = date(espn.season_of(today.isoformat()) - 4, 10, 1)  # three full seasons + this one
    end = today + timedelta(days=AHEAD_DAYS)

    finished, upcoming = {}, {}
    d = start
    while d <= end:
        d2 = min(d + timedelta(days=6), end)
        evs = espn.scoreboard(d.strftime("%Y%m%d"), d2.strftime("%Y%m%d"))
        if evs is None:  # range query refused: day by day
            evs = []
            dd = d
            while dd <= d2:
                evs += espn.scoreboard(dd.strftime("%Y%m%d")) or []
                dd += timedelta(days=1)
        for g in evs:
            if g["stype"] not in (2, 3, 5):  # preseason / exhibitions out
                continue
            if g["completed"] and g["home_pts"] is not None:
                finished[g["game_id"]] = g
            elif g["state"] in ("pre", "in"):
                upcoming[g["game_id"]] = g
        d = d2 + timedelta(days=1)

    # merge finished results, keeping box scores already stored
    old = games.set_index("game_id") if len(games) else None
    rows = []
    for gid, g in finished.items():
        r = {k: g.get(k) for k in ("game_id", "date", "day", "season", "stype", "home", "away", "home_pts", "away_pts",
                                   "ot", "neutral", "national_tv", "venue")}
        r["neutral"], r["national_tv"] = int(bool(r["neutral"])), int(bool(r["national_tv"]))
        if old is not None and gid in old.index and int(old.loc[gid, "box"] or 0):
            for c in old.columns:
                if c.startswith(("h_", "a_")) or c == "box":
                    r[c] = old.loc[gid, c]
        else:
            r["box"] = 0
        rows.append(r)
    if rows:
        games = pd.concat([games, pd.DataFrame(rows)], ignore_index=True)
        games = games.drop_duplicates("game_id", keep="last")

    # box scores, newest first
    cur = espn.season_of(today.isoformat())
    need = games[(games["box"].fillna(0).astype(int) == 0) & (games["season"].astype(int) >= cur - 1)]
    need = need.sort_values("date", ascending=False).head(MAX_SUMMARIES)
    new_players = []
    games = games.set_index("game_id")
    for gid in need["game_id"]:
        s = espn.summary(gid)
        if not s or not s["teams"]:
            continue
        h, a = games.loc[gid, "home"], games.loc[gid, "away"]
        for side, ab in (("h", h), ("a", a)):
            for c in BOX:
                games.loc[gid, f"{side}_{c}"] = s["teams"].get(ab, {}).get(c)
        games.loc[gid, "box"] = 1
        for p in s["players"]:
            new_players.append({"game_id": gid, **p})
    games = games.reset_index()
    save_games(games)
    if new_players:
        players = pd.concat([players, pd.DataFrame(new_players)], ignore_index=True)
        save_players(players)

    # injuries: league list, else from the next games' summaries
    inj = espn.injuries()
    if not inj:
        inj = {}
        soon = sorted(upcoming.values(), key=lambda g: g["date"])[:20]
        for g in soon:
            s = espn.summary(g["game_id"])
            for ab, lst in ((s or {}).get("injuries") or {}).items():
                inj.setdefault(ab, lst)
    write_json(STATE / "injuries.json", {"as_of": espn.now_utc().isoformat(), "teams": inj or {}})

    meta = read_json(STATE / "teams_meta.json", {}) or {}
    if len(meta) < 30:
        meta = espn.teams_meta() or meta
        write_json(STATE / "teams_meta.json", meta)
    for g in list(finished.values()) + list(upcoming.values()):  # logos from the scoreboard too
        for side in ("home", "away"):
            if g.get(f"{side}_logo") and not meta.get(g[side], {}).get("logo"):
                meta.setdefault(g[side], {})["logo"] = g[f"{side}_logo"]
    write_json(STATE / "teams_meta.json", meta)

    write_json(STATE / "upcoming.json", sorted(upcoming.values(), key=lambda g: g["date"]))
    write_json(STATE / "collect.json", {"calls": espn.CALLS["n"], "errors": espn.CALLS["errors"][-30:],
                                        "finished_seen": len(finished), "upcoming": len(upcoming),
                                        "summaries": len(need)})
    return {"games": len(games), "upcoming": len(upcoming), "calls": espn.CALLS["n"], "errors": len(espn.CALLS["errors"])}
