"""python -m pytest -q"""
import json

import numpy as np
import pandas as pd

from model import effects, ratings
from model.features import Tracker
from pipeline import espn
from pipeline.teams import canon, km

EVENT = {
    "id": "401810001", "date": "2026-11-10T00:30Z", "season": {"year": 2027, "type": 2},
    "competitions": [{
        "neutralSite": False, "venue": {"fullName": "TD Garden"},
        "status": {"period": 4, "type": {"state": "post", "completed": True, "shortDetail": "Final"}},
        "broadcasts": [{"market": "national", "names": ["ESPN"]}],
        "competitors": [
            {"homeAway": "home", "score": "112", "team": {"id": "2", "abbreviation": "BOS", "logo": "x.png"},
             "records": [{"name": "overall", "type": "total", "summary": "6-2"}]},
            {"homeAway": "away", "score": "104", "team": {"id": "13", "abbreviation": "LAL"},
             "records": [{"name": "overall", "summary": "4-4"}]},
        ]}],
}
SUMMARY = {
    "boxscore": {
        "teams": [
            {"team": {"id": "2", "abbreviation": "BOS"}, "statistics": [
                {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "41-88", "label": "FG"},
                {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "16-42", "label": "3PT"},
                {"name": "totalRebounds", "displayValue": "47", "label": "REB"},
                {"name": "assists", "displayValue": "27", "label": "AST"},
                {"name": "turnovers", "displayValue": "11", "label": "TO"}]},
            {"team": {"id": "13", "abbreviation": "LAL"}, "statistics": [
                {"label": "FG", "displayValue": "39-90"}, {"label": "3PT", "displayValue": "11-35"},
                {"label": "REB", "displayValue": "40"}, {"label": "AST", "displayValue": "22"}]},
        ],
        "players": [{"team": {"id": "2", "abbreviation": "BOS"}, "statistics": [{
            "keys": ["minutes", "points", "fieldGoalsMade-fieldGoalsAttempted", "rebounds", "assists"],
            "labels": ["MIN", "PTS", "FG", "REB", "AST"],
            "athletes": [
                {"athlete": {"id": "1", "displayName": "A One"}, "starter": True, "stats": ["36", "30", "11-20", "8", "5"]},
                {"athlete": {"id": "2", "displayName": "B Two"}, "didNotPlay": True, "stats": []}]}]}],
    },
    "injuries": [{"team": {"id": "13", "abbreviation": "LAL"}, "injuries": [
        {"athlete": {"id": "9", "displayName": "C Three"}, "status": "Out", "details": {"type": "Ankle"}}]}],
}


def test_canon():
    assert canon("GSW") == "GS" and canon("UTA") == "UTAH" and canon(espn_id=13) == "LAL"
    assert canon("EAST") is None
    assert 4000 < km("BOS", "LAL") < 4300


def test_parse_event():
    g = espn.parse_event(EVENT)
    assert g["home"] == "BOS" and g["away"] == "LAL" and g["home_pts"] == 112 and g["completed"]
    assert g["national_tv"] and g["day"] == "2026-11-09" and g["season"] == 2027 and g["home_record"] == "6-2"


def test_parse_summary():
    s = espn.parse_summary(SUMMARY)
    assert s["teams"]["BOS"]["tpm"] == 16 and s["teams"]["BOS"]["reb"] == 47
    assert s["teams"]["LAL"]["fga"] == 90 and s["teams"]["LAL"]["ast"] == 22
    p = {x["name"]: x for x in s["players"]}
    assert p["A One"]["pts"] == 30 and p["B Two"]["min"] == 0
    assert s["injuries"]["LAL"][0]["weight"] == 1.0


def _games(n_days=80, seed=1):
    rng = np.random.default_rng(seed)
    teams = sorted(ratings.ABBRS)
    true = {t: rng.normal(0, 5) for t in teams}
    rows = []
    gid = 0
    for d in range(n_days):
        day = (pd.Timestamp("2025-10-21") + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        rng.shuffle(teams)
        for i in range(0, 14, 2):
            h, a = teams[i], teams[i + 1]
            m = true[h] - true[a] + 3 + rng.normal(0, 11)
            t = 226 + rng.normal(0, 15)
            gid += 1
            rows.append({"game_id": str(gid), "date": day + "T23:30Z", "day": day, "season": 2026, "stype": 2, "home": h,
                         "away": a, "home_pts": round((t + m) / 2), "away_pts": round((t - m) / 2), "neutral": 0})
    return pd.DataFrame(rows), true


def test_ratings_recover_strength():
    g, true = _games()
    rt = ratings.fit(g, "pts", half_life=400, lam=3, carry=1)
    est = np.array([rt.net(t) for t in ratings.ABBRS])
    tru = np.array([true[t] for t in ratings.ABBRS])
    assert np.corrcoef(est, tru)[0, 1] > 0.8
    assert 1.0 < rt.home < 5.5


def test_tracker_context():
    g, _ = _games(10)
    tr = Tracker()
    tr.set_schedule(g.to_dict("records"))
    for r in g.to_dict("records"):
        ctx = tr.pre_game(r)
        assert set(ctx) == {"home", "away", "rivalry", "playoff"}
        assert ctx["home"]["rest"] >= 0 and ctx["away"]["km"] >= 0
        tr.post_game(r)
    assert sum(sum(v) for v in tr.wl[2026].values()) == 2 * len(g)


def test_effects_find_planted_effect():
    rng = np.random.default_rng(3)
    rows = []
    base_side = {k: 0 for k in ["b2b", "three_in_four", "rest", "tz_east", "km", "missing", "streak", "confidence", "bounce",
                                "letdown", "revenge", "lookahead", "homecoming", "road_long", "stakes", "elimination"]}
    for _ in range(3000):
        hs, as_ = dict(base_side), dict(base_side)
        as_["b2b"] = int(rng.random() < 0.3)
        hs["revenge"] = int(rng.random() < 0.3)
        m = -2.0 * (0 - as_["b2b"]) + 0.0 * hs["revenge"] + rng.normal(0, 12)
        rows.append(({"home": hs, "away": as_, "rivalry": 0, "playoff": 0}, m, 0.0, 225 + rng.normal(0, 15), 225.0))
    e = effects.estimate(rows, lam=50)
    tab = {r["key"]: r for r in e.table() if r["target"] == "margin"}
    assert -3.2 < tab["b2b"]["pts"] < -0.9 and tab["b2b"]["evidence"] in ("strong", "moderate")
    assert abs(tab["revenge"]["pts"]) < 1.2


def test_site_data_is_valid_json(tmp_path):
    from pipeline.store import write_json
    write_json(tmp_path / "x.json", {"a": float("nan"), "b": np.float64(1.5), "c": [np.int64(2)]})
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": None, "b": 1.5, "c": [2]}


def test_parse_full_player_line():
    s = espn.parse_summary({"boxscore": {"teams": [], "players": [{"team": {"id": "2"}, "statistics": [{
        "keys": ["minutes", "points", "fieldGoalsMade-fieldGoalsAttempted", "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                 "freeThrowsMade-freeThrowsAttempted", "rebounds", "assists", "turnovers", "steals", "blocks", "plusMinus"],
        "athletes": [{"athlete": {"id": "7", "displayName": "X Y", "jersey": "0"}, "stats": ["35", "28", "10-19", "4-9", "4-5", "6", "8", "3", "2", "1", "+9"]}]}]}]}})
    r = s["players"][0]
    assert (r["fgm"], r["fga"], r["tpm"], r["tpa"], r["ftm"], r["fta"]) == (10, 19, 4, 9, 4, 5)
    assert r["tov"] == 3 and r["stl"] == 2 and r["pm"] == 9 and r["jersey"] == "0"


def test_playoff_odds_sum():
    from model import extras
    wl = {t: [5, 5] for t in ratings.ABBRS}
    net = {t: 0.0 for t in ratings.ABBRS}
    rest = [("BOS", "LAL"), ("NY", "MIA")] * 5
    o = extras.playoff_odds(wl, rest, net, 2.5, 12.0, sims=300)
    east = [t for t in o if t in ("ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NY", "ORL", "PHI", "TOR", "WSH")]
    assert abs(sum(o[t]["playoffs"] for t in east) - 8) < 0.02
    assert abs(sum(o[t]["seed1"] for t in east) - 1) < 0.02


def test_player_projection_basic():
    from model.players import PlayerTracker
    pt = PlayerTracker()
    for i in range(8):
        g = {"home": "BOS", "away": "LAL", "season": 2027}
        rows = {"BOS": [{"player_id": "1", "name": "A", "pos": "G", "min": 34, "pts": 25, "reb": 5, "ast": 6, "tpm": 3},
                        {"player_id": "2", "name": "B", "pos": "C", "min": 30, "pts": 12, "reb": 11, "ast": 2, "tpm": 0}],
                "LAL": [{"player_id": "3", "name": "C", "pos": "F", "min": 36, "pts": 20, "reb": 7, "ast": 4, "tpm": 2}]}
        pt.post_game(g, rows)
    proj, x = pt.project("1", "BOS", "LAL", True, 0)
    assert 28 < proj["min"] < 38 and 15 < proj["pts"] < 30
    proj2, _ = pt.project("1", "BOS", "LAL", True, 0, absent={"2"}, missing_share=0.3)
    assert proj2["min"] >= proj["min"] and x["home"] == 1


def test_parlay_scoring_and_correlation():
    from model import parlay
    g = {"home": "BOS", "away": "LAL", "home_pts": 120, "away_pts": 110}
    assert parlay.score_leg({"kind": "ml", "team": "BOS"}, g, {}) == "hit"
    assert parlay.score_leg({"kind": "spread", "team": "LAL", "line": 9.5}, g, {}) == "miss"
    assert parlay.score_leg({"kind": "total", "line": 225.5, "side": "over"}, g, {}) == "hit"
    assert parlay.score_leg({"kind": "prop", "player": "1", "stat": "pts", "line": 20.5, "side": "over"}, g, {"1": {"min": 0}}) == "void"
    est = {"margin": 4.0, "sd_margin": 12.0, "total": 226.0, "sd_total": 15.0, "home_pts": 115.0, "away_pts": 111.0, "win_home": 0.63}
    players = {"home": [{"id": "1", "name": "A", "min": 34, "pts": 26.0, "reb": 5.0, "ast": 6.0, "tpm": 3.0, "lines": {}}], "away": []}
    import numpy as np
    sim = parlay.simulate({"id": "g", "home": "BOS", "away": "LAL"}, est, players, {"pts": 1.2, "reb": 0.6, "ast": 0.5, "tpm": 0.5}, np.random.default_rng(1))
    over_total = sim["t"] > 226
    star_over = sim["players"]["1"]["pts"] > 26
    assert (over_total & star_over).mean() > over_total.mean() * star_over.mean()  # positive correlation


def test_clv_and_market_view():
    from model import parlay
    leg = {"kind": "ml", "team": "BOS", "home": "BOS"}
    o1 = parlay.market_view(leg, {"ml_home": 1.9, "ml_away": 2.0})
    o2 = parlay.market_view(leg, {"ml_home": 1.7, "ml_away": 2.25})
    assert parlay.clv(leg, o1, o2)["p"] > 0          # price shortened on our side: positive CLV
    sp = {"kind": "spread", "team": "LAL", "home": "BOS"}
    v1 = parlay.market_view(sp, {"spread_home": -4.5})  # LAL +4.5
    v2 = parlay.market_view(sp, {"spread_home": -3.0})  # LAL +3.0 at close
    assert parlay.clv(sp, v1, v2)["pts"] == 1.5
    tot = {"kind": "total", "side": "under"}
    assert parlay.clv(tot, {"line": 230.5}, {"line": 228.5})["pts"] == 2.0


def test_should_run_gate(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from pipeline import should_run
    monkeypatch.setattr(should_run, "read_json", lambda *a, **k: [{"date": "2026-11-10T00:30Z", "home": "BOS", "away": "LAL"}])
    assert should_run.decide(datetime(2026, 11, 9, 22, 23, tzinfo=timezone.utc))[0]          # 2 h before tip
    assert not should_run.decide(datetime(2026, 11, 9, 16, 23, tzinfo=timezone.utc))[0]      # quiet hour
    assert should_run.decide(datetime(2026, 11, 9, 15, 23, tzinfo=timezone.utc))[0]          # 3-hour slot


def test_prop_real_lines_test():
    from model import prop_test
    fl = {("g1", "a b", "pts"): ({"line": "20.5", "over": "1.90", "under": "1.90"}, {"line": "21.5", "over": "1.90", "under": "1.90"})}
    out = prop_test.real_lines(fl, {("g1", "a b"): {"pts": 26.0}}, {("g1", "a b"): {"pts": 27}}, {"pts": 1.2}, {"pts": {"t": 1.0}})
    assert out["n"] == 1 and out["bets"]["n"] == 1 and out["bets"]["won"] == 1 and out["bets"]["clv_beat"] == 1


def test_parse_event_survives_odd_odds():
    import copy
    for odds in ([{"provider": "ESPN BET", "details": "BOS -4.5", "overUnder": 224.5, "spread": -4.5,
                   "homeTeamOdds": {"moneyLine": -190}, "awayTeamOdds": {"moneyLine": 160}}],
                 [{"moneyline": {"home": {"close": {"odds": "-190"}}, "away": {"close": {"odds": "+160"}}},
                   "pointSpread": {"home": {"close": {"line": "-4.5"}}}, "total": {"over": {"close": {"line": "o224.5"}}}}],
                 ["garbage", None, {"provider": "x", "spread": "n/a"}], {"weird": True}):
        e = copy.deepcopy(EVENT)
        e["competitions"][0]["odds"] = odds
        g = espn.parse_event(e)
        assert g and g["home"] == "BOS"
    e = copy.deepcopy(EVENT)
    e["competitions"][0]["odds"] = [{"provider": {"name": "ESPN BET"}, "spread": -4.5, "overUnder": 224.5,
                                     "homeTeamOdds": {"moneyLine": -190}, "awayTeamOdds": {"moneyLine": 160}}]
    o = espn.parse_event(e)["odds"]
    assert abs(o["ml_home"] - 1.5263) < 1e-3 and o["ml_away"] == 2.6 and o["spread_home"] == -4.5 and o["total"] == 224.5


def test_book_legs_only_from_book_menu():
    from model import parlay
    game = {"id": "g1", "home": "BOS", "away": "LAL"}
    est = {"margin": 5.0, "sd_margin": 12.0, "total": 226.0, "sd_total": 15.0, "home_pts": 115.5, "away_pts": 110.5, "win_home": 0.66}
    odds = {"provider": "winamax_fr", "ml_home": 1.55, "ml_away": 2.45, "spread_home": -4.5, "spread_price_home": 1.88,
            "spread_price_away": 1.88, "total": 225.5, "over": 1.87, "under": 1.87}
    offers = [{"kind": "prop", "stat": "pts", "player": "Jayson Tatum", "side": "over", "point": 26.5, "price": 1.85},
              {"kind": "prop", "stat": "pts", "player": "Jayson Tatum", "side": "under", "point": 26.5, "price": 1.85},
              {"kind": "spread", "team": "BOS", "point": -9.5, "price": 2.6},
              {"kind": "team_total", "team": "LAL", "side": "under", "point": 112.5, "price": 1.8}]
    players = {"home": [{"id": "1", "name": "Jayson Tatum", "min": 36, "pts": 28.0, "reb": 8.0, "ast": 5.0, "tpm": 3.0}], "away": []}
    legs = parlay.book_legs(game, est, players, odds, offers, {}, {"pts": 1.2}, 0.0)
    descs = {l["desc"] for l in legs}
    assert "Jayson Tatum over 26.5 points" in descs and "BOS -9.5" in descs and "LAL under 112.5 points" in descs
    assert all(l["book"] == "winamax_fr" and l["price"] for l in legs)
    assert {l["line"] for l in legs if l["kind"] == "prop"} == {26.5}   # no player line the book does not list


def test_no_player_unders():
    from model import parlay
    game = {"id": "g1", "home": "BOS", "away": "LAL"}
    players = {"home": [{"id": "1", "name": "A B", "min": 34, "pts": 18.0, "reb": 5.0, "ast": 4.0, "tpm": 2.5, "spots": []}], "away": []}
    avg = {"1": {"gp": 10, "pts": 24.0, "reb": 5.0, "ast": 4.0, "tpm": 2.5, "pra": 33.0}}
    legs = parlay.prop_legs(game, players, {}, avg, {"pts": 1.2, "reb": 0.6, "ast": 0.5, "tpm": 0.5, "pra": 1.1})
    assert legs == [] or all(l["side"] == "over" for l in legs)


def test_lineup_strength_follows_players():
    from model.lineup import LineupTracker
    lt = LineupTracker()
    star = {"player_id": "s", "min": 36, "pts": 32, "reb": 8, "ast": 7, "fgm": 12, "fga": 20, "ftm": 6, "fta": 7, "oreb": 1,
            "stl": 2, "blk": 1, "pf": 2, "tov": 3, "pm": 10, "tpm": 2}
    bench = {"player_id": "b", "min": 20, "pts": 4, "reb": 2, "ast": 1, "fgm": 2, "fga": 8, "ftm": 0, "fta": 0, "oreb": 0,
             "stl": 0, "blk": 0, "pf": 3, "tov": 2, "pm": -6, "tpm": 0}
    for i in range(10):
        lt.post_game({"season": 2027, "home": "BOS", "away": "LAL", "home_pts": 110, "away_pts": 100}, {"BOS": [star, bench]})
    with_star = lt.strength([("s", None), ("b", None)])
    without = lt.strength([("b", None)])
    assert with_star[0] > without[0] and with_star[1] > without[1]


def test_injury_report_keys():
    from pipeline.injury_log import key
    assert key("Out", "") == "out"
    assert key("Day-To-Day", "Jokic (elbow) is listed as questionable for Monday's game.", "2026-11-09") == "questionable"
    assert key("Day-To-Day", "Bane (illness) has been ruled out for Monday's game.", "2026-11-09") == "ruled out (note)"
    # a note about another day's game is stale
    assert key("Day-To-Day", "Bane (illness) has been ruled out for Saturday's game.", "2026-11-09") == "day-to-day"
    assert key("Day-To-Day", "Santos (knee) is listed as probable for Monday's game.", "2026-11-09") == "probable"


def test_minutes_model_learns():
    import numpy as np
    from model.players import MinutesModel, MIN_FEATS
    mm = MinutesModel()
    rng = np.random.default_rng(1)
    for _ in range(4000):
        f = [1.0] + list(rng.uniform(0, 36, len(MIN_FEATS) - 1))
        mm.add(f, 0.8 * f[2] + 3 + rng.normal(0, 1))  # minutes follow the short-term average
    assert mm.w is not None and abs(mm.predict([1.0] + [20.0] * (len(MIN_FEATS) - 1)) - 19.0) < 1.5


def test_quarter_hour_gate(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from pipeline import should_run, store
    import json
    monkeypatch.setattr(should_run, "STATE", tmp_path)
    (tmp_path / "upcoming.json").write_text(json.dumps([{"date": "2026-11-10T00:00Z", "home": "ATL", "away": "LAL"}]))
    assert should_run.decide(datetime(2026, 11, 9, 23, 8, tzinfo=timezone.utc))[0]       # 52 min before tip
    assert not should_run.decide(datetime(2026, 11, 9, 20, 8, tzinfo=timezone.utc))[0]   # quarter-hour, nothing close
    assert should_run.decide(datetime(2026, 11, 9, 21, 23, tzinfo=timezone.utc))[0]      # hourly slot, within 3 h


def test_rapm_recovers_ratings():
    import numpy as np
    from model.rapm import RAPM
    rng = np.random.default_rng(3)
    true = {str(i): rng.normal(0, 4) for i in range(60)}
    rp = RAPM(lam=5)
    for k in range(1500):
        ids = rng.choice(60, 16, replace=False).astype(str)
        h, a = ids[:8], ids[8:]
        rows_h = [{"player_id": p, "min": 30} for p in h]
        rows_a = [{"player_id": p, "min": 30} for p in a]
        m = 2.5 + sum(true[p] for p in h) * 5 / 8 - sum(true[p] for p in a) * 5 / 8 + rng.normal(0, 8)
        rp.add({"day": "2026-01-01", "season": 2026, "home_pts": 110 + m, "away_pts": 110, "ot": 0}, rows_h, rows_a)
    rp.fit("2026-01-02")
    est = np.array([rp.r[p] for p in true]); tru = np.array(list(true.values()))
    assert np.corrcoef(est, tru)[0, 1] > 0.8 and abs(rp.hca - 2.5) < 1.0


def test_market_weight_measured():
    import random
    from model.prop_test import market_weight
    rnd = random.Random(4)
    rows = []
    for _ in range(2000):
        truth = rnd.uniform(0.2, 0.8)
        mk = min(0.95, max(0.05, truth + rnd.gauss(0, 0.03)))     # a sharp market
        mo = min(0.95, max(0.05, truth + rnd.gauss(0, 0.12)))     # a noisier model
        rows.append({"model": mo, "market": mk, "y": 1.0 if rnd.random() < truth else 0.0})
    w = market_weight(rows)
    assert w["measured"] and w["w"] <= 0.4
    assert market_weight(rows[:100])["w"] == 0.5
