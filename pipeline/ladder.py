"""The Ladder: one bet a day at Winamax odds of 2.00-2.10 (model/parlay.py ladder_pick), played as a game.

Every landed bet climbs one level; a miss sends the ladder back to level 1; a void bet (the player sat) or a day
without a pick keeps the level. Nothing is stored apart from each day's locked pick and its result (data/parlays),
so the levels are rebuilt from the full history on every run and can never drift.
"""
START = 10.0      # the example stake: what 10 rolled over from level 1 would be worth now
GOAL = 10         # the finish line: winning the level-10 bet completes the ladder (about 1,000 times the stake at 2.0)


def state(days):
    """days: [(day, ladder pick or None), ...] oldest first, each pick with "result" once its game is over.
    Returns the current level, the climb so far, the best climb and every step, newest first."""
    level, climb, bank = 1, [], START
    best, best_days, runs, steps, trophies = 0, None, 0, [], []
    for day, lp in days:
        if not lp:
            continue
        res = lp.get("result")
        step = {"day": day, "desc": lp["leg"]["desc"], "matchup": lp["leg"].get("matchup"), "odds": lp["odds"],
                "odds_real": lp.get("odds_real", False), "p": lp["p"], "level": level, "result": res, "clv": lp.get("clv")}
        if res == "hit":
            climb.append(step)
            bank *= lp["odds"]
            if len(climb) > best:
                best, best_days = len(climb), (climb[0]["day"], day)
            level += 1
            if level > GOAL:  # the ladder is complete: a trophy, cash out, and a new ladder from level 1
                trophies.append({"from": climb[0]["day"], "to": day, "bank": round(bank, 2)})
                climb, bank, level = [], START, 1
        elif res == "miss":
            if climb or level > 1:
                runs += 1
            climb, bank, level = [], START, 1
        steps.append(step)
    done = [s for s in steps if s["result"] in ("hit", "miss")]
    moved = [s["clv"] for s in steps if s.get("clv")]
    beat = sum(1 for c in moved if (c.get("p") or c.get("pts") or 0) > 0)
    return {"level": level, "goal": GOAL, "climb": climb, "bank": round(bank, 2), "start": START,
            "best": best, "best_days": best_days, "restarts": runs, "trophies": trophies,
            "bets": len(done), "won": sum(s["result"] == "hit" for s in done),
            "expected": round(sum(s["p"] for s in done), 2),
            "profit": round(sum((s["odds"] - 1) if s["result"] == "hit" else -1 for s in done), 2),
            "clv_n": len(moved), "clv_beat": beat,  # the price at the lock vs the close: moved our way?
            "steps": steps[::-1][:90]}
