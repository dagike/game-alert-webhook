"""Read the data that humblebundle.com embeds in its pages (Next.js flight stream)."""

from __future__ import annotations

import json
import re

PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.DOTALL)
_DECODER = json.JSONDecoder()


def flight_text(html: str) -> str:
    """Join the text chunks that the page sends to its own scripts."""
    return "".join(json.loads(chunk) for chunk in PUSH_RE.findall(html))


def json_list(text: str, key: str) -> list[dict] | None:
    """Return the first JSON list that follows "key": in the text, or None."""
    match = re.search(rf'"{re.escape(key)}":\[', text)
    if not match:
        return None
    value, _ = _DECODER.raw_decode(text[match.end() - 1 :])
    return value
