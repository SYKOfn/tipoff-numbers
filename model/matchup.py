"""Player-by-player comparison for a game: physical (size, age, experience, workload, rest) and technical
(scoring, shooting, playmaking, rebounding, ball security, defensive activity) profiles of the likely starters,
paired by role. Shown on the game page; plain facts from box scores and ESPN rosters, no invented ratings."""
from datetime import date

PER36 = ("pts", "reb", "ast", "tpm", "tpa", "fga", "fta", "tov", "stl", "blk", "oreb")
ROLE = {"G": 0, "F": 1, "C": 2}


def _f(x):
    try:
        x = float(x)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def profiles(players, day_of, season_games, rosters, today):
    """{player_id: profile} from this season's box scores (players DataFrame) and ESPN rosters."""
    if players is None or not len(players):
        return {}
    p = players[players["game_id"].astype(str).isin(season_games) & (players["min"].fillna(0) > 0)].copy()
    if not len(p):
        return {}
    p["_day"] = p["game_id"].astype(str).map(day_of).fillna("")
    out = {}
    td = today if isinstance(today, date) else date.fromisoformat(str(today)[:10])
    for pid, d in p.groupby(p["player_id"].astype(str)):
        mins = float(d["min"].sum())
        if mins < 30:
            continue
        tot = {k: float(d[k].fillna(0).sum()) for k in PER36 if k in d}
        per = {k: round(36 * v / mins, 1) for k, v in tot.items()}
        fga, fta = tot.get("fga", 0), tot.get("fta", 0)
        days = sorted(x for x in d["_day"] if x)
        last = date.fromisoformat(days[-1]) if days else None
        recent = d[d["_day"].map(lambda x: bool(x) and 0 < (td - date.fromisoformat(x)).days <= 7)]
        ro = (rosters or {}).get(str(pid)) or {}
        out[str(pid)] = {
            "gp": int(len(d)), "mpg": round(mins / len(d), 1),
            "per36": per,
            "ts": round(tot.get("pts", 0) / (2 * (fga + 0.44 * fta)), 3) if fga + fta > 0 else None,
            "p3": round(tot.get("tpm", 0) / tot["tpa"], 3) if tot.get("tpa", 0) >= 10 else None,
            "tpa": int(tot.get("tpa", 0)),
            "usage36": round(36 * (fga + 0.44 * fta + tot.get("tov", 0)) / mins, 1),
            "ast_tov": round(tot.get("ast", 0) / tot["tov"], 2) if tot.get("tov", 0) > 0 else None,
            "stocks36": round(36 * (tot.get("stl", 0) + tot.get("blk", 0)) / mins, 1),
            "min7": round(float(recent["min"].sum()), 0), "g7": int(len(recent)),
            "rest_days": (td - last).days - 1 if last else None,
            "height_in": _f(ro.get("height_in")), "weight_lb": _f(ro.get("weight_lb")),
            "age": ro.get("age"), "exp": ro.get("exp"),
        }
    return out


def _height(h):
    return f"{int(h) // 12}'{int(h) % 12}\"" if h else None


def _starters(lst):
    """The five likely starters (most projected minutes, not out), ordered guards -> forwards -> centers."""
    ok = [x for x in lst or [] if not x.get("out") and (x.get("p_play") or 1) >= 0.5]
    top = sorted(ok, key=lambda x: -(x.get("min") or 0))[:5]
    return sorted(top, key=lambda x: (ROLE.get((x.get("pos") or "F")[:1], 1), -(x.get("min") or 0)))


def _edges(a, b, an, bn):
    """Plain-words differences worth noticing between two paired players (a is home, b is away)."""
    out = []

    def side(diff, good_for_a):
        return an if good_for_a else bn
    ha, hb = a.get("height_in"), b.get("height_in")
    if ha and hb and abs(ha - hb) >= 2:
        out.append(f"{side(0, ha > hb)} is {int(abs(ha - hb))} in taller")
    wa, wb = a.get("weight_lb"), b.get("weight_lb")
    if wa and wb and abs(wa - wb) >= 15:
        out.append(f"{side(0, wa > wb)} is {int(abs(wa - wb))} lb heavier")
    ga, gb = a.get("age"), b.get("age")
    if ga and gb and abs(ga - gb) >= 6:
        out.append(f"{side(0, ga < gb)} is {abs(ga - gb)} years younger")
    ma, mb = a.get("min7"), b.get("min7")
    if ma is not None and mb is not None and abs(ma - mb) >= 35:
        out.append(f"{side(0, ma < mb)} has played {int(abs(ma - mb))} fewer minutes in the last 7 days")
    ra, rb = a.get("rest_days"), b.get("rest_days")
    if ra is not None and rb is not None and ra != rb and min(ra, rb) == 0:
        out.append(f"{side(0, ra > rb)} is more rested ({bn if ra > rb else an} played yesterday)")
    pa, pb = a.get("p3"), b.get("p3")
    if pa and pb and min(a.get("tpa", 0), b.get("tpa", 0)) >= 20 and abs(pa - pb) >= 0.06:
        out.append(f"{side(0, pa > pb)} shoots threes better ({round(100 * max(pa, pb))}% vs {round(100 * min(pa, pb))}%)")
    sa, sb = (a.get("per36") or {}), (b.get("per36") or {})
    for k, label, gap in (("reb", "rebounds", 2.5), ("ast", "playmaking (assists)", 2.0), ("pts", "scoring", 5.0)):
        if sa.get(k) is not None and sb.get(k) is not None and abs(sa[k] - sb[k]) >= gap:
            out.append(f"{side(0, sa[k] > sb[k])}: more {label} ({max(sa[k], sb[k])} vs {min(sa[k], sb[k])} per 36 min)")
    return out[:4]


def compare(players, prof):
    """{"slots": [...], "teams": {...}} for a game's projected players (payload["players"])."""
    if not players or not prof:
        return None
    hs, as_ = _starters(players.get("home")), _starters(players.get("away"))
    if len(hs) < 5 or len(as_) < 5:
        return None
    pick = lambda pr: {k: pr.get(k) for k in ("gp", "mpg", "per36", "ts", "p3", "tpa", "usage36", "ast_tov", "stocks36",
                                              "min7", "g7", "rest_days", "height_in", "weight_lb", "age", "exp")}
    slots = []
    for h, a in zip(hs, as_):
        ph, pa = prof.get(str(h["id"])) or {}, prof.get(str(a["id"])) or {}
        slots.append({"home": {"id": h["id"], "name": h["name"], "pos": h.get("pos"), "height": _height(ph.get("height_in")), **pick(ph)},
                      "away": {"id": a["id"], "name": a["name"], "pos": a.get("pos"), "height": _height(pa.get("height_in")), **pick(pa)},
                      "edges": _edges(ph, pa, h["name"].split()[-1], a["name"].split()[-1])})

    def team(lst):
        ps = [prof.get(str(x["id"])) or {} for x in lst]
        mean = lambda k, d=1: (round(sum(p[k] for p in ps if p.get(k)) / max(1, sum(1 for p in ps if p.get(k))), d)
                               if any(p.get(k) for p in ps) else None)
        return {"height_in": mean("height_in"), "height": _height(mean("height_in")), "weight_lb": mean("weight_lb"),
                "age": mean("age"), "min7": round(sum(p.get("min7") or 0 for p in ps)),
                "reb36": round(sum((p.get("per36") or {}).get("reb", 0) for p in ps), 1),
                "p3": mean("p3", 3), "ts": mean("ts", 3)}
    return {"slots": slots, "teams": {"home": team(hs), "away": team(as_)}}
