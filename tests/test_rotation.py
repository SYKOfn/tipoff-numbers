import pandas as pd

from model import players as P
from model.player_engine import rotation_pbp


def test_fourth_quarter_close_and_blowout_time():
    # Q1 builds a 20-point home lead; in Q4 the first stretch starts at +20 (blowout), then the
    # away side closes to +6 (close) for the last stretch.
    st = pd.DataFrame([
        {"game_id": "1", "period": 1, "start": 0.0, "dur": 600.0, "h_pts": 30, "a_pts": 10, "home_ids": "a;b;c;d;e", "away_ids": "v;w;x;y;z"},
        {"game_id": "1", "period": 4, "start": 0.0, "dur": 300.0, "h_pts": 0, "a_pts": 14, "home_ids": "f;g;h;i;j", "away_ids": "v;w;x;y;z"},
        {"game_id": "1", "period": 4, "start": 300.0, "dur": 420.0, "h_pts": 5, "a_pts": 5, "home_ids": "a;b;c;d;j", "away_ids": "v;w;x;y;z"},
    ])
    r = rotation_pbp(st)
    assert r[("1", "a")] == (420.0, 420.0, 0.0, 300.0)    # starter: sat the blowout, played the close finish
    assert r[("1", "f")] == (0.0, 420.0, 300.0, 300.0)    # bench: played only the blowout
    assert r[("1", "j")] == (420.0, 420.0, 300.0, 300.0)
    assert r[("1", None)] == (0.0, 420.0, 0.0, 300.0)     # a player who sat all of the fourth
    assert P.ROT_CLOSE >= 6 and P.ROT_BLOW <= 20          # the thresholds this example relies on
