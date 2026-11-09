"""Open every page of the site in a real (headless) browser before it is published.

Fails (exit 1) if any page throws a script error, shows "Couldn't load this page", or comes up nearly
empty, or if adding a leg to the ticket does not show the bet slip. The update workflow then stops before
publishing, so a broken page never reaches the site, and GitHub emails the owner.
Usage: python -m tools.smoke [site_dir]
"""
import asyncio
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

SITE = Path(sys.argv[1] if len(sys.argv) > 1 else "site")


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(SITE))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def routes():
    d = SITE / "data"
    sch = json.loads((d / "schedule.json").read_text())
    pl = json.loads((d / "players.json").read_text())
    r = ["#/", "#/games", "#/players", "#/players/all", "#/accuracy", "#/parlay", "#/about", "#/standings", "#/teams", "#/mind"]
    if sch.get("upcoming"):
        r.append(f"#/game/{sch['upcoming'][0]['id']}")
        r.append(f"#/team/{sch['upcoming'][0]['home']}")
    if sch.get("results"):
        r.append(f"#/game/{sch['results'][0]['id']}")
    if pl:
        r.append(f"#/player/{pl[0]['id']}")
    return r


async def main():
    from playwright.async_api import async_playwright
    srv = serve()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    fails = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.goto(base)
        await pg.wait_for_timeout(1500)
        for r in routes():
            errors.clear()
            await pg.goto(base + r)
            await pg.wait_for_timeout(1200)
            txt = await pg.inner_text("#app")
            if errors:
                fails.append(f"{r}: script error: {errors[0][:200]}")
            elif "Couldn't load this page" in txt:
                fails.append(f"{r}: {txt.strip()[:200]}")
            elif len(txt.strip()) < 150:
                fails.append(f"{r}: page nearly empty ({len(txt.strip())} characters)")
            else:
                print("ok", r, len(txt))
        # the bet slip: add the first leg found on Tonight or the parlay page
        for r in ("#/", "#/parlay", "#/players"):
            await pg.goto(base + r)
            await pg.wait_for_timeout(1200)
            btn = await pg.query_selector("[data-add]")
            if btn:
                await btn.click()
                await pg.wait_for_timeout(400)
                if not await pg.is_visible("#slip"):
                    fails.append(f"{r}: adding a leg did not show the bet slip")
                else:
                    print("ok bet slip from", r)
                    await pg.evaluate("localStorage.clear()")
                break
        await b.close()
    srv.shutdown()
    for f in fails:
        print("FAIL", f)
    print(f"page tests: {len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
