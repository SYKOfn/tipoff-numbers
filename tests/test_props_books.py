from pipeline.oddsapi import PROPS_BOOKS, _one_book


def test_pinnacle_preferred_and_books_never_mixed():
    rows = [{"book": "draftkings", "line": 9.5}, {"book": "pinnacle", "line": 10.5}, {"book": "fanduel", "line": 9.5}]
    assert {r["book"] for r in _one_book(rows)} == {"pinnacle"}
    rows = [{"book": "draftkings"}, {"book": "fanduel"}, {"book": "fanduel"}]
    assert {r["book"] for r in _one_book(rows)} == {"fanduel"}


def test_props_books_fit_one_region():
    books = PROPS_BOOKS.split(",")
    assert books[0] == "pinnacle" and len(books) <= 10  # 10 books = 1 region = no extra credits
