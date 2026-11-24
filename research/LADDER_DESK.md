# The Ladder desk (daily, before the Ladder locks)

The owner's rule (Nov 2026): the Ladder is a challenge, like climbing stairs. Each day the team works to choose the best
single bet, then that bet becomes the day's step. One bet a day, Winamax 2.00-2.10, always a bet.

The model's own pick stays visible and is scored as `ladder_model`, so after a few weeks we know whether the desk beats
the model it overrules. This is the honest test of the desk; no replay can measure live news.

## Timing
- The Ladder locks at `ladder_lock_at` in `data/parlays/{day}.json` (6 hours before the first tip, usually 19:00 Madrid).
  The site updates every 15 minutes, so the choice must be pushed at least 30 minutes before the lock.
- If `ladder_locked` is already true, or there are no games, stop and only do the review of yesterday (step 6).

## Steps
1. `git pull -q`. Read today's `data/parlays/{day}.json` (`day` = the newest file): `ladder` (the model's pick),
   `ladder_options` (the shortlist: odds, chance `p`, the sharp market's chance `market`, value = p x odds, conviction
   tests L1-L4), `ladder_lock_at`. Player context: `data/predictions/2027/{game}.json`.
2. Send three desks in parallel, each on the top 5 options in the 2.00-2.10 window (priced options first):
   - **rotation-analyst**: minutes risk for each option. Injury report, minutes limits, returns from absence,
     blowout risk, back-to-backs.
   - **basketball-scout**: today's news and the basketball case for each option, with a verdict of Back, Neutral or Doubt
     and a source for every claim. The scout logs to `data/scout_notes.jsonl` as usual.
   - **market-trader**: the price on each option. Is Winamax's price real or estimated? How does it compare with
     Pinnacle's no-margin chance? Has the line moved since the morning, and which way?
3. Choose with the owner's rules, in this order:
   1. inside 2.00-2.10 when any option is priced there. Never an estimated price when a real one exists;
   2. no option a desk Doubts with a sourced, concrete reason, such as an injury, a minutes cap or a lineup change;
   3. the highest chance the team believes after the news. Keep the model's pick unless a desk has a sourced reason
      to change it. A hunch is not a reason;
   4. tie-break: better value (p x odds), then a real Winamax price.
4. Ask the **skeptic** to argue against the chosen bet in one paragraph. If it finds a concrete flaw, take the next
   option and say why.
5. Write `data/overrides/ladder.json`:
   `{"day": "<day>", "id": "<option id>", "desc": "...", "reason": "<one or two plain sentences for the owner: why this
   bet, and the news behind it>", "voices": {"rotation": "...", "scout": "...", "market": "...", "skeptic": "..."},
   "chosen_at": "<ISO time>"}`.
   Also append the same record, plus the model's pick id, to `data/state/ladder_desk.jsonl`. Commit those two files only
   and push. Never `.github/workflows`.
   After the next site update (about 15 minutes), check that `ladder.team` is set in the day's file. If it is not, the id
   was not among today's options: fix the id and push again before the lock.
6. Review yesterday: how the team's pick and the model's pick (`ladder_model`) each did, from the settled
   `data/parlays/{yesterday}.json`. Keep a running count in the last line of the report: team hits/bets and model
   hits/bets since the desk started.

## Rules
- The desk chooses a bet; it never changes the model, the stated chance, the tickets or the lock time.
- Statistical estimates, not promises. The Ladder has no proven edge at real prices (research/backlog.md), so the
  desk's job is to avoid the avoidable misses: news, minutes and stale prices.
- After 60 desk days, the results-reviewer compares team and model. If the team is not ahead, the owner decides
  whether the desk continues.

## Report to the owner (under 8 lines)
Today's bet, its odds and chance, and why. What the desk changed versus the model, if anything. Yesterday's result
for both picks, and the running count.
