from pathlib import Path

import httpx
import pytest
import respx

from gamealert.sources.humble_choice import (
    MEMBERSHIP_URL,
    HumbleChoice,
    choice_slug,
    parse_membership,
    parse_month,
)

FX = Path(__file__).parent / "fixtures"
MEMBERSHIP = (FX / "humble_choice_membership.html").read_text()
MONTH = (FX / "humble_choice_month.html").read_text()
EMPTY = (FX / "humble_choice_empty.html").read_text()
MONTH_URL = f"{MEMBERSHIP_URL}/november-2026"


def test_choice_slug():
    assert choice_slug("november_2026_choice") == "november-2026"
    assert choice_slug("odd_name") == "odd-name"


def test_parse_membership():
    info = parse_membership(MEMBERSHIP)
    assert info == {
        "machine_name": "november_2026_choice",
        "title": "Humble Choice: November 2026",
        "end_date": "2026-12-01",
        "price": "$17.99 CAD per month",
    }


def test_parse_month_skips_coupon_and_keeps_order():
    titles = [g["title"] for g in parse_month(MONTH)]
    assert titles == ["Mafia: The Old Country + 2 DLC Packs", "The Outer Worlds 2", "Space Haven"]


def test_missing_block_raises():
    with pytest.raises(ValueError, match="webpack-choice-marketing-data"):
        parse_membership("<html></html>")
    with pytest.raises(ValueError, match="webpack-monthly-product-data"):
        parse_month("<html></html>")


@respx.mock
def test_fetch_returns_one_item_for_the_month():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(200, text=MEMBERSHIP))
    respx.get(MONTH_URL).mock(return_value=httpx.Response(200, text=MONTH))
    source = HumbleChoice()
    (item,) = source.fetch()
    assert item.id == "choice:november_2026_choice"
    assert item.title == "Humble Choice: November 2026"
    assert item.url == MONTH_URL
    assert item.price == "$17.99 CAD per month" and item.end_date == "2026-12-01"
    assert item.note == "Mafia: The Old Country + 2 DLC Packs, The Outer Worlds 2, Space Haven"
    assert item.image.endswith("mafia_theoldcountry.png")
    assert source.warnings == []


@respx.mock
def test_month_page_404_gives_warning_and_no_item():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(200, text=MEMBERSHIP))
    respx.get(MONTH_URL).mock(return_value=httpx.Response(404))
    source = HumbleChoice()
    assert source.fetch() == []
    assert "not found" in source.warnings[0]


@respx.mock
def test_empty_game_list_gives_warning_and_no_item():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(200, text=MEMBERSHIP))
    respx.get(MONTH_URL).mock(return_value=httpx.Response(200, text=EMPTY))
    source = HumbleChoice()
    assert source.fetch() == []
    assert "No games listed yet" in source.warnings[0]


@respx.mock
def test_membership_http_error_raises():
    respx.get(MEMBERSHIP_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        HumbleChoice().fetch()
