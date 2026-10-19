"""Test doubles for the job scout. No network, no cost, fake data only."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from agents.job_scout.config import (
    AdzunaConfig,
    ArbeitnowConfig,
    Filters,
    JobScoutConfig,
)
from agents.job_scout.models import Posting, Score

NOW = datetime(2026, 10, 19, 6, 30, tzinfo=UTC)

FILTERS = Filters(
    salary_floor_eur=68000,
    title_include=["backend", "java", "software engineer", "sre"],
    title_exclude=["junior", "lead", "staff", "manager", "frontend"],
    onsite_locations=["berlin"],
    remote_exclude_locations=["us", "usa", "uk"],
)

CONFIG = JobScoutConfig(
    model="claude-haiku-4-5",
    max_tokens=200,
    max_calls=10,
    description_chars=2000,
    min_score=60,
    max_matches=3,
    seen_retention_days=60,
    filters=FILTERS,
    arbeitnow=ArbeitnowConfig(max_pages=2),
    adzuna=AdzunaConfig(
        country="de",
        what_or="backend java",
        where="Berlin",
        max_pages=2,
        results_per_page=2,
        max_days_old=7,
    ),
)


def make_posting(
    title: str = "Backend Engineer (Java)",
    company: str = "Acme GmbH",
    location: str = "Berlin",
    remote: bool | None = None,
    source: str = "greenhouse:acme",
    external_id: str = "1",
    salary_max_eur: int | None = None,
    posted_at: datetime | None = NOW,
    description: str = "Build Spring Boot services. English-speaking team.",
) -> Posting:
    return Posting(
        source=source,
        external_id=external_id,
        company=company,
        title=title,
        location=location,
        remote=remote,
        url=f"https://jobs.example.com/{external_id}",
        description=description,
        posted_at=posted_at,
        salary_max_eur=salary_max_eur,
    )


class FakeLLM:
    """Returns queued scores (or raises queued errors) and records each prompt."""

    def __init__(self, responses: list[Score | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def parse[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return schema.model_validate(response.model_dump())


class FakeSource:
    def __init__(self, name: str, postings: list[Posting] | Exception) -> None:
        self.name = name
        self._postings = postings

    def fetch(self) -> list[Posting]:
        if isinstance(self._postings, Exception):
            raise self._postings
        return list(self._postings)
