"""Did the morning news make minutes projections better? Compares, for every logged signal, the projected
minutes with and without the news against the minutes actually played.  python -m tools.news_check"""
import json
from collections import defaultdict
from pipeline.news import LOG
from pipeline.store import load_players


def main():
    if not LOG.exists():
        print("no news signals logged yet"); return
    rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    p = load_players()
    act = {(str(r.game_id), str(r.player_id)): float(r.min or 0) for r in p.itertuples()}
    by = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        a = act.get((r["game"], r["player"]))
        if a is None:
            continue
        for k in r["signals"]:
            by[k][0] += 1
            by[k][1] += abs((r["min_news"] or 0) - a)
            by[k][2] += abs((r["min_without"] or 0) - a)
    if not by:
        print(f"{len(rows)} signals logged, none settled yet"); return
    for k, (n, wn, wo) in sorted(by.items()):
        print(f"{k:10s} n {n:4d}  minutes miss with news {wn / n:5.2f}  without {wo / n:5.2f}  -> {'news helps' if wn < wo else 'news does not help'}")


if __name__ == "__main__":
    main()
