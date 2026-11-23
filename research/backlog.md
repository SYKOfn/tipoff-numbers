# Research backlog

The research team's single queue. Every agent reads it before starting and updates it before finishing.
The research-director keeps it ranked. Nothing here ships until it passes the replay (see the model-researcher) and the skeptic.

**Score = expected tickets gained × chance it works ÷ cost (replay hours, credits, data work).**
Baselines (2024-25 with books): tickets 460 landed (453 stated), legs 4,897/5,940. 2025-26 with books (dated run, `base` rule): tickets 436 (stated 429.6), legs 4,857/5,915.
Ladder 2024-25: 84/158 (83.5 stated), +9.2 units, best climb 11.

## Open (ranked)

| # | Idea | Why we think it might work | Cost | Status |
|---|------|----------------------------|------|--------|
| 1 | Season-opener star over-projection | Stars' PRA is 6-14% below projection in their first game (~100 games a year). Untested. | 2 replays | open |
| 2 | Close the replay leak | The walk knows who actually played, so edges vs opening lines are inflated. An honest replay needs "expected to play at lock" (prior-game status + injury report history). Makes every future verdict trustworthy. | data search + 1 day | needs data (data-scout) |
| 3 | Star rest: which game of a back-to-back | Stars skipping a b2b night pick the home / national-TV game ~66%. Not in rest.chance_sits. Low ticket value (Winamax voids sitters), but sharper minutes for teammates. | 2 replays | open |
| 4 | Refit the X+ blend on live prices | ALT_W was fitted on ESPN BET 2024-25. Refit on our own live alt rungs once ~500 have settled. | 30 min | waiting for data (~mid-December 2026) |
| 5 | Projection + market blend for every leg | pipeline/vsmarket.py tracks our projections vs Pinnacle closing lines. Decide at ~150 games. | 1 hour | waiting for data |
| 6 | Prop-line movement | Lines that move toward us between open and lock. Needs ~2 months of data/props/lines.csv. | 2 replays | waiting for data (mid-January 2027) |

## Done (kept)
- Back-to-back for key players (B2B_KEY): 2024-25 tickets 450 → 446, 2025-26 429 → 439; legs +13/+15.
- X+ prices lower over-optimistic legs (alt_lower): 440 → 459.
- Tickets stated at the blended chance (restate): 460 landed vs 453 stated.
- Ladder priced from the exact X+ rung (ALT_FAIR): 84/158 vs 83.5 stated, +9.2 units.

## Rejected (do not retest without new data)
- Win-chance slope calibration and moneyline-leg restating (2026-11-23, /tmp/tickets_2025_b25.json and /tmp/tickets_2026_b26.json). I rebuilt the model's win chances for every game from m_exp with sd(m) = 13.8 - 0.106|m|, recovered from the moneyline legs with residual 0.02. Across all games the model is calibrated: logit slope 1.16 in 2024-25 and 1.03 in 2025-26. Fitted on one season and scored on the other, the slope is 1.06 and 1.05, and log loss improves by only 0.0001 to 0.0002. The moneyline legs only look understated because, with no odds, the replay shrinks the leg chance 20% towards 50/50 (parlay.team_legs, sigmoid(0.8 logit ph)). Without that shrink the picked legs land as stated: 124/143 vs about 118 in 2024-25, 132/158 vs 131.4 in 2025-26. Live moneyline legs always have odds and are blended 50/50 with the books, so this is a replay artifact, not a live bias. No live win-chance calibration exists (pipeline/run.py blends model and market, win_home_model / win_home_market), so there is nothing to mirror. Replay leak: the game model's lineup features (engine.build_context, lfeat) use the players who actually played. Retest only if the replay is given historical moneyline prices.
- Same-game legs failing together (2026-11-23, /tmp/tickets_2025_b25.json and /tmp/tickets_2026_b26.json): within a ticket, leg misses are not correlated in either season. Same-team pairs give +0.016 and -0.020, opposite-team pairs -0.016 and -0.008 (about 5,600 to 6,200 pairs each). Stated tickets are about 1% above the product of their legs (453.1 vs 447.9; 429.6 vs 425.5) and still land slightly above stated (+6.9, +6.4). No group repeats across seasons. Max 4 legs from one team: +2.2 then -14.5. Max 3: +1.4 then +20.2. All legs from one team: +3.4 then +0.7. Expected margin 8+: +6.0 then -5.0. Fav/dog leg mixes at margin 6+: no cell above |z| 1.6. Ticket swings are not driven by correlated legs.
- Assist-leg logit offset (2026-11-23, same files): fitted on 2024-25 it is +0.052, which helps 2025-26 only slightly (+1.05 nats over 689 legs, still 579 landed vs 561.8 stated). Fitted on 2025-26 it is +0.231, which hurts 2024-25 (-1.65 nats, 705 vs 724.9 stated). The 2025-26 excess is only in lines of 2.5 or less (407/474 vs 385.5) and players averaging 3-6 assists. Primary handlers (6+ assists a game) are flat in both seasons. Retest with 2026-27 legs if low assist lines stay high.
- Softer min_hi leg penalty (2026-11-23): saved-leg refits suggested -0.05/-0.064 instead of -0.09, but the replay with books fails: 2024-25 460 → 460 tickets (stated 453.1 → 454.7), 2025-26 436 → 431 (stated 429.6 → 432.2). Better leg log loss did not mean more tickets. Fresh 2025-26 baseline with books: 436 tickets, legs 4,857/5,915.
- Ladder selection by stat (2026-11-23, /tmp/ladder_2025_live.json 84/158 and /tmp/ladder_2025_val.json 82/158): assists land 20/31 (16.4 stated) and 27/41 (21.3 stated), rebounds 29/60 (31.8) and 26/60 (31.7). Tier 3 is 17/29 vs 14.7 stated. The largest |z| is 1.8 across about 18 cells (stat, tier, line height, home/away, favourite/underdog), and none survives a multiple-comparison check. Ticket legs never sit at Ladder-like chances (only 15 legs at 0.45-0.60 per season), and rebound legs land as stated in tickets in both seasons (-1.6, +5.9). Retest when 2025-26 or 2026-27 has a full Ladder replay with current code.
- Monthly / season-phase calibration of leg chances (2026-11-23, saved replays /tmp/tickets_2025_live.json and /tmp/tickets_2026_lad.json, no new replay): legs land as stated in every month of both seasons (largest |z| 1.38; chi-square p 0.94 and 0.81). The 2024-25 ticket shape (Nov 78 vs 82.6, Mar 110 vs 96.0) reverses in 2025-26 (Nov 92 vs 83.0, Mar 76 vs 85.0): monthly ticket z correlate r = -0.61 across seasons, signs agree 2 of 6 months, chi-square p 0.53 and 0.44. Same in 4-week blocks and within chance bands (no level shift, no slope). Ticket swings are noise from all-or-nothing tickets, not drift. Retest only with a third season of replay.
See data/replay.json "rejected": minutes calibration, 18 leg factors, gradient boosting, market spreads/totals, referees, lineup role changes, play-by-play rotations, player blowout minutes, trade effects, after-blowout, last-game form, national TV, opponent strength, tanking, travel, altitude, streaks, shooting luck, real main lines in building, line movement (early test), later ticket lock, per-stat blend weights, market distillation, situational blends, lifting legs with book prices.

## Questions nobody has answered yet
- Do live moneyline legs count the market twice? The game's win chance is already a model + market blend (pipeline/run.py, win_home_model / win_home_market), and parlay.team_legs blends it 50/50 again with the books' no-vig price. So the market's weight is about 75%, not 50%. Live record so far: 11 of 14 settled moneyline legs landed (18 of 490 live legs). Check once 100+ settle, from data/parlays: model-only vs market-only vs the double blend, log loss on the same legs. Feeding Pinnacle prices from backtest/run.py load_pinnacle into the replay slate would let the replay test it now (data work, then 2 replays).
- Why do tickets in the 2 weeks after the trade deadline land ~3% below stated in both seasons, when projections show no bias there?
- Is the Ladder edge real at Winamax's own prices, or only at US-book-derived prices? (needs payout-auditor records)
- Do our misses cluster by team (a coach we model badly)?
- Launch replays from a bash script (`bash run.sh`), not `env $VARS` in zsh: zsh does not split `$VARS`, so the books blend silently stays off. Check every log for `milestone blend on`.
