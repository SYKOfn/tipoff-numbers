"""Plain-language reasoning: what each factor means for this game and what history says it is worth."""
from pipeline.teams import TEAMS

EV_WORD = {"strong": "strong evidence", "moderate": "moderate evidence", "weak": "weak evidence", "none": "no clear evidence"}


def short(ab):
    return TEAMS[ab][2]


def spot_text(key, f, team, opp):
    """One sentence describing a team's situation for a factor, or None if it does not apply."""
    t, o = short(team), short(opp)
    if key == "b2b" and f["b2b"]:
        return f"{t} played last night."
    if key == "three_in_four" and f["three_in_four"]:
        return f"{t} play their third game in four nights."
    if key == "rest" and f["rest"] >= 2 and not f["b2b"]:
        return f"{t} have had {min(f['rest'], 9)} days off."
    if key == "tz_east" and f["tz_east"] > 0:
        return f"{t} cross {f['tz_east']} time zone{'s' if f['tz_east'] > 1 else ''} heading east."
    if key == "travel" and f["km"] >= 1500:
        return f"{t} travelled about {f['km']:,} km since their last game."
    if key == "luck" and abs(f.get("luck", 0.0)) >= 3:
        return (f"{t} have been {'lucky' if f['luck'] > 0 else 'unlucky'} from three lately: about "
                f"{abs(f['luck']):.1f} points a game {'above' if f['luck'] > 0 else 'below'} league-average shooting (theirs and their opponents').")
    if key == "missing" and f["missing"] > 0.04:
        names = ", ".join(x["name"] for x in f["missing_list"][:3])
        return f"{t} are without about {round(f['missing'] * 100)}% of their regular production ({names})."
    if key == "streak" and abs(f["streak"]) >= 3:
        return f"{t} have {'won' if f['streak'] > 0 else 'lost'} {abs(f['streak'])} straight."
    if key == "confidence" and abs(f["confidence"]) >= 4:
        return (f"{t} have {'beaten' if f['confidence'] > 0 else 'fallen short of'} expectations by "
                f"{abs(f['confidence']):.1f} points a game over their last five.")
    if key == "bounce" and f["bounce"]:
        return f"{t} lost by {abs(f['last_margin'])} to the {short(f['last_opp'])} last time out."
    if key == "letdown" and f["letdown"]:
        return f"{t} are coming off a win over the {short(f['last_opp'])}, a top team, and now face a weaker side."
    if key == "revenge" and f["revenge"]:
        return f"{t} lost the last meeting with the {o} by {f['revenge_margin']}."
    if key == "lookahead" and f["lookahead"]:
        return f"{t} face the {short(f['lookahead_opp'])}, a top team, next."
    if key == "homecoming" and f["homecoming"]:
        return f"{t} are home after a long road trip."
    if key == "road_long" and f["road_long"]:
        return f"Road game number {f['road_game_no']} in a row for the {t}."
    if key == "stakes" and f["stakes"]:
        return f"{t}: {f['stakes_why']}." if f.get("stakes_why") else None
    if key == "elimination" and f["elimination"]:
        return f"{t} trail {f.get('series', '')} and face elimination."
    return None


def sides(est, ctx, home, away, eff_table):
    """Per team, per layer: the factors that apply, with their effect here and their track record."""
    ev = {r["key"]: r for r in eff_table if r["target"] == "margin"}
    out = {"home": {"physical": [], "mind": []}, "away": {"physical": [], "mind": []}}
    for p in est["parts"]:
        if p["target"] != "margin":
            continue
        for side, team, opp in (("home", home, away), ("away", away, home)):
            f = ctx[side]
            txt = spot_text(p["key"], f, team, opp)
            pts = p[f"{side}_pts"]
            if txt is None:
                continue
            e = ev.get(p["key"], {})
            out[side][p["layer"]].append({
                "key": p["key"], "label": p["label"], "text": txt, "pts": round(pts, 2),
                "per": e.get("pts"), "means": e.get("means"), "evidence": e.get("evidence", "none"), "n": e.get("n", 0),
            })
    for side in out:
        for layer in out[side]:
            out[side][layer].sort(key=lambda x: -abs(x["pts"]))
    return out


def gauge(side_list):
    return round(sum(x["pts"] for x in side_list), 2)


def reasoning(est, ctx, home, away, sd, rts_net=None):
    """Short bullets: base, physical, mind, bottom line."""
    H, A = short(home), short(away)
    b = est["base"]
    fav, dog = (H, A) if b["margin"] >= 0 else (A, H)
    lines = []
    if rts_net:
        nh, na = rts_net
        lines.append(f"Base ratings: the {H} are {nh:+.1f} and the {A} {na:+.1f} points per game against an average team; "
                     f"with home court that makes the {fav} {abs(b['margin']):.1f} better here, total {b['total']:.0f}.")
    else:
        lines.append(f"Base ratings make the {fav} {abs(b['margin']):.1f} points better here, total {b['total']:.0f}.")
    pm, mm = est["physical"]["margin"], est["mind"]["margin"]
    if abs(pm) >= 0.3:
        lines.append(f"Rest, travel and availability move it {abs(pm):.1f} towards the {H if pm > 0 else A}.")
    else:
        lines.append("Rest, travel and availability barely move it.")
    phome, paway = sd["home"]["mind"], sd["away"]["mind"]
    if abs(mm) >= 0.3:
        lead = H if mm > 0 else A
        why = [x["label"].lower() for x in (phome if mm > 0 else paway) if abs(x["pts"]) >= 0.2][:2]
        lines.append(f"The psychological spots lean {abs(mm):.1f} towards the {lead}"
                     + (f" ({', '.join(why)})." if why else "."))
    elif phome or paway:
        lines.append("There are psychological storylines, but history says they are worth little here.")
    else:
        lines.append("No psychological spot stands out for either team.")
    m = est["margin"]
    w = est["win_home"]
    lines.append(f"Bottom line: {H if m >= 0 else A} by {abs(m):.1f}, {round(max(w, 1 - w) * 100)}% to win; "
                 f"total {est['total']:.0f} (80% range {est['total'] - 1.28 * est['sd_total']:.0f}-{est['total'] + 1.28 * est['sd_total']:.0f}).")
    return lines
