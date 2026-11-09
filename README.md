# Tip-Off Numbers

Statistical estimates for every NBA game in the next two weeks — win chances, margin, total points, threes, rebounds and assists — with a **measured psychological layer** and a public track record. An information tool, not betting advice: every estimate shows its inputs, its uncertainty and how it has done.

Built on the same idea as [Matchday Numbers](https://matchday-numbers.github.io/) (football), adapted to basketball.

## Put it online (GitHub Pages, free)

1. Create a new **public** GitHub repository and push this folder to its `main` branch.
2. **Settings → Pages → Source: "GitHub Actions".**
3. **Settings → Actions → General → Workflow permissions: "Read and write".**
4. **Actions → update → Run workflow.** The first run backfills three seasons from ESPN and tunes the model (≈ 10–20 min). Box scores fill in over the next few runs (700 per run).

After that it updates itself every 3 hours. The site is at `https://<user>.github.io/<repo>/`.

Preview without network: `python -m pipeline.run --demo` (simulated league, clearly labelled on every page), then serve `site/` (`python -m http.server -d site`).

## Real prices (optional, recommended)

1. Create a free key at https://the-odds-api.com (500 credits/month).
2. GitHub repo -> Settings -> Secrets and variables -> Actions -> **New repository secret**: `ODDS_API_KEY` = your key.
3. Optional **variables** (same page, Variables tab): `ODDS_API_BOOKS` (default `winamax_fr,pinnacle`), `ODDS_API_DAILY` (credits per day, default 15 = free plan), `ODDS_API_PROPS` = `1` to archive player-prop lines (about 10 credits per game per day: needs the $30 plan).

Without a key everything still works, with ESPN's US prices.

## How it runs

`.github/workflows/update.yml`, every 3 hours:

1. **Collect** (`pipeline/collect.py`) from ESPN's public feed: results and schedule (3 full seasons + current), box scores and player minutes (this season and last), the league injury report.
2. **Rebuild** (`model/engine.py`): out-of-sample base prediction for every past game (refit weekly on earlier games), the situation before every game (`model/features.py`), and the size of each factor (`model/effects.py`).
3. **Predict** every game in the next 14 days. An estimate is rewritten each run until tip-off, then **frozen** in `data/predictions/` (git history proves it existed before tip-off) and scored after the game.
4. **Write** the website data (`site/data/`) and publish `site/`.

`backtest.yml` re-tunes monthly: tune on season N-2, test once on season N-1, walk-forward by week.

## Model

**estimate = base ratings + physical adjustments + psychological adjustments**

- **Base** (`model/ratings.py`): per stat, `points for = avg + home edge + attack[team] − defence[opponent]`, ridge-penalised, time-weighted (half-life tuned), last season's games discounted again (`carry`).
- **Physical**: back-to-back, 3-in-4 nights, rest days, time zones crossed eastward, travel km, missing players (each rotation regular's share of production; past games = who didn't play, upcoming = ESPN injury report weighted by status).
- **Psychological**: streak, confidence (last 5 vs expectation), bounce-back after a 20+ loss, letdown after beating a top team, revenge (lost the last meeting / previous series game), look-ahead (top team within two days), homecoming, long road trip, stakes (late-season seed race vs nothing to play for), facing elimination. On the total: division rivalry, playoff intensity, dead-rubber games.
- **Sizes are measured, not assumed**: one ridge regression of what the base missed on all factors at once; each factor gets points, a standard error and an evidence label. Stories history doesn't support shrink towards zero.
- **Chances**: normal distribution around the margin/total with the spread of past misses.
- **Honesty**: track record against plain averages and against the same model *without* the psychological layer.

`data/overrides/analyst.json` adds an optional written view per game (news, locker room…), shown but never mixed into the numbers.

## Layout

```
pipeline/   ESPN feed, collector, demo league, run (site data)
model/      ratings, context tracker, effects, engine, explanations
backtest/   tuning + test
data/       history CSVs, state, frozen predictions, overrides
site/       static website (index.html, app.js, styles.css, data/)
tests/      python -m pytest -q
```
