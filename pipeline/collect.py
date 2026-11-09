"""Incremental collection from ESPN: results, schedule, box scores, injuries.

First run backfills five full seasons plus the current one (box scores fill over a few runs,
MAX_SUMMARIES per run, newest first). Later runs re-read the last few days and the next two weeks.
"""
import os
from datetime import date, datetime, timedelta

import pandas as pd

from . import espn
from .store import (BOX, STATE, load_games, load_players, read_json, save_games, save_players, write_json)

MAX_SUMMARIES = int(os.environ.get("MAX_SUMMARIES", "1000"))
AHEAD_DAYS = 14
HIST_SEASONS = int(os.environ.get("HIST_SEASONS", "5"))  # full seasons kept before the current one


def _d(s):
    return date.fromisoformat(s)


def collect(today=None):
    today = today or espn.now_utc().astimezone(espn.ET).date()
    games = load_games()
    players = load_players()
    cur = espn.season_of(today.isoformat())
    if len(games):
        start = _d(games["day"].max()) - timedelta(days=3)
        # upgrades: quarter scores missing for recent seasons -> re-read those days once
        noq = games[(games["q"].fillna(0).astype(int) == 0) & (games["season"].astype(int) >= cur - 1)]
        if len(noq) > 30:
            start = min(start, _d(noq["day"].min()))
        # more history: results back to HIST_SEASONS seasons before this one (one-time scan)
        if int(games["season"].min()) > cur - HIST_SEASONS:
            start = date(cur - HIST_SEASONS - 1, 10, 1)
        # player lines stored before the full stat line existed -> fetch those box scores again
        if len(players):
            full = set(players.loc[players["fga"].notna(), "game_id"].astype(str))
            stale = (games["box"].fillna(0).astype(int) == 1) & ~games["game_id"].astype(str).isin(full) \
                & (games["season"].astype(int) >= cur - 1)
            games.loc[stale, "box"] = 0
    else:
        start = date(cur - HIST_SEASONS - 1, 10, 1)
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
        hl, al = g.get("home_lines") or [], g.get("away_lines") or []
        if len(hl) >= 4 and len(al) >= 4 and None not in hl[:4] + al[:4]:
            for i in range(4):
                r[f"h_q{i + 1}"], r[f"a_q{i + 1}"] = hl[i], al[i]
            r["q"] = 1
        else:
            r["q"] = 0
        if old is not None and gid in old.index and int(old.loc[gid, "box"] or 0):
            for c in old.columns:
                if (c.startswith(("h_", "a_")) and "_q" not in c) or c == "box":
                    r[c] = old.loc[gid, c]
        else:
            r["box"] = 0
        rows.append(r)
    if rows:
        games = pd.concat([games, pd.DataFrame(rows)], ignore_index=True)
        games = games.drop_duplicates("game_id", keep="last")

    # box scores, newest first
    need = games[(games["box"].fillna(0).astype(int) == 0) & (games["season"].astype(int) >= cur - HIST_SEASONS)]
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

    from . import oddsapi
    ups = sorted(upcoming.values(), key=lambda g: g["date"])
    if not ups and not finished:
        # nothing parsed at all: a feed change or outage, not an empty NBA calendar; keep the last good schedule
        prev = read_json(STATE / "upcoming.json", []) or []
        ups = [g for g in prev if g.get("date", "") >= espn.now_utc().strftime("%Y-%m-%dT%H:%M")]
        espn.CALLS["errors"].append("no games parsed from the scoreboard; kept the previous schedule")
    odds_status = oddsapi.collect(ups)
    write_json(STATE / "upcoming.json", ups)

    # rest of the regular season (for playoff chances): refreshed twice a day, it barely changes
    rest_old = read_json(STATE / "season_rest.json", None)
    rest_at = (read_json(STATE / "collect.json", {}) or {}).get("season_rest_at")
    fresh = rest_old is not None and rest_at and espn.now_utc() - datetime.fromisoformat(rest_at) < timedelta(hours=12)
    rest = [] if not fresh else rest_old
    d, last = end + timedelta(days=1), date(cur, 4, 20)
    while d <= last and not fresh:
        d2 = min(d + timedelta(days=6), last)
        for g in espn.scoreboard(d.strftime("%Y%m%d"), d2.strftime("%Y%m%d")) or []:
            if g["stype"] == 2 and not g["completed"]:
                rest.append({"game_id": g["game_id"], "day": g["day"], "home": g["home"], "away": g["away"]})
        d = d2 + timedelta(days=1)
    if not fresh:
        write_json(STATE / "season_rest.json", rest)
        rest_at = espn.now_utc().isoformat()
    # head coaches per season: past seasons once, this season once a day
    co = read_json(STATE / "coaches.json", {}) or {}
    co_at = co.get("_at")
    for sn in range(cur - HIST_SEASONS, cur + 1):
        stale = sn == cur and (not co_at or espn.now_utc() - datetime.fromisoformat(co_at) > timedelta(hours=24))
        if str(sn) not in co or len(co.get(str(sn)) or {}) < 25 or stale:
            got = espn.coaches(sn)
            if got:
                co[str(sn)] = got
            if sn == cur:
                co["_at"] = espn.now_utc().isoformat()
    write_json(STATE / "coaches.json", co)
    write_json(STATE / "collect.json", {"calls": espn.CALLS["n"], "errors": espn.CALLS["errors"][-30:],
                                        "finished_seen": len(finished), "upcoming": len(upcoming),
                                        "summaries": len(need), "odds_api": odds_status, "season_rest_at": rest_at})
    return {"games": len(games), "upcoming": len(upcoming), "calls": espn.CALLS["n"], "errors": len(espn.CALLS["errors"])}
