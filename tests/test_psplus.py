from pathlib import Path

import httpx
import respx

from gamealert.sources.psplus import FEED_URL, PsPlus, parse_feed

XML = (Path(__file__).parent / "fixtures" / "psplus.xml").read_text()


def test_only_monthly_games_posts():
    items = parse_feed(XML)
    assert [i.title for i in items] == [
        "PS Plus Essential: October games",
        "PS Plus Essential: September games",
    ]
    assert "F1 25" in items[0].note
    assert items[0].url.startswith("https://blog.playstation.com/2026/09/30/")
    assert items[0].id != items[1].id


def test_empty_feed():
    assert parse_feed("<rss version='2.0'><channel></channel></rss>") == []


@respx.mock
def test_fetch():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=XML))
    assert len(PsPlus().fetch()) == 1


@respx.mock
def test_fetch_returns_only_newest_post():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=XML))
    items = PsPlus().fetch()
    assert [i.title for i in items] == ["PS Plus Essential: October games"]
