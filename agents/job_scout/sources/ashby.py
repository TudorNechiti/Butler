"""Ashby public job posting API: no auth.
https://developers.ashbyhq.com/docs/public-job-posting-api
"""

from __future__ import annotations

from typing import Any

import httpx

from agents.job_scout.models import Posting
from agents.job_scout.sources.base import from_iso, get_json, https_url, line, text

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _location(job: dict[str, Any]) -> str:
    names = [job.get("location")]
    names += [extra.get("location") for extra in job.get("secondaryLocations") or []]
    return line(", ".join(str(n) for n in names if n))


def parse_board(data: Any, company: str, slug: str, description_chars: int) -> list[Posting]:
    postings = []
    for job in data.get("jobs", []):
        if not job.get("id") or not job.get("title") or job.get("isListed") is False:
            continue
        remote = job.get("isRemote")
        postings.append(
            Posting(
                source=f"ashby:{slug}",
                external_id=str(job["id"]),
                company=company,
                title=line(job["title"]),
                location=_location(job),
                remote=remote if isinstance(remote, bool) else None,
                url=https_url(job.get("jobUrl")),
                description=text(job.get("descriptionHtml"), description_chars),
                posted_at=from_iso(job.get("publishedAt")),
            )
        )
    return postings


class Ashby:
    def __init__(self, http: httpx.Client, company: str, slug: str, description_chars: int) -> None:
        self.name = f"ashby:{slug}"
        self._http = http
        self._company = company
        self._slug = slug
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        data = get_json(self._http, URL.format(slug=self._slug))
        return parse_board(data, self._company, self._slug, self._chars)
