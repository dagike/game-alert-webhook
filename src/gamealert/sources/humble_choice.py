"""The current Humble Choice month and its games, read from humblebundle.com/membership."""

from __future__ import annotations

import re

import httpx

from .base import Item
from .humble_page import flight_text, json_list

SITE = "https://www.humblebundle.com"
MEMBERSHIP_URL = f"{SITE}/membership"
MONTH_RE = re.compile(r"Get ([A-Z][a-z]+) (\d{4}) Humble Choice")
PRICE_RE = re.compile(r"subscribe for just (\$[\d.,]+) per month")


def _is_game(product: dict) -> bool:
    """Skip entries that are not games, for example the IGN Plus subscription."""
    ident = (product.get("id") or "").lower()
    return not ("coupon" in ident or "ignplus" in ident or "subscription" in (product.get("title") or "").lower())


def parse_membership(html: str) -> tuple[dict, list[dict]]:
    """Return (month info, games). Raise ValueError if the page has no Choice data."""
    text = flight_text(html)
    products = json_list(text, "subscriptionProducts")
    month = MONTH_RE.search(text)
    if products is None or month is None:
        raise ValueError("Humble Choice page has no subscriptionProducts list or month name")
    price = PRICE_RE.search(text)
    name, year = month.group(1), month.group(2)
    info = {
        "machine_name": f"{name.lower()}_{year}_choice",
        "title": f"Humble Choice: {name} {year}",
        "price": f"{price.group(1)} per month" if price else "",
    }
    games = [
        {"title": p.get("title", p.get("id", "")), "image": p.get("thumbnail", "")}
        for p in products
        if _is_game(p)
    ]
    return info, games


class HumbleChoice:
    name = "humble_choice"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=30, headers={"User-Agent": "Mozilla/5.0 game-alert-webhook"}
        )
        self.warnings: list[str] = []

    def fetch(self) -> list[Item]:
        self.warnings = []
        r = self.client.get(MEMBERSHIP_URL)
        r.raise_for_status()
        info, games = parse_membership(r.text)
        if not games:
            self.warnings.append(f"No games listed yet for {info['title']}")
            return []
        return [
            Item(
                source="humble_choice",
                id=f"choice:{info['machine_name']}",
                title=info["title"],
                url=MEMBERSHIP_URL,
                price=info["price"],
                image=games[0]["image"],
                note=", ".join(g["title"] for g in games),
            )
        ]
