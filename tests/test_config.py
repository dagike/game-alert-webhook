import pytest

from gamealert.config import Settings, load_settings, load_wishlist


def test_defaults_when_no_files(tmp_path):
    s = load_settings(tmp_path / "none.yaml", tmp_path / "none.env")
    assert s.run_times == ["09:00", "21:00"]
    assert s.country == "CA"
    assert s.parsed_run_times() == [(9, 0), (21, 0)]


def test_yaml_and_env_merge(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    (tmp_path / "c.yaml").write_text("run_times: ['07:30']\nsources:\n  ps_plus: false\n")
    (tmp_path / "e.env").write_text("DISCORD_WEBHOOK_URL=https://x/y\nITAD_API_KEY=k\n")
    s = load_settings(tmp_path / "c.yaml", tmp_path / "e.env")
    assert s.parsed_run_times() == [(7, 30)]
    assert s.sources.ps_plus is False and s.sources.free_games is True
    assert s.discord_webhook_url == "https://x/y" and s.itad_api_key == "k"


@pytest.mark.parametrize("bad", ["9", "25:00", "09:60", "ab:cd"])
def test_bad_run_time(bad):
    with pytest.raises(ValueError):
        Settings(run_times=[bad]).parsed_run_times()


def test_wishlist(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("games:\n  - Hades\n  - ' Celeste '\n  - ''\n")
    assert load_wishlist(f) == ["Hades", "Celeste"]
    assert load_wishlist(tmp_path / "missing.yaml") == []


def test_wishlist_file_found_next_to_config(tmp_path):
    (tmp_path / "config.yaml").write_text("timezone: UTC\n")
    (tmp_path / "wishlist.yaml").write_text("games: [Hades]\n")
    s = load_settings(tmp_path / "config.yaml", tmp_path / "none.env")
    assert load_wishlist(s.wishlist_file) == ["Hades"]
