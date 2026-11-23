# Research backlog

The research team's single queue. Every agent reads it before starting and updates it before finishing.
The research-director keeps it ranked. Nothing here ships until it passes the replay (see the model-researcher) and the skeptic.

**Score = expected tickets gained × chance it works ÷ cost (replay hours, credits, data work).**
Baselines (2024-25 with books): tickets 460 landed (453 stated), legs 4,897/5,940. 2025-26: tickets 439.
Ladder 2024-25: 84/158 (83.5 stated), +9.2 units, best climb 11.

## Open (ranked)

| # | Idea | Why we think it might work | Cost | Status |
|---|------|----------------------------|------|--------|
| 1 | Ladder selection by stat | Ladder replay tier 3 made +5.5 units, tier 4 about 0. Check if some stats (reb 60 picks, ast 31) land above stated. Saved ladder files, no replay. | 10 min | open |
| 2 | Same-game legs failing together | Monthly check (2026-11-23) showed tickets swing far more than their legs (2024-25 March tickets +14 while legs only +8; 2025-26 March tickets -9 with legs +3): all-or-nothing tickets amplify correlated legs. Tickets with 2+ legs from one team in an expected blowout: do they land below stated? Saved ticket files first. | 15 min, then 2 replays | open |
| 3 | Season-opener star over-projection | Stars' PRA is 6-14% below projection in their first game (~100 games a year). Untested. | 2 replays | open |
| 4 | Close the replay leak | The walk knows who actually played, so edges vs opening lines are inflated. An honest replay needs "expected to play at lock" (prior-game status + injury report history). Makes every future verdict trustworthy. | data search + 1 day | needs data (data-scout) |
| 5 | Star rest: which game of a back-to-back | Stars skipping a b2b night pick the home / national-TV game ~66%. Not in rest.chance_sits. Low ticket value (Winamax voids sitters), but sharper minutes for teammates. | 2 replays | open |
| 6 | Refit the X+ blend on live prices | ALT_W was fitted on ESPN BET 2024-25. Refit on our own live alt rungs once ~500 have settled. | 30 min | waiting for data (~mid-December 2026) |
| 7 | Projection + market blend for every leg | pipeline/vsmarket.py tracks our projections vs Pinnacle closing lines. Decide at ~150 games. | 1 hour | waiting for data |
| 8 | Prop-line movement | Lines that move toward us between open and lock. Needs ~2 months of data/props/lines.csv. | 2 replays | waiting for data (mid-January 2027) |

## Done (kept)
- Back-to-back for key players (B2B_KEY): 2024-25 tickets 450 → 446, 2025-26 429 → 439; legs +13/+15.
- X+ prices lower over-optimistic legs (alt_lower): 440 → 459.
- Tickets stated at the blended chance (restate): 460 landed vs 453 stated.
- Ladder priced from the exact X+ rung (ALT_FAIR): 84/158 vs 83.5 stated, +9.2 units.

## Rejected (do not retest without new data)
- Monthly / season-phase calibration of leg chances (2026-11-23, saved replays /tmp/tickets_2025_live.json and /tmp/tickets_2026_lad.json, no new replay): legs land as stated in every month of both seasons (largest |z| 1.38; chi-square p 0.94 and 0.81). The 2024-25 ticket shape (Nov 78 vs 82.6, Mar 110 vs 96.0) reverses in 2025-26 (Nov 92 vs 83.0, Mar 76 vs 85.0): monthly ticket z correlate r = -0.61 across seasons, signs agree 2 of 6 months, chi-square p 0.53 and 0.44. Same in 4-week blocks and within chance bands (no level shift, no slope). Ticket swings are noise from all-or-nothing tickets, not drift. Retest only with a third season of replay.
See data/replay.json "rejected": minutes calibration, 18 leg factors, gradient boosting, market spreads/totals, referees, lineup role changes, play-by-play rotations, player blowout minutes, trade effects, after-blowout, last-game form, national TV, opponent strength, tanking, travel, altitude, streaks, shooting luck, real main lines in building, line movement (early test), later ticket lock, per-stat blend weights, market distillation, situational blends, lifting legs with book prices.

## Questions nobody has answered yet
- Is the min_hi leg penalty (LEG_W min_hi -0.09 per projected minute above 34) too strong? Legs of players projected 36+ minutes land above stated in both seasons (+16.6 of 695, z +1.65; +14.9 of 515, z +1.70), but 34-36 lands below in 2024-25 (-12.7) and is flat in 2025-26 (-4.4). Also 32-34 is +21/+18 with no penalty. Check: refit min_hi on 2024-25 legs alone, apply to 2025-26 saved legs (no replay), and only then 2 replays. Caveat: projected minutes still carry the replay leak (#4).
- Why do tickets in the 2 weeks after the trade deadline land ~3% below stated in both seasons, when projections show no bias there?
- Is the Ladder edge real at Winamax's own prices, or only at US-book-derived prices? (needs payout-auditor records)
- Do our misses cluster by team (a coach we model badly)?
