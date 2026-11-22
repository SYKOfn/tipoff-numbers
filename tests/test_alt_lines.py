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


def test_tickets_are_stated_at_the_calibrated_blend():
    a = {"p": 0.80, "line": 4.5}
    parlay.alt_lower(a, 0.97)                     # the books like it more: chosen at 0.80, stated at the blend
    b = {"p": 0.85, "line": 9.5}
    parlay.alt_lower(b, 0.80)                     # the books like it less: lowered and stated at the blend
    t = parlay.restate({"p": 0.70, "p_independent": 0.68, "legs": [dict(a), dict(b), {"p": 0.9}]})
    ratio = (a["p_books"] / 0.80) * (b["p_books"] / b["p"])
    assert abs(t["p"] - round(0.70 * ratio, 4)) < 1e-4
    assert t["legs"][0]["p"] == a["p_books"] and t["legs"][0]["p_chosen"] == 0.80
    assert abs(t["fair"] - 1 / t["p"]) < 0.011 and abs(t["min_odds"] - parlay.SAFETY / t["p"]) < 0.011
    assert t["legs"][2]["p"] == 0.9               # a leg without a books price keeps its chance


def test_the_ladder_prices_an_exact_rung_from_the_books():
    l = {"p": 0.55, "alt_book": 0.52, "book": "pinnacle", "market": 0.40}
    o, real = parlay.ladder_odds(l)
    assert not real and o == round(parlay.wmx_odds(parlay.alt_fair(0.52)), 2)
