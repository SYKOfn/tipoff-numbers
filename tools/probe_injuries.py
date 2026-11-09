"""One-off check: coach record structure, and a team with a mid-season change (2025 MIL? 2023 several)."""
import json
from pipeline import espn
d = espn.fetch("https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2025/coaches/52120?lang=en&region=us")
print(json.dumps(d)[:2500])
for s in (2023, 2024, 2025, 2026):
    for tid in range(1, 31):
        c = espn.fetch(f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/{s}/teams/{tid}/coaches")
        if c.get("count", 1) != 1:
            print("MULTI", s, tid, json.dumps(c)[:600])
