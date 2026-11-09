"""History on disk: one CSV of games, one of player lines, plus small JSON state files."""
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HIST = DATA / "history"
STATE = DATA / "state"
PRED = DATA / "predictions"
OVR = DATA / "overrides"
SITE = ROOT / "site" / "data"

BOX = ["fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "reb", "ast", "tov", "stl", "blk"]
GAME_COLS = (["game_id", "date", "day", "season", "stype", "home", "away", "home_pts", "away_pts", "ot",
              "neutral", "national_tv", "venue", "box", "q", "refs"]
             + [f"h_q{i}" for i in range(1, 5)] + [f"a_q{i}" for i in range(1, 5)]
             + [f"h_{c}" for c in BOX] + [f"a_{c}" for c in BOX])
PLAYER_STATS = ["min", "pts", "reb", "ast", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "stl", "blk", "tov", "pf", "pm"]
PLAYER_COLS = ["game_id", "team", "player_id", "name", "pos", "jersey", "starter", "dnp_reason"] + PLAYER_STATS


def _read(path, cols):
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path, dtype={"game_id": str, "player_id": str})
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        return df[cols]
    return pd.DataFrame(columns=cols)


def load_games(min_season=None):
    """Live seasons from games.csv plus older seasons kept in games_archive_<season>.csv (written once by
    the history backfill and never touched by the regular runs). min_season: drop older seasons."""
    parts = [_read(f, GAME_COLS) for f in sorted(HIST.glob("games_archive_*.csv"))] + [_read(HIST / "games.csv", GAME_COLS)]
    parts = [x for x in parts if len(x)]
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=GAME_COLS)
    if len(df):
        df = df.drop_duplicates("game_id", keep="last")
        df["season"] = df["season"].astype(int)
        df["stype"] = df["stype"].astype(int)
        df["box"] = df["box"].fillna(0).astype(int)
        df["q"] = df["q"].fillna(0).astype(int)
        if min_season is not None:
            df = df[df["season"] >= int(min_season)]
    return df.sort_values(["date", "game_id"]).reset_index(drop=True)


def archived_seasons():
    return {int(f.stem.rsplit("_", 1)[1]) for f in HIST.glob("games_archive_*.csv")}


def save_games(df):
    HIST.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates("game_id", keep="last").sort_values(["date", "game_id"])
    old = archived_seasons()
    if old:
        df = df[~df["season"].astype(int).isin(old)]
    df[GAME_COLS].to_csv(HIST / "games.csv", index=False)


def save_archive(df, season):
    """Older seasons (history backfill only)."""
    HIST.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates("game_id", keep="last").sort_values(["date", "game_id"])
    df[GAME_COLS].to_csv(HIST / f"games_archive_{season}.csv", index=False)


STINT_COLS = ["game_id", "period", "start", "dur", "h_pts", "a_pts", "home_ids", "away_ids"]


def load_stints(min_season=None):
    parts = []
    for f in sorted(HIST.glob("stints_*.csv")):
        s_ = int(f.stem.rsplit("_", 1)[1])
        if min_season is None or s_ >= min_season:
            parts.append(pd.read_csv(f, dtype={"game_id": str, "home_ids": str, "away_ids": str}))
    parts = [x for x in parts if len(x)]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=STINT_COLS)


def save_stints(df, season):
    HIST.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(["game_id", "period", "start"], keep="last").sort_values(["game_id", "period", "start"])
    df[STINT_COLS].to_csv(HIST / f"stints_{season}.csv", index=False)


def load_players():
    """Player lines, one file per season (old seasons never change, so the repository stays small)."""
    parts = [_read(f, PLAYER_COLS) for f in sorted(HIST.glob("players_*.csv"))]
    if (HIST / "players.csv").exists():  # older single-file layout
        parts.append(_read(HIST / "players.csv", PLAYER_COLS))
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=PLAYER_COLS)
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates(["game_id", "team", "player_id"], keep="last").reset_index(drop=True)


def save_players(df):
    HIST.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(["game_id", "team", "player_id"], keep="last").sort_values(["game_id", "team"])
    g = load_games()
    season = df["game_id"].astype(str).map(dict(zip(g["game_id"].astype(str), g["season"])))
    season = pd.to_numeric(season, errors="coerce").fillna(0).astype(int)
    for s, part in df.groupby(season):
        if int(s) <= 0:
            continue  # a line whose game is unknown is not stored
        part[PLAYER_COLS].to_csv(HIST / f"players_{s}.csv", index=False)
    old = HIST / "players.csv"
    if old.exists():
        old.unlink()


def read_json(path, default=None):
    path = Path(path)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def clean(o):
    """NaN/NA -> None, numpy scalars -> Python, so the JSON is valid for browsers."""
    import math
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if o is pd.NA:
        return None
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return clean(float(o))
        if isinstance(o, np.bool_):
            return bool(o)
    except ImportError:
        pass
    return o


def write_json(path, obj, compact=True):
    path = Path(path)
    obj = clean(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        if compact:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False, default=_default, allow_nan=False)
        else:
            json.dump(obj, f, indent=1, ensure_ascii=False, default=_default, allow_nan=False)
    os.replace(tmp, path)


def _default(o):
    try:
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else round(float(o), 4)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if o is pd.NA:
        return None
    raise TypeError(f"not serialisable: {type(o)}")
