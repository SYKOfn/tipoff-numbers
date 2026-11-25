"""Posts for the X account (owner-approved formats, at most 16 a day, no betting). Runs at the end of each update.

Live only when X_POST_LIVE=1 and the four keys are set (GitHub secrets X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN,
X_ACCESS_SECRET); otherwise each post is written to data/state/x_drafts.jsonl instead. Formats:
  morning (1): tonight's games with each team's chance to win, after 10:00 ET;
  pregame (1 a game, within 90 minutes of tip): the win chance, projected score and 3 key projections;
  news (up to 4): a player projected 12+ points this morning is now out, and how his teammates moved;
  night (up to 3): the day's finals against the model's favourite, once every game is over.
"""
import base64, hashlib, hmac, json, os, time, urllib.parse, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .store import PRED, ROOT

ET = ZoneInfo("America/New_York")
STATE = ROOT / "data" / "state" / "x_posts.json"
DRAFTS = ROOT / "data" / "state" / "x_drafts.jsonl"
CAP, NEWS_CAP, NIGHT_CAP = 16, 4, 3
URL = "https://api.x.com/2/tweets"


def _q(s):
    return urllib.parse.quote(str(s), safe="~-._")


def _send(text):
    k = {n: os.environ.get(n, "") for n in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
    if os.environ.get("X_POST_LIVE") != "1" or not all(k.values()):
        with open(DRAFTS, "a") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "text": text}) + "\n")
        return True
    o = {"oauth_consumer_key": k["X_API_KEY"], "oauth_nonce": uuid.uuid4().hex, "oauth_signature_method": "HMAC-SHA1",
         "oauth_timestamp": str(int(time.time())), "oauth_token": k["X_ACCESS_TOKEN"], "oauth_version": "1.0"}
    base = "&".join(["POST", _q(URL), _q("&".join(f"{_q(a)}={_q(b)}" for a, b in sorted(o.items())))])
    key = f"{_q(k['X_API_SECRET'])}&{_q(k['X_ACCESS_SECRET'])}"
    o["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    auth = "OAuth " + ", ".join(f'{_q(a)}="{_q(b)}"' for a, b in sorted(o.items()))
    req = urllib.request.Request(URL, data=json.dumps({"text": text}).encode(), method="POST",
                                 headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 201)
    except Exception as e:  # never break the update
        print("x post failed:", getattr(e, "code", ""), str(e)[:120])
        return False


def _games(day, season):
    out = []
    for f in sorted((PRED / str(season)).glob("*.json")):
        d = json.loads(f.read_text())
        p = d.get("payload") or {}
        if p.get("day") == day:
            out.append((d, p))
    return sorted(out, key=lambda x: x[1].get("tip") or "")


def _fav(p):
    w = (p.get("est") or {}).get("win_home") or 0.5
    return (p["home"]["abbr"], w) if w >= 0.5 else (p["away"]["abbr"], 1 - w)


def _proj(p):
    return {x["name"]: x for s in ("home", "away") for x in (p.get("players") or {}).get(s, []) if not x.get("out")}


def run(now=None, season=None):
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(ET)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    day = et.date().isoformat()
    season = season or (et.year + 1 if et.month >= 9 else et.year)
    S = st.setdefault(day, {"n": 0, "keys": [], "snap": {}})

    def post(key, text, cap_key=None, cap=None):
        if key in S["keys"] or S["n"] >= CAP or len(text) > 280:
            return
        if cap_key and sum(k.startswith(cap_key) for k in S["keys"]) >= cap:
            return
        if _send(text):
            S["keys"].append(key)
            S["n"] += 1

    games = _games(day, season)
    if games and et.hour >= 10:
        lines = [f"{_fav(p)[0]} {round(_fav(p)[1] * 100)}% ({p['away']['abbr']} at {p['home']['abbr']})" for _, p in games]
        post("morning", "Tonight in the NBA, the model's favourite and its chance to win:\n" + "\n".join(lines) + "\n#NBA")
        if not S["snap"]:
            S["snap"] = {str(d["game_id"]): {n: x.get("pts") for n, x in _proj(p).items()} for d, p in games}
    for d, p in games:
        gid = str(d["game_id"])
        tip = datetime.fromisoformat((p.get("tip") or d["tip"]).replace("Z", "+00:00"))
        pl = list(_proj(p).values())
        if timedelta(0) < tip - now <= timedelta(minutes=90) and pl:
            t, w = _fav(p)
            e = p.get("est") or {}
            best, used = [], set()
            for s_ in ("pts", "reb", "ast"):  # three different players
                b = max((x for x in pl if x["name"] not in used), key=lambda x: x.get(s_) or 0)
                best.append(b); used.add(b["name"])
            key_ = ", ".join(f"{b['name']} {b.get(s, 0):.1f} {s}" for b, s in zip(best, ("pts", "reb", "ast")))
            post(f"pre:{gid}", f"{p['away']['short']} at {p['home']['short']}, {tip.astimezone(ET):%-I:%M %p} ET\n"
                 f"Model: {t} {round(w * 100)}% to win, projected {p['away']['abbr']} {e.get('away_pts', 0):.0f}-"
                 f"{e.get('home_pts', 0):.0f} {p['home']['abbr']}\nKey projections: {key_}\n#NBA")
        snap = S["snap"].get(gid) or {}
        now_p = _proj(p)
        for name, pts in snap.items():
            if (pts or 0) >= 12 and name not in now_p and tip > now:
                moved = sorted(((n, x.get("pts") or 0, snap.get(n) or 0) for n, x in now_p.items() if n in snap),
                               key=lambda r: r[2] - r[1])[:2]
                mv = "; ".join(f"{n} now {a:.1f} pts (was {b:.1f})" for n, a, b in moved if a - b >= 0.5)
                post(f"news:{gid}:{name}", f"{name} is out tonight ({p['away']['abbr']} at {p['home']['abbr']})."
                     + (f" Model update: {mv}." if mv else "") + " #NBA", "news:", NEWS_CAP)
    # night: the previous ET day's finals, once all are in
    y = (et.date() - timedelta(days=1)).isoformat()
    yg = _games(y, season)
    if yg and all(d.get("result") for d, _ in yg):
        rows, hits = [], 0
        for d, p in yg:
            r = d["result"]
            t, w = _fav(p)
            won = (r["home_pts"] > r["away_pts"]) == (t == p["home"]["abbr"])
            hits += won
            rows.append(f"{p['away']['abbr']} {r['away_pts']}-{r['home_pts']} {p['home']['abbr']} "
                        f"(model: {t} {round(w * 100)}%) {'✓' if won else '✗'}")
        chunks = [rows[i:i + 6] for i in range(0, len(rows), 6)][:NIGHT_CAP]
        for i, c in enumerate(chunks):
            head = f"Last night: the model's favourite won {hits} of {len(rows)}.\n" if i == 0 else ""
            post(f"night:{y}:{i}", head + "\n".join(c) + ("\n#NBA" if i == len(chunks) - 1 else ""), "night:", NIGHT_CAP)
    for k in [k for k in st if k < (et.date() - timedelta(days=3)).isoformat()]:
        st.pop(k)
    STATE.write_text(json.dumps(st))
