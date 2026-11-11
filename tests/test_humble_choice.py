from pathlib import Path

import httpx
import pytest
import respx

from gamealert.sources.humble_choice import MEMBERSHIP_URL, HumbleChoice, parse_membership

FX = Path(__file__).parent / "fixtures"
PAGE = (FX / "humble_choice.html").read_text()
EMPTY = (FX / "humble_choice_empty.html").read_text()


def test_parse_membership_skips_ign_plus_and_keeps_order():
    info, games = parse_membership(PAGE)
    assert info == {
        "machine_name": "november_2026_choice",
        "title": "Humble Choice: November 2026",
        "price": "$11.99 per month",
    }
    assert [g["title"] for g in games] == ["Mafia: The Old Country", "The Outer Worlds 2"]


def test_missing_data_raises():
    with pytest.raises(ValueError, match="subscriptionProducts"):
        parse_membership("<html></html>")


@respx.mock
def test_fetch_returns_one_item_for_the_month():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(200, text=PAGE))
    source = HumbleChoice()
    (item,) = source.fetch()
    assert item.id == "choice:november_2026_choice"
    assert item.title == "Humble Choice: November 2026"
    assert item.url == MEMBERSHIP_URL and item.price == "$11.99 per month"
    assert item.note == "Mafia: The Old Country, The Outer Worlds 2"
    assert item.image.endswith("mafia_choice.jpg")
    assert source.warnings == []


@respx.mock
def test_empty_game_list_gives_warning_and_no_item():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(200, text=EMPTY))
    source = HumbleChoice()
    assert source.fetch() == []
    assert "No games listed yet" in source.warnings[0]


@respx.mock
def test_http_error_raises():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        HumbleChoice().fetch()
