"""New Fanatical bundles and sales promotions, from the public /api/all/en JSON."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import httpx

from .base import Item

API_URL = "https://www.fanatical.com/api/all/en"
SITE = "https://www.fanatical.com/en"
CDN = "https://cdn.fanatical.com/production/product/400x225/"
PROMO_TYPES = {"TakeOver", "SlimBanner", "CarouselBackground"}
SKIP_PROMO = re.compile(r"pre-?order|upcoming|coming soon", re.IGNORECASE)
SUFFIX = re.compile(r"\s+(footer banner|home page|filter backgrounds|slim banner|banner|deals|tak(?:e ?)?over)$", re.IGNORECASE)


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _money(cents: float, currency: str) -> str:
    return f"${cents / 100:.2f} {currency}"


def parse_bundles(
    data: dict, now: datetime, currency: str = "CAD", max_age_days: int = 30
) -> list[Item]:
    """Bundles that are live now and went live within max_age_days."""
    items = []
    for b in data.get("pickandmix", []):
        start, end = _dt(b.get("valid_from")), _dt(b.get("valid_until"))
        if start is None or start > now or (end and end <= now):
            continue
        if now - start > timedelta(days=max_age_days):
            continue
        tiers = [t for t in b.get("tiers", []) if currency in t.get("price", {})]
        price = ""
        if tiers:
            first, last = tiers[0], tiers[-1]
            price = f"{first['quantity']} for {_money(first['price'][currency], currency)}"
            if last is not first:
                price += f", {last['quantity']} for {_money(last['price'][currency], currency)}"
        items.append(
            Item(
                source="fanatical",
                id=f"bundle:{b['_id']}",
                title=b["name"],
                url=f"{SITE}/pick-and-mix/{b['slug']}",
                price=price,
                end_date=end.date().isoformat() if end else "",
                image=f"{CDN}{b['cover_image']}" if b.get("cover_image") else "",
                note="Bundle",
            )
        )
    return items


def parse_promotions(data: dict, now: datetime) -> list[Item]:
    """Active sales and takeovers. Banners of one promotion collapse into one item."""
    found: dict[str, Item] = {}
    for p in data.get("images", []):
        if p.get("advert_type") not in PROMO_TYPES or SKIP_PROMO.search(p.get("name", "")):
            continue
        if (p.get("appears_on") or {}).get("coming_soon"):
            continue
        start, end = _dt(p.get("start_date")), _dt(p.get("end_date"))
        if start is None or end is None or not (start <= now < end):
            continue
        name = SUFFIX.sub("", p["name"]).strip()
        item_id = f"promo:{name.lower()}:{end.date().isoformat()}"
        found.setdefault(
            item_id,
            Item(
                source="fanatical",
                id=item_id,
                title=name,
                url=p.get("url") or f"{SITE}/on-sale",
                end_date=end.date().isoformat(),
                note="Sale / promotion",
            ),
        )
    return list(found.values())


class Fanatical:
    name = "fanatical"

    def __init__(self, currency: str = "CAD", client: httpx.Client | None = None, clock=None):
        self.currency = currency
        self.clock = clock or (lambda: datetime.now(UTC))
        self.warnings: list[str] = []
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0 game-alert-webhook"})

    def fetch(self) -> list[Item]:
        r = self.client.get(API_URL)
        r.raise_for_status()
        data = r.json()
        self.warnings = [
            f"Fanatical JSON has no '{key}' list. The site format may have changed."
            for key in ("pickandmix", "images")
            if not isinstance(data.get(key), list)
        ]
        now = self.clock()
        return parse_bundles(data, now, self.currency) + parse_promotions(data, now)
