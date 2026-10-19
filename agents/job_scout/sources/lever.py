"""Lever public postings API: no auth. https://github.com/lever/postings-api

Companies on Lever's EU instance use api.eu.lever.co instead; none in the starter list do.
"""

from __future__ import annotations

from typing import Any

import httpx

from agents.job_scout.models import Posting
from agents.job_scout.sources.base import from_unix, get_json, https_url, line, text

URL = "https://api.lever.co/v0/postings/{slug}"
_WORKPLACE_REMOTE = {"remote": True, "onsite": False, "hybrid": False}


def _salary_max(job: dict[str, Any]) -> int | None:
    salary = job.get("salaryRange") or {}
    value = salary.get("max")
    if (
        salary.get("currency") != "EUR"
        or salary.get("interval") != "per-year-salary"
        or not isinstance(value, int | float)
    ):
        return None
    return int(value)


def _description(job: dict[str, Any]) -> str:
    # The ad is split into a plain intro, HTML lists (requirements, ...) and a plain closing.
    parts = [str(job.get("descriptionPlain") or "")]
    for block in job.get("lists") or []:
        parts.append(f"<h3>{block.get('text', '')}</h3><ul>{block.get('content', '')}</ul>")
    parts.append(str(job.get("additionalPlain") or ""))
    return "\n".join(parts)


def parse_postings(data: Any, company: str, slug: str, description_chars: int) -> list[Posting]:
    postings = []
    for job in data if isinstance(data, list) else []:
        if not job.get("id") or not job.get("text"):
            continue
        postings.append(
            Posting(
                source=f"lever:{slug}",
                external_id=str(job["id"]),
                company=company,
                title=line(job["text"]),
                location=line((job.get("categories") or {}).get("location")),
                remote=_WORKPLACE_REMOTE.get(str(job.get("workplaceType"))),
                url=https_url(job.get("hostedUrl")),
                description=text(_description(job), description_chars),
                posted_at=from_unix(job.get("createdAt"), millis=True),
                salary_max_eur=_salary_max(job),
            )
        )
    return postings


class Lever:
    def __init__(self, http: httpx.Client, company: str, slug: str, description_chars: int) -> None:
        self.name = f"lever:{slug}"
        self._http = http
        self._company = company
        self._slug = slug
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        data = get_json(self._http, URL.format(slug=self._slug), {"mode": "json"})
        return parse_postings(data, self._company, self._slug, self._chars)
