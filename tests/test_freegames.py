import json
from pathlib import Path

import httpx
import respx

from gamealert.sources.freegames import (
    EPIC_URL,
    GAMERPOWER_URL,
    FreeGames,
    parse_epic,
    parse_gamerpower,
)

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


def test_epic_only_truly_free_games():
    items = parse_epic(load("epic.json"))
    assert [i.title for i in items] == ["Flotsam"]  # LISA is 60% off, Idle Champions is always free
    flotsam = items[0]
    assert flotsam.end_date == "2026-11-12"
    assert flotsam.url == "https://store.epicgames.com/en-US/p/flotsam-266287"
    assert "CA$27.99" in flotsam.price
    assert flotsam.id.startswith("epic:") and flotsam.id.endswith("2026-11-12T16:00:00.000Z")


def test_gamerpower_active_games():
    items = parse_gamerpower(load("gamerpower_steam.json"), "Steam")
    assert items and all(i.note == "Steam" and i.id.startswith("gamerpower:") for i in items)


def test_gamerpower_empty_response():
    assert parse_gamerpower({"status": 0, "status_message": "none"}, "GOG") == []


@respx.mock
def test_fetch_combines_sources_and_tolerates_gog_201():
    respx.get(EPIC_URL).mock(return_value=httpx.Response(200, json=load("epic.json")))

    def gp(request):
        if request.url.params["platform"] == "steam":
            return httpx.Response(200, json=load("gamerpower_steam.json"))
        return httpx.Response(201, json={"status": 0})

    respx.get(GAMERPOWER_URL).mock(side_effect=gp)
    items = FreeGames().fetch()
    assert {i.note for i in items} == {"Epic Games Store", "Steam"}


@respx.mock
def test_epic_failure_is_a_warning_when_gamerpower_works():
    respx.get(EPIC_URL).mock(return_value=httpx.Response(500))
    respx.get(GAMERPOWER_URL).mock(
        side_effect=lambda r: httpx.Response(200, json=load("gamerpower_steam.json"))
        if r.url.params["platform"] == "steam"
        else httpx.Response(201, json={"status": 0})
    )
    source = FreeGames()
    items = source.fetch()
    assert items and all(i.note == "Steam" for i in items)
    assert len(source.warnings) == 1 and "Epic" in source.warnings[0]  # GOG 201 is not a warning


@respx.mock
def test_all_free_game_sources_failing_raises():
    import pytest

    respx.get(EPIC_URL).mock(return_value=httpx.Response(500))
    respx.get(GAMERPOWER_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        FreeGames().fetch()
