"""Shared item model for all sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Item:
    """One deal or announcement. (source, id) must be stable between runs."""

    source: str  # "free_games", "ps_plus", "fanatical", "wishlist"
    id: str
    title: str
    url: str = ""
    price: str = ""  # display text, for example "$4.99 CAD (was $19.99)"
    end_date: str = ""  # ISO date or free text
    image: str = ""
    note: str = ""  # short extra line, for example the store name


class Source(Protocol):
    name: str

    def fetch(self) -> list[Item]: ...
