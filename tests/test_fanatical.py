import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from gamealert.sources.fanatical import API_URL, Fanatical, parse_bundles, parse_promotions

DATA = json.loads((Path(__file__).parent / "fixtures" / "fanatical.json").read_text())
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


def test_bundles_recent_live_only():
    titles = {i.title for i in parse_bundles(DATA, NOW)}
    assert "Build your own Birthday Bonanza Bundle" in titles
    assert "Platinum Collection - Build your own Bundle (November 2026)" in titles
    assert "Excel Build your own Bundle with Zenva" not in titles  # live since 2020
    assert "Expired Bundle" not in titles


def test_bundle_fields():
    item = next(i for i in parse_bundles(DATA, NOW) if "Birthday Bonanza" in i.title)
    assert item.url == "https://www.fanatical.com/en/pick-and-mix/build-your-own-birthday-bonanza-bundle"
    assert item.end_date == "2026-12-11"
    assert "$" in item.price and "CAD" in item.price
    assert item.id.startswith("bundle:")


def test_promotions_collapse_and_filter():
    items = parse_promotions(DATA, NOW)
    titles = [i.title for i in items]
    assert titles.count("Birthday Bash 2026") == 1
    assert "The FantasyVerse" in titles
    assert not any("Football Manager" in t for t in titles)


def test_promotion_expires():
    later = datetime(2026, 11, 20, tzinfo=UTC)
    assert not any("Birthday Bash" in i.title for i in parse_promotions(DATA, later))


@respx.mock
def test_fetch():
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=DATA))
    assert any(i.note == "Bundle" for i in Fanatical(clock=lambda: NOW).fetch())
