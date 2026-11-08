"""Free games from Epic (official API), plus Steam and GOG (GamerPower API)."""

from __future__ import annotations

import httpx

from .base import Item

EPIC_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways"
GAMERPOWER_PLATFORMS = {"steam": "Steam", "gog": "GOG"}


def parse_epic(data: dict) -> list[Item]:
    """Return games that are free now. Skip games that are always free and future offers."""
    items = []
    elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
    for g in elements:
        offers = ((g.get("promotions") or {}).get("promotionalOffers")) or []
        active = [o for block in offers for o in block.get("promotionalOffers", [])]
        price = (g.get("price") or {}).get("totalPrice") or {}
        free_now = [
            o
            for o in active
            if (o.get("discountSetting") or {}).get("discountPercentage") == 0
        ]
        if not free_now or price.get("originalPrice", 0) <= 0 or price.get("discountPrice", 1) != 0:
            continue
        offer = free_now[0]
        mappings = g.get("offerMappings") or []
        slug = (mappings[0].get("pageSlug") if mappings else None) or g.get("productSlug") or g.get("urlSlug")
        images = [k["url"] for k in g.get("keyImages", []) if k.get("type") == "OfferImageWide"]
        end = offer.get("endDate", "")
        items.append(
            Item(
                source="free_games",
                id=f"epic:{g['id']}:{end}",
                title=g["title"],
                url=f"https://store.epicgames.com/en-US/p/{slug}" if slug else "",
                price=f"Free (was {price.get('fmtPrice', {}).get('originalPrice', '?')})",
                end_date=end[:10],
                image=images[0] if images else "",
                note="Epic Games Store",
            )
        )
    return items


def parse_gamerpower(data, store: str) -> list[Item]:
    """GamerPower returns a dict with status 0 (or HTTP 201) when nothing is available."""
    if not isinstance(data, list):
        return []
    items = []
    for g in data:
        if g.get("status") != "Active" or g.get("type") != "Game":
            continue
        end = g.get("end_date") or ""
        items.append(
            Item(
                source="free_games",
                id=f"gamerpower:{g['id']}",
                title=g["title"],
                url=g.get("open_giveaway_url") or g.get("gamerpower_url", ""),
                price=f"Free (worth {g['worth']})" if g.get("worth", "N/A") != "N/A" else "Free",
                end_date=end[:10] if end != "N/A" else "",
                image=g.get("image", ""),
                note=store,
            )
        )
    return items


class FreeGames:
    name = "free_games"

    def __init__(self, country: str = "CA", client: httpx.Client | None = None):
        self.country = country
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "game-alert-webhook"})
        self.warnings: list[str] = []

    def fetch(self) -> list[Item]:
        """Epic and GamerPower are separate. One may fail while the other still works."""
        self.warnings = []
        items: list[Item] = []
        failures = 0
        try:
            r = self.client.get(EPIC_URL, params={"locale": "en-US", "country": self.country})
            r.raise_for_status()
            items += parse_epic(r.json())
        except (httpx.HTTPError, ValueError) as exc:
            failures += 1
            self.warnings.append(f"Epic Games Store unavailable: {type(exc).__name__}: {exc}")
        for platform, store in GAMERPOWER_PLATFORMS.items():
            try:
                r = self.client.get(GAMERPOWER_URL, params={"platform": platform, "type": "game"})
                if r.status_code == 200:
                    items += parse_gamerpower(r.json(), store)
                elif r.status_code != 201:  # 201 means "no giveaways right now"
                    raise httpx.HTTPError(f"HTTP {r.status_code}")
            except (httpx.HTTPError, ValueError) as exc:
                failures += 1
                self.warnings.append(f"GamerPower {store} unavailable: {type(exc).__name__}: {exc}")
        if failures == 1 + len(GAMERPOWER_PLATFORMS):
            raise RuntimeError("Epic and GamerPower both failed")
        return items
