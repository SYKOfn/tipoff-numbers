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


RECENT_MIN = 10   # a data update this recent makes another one in the same slot pointless


def data_age_min(now, last=None):
    """Minutes since the last data update (env LAST_DATA_COMMIT: "<unix time> <subject>" of the newest commit),
    or None when the newest commit is not a data update (a code push, which runs the full update anyway)."""
    last = os.environ.get("LAST_DATA_COMMIT", "") if last is None else last
    try:
        ts, subject = last.split(" ", 1)
        age = (now.timestamp() - int(ts)) / 60
    except ValueError:
        return None
    return age if subject.startswith("Data update") and age >= 0 else None


def recent_update(now, last=None):
    a = data_age_min(now, last)
    return a is not None and a < RECENT_MIN


def _games_near(now, ups):
    """(a game tips within 75 min, a game tips within 3 h or is under way / finished in the last 4 h)"""
    soon = near = None
    for g in ups:
        try:
            t = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if soon is None and timedelta(0) <= t - now <= timedelta(minutes=75):
            soon = f"{g['away']} at {g['home']} tips off within 75 minutes (lineups)"
        if near is None and timedelta(0) <= t - now <= timedelta(hours=3):
            near = f"{g['away']} at {g['home']} tips off within 3 hours"
        if near is None and timedelta(0) <= now - t <= timedelta(hours=4):
            near = f"{g['away']} at {g['home']} under way or just finished"
    return soon, near


def decide(now=None, ups=None, par_dir=None, last=None):
    """When the age of the last data update is known, decide by it, so any trigger minute works (GitHub's
    schedule drifts and drops runs; the external timer may fire at other minutes):
    lineups window every run (10+ min apart), near tip-off or games on hourly, otherwise every 3 hours.
    Without that age (local runs, tests) the fixed-slot rules apply."""
    now = now or datetime.now(timezone.utc)
    if lock_due(now, par_dir):
        return True, "the day's tickets are due to be locked"
    age = data_age_min(now, last)
    if age is not None and age < RECENT_MIN:
        return False, f"data updated less than {RECENT_MIN} minutes ago"
    ups = (read_json(STATE / "upcoming.json", []) or []) if ups is None else ups
    if age is not None:
        soon, near = _games_near(now, ups)
        if soon:
            return True, soon
        if near:
            return (True, near) if age >= 50 else (False, f"{near}; updated {age:.0f} min ago")
        return (True, "regular 3-hour update") if age >= 170 else (False, f"quiet time; updated {age:.0f} min ago")
    return _slot_decide(now, ups)


def _slot_decide(now, ups):
    main_slot = 18 <= now.minute <= 33
    soon, near = _games_near(now, ups)
    if not main_slot:
        return (True, soon) if soon else (False, "quarter-hour run: nothing tips off within 75 minutes")
    if now.hour % 3 == 0:
        return True, "regular 3-hour run"
    return (True, near) if near else (False, "nothing tips off within 3 hours")


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
