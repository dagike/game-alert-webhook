from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from gamealert.sources.humble import PAGE_URL, Humble, parse_games_page

HTML = (Path(__file__).parent / "fixtures" / "humble_games.html").read_text()
NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def test_only_live_game_bundles():
    items, warnings = parse_games_page(HTML, NOW)
    assert [i.title for i in items] == ["Flat2VR Bundle", "Unhinged & Unsettling Visual Novels"]
    assert warnings == []
    titles = " ".join(i.title for i in items)
    for excluded in ("Book", "Expired", "Future", "Software"):
        assert excluded not in titles


def test_fields():
    flat = parse_games_page(HTML, NOW)[0][0]
    assert flat.id == "bundle:flat2vr_bundle"
    assert flat.price == "$11.23 CAD"
    assert flat.url == "https://www.humblebundle.com/games/flat2vr-bundle"
    assert flat.end_date == "2026-11-11"
    assert flat.note == "Bundle of 2 items: Game A, Game B"
    assert flat.source == "humble" and flat.image.endswith("flat2vr_bundle.jpg")


def test_bundle_ends_exactly_at_end_time():
    at_end = datetime(2026, 11, 11, 5, tzinfo=UTC)
    assert [i.title for i in parse_games_page(HTML, at_end)[0]] == ["Unhinged & Unsettling Visual Novels"]


def test_missing_block_raises():
    with pytest.raises(ValueError, match="feedItems"):
        parse_games_page("<html></html>", NOW)


def test_empty_games_list_warns():
    html = '<script>self.__next_f.push([1,"{\\"feedItems\\":[]}"])</script>'
    items, warnings = parse_games_page(html, NOW)
    assert items == [] and "page format may have changed" in warnings[0]


@respx.mock
def test_fetch():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    source = Humble(clock=lambda: NOW)
    assert len(source.fetch()) == 2 and source.warnings == []


@respx.mock
def test_fetch_http_error_raises():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        Humble(clock=lambda: NOW).fetch()
