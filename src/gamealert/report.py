"""Collect problems during one run, so the summary can show them at the end."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_MESSAGE = 200

# Patterns that must never reach Discord or the logs of a public repo.
_PATTERNS = [
    re.compile(r"([?&]key=)[^&\s\"'>]+", re.IGNORECASE),
    re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", re.IGNORECASE),
]


def scrub(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    """Remove known secrets, URL keys, and webhook URLs from text. Keep the layout."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    text = _PATTERNS[0].sub(r"\1***", text)
    return _PATTERNS[1].sub("***", text)


def redact(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    """Scrub text, join it into one line, and shorten it for a Discord message."""
    text = " ".join(scrub(text, secrets).split())
    if len(text) > MAX_MESSAGE:
        text = text[: MAX_MESSAGE - 3] + "..."
    return text


@dataclass(frozen=True)
class Issue:
    source: str
    level: str  # "error" (the source failed) or "warning" (it worked, with problems)
    message: str


@dataclass
class RunReport:
    sources: list[str] = field(default_factory=list)  # names of all sources that ran
    issues: list[Issue] = field(default_factory=list)
    new_items: int = 0
    duration: float = 0.0
    secrets: list[str] = field(default_factory=list)

    def add_error(self, source: str, exc: BaseException) -> None:
        self.issues.append(Issue(source, "error", redact(f"{type(exc).__name__}: {exc}", self.secrets)))

    def add_warning(self, source: str, message: str) -> None:
        self.issues.append(Issue(source, "warning", redact(message, self.secrets)))

    @property
    def failed_sources(self) -> list[str]:
        return sorted({i.source for i in self.issues if i.level == "error"})

    @property
    def level(self) -> str:
        if self.failed_sources:
            return "error"
        return "warning" if self.issues else "ok"
