"""Injury-status calibration.

ESPN keeps only today's injury list (past box scores show the current list, not the one at game time),
so every run writes down the status each listed player had before tip-off. Once the games are played,
the log says how often each status really meant "did not play", and how many minutes those who did
play got compared with their usual. Those measured numbers replace the fixed guesses once a status has
enough cases.
"""
from datetime import datetime, timedelta

import pandas as pd

from . import espn
from .store import HIST

LOG = HIST / "injury_log.csv"
COLS = ["game_id", "day", "team", "player_id", "name", "status", "detail", "seen"]
MIN_N = 30          # cases before a measured status replaces the default
KEYS = ["out", "ruled out (note)", "doubtful", "questionable", "day-to-day", "probable"]
# defaults until measured (chance he misses the game)
DEFAULT_W = {"out": 1.0, "ruled out (note)": 0.85, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.3,
             "probable": 0.1}
NOTE_RULES = [  # ESPN only says Out / Day-To-Day; the report's note often says more
    (("ruled out", "won't play", "will not play", "will miss", "is out for"), "ruled out (note)"),
    (("doubtful",), "doubtful"),
    (("questionable", "game-time decision", "uncertain"), "questionable"),
    (("probable", "expected to play", "will play", "plans to play", "available", "cleared", "upgraded"), "probable"),
]


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def key(status, detail="", day=None):
    """day: the game's date (ISO); a note about another day's game is stale and is ignored."""
    s = (status or "").lower()
    if not s:
        return None
    if "out" in s and "day" not in s:
        return "out"
    for k in ("doubtful", "questionable", "probable"):
        if k in s:
            return k
    d = (detail or "").lower()
    if day:
        named = [w for w in WEEKDAYS if w in d]
        wd = WEEKDAYS[datetime.fromisoformat(str(day)[:10]).weekday()]
        if named and wd not in named:
            return "day-to-day"
    for words, k in NOTE_RULES:
        if any(w in d for w in words):
            return k
    return "day-to-day"


def load():
    if LOG.exists() and LOG.stat().st_size > 0:
        return pd.read_csv(LOG, dtype={"game_id": str, "player_id": str})
    return pd.DataFrame(columns=COLS)


def update(upcoming, injuries, now=None):
    """Record (or refresh) the status of every listed player for games starting in the next 36 hours."""
    now = now or espn.now_utc()
    rows = []
    for g in upcoming:
        tip = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        if not (now < tip <= now + timedelta(hours=36)):
            continue
        for team in (g["home"], g["away"]):
            for i in (injuries or {}).get(team, []) or []:
                if not key(i.get("status"), i.get("detail"), g["day"]):
                    continue
                rows.append({"game_id": str(g["game_id"]), "day": g["day"], "team": team,
                             "player_id": str(i.get("player_id") or ""), "name": i.get("name"),
                             "status": i.get("status"), "detail": i.get("detail") or "", "seen": now.isoformat()})
    if not rows:
        return 0
    df = pd.concat([load(), pd.DataFrame(rows)], ignore_index=True)
    # the last status seen before tip-off wins
    df = df.drop_duplicates(["game_id", "player_id"], keep="last").sort_values(["day", "game_id", "team"])
    HIST.mkdir(parents=True, exist_ok=True)
    df[COLS].to_csv(LOG, index=False)
    return len(rows)


def calibrate(players, games):
    """{status: {n, play, n_play, min_ratio}} from finished games in the log."""
    log = load()
    if not len(log) or not len(players):
        return {}
    done = set(games.loc[games["home_pts"].notna(), "game_id"].astype(str))
    have_box = set(players["game_id"].astype(str))
    log = log[log["game_id"].isin(done & have_box)]
    if not len(log):
        return {}
    pl = players[["game_id", "team", "player_id", "name", "min"]].copy()
    pl["game_id"] = pl["game_id"].astype(str)
    pl["player_id"] = pl["player_id"].astype(str)
    # the injury feed sometimes gives names instead of ids
    names = {(t, str(n).lower()): pid for t, n, pid in zip(pl["team"], pl["name"], pl["player_id"])}
    log = log.copy()
    log["player_id"] = [p if p.isdigit() else names.get((t, str(n).lower()), p)
                        for p, t, n in zip(log["player_id"].astype(str), log["team"], log["name"])]
    pl["min"] = pd.to_numeric(pl["min"], errors="coerce").fillna(0.0)
    day = dict(zip(games["game_id"].astype(str), games["day"]))
    pl["day"] = pl["game_id"].map(day)
    pl = pl[pl["player_id"].isin(set(log["player_id"]))].sort_values("day")
    by_p = {pid: d for pid, d in pl.groupby("player_id")}
    out = {}
    for k in KEYS:
        sub = log[[key(a, b, d) == k for a, b, d in zip(log["status"], log["detail"].fillna(""), log["day"])]]
        n = play = 0
        ratios = []
        for r in sub.itertuples():
            mine = by_p.get(r.player_id)
            if mine is None:
                mine = pl.iloc[0:0]
            row = mine[mine["game_id"] == r.game_id]
            m = float(row["min"].iloc[0]) if len(row) else 0.0
            n += 1
            if m > 0:
                play += 1
                before = mine[(mine["day"] < r.day) & (mine["min"] > 0)].tail(10)
                if len(before) >= 3:
                    ratios.append(m / max(before["min"].mean(), 1.0))
        if n:
            out[k] = {"n": n, "play": round(play / n, 3), "n_play": play,
                      "min_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None, "n_ratio": len(ratios)}
    return out


def apply(injuries, cal, next_day=None):
    """Replace the fixed status weights by measured miss rates where a status has enough cases.
    Adds 'play' (chance he plays) and 'min_ratio' (minutes if he plays, vs usual) to each entry."""
    for team, lst in (injuries or {}).items():
        for i in lst or []:
            k = key(i.get("status"), i.get("detail"), (next_day or {}).get(team))
            c = cal.get(k) if k else None
            if k:
                i["weight"] = DEFAULT_W[k]
                i["report"] = k
            if c and c["n"] >= MIN_N:
                i["weight"] = round(1.0 - c["play"], 3)
                i["measured"] = True
            i["play"] = round(1.0 - (i.get("weight") or 0.0), 3)
            if c and c.get("n_ratio", 0) >= MIN_N and c.get("min_ratio"):
                i["min_ratio"] = min(1.0, c["min_ratio"])
    return injuries
