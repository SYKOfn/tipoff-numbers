from model import parlay
from pipeline import ladder


def _pick(result, odds=2.05, p=0.55, desc="X"):
    return {"leg": {"desc": desc, "matchup": "A at B"}, "odds": odds, "odds_real": True, "p": p, "result": result}


def test_levels_climb_restart_and_hold():
    days = [("d1", _pick("hit")), ("d2", _pick("hit", odds=2.0)), ("d3", _pick("miss")), ("d4", None),
            ("d5", _pick("hit")), ("d6", _pick("void")), ("d7", _pick(None))]
    s = ladder.state(days)
    assert s["level"] == 2                       # d5 climbed to 2; a void and a pending bet keep it
    assert s["best"] == 2 and s["best_days"] == ("d1", "d2")
    assert s["restarts"] == 1                    # the miss on d3 at level 3
    assert [x["level"] for x in s["steps"][::-1]] == [1, 2, 3, 1, 2, 2]
    assert s["bank"] == round(10 * 2.05, 2)      # 10 rolled over from the restart: d5's win
    assert s["bets"] == 4 and s["won"] == 3      # void and pending don't count as bets
    assert abs(s["profit"] - (1.05 + 1.0 - 1 + 1.05)) < 1e-9


def _leg(id_, kind, p, wmx=None, real=False, price=None, price_est=True, game="1", book="pinnacle"):
    return {"id": id_, "kind": kind, "p": p, "wmx": wmx, "wmx_real": real, "price": price, "price_est": price_est, "book": book,
            "game": game, "desc": id_, "matchup": "A at B", "home": "B", "team": "B", "mind_flag": "neutral",
            "proj": 20.0, "avg": 18.0, "last5": 21.0, "line": 17.5}


def test_pick_prefers_a_real_winamax_price_in_range():
    cands = [_leg("prop", "prop", 0.60, price=2.05),                 # estimated price, higher chance
             _leg("ml", "ml", 0.53, wmx=2.05, real=True),             # real Winamax price, in range
             _leg("far", "ml", 0.70, wmx=2.40, real=True),            # outside 2.00-2.10
             _leg("thin", "ml", 0.50, wmx=2.04, real=True)]           # 0.50 x 2.04 < 1.05: no margin of safety
    lp = parlay.ladder_pick(cands, {}, {})
    assert lp["leg"]["id"] == "ml" and lp["odds_real"] and lp["odds"] == 2.05
    assert lp["min_odds"] == round(1.05 / 0.53, 2) and "53%" in lp["why"]


def test_pick_falls_back_to_the_most_likely_estimated_bet():
    cands = [_leg("a", "prop", 0.55, price=2.02), _leg("b", "prop", 0.58, price=2.08), _leg("c", "prop", 0.62, price=1.70)]
    lp = parlay.ladder_pick(cands, {}, {})
    assert lp["leg"]["id"] == "b" and not lp["odds_real"]
    alone = parlay.ladder_pick([_leg("c", "prop", 0.62, price=1.70)], {}, {})        # nothing at 2.00-2.10: the closest
    assert alone["tier"] == 4 and "closest" in alone["note"]


def test_market_prices_beat_season_average_estimates_and_there_is_always_a_bet():
    cands = [_leg("est", "prop", 0.70, price=2.05, book=None), _leg("mkt", "prop", 0.49, price=2.06)]
    lp = parlay.ladder_pick(cands, {}, {})
    assert lp["leg"]["id"] == "mkt" and lp["tier"] == 3 and "little or no edge" in lp["note"]
    only_est = parlay.ladder_pick([_leg("est", "prop", 0.70, price=2.05, book=None)], {}, {})
    assert only_est["leg"]["id"] == "est" and "only an estimate" in only_est["note"]
    assert parlay.ladder_pick([], {}, {}) is None                                     # no games, no bet


def test_another_books_price_is_converted_to_winamax_and_never_called_checked():
    l = _leg("dk", "prop", 0.56, price=2.30, price_est=False)
    l["market"] = 0.47                                      # the book's no-margin chance at its real line
    o, real = parlay.ladder_odds(l)
    assert not real and o == round(parlay.wmx_odds(0.47), 2) and o < 2.30


def test_winning_level_ten_completes_the_ladder():
    days = [(f"d{i:02d}", _pick("hit", odds=2.0)) for i in range(1, 11)] + [("d11", _pick("hit", odds=2.0))]
    s = ladder.state(days)
    assert len(s["trophies"]) == 1 and s["trophies"][0]["from"] == "d01" and s["trophies"][0]["to"] == "d10"
    assert s["trophies"][0]["bank"] == round(10 * 2.0 ** 10, 2)
    assert s["level"] == 2 and s["bank"] == 20.0          # a new ladder: d11 won its level 1
