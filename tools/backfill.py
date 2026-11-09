"""History backfill, one season per job (run on GitHub, several seasons in parallel).

  python -m tools.backfill 2024 stints   lineup stints for a stored season (play-by-play)
  python -m tools.backfill 2019 full     an older season from scratch: results, quarters, box scores,
                                         referees, player lines and stints, kept in its own archive files

Resumable: work already saved is skipped, and progress is saved every 150 games, so a job that runs out
of time continues where it stopped when run again. The regular site runs never write these files.
"""
import sys
import time
from datetime import date, timedelta

import pandas as pd

from pipeline import espn
from pipeline.store import (BOX, GAME_COLS, HIST, PLAYER_COLS, load_games, load_stints, save_archive, save_stints)

BUDGET = 52 * 60  # seconds per job


def stints_for(season, gids, t0):
    old = load_stints()
    old = old[old["game_id"].astype(str).isin(set(map(str, gids)))]
    have = set(old["game_id"].astype(str))
    todo = [g for g in gids if str(g) not in have]
    print(f"{season}: {len(have)} games already have stints, {len(todo)} to fetch")
    new, done = [], 0
    for gid in todo:
        if time.time() - t0 > BUDGET:
            print("time budget reached; run again to continue")
            break
        s = espn.summary(gid)
        if s and s.get("stint_cov", 0) >= 0.9:
            new += s["stints"]
        done += 1
        if done % 150 == 0 and new:
            save_stints(pd.concat([old, pd.DataFrame(new)], ignore_index=True), season)
            print("saved", done)
    if new:
        save_stints(pd.concat([old, pd.DataFrame(new)], ignore_index=True), season)
    return done


def full(season, t0):
    arch = HIST / f"games_archive_{season}.csv"
    games = pd.read_csv(arch, dtype={"game_id": str}) if arch.exists() else pd.DataFrame(columns=GAME_COLS)
    if not len(games):
        rows = []
        d, end = date(season - 1, 10, 1), date(season, 7, 1)
        while d <= end:
            for g in espn.scoreboard(d.strftime("%Y%m%d")) or []:
                if g["stype"] in (2, 3, 5) and g["completed"] and g["home_pts"] is not None and g["season"] == season:
                    r = {k: g.get(k) for k in ("game_id", "date", "day", "season", "stype", "home", "away", "home_pts",
                                               "away_pts", "ot", "neutral", "national_tv", "venue")}
                    r["neutral"], r["national_tv"] = int(bool(r["neutral"])), int(bool(r["national_tv"]))
                    hl, al = g.get("home_lines") or [], g.get("away_lines") or []
                    if len(hl) >= 4 and len(al) >= 4 and None not in hl[:4] + al[:4]:
                        for i in range(4):
                            r[f"h_q{i + 1}"], r[f"a_q{i + 1}"] = hl[i], al[i]
                        r["q"] = 1
                    else:
                        r["q"] = 0
                    r["box"] = 0
                    rows.append(r)
            d += timedelta(days=1)
        games = pd.DataFrame(rows, columns=GAME_COLS).drop_duplicates("game_id")
        save_archive(games, season)
        print(f"{season}: {len(games)} games found")
    pfile = HIST / f"players_{season}.csv"
    players = pd.read_csv(pfile, dtype={"game_id": str, "player_id": str}) if pfile.exists() else pd.DataFrame(columns=PLAYER_COLS)
    old_st = load_stints()
    old_st = old_st[old_st["game_id"].astype(str).isin(set(games["game_id"].astype(str)))]
    games = games.set_index("game_id")
    games["refs"] = games["refs"].astype(object)  # an empty column reads back as float
    need = [g for g in games.index if int(games.loc[g, "box"] or 0) == 0]
    print(f"{season}: {len(need)} box scores to fetch")
    new_p, new_s, done = [], [], 0
    for gid in need:
        if time.time() - t0 > BUDGET:
            print("time budget reached; run again to continue")
            break
        s = espn.summary(gid)
        done += 1
        if not s or not s["teams"]:
            continue
        h, a = games.loc[gid, "home"], games.loc[gid, "away"]
        for side, ab in (("h", h), ("a", a)):
            for c in BOX:
                games.loc[gid, f"{side}_{c}"] = s["teams"].get(ab, {}).get(c)
        games.loc[gid, "box"] = 1
        games.loc[gid, "refs"] = ";".join(s["officials"]) if s.get("officials") else "-"
        new_p += [{"game_id": gid, **p} for p in s["players"]]
        if s.get("stint_cov", 0) >= 0.9:
            new_s += s["stints"]
        if done % 150 == 0:
            _save(games, season, players, new_p, old_st, new_s)
            print("saved", done)
    _save(games, season, players, new_p, old_st, new_s)
    return done


def _save(games, season, players, new_p, old_st, new_s):
    save_archive(games.reset_index(), season)
    if new_p:
        p = pd.concat([players, pd.DataFrame(new_p)], ignore_index=True)
        p = p.drop_duplicates(["game_id", "team", "player_id"], keep="last").sort_values(["game_id", "team"])
        p[PLAYER_COLS].to_csv(HIST / f"players_{season}.csv", index=False)
    if new_s:
        save_stints(pd.concat([old_st, pd.DataFrame(new_s)], ignore_index=True), season)


def main():
    season, mode = int(sys.argv[1]), sys.argv[2]
    t0 = time.time()
    if mode == "stints":
        g = load_games()
        gids = list(g[(g["season"] == season) & (g["box"] == 1)]["game_id"].astype(str))
        stints_for(season, gids, t0)
    else:
        full(season, t0)
    print("calls", espn.CALLS["n"], "errors", len(espn.CALLS["errors"]), espn.CALLS["errors"][:3])


if __name__ == "__main__":
    main()
