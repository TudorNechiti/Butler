"""Adzuna search API. Free developer key (ADZUNA_APP_ID / ADZUNA_APP_KEY) with a monthly call
limit: check the current limits on developer.adzuna.com. Results must credit Adzuna, which the
digest footer does. Descriptions are short snippets, not full ads.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr

from agents.job_scout.config import AdzunaConfig
from agents.job_scout.models import Posting
from agents.job_scout.sources.base import from_iso, get_json, https_url, line, text

URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _stated_salary_max(job: dict[str, Any]) -> int | None:
    # salary_is_predicted == "1" means Adzuna estimated it; only trust what the ad states.
    value = job.get("salary_max")
    if str(job.get("salary_is_predicted")) != "0" or not isinstance(value, int | float):
        return None
    return int(value)


def parse_page(data: Any, description_chars: int) -> list[Posting]:
    postings = []
    for job in data.get("results", []):
        if not job.get("id") or not job.get("title"):
            continue
        postings.append(
            Posting(
                source="adzuna",
                external_id=str(job["id"]),
                company=line((job.get("company") or {}).get("display_name")),
                title=line(job["title"]),
                location=line((job.get("location") or {}).get("display_name")),
                remote=None,
                url=https_url(job.get("redirect_url")),
                description=text(job.get("description"), description_chars),
                posted_at=from_iso(job.get("created")),
                salary_max_eur=_stated_salary_max(job),
            )
        )
    return postings


class Adzuna:
    name = "adzuna"

    def __init__(
        self,
        http: httpx.Client,
        config: AdzunaConfig,
        app_id: str,
        app_key: SecretStr,
        description_chars: int,
    ) -> None:
        self._http = http
        self._config = config
        self._app_id = app_id
        self._app_key = app_key
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        postings: list[Posting] = []
        for page in range(1, self._config.max_pages + 1):
            url = URL.format(country=self._config.country, page=page)
            params: dict[str, str | int] = {
                "app_id": self._app_id,
                "app_key": self._app_key.get_secret_value(),
                "results_per_page": self._config.results_per_page,
                "what_or": self._config.what_or,
                "where": self._config.where,
                "max_days_old": self._config.max_days_old,
                "sort_by": "date",
            }
            batch = parse_page(get_json(self._http, url, params), self._chars)
            postings += batch
            if len(batch) < self._config.results_per_page:
                break
        return postings
