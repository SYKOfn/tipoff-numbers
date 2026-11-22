import json

from model import parlay
from pipeline import oddsapi


def test_parse_alt_takes_the_median_over_price_per_rung():
    ev = {"bookmakers": [
        {"key": "draftkings", "markets": [{"key": "player_rebounds_alternate", "outcomes": [
            {"name": "Over", "description": "Jakob Poeltl", "point": 4.5, "price": 1.10},
            {"name": "Over", "description": "Jakob Poeltl", "point": 6.5, "price": 1.40}]}]},
        {"key": "fanduel", "markets": [{"key": "player_rebounds_alternate", "outcomes": [
            {"name": "Over", "description": "Jakob Poeltl", "point": 4.5, "price": 1.12}]}]},
        {"key": "betmgm", "markets": [{"key": "player_points", "outcomes": [            # not an alternate market
            {"name": "Over", "description": "Jakob Poeltl", "point": 12.5, "price": 1.9}]}]}]}
    rows = {(r[0], r[1], r[2]): r[3] for r in oddsapi.parse_alt(ev)}
    assert set(rows) == {("Jakob Poeltl", "reb", 4.5), ("Jakob Poeltl", "reb", 6.5)}
    assert rows[("Jakob Poeltl", "reb", 4.5)] == round(1 / 1.10, 4)           # median of two: the higher implied
    assert rows[("Jakob Poeltl", "reb", 6.5)] == round(1 / 1.40, 4)


def test_alt_latest_reads_back_by_game_player_stat_line(tmp_path, monkeypatch):
    f = tmp_path / "alt.json"
    f.write_text(json.dumps({"401": {"at": "2026-11-22T00:00:00+00:00", "rows": [["Jakob Pöltl", "reb", 4.5, 0.9091]]}}))
    monkeypatch.setattr(oddsapi, "ALT_JSON", f)
    assert oddsapi.alt_latest()[("401", oddsapi.norm_name("Jakob Poltl"), "reb", 4.5)] == 0.9091


def test_books_only_ever_lower_a_leg():
    hi = {"p": 0.85, "line": 4.5, "note": "x"}
    assert parlay.alt_lower(hi, 0.80)                    # the books say less: lowered
    assert hi["p"] < 0.85 and hi["p_before_books"] == 0.85 and "lowered" in hi["note"]
    lo = {"p": 0.80, "line": 4.5, "note": "x"}
    assert not parlay.alt_lower(lo, 0.97)                # the books say more: left alone, never lifted
    assert lo["p"] == 0.80 and lo["alt_book"] == 0.97
