from pipeline import share

T = {"name": "BKN at NO", "game": "1", "p": 0.43, "fair": 2.34, "min_odds": 2.45, "result": "miss",
     "legs": [{"desc": "Julius Randle over 4.5 rebounds", "p": 0.82, "result": "miss"}] + [{"desc": f"Leg {i}", "p": 0.85, "result": "hit"} for i in range(4)]}


def test_picture_is_a_share_card():
    assert share.draw(T, "2026-11-11").size == (1200, 630)


def test_page_has_preview_tags_and_sends_visitors_on():
    html = share.page(T, "2026-11-11", "2026-11-11-1")
    for tag in ('og:image" content="https://sykofn.github.io/tipoff-numbers/t/2026-11-11-1.png', 'twitter:card" content="summary_large_image',
                "43% ticket", "2.45+", 'url=../#/parlay'):
        assert tag in html
