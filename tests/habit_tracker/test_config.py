from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from agents.habit_tracker.config import HabitConfig, HabitSettings, Targets, load_config
from tests.habit_tracker.fakes import CONFIG, TARGETS


def test_shipped_config_is_valid() -> None:
    config = load_config()
    assert config.active_targets.weekly_study_minutes > 0


def _targets(**overrides: Any) -> dict[str, Any]:
    return {**TARGETS.model_dump(), **overrides}


def test_subject_targets_must_add_up_to_weekly_total() -> None:
    with pytest.raises(ValidationError, match="add up to"):
        Targets.model_validate(_targets(weekly_study_minutes=450))


def test_subject_targets_must_list_every_subject() -> None:
    with pytest.raises(ValidationError, match="exactly"):
        Targets.model_validate(
            _targets(subject_minutes_per_week={"golang": 400}, weekly_study_minutes=400)
        )


def test_active_phase_must_exist() -> None:
    with pytest.raises(ValidationError, match="active_phase"):
        HabitConfig.model_validate({**CONFIG.model_dump(), "active_phase": "phase9"})


def test_trial_must_start_on_a_monday() -> None:
    with pytest.raises(ValidationError, match="Monday"):
        HabitConfig.model_validate({**CONFIG.model_dump(), "trial_start": date(2030, 1, 8)})


def _settings_env(monkeypatch: pytest.MonkeyPatch, **keys: str) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("HABIT_SHEET_ID", "sheet-id")
    monkeypatch.setenv("HABIT_FORM_URL", "https://forms.example/secret")
    for name in ("HABIT_SA_KEY_FILE", "HABIT_SA_KEY_JSON"):
        monkeypatch.delenv(name, raising=False)
    for name, value in keys.items():
        monkeypatch.setenv(name, value)


def test_settings_need_no_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _settings_env(monkeypatch, HABIT_SA_KEY_FILE="key.json")
    settings = HabitSettings(_env_file=None)  # type: ignore[call-arg]
    assert "secret" not in repr(settings)


@pytest.mark.parametrize("keys", [{}, {"HABIT_SA_KEY_FILE": "k", "HABIT_SA_KEY_JSON": "{}"}])
def test_settings_need_exactly_one_key_source(
    monkeypatch: pytest.MonkeyPatch, keys: dict[str, str]
) -> None:
    _settings_env(monkeypatch, **keys)
    with pytest.raises(ValidationError, match="exactly one"):
        HabitSettings(_env_file=None)  # type: ignore[call-arg]
