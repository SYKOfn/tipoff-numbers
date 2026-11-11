"""Player events from ESPN play-by-play: every shot (with distance, value, made, assisted by whom), free throw,
rebound and turnover, timed in game seconds so it can be matched to the lineup on the floor (stints).

Used for: teammate on/off effects (how a player's shots, assists and rebounds change with a given teammate on or
off the floor) and shot quality (makes expected from shot distance and type, to tell real form from luck)."""
import re

from .stints import _plen, _pstart, _secs

COLS = ["game_id", "t", "side", "kind", "pid", "made", "val", "dist", "ast", "shot"]
_DIST = re.compile(r"(\d+)-foot")
_CLOSE = ("layup", "dunk", "tip", "putback", "alley oop", "finger roll")


def _from_xy(c):
    """Distance in feet from ESPN's court coordinate (basket near x=25, y=0); None when the coordinate is a filler."""
    try:
        x, y = float(c["x"]), float(c["y"])
    except (TypeError, KeyError, ValueError):
        return None
    if abs(x) > 100 or abs(y) > 100:
        return None
    return int(round(((x - 25) ** 2 + y ** 2) ** 0.5))


def build(summary, game_id=None):
    """Raw ESPN summary JSON -> list of event dicts (COLS)."""
    plays = summary.get("plays") or []
    comps = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []
    side_of = {str(c.get("id") or (c.get("team") or {}).get("id")): c.get("homeAway") for c in comps}
    out = []
    for p in plays:
        try:
            n = int((p.get("period") or {}).get("number") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        side = side_of.get(str((p.get("team") or {}).get("id")))
        ids = [str((x.get("athlete") or {}).get("id")) for x in (p.get("participants") or []) if x.get("athlete")]
        if not side or not ids:
            continue
        t = round(_pstart(n) + _plen(n) - _secs(p.get("clock")), 1)
        typ = str((p.get("type") or {}).get("text") or "")
        text = str(p.get("text") or "").lower()
        row = {"game_id": str(game_id or ""), "t": t, "side": side, "pid": ids[0], "made": 0, "val": 0, "dist": None,
               "ast": None, "shot": None}
        if "Free Throw" in typ:
            row.update(kind="ft", made=int(bool(p.get("scoringPlay"))), val=1)
        elif p.get("shootingPlay"):
            val = p.get("pointsAttempted") or (3 if "three point" in text else 2)
            m = _DIST.search(text)
            dist = int(m.group(1)) if m else (1 if any(k in text for k in _CLOSE) else _from_xy(p.get("coordinate")))
            made = int(bool(p.get("scoringPlay")))
            row.update(kind="fg", made=made, val=int(val), dist=dist, shot=typ[:40],
                       ast=ids[1] if made and len(ids) > 1 else None)
        elif "Offensive Rebound" in typ:
            row.update(kind="oreb")
        elif "Defensive Rebound" in typ:
            row.update(kind="dreb")
        elif "Turnover" in typ:
            row.update(kind="tov")
        else:
            continue
        out.append(row)
    return out
