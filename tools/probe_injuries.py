"""One-off check: where ESPN keeps head coaches per season."""
from pipeline import espn
for url in ["https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2025/teams/1/coaches",
            "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2025/coaches?limit=60",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/1?enable=coaches",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/1/roster"]:
    d = espn.fetch(url)
    print(url, str(d)[:700])
    if isinstance(d, dict) and d.get("items"):
        for it in d["items"][:3]:
            ref = it.get("$ref")
            if ref:
                print("  ", str(espn.fetch(ref.replace("http://", "https://")))[:600])
