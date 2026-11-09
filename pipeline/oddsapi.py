"""Real bookmaker prices from The Odds API (the-odds-api.com), switched on by a GitHub secret.

ODDS_API_KEY        the key (free plan: 500 credits a month)
ODDS_API_BOOKS      bookmakers for game odds, default "winamax_fr,pinnacle"
                    (Winamax = the prices you bet at; Pinnacle = the sharpest closing line, for CLV)
ODDS_API_DAILY      credits the site may spend per day, default 15 (fits the free plan)
ODDS_API_PROPS      "1" to also record US player-prop lines (5 credits per game per snapshot;
                    needs a paid plan in practice)

Game odds cost 3 credits per call for every NBA game at once. They are fetched when the last snapshot
is 3+ hours old, and again in the 75 minutes before each slate's first tip-off (the closing price).
Every snapshot is archived in data/odds/ so opening and closing prices can be compared later.
Player-prop lines are archived in data/props/lines.csv: the real lines the player model is tested on.
"""
import csv
import json
import os
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .store import DATA, STATE, read_json, write_json
from .teams import TEAMS

BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"
PROP_MARKETS = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "tpm",
                "player_points_rebounds_assists": "pra"}
PROPS_CSV = DATA / "props" / "lines.csv"
PROPS_COLS = ["fetched_at", "game_id", "day", "player", "stat", "line", "over", "under", "book", "phase"]


def env(name, default):
    """GitHub passes unset variables as empty strings: treat those as unset."""
    v = (os.environ.get(name) or "").strip()
    return v or default


def key():
    return env("ODDS_API_KEY", "").strip().strip('"').strip("'")


def _get(path, params):
    params = {**params, "apiKey": key()}
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tipoff-numbers"}), timeout=30) as r:
            used = r.headers.get("x-requests-last")
            remaining = r.headers.get("x-requests-remaining")
            return json.loads(r.read().decode()), int(float(used or 0)), remaining
    except Exception as e:  # never let the odds feed break the site
        return {"error": str(e)}, 0, None


def team_of(name):
    n = (name or "").lower()
    for ab, t in TEAMS.items():
        if t[2].lower() in n:
            return ab
    return None


def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    for suf in (" jr.", " jr", " sr.", " iii", " ii", " iv"):
        s = s.replace(suf, "")
    return "".join(ch for ch in s if ch.isalnum() or ch == " ").strip()


def match_game(ev, upcoming):
    h, a = team_of(ev.get("home_team")), team_of(ev.get("away_team"))
    t = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
    best = None
    for g in upcoming:
        if g["home"] == h and g["away"] == a:
            gt = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
            d = abs((gt - t).total_seconds())
            if d < 36 * 3600 and (best is None or d < best[0]):
                best = (d, g)
    return best[1] if best else None


def parse_game_markets(ev, home, away):
    """{book: {ml_home, ml_away, spread_home, spread_price_home, spread_price_away, total, over, under}}"""
    out = {}
    for bk in ev.get("bookmakers") or []:
        o = {"last_update": bk.get("last_update")}
        for m in bk.get("markets") or []:
            for oc in m.get("outcomes") or []:
                side = team_of(oc.get("name"))
                if m["key"] == "h2h":
                    if side == home:
                        o["ml_home"] = oc.get("price")
                    elif side == away:
                        o["ml_away"] = oc.get("price")
                elif m["key"] == "spreads":
                    if side == home:
                        o["spread_home"], o["spread_price_home"] = oc.get("point"), oc.get("price")
                    elif side == away:
                        o["spread_price_away"] = oc.get("price")
                elif m["key"] == "totals":
                    if (oc.get("name") or "").lower() == "over":
                        o["total"], o["over"] = oc.get("point"), oc.get("price")
                    elif (oc.get("name") or "").lower() == "under":
                        o["under"] = oc.get("price")
        out[bk["key"]] = o
    return out


def budget():
    st = read_json(STATE / "oddsapi.json", {}) or {}
    today = datetime.now(timezone.utc).date().isoformat()
    if st.get("day") != today:
        st = {"day": today, "spent": 0, "last_games": st.get("last_games"), "props_done": st.get("props_done", {})}
    return st


def collect(upcoming, now=None):
    """Adds real odds to the upcoming games in place; archives snapshots. Returns a status dict."""
    if not key():
        return {"enabled": False}
    now = now or datetime.now(timezone.utc)
    st = budget()
    try:
        daily = int(float(env("ODDS_API_DAILY", "15")))
    except ValueError:
        daily = 15
    books = env("ODDS_API_BOOKS", "winamax_fr,pinnacle")
    tips = sorted(datetime.fromisoformat(g["date"].replace("Z", "+00:00")) for g in upcoming if g.get("state") == "pre")
    soon = any(timedelta(0) <= t - now <= timedelta(minutes=75) for t in tips)
    last = datetime.fromisoformat(st["last_games"]) if st.get("last_games") else None
    due = last is None or now - last >= timedelta(hours=3) or (soon and now - last >= timedelta(minutes=50))
    status = {"enabled": True, "books": books, "fetched": False}
    snap = read_json(STATE / "odds_latest.json", {}) or {}
    if due and st["spent"] + 3 <= daily:
        data, used, remaining = _get("/odds", {"bookmakers": books, "markets": "h2h,spreads,totals", "oddsFormat": "decimal"})
        st["spent"] += used or 3
        status["remaining"] = remaining
        if isinstance(data, list):
            st["last_games"] = now.isoformat()
            status["fetched"] = True
            arch = DATA / "odds" / f"{now.date().isoformat()}.jsonl"
            arch.parent.mkdir(parents=True, exist_ok=True)
            with open(arch, "a") as f:
                for ev in data:
                    g = match_game(ev, upcoming)
                    if not g:
                        continue
                    mk = parse_game_markets(ev, g["home"], g["away"])
                    snap[g["game_id"]] = {"at": now.isoformat(), "event_id": ev["id"], "books": mk}
                    f.write(json.dumps({"at": now.isoformat(), "game_id": g["game_id"], "books": mk}) + "\n")
        else:
            err = data.get("error") or ""
            status["error"] = ("the key was refused (401): check the ODDS_API_KEY secret is exactly the key from the-odds-api.com"
                               if "401" in err else err)
    write_json(STATE / "odds_latest.json", snap)
    # props (optional): an "open" snapshot when a game is within 12 h, a "close" one within 75 min
    if env("ODDS_API_PROPS", "0") == "1":
        done = st.setdefault("props_done", {})
        for g in upcoming:
            if g.get("state") != "pre" or g["game_id"] not in snap:
                continue
            t = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
            left = t - now
            phase = "close" if left <= timedelta(minutes=75) else "open" if left <= timedelta(hours=12) else None
            if not phase or phase in done.get(g["game_id"], []) or st["spent"] + 5 > daily:
                continue
            data, used, _ = _get(f"/events/{snap[g['game_id']]['event_id']}/odds",
                                 {"regions": "us", "markets": ",".join(PROP_MARKETS), "oddsFormat": "decimal"})
            st["spent"] += used or 5
            if isinstance(data, dict) and data.get("bookmakers"):
                archive_props(data, g, now, phase)
                done.setdefault(g["game_id"], []).append(phase)
    write_json(STATE / "oddsapi.json", st)
    attach(upcoming)
    return status


def archive_props(ev, g, now, phase):
    rows = {}
    for bk in ev.get("bookmakers") or []:
        for m in bk.get("markets") or []:
            st = PROP_MARKETS.get(m["key"])
            if not st:
                continue
            for oc in m.get("outcomes") or []:
                k = (oc.get("description"), st, oc.get("point"), bk["key"])
                r = rows.setdefault(k, {"fetched_at": now.isoformat(), "game_id": g["game_id"], "day": g["day"],
                                        "player": oc.get("description"), "stat": st, "line": oc.get("point"),
                                        "over": None, "under": None, "book": bk["key"], "phase": phase})
                r["over" if (oc.get("name") or "").lower() == "over" else "under"] = oc.get("price")
    PROPS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not PROPS_CSV.exists()
    with open(PROPS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PROPS_COLS)
        if new:
            w.writeheader()
        for r in rows.values():
            if r["over"] and r["under"]:
                w.writerow(r)


def attach(upcoming):
    """Put the freshest real prices on each upcoming game: g['odds'] (preferred book, ESPN fallback stays
    if missing) and g['odds_books'] (every book we have)."""
    snap = read_json(STATE / "odds_latest.json", {}) or {}
    pref = [b.strip() for b in env("ODDS_API_BOOKS", "winamax_fr,pinnacle").split(",")]
    for g in upcoming:
        s = snap.get(g["game_id"])
        if not s:
            continue
        g["odds_books"] = s["books"]
        for b in pref:
            o = s["books"].get(b)
            if o and o.get("ml_home"):
                g["odds"] = {"provider": b, **o}
                break


def latest_props():
    """{(game_id, normalised player, stat): {line, over, under, book, phase}} - latest snapshot, median line."""
    if not PROPS_CSV.exists():
        return {}
    groups = {}
    with open(PROPS_CSV) as f:
        for r in csv.DictReader(f):
            groups.setdefault((r["game_id"], norm_name(r["player"]), r["stat"]), []).append(r)
    out = {}
    for k, rows in groups.items():
        last = max(r["fetched_at"] for r in rows)
        cur = [r for r in rows if r["fetched_at"] == last]
        # the main line: the one priced closest to even money
        out[k] = min(cur, key=lambda r: abs(float(r["over"]) - float(r["under"])))
    return out


def first_last_props():
    """{(game_id, player, stat): (open row, close row)} for the model test and prop CLV."""
    if not PROPS_CSV.exists():
        return {}
    groups = {}
    with open(PROPS_CSV) as f:
        for r in csv.DictReader(f):
            groups.setdefault((r["game_id"], norm_name(r["player"]), r["stat"]), []).append(r)
    out = {}
    for k, rows in groups.items():
        def main(ph):
            c = [r for r in rows if r["phase"] == ph]
            if not c:
                return None
            last = max(r["fetched_at"] for r in c)
            c = [r for r in c if r["fetched_at"] == last]
            return min(c, key=lambda r: abs(float(r["over"]) - float(r["under"])))
        out[k] = (main("open"), main("close") or main("open"))
    return out
