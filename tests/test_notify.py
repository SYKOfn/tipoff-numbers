import json
from pipeline import notify


def _day(tmp_path, results):
    t = lambda g, r: {"name": "BOS at TOR", "game": g, "p": 0.4, "min_odds": 2.6, "result": r,
                      "legs": [{"id": g + "a", "kind": "prop", "desc": "x", "tip": "2099-01-01T00:00Z", "result": r}]}
    d = {"locked": True, "first_tip": "2099-01-01T00:00Z", "game_tickets": [t(str(i), r) for i, r in enumerate(results)]}
    p = tmp_path / "2026-11-11.json"; p.write_text(json.dumps(d)); return p


def test_lock_lists_game_tickets(tmp_path):
    keys = [k for k, _ in notify.messages(_day(tmp_path, [None, None]), {}, {"BOS": "Celtics", "TOR": "Raptors"})]
    assert keys == ["lock:2026-11-11"]


def test_results_one_by_one_then_summary(tmp_path):
    msgs = dict(notify.messages(_day(tmp_path, ["hit", "miss"]), {"lock:2026-11-11": "x"}, {}))
    assert "result:2026-11-11:0" in msgs and "result:2026-11-11:1" in msgs
    assert msgs["summary:2026-11-11"]["title"] == "1 of 2 game tickets landed"
