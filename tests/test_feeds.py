"""The collector against real feed replies (tests/fixtures/, saved by tools/capture_fixtures.py on GitHub).

These run before every push (tests workflow), so a change that breaks reading ESPN, the NBA referee page or
the odds feed fails here instead of on the live site.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from pipeline import espn, refs

FX = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not (FX / "meta.json").exists(), reason="no captured fixtures")


def fx(name):
    return json.loads((FX / name).read_text())


def router(meta):
    fin_day = meta["finished_day"].replace("-", "")
    up_day = meta["today"].replace("-", "")
    sb_fin, sb_up = fx("scoreboard_finished.json"), fx("scoreboard_upcoming.json")
    fin_ids = {e["id"] for e in sb_fin.get("events", [])}

    def fetch(url, retries=3, timeout=30):
        espn.CALLS["n"] += 1
        if "/scoreboard" in url:
            if f"dates={fin_day}" in url:
                return sb_fin
            if f"dates={up_day}" in url:
                return sb_up
            return {"events": []}
        if "/summary" in url:
            gid = url.split("event=")[1].split("&")[0]
            return fx("summary_finished.json") if gid in fin_ids else fx("summary_upcoming.json")
        if url.endswith("/injuries"):
            return fx("injuries.json")
        if url.endswith("/teams"):
            return fx("teams.json")
        if "/coaches/" in url:
            return fx("coach.json")
        if url.endswith("/coaches"):
            return fx("coaches_team.json")
        return {}
    return fetch


@pytest.fixture
def meta(monkeypatch):
    m = fx("meta.json")
    monkeypatch.setattr(espn, "fetch", router(m))
    monkeypatch.setattr(espn, "now_utc", lambda: datetime.fromisoformat(m["today"] + "T15:00:00+00:00"))
    return m


def test_scoreboard_real(meta):
    fin = espn.scoreboard(meta["finished_day"].replace("-", ""))
    up = espn.scoreboard(meta["today"].replace("-", ""))
    assert fin and all(g["completed"] and g["home_pts"] is not None for g in fin)
    assert up and all(g["state"] in ("pre", "in", "post") for g in up)
    for g in fin + up:
        assert g["home"] and g["away"] and g["home"] != g["away"]
        assert g["season"] >= 2026 and g["day"]


def test_summary_real(meta):
    s = espn.summary(meta["finished_game"])
    assert len(s["teams"]) == 2
    for box in s["teams"].values():
        assert box.get("fga") and box.get("reb") is not None
    played = [p for p in s["players"] if (p.get("min") or 0) > 0]
    assert len(played) >= 16
    assert all(p["player_id"].isdigit() for p in played)
    assert sum(p["pts"] for p in played) > 150
    assert len(s["officials"]) == 3
    up = espn.summary(meta["upcoming_game"])
    inj = [i for lst in up["injuries"].values() for i in lst]
    assert all(i["status"] and i["player_id"] for i in inj)


def test_injuries_real(meta):
    inj = espn.injuries()
    assert len(inj) >= 20
    for lst in inj.values():
        for i in lst:
            assert i["status"] and 0 <= i["weight"] <= 1


def test_coaches_real(meta):
    co = espn.coaches(2027)
    assert len(co) == 30 and all(c["name"] for c in co.values())


def test_referee_page_real():
    crews = refs.parse((FX / "referees.html").read_text())
    assert crews
    for (away, home), names in crews.items():
        assert away and home and len(names) == 3


def test_collect_end_to_end(meta, tmp_path, monkeypatch):
    """A first run from nothing: backfill scan, box scores, injuries, coaches, referee crews, game reports."""
    from pipeline import collect, oddsapi, store
    for mod in (store, collect, oddsapi):
        for name in ("HIST", "STATE", "DATA", "PROPS_CSV"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, tmp_path / name.lower())
    (tmp_path / "state").mkdir()
    monkeypatch.setenv("ODDS_API_KEY", "")
    monkeypatch.setattr(refs, "today_crews", lambda: refs.parse((FX / "referees.html").read_text()))
    from datetime import date
    out = collect.collect(date.fromisoformat(meta["today"]))
    assert out["games"] > 0 and out["upcoming"] > 0
    g = store.load_games()
    assert (g["box"] == 1).any()
    assert g.loc[g["box"] == 1, "refs"].notna().all()
    pl = store.load_players()
    assert len(pl) >= 16 and pl["min"].notna().all()
    ups = json.loads((tmp_path / "state" / "upcoming.json").read_text())
    assert ups and all(u["home"] and u["away"] for u in ups)
    assert any(u.get("refs") for u in ups) or not refs.parse((FX / "referees.html").read_text())
    inj = json.loads((tmp_path / "state" / "injuries.json").read_text())
    assert inj["teams"]
    st = store.load_stints()
    assert len(st) > 10 and set(st["game_id"]) <= set(g["game_id"].astype(str))
    co = json.loads((tmp_path / "state" / "coaches.json").read_text())
    assert len(co[str(espn.season_of(meta["today"]))]) == 30


def test_odds_feed_parsing(tmp_path, monkeypatch):
    """The Odds API's format (game markets for Winamax/Pinnacle, Pinnacle player props)."""
    from pipeline import oddsapi
    monkeypatch.setattr(oddsapi, "PROPS_CSV", tmp_path / "props" / "lines.csv")
    ev = {"id": "e1", "home_team": "Atlanta Hawks", "away_team": "Los Angeles Lakers", "commence_time": "2026-11-10T00:10:00Z",
          "bookmakers": [
              {"key": "winamax_fr", "last_update": "2026-11-09T15:00:00Z", "markets": [
                  {"key": "h2h", "outcomes": [{"name": "Atlanta Hawks", "price": 1.94}, {"name": "Los Angeles Lakers", "price": 1.7}]}]},
              {"key": "pinnacle", "last_update": "2026-11-09T15:00:00Z", "markets": [
                  {"key": "h2h", "outcomes": [{"name": "Atlanta Hawks", "price": 2.04}, {"name": "Los Angeles Lakers", "price": 1.85}]},
                  {"key": "spreads", "outcomes": [{"name": "Atlanta Hawks", "point": 1.5, "price": 1.95},
                                                  {"name": "Los Angeles Lakers", "point": -1.5, "price": 1.93}]},
                  {"key": "totals", "outcomes": [{"name": "Over", "point": 235.5, "price": 1.85}, {"name": "Under", "point": 235.5, "price": 2.02}]},
                  {"key": "player_points", "outcomes": [
                      {"name": "Over", "description": "Austin Reaves", "point": 21.5, "price": 1.9},
                      {"name": "Under", "description": "Austin Reaves", "point": 21.5, "price": 1.83}]}]}]}
    m = oddsapi.parse_game_markets(ev, "ATL", "LAL")
    assert m["winamax_fr"]["ml_home"] == 1.94 and m["pinnacle"]["ml_away"] == 1.85
    assert m["pinnacle"]["spread_home"] == 1.5 and m["pinnacle"]["total"] == 235.5
    g = {"game_id": "401909952", "day": "2026-11-09", "home": "ATL", "away": "LAL"}
    oddsapi.archive_props(ev, g, datetime(2026, 11, 9, 15, tzinfo=timezone.utc), "open")
    lines = pd.read_csv(tmp_path / "props" / "lines.csv")
    row = lines[(lines["stat"] == "pts")].iloc[0]
    assert row["line"] == 21.5 and row["over"] == 1.9 and row["under"] == 1.83 and row["book"] == "pinnacle"


def test_stints_rebuild_real_game():
    """Lineups from play-by-play: time adds up, points add up to the final score, minutes match the box."""
    from collections import Counter
    from pipeline.stints import build
    d = fx("summary_finished.json")
    st, cov = build(d, "g")
    assert cov > 0.95 and len(st) > 10
    comp = {c["homeAway"]: int(c["score"]) for c in d["header"]["competitions"][0]["competitors"]}
    assert sum(x["h_pts"] for x in st) == comp["home"] and sum(x["a_pts"] for x in st) == comp["away"]
    assert abs(sum(x["dur"] for x in st) - 2880) < 1 or sum(x["dur"] for x in st) > 2880
    mins = Counter()
    for x in st:
        for pid in x["home_ids"].split(";") + x["away_ids"].split(";"):
            mins[pid] += x["dur"] / 60
    box = {a["athlete"]["id"]: float(a["stats"][0]) for t in d["boxscore"]["players"] for b in t["statistics"]
           for a in b["athletes"] if a.get("stats") and str(a["stats"][0]).replace(".", "").isdigit()}
    assert all(abs(mins[p] - m) <= 1.5 for p, m in box.items() if m > 0)


def test_play_by_play_events_match_the_box_score():
    import collections
    from pipeline import events
    d = json.load(open(FIX / "summary_finished.json")) if "FIX" in globals() else json.load(open("tests/fixtures/summary_finished.json"))
    ev = events.build(d, "g")
    kinds = collections.Counter(e["kind"] for e in ev)
    assert kinds["fg"] > 150 and kinds["ft"] > 20 and kinds["dreb"] > 40 and kinds["tov"] > 10
    box = d["boxscore"]["players"]
    lab = box[0]["statistics"][0]["labels"]
    ok = 0
    for t in box:
        for a in t["statistics"][0]["athletes"]:
            st = dict(zip(lab, a.get("stats") or []))
            if not st.get("FG"):
                continue
            pid = a["athlete"]["id"]
            made = sum(e["made"] for e in ev if e["kind"] == "fg" and e["pid"] == pid)
            ast = sum(1 for e in ev if e["ast"] == pid)
            ok += made == int(st["FG"].split("-")[0]) and ast == int(st["AST"])
    assert ok >= 15
    assert all(e["dist"] is not None for e in ev if e["kind"] == "fg" and e["val"] == 3)
