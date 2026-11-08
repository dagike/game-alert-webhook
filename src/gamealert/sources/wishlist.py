"""Wishlist games at or near their all-time low price, using the IsThereAnyDeal API."""

from __future__ import annotations

import httpx

from .base import Item

API = "https://api.isthereanydeal.com"


def _money(price: dict) -> str:
    return f"${price['amount']:.2f} {price['currency']}"


def best_alert(entry: dict, title: str, tolerance_percent: float) -> Item | None:
    """Return an Item if the cheapest current deal is at or near the all-time low."""
    low = (entry.get("historyLow") or {}).get("all")
    deals = entry.get("deals") or []
    if not low or not deals:
        return None
    best = min(deals, key=lambda d: d["price"]["amountInt"])
    limit = low["amountInt"] * (1 + tolerance_percent / 100)
    if best["price"]["amountInt"] > limit:
        return None
    at_low = best["price"]["amountInt"] <= low["amountInt"]
    shop = best["shop"]["name"]
    price = f"{_money(best['price'])} at {shop}"
    if best.get("cut"):
        price += f" (-{best['cut']}%, was {_money(best['regular'])})"
    return Item(
        source="wishlist",
        id=f"{entry['id']}:{best['shop']['id']}:{best['price']['amountInt']}",
        title=title,
        url=best.get("url", ""),
        price=price,
        end_date=(best.get("expiry") or "")[:10],
        note="All-time low" if at_low else f"Within {tolerance_percent:g}% of all-time low ({_money(low)})",
    )


class Wishlist:
    name = "wishlist"

    def __init__(
        self,
        titles: list[str],
        api_key: str,
        country: str = "CA",
        tolerance_percent: float = 0.0,
        client: httpx.Client | None = None,
    ):
        self.titles = titles
        self.api_key = api_key
        self.country = country
        self.tolerance = tolerance_percent
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": "game-alert-webhook"})
        self.warnings: list[str] = []

    def lookup(self, title: str) -> str | None:
        r = self.client.get(f"{API}/games/lookup/v1", params={"key": self.api_key, "title": title})
        r.raise_for_status()
        data = r.json()
        return data["game"]["id"] if data.get("found") else None

    def fetch(self) -> list[Item]:
        self.warnings = []
        if not self.titles:
            return []
        if not self.api_key:
            raise ValueError("ITAD_API_KEY is not set")
        ids: dict[str, str] = {}  # game id -> wishlist title
        for title in self.titles:
            game_id = self.lookup(title)
            if game_id:
                ids[game_id] = title
            else:
                self.warnings.append(f"Wishlist title not found on IsThereAnyDeal: {title}")
        if not ids:
            return []
        items = []
        id_list = list(ids)
        for start in range(0, len(id_list), 200):
            r = self.client.post(
                f"{API}/games/prices/v3",
                params={"key": self.api_key, "country": self.country, "deals": "true"},
                json=id_list[start : start + 200],
            )
            r.raise_for_status()
            for entry in r.json():
                if entry["id"] not in ids:
                    continue
                item = best_alert(entry, ids[entry["id"]], self.tolerance)
                if item:
                    items.append(item)
        return items
