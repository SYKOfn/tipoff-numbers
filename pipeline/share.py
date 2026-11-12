"""Share previews: one small page and one 1200x630 picture per game ticket, so a ticket forwarded on WhatsApp,
Telegram or X shows up as the slip itself (title, chance, the five legs, the odds to place it at) instead of a
bare link. Pages live at site/t/<day>-<game>.html and send a visitor straight on to the site's Tickets page.

Written each run for the day's game tickets; a picture is redrawn only when its ticket changed (a result came
in). Days older than KEEP_DAYS are removed so the repository stays small.
"""
import hashlib
import html
import json
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "t"
ASSETS = Path(__file__).resolve().parent / "assets"
SITE = "https://sykofn.github.io/tipoff-numbers/"
KEEP_DAYS = 14
W, H = 1200, 630
INK, MUTED, FLOOR, CARD, EDGE = (244, 245, 247), (169, 173, 187), (9, 10, 14), (18, 20, 27), (38, 41, 52)
MINT, GOLD, CORAL = (61, 240, 165), (233, 201, 135), (255, 138, 122)
TEAM = {}  # abbreviation -> short name, filled from site/data/teams.json


def _font(name, size, weight):
    f = ImageFont.truetype(str(ASSETS / f"{name}.ttf"), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:  # an older FreeType without variable fonts: the default instance
        pass
    return f


def _short(ab):
    return TEAM.get(ab, ab)


def _title(t):
    a, _, b = str(t.get("name", "")).partition(" at ")
    return f"{_short(a)} at {_short(b)}" if b else t.get("name", "")


def _fit(draw, text, font, width):
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def draw(t, day):
    img = Image.new("RGB", (W, H), FLOOR)
    glow = Image.new("RGB", (W, H), FLOOR)
    g = ImageDraw.Draw(glow)
    g.ellipse((-200, -380, 700, 260), fill=(40, 30, 70))
    g.ellipse((700, -360, 1500, 240), fill=(14, 52, 40))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, W - 40, H - 40), radius=36, fill=CARD, outline=EDGE, width=2)
    serif, serif_big = _font("Fraunces", 54, b"SemiBold"), _font("Fraunces", 50, b"SemiBold")
    sans, sans_b, small = _font("Inter", 27, b"Medium"), _font("Inter", 27, b"SemiBold"), _font("Inter", 21, b"Medium")
    d.text((90, 84), _fit(d, _title(t), serif, 760), font=serif, fill=INK)
    when = date.fromisoformat(day).strftime("%A %-d %B")
    d.text((92, 156), f"{when} · {len(t['legs'])} legs priced together on 20,000 simulated games", font=small, fill=MUTED)
    # the ticket's chance as a ring
    cx, cy, r = W - 175, 150, 78
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(40, 44, 56), width=10)
    d.arc((cx - r, cy - r, cx + r, cy + r), start=-90, end=-90 + 360 * max(0.02, min(1.0, t["p"])), fill=MINT, width=10)
    pct = f"{round(t['p'] * 100)}%"
    d.text((cx, cy - 6), pct, font=serif_big, fill=INK, anchor="mm")
    d.text((cx, cy + 34), "CHANCE", font=_font("Inter", 15, b"SemiBold"), fill=MUTED, anchor="mm")
    # tear line
    for x in range(90, W - 90, 22):
        d.line((x, 222, x + 11, 222), fill=(48, 52, 64), width=2)
    # legs
    y = 248
    for l in t["legs"][:6]:
        res = l.get("result")
        col = MINT if res == "hit" else CORAL if res == "miss" else MUTED
        d.text((92, y), f"{round(l['p'] * 100)}%", font=sans_b, fill=col)
        mark = "  ✓" if res == "hit" else "  ✗" if res == "miss" else ""
        d.text((190, y), _fit(d, l["desc"], sans, 820) + mark, font=sans, fill=INK)
        y += 46
    # footer
    d.text((92, H - 124), "Place at", font=small, fill=MUTED)
    d.text((92, H - 100), f"{t.get('min_odds', 0):.2f}+", font=_font("Fraunces", 38, b"SemiBold"), fill=GOLD)
    d.text((290, H - 124), "Fair odds", font=small, fill=MUTED)
    d.text((290, H - 100), f"{t.get('fair', 0):.2f}", font=_font("Fraunces", 38, b"Regular"), fill=INK)
    d.text((W - 90, H - 116), "Tip-Off Numbers", font=_font("Fraunces", 30, b"SemiBold"), fill=INK, anchor="ra")
    d.text((W - 90, H - 78), "18+ · statistical estimates, not advice", font=_font("Inter", 17, b"Regular"), fill=MUTED, anchor="ra")
    if t.get("result") in ("hit", "miss"):
        st = "LANDED" if t["result"] == "hit" else "MISSED"
        col = MINT if t["result"] == "hit" else CORAL
        d.rounded_rectangle((W - 420, 62, W - 280, 104), radius=10, outline=col, width=3)
        d.text((W - 350, 83), st, font=_font("Inter", 20, b"Bold"), fill=col, anchor="mm")
    return img


def page(t, day, slug):
    title = f"{_title(t)}: {round(t['p'] * 100)}% ticket · Tip-Off Numbers"
    legs = "; ".join(l["desc"] for l in t["legs"])
    desc = f"{legs}. Worth placing at {t.get('min_odds', 0):.2f}+ (fair {t.get('fair', 0):.2f})."
    e = html.escape
    img = f"{SITE}t/{slug}.png"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Tip-Off Numbers">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:url" content="{SITE}t/{slug}.html"><meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{img}">
<link rel="canonical" href="{SITE}t/{slug}.html"><meta http-equiv="refresh" content="0; url=../#/parlay">
<style>body{{margin:0;background:#090A0E;color:#F4F5F7;font:16px system-ui,sans-serif;display:grid;place-items:center;min-height:100vh}}a{{color:#3DF0A5}}</style>
</head><body><p><a href="../#/parlay">Open tonight's tickets on Tip-Off Numbers</a></p>
<script>location.replace("../#/parlay")</script></body></html>
"""


def write(today, teams=None):
    """today: the day's parlay.json "today" block. Returns the number of tickets written."""
    if not today or not today.get("game_tickets") or not today.get("day") or today.get("locked") is False:
        return 0  # drafts change until the lock: only locked tickets get a share page
    for t in (teams or []):
        TEAM[t["abbr"]] = t.get("short") or t["abbr"]
    OUT.mkdir(parents=True, exist_ok=True)
    day, n = today["day"], 0
    for t in today["game_tickets"]:
        slug = f"{day}-{t.get('game')}"
        state = hashlib.md5(json.dumps([t["p"], t.get("result"), [(l["desc"], l.get("result")) for l in t["legs"]]]).encode()).hexdigest()[:10]
        png, htm = OUT / f"{slug}.png", OUT / f"{slug}.html"
        stamp = OUT / f"{slug}.state"
        if not png.exists() or not stamp.exists() or stamp.read_text() != state:
            draw(t, day).save(png, optimize=True)
            stamp.write_text(state)
        htm.write_text(page(t, day, slug))
        n += 1
    cutoff = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
    for f in OUT.iterdir():
        if f.name[:10] < cutoff:
            f.unlink()
    return n
