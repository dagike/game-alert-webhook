"""Run all enabled sources once, drop items already sent, and post the summary."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Settings, load_wishlist
from .discord import build_embeds, send_summary
from .sources.base import Item, Source
from .sources.fanatical import Fanatical
from .sources.freegames import FreeGames
from .sources.psplus import PsPlus
from .sources.wishlist import Wishlist
from .state import State

log = logging.getLogger("gamealert")


@dataclass
class RunResult:
    sections: dict[str, list[Item]] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)
    messages_sent: int = 0

    @property
    def new_count(self) -> int:
        return sum(len(v) for v in self.sections.values())


def build_sources(settings: Settings) -> list[Source]:
    enabled = settings.sources
    sources: list[Source] = []
    if enabled.free_games:
        sources.append(FreeGames(settings.country))
    if enabled.ps_plus:
        sources.append(PsPlus())
    if enabled.fanatical:
        sources.append(Fanatical(settings.currency))
    if enabled.wishlist:
        sources.append(
            Wishlist(
                load_wishlist(settings.wishlist_file),
                settings.itad_api_key,
                settings.country,
                settings.wishlist_tolerance_percent,
            )
        )
    return sources


def render_text(sections: dict[str, list[Item]], unavailable: list[str]) -> str:
    """Plain text version of the summary, used by --dry-run."""
    lines = []
    for embed in build_embeds(sections, unavailable):
        lines.append(f"== {embed['title']}")
        lines.append(embed["description"])
        lines.append("")
    return "\n".join(lines) if lines else "No new deals.\n"


def run_once(
    settings: Settings,
    dry_run: bool = False,
    sources: list[Source] | None = None,
    state: State | None = None,
) -> RunResult:
    sources = build_sources(settings) if sources is None else sources
    own_state = state is None
    state = state or State(settings.database_path)
    result = RunResult()
    try:
        for source in sources:
            try:
                items = source.fetch()
            except Exception:  # one broken source must not stop the others
                log.exception("Source %s failed", source.name)
                result.unavailable.append(source.name)
                continue
            result.sections[source.name] = state.filter_new(items)

        if dry_run:
            print(render_text(result.sections, result.unavailable))
            return result

        if not settings.discord_webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL is not set")
        result.messages_sent = send_summary(
            settings.discord_webhook_url,
            result.sections,
            result.unavailable,
            post_when_empty=settings.post_when_empty,
        )
        # Mark items as sent only after Discord accepted the message.
        state.mark_sent([i for items in result.sections.values() for i in items])
        return result
    finally:
        if own_state:
            state.close()
