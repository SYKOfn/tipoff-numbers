"""Phone notifications through ntfy (free app, no account): sent once each, after the safety checks pass.

  * the day's game tickets as soon as they are locked
  * late news on a locked leg (player out or doubtful, moved to the bench, or the chance clearly down), with the
    suggested swap
  * each game ticket's result as it settles, then the night's summary

The channel name is the NTFY_TOPIC secret; without it nothing is sent. What was sent is remembered in
data/state/notified.json so a message never repeats.
"""
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAR = ROOT / "data" / "parlays"
SENT = ROOT / "data" / "state" / "notified.json"
SITE = "https://sykofn.github.io/tipoff-numbers/"
STAT = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "threes", "pra": "pts+reb+ast"}


def leg_text(l):
    if l.get("kind") == "prop" and l.get("side") == "over" and l.get("line") is not None:
        return f"{l.get('player_name')} {math.ceil(float(l['line']))}+ {STAT.get(l.get('stat'), l.get('stat'))}"
    return l.get("desc", "")


def madrid(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return ""
    # Madrid: UTC+1 in winter, UTC+2 from the last Sunday of March to the last Sunday of October
    y = t.year
    last_sun = lambda m: max(datetime(y, m, d, 1, tzinfo=timezone.utc) for d in range(25, 32)
                             if datetime(y, m, d, tzinfo=timezone.utc).weekday() == 6)
    off = 2 if last_sun(3) <= t < last_sun(10) else 1
    return (t + timedelta(hours=off)).strftime("%H:%M")


def _title(t, short=None):
    a, _, b = str(t.get("name", "")).partition(" at ")
    sh = short or {}
    return f"{sh.get(a, a)} at {sh.get(b, b)}" if b else t.get("name", "")


def messages(day_file, sent, short=None):
    """What to send for one day: the lock, late news on locked legs, and results as tickets settle."""
    d = json.loads(day_file.read_text())
    day, out = day_file.stem, []
    tickets = d.get("game_tickets") or []
    if not d.get("locked") or not (tickets or d.get("parlays")):
        return out
    now = datetime.now(timezone.utc)
    upcoming = lambda iso: bool(iso) and datetime.fromisoformat(str(iso).replace("Z", "+00:00")) > now
    legs_all = [l for t in tickets + d.get("parlays", []) for l in t["legs"]]
    # 1. the lock: tonight's game tickets, best chance first
    key = f"lock:{day}"
    if key not in sent and upcoming(d.get("first_tip")) and tickets:
        lines = [f"{_title(t, short)}: {round(100 * t['p'])}%, place at {t['min_odds']:.2f}+" for t in sorted(tickets, key=lambda t: -t["p"])]
        sg = d.get("singles") or []
        out.append((key, {"title": f"Tonight's {len(tickets)} game tickets are locked",
                          "message": "\n".join(lines) + (f"\nPlus {len(sg)} singles." if sg else "") + f"\nFirst tip-off {madrid(d.get('first_tip'))}.",
                          "tags": ["basketball"], "priority": 4, "click": SITE + "#/parlay"}))
    # 2. late news on a locked leg, once per leg
    for l in legs_all:
        k = f"alert:{day}:{l['id']}"
        if l.get("alert") and k not in sent and upcoming(l.get("tip")):
            names = ", ".join(_title(t, short) for t in tickets + d.get("parlays", []) if any(x["id"] == l["id"] for x in t["legs"]))
            sw = l.get("swap")
            body = f"{l['alert']}.\nIn: {names}."
            if sw:
                body += f"\nSuggested swap: {sw.get('desc')} ({sw.get('matchup', '')}, {round(100 * (sw.get('p') or 0))}%)."
            out.append((k, {"title": f"Late news: {leg_text(l)}", "message": body, "tags": ["warning"],
                            "priority": 5, "click": SITE + "#/parlay"}))
            sent[k] = "pending"
    # 3. results: each ticket as it settles (a few at a time), then the night's summary
    new = [t for t in tickets if t.get("result") in ("hit", "miss") and f"result:{day}:{t.get('game')}" not in sent]
    if 0 < len(new) <= 3:
        for t in new:
            hit = t["result"] == "hit"
            out.append((f"result:{day}:{t.get('game')}", {"title": f"{'✓ Landed' if hit else '✗ Missed'}: {_title(t, short)}",
                        "message": f"Stated chance {round(100 * t['p'])}%. " + " · ".join(f"{'✓' if l.get('result') == 'hit' else '✗' if l.get('result') == 'miss' else '·'} {leg_text(l)}" for l in t["legs"]),
                        "tags": ["white_check_mark" if hit else "x"], "priority": 3, "click": SITE + "#/results"}))
    elif len(new) > 3:
        for t in new:
            sent[f"result:{day}:{t.get('game')}"] = "in summary"
    done = [t for t in tickets if t.get("result") in ("hit", "miss")]
    if tickets and len(done) == len(tickets) and f"summary:{day}" not in sent:
        n_hit = sum(t["result"] == "hit" for t in done)
        out.append((f"summary:{day}", {"title": f"{n_hit} of {len(done)} game tickets landed",
                    "message": "\n".join(f"{'✓' if t['result'] == 'hit' else '✗'} {_title(t, short)} ({round(100 * t['p'])}%)" for t in done)
                               + f"\nWe said {sum(t['p'] for t in done):.1f} would land.",
                    "tags": ["bar_chart"], "priority": 3, "click": SITE + "#/results"}))
    return out


DISCLAIMER = "\nStatistical estimate, not advice; most bets lose. 18+ · jugarbien.es"


def send(topic, msg):
    msg = {**msg, "message": (msg.get("message") or "") + DISCLAIMER}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps({"topic": topic, **msg}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    sent = json.loads(SENT.read_text()) if SENT.exists() else {}
    files = sorted(PAR.glob("*.json"))[-2:]
    teams = ROOT / "site" / "data" / "teams.json"
    short = {t["abbr"]: t.get("short", t["abbr"]) for t in (json.loads(teams.read_text()) if teams.exists() else [])}
    work = dict(sent)
    todo = [m for f in files for m in messages(f, work, short)]
    sent.update({k: v for k, v in work.items() if v == "in summary"})
    if not topic:
        print(f"notify: no NTFY_TOPIC set; {len(todo)} message(s) not sent")
        return 0
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    if "hello" not in sent:  # first message once the channel is set up, so you know it works
        todo.insert(0, ("hello", {"title": "Tip-Off Numbers notifications are on",
                                  "message": "You will get tonight's game tickets when they lock at 22:00, a warning if late news hits a locked leg, and each result as it settles.",
                                  "tags": ["white_check_mark"], "click": SITE}))
    for key, msg in todo:
        try:
            send(topic, msg)
            sent[key] = now
            print("notify: sent", key)
        except Exception as e:  # never fail the run over a notification
            print("notify: failed", key, e)
    # keep the memory short: the last ten days
    keep = {f.stem for f in sorted(PAR.glob("*.json"))[-10:]}
    sent = {k: v for k, v in sent.items() if ":" not in k or k.split(":")[1] in keep}
    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(sent, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
