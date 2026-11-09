"""Chance a key player sits a game, before any news.

Measured on every stored game: a player averaging 24+ minutes over his last 10 team games, who played
the previous game, misses this one about 6-7% of the time - more on the second night of a back-to-back,
more late in the regular season, almost never in the playoffs. Those measured rates (out of sample: they
improved the log loss over a flat rate on 2024-25 and 2025-26) are used for games still more than
NEWS_HOURS away when the player is not on the injury report: his expected minutes in the team-strength
sum are scaled by the chance he plays. Closer to tip-off the injury report is trusted instead.
"""
from collections import defaultdict

KEY_MIN = 24.0
NEWS_HOURS = 6.0
MIN_N = 300


def cell(b2b, month, playoff):
    if playoff:
        return "playoffs"
    late = month in (3, 4)
    return f"{'b2b' if b2b else 'rest'}-{'late' if late else 'early'}"


def measure(games, players, ctxs):
    """{cell: {"n", "rate"}} from stored box scores."""
    if not len(players):
        return {}
    mins = defaultdict(dict)
    for gid, team, pid, m in zip(players["game_id"].astype(str), players["team"], players["player_id"].astype(str),
                                 players["min"]):
        try:
            m = float(m)
        except (TypeError, ValueError):
            m = 0.0
        mins[(gid, team)][pid] = m if m == m else 0.0
    acc = defaultdict(lambda: [0, 0])
    hist = defaultdict(dict)   # team -> pid -> list of minutes
    g = games[games["box"] == 1].sort_values(["date", "game_id"])
    for gid, day, home, away, stype in zip(g["game_id"].astype(str), g["day"], g["home"], g["away"], g["stype"]):
        for side, team in (("home", home), ("away", away)):
            m = mins.get((gid, team))
            if m is None:
                continue
            ctx = (ctxs.get(gid) or {}).get(side) or {}
            k = cell(ctx.get("b2b", 0), int(str(day)[5:7]), int(stype) == 3)
            for pid, h in hist[team].items():
                if len(h) >= 5 and h[-1] > 0 and sum(h[-10:]) / len(h[-10:]) >= KEY_MIN:
                    acc[k][0] += 1
                    acc[k][1] += int(m.get(pid, 0.0) <= 0)
            for pid in set(hist[team]) | set(m):
                hist[team].setdefault(pid, []).append(m.get(pid, 0.0))
    return {k: {"n": n, "rate": round(a / n, 4)} for k, (n, a) in acc.items() if n >= MIN_N}


def chance_sits(table, b2b, month, playoff):
    c = table.get(cell(b2b, month, playoff))
    return c["rate"] if c else 0.0
