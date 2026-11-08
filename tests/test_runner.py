import json

import httpx
import respx

from gamealert.config import Settings
from gamealert.runner import render_text, run_once
from gamealert.sources.base import Item
from gamealert.state import State

URL = "https://discord.test/api/webhooks/1/abc"


class Fake:
    def __init__(self, name, items=None, error=None):
        self.name, self.items, self.error = name, items or [], error

    def fetch(self):
        if self.error:
            raise self.error
        return self.items


def it(i, source="free_games"):
    return Item(source=source, id=str(i), title=f"Game {i}")


def settings(**kw):
    return Settings(discord_webhook_url=URL, database_path=":memory:", **kw)


@respx.mock
def test_posts_new_items_and_dedupes_on_second_run():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    state = State(":memory:")
    sources = [Fake("free_games", [it(1)]), Fake("ps_plus", [it(2, "ps_plus")])]
    first = run_once(settings(), sources=sources, state=state)
    assert first.new_count == 2 and route.call_count == 1
    second = run_once(settings(post_when_empty=False), sources=sources, state=state)
    assert second.new_count == 0 and route.call_count == 1  # nothing posted


@respx.mock
def test_failed_source_does_not_stop_others():
    respx.post(URL).mock(return_value=httpx.Response(204))
    sources = [Fake("fanatical", error=RuntimeError("boom")), Fake("free_games", [it(1)])]
    result = run_once(settings(), sources=sources, state=State(":memory:"))
    assert result.report.failed_sources == ["fanatical"]
    assert [i.id for i in result.sections["free_games"]] == ["1"]


@respx.mock
def test_items_not_marked_sent_when_discord_fails():
    respx.post(URL).mock(return_value=httpx.Response(500))
    state = State(":memory:")
    try:
        run_once(settings(), sources=[Fake("free_games", [it(1)])], state=state)
    except httpx.HTTPStatusError:
        pass
    assert not state.is_sent(it(1))


@respx.mock
def test_dry_run_posts_nothing_and_saves_nothing(capsys):
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    state = State(":memory:")
    run_once(settings(), dry_run=True, sources=[Fake("free_games", [it(1)])], state=state)
    assert route.call_count == 0 and not state.is_sent(it(1))
    assert "Game 1" in capsys.readouterr().out


def test_render_text_empty():
    assert render_text({"free_games": []}) == "No new deals.\n"


@respx.mock
def test_post_payload_has_summary_embed():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    run_once(settings(), sources=[Fake("free_games", [it(1)])], state=State(":memory:"))
    assert json.loads(route.calls[0].request.content)["embeds"][0]["title"] == "Free games"
