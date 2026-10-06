"""Configuration.

Two sources, kept apart on purpose:
- Secrets come only from environment variables (or a gitignored `.env` locally).
- Non-secret settings (model id, limits, labels) live in a committed TOML file per agent.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets shared by every agent. Agents subclass this to add their own."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr
    telegram_bot_token: SecretStr
    telegram_chat_id: str


def load_toml(path: Path) -> dict[str, Any]:
    """Load a non-secret TOML config file."""
    with path.open("rb") as f:
        return tomllib.load(f)
