import json

import httpx
import respx

from gamealert.config import Settings
from gamealert.discord import build_embeds, send_failure, send_summary, status_embed
from gamealert.report import RunReport, redact
from gamealert.runner import run_once
from gamealert.scheduler import _safe, build_scheduler
from gamealert.sources.base import Item
from gamealert.state import State

URL = "https://discord.com/api/webhooks/123/SECRETTOKEN"
KEY = "itad-secret-key-123"


def item(i=1):
    return Item(source="free_games", id=str(i), title=f"Game {i}")


class Fake:
    def __init__(self, name, items=None, error=None, warnings=None):
        self.name, self.items, self.error = name, items or [], error
        self.warnings = warnings or []

    def fetch(self):
        if self.error:
            raise self.error
        return self.items


def settings(**kw):
    return Settings(discord_webhook_url=URL, itad_api_key=KEY, database_path=":memory:", **kw)


def test_redact_known_secrets_url_key_and_webhook():
    text = f"Client error for url https://api.isthereanydeal.com/x?key={KEY}&country=CA hook {URL}"
    out = redact(text, [KEY, URL])
    assert KEY not in out and "SECRETTOKEN" not in out
    # patterns work even when the secret list is empty
    out = redact(text)
    assert KEY not in out and "SECRETTOKEN" not in out


def test_redact_shortens_long_text():
    assert len(redact("x" * 500)) == 200


def test_status_levels_and_colors():
    ok = RunReport(sources=["a", "b"], new_items=1, duration=2.0)
    assert ok.level == "ok"
    e = status_embed(ok)
    assert e["color"] == 0x2ECC71 and e["description"] == "All 2 sources OK, 1 new item, 2.0 s"

    warn = RunReport(sources=["fanatical"])
    warn.add_warning("fanatical", "format changed")
    assert status_embed(warn)["color"] == 0xF1C40F

    err = RunReport(sources=["fanatical", "ps_plus"])
    err.add_error("fanatical", RuntimeError("boom"))
    e = status_embed(err)
    assert e["color"] == 0xE74C3C
    assert "1 of 2 sources OK" in e["description"]
    assert "Fanatical bundles and sales: error: RuntimeError: boom" in e["description"]


def test_report_when_ok_false_hides_clean_status_only():
    ok = RunReport(sources=["a"])
    assert status_embed(ok, report_when_ok=False) is None
    bad = RunReport(sources=["a"])
    bad.add_warning("a", "w")
    assert status_embed(bad, report_when_ok=False) is not None


def test_many_issues_are_capped():
    r = RunReport(sources=["a"])
    for i in range(20):
        r.add_warning("a", f"w{i}")
    assert status_embed(r)["description"].endswith("and 5 more")


def test_status_embed_is_last():
    r = RunReport(sources=["free_games"])
    embeds = build_embeds({"free_games": [item()]}, r)
    assert [e["title"] for e in embeds] == ["Free games", "Run status"]


@respx.mock
def test_error_text_with_key_never_reaches_discord():
    respx.post(URL).mock(return_value=httpx.Response(204))
    request = httpx.Request("GET", f"https://api.isthereanydeal.com/games/lookup/v1?key={KEY}&title=x")
    exc = httpx.HTTPStatusError("Client error '403' for url " + str(request.url), request=request,
                                response=httpx.Response(403, request=request))
    result = run_once(settings(), sources=[Fake("wishlist", error=exc)], state=State(":memory:"))
    posted = respx.calls.last.request.content.decode()
    assert KEY not in posted and "SECRETTOKEN" not in posted
    assert "HTTPStatusError" in posted
    assert result.report.failed_sources == ["wishlist"]


@respx.mock
def test_warnings_from_sources_reach_the_report():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    sources = [Fake("wishlist", [], warnings=["title not found: Nope"]), Fake("free_games", [item()])]
    run_once(settings(), sources=sources, state=State(":memory:"))
    body = json.loads(route.calls[0].request.content)
    status = body["embeds"][-1]
    assert status["title"] == "Run status" and "title not found: Nope" in status["description"]


@respx.mock
def test_empty_run_with_problem_posts_even_if_post_when_empty_false():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    r = RunReport(sources=["a"])
    r.add_error("a", RuntimeError("down"))
    assert send_summary(URL, {"a": []}, r, post_when_empty=False) == 1
    assert route.call_count == 1


@respx.mock
def test_clean_empty_run_stays_quiet_when_both_flags_off():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    r = RunReport(sources=["a"])
    assert send_summary(URL, {"a": []}, r, post_when_empty=False, report_when_ok=False) == 0
    assert route.call_count == 0


@respx.mock
def test_clean_run_without_status_when_report_when_ok_false():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    run_once(settings(report_when_ok=False), sources=[Fake("free_games", [item()])], state=State(":memory:"))
    titles = [e["title"] for e in json.loads(route.calls[0].request.content)["embeds"]]
    assert titles == ["Free games"]


@respx.mock
def test_send_failure_is_red_and_redacted():
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    send_failure(URL, RuntimeError(f"cannot open {KEY}"), [KEY])
    embed = json.loads(route.calls[0].request.content)["embeds"][0]
    assert embed["title"] == "Run failed" and embed["color"] == 0xE74C3C
    assert KEY not in embed["description"]


@respx.mock
def test_scheduler_posts_failure_notice_and_keeps_running():
    route = respx.post(URL).mock(return_value=httpx.Response(204))

    def boom():
        raise RuntimeError("database locked")

    s = build_scheduler(settings(), job=boom)
    job_func = s._pending_jobs[0][0].func
    job_func()  # must not raise
    assert "Run failed" in route.calls[0].request.content.decode()


def test_failure_notice_that_fails_is_only_logged(caplog):
    def bad_notice(exc):
        raise OSError("discord down")

    _safe(lambda: 1 / 0, bad_notice)()
    assert "Could not report the failure" in caplog.text


def test_log_filter_hides_secrets_in_message_and_traceback(capsys):
    import logging

    from gamealert.__main__ import SecretFilter

    handler = logging.StreamHandler()
    handler.addFilter(SecretFilter([KEY, URL]))
    logger = logging.getLogger("secret-test")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        raise RuntimeError(f"failed for ?key={KEY} and {URL}")
    except RuntimeError:
        logger.exception("Request https://x/y?key=%s broke", KEY)
    err = capsys.readouterr().err
    assert "Traceback" in err and "RuntimeError" in err
    assert KEY not in err and "SECRETTOKEN" not in err
