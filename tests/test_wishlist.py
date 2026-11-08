import json
from pathlib import Path

import httpx
import pytest
import respx

from gamealert.sources.wishlist import API, Wishlist, best_alert

PRICES = json.loads((Path(__file__).parent / "fixtures" / "itad_prices.json").read_text())
H = "11111111-1111-1111-1111-11111111111"
GAMES = {"Hades": H + "1", "Celeste": H + "2", "Hollow Knight": H + "3"}


def test_at_all_time_low_picks_cheapest_shop():
    item = best_alert(PRICES[0], "Hades", 0)
    assert item.note == "All-time low"
    assert item.price == "$7.49 CAD at Steam (-70%, was $24.99 CAD)"
    assert item.end_date == "2026-11-20"
    assert item.url == "https://itad.link/hades"


def test_near_low_needs_tolerance():
    assert best_alert(PRICES[1], "Celeste", 0) is None
    item = best_alert(PRICES[1], "Celeste", 5)
    assert item and item.note.startswith("Within 5%")


def test_not_on_sale_and_no_data():
    assert best_alert(PRICES[2], "Hollow Knight", 50) is None
    assert best_alert(PRICES[3], "Unknown", 0) is None


def test_new_id_when_price_changes():
    a = best_alert(PRICES[0], "Hades", 0)
    changed = json.loads(json.dumps(PRICES[0]))
    changed["deals"][0]["price"] = {"amount": 6.99, "amountInt": 699, "currency": "CAD"}
    assert best_alert(changed, "Hades", 0).id != a.id


def mock_api():
    def lookup(request):
        title = request.url.params["title"]
        if title in GAMES:
            return httpx.Response(200, json={"found": True, "game": {"id": GAMES[title]}})
        return httpx.Response(200, json={"found": False})

    respx.get(f"{API}/games/lookup/v1").mock(side_effect=lookup)
    return respx.post(f"{API}/games/prices/v3").mock(return_value=httpx.Response(200, json=PRICES))


@respx.mock
def test_fetch_end_to_end_with_missing_title():
    route = mock_api()
    w = Wishlist(["Hades", "Celeste", "Nope Game"], "k", tolerance_percent=0)
    items = w.fetch()
    assert [i.title for i in items] == ["Hades"]
    assert w.warnings == ["Wishlist title not found on IsThereAnyDeal: Nope Game"]
    request = route.calls[0].request
    assert request.url.params["country"] == "CA" and request.url.params["key"] == "k"
    assert json.loads(request.content) == [GAMES["Hades"], GAMES["Celeste"]]


def test_missing_key_raises():
    with pytest.raises(ValueError, match="ITAD_API_KEY"):
        Wishlist(["Hades"], "").fetch()


def test_empty_wishlist_needs_no_key():
    assert Wishlist([], "").fetch() == []
