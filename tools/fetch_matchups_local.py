"""Download NBA.com per-game defender matchups (who guarded whom) into data/history/matchups_<season>.csv.gz.
Local-only: stats.nba.com closes the connection from GitHub Actions runners (see tests/fixtures/nba_matchups_probe.json),
so this can't run in CI like tools/nba_matchups.py's probe. Run it from a normal network and commit the result.
Usage: python3 -m tools.fetch_matchups_local 2025-26 [2024-25 ...]   Resumable; ~1 request per second."""
import csv, gzip, io, json, os, sys, time, random
import requests
DEADLINE = time.time() + float(os.environ.get("FETCH_SECS", "1e9"))

H = {"Host": "stats.nba.com", "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip, deflate, br",
     "x-nba-stats-origin": "stats", "x-nba-stats-token": "true", "Connection": "keep-alive", "Referer": "https://www.nba.com/",
     "Origin": "https://www.nba.com", "Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "history")
COLS = ["game_id", "date", "def_team", "def_id", "def_name", "off_id", "off_name", "secs", "poss", "pct_def", "pct_off",
        "pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "ast", "tov", "blk", "sw"]
S = requests.Session()


def get(url, tries=2):
    for i in range(tries):
        try:
            r = S.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            pass
        time.sleep(20 * (i + 1))
    return None


def games(season):
    d = get(f"https://stats.nba.com/stats/leaguegamelog?Counter=0&Direction=ASC&LeagueID=00&PlayerOrTeam=T&Season={season}&SeasonType=Regular%20Season&Sorter=DATE")
    rs = d["resultSets"][0]; i = {k: n for n, k in enumerate(rs["headers"])}
    out = {}
    for r in rs["rowSet"]:
        out[r[i["GAME_ID"]]] = r[i["GAME_DATE"]]
    return out


def rows(gid, date, d):
    b = d["boxScoreMatchups"]
    for side in ("homeTeam", "awayTeam"):
        t = b[side]
        for p in t["players"]:
            for m in p.get("matchups") or []:
                s = m["statistics"]
                yield [gid, date, t["teamTricode"], p["personId"], p["nameI"], m["personId"], m["nameI"], s["matchupMinutesSort"],
                       s["partialPossessions"], s["percentageDefenderTotalTime"], s["percentageOffensiveTotalTime"], s["playerPoints"],
                       s["matchupFieldGoalsMade"], s["matchupFieldGoalsAttempted"], s["matchupThreePointersMade"],
                       s["matchupThreePointersAttempted"], s["matchupFreeThrowsMade"], s["matchupFreeThrowsAttempted"],
                       s["matchupAssists"], s["matchupTurnovers"], s["matchupBlocks"], s["switchesOn"]]


def run(season):
    os.makedirs(DIR, exist_ok=True)
    f = os.path.join(DIR, f"matchups_{season}.csv.gz")
    done = set()
    if os.path.exists(f):
        with gzip.open(f, "rt") as fh:
            done = {r["game_id"] for r in csv.DictReader(fh)}
    gl = games(season)
    todo = [g for g in sorted(gl) if g not in done]
    print(season, len(gl), "games,", len(todo), "to fetch", flush=True)
    new = not os.path.exists(f)
    if new:
        with gzip.open(f, "wt") as fh:
            csv.writer(fh).writerow(COLS)
    if True:
        from concurrent.futures import ThreadPoolExecutor
        def one(g):
            time.sleep(1.0 + random.random() * 0.8)
            return g, get(f"https://stats.nba.com/stats/boxscorematchupsv3?GameID={g}&LeagueID=00")
        with ThreadPoolExecutor(1) as ex:
            for i in range(0, len(todo), 5):
                if time.time() > DEADLINE:
                    print(season, "paused at", i, flush=True)
                    return False
                got = list(ex.map(one, todo[i:i + 5]))
                buf = io.StringIO(); w = csv.writer(buf)
                for g, d in got:
                    if d:
                        for r in rows(g, gl[g], d):
                            w.writerow(r)
                    else:
                        print("failed", g, flush=True)
                with gzip.open(f, "at") as fh:  # one complete gzip member per batch: an interrupted run never corrupts the file
                    fh.write(buf.getvalue())
                if i % 50 == 0:
                    print(season, i, "/", len(todo), flush=True)
    print(season, "done", flush=True)
    return True


if __name__ == "__main__":
    for s in sys.argv[1:]:
        if not run(s):
            break
