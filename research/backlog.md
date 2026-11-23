# Research backlog

The research team's single queue. Every agent reads it before starting and updates it before finishing.
The research-director keeps it ranked. Nothing here ships until it passes the replay (see the model-researcher) and the skeptic.

**Score = expected tickets gained × chance it works ÷ cost (replay hours, credits, data work).**
Baselines (2024-25 with books): tickets 460 landed (453 stated), legs 4,897/5,940. 2025-26: tickets 439.
Ladder 2024-25: 84/158 (83.5 stated), +9.2 units, best climb 11.

## Open (ranked)

| # | Idea | Why we think it might work | Cost | Status |
|---|------|----------------------------|------|--------|
| 1 | Same-game legs failing together | Monthly check (2026-11-23) showed tickets swing far more than their legs (2024-25 March tickets +14 while legs only +8; 2025-26 March tickets -9 with legs +3): all-or-nothing tickets amplify correlated legs. Tickets with 2+ legs from one team in an expected blowout: do they land below stated? Saved ticket files first. | 15 min, then 2 replays | open |
| 2 | Softer min_hi leg penalty (brief ready, no code) | Saved-leg check 2026-11-23: refit on one season, scored on the other, both directions agree the penalty is too strong. Fit on 2024-25 gives min_hi -0.050, which scores 2025-26 slightly better (+0.3 nats). Fit on 2025-26 gives -0.064, which scores 2024-25 better (+1.2 to +1.4 nats). Threshold 32 also helped both ways; 36 did not. Only 3 thresholds tried. The 36+ minutes band improves (+15 → +4, +20 → +9 legs), but 34-36 gets slightly worse, and the gain is small (likelihood-ratio test p ≈ 0.1). Legs projected for 36+ minutes are almost all from players who started their previous game, so that split doesn't rule out the replay leak. No code needed: the existing "refit" rule in backtest/tickets.py reads LEG_DOG and LEG_MINHI. Prefix every run with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 ALT_BLEND=0.2987,0.5242,-0.0711 ALT_MODE=live nohup`. Runs: `TAG=_mh064 LEG_DOG=-0.010 LEG_MINHI=-0.064 python -m backtest.tickets 2025 2024-10-01 2025-04-30 refit`; `TAG=_mh050 LEG_DOG=-0.010 LEG_MINHI=-0.050 python -m backtest.tickets 2026 2025-10-01 2026-04-30 refit`; `TAG=_live python -m backtest.tickets 2026` (fresh baseline: /tmp/tickets_2026_lad.json predates the books changes). Stop if either season loses tickets or gains 2 or fewer (monthly ticket noise is about ±9). Pass: 2024-25 above 460 tickets at about 453 stated with legs at least 4,897, and 2025-26 above the fresh baseline at the same stated chance. | 3 replays (2 variants + fresh 2025-26 baseline) | brief ready |
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
- Ladder selection by stat (2026-11-23, /tmp/ladder_2025_live.json 84/158 and /tmp/ladder_2025_val.json 82/158): assists land 20/31 (16.4 stated) and 27/41 (21.3 stated), rebounds 29/60 (31.8) and 26/60 (31.7). Tier 3 is 17/29 vs 14.7 stated. The largest |z| is 1.8 across about 18 cells (stat, tier, line height, home/away, favourite/underdog), and none survives a multiple-comparison check. Ticket legs never sit at Ladder-like chances (only 15 legs at 0.45-0.60 per season), and rebound legs land as stated in tickets in both seasons (-1.6, +5.9). Retest when 2025-26 or 2026-27 has a full Ladder replay with current code.
- Monthly / season-phase calibration of leg chances (2026-11-23, saved replays /tmp/tickets_2025_live.json and /tmp/tickets_2026_lad.json, no new replay): legs land as stated in every month of both seasons (largest |z| 1.38; chi-square p 0.94 and 0.81). The 2024-25 ticket shape (Nov 78 vs 82.6, Mar 110 vs 96.0) reverses in 2025-26 (Nov 92 vs 83.0, Mar 76 vs 85.0): monthly ticket z correlate r = -0.61 across seasons, signs agree 2 of 6 months, chi-square p 0.53 and 0.44. Same in 4-week blocks and within chance bands (no level shift, no slope). Ticket swings are noise from all-or-nothing tickets, not drift. Retest only with a third season of replay.
See data/replay.json "rejected": minutes calibration, 18 leg factors, gradient boosting, market spreads/totals, referees, lineup role changes, play-by-play rotations, player blowout minutes, trade effects, after-blowout, last-game form, national TV, opponent strength, tanking, travel, altitude, streaks, shooting luck, real main lines in building, line movement (early test), later ticket lock, per-stat blend weights, market distillation, situational blends, lifting legs with book prices.

## Questions nobody has answered yet
- Are assist legs understated? Ticket legs: +4.4 of 849 in 2024-25 (z +0.4), +24.2 of 694 in 2025-26 (z +2.35, above stated in both chance bands), and the Ladder also leans the same way (+3.6 to +5.7). LEG_W has a stat-specific term only for threes (tpm_high). Cheap check: fit one logit offset for assists on one season's saved legs and score it on the other (no replay).
- Why do tickets in the 2 weeks after the trade deadline land ~3% below stated in both seasons, when projections show no bias there?
- Is the Ladder edge real at Winamax's own prices, or only at US-book-derived prices? (needs payout-auditor records)
- Do our misses cluster by team (a coach we model badly)?
