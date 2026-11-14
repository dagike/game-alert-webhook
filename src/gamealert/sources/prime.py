"""Free games that come with Amazon Prime, read from the Amazon Luna claims page."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx

from .base import Item

SITE = "https://luna.amazon.com"
PAGE_URL = f"{SITE}/claims/home"
GRAPHQL_URL = f"{SITE}/graphql"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64)"
QUERY = (
    "{ items(collectionType: FEATURED_CONTENT, dateOverride: null, pageSize: 50) "
    "{ items { id isFGWP category assets { title externalClaimLink } "
    "offers { startTime endTime } } } }"
)
CSRF_RE = re.compile(r"name=['\"]csrf-key['\"]\s+value=['\"]([^'\"]+)['\"]")
STORES = {"epic": "Epic Games Store", "gog": "GOG", "aga": "Amazon Games app"}


def parse_csrf(html: str) -> str:
    """Return the session token in the claims page. Raise ValueError if it is missing."""
    match = CSRF_RE.search(html)
    if not match:
        raise ValueError("Luna claims page has no csrf-key")
    return match.group(1)


def store_name(link: str) -> str:
    """The claim link ends in a slug such as jurassic-world-evolution-2-epic."""
    match = re.search(r"/([a-z0-9-]+)/dp/", link)
    suffix = match.group(1).rsplit("-", 1)[-1] if match else ""
    return STORES.get(suffix, "Amazon Prime")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def parse_items(data: dict, now: datetime) -> list[Item]:
    """Return live free games. Raise ValueError if Amazon sent an error."""
    if data.get("errors"):
        raise ValueError(f"Luna API error: {data['errors'][0].get('message', 'unknown')}")
    entries = ((data.get("data") or {}).get("items") or {}).get("items") or []
    items = []
    for e in entries:
        # Only full free games. Luna streaming promotions are "EXTERNAL".
        if not e.get("isFGWP") or e.get("category") != "FULL_GAME":
            continue
        for offer in e.get("offers") or []:
            start, end = _dt(offer["startTime"]), _dt(offer["endTime"])
            if not (start <= now < end):
                continue
            assets = e.get("assets") or {}
            link = assets.get("externalClaimLink", "")
            items.append(
                Item(
                    source="prime",
                    id=f"prime:{e['id']}:{offer['endTime']}",
                    title=assets.get("title", e["id"]),
                    url=link,
                    price="Free with Prime",
                    end_date=offer["endTime"][:10],
                    note=store_name(link),
                )
            )
            break
    return items


class Prime:
    name = "prime"

    def __init__(self, client: httpx.Client | None = None, clock=None):
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
        self.clock = clock or (lambda: datetime.now(UTC))
        self.warnings: list[str] = []

    def fetch(self) -> list[Item]:
        self.warnings = []
        page = self.client.get(PAGE_URL)
        page.raise_for_status()
        token = parse_csrf(page.text)
        r = self.client.post(
            GRAPHQL_URL,
            json={"query": QUERY},
            headers={"client-id": "CarboniteApp", "csrf-token": token},
        )
        r.raise_for_status()
        items = parse_items(r.json(), self.clock())
        if not items:
            self.warnings.append("No Prime free games listed. The page format may have changed.")
        return items
