"""Game simulation, before tip-off: thousands of versions of tonight's game, each with a final score, every
player's minutes and every player's box score line. Used for the "How tonight plays out" panel on game
pages and for how legs of the same game move together in tickets.

Each run, measured on 190,000 past player-games (2018-19 to 2024-25, projections made before each game):
  1. Final margin and total from the game estimate (spread per game from the model).
  2. Overtime when the regulation margin ends within a point (about 6% of games, as in the NBA).
  3. Minutes: each player's projection, then blowouts (starters sit, the bench plays: per point of margin
     beyond 12, about -0.6% for heavy-minute players and +0.4% for the rest), overtime (+11% / +6%) and a
     night-to-night swing (sd about 20% for heavy-minute players, about 45% for the rest).
  4. Counts: mean = projection x minutes ratio x (team points / expected)^beta, beta measured per stat
     (points 0.96, threes 0.97, assists 0.70, rebounds 0.01), then a negative binomial draw whose spread
     brings the total variance back to what the player's history shows.
  5. Teammates share the team's points: within a run, the team's scorers are pulled partly towards the
     team's simulated points, which reproduces the measured -0.10 correlation between teammates' scoring
     once the team's total is known.
"""
import numpy as np

SIMS = 20000
BETA = {"pts": 0.96, "tpm": 0.97, "ast": 0.70, "reb": 0.01}
BIG_MIN = 28.0
MIN_BLOW = {True: -0.0057, False: 0.0040}   # per point of final margin beyond BLOW_FROM
MIN_OT = {True: 0.106, False: 0.063}
MIN_SD = {True: 0.195, False: 0.45}
BLOW_FROM = 12.0
OT_BAND = 0.8          # |regulation margin| below this goes to overtime
MIN_SD_SCALE = 0.75    # share of the measured minutes swing that also moves the counts (tuned walk-forward)
BETA_SCALE = 1.0       # how much of the measured team-points link carries into a run (tuned walk-forward)
SHARE_PULL = 0.70      # how strongly a team's simulated scorers are pulled to the team's simulated points


def _nb(rng, mu, disp):
    """Negative binomial draws with mean mu (array) and variance mu x disp (disp > 1), Poisson-gamma mixture."""
    mu = np.maximum(mu, 1e-3)
    d = max(float(disp), 1.02)
    shape = mu / (d - 1.0)
    return rng.poisson(rng.gamma(shape, d - 1.0))


def simulate(game, est, players, disp, rng, sims=SIMS):
    """game: {"home","away"}; est: margin, total, sd_margin, sd_total, home_pts, away_pts;
    players: {"home": [player blocks with id, min, pts, reb, ast, tpm, p_play, out], "away": [...]}.
    Returns {"m","t","home","away","ot","players": {id: {"min","pts","reb","ast","tpm","pra"}}}."""
    m = rng.normal(est["margin"], est["sd_margin"], sims)
    t = rng.normal(est["total"], est["sd_total"], sims)
    ot = np.abs(m) < OT_BAND
    if ot.any():  # overtime: a fresh 5-minute period decides it
        extra = rng.normal(0, 4.5, ot.sum())
        extra = np.where(np.abs(extra) < 0.5, np.sign(extra + 1e-9) * 1.0, extra)
        m[ot] = np.sign(extra) * np.maximum(np.abs(extra), 1.0)
        t[ot] += rng.normal(20.0, 4.0, ot.sum())
    hp, ap = (t + m) / 2, (t - m) / 2
    out = {"m": m, "t": t, "home": hp, "away": ap, "ot": ot, "players": {}}
    blow = np.maximum(np.abs(m) - BLOW_FROM, 0.0)
    for side, pts_ in (("home", hp), ("away", ap)):
        exp_team = max(est["home_pts"] if side == "home" else est["away_pts"], 60.0)
        r = np.clip(pts_ / exp_team, 0.55, 1.6)
        lr = np.log(r)
        team, f_mean = {}, {}
        for pl in players.get(side, []):
            if pl.get("out") or not pl.get("min"):
                continue
            big = pl["min"] >= BIG_MIN
            sd = MIN_SD[big] * MIN_SD_SCALE
            f = np.exp(MIN_BLOW[big] * blow + MIN_OT[big] * ot + rng.normal(0, sd, sims) - sd * sd / 2)
            p_play = float(pl.get("p_play", 1.0) or 1.0)
            if p_play < 0.999:  # some runs he does not play at all
                f = f * (rng.random(sims) < p_play)
            mins = np.minimum(pl["min"] * f, 53.0 + 5 * ot)
            sims_ = {"min": mins}
            for st, beta in BETA.items():
                proj = float(pl.get(st) or 0.0)
                mu = proj * f * np.exp(BETA_SCALE * beta * lr)
                # spread left after minutes and team points: total variance mu x disp, minus what the
                # simulated mean already varies
                v_mu = float(np.var(mu)); mbar = max(float(np.mean(mu)), 1e-3)
                d_left = max(1.02, float(disp.get(st, 1.5)) - v_mu / mbar)
                sims_[st] = _nb(rng, mu, d_left).astype(float)
            team[pl["id"]] = sims_
            f_mean[pl["id"]] = np.exp(MIN_BLOW[big] * blow + MIN_OT[big] * ot)  # expected minutes factor this run
        # teammates share the team's points: pull the simulated scorers partly towards the team's points
        if team:
            # target: what the players who play in this run were expected to score, at this run's team pace
            # (so a doubtful teammate sitting out does not hand his points to the others)
            proj_pts = {pl["id"]: float(pl.get("pts") or 0.0) for pl in players.get(side, [])}
            tot = sum(v["pts"] for v in team.values())
            target = sum(proj_pts[k] * (v["min"] > 0) * f_mean[k] for k, v in team.items()) * r
            k = np.where(tot > 0, (target / np.maximum(tot, 1e-6)) ** SHARE_PULL, 1.0)
            for v in team.values():
                v["pts"] = np.round(v["pts"] * k)
                v["pra"] = v["pts"] + v["reb"] + v["ast"]
            out["players"].update(team)
    return out


def summary(sim, game, lines=None):
    """What the game page shows: outcome shares, margin histogram, and each player's range."""
    m, t = sim["m"], sim["t"]
    edges = list(range(-30, 31, 5))
    hist = np.histogram(np.clip(m, -32, 32), bins=[-99] + edges + [99])[0] / len(m)
    pl = {}
    for pid, s in sim["players"].items():
        played = s["min"] > 0
        if played.mean() < 0.05:
            continue
        row = {"p_play": round(float(played.mean()), 3)}
        for st in ("min", "pts", "reb", "ast", "pra"):
            x = s[st][played]
            row[st] = [round(float(np.percentile(x, q)), 1) for q in (10, 50, 90)]
        for st, L in (lines or {}).get(pid, {}).items():
            if st in s:
                # when he plays (Winamax voids a player leg if he does not)
                row.setdefault("lines", {})[st] = {"line": L, "over": round(float((s[st][played] > L).mean()), 3)}
        pl[pid] = row
    return {
        "n": int(len(m)), "home_win": round(float((m > 0).mean()), 3), "ot": round(float(sim["ot"].mean()), 3),
        "blowout_home": round(float((m >= 15).mean()), 3), "blowout_away": round(float((m <= -15).mean()), 3),
        "close": round(float((np.abs(m) <= 5).mean()), 3),
        "margin_hist": {"edges": edges, "p": [round(float(x), 4) for x in hist]},
        "total": [round(float(np.percentile(t, q)), 1) for q in (10, 50, 90)],
        "players": pl,
    }
