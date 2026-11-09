"""Lineup stints from ESPN play-by-play.

A stint is a stretch of play with the same ten players on the court. From the starters (box score), the
substitutions ("X enters the game for Y", participants = [in, out]) and the running score, every game
becomes ~25-40 stints: who was on the floor, for how long, and the points each side scored meanwhile.

Players who start a period are not announced by a substitution, so for periods after the first they are
inferred the standard way: anyone who appears in the period before being subbed in, or who is subbed out
before being subbed in, was on the floor at the start; a gap is filled with whoever finished the previous
period. Stints whose lineups are not exactly five a side are dropped (reported as coverage).
"""
import json

from .teams import canon

COLS = ["game_id", "period", "start", "dur", "h_pts", "a_pts", "home_ids", "away_ids"]


def _secs(clock):
    s = str((clock or {}).get("displayValue") or clock or "0")
    if ":" in s:
        m, x = s.split(":", 1)
        return int(m) * 60 + float(x)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _plen(p):
    return 720 if p <= 4 else 300


def _pstart(p):
    return 720 * min(p - 1, 4) + 300 * max(0, p - 5)


def build(summary, game_id=None):
    """Raw ESPN summary JSON -> (list of stint dicts, coverage share of game time)."""
    plays = summary.get("plays") or []
    box = (summary.get("boxscore") or {}).get("players") or []
    comps = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or []
    side_of = {str(c.get("id") or c.get("team", {}).get("id")): c.get("homeAway") for c in comps}
    if not plays or len(box) != 2 or len(side_of) != 2:
        return [], 0.0
    starters, roster = {}, {}
    for t in box:
        tid = str(t["team"]["id"])
        side = side_of.get(tid)
        if side is None:
            return [], 0.0
        roster[side] = set()
        starters[side] = []
        for blk in t.get("statistics") or []:
            for a in blk.get("athletes") or []:
                pid = str(a["athlete"]["id"])
                roster[side].add(pid)
                if a.get("starter"):
                    starters[side].append(pid)
    team_side = {tid: s for tid, s in side_of.items()}

    # group plays by period
    periods = {}
    for p in plays:
        n = int((p.get("period") or {}).get("number") or 0)
        if n > 0:
            periods.setdefault(n, []).append(p)

    def is_sub(p):
        return "ubstitution" in json.dumps(p.get("type") or {})

    def parts(p):
        return [str((x.get("athlete") or {}).get("id")) for x in (p.get("participants") or []) if x.get("athlete")]

    on = {"home": list(dict.fromkeys(starters["home"])), "away": list(dict.fromkeys(starters["away"]))}
    stints, total, covered = [], 0.0, 0.0
    for n in sorted(periods):
        pl = periods[n]
        if n > 1:
            # who started this period
            for side in ("home", "away"):
                seen, subbed_in, first = set(), set(), []
                for p in pl:
                    ids = parts(p)
                    if is_sub(p) and team_side.get(str((p.get("team") or {}).get("id"))) == side and len(ids) >= 2:
                        pin, pout = ids[0], ids[1]
                        if pout not in subbed_in and pout not in seen:
                            first.append(pout)
                        seen.add(pout)
                        subbed_in.add(pin)
                        seen.add(pin)
                        continue
                    for pid in ids:
                        if pid in roster[side] and pid not in seen and pid not in subbed_in:
                            first.append(pid)
                        seen.add(pid)
                first = list(dict.fromkeys(first))[:5]
                if len(first) < 5:  # fill from those on court at the end of the previous period
                    for pid in on[side]:
                        if len(first) >= 5:
                            break
                        if pid not in first and pid not in subbed_in:
                            first.append(pid)
                on[side] = first
        t0 = _pstart(n)
        cur_start, cur_h, cur_a = t0, None, None
        last_h = last_a = None

        def close(t_end, h_score, a_score):
            nonlocal cur_start, cur_h, cur_a, total, covered
            dur = t_end - cur_start
            if dur <= 0 or cur_h is None:
                return
            total += dur
            ok = len(set(on["home"])) == 5 and len(set(on["away"])) == 5
            if ok:
                covered += dur
                stints.append({"game_id": str(game_id or ""), "period": n, "start": round(cur_start, 1), "dur": round(dur, 1),
                               "h_pts": h_score - cur_h, "a_pts": a_score - cur_a,
                               "home_ids": ";".join(sorted(on["home"])), "away_ids": ";".join(sorted(on["away"]))})

        for p in pl:
            t = t0 + _plen(n) - _secs(p.get("clock"))
            h_s, a_s = int(p.get("homeScore") or 0), int(p.get("awayScore") or 0)
            if cur_h is None:
                cur_h, cur_a = (last_h if last_h is not None else h_s), (last_a if last_a is not None else a_s)
                # the score before the first play of the period: take it from the first play minus its own points
                if p.get("scoringPlay"):
                    side = team_side.get(str((p.get("team") or {}).get("id")))
                    v = int(p.get("scoreValue") or 0)
                    cur_h, cur_a = (h_s - v, a_s) if side == "home" else (h_s, a_s - v)
            if is_sub(p):
                side = team_side.get(str((p.get("team") or {}).get("id")))
                ids = parts(p)
                if side and len(ids) >= 2:
                    pin, pout = ids[0], ids[1]
                    if pout in on[side] and pin not in on[side]:
                        # the score at the moment of the substitution is the score before this play
                        close(t, h_s, a_s)
                        cur_start, cur_h, cur_a = t, h_s, a_s
                        on[side] = [pin if x == pout else x for x in on[side]]
                    elif pin not in on[side]:
                        close(t, h_s, a_s)
                        cur_start, cur_h, cur_a = t, h_s, a_s
                        on[side] = [x for x in on[side] if x != pout] + [pin]
            last_h, last_a = h_s, a_s
        close(t0 + _plen(n), last_h if last_h is not None else 0, last_a if last_a is not None else 0)
    return stints, (covered / total if total else 0.0)
