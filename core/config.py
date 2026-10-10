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


class TelegramSettings(BaseSettings):
    """Secrets every agent needs. Agents that don't call Claude subclass this one."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors otherwise echo the input values, i.e. the other secrets, into
        # (public) CI logs when one variable is missing.
        hide_input_in_errors=True,
    )

    telegram_bot_token: SecretStr
    telegram_chat_id: str


class Settings(TelegramSettings):
    """Secrets for agents that call Claude. Agents subclass this to add their own."""

    anthropic_api_key: SecretStr


def load_toml(path: Path) -> dict[str, Any]:
    """Load a non-secret TOML config file."""
    with path.open("rb") as f:
        return tomllib.load(f)
