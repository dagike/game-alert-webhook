import json

import httpx
import respx

from gamealert.discord import build_embeds, send_summary, split_messages
from gamealert.sources.base import Item

URL = "https://discord.test/api/webhooks/1/abc"


def it(i, source="free_games", **kw):
    return Item(source=source, id=str(i), title=f"Game {i}", url=f"https://x/{i}", **kw)


def test_embed_per_non_empty_section():
    embeds = build_embeds({"free_games": [it(1, price="Free", end_date="2026-11-14")], "ps_plus": []})
    assert len(embeds) == 1
    assert "[Game 1](https://x/1)" in embeds[0]["description"]
    assert "Free" in embeds[0]["description"] and "ends 2026-11-14" in embeds[0]["description"]


def test_long_section_splits_and_stays_under_limit():
    embeds = build_embeds({"fanatical": [it(i, "fanatical", note="x" * 200) for i in range(60)]})
    assert len(embeds) > 1
    assert all(len(e["description"]) <= 4096 for e in embeds)
    assert embeds[0]["title"].endswith(f"(1/{len(embeds)})")


def test_split_messages_limits():
    embeds = [{"title": "t", "description": "d" * 3000} for _ in range(5)]
    msgs = split_messages(embeds)
    assert all(sum(len(e["description"]) for e in m) <= 5500 for m in msgs)
    many = [{"title": "t", "description": "d"} for _ in range(25)]
    assert [len(m) for m in split_messages(many)] == [10, 10, 5]


def test_unavailable_embed():
    embeds = build_embeds({"free_games": [it(1)]}, unavailable=["ps_plus"])
    assert embeds[-1]["title"] == "Unavailable this run"
    assert "PlayStation Plus" in embeds[-1]["description"]


@respx.mock
def test_send_summary_posts_json():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    n = send_summary(URL, {"free_games": [it(1)]})
    assert n == 1 and route.call_count == 1
    body = json.loads(route.calls[0].request.content)
    assert body["embeds"][0]["title"] == "Free games"


@respx.mock
def test_empty_summary_respects_flag():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    assert send_summary(URL, {"free_games": []}, post_when_empty=False) == 0
    assert route.call_count == 0
    assert send_summary(URL, {"free_games": []}) == 1
    assert "no new deals" in json.loads(route.calls[0].request.content)["content"]


@respx.mock
def test_retry_after_429(monkeypatch):
    monkeypatch.setattr("gamealert.discord.time.sleep", lambda s: None)
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(429, json={"retry_after": 0.1}), httpx.Response(204)]
    )
    send_summary(URL, {"free_games": [it(1)]})
    assert route.call_count == 2
