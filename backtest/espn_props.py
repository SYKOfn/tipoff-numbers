"""Past player prop lines from ESPN's public odds API (free), for replay tests with a real market.

ESPN keeps each game's player props from the book it partners with: ESPN BET for 2024-25 and October-November
2025, DraftKings from 2026-27. Every prop has its opening and its latest (closing) line and both prices.

    python -m backtest.espn_props fetch 2025        # raw replies cached in /tmp/espn_props/
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
CACHE = Path("/tmp/espn_props")
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


def fetch(season):
    g = load_games()
    gids = g[(g.season == season) & (g.stype == 2)].sort_values("date").game_id.astype(str).tolist()
    CACHE.mkdir(exist_ok=True)
    for i, gid in enumerate(gids):
        f = CACHE / f"{gid}.json"
        if f.exists():
            continue
        od = _get(f"{B}/{gid}/competitions/{gid}/odds") or {}
        time.sleep(PAUSE)
        out = {"provider": None, "items": []}
        for it in od.get("items", []):
            pid, name = it["provider"]["id"], it["provider"]["name"]
            if "Live" in name:
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
        f.write_text(json.dumps(out))
        if i % 50 == 0:
            print(f"{i}/{len(gids)} {gid} {out['provider']} {len(out['items'])}", flush=True)


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


if __name__ == "__main__":
    {"fetch": fetch, "parse": parse}[sys.argv[1]](int(sys.argv[2]))
