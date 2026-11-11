"""New Humble Bundle game bundles, read from the data embedded in humblebundle.com/games."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from .base import Item
from .humble_page import flight_text, json_list

SITE = "https://www.humblebundle.com"
PAGE_URL = f"{SITE}/games"
BLURB_LIMIT = 120


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _money(price: dict | None) -> str:
    current = (price or {}).get("currentPrice") or {}
    if "centAmount" not in current:
        return ""
    return f"${current['centAmount'] / 100:.2f} {current.get('currencyCode', '')}".strip()


def parse_games_page(html: str, now: datetime) -> tuple[list[Item], list[str]]:
    """Return (live game bundles, warnings). Raise ValueError if the bundle list is missing."""
    feed = json_list(flight_text(html), "feedItems")
    if feed is None:
        raise ValueError("Humble Bundle page has no feedItems list")
    items: list[Item] = []
    seen: set[str] = set()
    for entry in feed:
        p = entry.get("value") or {}
        url = p.get("url", "")
        # Only the Games category. Books and software bundles are skipped.
        if p.get("category") != "games" or not url.startswith("/games/"):
            continue
        end = _dt(p.get("endDate"))
        if end is None or now >= end:
            continue
        key = p.get("productKey") or url
        if key in seen:
            continue
        seen.add(key)
        titles = p.get("includedItemTitles") or []
        count = p.get("itemsCount") or len(titles)
        note = f"Bundle of {count} items" if count else "Bundle"
        if titles:
            note += ": " + ", ".join(titles)
        items.append(
            Item(
                source="humble",
                id=f"bundle:{key}",
                title=p.get("title") or key,
                url=f"{SITE}{url}",
                price=_money(p.get("displayPrice")),
                end_date=end.date().isoformat(),
                image=p.get("thumbnail", ""),
                note=note[:BLURB_LIMIT * 2],
            )
        )
    warnings = []
    if not feed:
        warnings.append("Humble Bundle page has no game bundle list. The page format may have changed.")
    return items, warnings


class Humble:
    name = "humble"

    def __init__(self, client: httpx.Client | None = None, clock=None):
        self.client = client or httpx.Client(
            timeout=30, headers={"User-Agent": "Mozilla/5.0 game-alert-webhook"}
        )
        self.clock = clock or (lambda: datetime.now(UTC))
        self.warnings: list[str] = []

    def fetch(self) -> list[Item]:
        r = self.client.get(PAGE_URL)
        r.raise_for_status()
        items, self.warnings = parse_games_page(r.text, self.clock())
        return items
