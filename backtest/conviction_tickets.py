"""Conviction levels on 3-leg game tickets (research/backlog.md item 9, pre-registered rule). No replay: scores the
_n3 files in ~/.cache/tipoff_replays. T3 bands fitted on 2018-19..2022-23, judged on 2023-24..2026-27.
  python backtest/conviction_tickets.py [strict]"""
import json, math, collections, os, sys
D = os.path.expanduser("~/.cache/tipoff_replays")
STRICT = len(sys.argv) > 1 and sys.argv[1] == "strict"   # "Available" counted as listed (fails T1)
FIT, JUDGE = range(2019, 2024), range(2024, 2028)
def load(s):
    x = json.load(open(f"{D}/xtickets_{s}_n3.json"))["g5"]
    det = {t["game"]: t for t in json.load(open(f"{D}/tickets_{s}_n3.json"))["base"]}
    out = []
    for a in x:
        t = det[a["legs"][0][3]]
        assert abs(t["p"] - a["p"]) < 1e-9 and t["hit"] == a["hit"]
        out.append((a, t))
    return out
band = lambda p: int(math.floor(p / 0.05 + 1e-9))
cell = collections.defaultdict(lambda: [0, 0.0])
for s in FIT:
    for a, t in load(s):
        for d in t["detail"]:
            if d["res"] == "void":
                continue
            c = cell[(d["kind"], band(d["p"]))]
            c[0] += d["res"] == "hit"; c[1] += d["p"]
good = {k for k, (h, st) in cell.items() if h >= st}
print("T3 cells passing:", sorted(good), " failing:", sorted(set(cell) - good))
ok_st = (None, "Probable") if STRICT else (None, "Probable", "Available")
def level(t):
    t1 = all(d.get("lk_st") in ok_st and "lk_st" in d and (d.get("pmin") or 0) >= 24 for d in t["detail"] if d["kind"] == "prop")
    t2 = t.get("m_exp") is not None and abs(t["m_exp"]) <= 8
    t3 = all((d["kind"], band(d["p"])) in good for d in t["detail"])
    n = t1 + t2 + t3
    return "H" if n == 3 else "M" if n == 2 else "L", (t1, t2, t3)
pool = {k: [] for k in "HML"}
for s in list(FIT) + list(JUDGE):
    rows = collections.defaultdict(list); tests = collections.Counter()
    for a, t in load(s):
        lv, ts = level(t); rows[lv].append((a["hit"], a["p"])); tests[ts] += 1
        if s in JUDGE: pool[lv].append((a["hit"], a["p"]))
    n_all = sum(len(v) for v in rows.values())
    line = [f"{s}{'*' if s in JUDGE else ' '}"]
    for k in "HML":
        v = rows[k]; h = sum(x for x, _ in v); st = sum(p for _, p in v)
        line.append(f"{k} {len(v)} {h}/{st:.1f} r={h/st if st else float('nan'):.3f}")
    line.append(f"Hshare {len(rows['H'])/n_all:.3f}")
    print("  ".join(line))
def stats(v):
    r = [h - p for h, p in v]; n = len(r); m = sum(r) / n
    var = sum((x - m) ** 2 for x in r) / (n - 1)
    return n, m, var
for k in "HML":
    v = pool[k]; print("pooled", k, len(v), sum(h for h, _ in v), round(sum(p for _, p in v), 1), round(sum(h for h, _ in v) / sum(p for _, p in v), 3))
nh, mh, vh = stats(pool["H"]); nl, ml, vl = stats(pool["L"])
print("z H vs L:", round((mh - ml) / math.sqrt(vh / nh + vl / nl), 2), "per-ticket", round(mh, 4), round(ml, 4))
