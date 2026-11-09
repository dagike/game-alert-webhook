"""Build Discord embeds from items and post them to a webhook."""

from __future__ import annotations

import time

import httpx

from .report import RunReport, redact
from .sources.base import Item

TITLES = {
    "free_games": "Free games",
    "ps_plus": "PlayStation Plus Essential",
    "fanatical": "Fanatical bundles and sales",
    "humble": "Humble Bundle games",
    "wishlist": "Wishlist all-time lows",
}
COLORS = {
    "free_games": 0x2ECC71,
    "ps_plus": 0x0070D1,
    "fanatical": 0xF39C12,
    "humble": 0xCC2929,
    "wishlist": 0xE74C3C,
}
DESC_LIMIT = 3800  # Discord allows 4096 per embed description
MESSAGE_LIMIT = 5500  # Discord allows 6000 characters across all embeds in a message
MAX_EMBEDS = 10
STATUS_COLORS = {"ok": 0x2ECC71, "warning": 0xF1C40F, "error": 0xE74C3C}
MAX_STATUS_LINES = 15


def format_item(item: Item) -> str:
    title = f"[{item.title}]({item.url})" if item.url else item.title
    parts = [title]
    if item.note:
        parts.append(item.note)
    if item.price:
        parts.append(item.price)
    if item.end_date:
        parts.append(f"ends {item.end_date}")
    return "• " + " | ".join(parts)


def status_embed(report: RunReport, report_when_ok: bool = True) -> dict | None:
    """The "Run status" embed. Return None for a clean run when report_when_ok is false."""
    if report.level == "ok" and not report_when_ok:
        return None
    total = len(report.sources)
    failed = len(report.failed_sources)
    items = f"{report.new_items} new item{'' if report.new_items == 1 else 's'}"
    took = f"{report.duration:.1f} s"
    if report.level == "ok":
        summary = f"All {total} sources OK, {items}, {took}"
    else:
        summary = f"{total - failed} of {total} sources OK, {items}, {took}"
    lines = [
        f"{TITLES.get(i.source, i.source)}: {i.level}: {i.message}"
        for i in report.issues[:MAX_STATUS_LINES]
    ]
    if len(report.issues) > MAX_STATUS_LINES:
        lines.append(f"and {len(report.issues) - MAX_STATUS_LINES} more")
    return {
        "title": "Run status",
        "description": "\n".join([summary, *lines]),
        "color": STATUS_COLORS[report.level],
    }


def build_embeds(
    sections: dict[str, list[Item]], report: RunReport | None = None, report_when_ok: bool = True
) -> list[dict]:
    """One embed per non-empty section, then the run status. A long section becomes several embeds."""
    embeds: list[dict] = []
    for source, items in sections.items():
        if not items:
            continue
        title = TITLES.get(source, source)
        chunk: list[str] = []
        size = 0
        pages: list[list[str]] = []
        for item in items:
            line = format_item(item)[:500]
            if chunk and size + len(line) + 1 > DESC_LIMIT:
                pages.append(chunk)
                chunk, size = [], 0
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            pages.append(chunk)
        for n, page in enumerate(pages, 1):
            suffix = f" ({n}/{len(pages)})" if len(pages) > 1 else ""
            embeds.append(
                {
                    "title": f"{title}{suffix}",
                    "description": "\n".join(page),
                    "color": COLORS.get(source, 0x95A5A6),
                }
            )
    status = status_embed(report, report_when_ok) if report else None
    if status:
        embeds.append(status)
    return embeds


def _embed_size(embed: dict) -> int:
    return len(embed.get("title", "")) + len(embed.get("description", ""))


def split_messages(embeds: list[dict]) -> list[list[dict]]:
    """Group embeds so each message stays inside Discord limits."""
    messages: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for embed in embeds:
        s = _embed_size(embed)
        if current and (len(current) >= MAX_EMBEDS or size + s > MESSAGE_LIMIT):
            messages.append(current)
            current, size = [], 0
        current.append(embed)
        size += s
    if current:
        messages.append(current)
    return messages


def post(webhook_url: str, content: str, embeds: list[dict], client: httpx.Client | None = None) -> None:
    """Post one message. Retry once if Discord rate limits the request (HTTP 429)."""
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        payload = {"content": content, "embeds": embeds, "username": "Game Alerts"}
        for attempt in range(2):
            r = client.post(webhook_url, json=payload)
            if r.status_code == 429 and attempt == 0:
                time.sleep(min(float(r.json().get("retry_after", 1)), 10))
                continue
            r.raise_for_status()
            return
    finally:
        if own:
            client.close()


def send_summary(
    webhook_url: str,
    sections: dict[str, list[Item]],
    report: RunReport | None = None,
    header: str = "Game deals summary",
    post_when_empty: bool = True,
    report_when_ok: bool = True,
) -> int:
    """Post the summary. Return the number of messages sent."""
    embeds = build_embeds(sections, report, report_when_ok)
    has_items = any(sections.values())
    has_issues = bool(report and report.issues)
    if not has_items:
        # Problems are never hidden: post even when post_when_empty is false.
        if not post_when_empty and not has_issues:
            return 0
        post(webhook_url, f"{header}: no new deals this time.", embeds)
        return 1
    messages = split_messages(embeds)
    for i, group in enumerate(messages):
        post(webhook_url, header if i == 0 else "", group)
    return len(messages)


def send_failure(webhook_url: str, exc: BaseException, secrets: list[str] | tuple[str, ...] = ()) -> None:
    """Post a short red message when a whole run failed outside the sources."""
    message = redact(f"{type(exc).__name__}: {exc}", secrets)
    embed = {"title": "Run failed", "description": message, "color": STATUS_COLORS["error"]}
    post(webhook_url, "Game deals summary: the run failed.", [embed])
