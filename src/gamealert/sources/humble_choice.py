"""The current Humble Choice month and its games, read from humblebundle.com/membership."""

from __future__ import annotations

import json
import re

import httpx

from .base import Item

SITE = "https://www.humblebundle.com"
MEMBERSHIP_URL = f"{SITE}/membership"
SUFFIX = " Humble Choice"


def _block(html: str, script_id: str) -> dict:
    """Return the JSON in <script id=script_id>. Raise ValueError if the block is missing."""
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    if not match:
        raise ValueError(f"Humble Bundle page has no {script_id} block")
    return json.loads(match.group(1))


def choice_slug(machine_name: str) -> str:
    """november_2026_choice -> november-2026"""
    return machine_name.removesuffix("_choice").replace("_", "-")


def parse_membership(html: str) -> dict:
    """Return machine_name, title, end_date and price for the active Choice month."""
    data = _block(html, "webpack-choice-marketing-data")
    machine_name = data.get("activeContentMachineName")
    if not machine_name:
        raise ValueError("Humble Choice page has no activeContentMachineName")
    nav = data.get("navbarOptions") or {}
    human = nav.get("productHumanName") or choice_slug(machine_name).replace("-", " ").title()
    month = human.removesuffix(SUFFIX)
    money = data.get("baseSubscriptionPrice|money") or {}
    price = f"${money['amount']:.2f} {money['currency']} per month" if money else ""
    return {
        "machine_name": machine_name,
        "title": f"Humble Choice: {month}",
        "end_date": (nav.get("activeContentEndDate|datetime") or "")[:10],
        "price": price,
    }


def parse_month(html: str) -> list[dict]:
    """Return the games (title, image) of one Choice month, in display order."""
    data = _block(html, "webpack-monthly-product-data")
    choice = (data.get("contentChoiceOptions") or {}).get("contentChoiceData") or {}
    games = choice.get("game_data") or {}
    result = []
    for game_id in choice.get("display_order") or []:
        # Skip entries that are not games, for example an IGN Plus coupon.
        if "coupon" in game_id or game_id not in games:
            continue
        game = games[game_id]
        result.append({"title": game.get("title", game_id), "image": game.get("image", "")})
    return result


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
        info = parse_membership(r.text)
        url = f"{MEMBERSHIP_URL}/{choice_slug(info['machine_name'])}"
        r = self.client.get(url)
        if r.status_code == 404:
            self.warnings.append(f"Humble Choice page not found for {info['title']}")
            return []
        r.raise_for_status()
        games = parse_month(r.text)
        if not games:
            self.warnings.append(f"No games listed yet for {info['title']}")
            return []
        return [
            Item(
                source="humble_choice",
                id=f"choice:{info['machine_name']}",
                title=info["title"],
                url=url,
                price=info["price"],
                end_date=info["end_date"],
                image=games[0]["image"],
                note=", ".join(g["title"] for g in games),
            )
        ]
