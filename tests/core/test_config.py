from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings, load_toml


def _settings() -> Settings:
    # _env_file=None: tests must never read a developer's real .env.
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-456")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    settings = _settings()

    assert settings.anthropic_api_key.get_secret_value() == "sk-test-123"
    assert settings.telegram_chat_id == "42"


def test_secrets_are_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-456")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    text = repr(_settings())

    assert "sk-test-123" not in text
    assert "bot-token-456" not in text


def test_missing_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        _settings()


def test_load_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('model = "claude-haiku-4-5"\nmax_items = 50\n', encoding="utf-8")

    assert load_toml(path) == {"model": "claude-haiku-4-5", "max_items": 50}
