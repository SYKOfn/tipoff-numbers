"""The NBA's official injury report at the ticket lock, for a leak-free season replay.

The league posts its injury report as static PDFs (ak-static.cms.nba.com). For every game day this fetches the report
at or just before the 16:00 ET ticket lock (22:00 Madrid), parses it, matches names to our player ids and writes
data/history/injury_status.csv.gz: date, team, player_id, name, status, report_time, note
(note "gleague" = two-way / G League assignment, "unsubmitted" = the team had not filed yet, player columns empty).
Players absent from the report are healthy as far as their team says.

    python -m backtest.injury_reports [FIRST_DAY LAST_DAY]     (default: every game day from 2018-12-18)

PDFs are cached in ~/.cache/tipoff_injury/pdf (a missing file answers 403 and is cached as an empty file).
"""
import csv
import gzip
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

CACHE = Path.home() / ".cache" / "tipoff_injury" / "pdf"
URL = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_%s_%s.pdf"
UA = "Mozilla/5.0 (compatible; research-replay/1.0; personal non-commercial use)"
OUT = Path(__file__).resolve().parent.parent / "data" / "history" / "injury_status.csv.gz"
FIRST = "2018-12-18"   # no reports before this day
NEW_ERA = "2025-12-22"
PREV_FALLBACK_FROM = "2026-08-01"  # last season's names as a fallback (added for 2026-27; earlier rows kept as built)  # file names become _HH_MMPM (every 15 minutes)
STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "Available")
ST = re.compile(r"\b(Out|Doubtful|Questionable|Probable|Available)\b")
DROP = {"jr", "sr", "ii", "iii", "iv"}
# the replay's play rates by status (fit_rates below) live in model/player_engine.py LOCK_PLAY


def lock_times(day):
    """Report file stamps to try, latest first, at or before 16:00 ET."""
    if day >= NEW_ERA:
        return ["04_00PM", "03_45PM", "03_30PM", "03_15PM", "03_00PM", "02_30PM", "02_00PM", "01_00PM"]
    return ["03PM", "02PM", "01PM", "12PM"]


def fetch(day, stamp):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{day}_{stamp}.pdf"
    if f.exists():
        return f if f.stat().st_size else None
    try:
        data = urllib.request.urlopen(urllib.request.Request(URL % (day, stamp), headers={"User-Agent": UA}),
                                      timeout=30).read()
    except Exception:
        data = b""
    time.sleep(0.3)
    f.write_bytes(data if data[:4] == b"%PDF" else b"")
    return f if f.stat().st_size else None


def lock_report(day):
    for t in lock_times(day):
        f = fetch(day, t)
        if f:
            return f
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum() or ch == " ").strip()


def compact(s):
    """norm_name rules (pipeline/oddsapi.py) with spaces dropped: the 2025-26 PDFs glue words together."""
    return "".join(w for w in norm(s.replace(".", " ")).split() if w not in DROP)  # glued "OubreJr." -> strip_suffix


def strip_suffix(c):
    for suf in ("jr", "sr", "iii", "ii", "iv"):
        if c.endswith(suf) and len(c) > len(suf) + 2:
            return c[:-len(suf)]
    return c


def team_patterns():
    from pipeline.teams import TEAMS
    return [(ab, re.compile(r"\s*".join(re.escape(w) for w in t[1].split()))) for ab, t in TEAMS.items()]


DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
PREFIX = re.compile(r"\d{2}/\d{2}/\d{4}|\d{2}:\d{2}\s*\(ET\)|[A-Z]{2,3}\s*@\s*[A-Z]{2,3}")


def parse(f, pats):
    """[(game_date, team, last_compact, first_compact, status, gleague, raw)], report stamp, unsubmitted teams."""
    import pdfplumber
    out, unsub, stamp = [], [], None
    team, gdate = None, None
    with pdfplumber.open(f) as p:
        for pg in p.pages:
            for ln in (pg.extract_text() or "").split("\n"):
                if ln.startswith("Injury Report:"):
                    stamp = ln.split(":", 1)[1].strip()
                    continue
                m = DATE.search(ln)
                if m:
                    gdate = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
                pos = None
                for ab, pat in pats:
                    mt = pat.search(ln)
                    if mt and (pos is None or mt.start() < pos[1]):
                        pos = (ab, mt.start(), mt.end())
                if pos:
                    team = pos[0]
                    ln_ = ln[pos[2]:]
                else:
                    ln_ = PREFIX.sub(" ", ln)
                if "NOT YET SUBMITTED" in ln_.upper().replace(" ", " "):
                    if pos:
                        unsub.append((gdate, team))
                    continue
                if "," not in ln_:
                    continue
                left, right = ln_.split(",", 1)
                left = PREFIX.sub(" ", left).strip()
                mm = re.match(r"\s*([A-Za-z'.\-]+)\s*(.*)", right)
                if not mm or not left:
                    continue
                first, rest = mm.groups()
                s = ST.search(rest)
                if not s:
                    continue
                gl = "gleague" in rest.lower().replace(" ", "").replace("-", "")
                out.append((gdate, team, compact(left), compact(first), s.group(1), gl, ln.strip()))
    return out, stamp, unsub


def rosters(seasons):
    """{(season, team): {compact full name: (player_id, name)}} from our box scores, plus every season's names."""
    import pandas as pd
    from pipeline.store import HIST
    ros, allp = defaultdict(dict), defaultdict(dict)
    for s in seasons:
        f = HIST / f"players_{s}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f, usecols=["team", "player_id", "name"], dtype={"player_id": str}).drop_duplicates()
        for t, pid, nm in zip(d["team"], d["player_id"], d["name"]):
            ros[(s, t)][compact(nm)] = (pid, nm)
            allp[s][compact(nm)] = (pid, nm)
    return ros, allp


def match(last, first, cands):
    """Player in cands {compact full: (pid, name)} for a report name ("Last", "First")."""
    for lc in {last, strip_suffix(last)}:
        if first + lc in cands:
            return cands[first + lc]
    hit = [v for pc, v in cands.items() if pc.startswith(first) and pc.endswith(strip_suffix(last))]
    if len(hit) == 1:
        return hit[0]
    hit = [v for pc, v in cands.items() if pc.endswith(strip_suffix(last)) and len(strip_suffix(last)) >= 4]
    if len(hit) == 1:
        return hit[0]
    hit = [v for pc, v in cands.items() if pc.startswith(first[:3]) and strip_suffix(last)[:5] and strip_suffix(last)[:5] in pc]
    return hit[0] if len(hit) == 1 else None


def season_of(day):
    return int(day[:4]) + (1 if int(day[5:7]) >= 8 else 0)


def game_days(d0=FIRST, d1="2099-12-31"):
    from pipeline.store import load_games
    g = load_games()
    g = g[g["home_pts"].notna()]
    out = defaultdict(set)
    for d, h, a in zip(g["day"], g["home"], g["away"]):
        if d0 <= d <= d1:
            out[d] |= {h, a}
    return dict(sorted(out.items()))


def build(d0=FIRST, d1="2099-12-31"):
    days = game_days(d0, d1)
    pats = team_patterns()
    ros, allp = rosters(sorted({season_of(d) + k for d in days for k in (-1, 0)}))
    rows, miss_days, stats = [], [], Counter()
    unmatched = Counter()
    for i, (day, teams) in enumerate(days.items()):
        f = lock_report(day)
        if not f:
            miss_days.append(day)
            continue
        try:
            ent, stamp, unsub = parse(f, pats)
        except Exception as e:
            print(day, "parse failed:", e, flush=True)
            miss_days.append(day)
            continue
        s = season_of(day)
        rt = f.stem.split("_", 1)[1]
        for gd, t in unsub:
            if gd in (None, day) and t in teams:
                rows.append({"date": day, "team": t, "player_id": "", "name": "", "status": "", "report_time": rt,
                             "note": "unsubmitted"})
                stats["unsubmitted"] += 1
        for gd, t, last, first, st, gl, raw in ent:
            if gd not in (None, day) or t not in teams:
                continue
            hit = match(last, first, ros.get((s, t), {})) or match(last, first, allp.get(s, {}))
            if not hit and d0 >= PREV_FALLBACK_FROM:  # not yet in this season's box scores: last season's names
                hit = match(last, first, ros.get((s - 1, t), {})) or match(last, first, allp.get(s - 1, {}))
            stats["rows"] += 1
            if not gl:
                stats["nongl"] += 1
                stats["nongl_matched"] += bool(hit)
                if not hit:
                    unmatched[(t, last, first)] += 1
            rows.append({"date": day, "team": t, "player_id": hit[0] if hit else "", "name": hit[1] if hit else f"{first} {last}",
                         "status": st, "report_time": rt, "note": "gleague" if gl else ""})
        if i % 50 == 0:
            print(day, len(rows), dict(stats), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():  # keep the days outside this run
        with gzip.open(OUT, "rt") as fh:
            rows += [r for r in csv.DictReader(fh) if not (d0 <= r["date"] <= d1)]
    rows.sort(key=lambda r: (r["date"], r["team"], r["name"]))
    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "team", "player_id", "name", "status", "report_time", "note"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(days)} game days, {len(days) - len(miss_days)} with a report; missing: {miss_days[:20]}{'...' if len(miss_days) > 20 else ''}")
    print(f"rows {stats['rows']}, non-G-League {stats['nongl']}, matched {stats['nongl_matched']} "
          f"({stats['nongl_matched'] / max(stats['nongl'], 1):.1%}), unsubmitted teams {stats['unsubmitted']}")
    print("most common unmatched:", unmatched.most_common(25))
    return rows


def load(path=OUT):
    """{(date, team): {"st": {player_id: status}, "unsub": bool}} and the set of days with a report."""
    out, days = {}, set()
    if not Path(path).exists():
        return out, days
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            days.add(r["date"])
            e = out.setdefault((r["date"], r["team"]), {"st": {}, "unsub": False})
            if r["note"] == "unsubmitted":
                e["unsub"] = True
            elif r["player_id"]:
                e["st"][r["player_id"]] = r["status"]
    return out, days


def fit_rates(d0="2018-12-18", d1="2024-06-30", min_avg=20.0):
    """Chance a rotation player (min_avg+ minutes over his last 5 games, 10+ games) plays, by lock status,
    and his minutes when he plays relative to his last-5 average."""
    import pandas as pd
    from pipeline.store import load_games, load_players
    st, days = load()
    g = load_games()
    day_of = dict(zip(g["game_id"].astype(str), g["day"]))
    p = load_players()[["game_id", "team", "player_id", "min"]].copy()
    p["game_id"] = p["game_id"].astype(str)
    p["player_id"] = p["player_id"].astype(str)
    p["day"] = p["game_id"].map(day_of)
    p["min"] = pd.to_numeric(p["min"], errors="coerce").fillna(0.0)
    p = p.dropna(subset=["day"]).sort_values("day")
    teams_on = defaultdict(set)
    for d, h, a in zip(g["day"], g["home"], g["away"]):
        teams_on[d] |= {h, a}
    hist = defaultdict(list)
    res = defaultdict(lambda: [0, 0, []])
    from datetime import date, timedelta
    recent_from = lambda d: (date.fromisoformat(d) - timedelta(days=15)).isoformat()  # still with the team
    for d, grp in p.groupby("day", sort=True):
        if d0 <= d <= d1 and d in days:
            today = {(t, pid): m for t, pid, m in zip(grp["team"], grp["player_id"], grp["min"])}
            for pid, h in hist.items():
                if len(h) < 10:
                    continue
                t = h[-1][0]
                if t not in teams_on[d] or h[-1][2] < recent_from(d):
                    continue
                avg = sum(x[1] for x in h[-5:]) / 5
                if avg < min_avg:
                    continue
                e = st.get((d, t)) or {"st": {}, "unsub": False}
                if e["unsub"]:
                    continue
                s = e["st"].get(pid, "unlisted")
                m = today.get((t, pid), 0.0)
                r = res[s]
                r[0] += 1
                if m > 0:
                    r[1] += 1
                    r[2].append(m / max(avg, 1.0))
        for t, pid, m in zip(grp["team"], grp["player_id"], grp["min"]):
            if m > 0:
                hist[pid].append((t, m, d))
    return {s: {"n": v[0], "play": round(v[1] / v[0], 3), "min_ratio": round(sum(v[2]) / len(v[2]), 3) if v[2] else None}
            for s, v in res.items() if v[0]}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "rates":
        for k, v in fit_rates(*(a[1:3] if len(a) >= 3 else ())).items():
            print(k, v)
    else:
        build(*(a[:2] if len(a) >= 2 else ()))
