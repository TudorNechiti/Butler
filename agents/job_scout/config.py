"""Settings for the job scout: secrets from the environment, everything else from config.toml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, SecretStr, model_validator

from core.config import Settings, load_toml

CONFIG_PATH = Path(__file__).parent / "config.toml"

type HiringSystem = Literal["greenhouse", "lever", "ashby", "personio"]


class JobScoutSettings(Settings):
    # Free text about me (experience, languages, salary, wishes). Personal, so never in git.
    job_profile: SecretStr
    # Optional: without these the Adzuna source is skipped.
    adzuna_app_id: str | None = None
    adzuna_app_key: SecretStr | None = None

    @model_validator(mode="after")
    def _adzuna_pair(self) -> Self:
        if (self.adzuna_app_id is None) != (self.adzuna_app_key is None):
            raise ValueError("set both ADZUNA_APP_ID and ADZUNA_APP_KEY, or neither")
        return self


class Filters(BaseModel):
    """Hard filters applied in code before anything reaches Claude. Matching is per whole word."""

    salary_floor_eur: int = Field(ge=0)
    title_include: list[str] = Field(min_length=1)
    title_exclude: list[str]
    onsite_locations: list[str] = Field(min_length=1)
    remote_exclude_locations: list[str]


class ArbeitnowConfig(BaseModel):
    max_pages: int = Field(ge=1, le=10)


class AdzunaConfig(BaseModel):
    country: str
    what_or: str
    where: str
    max_pages: int = Field(ge=1, le=5)
    results_per_page: int = Field(ge=1, le=50)
    max_days_old: int = Field(ge=1)


class Company(BaseModel):
    name: str
    system: HiringSystem
    slug: str = Field(pattern=r"^[a-z0-9-]+$")  # goes into a URL, so keep it boring


class JobScoutConfig(BaseModel):
    model: str
    max_tokens: int = Field(ge=64)
    max_calls: int = Field(ge=1)
    description_chars: int = Field(ge=200)
    min_score: int = Field(ge=0, le=100)
    max_matches: int = Field(ge=1)
    seen_retention_days: int = Field(ge=1)
    filters: Filters
    arbeitnow: ArbeitnowConfig
    adzuna: AdzunaConfig
    companies: list[Company] = Field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> JobScoutConfig:
    return JobScoutConfig.model_validate(load_toml(path))
