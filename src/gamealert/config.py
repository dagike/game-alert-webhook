"""Load settings from environment variables (.env) and an optional config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    """Secrets. They come from the environment or from a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_webhook_url: str = ""
    itad_api_key: str = ""


class Sources(BaseModel):
    free_games: bool = True
    ps_plus: bool = True
    fanatical: bool = True
    humble: bool = True
    wishlist: bool = True


class Settings(BaseModel):
    timezone: str = "America/Toronto"
    run_times: list[str] = Field(default_factory=lambda: ["09:00", "13:05"])
    country: str = "CA"
    currency: str = "CAD"
    post_when_empty: bool = False
    report_when_ok: bool = True
    wishlist_tolerance_percent: float = 0.0
    wishlist_file: str = "wishlist.yaml"
    database_path: str = "data/state.db"
    sources: Sources = Field(default_factory=Sources)
    discord_webhook_url: str = ""
    itad_api_key: str = ""

    def parsed_run_times(self) -> list[tuple[int, int]]:
        """Return run_times as (hour, minute) pairs. Raise ValueError on a bad value."""
        result = []
        for value in self.run_times:
            hour, sep, minute = value.partition(":")
            if not sep or not hour.isdigit() or not minute.isdigit():
                raise ValueError(f"Invalid run time {value!r}. Use HH:MM.")
            h, m = int(hour), int(minute)
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError(f"Invalid run time {value!r}. Use HH:MM.")
            result.append((h, m))
        return result


def load_settings(config_path: str | Path = "config.yaml", env_file: str | Path = ".env") -> Settings:
    """Merge config.yaml (if it exists) with secrets from the environment."""
    data: dict = {}
    path = Path(config_path)
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        # A relative wishlist_file is read from the folder that holds config.yaml.
        wishlist = Path(data.get("wishlist_file", "wishlist.yaml"))
        if not wishlist.is_absolute() and (path.parent / wishlist).exists():
            data["wishlist_file"] = str(path.parent / wishlist)
    env = Env(_env_file=env_file)
    data["discord_webhook_url"] = env.discord_webhook_url
    data["itad_api_key"] = env.itad_api_key
    return Settings(**data)


def load_wishlist(path: str | Path) -> list[str]:
    """Read game titles from wishlist.yaml. The file holds a `games:` list."""
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return [str(title).strip() for title in data.get("games", []) if str(title).strip()]
