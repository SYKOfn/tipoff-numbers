"""Paired comparison of two multi-season replays (backtest/multi.sh): per season and pooled.

    python -m backtest.multi_report BASE_TAG CAND_TAG [SEASONS...]

Tickets are paired by game: a flip is a game whose ticket landed in one run and missed in the other. The pooled sign
test asks whether the flips up outnumber the flips down by more than luck would (two-sided binomial, p = 0.5).
"""
import json
import math
import sys
from pathlib import Path

DIRS = [Path("/tmp"), Path.home() / ".cache" / "tipoff_replays"]
SEASONS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027]


def _load(kind, season, tag):
    for d in DIRS:
        f = d / f"{kind}_{season}{tag}.json"
        if f.exists():
            return json.load(open(f))
    return None


def sign_p(up, down):
    n, k = up + down, max(up, down)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n) if n else 1.0


def summary(T, L):
    legs = [d for t in T for d in t["detail"] if d["res"] in ("hit", "miss")]
    out = {"t": sum(t["hit"] for t in T), "n": len(T), "ts": sum(t["p"] for t in T),
           "l": sum(d["res"] == "hit" for d in legs), "ln": len(legs), "ls": sum(d["p"] for d in legs)}
    pk = [x for _, x in (L or []) if x and x.get("result") in ("hit", "miss")]
    out.update(lw=sum(x["result"] == "hit" for x in pk), lb=len(pk), lst=sum(x["p"] for x in pk),
               lp=sum((x["odds"] - 1) if x["result"] == "hit" else -1 for x in pk))
    return out


def main(base, cand, seasons):
    tu = td = 0
    for s in seasons:
        A, B = _load("tickets", s, base), _load("tickets", s, cand)
        if not A or not B:
            print(f"{s}: missing run ({'base' if not A else 'candidate'})")
            continue
        A, B = A["base"], B["base"]
        a, b = summary(A, _load("ladder", s, base)), summary(B, _load("ladder", s, cand))
        ga, gb = {t["game"]: t["hit"] for t in A}, {t["game"]: t["hit"] for t in B}
        both = set(ga) & set(gb)
        up, dn = sum(gb[g] and not ga[g] for g in both), sum(ga[g] and not gb[g] for g in both)
        tu, td = tu + up, td + dn
        f = lambda x: (f"tickets {x['t']}/{x['n']} ({x['ts']:.1f}) legs {x['l']}/{x['ln']} ({x['ls']:.1f}) "
                       f"ladder {x['lw']}/{x['lb']} ({x['lst']:.1f}, {x['lp']:+.1f}u)")
        print(f"{s - 1}-{str(s)[2:]}: base {f(a)} | cand {f(b)} | flips +{up} -{dn} (p {sign_p(up, dn):.2f})")
    print(f"pooled flips: +{tu} -{td}, net {tu - td:+d}, two-sided sign test p = {sign_p(tu, td):.3f}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], [int(x) for x in a[2:]] or SEASONS)
