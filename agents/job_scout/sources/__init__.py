"""Job sources. Each one turns a public API or feed into the same Posting model.

Adding a company is one entry in config.toml; adding a hiring system is one module here.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from agents.job_scout.config import HiringSystem, JobScoutConfig, JobScoutSettings
from agents.job_scout.sources.adzuna import Adzuna
from agents.job_scout.sources.arbeitnow import Arbeitnow
from agents.job_scout.sources.ashby import Ashby
from agents.job_scout.sources.base import Source, SourceError, new_http_client
from agents.job_scout.sources.greenhouse import Greenhouse
from agents.job_scout.sources.lever import Lever
from agents.job_scout.sources.personio import Personio

__all__ = ["Source", "SourceError", "build_sources", "new_http_client"]

type BoardFactory = Callable[[httpx.Client, str, str, int], Source]

_BOARDS: dict[HiringSystem, BoardFactory] = {
    "greenhouse": Greenhouse,
    "lever": Lever,
    "ashby": Ashby,
    "personio": Personio,
}


def build_sources(
    config: JobScoutConfig, settings: JobScoutSettings, http: httpx.Client
) -> list[Source]:
    """Company boards first: their ads are the most complete, so they win when deduping."""
    chars = config.description_chars
    sources: list[Source] = [
        _BOARDS[company.system](http, company.name, company.slug, chars)
        for company in config.companies
    ]
    sources.append(Arbeitnow(http, config.arbeitnow.max_pages, chars))
    if settings.adzuna_app_id and settings.adzuna_app_key:
        sources.append(
            Adzuna(
                http,
                config.adzuna,
                settings.adzuna_app_id,
                settings.adzuna_app_key,
                chars,
            )
        )
    return sources
