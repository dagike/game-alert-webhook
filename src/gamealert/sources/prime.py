"""Free games that come with Amazon Prime, read from the Amazon Luna claims page."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from .base import Item

log = logging.getLogger(__name__)

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
REDDIT_URL = "https://www.reddit.com/r/FreeGameFindings/new/.rss?limit=100"
REDDIT_STORES = {"egs": "Epic Games Store", "gog": "GOG", "amazon games": "Amazon Games app"}
REDDIT_TITLE_RE = re.compile(r"^\[PSA\]\s*(.+?)\s+(?:is|are) complimentary with Amazon Prime", re.IGNORECASE)
REDDIT_GAME_RE = re.compile(r"(?:^|,\s*|\s+and\s+)(.+?)\s*\(([^)]+)\)(?=,|\s+and\s|$)")
REDDIT_MAX_AGE = timedelta(days=35)


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


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _item_id(title: str, month: str) -> str:
    """The same game in the same month gets the same ID from Amazon and from Reddit."""
    return f"prime:{_slug(title)}:{month}"


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
                    id=_item_id(assets.get("title", e["id"]), offer["startTime"][:7]),
                    title=assets.get("title", e["id"]),
                    url=link,
                    price="Free with Prime",
                    end_date=offer["endTime"][:10],
                    note=f"{store_name(link)}, via Amazon",
                )
            )
            break
    return items


def _short(exc: Exception) -> str:
    """One short line for the run status box, which cuts long text."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"[:80]


def parse_reddit(feed_text: str, now: datetime) -> list[Item]:
    """Read r/FreeGameFindings posts such as "[PSA] A (EGS), B (GOG) are complimentary with Amazon Prime"."""
    items = []
    for entry in feedparser.parse(feed_text).entries:
        match = REDDIT_TITLE_RE.match(entry.get("title", ""))
        stamp = entry.get("updated_parsed") or entry.get("published_parsed")
        if not match or not stamp:
            continue
        posted = datetime(*stamp[:6], tzinfo=UTC)
        if now - posted > REDDIT_MAX_AGE:
            continue
        for title, store in REDDIT_GAME_RE.findall(match.group(1)):
            store_text = REDDIT_STORES.get(store.strip().lower(), store.strip())
            items.append(
                Item(
                    source="prime",
                    id=_item_id(title, posted.strftime("%Y-%m")),
                    title=title.strip(),
                    url=entry.get("link", ""),
                    price="Free with Prime",
                    note=f"{store_text}, via Reddit, posted {posted.date().isoformat()}",
                )
            )
    return items


class Prime:
    name = "prime"

    def __init__(self, client: httpx.Client | None = None, clock=None):
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
        self.clock = clock or (lambda: datetime.now(UTC))
        self.warnings: list[str] = []

    def _amazon(self) -> list[Item]:
        page = self.client.get(PAGE_URL)
        page.raise_for_status()
        token = parse_csrf(page.text)
        r = self.client.post(
            GRAPHQL_URL,
            json={"query": QUERY},
            headers={"client-id": "CarboniteApp", "csrf-token": token},
        )
        r.raise_for_status()
        return parse_items(r.json(), self.clock())

    def _reddit(self) -> list[Item]:
        r = self.client.get(REDDIT_URL)
        r.raise_for_status()
        return parse_reddit(r.text, self.clock())

    def fetch(self) -> list[Item]:
        """Try Amazon first. Use Reddit when Amazon fails or lists nothing."""
        self.warnings = []
        amazon_error = ""
        try:
            items = self._amazon()
            if items:
                return items
        except Exception as exc:  # noqa: BLE001 - any Amazon failure must fall back to Reddit
            amazon_error = _short(exc)
            log.warning("Amazon Prime source failed, trying Reddit. %s", amazon_error)
        try:
            items = self._reddit()
        except Exception as exc:
            reddit_error = _short(exc)
            if not amazon_error:
                self.warnings.append(f"Amazon listed no Prime games and Reddit failed. {reddit_error}")
                return []
            raise RuntimeError(f"Amazon failed: {amazon_error}. Reddit failed: {reddit_error}") from exc
        if not items:
            self.warnings.append("No Prime free games listed. The page format may have changed.")
        return items
