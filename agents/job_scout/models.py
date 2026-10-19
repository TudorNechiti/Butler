from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Posting:
    """One job ad from any source, already sanitised: plain text, bounded length.

    Everything except `source` comes from a third party and is untrusted.
    """

    source: str  # "arbeitnow", "adzuna", "greenhouse:n26", ...
    external_id: str
    company: str
    title: str
    location: str
    remote: bool | None  # None: the source doesn't say
    url: str  # https only, or "" when the source gave nothing usable
    description: str
    posted_at: datetime | None
    # Yearly, in EUR. Only set when the source states it explicitly (never an estimate).
    salary_max_eur: int | None = None


class Score(BaseModel):
    """What Claude returns (structured output). The scorer clamps and trims it."""

    score: int = Field(description="Fit from 0 (no fit) to 100 (excellent fit).")
    reason: str = Field(
        description="At most 20 words, in English. Do not quote the ad or include links."
    )


@dataclass(frozen=True)
class Match:
    posting: Posting
    score: Score


@dataclass
class JobDigest:
    """Result of one run. A later shared morning brief can consume this as-is."""

    matches: list[Match] = field(default_factory=list)
    fetched: int = 0
    candidates: int = 0  # after the code filters
    new: int = 0  # after dedupe and the seen check
    scored: int = 0
    failed_sources: list[str] = field(default_factory=list)
