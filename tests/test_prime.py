import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from gamealert.sources.prime import (
    GRAPHQL_URL,
    PAGE_URL,
    REDDIT_URL,
    Prime,
    parse_csrf,
    parse_items,
    parse_reddit,
    store_name,
)

FX = Path(__file__).parent / "fixtures"
HTML = (FX / "prime_claims.html").read_text()
REDDIT = (FX / "prime_reddit.xml").read_text()
DATA = json.loads((FX / "prime_items.json").read_text())
NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)


def test_parse_csrf():
    assert parse_csrf(HTML) == "tok123+/="
    with pytest.raises(ValueError, match="csrf-key"):
        parse_csrf("<html></html>")


def test_only_live_free_games():
    items = parse_items(DATA, NOW)
    assert [i.title for i in items] == ["Jurassic World Evolution 2", "Squirrel with a Gun"]
    first = items[0]
    assert first.id == "prime:jurassicworldevolution2:2026-11"
    assert first.end_date == "2026-12-16" and first.price == "Free with Prime"
    assert first.note == "Epic Games Store, via Amazon" and first.url.startswith("https://gaming.amazon.com/")


def test_offer_window_is_respected():
    late = datetime(2026, 12, 20, tzinfo=UTC)
    assert [i.title for i in parse_items(DATA, late)] == ["Future Game"]


def test_store_name():
    base = "https://gaming.amazon.com/{}/dp/x"
    assert store_name(base.format("a-b-epic")) == "Epic Games Store"
    assert store_name(base.format("a-b-gog")) == "GOG"
    assert store_name(base.format("a-b-aga")) == "Amazon Games app"
    assert store_name(base.format("a-b")) == "Amazon Prime"
    assert store_name("https://luna.amazon.com/game/x") == "Amazon Prime"


def test_api_error_raises():
    with pytest.raises(ValueError, match="Luna API error: boom"):
        parse_items({"errors": [{"message": "boom"}]}, NOW)


@respx.mock
def test_fetch_sends_token_and_returns_items():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    post = respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=DATA))
    source = Prime(clock=lambda: NOW)
    assert len(source.fetch()) == 2 and source.warnings == []
    sent = post.calls[0].request.headers
    assert sent["csrf-token"] == "tok123+/=" and sent["client-id"] == "CarboniteApp"


def test_parse_reddit():
    items = parse_reddit(REDDIT, NOW)
    assert [(i.title, i.note.split(",")[0]) for i in items] == [
        ("Jurassic World Evolution 2", "Epic Games Store"),
        ("Radiolight", "Epic Games Store"),
        ("Squirrel with a Gun", "Amazon Games app"),
        ("WRC Generations", "Epic Games Store"),
    ]
    assert items[0].url.endswith("/aaa/") and "via Reddit" in items[0].note


def test_amazon_and_reddit_share_ids():
    amazon = {i.title: i.id for i in parse_items(DATA, NOW)}
    reddit = {i.title: i.id for i in parse_reddit(REDDIT, NOW)}
    assert amazon["Jurassic World Evolution 2"] == reddit["Jurassic World Evolution 2"]
    assert amazon["Squirrel with a Gun"] == reddit["Squirrel with a Gun"]


@respx.mock
def test_amazon_ok_does_not_call_reddit():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=DATA))
    reddit = respx.get(REDDIT_URL).mock(return_value=httpx.Response(200, text=REDDIT))
    assert len(Prime(clock=lambda: NOW).fetch()) == 2
    assert not reddit.called


@respx.mock
def test_amazon_blocked_falls_back_to_reddit_without_warning():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(403))
    respx.get(REDDIT_URL).mock(return_value=httpx.Response(200, text=REDDIT))
    source = Prime(clock=lambda: NOW)
    items = source.fetch()
    assert len(items) == 4 and all("via Reddit" in i.note for i in items)
    assert source.warnings == []


@respx.mock
def test_amazon_empty_falls_back_to_reddit():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"items": {"items": []}}}))
    respx.get(REDDIT_URL).mock(return_value=httpx.Response(200, text=REDDIT))
    assert len(Prime(clock=lambda: NOW).fetch()) == 4


@respx.mock
def test_no_games_anywhere_gives_warning():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json={"data": {"items": {"items": []}}}))
    respx.get(REDDIT_URL).mock(return_value=httpx.Response(200, text="<feed xmlns='http://www.w3.org/2005/Atom'/>"))
    source = Prime(clock=lambda: NOW)
    assert source.fetch() == [] and "No Prime free games" in source.warnings[0]


@respx.mock
def test_both_failed_raises_and_names_both():
    respx.get(PAGE_URL).mock(return_value=httpx.Response(200, text=HTML))
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(403))
    respx.get(REDDIT_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(RuntimeError, match="Amazon failed: HTTP 403. Reddit failed: HTTP 429"):
        Prime(clock=lambda: NOW).fetch()
