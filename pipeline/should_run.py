from pathlib import Path
"""Decide whether a scheduled run (every 15 minutes) should do the full update.

At :23 past each hour: always every 3 hours; in between, when a game tips off within the next 3 hours
(team news, closing prices) or started in the last 4 hours (results come in quickly).
At the other quarter hours: only when a game tips off within 75 minutes (starting lineups, late scratches).
Prints run=true/false for GitHub Actions ($GITHUB_OUTPUT).
"""
import json
import os
from datetime import datetime, timedelta, timezone

# self-contained on purpose: the gate runs before the dependencies (pandas) are installed
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state"


def read_json(path, default=None):
    path = Path(path)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def lock_due(now, par_dir=None):
    """True when a slate's ticket lock time has passed, its first game has not started and the tickets
    are not locked yet (so a skipped run never delays the lock by more than one quarter hour)."""
    par_dir = par_dir or (ROOT / "data" / "parlays")
    for f in sorted(par_dir.glob("*.json"))[-2:]:
        d = read_json(f, {}) or {}
        try:
            lock = datetime.fromisoformat(d["lock_at"]); tip = datetime.fromisoformat(d["first_tip"])
        except (KeyError, TypeError, ValueError):
            continue
        if not d.get("locked") and lock <= now < tip:
            return True
    return False


def decide(now=None, ups=None, par_dir=None):
    now = now or datetime.now(timezone.utc)
    if lock_due(now, par_dir):
        return True, "the day's tickets are due to be locked"
    main_slot = 18 <= now.minute <= 33
    ups = (read_json(STATE / "upcoming.json", []) or []) if ups is None else ups
    if not main_slot:
        for g in ups:
            try:
                t = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if timedelta(0) <= t - now <= timedelta(minutes=75):
                return True, f"{g['away']} at {g['home']} tips off within 75 minutes (lineups)"
        return False, "quarter-hour run: nothing tips off within 75 minutes"
    if now.hour % 3 == 0:
        return True, "regular 3-hour run"
    for g in ups:
        try:
            t = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if timedelta(0) <= t - now <= timedelta(hours=3):
            return True, f"{g['away']} at {g['home']} tips off within 3 hours"
        if timedelta(0) <= now - t <= timedelta(hours=4):
            return True, f"{g['away']} at {g['home']} under way or just finished"
    return False, "nothing tips off within 3 hours"


SLOTS = (8, 23, 38, 53)  # the scheduled minutes (update.yml)


def next_run(now=None, ups=None, hours=12):
    """The next scheduled slot that will do a full update (GitHub may start it a few minutes late)."""
    now = now or datetime.now(timezone.utc)
    t = now.replace(second=0, microsecond=0)
    end = now + timedelta(hours=hours)
    while t <= end:
        t += timedelta(minutes=1)
        if t.minute in SLOTS and decide(t, ups)[0]:
            return t
    return None


if __name__ == "__main__":
    ok, why = decide()
    print(f"{'RUN' if ok else 'SKIP'}: {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"run={'true' if ok else 'false'}\n")
