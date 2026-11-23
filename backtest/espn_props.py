"""Past player prop lines from ESPN's public odds API (free), for replay tests with a real market.

ESPN keeps each game's player props from the book it partners with: ESPN BET for 2024-25 and October-November
2025, DraftKings from 2026-27. Every prop has its opening and its latest (closing) line and both prices.

    python -m backtest.espn_props fetch 2025        # raw replies cached in ~/.cache/tipoff_espn/
    python -m backtest.espn_props fetch 2024 40,47,45,31,58   # 2022-24: DraftKings, else MGM, Caesars, ESPN BET
    python -m backtest.espn_props parse 2025        # -> data/props/espn_{season}.csv

Rows: game_id, player_id, player, stat, line, over, under, book, phase (open/close). The main line is the pair
priced closest to even money. Each entry names its side ("over"/"under" under current and open); the order
varies, so it is never inferred from position. Unlabelled pairs are skipped.
"""
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

from pipeline.store import ROOT, load_games, load_players

B = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events"
CACHE = Path.home() / ".cache" / "tipoff_espn"  # outside /tmp, which a restart clears
TYPES = {"Total Points": "pts", "Total Rebounds": "reb", "Total Assists": "ast", "Total 3-Point Field Goals": "tpm",
         "Total Points, Rebounds, and Assists": "pra"}
PAUSE = 0.3


def _get(url):
    for k in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(2 + 3 * k)
    return None


def fetch(season, prefer=None):
    """prefer: provider ids to try first, in order (e.g. "40,47,45,31" = DraftKings, MGM, Caesars for 2022-24,
    where ESPN lists several books and the first in its own order may have no props)."""
    order = [x for x in str(prefer or "").split(",") if x]
    g = load_games()
    gids = g[(g.season == season) & (g.stype == 2)].sort_values("date").game_id.astype(str).tolist()
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [gid for gid in gids if not (CACHE / f"{gid}.json").exists()]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:  # six at a time, like fetch_ml
        for i, (gid, out) in enumerate(zip(todo, ex.map(lambda x: _fetch_game(x, order), todo))):
            if i % 50 == 0:
                print(f"{i}/{len(todo)} {gid} {out['provider']} {len(out['items'])}", flush=True)


def _fetch_game(gid, order):
    f = CACHE / f"{gid}.json"
    od = _get(f"{B}/{gid}/competitions/{gid}/odds") or {}
    time.sleep(PAUSE)
    out = {"provider": None, "items": []}
    provs = sorted(od.get("items", []), key=lambda it: order.index(it["provider"]["id"]) if it["provider"]["id"] in order else len(order))
    for it in provs:
        pid, name = it["provider"]["id"], it["provider"]["name"]
        if "Live" in name or (order and pid not in order):
            continue
        items, page = [], 1
        while True:
            pb = _get(f"{B}/{gid}/competitions/{gid}/odds/{pid}/propBets?limit=1000&page={page}") or {}
            time.sleep(PAUSE)
            items += pb.get("items", [])
            if page >= (pb.get("pageCount") or 1):
                break
            page += 1
        if items:
            out = {"provider": name, "items": items}
            break
    tmp = f.with_suffix(".part")
    tmp.write_text(json.dumps(out))
    tmp.rename(f)  # whole files only, so an interrupted fetch resumes cleanly
    return out


def _dec(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def parse(season):
    g = load_games()
    gids = g[(g.season == season) & (g.stype == 2)].game_id.astype(str).tolist()
    pl = load_players()
    names = dict(zip(pl.player_id.astype(str), pl.name))
    rows = []
    for gid in gids:
        f = CACHE / f"{gid}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        groups = {}
        for it in d.get("items", []):
            st = TYPES.get((it.get("type") or {}).get("name"))
            o = it.get("odds") or {}
            if not st or not o.get("total"):
                continue
            ath = str(it["athlete"]["$ref"].split("/athletes/")[1].split("?")[0])
            groups.setdefault((ath, st, o["total"].get("value")), []).append(it)
        best = {}
        for (ath, st, line), its in groups.items():
            side = {}
            for x in its:  # each entry says which side it prices ("over"/"under" under current and open)
                cur = x.get("current") or {}
                k = "over" if "over" in cur else "under" if "under" in cur else None
                if k:
                    side[k] = x
            if len(side) != 2:
                continue  # unlabelled, a milestone or a one-sided alternate line
            c_o, c_u = _dec(side["over"]["current"]["over"].get("decimal")), _dec(side["under"]["current"]["under"].get("decimal"))
            if not c_o or not c_u:
                continue
            gap = abs(c_o - c_u)
            if (ath, st) not in best or gap < best[(ath, st)][0]:
                op_o, op_u = (side["over"].get("open") or {}), (side["under"].get("open") or {})
                o_o = _dec((op_o.get("over") or {}).get("decimal")); o_u = _dec((op_u.get("under") or {}).get("decimal"))
                o_line = (op_o.get("target") or {}).get("value")
                best[(ath, st)] = (gap, float(line), c_o, c_u, o_line, o_o, o_u)
        for (ath, st), (_, line, c_o, c_u, o_line, o_o, o_u) in best.items():
            base = {"game_id": gid, "player_id": ath, "player": names.get(ath, ath), "stat": st, "book": d["provider"]}
            rows.append({**base, "line": line, "over": c_o, "under": c_u, "phase": "close"})
            if o_line is not None and o_o and o_u:
                rows.append({**base, "line": float(o_line), "over": o_o, "under": o_u, "phase": "open"})
    out = ROOT / "data" / "props" / f"espn_{season}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["game_id", "player_id", "player", "stat", "line", "over", "under", "book", "phase"])
        w.writeheader()
        w.writerows(rows)
    print(f"{out}: {len(rows)} rows, {len({r['game_id'] for r in rows})} games")


def load(season, phase="close"):
    """{(game_id, normalised player name, stat): {line, over, under, book}} in the live pipeline's format."""
    from pipeline.oddsapi import norm_name
    f = ROOT / "data" / "props" / f"espn_{season}.csv"
    out = {}
    if f.exists():
        with open(f) as fh:
            for r in csv.DictReader(fh):
                if r["phase"] == phase:
                    out[(r["game_id"], norm_name(r["player"]), r["stat"])] = {
                        "line": float(r["line"]), "over": float(r["over"]), "under": float(r["under"]), "book": r["book"]}
    return out


def parse_all(season):
    """Every labelled over/under pair (all lines, not just the main one) -> data/props/espn_all_{season}.csv
    (kept locally, not committed: about 50 MB a season). For testing the model where tickets bet (80%+ lines)."""
    g = load_games()
    gids = g[(g.season == season) & (g.stype == 2)].game_id.astype(str).tolist()
    out = ROOT / "data" / "props" / f"espn_all_{season}.csv"
    n = 0
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["game_id", "player_id", "stat", "line", "over", "under", "o_line", "o_over", "o_under"])
        for gid in gids:
            f = CACHE / f"{gid}.json"
            if not f.exists():
                continue
            groups = {}
            for it in json.loads(f.read_text()).get("items", []):
                st = TYPES.get((it.get("type") or {}).get("name"))
                o = it.get("odds") or {}
                cur = it.get("current") or {}
                side = "over" if "over" in cur else "under" if "under" in cur else None
                if not st or not o.get("total") or not side:
                    continue
                ath = str(it["athlete"]["$ref"].split("/athletes/")[1].split("?")[0])
                groups.setdefault((ath, st, o["total"].get("value")), {})[side] = it
            for (ath, st, line), sd in groups.items():
                if len(sd) != 2:
                    continue
                co, cu = _dec(sd["over"]["current"]["over"].get("decimal")), _dec(sd["under"]["current"]["under"].get("decimal"))
                if not co or not cu:
                    continue
                op_o, op_u = sd["over"].get("open") or {}, sd["under"].get("open") or {}
                w.writerow([gid, ath, st, float(line), co, cu, (op_o.get("target") or {}).get("value"),
                            _dec((op_o.get("over") or {}).get("decimal")), _dec((op_u.get("under") or {}).get("decimal"))])
                n += 1
    print(f"{out}: {n} line pairs")


def _ml_row(gid):
    od = _get(f"{B}/{gid}/competitions/{gid}/odds") or {}
    for it in od.get("items", []):
        name = it["provider"]["name"]
        if "Live" in name:
            continue
        h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
        dec = lambda o, k: (((o.get(k) or {}).get("moneyLine") or {}).get("decimal"))
        hc, ac = dec(h, "close") or dec(h, "current"), dec(a, "close") or dec(a, "current")
        if hc and ac:
            return [name, dec(h, "open"), dec(a, "open"), hc, ac]
    for it in od.get("items", []):  # before 2023-24 the books only give American odds (the latest line)
        name = it["provider"]["name"]
        if "Live" in name or name in ("accuscore", "numberfire", "teamrankings"):
            continue
        h, a = (it.get("homeTeamOdds") or {}).get("moneyLine"), (it.get("awayTeamOdds") or {}).get("moneyLine")
        if h and a:
            return [name, None, None, round(_us(h), 3), round(_us(a), 3)]
    return None


def _us(x):
    x = float(x)
    return 1 + (x / 100 if x > 0 else 100 / -x)


def fetch_ml(season):
    """Each game's pre-game moneyline (open and close, decimal) from ESPN's partner book ->
    data/odds/espn_ml_{season}.csv. Used by the replay (REPLAY_ML=1) to price winner legs like live."""
    from concurrent.futures import ThreadPoolExecutor
    g = load_games()
    g = g[(g.season == season)].sort_values("date")
    out = ROOT / "data" / "odds" / f"espn_ml_{season}.csv"
    have = set()
    if out.exists():
        with open(out) as f:
            have = {r["game_id"] for r in csv.DictReader(f)}
    todo = [(gid, d) for gid, d in zip(g.game_id.astype(str), g.date.astype(str)) if gid not in have]
    new = not out.exists()
    with open(out, "a", newline="") as f, ThreadPoolExecutor(6) as ex:
        w = csv.writer(f)
        if new:
            w.writerow(["game_id", "date", "book", "ml_home_open", "ml_away_open", "ml_home", "ml_away"])
        for i, ((gid, d), r) in enumerate(zip(todo, ex.map(lambda x: _ml_row(x[0]), todo))):
            if r:
                w.writerow([gid, d] + r)
            if i % 100 == 0:
                f.flush()
                print(f"{i}/{len(todo)} {gid}", flush=True)


if __name__ == "__main__":
    {"fetch": fetch, "parse": parse, "parse_all": parse_all, "fetch_ml": fetch_ml}[sys.argv[1]](int(sys.argv[2]), *sys.argv[3:])
