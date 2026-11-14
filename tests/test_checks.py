import json

from pipeline import checks


def _site(tmp_path, tickets):
    site = tmp_path / "data"
    (site / "game").mkdir(parents=True)
    for name in ("schedule.json", "players.json", "teams.json", "accuracy.json", "standings.json", "meta.json"):
        (site / name).write_text("{}")
    (site / "replay.json").write_text("{}")
    (site / "parlay.json").write_text(json.dumps({"today": {"game_tickets": tickets}}))
    return site


def _ticket(**kw):
    t = {"name": "BOS at TOR", "game": "1", "p": 0.4, "n_legs": 2, "fair": 2.5, "min_odds": 2.63,
         "legs": [{"game": "1", "p": 0.8, "desc": "A over 4.5 rebounds"}, {"game": "1", "p": 0.75, "desc": "B over 9.5 points"}]}
    t.update(kw)
    return t


def test_good_game_ticket_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "SITE", _site(tmp_path, [_ticket()]))
    r = checks.run(compare=False)
    assert r["ok"], r["fails"]


def test_bad_game_tickets_fail(tmp_path, monkeypatch):
    bad = [_ticket(p=1.2),
           _ticket(name="two games", legs=[{"game": "1", "p": 0.8}, {"game": "2", "p": 0.8}]),
           _ticket(name="cheap", min_odds=2.0),
           _ticket(name="short", n_legs=5)]
    monkeypatch.setattr(checks, "SITE", _site(tmp_path, bad))
    fails = " | ".join(checks.run(compare=False)["fails"])
    assert "chance 1.2" in fails and "another game" in fails and "below fair" in fails and "2 legs, says 5" in fails


def test_missing_or_broken_core_file_fails(tmp_path, monkeypatch):
    site = _site(tmp_path, [_ticket()])
    (site / "schedule.json").unlink()
    (site / "players.json").write_text("{not json")
    monkeypatch.setattr(checks, "SITE", site)
    fails = " | ".join(checks.run(compare=False)["fails"])
    assert "schedule.json: missing" in fails and "players.json: not valid JSON" in fails
