"""Structured news for tonight's players, written each morning by the analyst task in data/overrides/news.json:

    {"players": {"<Full Name>": {"day": "2026-11-10", "team": "OKC", "rest": true | "min_cap": 20 | "start": true |
                                 "bench": true | "returning": true, "quote": "...", "source": "https://..."}}}

Only facts stated by a reputable source count (no mood, no adjectives). A signal applies only to games on its
"day" (US date). Every signal used is logged (data/state/news_log.jsonl) with the minutes projected with and
without it, so tools/news_check.py can measure after a few weeks whether the news made projections better.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "overrides" / "news.json"
LOG = ROOT / "data" / "state" / "news_log.jsonl"
KINDS = ("rest", "min_cap", "start", "bench", "returning")


def norm(name):
    from .oddsapi import norm_name
    return norm_name(name or "")


def signals_for(day):
    """{normalized name: signal} for games on `day`."""
    from .oddsapi import norm_name
    try:
        d = json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for name, s in (d.get("players") or {}).items():
        if not isinstance(s, dict) or str(s.get("day")) != str(day):
            continue
        s = {k: v for k, v in s.items() if k in KINDS + ("quote", "source", "team", "day") and v not in (None, False, "")}
        s["name"] = name
        if "min_cap" in s:
            try:
                s["min_cap"] = float(s["min_cap"])
                if not 4 <= s["min_cap"] <= 40:
                    s.pop("min_cap")
            except (TypeError, ValueError):
                s.pop("min_cap")
        if any(k in s for k in KINDS):
            out[norm_name(name)] = s
    return out


def log(day, gid, with_news, without_news):
    """Append one line per player with a signal (once per day and game)."""
    seen = set()
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line); seen.add((r["day"], r["game"], r["player"]))
            except ValueError:
                pass
    base = {str(x["id"]): x for side in ("home", "away") for x in (without_news.get(side) or [])}
    rows = []
    for side in ("home", "away"):
        for x in with_news.get(side) or []:
            if not x.get("news") or (day, str(gid), str(x["id"])) in seen:
                continue
            b = base.get(str(x["id"])) or {}
            rows.append({"day": day, "game": str(gid), "player": str(x["id"]), "name": x["name"],
                         "signals": {k: x["news"][k] for k in KINDS if k in x["news"]},
                         "min_news": 0.0 if x.get("out") else x.get("min"), "min_without": 0.0 if b.get("out") else b.get("min")})
    if rows:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    return len(rows)
