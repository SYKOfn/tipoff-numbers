"""Safety checks before anything is published.

Run after the pipeline, before the site is packaged. If a check fails, the workflow restores the last
published site data (so a bad run never reaches the site) and marks the run as failed, which makes
GitHub email the repository owner.  Exit code 1 = failed.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site" / "data"


def _old(path):
    """The same file as last published (git HEAD), or None."""
    try:
        rel = path.relative_to(ROOT).as_posix()
        out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout else None
    except Exception:
        return None


def run(compare=True):
    fails, warns = [], []
    games = 0
    jumps = n_players = 0
    for f in sorted((SITE / "game").glob("*.json")):
        try:
            g = json.loads(f.read_text())
        except ValueError:
            fails.append(f"{f.name}: not valid JSON")
            continue
        e = g.get("est") or {}
        pl = g.get("players") or {}
        if not pl or g.get("result") or g.get("kind") not in (None, "estimate"):
            continue
        games += 1
        name = f"{g.get('away', '?')} at {g.get('home', '?')} ({f.stem})"
        w = e.get("win_home")
        if w is None or not 0.01 <= w <= 0.99:
            fails.append(f"{name}: win chance {w}")
        if e.get("margin") is not None and abs(e["margin"]) > 35:
            fails.append(f"{name}: margin {e['margin']:.1f}")
        if e.get("total") is not None and not 180 <= e["total"] <= 290:
            fails.append(f"{name}: total {e['total']:.1f}")
        for side in ("home", "away"):
            rows = [p for p in pl.get(side, []) if not p.get("out")]
            if not rows:
                continue
            tot = sum(p.get("min", 0) * p.get("p_play", 1.0) for p in rows)
            if not 170 <= tot <= 265:
                fails.append(f"{name} {side}: expected minutes add up to {tot:.0f} (should be about 240)")
            top = sorted((p.get("min", 0) for p in rows), reverse=True)[:5]
            if len(top) == 5 and (top[0] > 44 or top[-1] < 12):
                fails.append(f"{name} {side}: top-5 minutes {[round(x, 1) for x in top]}")
            for p in rows:
                for st in ("min", "pts", "reb", "ast"):
                    v = p.get(st)
                    if v is None or v != v or v < 0 or v > {"min": 48, "pts": 60, "reb": 25, "ast": 20}[st]:
                        fails.append(f"{name}: {p.get('name')} {st} = {v}")
        if compare:
            old = _old(f)
            if old and old.get("players"):
                prev = {(s, p["id"]): p for s in ("home", "away") for p in old["players"].get(s, []) if not p.get("out")}
                for side in ("home", "away"):
                    for p in pl.get(side, []):
                        q = prev.get((side, p["id"]))
                        if not q or p.get("out") or q.get("pts", 0) < 10:
                            continue
                        n_players += 1
                        if abs(p["pts"] - q["pts"]) / q["pts"] > 0.4 and p.get("status") == q.get("status"):
                            jumps += 1
    if n_players >= 50 and jumps / n_players > 0.15:
        fails.append(f"{jumps} of {n_players} player projections moved more than 40% since the last run with no news")
    elif jumps:
        warns.append(f"{jumps} player projections moved more than 40% with no news")
    pj = SITE / "parlay.json"
    if pj.exists():
        try:
            par = json.loads(pj.read_text())
        except ValueError:
            par = {}
            fails.append("parlay.json: not valid JSON")
        td = par.get("today") or {}
        legs = list(td.get("board") or []) + list(td.get("singles") or [])
        for t in td.get("parlays") or []:
            legs += t.get("legs") or []
            if t.get("p") is not None and not 0 < t["p"] < 1:
                fails.append(f"ticket {t.get('name')}: chance {t['p']}")
        for lg in legs:
            p = lg.get("p")
            if p is not None and not 0 < p < 1:
                fails.append(f"parlay leg {lg.get('desc')}: chance {p}")
            o = lg.get("price")
            if isinstance(o, (int, float)) and o < 1.01:
                fails.append(f"parlay leg {lg.get('desc')}: odds {o}")
    report = {"games_checked": games, "fails": fails[:50], "warnings": warns, "ok": not fails}
    (SITE / "checks.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    r = run(compare="--no-compare" not in sys.argv)
    print(f"checks: {r['games_checked']} games, {len(r['fails'])} failures, {len(r['warnings'])} warnings")
    for x in r["fails"]:
        print("FAIL", x)
    for x in r["warnings"]:
        print("warn", x)
    sys.exit(0 if r["ok"] else 1)
