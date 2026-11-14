"""Check every main page of the site in a real browser, at desktop and phone size.

    python -m tools.site_check                 report problems (script errors, sideways scrolling, text under 11px,
                                               accessibility issues from axe) and compare the layout to the baseline
    python -m tools.site_check --baseline      save the current layout as the baseline (after a change you approve)
    python -m tools.site_check --ci            CI mode: bundled Chromium, exit 1 on script errors, sideways scrolling
                                               or serious accessibility issues

Screenshots go to /tmp/site_check/. The layout baseline (every element's box and main styles) is what makes a CSS
clean-up safe: zero differences means nothing on screen moved.
"""
import json
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = Path("/tmp/site_check")
BASE = OUT / "baseline.json"
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js"
SIZES = {"desktop": dict(viewport={"width": 1280, "height": 900}),
         "phone": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)}
QUIET = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}.reveal{opacity:1!important;transform:none!important}"

FINGERPRINT = """() => {
  const out = [], keys = ["color", "backgroundColor", "fontSize", "fontWeight", "fontFamily", "display", "borderRadius", "position"];
  const path = e => { const p = []; for (let x = e; x && x !== document.body; x = x.parentElement) p.unshift(x.tagName.toLowerCase() + (x.classList.length ? "." + [...x.classList].filter(c => c !== "lit").join(".") : "")); return p.join(">"); };
  document.querySelectorAll("header *, #app *").forEach(e => {
    const r = e.getBoundingClientRect(); if (!r.width && !r.height) return;
    const cs = getComputedStyle(e);
    out.push([path(e), Math.round(r.x), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height), ...keys.map(k => k === "fontFamily" ? cs[k].split(",")[0] : cs[k])]);
  });
  return out;
}"""
PROBLEMS = """() => {
  const W = innerWidth, res = { overflow: [], tiny: [] };
  if (document.documentElement.scrollWidth > W + 1)
    document.querySelectorAll("body *").forEach(e => {
      const r = e.getBoundingClientRect();
      if (r.right > W + 1 && r.width && !e.closest(".tscroll, .segs, .nav, [style*=overflow]") && getComputedStyle(e).position !== "fixed")
        res.overflow.push((e.className && String(e.className).slice(0, 40)) || e.tagName);
    });
  document.querySelectorAll("#app *, header *").forEach(e => {
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own || !e.getClientRects().length) return;
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 11 && fs > 0 && !e.closest("svg")) res.tiny.push(`${e.tagName.toLowerCase()}.${[...e.classList].join(".")} ${fs}px "${e.textContent.trim().slice(0, 24)}"`);
  });
  res.overflow = [...new Set(res.overflow)].slice(0, 8);
  res.tiny = [...new Set(res.tiny)];
  return res;
}"""


def pages():
    sched = json.loads((SITE / "data" / "schedule.json").read_text())
    gid = (sched.get("upcoming") or sched.get("recent") or [{}])[0].get("id")
    pl = sorted(p.stem for p in (SITE / "data" / "player").glob("*.json"))
    out = ["#/", "#/parlay", "#/games", "#/players", "#/mind", "#/standings", "#/teams", "#/team/BOS", "#/accuracy", "#/results", "#/you", "#/about"]
    if gid:
        out.append(f"#/game/{gid}")
    if pl:
        out.append(f"#/player/{pl[0]}")
    return out


def serve():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(QuietHandler, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def keyboard(page, url):
    """Keyboard-only use of the header: skip link, "/" search with arrows and Enter, Escape on the menu,
    page announcements, plus an accessibility scan with the search results and the menu open."""
    out = []
    def check(ok, what):
        if not ok:
            out.append(what)
    page.goto(url + "#/")
    page.reload()  # a fresh load: changing only the hash keeps the old page's state
    page.wait_for_function("() => document.querySelector('#app h1')")
    page.add_style_tag(content=QUIET)  # animations off, so contrast is measured on the settled page
    page.keyboard.press("Tab")
    check(page.evaluate("document.activeElement.textContent.trim()") == "Skip to content", "Tab does not reach the skip link first")
    page.keyboard.press("Enter")
    check(page.evaluate("document.activeElement.id") == "app", "skip link does not move focus to the content")
    page.keyboard.press("/")
    check(page.evaluate("document.activeElement.id") == "hq", '"/" does not focus the search')
    page.keyboard.type("standings")
    page.wait_for_selector("#hq-list [role=option]")
    check(page.get_attribute("#hq", "aria-expanded") == "true", "search does not report its results as expanded")
    check(bool(page.get_attribute("#hq", "aria-activedescendant")), "no active search result for screen readers")
    page.evaluate("document.getElementById('app').classList.remove('entering','leaving')")
    try:
        page.add_script_tag(url=AXE)
        res = page.evaluate("() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] })")
        check(not [v for v in res["violations"] if v["impact"] in ("serious", "critical")], "accessibility problems with search results open: "
              + ", ".join(v["id"] for v in res["violations"]))
    except Exception:
        pass
    page.keyboard.press("Enter")
    page.wait_for_function("() => location.hash === '#/standings' && document.querySelector('#app h1')")
    try:
        page.wait_for_function("() => { const h = document.querySelector('#app h1'); return h && document.getElementById('announce').textContent.includes(h.textContent.trim()); }", timeout=5000)
    except Exception:
        pass
    ann, h1 = page.evaluate("[document.getElementById('announce').textContent, document.querySelector('#app h1').textContent.trim()]")
    check(bool(ann) and h1 in ann, f"page change not announced (announced: {ann!r}, heading: {h1!r})")
    name = page.evaluate("fetch('data/players.json').then(r => r.json()).then(p => p[0].name)")
    page.keyboard.press("/")
    page.keyboard.type(name.split()[-1][:5].lower())
    page.wait_for_selector("#hq-list [role=option]")
    n = page.evaluate("document.querySelectorAll('#hq-list [role=option]').length")
    for _ in range(n):  # arrow down to the first player
        if page.evaluate("(document.querySelector('#hq-list [aria-selected=true]') || {}).getAttribute?.('href') || ''").startswith("#/player/"):
            break
        page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    check(page.evaluate("location.hash").startswith("#/player/"), "arrow keys + Enter do not open a player from search")
    if page.is_visible("details.more summary"):
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('app').classList.remove('entering','leaving'); document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'))")
        page.click("details.more summary")
        try:
            page.add_script_tag(url=AXE)
            res = page.evaluate("() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] })")
            check(not [v for v in res["violations"] if v["impact"] in ("serious", "critical")], "accessibility problems with the menu open: "
                  + ", ".join(v["id"] for v in res["violations"]))
        except Exception:
            pass
        page.keyboard.press("Escape")
        check(not page.evaluate("document.querySelector('details.more').open"), "Escape does not close the More menu")
    return out


def main(argv):
    baseline, ci = "--baseline" in argv, "--ci" in argv
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, url = serve()
    prints, layouts, fails = [], {}, 0
    with sync_playwright() as p:
        browser = p.chromium.launch(**({} if ci else {"channel": "chrome"}))
        for size, opts in SIZES.items():
            ctx = browser.new_context(service_workers="block", **opts)
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m: m.type == "error" and "404" not in m.text and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            for hsh in pages():
                errors.clear()
                page.goto(url + hsh)
                page.wait_for_load_state("networkidle")
                page.wait_for_function("() => document.querySelector('#app') && !document.querySelector('#app .sk') && document.querySelector('#app').children.length")
                page.add_style_tag(content=QUIET)
                page.evaluate("document.getElementById('app').classList.remove('entering','leaving')")
                page.wait_for_timeout(150)
                key = f"{size} {hsh}"
                layouts[key] = page.evaluate(FINGERPRINT)
                prob = page.evaluate(PROBLEMS)
                ax = []
                try:
                    page.add_script_tag(url=AXE)
                    res = page.evaluate("() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] })")
                    ax = [(v["impact"], v["id"], len(v["nodes"]), v["nodes"][0]["target"][0] if v["nodes"] else "") for v in res["violations"]]
                except Exception as e:  # no network: skip the accessibility scan
                    ax = [("skipped", str(e)[:60], 0, "")]
                page.screenshot(path=str(OUT / f"{size}_{hsh.strip('#/').replace('/', '_') or 'home'}.png"), full_page=True)
                bad = bool(errors or prob["overflow"] or any(i in ("serious", "critical") for i, *_ in ax))
                fails += bad
                prints.append((key, errors[:3], prob, ax))
            if size == "desktop":
                kb = keyboard(page, url)
                fails += bool(kb)
                prints.append(("desktop keyboard", kb, {"overflow": [], "tiny": []}, []))
            ctx.close()
        browser.close()
    httpd.shutdown()
    for key, errs, prob, ax in prints:
        flag = "OK " if not (errs or prob["overflow"] or prob["tiny"] or ax) else "!! "
        print(f"{flag}{key}")
        for e in errs:
            print("    problem:" if key.endswith("keyboard") else "    script error:", e[:160])
        if prob["overflow"]:
            print("    scrolls sideways because of:", ", ".join(prob["overflow"]))
        if prob["tiny"]:
            print(f"    {len(prob['tiny'])} text elements under 11px, e.g.", "; ".join(prob["tiny"][:3]))
        for imp, rid, n, tgt in ax:
            print(f"    a11y {imp}: {rid} ({n} element{'s' if n != 1 else ''}, e.g. {tgt})")
    if baseline:
        BASE.write_text(json.dumps(layouts))
        print(f"\nbaseline saved: {sum(len(v) for v in layouts.values())} elements on {len(layouts)} page views")
    elif BASE.exists():
        old = json.loads(BASE.read_text())
        moved = 0
        for k, cur in layouts.items():
            a, b = {tuple(x) for x in old.get(k, [])}, {tuple(x) for x in cur}
            d = len(a ^ b)
            if d:
                moved += 1
                print(f"layout changed: {k}: {d} element entries differ, e.g. {sorted(a - b)[:1]} -> {sorted(b - a)[:1]}")
        print(f"\nlayout vs baseline: {'no change' if not moved else f'{moved} page views changed'}")
    print(f"screenshots: {OUT}")
    return 1 if (ci and fails) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
