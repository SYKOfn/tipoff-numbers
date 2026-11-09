"""Save real replies from every free feed the collector reads, as test fixtures (tests/fixtures/).
ESPN (scoreboard: a finished day and today, summaries of a finished and an upcoming game, injuries, teams,
a coach), and the NBA's referee-assignments page. No odds credits are used."""
import json
import urllib.request
from datetime import timedelta
from pathlib import Path

from pipeline import espn, refs

OUT = Path("tests/fixtures")


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(data if isinstance(data, str) else json.dumps(data))
    print("saved", name, len(data if isinstance(data, str) else json.dumps(data)))


today = espn.now_utc().astimezone(espn.ET).date()
fin = today - timedelta(days=1)
sb_fin = espn.fetch(f"{espn.BASE}/scoreboard?dates={fin.strftime('%Y%m%d')}&limit=200")
sb_up = espn.fetch(f"{espn.BASE}/scoreboard?dates={today.strftime('%Y%m%d')}&limit=200")
save("scoreboard_finished.json", sb_fin)
save("scoreboard_upcoming.json", sb_up)
gid_fin = sb_fin["events"][0]["id"]
gid_up = sb_up["events"][0]["id"]
save("summary_finished.json", espn.fetch(f"{espn.BASE}/summary?event={gid_fin}"))
save("summary_upcoming.json", espn.fetch(f"{espn.BASE}/summary?event={gid_up}"))
save("injuries.json", espn.fetch(f"{espn.BASE}/injuries"))
save("teams.json", espn.fetch(f"{espn.BASE}/teams"))
c = espn.fetch(f"{espn.CORE}/seasons/2027/teams/1/coaches")
save("coaches_team.json", c)
save("coach.json", espn.fetch(c["items"][0]["$ref"].replace("http://", "https://")))
req = urllib.request.Request(refs.URL, headers={"User-Agent": "Mozilla/5.0 (tipoff-numbers)"})
save("referees.html", urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore"))
save("meta.json", {"finished_day": fin.isoformat(), "today": today.isoformat(), "finished_game": gid_fin, "upcoming_game": gid_up})
