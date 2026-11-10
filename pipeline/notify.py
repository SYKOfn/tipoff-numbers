"""Phone notifications through ntfy (free app, no account): sent once each, after the safety checks pass.

  * the day's tickets as soon as they are locked
  * late news on a locked leg (player out or doubtful, moved to the bench, or the chance clearly down), with the
    suggested swap

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


def messages(day_file, sent):
    d = json.loads(day_file.read_text())
    day, out = day_file.stem, []
    if not d.get("locked") or not d.get("parlays"):
        return out
    now = datetime.now(timezone.utc)
    upcoming = lambda iso: bool(iso) and datetime.fromisoformat(str(iso).replace("Z", "+00:00")) > now
    if not upcoming(d.get("first_tip")) and not any(upcoming(l.get("tip")) for pr in d["parlays"] for l in pr["legs"]):
        return out  # the night is over
    key = f"lock:{day}"
    if key not in sent and upcoming(d.get("first_tip")):
        lines = []
        for pr in d["parlays"]:
            lines.append(f"{pr['name']} ({round(100 * pr['p'])}%, worth placing at {pr['min_odds']:.2f}+)")
            lines += [f"  - {leg_text(l)}" for l in pr["legs"]]
        out.append((key, {"title": "Tonight's tickets are in",
                          "message": "\n".join(lines) + f"\nFirst tip-off {madrid(d.get('first_tip'))}.",
                          "tags": ["basketball"], "priority": 4, "click": SITE + "#/parlay"}))
    for pr in d["parlays"]:
        for l in pr["legs"]:
            k = f"alert:{day}:{l['id']}"
            if l.get("alert") and k not in sent and upcoming(l.get("tip")):
                names = ", ".join(p["name"] for p in d["parlays"] if any(x["id"] == l["id"] for x in p["legs"]))
                sw = l.get("swap")
                body = f"{l['alert']}.\nIn: {names}."
                if sw:
                    body += f"\nSuggested swap: {sw.get('desc')} ({sw.get('matchup', '')}, {round(100 * (sw.get('p') or 0))}%)."
                out.append((k, {"title": f"Late news: {leg_text(l)}", "message": body, "tags": ["warning"],
                                "priority": 5, "click": SITE + "#/parlay"}))
                sent[k] = "pending"  # one message per leg, even when it sits in two tickets
    return out


def send(topic, msg):
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps({"topic": topic, **msg}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    sent = json.loads(SENT.read_text()) if SENT.exists() else {}
    files = sorted(PAR.glob("*.json"))[-2:]
    todo = [m for f in files for m in messages(f, dict(sent))]
    if not topic:
        print(f"notify: no NTFY_TOPIC set; {len(todo)} message(s) not sent")
        return 0
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    if "hello" not in sent:  # first message once the channel is set up, so you know it works
        todo.insert(0, ("hello", {"title": "Tip-Off Numbers notifications are on",
                                  "message": "You will get tonight's tickets as soon as they lock, and a warning if late news hits a locked leg.",
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
