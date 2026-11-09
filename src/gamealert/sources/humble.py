"""New Humble Bundle game bundles, read from the JSON block on humblebundle.com/games."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import httpx

from .base import Item

SITE = "https://www.humblebundle.com"
PAGE_URL = f"{SITE}/games"
BLOCK_RE = re.compile(
    r'<script id="landingPage-json-data" type="application/json">(.*?)</script>', re.DOTALL
)
BLURB_LIMIT = 120


def _dt(value: str | None) -> datetime | None:
    """Humble dates have no time zone. They are UTC."""
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def parse_games_page(html: str, now: datetime) -> tuple[list[Item], list[str]]:
    """Return (live game bundles, warnings). Raise ValueError if the JSON block is missing."""
    match = BLOCK_RE.search(html)
    if not match:
        raise ValueError("Humble Bundle page has no landingPage-json-data block")
    data = json.loads(match.group(1)).get("data", {})
    sections = (data.get("games") or {}).get("mosaic") or []
    items: list[Item] = []
    seen: set[str] = set()
    for section in sections:
        for p in section.get("products", []):
            url = p.get("product_url", "")
            # Only the Games category. Books and software bundles are skipped.
            if p.get("tile_stamp") != "games" or not url.startswith("/games/"):
                continue
            start, end = _dt(p.get("start_date|datetime")), _dt(p.get("end_date|datetime"))
            if start is None or end is None or not (start <= now < end):
                continue
            machine_name = p.get("machine_name") or url
            if machine_name in seen:
                continue
            seen.add(machine_name)
            blurb = " ".join((p.get("short_marketing_blurb") or "").split())
            note = "Bundle" + (f": {blurb[:BLURB_LIMIT]}" if blurb else "")
            items.append(
                Item(
                    source="humble",
                    id=f"bundle:{machine_name}",
                    title=p.get("tile_short_name") or p.get("tile_name") or machine_name,
                    url=f"{SITE}{url}",
                    end_date=end.date().isoformat(),
                    image=p.get("tile_image", ""),
                    note=note,
                )
            )
    warnings = []
    if not sections:
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
