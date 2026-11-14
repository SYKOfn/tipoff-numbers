"""The site's own JavaScript, run in a real browser: the chance maths must match the Python model exactly, and the
search must find pages, teams, games and players. Skipped where Playwright and a browser are not installed (the
data-update workflow); run locally and by the site-check workflow's environment."""
import math

import pytest

pw = pytest.importorskip("playwright.sync_api")

from model.players import over_prob  # noqa: E402


@pytest.fixture(scope="module")
def page():
    from tools.site_check import serve
    httpd, url = serve()
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            try:
                b = p.chromium.launch()
            except Exception as e:  # no browser on this machine
                httpd.shutdown()
                pytest.skip(f"no browser: {e}")
        pg = b.new_page()
        pg.goto(url + "#/about")
        pg.wait_for_function("() => typeof nbOver === 'function' && Object.keys(TEAMS).length")
        yield pg
        b.close()
    httpd.shutdown()


@pytest.mark.parametrize("line,mu,disp", [(4.5, 7.6, 1.32), (9.5, 15.3, 3.0), (0.5, 1.9, 1.22), (24.5, 26.0, 2.5), (2.5, 0.8, 1.02)])
def test_negative_binomial_matches_python(page, line, mu, disp):
    js = page.evaluate(f"nbOver({line}, {mu}, {disp})")
    assert abs(js - over_prob("pts", line, mu, {"pts": disp})) < 1e-9


def test_normal_cdf(page):
    for x in (-2.0, -0.5, 0.0, 0.7, 1.96):
        assert abs(page.evaluate(f"ncdf({x})") - 0.5 * (1 + math.erf(x / math.sqrt(2)))) < 1e-6


def test_formatting(page):
    assert page.evaluate("pct(0.374)") == "37%"
    assert page.evaluate("sgn(-3.4, 1)") == "−3.4"
    assert page.evaluate("sgn(2, 0)") == "+2"
    assert page.evaluate("h('<b>\"x\"</b>')") == "&lt;b&gt;&quot;x&quot;&lt;/b&gt;"


def test_search_finds_pages_teams_and_players(page):
    hrefs = lambda q, ps="[]", gs="[]": page.evaluate(f"searchHits({q!r}, {ps}, {gs}).map(x => x.href)")
    assert "#/standings" in hrefs("stand")
    assert len(hrefs("")) == 11  # an empty search lists every page
    team = page.evaluate("Object.values(TEAMS)[0]")
    assert f"#/team/{team['abbr']}" in hrefs(team["name"].lower()[:5])
    ps = '[{"id": "7", "name": "Test Player", "team": "' + team["abbr"] + '", "ppg": 20}]'
    assert "#/player/7" in hrefs("test p", ps)
    gs = '[{"id": "9", "home": "' + team["abbr"] + '", "away": "' + team["abbr"] + '", "tip": "2026-11-15T00:00Z"}]'
    assert "#/game/9" in hrefs(team["name"].lower()[:5], "[]", gs)


def test_ring_draws_the_chance(page):
    svg = page.evaluate("ring(0.5, 40)")
    r = 40 / 2 - 3
    assert f'stroke-dasharray="{0.5 * 2 * math.pi * r:.1f} {2 * math.pi * r:.1f}"' in svg
