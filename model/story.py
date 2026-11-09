"""Why a ticket was chosen, in plain words about the matchup (no numbers).

Built from what the model already knows about each game: who is missing, rest and travel, form and
psychological spots, each player's role, his recent form, teammates out, the opponent's defence, the
pace of both teams. The numbers decide the picks; this explains them the way an analyst would.
"""
import re

STAT_WORD = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "threes", "pra": "points, rebounds and assists"}


def _no_digits(text):
    return not re.search(r"\d", text or "")


def _names(lst, k=2):
    n = [x for x in lst if x][:k]
    return " and ".join(n)


def _side_of(pay, team):
    return "home" if pay["home"]["abbr"] == team else "away"


def _other(side):
    return "away" if side == "home" else "home"


def _keys(pay, side):
    sd = (pay.get("sides") or {}).get(side) or {}
    return {s["key"]: s for layer in ("physical", "mind") for s in sd.get(layer, [])}


def _form_word(t):
    f = [x[0] for x in (t.get("form") or [])[:5]]
    if len(f) < 5:
        return None
    w = f.count("W")
    return "in good form" if w >= 4 else "struggling for results" if w <= 1 else None


def team_reasons(pay, side):
    """Things that favour this side, as short phrases."""
    me, op = pay[side], pay[_other(side)]
    k_me, k_op = _keys(pay, side), _keys(pay, _other(side))
    out = []
    a, b = me.get("net_rank") or 15, op.get("net_rank") or 15
    if a <= 8 and b >= 20:
        out.append(f"the {me['short']} are one of the better teams in the league and the {op['short']} one of the weaker ones")
    elif a + 8 <= b:
        out.append(f"the {me['short']} have been the clearly better team this season")
    miss = op.get("missing_list") or []
    if miss and (op.get("missing") or 0) >= 0.08:
        out.append(f"the {op['short']} are without {_names([m['name'] for m in miss])}")
    if op.get("b2b") and not me.get("b2b"):
        out.append(f"the {op['short']} played last night while the {me['short']} come in fresher")
    elif (me.get("rest") or 0) >= 2 and (op.get("rest") or 0) <= 1:
        out.append(f"the {me['short']} have had extra rest")
    if (op.get("km") or 0) >= 1500 and (me.get("km") or 0) < 500:
        out.append(f"the {op['short']} arrive after a long trip")
    if side == "home":
        out.append(f"the {me['short']} are at home")
    fw = _form_word(me)
    if fw == "in good form":
        out.append(f"the {me['short']} are in good form")
    fo = _form_word(op)
    if fo == "struggling for results":
        out.append(f"the {op['short']} are struggling for results")
    if "revenge" in k_me:
        out.append(f"the {me['short']} lost the last meeting and will want this one back")
    if "letdown" in k_op:
        out.append(f"the {op['short']} are coming off a big win and could ease off")
    if "lookahead" in k_op:
        out.append(f"the {op['short']} have a bigger game coming up next")
    if "stakes" in k_me and (me.get("stakes") or 0) > 0:
        out.append(f"the {me['short']} are in a race for a playoff place")
    return out


def _analyst(pay):
    t = ((pay.get("analyst") or {}).get("text") or "").strip()
    if not t:
        return None
    first = re.split(r"(?<=[.!?])\s", t)[0]
    return first if _no_digits(first) else None


def _player(pay, pid):
    for side in ("home", "away"):
        for x in (pay.get("players") or {}).get(side, []):
            if str(x.get("id")) == str(pid):
                return side, x
    return None, None


def leg_story(leg, pay):
    kind = leg.get("kind")
    if kind in ("ml", "spread") and leg.get("team"):
        side = _side_of(pay, leg["team"])
        me, op = pay[side], pay[_other(side)]
        rs = team_reasons(pay, side)
        head = (f"{me['short']} to win" if kind == "ml" else
                f"{me['short']} to cover" if (leg.get("line") or 0) < 0 else f"{me['short']} to stay close or win")
        why = "; ".join(rs[:3]) if rs else f"the model rates the {me['short']} as the better side in this matchup"
        txt = f"{head}: {why}."
        if kind == "spread" and (leg.get("line") or 0) < 0:
            txt += f" The gap between the two rosters is wide enough to expect more than a narrow win."
        return txt[0].upper() + txt[1:]
    if kind in ("total", "team_total"):
        over = (leg.get("side") or "").lower() == "over"
        h, a = pay["home"], pay["away"]
        st = pay.get("style") or {}
        paces = [(pay[s]["short"], (st.get(s) or {}).get("pace")) for s in ("home", "away")]
        bits = []
        fast = [n for n, p in paces if p == "fast"]
        slow = [n for n, p in paces if p == "slow"]
        if over and fast:
            bits.append(f"the {' and the '.join(fast)} like to play fast")
        if not over and slow:
            bits.append(f"the {' and the '.join(slow)} like to slow the game down")
        for t in (h, a):
            miss = t.get("missing_list") or []
            if miss and (t.get("missing") or 0) >= 0.08:
                bits.append(f"the {t['short']} are without {_names([m['name'] for m in miss])}" +
                            (", which takes scoring out of their offence" if not over else
                             ", so they defend with a thinner, weaker rotation"))
        if not over and (h.get("b2b") or a.get("b2b")):
            bits.append("tired legs on a back-to-back tend to mean flatter offence")
        if pay.get("refs") and not bits:
            bits.append("the matchup and the officiating crew point the same way")
        why = "; ".join(bits[:3]) if bits else ("both offences match up well against these defences" if over
                                               else "both defences should control the tempo")
        return f"{'Over' if over else 'Under'} on the total: {why}."
    if kind == "prop":
        side, x = _player(pay, leg.get("player"))
        name = leg.get("player_name") or (x or {}).get("name") or "He"
        stw = STAT_WORD.get(leg.get("stat"), "his numbers")
        if x is None:
            return f"{name} over on {stw}: the projection sits clearly above the line."
        opp = pay[_other(side)]["short"]
        keys = {s["key"]: s for s in (x.get("spots") or [])}
        bits = []
        if x.get("without_names"):
            bits.append(f"with {_names(x['without_names'])} out, more of the offence runs through him")
        if x.get("lineup") == "starting" or x.get("started"):
            bits.append("he is in the starting group and plays heavy minutes")
        if "hot" in keys and "Hot" in (keys["hot"].get("label") or ""):
            bits.append("he has been in good form lately")
        if x.get("matchup") == "soft":
            bits.append(f"the {opp} have given up a lot in this area")
        if "vs_opp" in keys:
            bits.append(f"he has tended to play well against the {opp}")
        if "former_team" in keys:
            bits.append(f"he faces his former team")
        if "returning" in keys:
            bits.append("he is settling back in after his absence")
        if abs((pay.get("est") or {}).get("margin") or 0) < 6:
            bits.append("a close game should keep the starters on the floor late")
        why = "; ".join(bits[:3]) if bits else "his role and the matchup point to a solid night"
        return f"{name} over on {stw}: {why}."
    return None


def _theme(leg, pays):
    pay = pays.get(str(leg.get("game")))
    if not pay:
        return None
    kind = leg.get("kind")
    if kind in ("ml", "spread") and leg.get("team"):
        side = _side_of(pay, leg["team"])
        me, op = pay[side], pay[_other(side)]
        miss = op.get("missing_list") or []
        if miss and (op.get("missing") or 0) >= 0.08:
            return f"the {me['short']} against a {op['short']} side without {_names([m['name'] for m in miss])}"
        if op.get("b2b") and not me.get("b2b"):
            return f"fresh {me['short']} legs against a tired {op['short']} team"
        return f"the {me['short']}'s edge in quality over the {op['short']}"
    if kind in ("total", "team_total"):
        over = (leg.get("side") or "").lower() == "over"
        return f"{'a high-scoring' if over else 'a low-scoring'} game between the {pay['away']['short']} and the {pay['home']['short']}"
    if kind == "prop":
        side, x = _player(pay, leg.get("player"))
        name = leg.get("player_name") or "a player"
        if x and x.get("without_names"):
            return f"{name} taking on a bigger role with {_names(x['without_names'], 1)} out"
        if x and x.get("matchup") == "soft":
            return f"{name} against a defence that gives up plenty"
        return f"{name}'s steady role"
    return None


def ticket_story(pr, pays):
    legs = pr.get("legs") or []
    games = {l["game"] for l in legs}
    themes, step_up = [], {}
    for l in legs:
        pay = pays.get(str(l.get("game")))
        if l.get("kind") == "prop" and pay:
            _, x = _player(pay, l.get("player"))
            if x and x.get("without_names"):
                key = x["without_names"][0]
                if key not in step_up:
                    step_up[key] = []
                    themes.append(("STEP", key))
                if l.get("player_name") not in step_up[key]:
                    step_up[key].append(l.get("player_name"))
                continue
        t = _theme(l, pays)
        if t and t not in themes:
            themes.append(t)
    def _fmt(t):
        if isinstance(t, tuple):
            ns = step_up[t[1]]
            who = ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]
            return f"{who} picking up the slack with {t[1]} out"
        return t
    themes = [_fmt(t) for t in themes]
    txt = ""
    if themes:
        body = themes[0] if len(themes) == 1 else ", ".join(themes[:-1]) + " and " + themes[-1]
        txt = f"Built around {body}."
    if len(games) == len(legs) and len(legs) > 1:
        txt += " Every leg comes from a different game, so one surprise result cannot sink two legs at once."
    elif len(games) == 1 and len(legs) > 1:
        txt += " The legs come from one game and tell the same story, so they tend to land together."
    analyst = [a for a in (_analyst(pays.get(g)) for g in games if pays.get(g)) if a]
    if analyst:
        txt += " " + analyst[0]
    txt = txt.strip()
    return txt if _no_digits(txt) else " ".join(x for x in re.split(r"(?<=[.!?])\s", txt) if _no_digits(x))


def annotate(tickets, singles, slate):
    """Adds 'story' to every ticket and leg. slate: [(game, payload)]."""
    pays = {str(p["id"]): p for _, p in slate}
    for pr in tickets:
        for l in pr.get("legs") or []:
            p = pays.get(str(l.get("game")))
            s = leg_story(l, p) if p else None
            l["story"] = s if s and _no_digits(s) else None
        pr["story"] = ticket_story(pr, pays)
    for l in singles or []:
        p = pays.get(str(l.get("game")))
        s = leg_story(l, p) if p else None
        l["story"] = s if s and _no_digits(s) else None
