# Research backlog

The research team's single queue. Every agent reads it before starting and updates it before finishing.
The research-director keeps it ranked. Nothing here ships until it passes the replay (see the model-researcher) and the skeptic.

**Score = expected tickets gained × chance it works ÷ cost (replay hours, credits, data work).**
Baselines (2024-25 with books): tickets 460 landed (453 stated), legs 4,897/5,940. 2025-26: tickets 439.
Ladder 2024-25: 84/158 (83.5 stated), +9.2 units, best climb 11.

## Open (ranked)

| # | Idea | Why we think it might work | Cost | Status |
|---|------|----------------------------|------|--------|
| 1 | Monthly drift in leg chances | 2024-25 replay: March legs land 110 vs 96 expected, November 78 vs 82.6. If 2025-26 shows the same shape, a season-phase calibration is real. Check the saved leg files first (no replay). | 10 min analysis, then 2 replays | open |
| 2 | Season-opener star over-projection | Stars' PRA is 6-14% below projection in their first game (~100 games a year). Untested. | 2 replays | open |
| 3 | Ladder selection by stat | Ladder replay tier 3 made +5.5 units, tier 4 about 0. Check if some stats (reb 60 picks, ast 31) land above stated. Saved ladder files, no replay. | 10 min | open |
| 4 | Close the replay leak | The walk knows who actually played, so edges vs opening lines are inflated. An honest replay needs "expected to play at lock" (prior-game status + injury report history). Makes every future verdict trustworthy. | data search + 1 day | needs data (data-scout) |
| 5 | Same-game legs failing together | Tickets with 2+ legs from one team in an expected blowout: do they land below stated? Saved ticket files first. | 15 min, then 2 replays | open |
| 6 | Star rest: which game of a back-to-back | Stars skipping a b2b night pick the home / national-TV game ~66%. Not in rest.chance_sits. Low ticket value (Winamax voids sitters), but sharper minutes for teammates. | 2 replays | open |
| 7 | Refit the X+ blend on live prices | ALT_W was fitted on ESPN BET 2024-25. Refit on our own live alt rungs once ~500 have settled. | 30 min | waiting for data (~mid-December 2026) |
| 8 | Projection + market blend for every leg | pipeline/vsmarket.py tracks our projections vs Pinnacle closing lines. Decide at ~150 games. | 1 hour | waiting for data |
| 9 | Prop-line movement | Lines that move toward us between open and lock. Needs ~2 months of data/props/lines.csv. | 2 replays | waiting for data (mid-January 2027) |

## Done (kept)
- Back-to-back for key players (B2B_KEY): 2024-25 tickets 450 → 446, 2025-26 429 → 439; legs +13/+15.
- X+ prices lower over-optimistic legs (alt_lower): 440 → 459.
- Tickets stated at the blended chance (restate): 460 landed vs 453 stated.
- Ladder priced from the exact X+ rung (ALT_FAIR): 84/158 vs 83.5 stated, +9.2 units.

## Rejected (do not retest without new data)
See data/replay.json "rejected": minutes calibration, 18 leg factors, gradient boosting, market spreads/totals, referees, lineup role changes, play-by-play rotations, player blowout minutes, trade effects, after-blowout, last-game form, national TV, opponent strength, tanking, travel, altitude, streaks, shooting luck, real main lines in building, line movement (early test), later ticket lock, per-stat blend weights, market distillation, situational blends, lifting legs with book prices.

## Questions nobody has answered yet
- Why do tickets in the 2 weeks after the trade deadline land ~3% below stated in both seasons, when projections show no bias there?
- Is the Ladder edge real at Winamax's own prices, or only at US-book-derived prices? (needs payout-auditor records)
- Do our misses cluster by team (a coach we model badly)?
