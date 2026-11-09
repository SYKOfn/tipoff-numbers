"""ESPN's public JSON feed (the one behind espn.com): schedule, results, box scores, injuries.

Every parser is defensive: ESPN fields come and go, so a missing field gives None, never a crash.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .teams import canon

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")
CALLS = {"n": 0, "errors": []}
UA = "Mozilla/5.0 (compatible; tipoff-numbers/1.0; +https://github.com)"


def fetch(url, retries=3, timeout=30):
    last = None
    for i in range(retries):
        try:
            CALLS["n"] += 1
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):  # e.g. a date range with no games: an empty answer, not worth retrying
                return {}
            last = e
            time.sleep(1.5 * (i + 1))
        except Exception as e:  # network or JSON error
            last = e
            time.sleep(1.5 * (i + 1))
    CALLS["errors"].append(f"{url}: {last}")
    return None


def season_of(day):
    """NBA season id = the year it ends (2026-27 -> 2027). day: 'YYYY-MM-DD' (US Eastern)."""
    y, m = int(day[:4]), int(day[5:7])
    return y + 1 if m >= 8 else y


def et_day(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET).strftime("%Y-%m-%d")


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ scoreboard
def scoreboard(day_from, day_to=None):
    """Events between two US-Eastern dates (YYYYMMDD), inclusive, one day per request
    (ESPN answers 400 to date ranges). None if every request failed."""
    from datetime import date as _date, timedelta as _td
    d0 = _date(int(day_from[:4]), int(day_from[4:6]), int(day_from[6:]))
    d1 = d0 if not day_to else _date(int(day_to[:4]), int(day_to[4:6]), int(day_to[6:]))
    out, ok = [], False
    d = d0
    while d <= d1:
        data = fetch(f"{BASE}/scoreboard?dates={d.strftime('%Y%m%d')}&limit=200")
        if data is not None:
            ok = True
            for e in data.get("events", []) or []:
                g = parse_event(e)
                if g:
                    out.append(g)
        d += _td(days=1)
    return out if ok else None


def parse_event(e):
    try:
        comp = (e.get("competitions") or [{}])[0]
        st = (comp.get("status") or e.get("status") or {}).get("type", {}) or {}
        teams = {}
        for c in comp.get("competitors", []) or []:
            t = c.get("team", {}) or {}
            ab = canon(t.get("abbreviation"), t.get("id"))
            if not ab:
                return None  # All-Star game, international exhibitions...
            recs = {r.get("type") or r.get("name"): r.get("summary") for r in (c.get("records") or [])}
            teams[c.get("homeAway")] = {
                "abbr": ab, "score": _int(c.get("score")),
                "record": recs.get("total") or recs.get("overall") or recs.get("Overall"),
                "logo": t.get("logo") or ((t.get("logos") or [{}])[0].get("href")),
                "linescores": [_int(x.get("value")) for x in (c.get("linescores") or [])],
            }
        if "home" not in teams or "away" not in teams:
            return None
        season = e.get("season") or {}
        nat = False
        for b in comp.get("broadcasts", []) or []:
            if (b.get("market") or "").lower() == "national":
                nat = True
        for b in comp.get("geoBroadcasts", []) or []:
            if ((b.get("market") or {}).get("type") or "").lower() == "national":
                nat = True
        periods = _int((comp.get("status") or {}).get("period")) or 4
        venue = comp.get("venue") or {}
        notes = [n.get("headline") for n in (comp.get("notes") or []) if n.get("headline")]
        day = et_day(e["date"])
        out = {
            "game_id": str(e["id"]), "date": e["date"], "day": day,
            "season": _int(season.get("year")) or season_of(day), "stype": _int(season.get("type")) or 2,
            "home": teams["home"]["abbr"], "away": teams["away"]["abbr"],
            "home_pts": teams["home"]["score"], "away_pts": teams["away"]["score"],
            "state": st.get("state"), "completed": bool(st.get("completed")), "detail": st.get("shortDetail") or st.get("detail"),
            "ot": max(0, periods - 4), "neutral": bool(comp.get("neutralSite")), "national_tv": nat,
            "venue": venue.get("fullName"), "note": notes[0] if notes else None,
            "home_logo": teams["home"]["logo"], "away_logo": teams["away"]["logo"],
            "home_record": teams["home"]["record"], "away_record": teams["away"]["record"],
            "home_lines": teams["home"]["linescores"], "away_lines": teams["away"]["linescores"],
        }
        out["odds"] = parse_odds(comp)
        return out
    except Exception:
        return None


# ------------------------------------------------------------------ market odds
def american_to_decimal(x):
    try:
        v = float(str(x).replace("+", "").strip())
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    return round(1 + (v / 100 if v > 0 else 100 / -v), 4)


def _num(x):
    try:
        return float(str(x).lstrip("ou").replace("+", ""))
    except (TypeError, ValueError):
        return None


def parse_odds(comp):
    """Moneyline (decimal), spread (home line) and total from the scoreboard odds block, if ESPN has one.
    Never raises: odds are a bonus, a game without them is still a game."""
    try:
        return _parse_odds(comp)
    except Exception as e:
        msg = f"odds block not understood: {type(e).__name__}: {e}"
        if msg not in CALLS["errors"]:
            CALLS["errors"].append(msg)
        return None


def _parse_odds(comp):
    for o in comp.get("odds") or []:
        if not isinstance(o, dict):
            continue
        out = {"provider": (o.get("provider") or {}).get("name")}
        ht, at = o.get("homeTeamOdds") or {}, o.get("awayTeamOdds") or {}
        out["ml_home"] = american_to_decimal(ht.get("moneyLine"))
        out["ml_away"] = american_to_decimal(at.get("moneyLine"))
        ml = o.get("moneyline") or {}
        if not out["ml_home"]:
            out["ml_home"] = american_to_decimal(((ml.get("home") or {}).get("close") or (ml.get("home") or {}).get("open") or {}).get("odds"))
        if not out["ml_away"]:
            out["ml_away"] = american_to_decimal(((ml.get("away") or {}).get("close") or (ml.get("away") or {}).get("open") or {}).get("odds"))
        sp = o.get("spread")
        if sp is None:
            ps = (o.get("pointSpread") or {}).get("home") or {}
            sp = _num((ps.get("close") or ps.get("open") or {}).get("line"))
        # ESPN's "spread" is the home team's line (negative = home favoured)
        out["spread_home"] = _num(sp)
        out["total"] = _num(o.get("overUnder"))
        if out["total"] is None:
            tt = (o.get("total") or {}).get("over") or {}
            out["total"] = _num((tt.get("close") or tt.get("open") or {}).get("line"))
        if any(out.get(k) for k in ("ml_home", "spread_home", "total")):
            return out
    return None


# ------------------------------------------------------------------ summary (box score)
STAT_KEYS = {
    "fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("tpm", "tpa"),
    "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"),
    "offensiveRebounds": ("oreb",), "totalRebounds": ("reb",), "rebounds": ("reb",),
    "assists": ("ast",), "turnovers": ("tov",), "totalTurnovers": ("tov",), "steals": ("stl",), "blocks": ("blk",),
}
PLAYER_FIELDS = {"min": ("minutes", "MIN"), "pts": ("points", "PTS"),
                 "fg": ("fieldGoalsMade-fieldGoalsAttempted", "FG"),
                 "tp": ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "3PT"),
                 "ft": ("freeThrowsMade-freeThrowsAttempted", "FT"), "reb": ("rebounds", "REB"),
                 "ast": ("assists", "AST"), "tov": ("turnovers", "TO"), "stl": ("steals", "STL"),
                 "blk": ("blocks", "BLK"), "oreb": ("offensiveRebounds", "OREB"), "pf": ("fouls", "PF"),
                 "pm": ("plusMinus", "+/-")}
PAIRS = {"fg": ("fgm", "fga"), "tp": ("tpm", "tpa"), "ft": ("ftm", "fta")}
LABEL_KEYS = {"FG": ("fgm", "fga"), "3PT": ("tpm", "tpa"), "FT": ("ftm", "fta"), "OR": ("oreb",), "REB": ("reb",),
              "AST": ("ast",), "TO": ("tov",), "STL": ("stl",), "BLK": ("blk",)}


def summary(game_id):
    data = fetch(f"{BASE}/summary?event={game_id}")
    return parse_summary(data) if data else None


def _split(display, keys):
    parts = str(display).replace("–", "-").split("-") if len(keys) == 2 else [display]
    vals = [_int(p) for p in parts]
    return dict(zip(keys, vals)) if len(vals) == len(keys) else {}


def parse_summary(s):
    """Team box (fgm..blk) and player lines (min, pts, reb, ast) from a summary payload."""
    box = s.get("boxscore") or {}
    teams = {}
    for t in box.get("teams", []) or []:
        tm = t.get("team", {}) or {}
        ab = canon(tm.get("abbreviation"), tm.get("id"))
        if not ab:
            continue
        vals = {}
        for st in t.get("statistics", []) or []:
            keys = STAT_KEYS.get(st.get("name")) or LABEL_KEYS.get(st.get("label") or st.get("abbreviation"))
            if keys and not all(k in vals for k in keys):
                vals.update({k: v for k, v in _split(st.get("displayValue"), keys).items() if v is not None})
        teams[ab] = vals
    players = []
    for blk in box.get("players", []) or []:
        tm = blk.get("team", {}) or {}
        ab = canon(tm.get("abbreviation"), tm.get("id"))
        if not ab:
            continue
        for grp in blk.get("statistics", []) or []:
            keys = [str(k) for k in (grp.get("keys") or [])]
            labels = [str(k).upper() for k in (grp.get("labels") or grp.get("names") or [])]
            cols = {}
            for field, (key, label) in PLAYER_FIELDS.items():
                if key in keys:
                    cols[field] = keys.index(key)
                elif label in labels:
                    cols[field] = labels.index(label)
            for a in grp.get("athletes", []) or []:
                ath = a.get("athlete", {}) or {}
                stats = a.get("stats") or []
                dnp = bool(a.get("didNotPlay")) or not stats
                row = {"team": ab, "player_id": str(ath.get("id") or ath.get("displayName")),
                       "name": ath.get("displayName") or ath.get("shortName"),
                       "pos": (ath.get("position") or {}).get("abbreviation"), "jersey": ath.get("jersey"),
                       "starter": int(bool(a.get("starter"))), "dnp_reason": (a.get("reason") or "") if dnp else ""}
                for field, i in cols.items():
                    v = stats[i] if (not dnp and i < len(stats)) else None
                    if field in PAIRS:
                        m_, a_ = PAIRS[field]
                        parts = str(v).replace("\u2013", "-").split("-") if v not in (None, "", "--") else []
                        row[m_] = _int(parts[0]) if len(parts) == 2 else (0 if not dnp else None)
                        row[a_] = _int(parts[1]) if len(parts) == 2 else (0 if not dnp else None)
                    else:
                        row[field] = _int(v) if v not in (None, "", "--") else (0 if not dnp else None)
                if dnp:
                    row["min"] = 0
                    for k in ("pts", "reb", "ast"):
                        row[k] = 0
                players.append(row)
            break  # first statistics group holds the full line
    injuries = parse_injury_blocks(s.get("injuries") or [])
    return {"teams": teams, "players": players, "injuries": injuries}


# ------------------------------------------------------------------ injuries
STATUS_W = {"out": 1.0, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.3, "probable": 0.1}


def status_weight(status):
    s = (status or "").lower()
    for k, w in STATUS_W.items():
        if k in s:
            return w
    return 0.0


def parse_injury_blocks(blocks):
    out = {}
    for b in blocks or []:
        tm = b.get("team") or {}
        ab = canon(tm.get("abbreviation") or b.get("abbreviation"), tm.get("id") or b.get("id"))
        if not ab:
            continue
        lst = out.setdefault(ab, [])
        for inj in b.get("injuries", []) or []:
            ath = inj.get("athlete") or {}
            status = inj.get("status") or (inj.get("type") or {}).get("description")
            det = inj.get("details") or {}
            lst.append({
                "player_id": str(ath.get("id") or ath.get("displayName")), "name": ath.get("displayName"),
                "status": status, "weight": status_weight(status),
                "detail": inj.get("shortComment") or det.get("type") or "",
                "returns": det.get("returnDate"),
            })
    return out


def injuries():
    data = fetch(f"{BASE}/injuries")
    if not data:
        return None
    return parse_injury_blocks(data.get("injuries") or [])


def teams_meta():
    """Logos per team from the teams endpoint."""
    data = fetch(f"{BASE}/teams")
    out = {}
    try:
        for t in data["sports"][0]["leagues"][0]["teams"]:
            t = t["team"]
            ab = canon(t.get("abbreviation"), t.get("id"))
            if ab:
                out[ab] = {"logo": (t.get("logos") or [{}])[0].get("href")}
    except (TypeError, KeyError, IndexError):
        pass
    return out


def now_utc():
    return datetime.now(timezone.utc)
