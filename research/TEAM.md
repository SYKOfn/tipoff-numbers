# The team

Sixteen agents, organised like a small betting syndicate. Each is a role prompt in `.claude/agents/`; they run only when started (by the owner or the main session), and each run costs usage, so the research-director decides who works next.

| Desk | Agent | Job |
|------|-------|-----|
| Head of research | research-director | Owns `research/backlog.md`, ranks ideas, briefs the builders, always asks what's next (with a mechanism) |
| Validation | skeptic | Must say "ship" before any change goes live: noise, leaks, overfitting, live/replay parity |
| Quant research | model-researcher | Builds one idea, replays both seasons (leak-free), reports flips |
| Mathematics | probability-modeler | Stat distributions, dependence between legs, blend and calibration formulas |
| Coaching and minutes | rotation-analyst | How coaches hand out minutes; the biggest source of error |
| Psychology | behavioral-analyst | Player and coach motivation (with mechanisms); the owner's betting discipline |
| Basketball | basketball-scout | Human-style read of the day's picks before the locks; logs verdicts |
| Trading | market-trader | Prices, timing, closing-line value, where Winamax is soft |
| Risk | risk-analyst | Variance, losing runs, Ladder completion odds, luck vs broken model |
| Pricing | payout-auditor | Real Winamax odds and payouts vs the model's assumptions |
| Data | data-scout | Finds and tests free data sources |
| Research library | literature-scout | Papers and public work turned into testable ideas |
| Performance review | results-reviewer | Weekly: what landed, what missed, why |
| Software | code-auditor | Bugs, leaks, live vs replay differences, tests |
| Operations | pipeline-doctor | Fixes failed data updates |
| Front end | site-qa | Checks the site after design changes |

## How work flows
ideas (literature-scout, data-scout, rotation-analyst, behavioral-analyst, market-trader, probability-modeler, results-reviewer, basketball-scout)
→ research-director (ranks, cheap check, brief)
→ model-researcher (build, leak-free replay)
→ code-auditor (live and replay compute it the same way?) and skeptic (is it real?)
→ owner's OK → live.

## Rules every agent follows
- Only more tickets landing at honest stated chances on the leak-free replay counts; better projections alone do not.
- A new idea needs a mechanism and outside evidence, not a data slice.
- Never retest a rejected idea without new data.
- Never push `.github/workflows`; never commit private bet files.
