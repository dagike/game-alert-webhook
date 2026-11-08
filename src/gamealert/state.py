"""SQLite store of items that the bot already sent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .sources.base import Item


class State:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sent ("
            "source TEXT NOT NULL, id TEXT NOT NULL, "
            "sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (source, id))"
        )
        self.db.commit()

    def is_sent(self, item: Item) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sent WHERE source = ? AND id = ?", (item.source, item.id)
        ).fetchone()
        return row is not None

    def filter_new(self, items: list[Item]) -> list[Item]:
        """Return items not yet sent. Duplicates inside one list count once."""
        seen: set[tuple[str, str]] = set()
        new = []
        for item in items:
            key = (item.source, item.id)
            if key in seen or self.is_sent(item):
                continue
            seen.add(key)
            new.append(item)
        return new

    def mark_sent(self, items: list[Item]) -> None:
        self.db.executemany(
            "INSERT OR IGNORE INTO sent (source, id) VALUES (?, ?)",
            [(i.source, i.id) for i in items],
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
