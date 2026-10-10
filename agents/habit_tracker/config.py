"""Settings for the habit tracker: secrets from the environment, targets from config.toml."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, SecretStr, model_validator

from agents.habit_tracker.models import SUBJECTS
from core.config import TelegramSettings, load_toml

CONFIG_PATH = Path(__file__).parent / "config.toml"


class HabitSettings(TelegramSettings):
    """No Anthropic key: this agent never calls Claude."""

    habit_sheet_id: str
    habit_form_url: SecretStr  # anyone with the link can submit rows
    # Locally a path to the key file (kept outside the repo); in CI the key's JSON content.
    habit_sa_key_file: str | None = None
    habit_sa_key_json: SecretStr | None = None

    @model_validator(mode="after")
    def _one_key_source(self) -> Self:
        if (self.habit_sa_key_file is None) == (self.habit_sa_key_json is None):
            raise ValueError("set exactly one of HABIT_SA_KEY_FILE or HABIT_SA_KEY_JSON")
        return self


class Targets(BaseModel):
    study_days_per_week: int = Field(ge=0, le=7)
    min_minutes_day_counts: int = Field(ge=1)
    min_minutes_full_day: int = Field(ge=1)
    weekly_study_minutes: int = Field(ge=0)
    gym_sessions_per_week: int = Field(ge=0, le=7)
    sleep_hours_min: float = Field(gt=0)
    sleep_hours_aim: float = Field(gt=0)
    project_minutes_per_week: int = Field(ge=0)
    project_min_sessions: int = Field(ge=0, le=7)
    video_minutes_per_week: int = Field(ge=0)
    subject_minutes_per_week: dict[str, int]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if set(self.subject_minutes_per_week) != set(SUBJECTS):
            raise ValueError(f"subject_minutes_per_week must list exactly: {', '.join(SUBJECTS)}")
        total = sum(self.subject_minutes_per_week.values())
        if total != self.weekly_study_minutes:
            raise ValueError(
                f"subject targets add up to {total}, but weekly_study_minutes is "
                f"{self.weekly_study_minutes}"
            )
        if self.min_minutes_full_day < self.min_minutes_day_counts:
            raise ValueError("min_minutes_full_day must be >= min_minutes_day_counts")
        return self


class HabitConfig(BaseModel):
    timezone: str
    day_starts_at_hour: int = Field(ge=0, le=12)
    trial_start: date
    active_phase: str
    reminder_hour: int = Field(ge=0, le=23)
    weekly_report_hour: int = Field(ge=0, le=23)
    min_n: int = Field(ge=2)
    targets: dict[str, Targets]

    @model_validator(mode="after")
    def _phase_exists(self) -> Self:
        if self.active_phase not in self.targets:
            raise ValueError(f"active_phase {self.active_phase!r} has no [targets.*] block")
        if self.trial_start.weekday() != 0:
            raise ValueError("trial_start must be a Monday (reports run Monday-Sunday)")
        return self

    @property
    def active_targets(self) -> Targets:
        return self.targets[self.active_phase]


def load_config(path: Path = CONFIG_PATH) -> HabitConfig:
    return HabitConfig.model_validate(load_toml(path))
