"""Where are referee crews? Past box scores (ESPN gameInfo) and today's assignments (official.nba.com)."""
import json
import re
import urllib.request
from pipeline import espn
d = espn.fetch(f"{espn.BASE}/summary?event=401909088")
print("past gameInfo:", json.dumps(d.get("gameInfo"))[:900])
for url in ["https://official.nba.com/referee-assignments/"]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        print(url, len(html))
        i = html.find("Crew Chief")
        print(re.sub(r"\s+", " ", html[i - 200:i + 2500]) if i >= 0 else html[:1500])
    except Exception as e:
        print(url, "error", e)
