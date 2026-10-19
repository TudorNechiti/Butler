"""Greenhouse public job board API: no auth, meant for exactly this use.
https://developers.greenhouse.io/job-board.html
"""

from __future__ import annotations

from typing import Any

import httpx

from agents.job_scout.models import Posting
from agents.job_scout.sources.base import from_iso, get_json, https_url, line, text

URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def parse_board(data: Any, company: str, slug: str, description_chars: int) -> list[Posting]:
    postings = []
    for job in data.get("jobs", []):
        if not job.get("id") or not job.get("title"):
            continue
        postings.append(
            Posting(
                source=f"greenhouse:{slug}",
                external_id=str(job["id"]),
                company=company,
                title=line(job["title"]),
                location=line((job.get("location") or {}).get("name")),
                remote=None,  # only in the location text, e.g. "Remote - Germany"
                url=https_url(job.get("absolute_url")),
                # `content` is HTML that is entity-escaped a second time.
                description=text(job.get("content"), description_chars, escaped=True),
                posted_at=from_iso(job.get("first_published") or job.get("updated_at")),
            )
        )
    return postings


class Greenhouse:
    def __init__(self, http: httpx.Client, company: str, slug: str, description_chars: int) -> None:
        self.name = f"greenhouse:{slug}"
        self._http = http
        self._company = company
        self._slug = slug
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        data = get_json(self._http, URL.format(slug=self._slug), {"content": "true"})
        return parse_board(data, self._company, self._slug, self._chars)
