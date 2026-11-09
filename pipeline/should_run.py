"""Decide whether an hourly scheduled run should do the full update.

Always every 3 hours; in between, only when a game tips off within the next 3 hours (team news and
late scratches, closing prices) or a game started in the last 4 hours (results come in quickly).
Prints run=true/false for GitHub Actions ($GITHUB_OUTPUT).
"""
import os
from datetime import datetime, timedelta, timezone

from .store import STATE, read_json


def decide(now=None):
    now = now or datetime.now(timezone.utc)
    if now.hour % 3 == 0:
        return True, "regular 3-hour run"
    for g in read_json(STATE / "upcoming.json", []) or []:
        try:
            t = datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if timedelta(0) <= t - now <= timedelta(hours=3):
            return True, f"{g['away']} at {g['home']} tips off within 3 hours"
        if timedelta(0) <= now - t <= timedelta(hours=4):
            return True, f"{g['away']} at {g['home']} under way or just finished"
    return False, "nothing tips off within 3 hours"


if __name__ == "__main__":
    ok, why = decide()
    print(f"{'RUN' if ok else 'SKIP'}: {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"run={'true' if ok else 'false'}\n")
