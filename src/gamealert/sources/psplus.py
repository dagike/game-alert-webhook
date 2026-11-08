"""New PlayStation Plus monthly games, read from the PlayStation Blog tag feed."""

from __future__ import annotations

import re

import feedparser
import httpx

from .base import Item

FEED_URL = "https://blog.playstation.com/tag/playstation-plus/feed/"
TITLE_RE = re.compile(r"PlayStation Plus Monthly Games for (\w+)\s*[:–—-]\s*(.+)", re.IGNORECASE)
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')


def parse_feed(text: str) -> list[Item]:
    items = []
    for entry in feedparser.parse(text).entries:
        match = TITLE_RE.search(entry.get("title", ""))
        if not match:
            continue
        month, games = match.group(1), match.group(2).strip()
        html = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
        image = IMG_RE.search(html)
        items.append(
            Item(
                source="ps_plus",
                id=entry.get("id") or entry.link,
                title=f"PS Plus Essential: {month} games",
                url=entry.link,
                note=games,
                end_date="",
                image=image.group(1) if image else "",
            )
        )
    return items


class PsPlus:
    name = "ps_plus"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "game-alert-webhook"})

    def fetch(self) -> list[Item]:
        r = self.client.get(FEED_URL)
        r.raise_for_status()
        return parse_feed(r.text)[:1]  # only the newest monthly post counts as new
