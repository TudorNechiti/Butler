"""Arbeitnow: free public job board API, no key. https://www.arbeitnow.com/blog/job-board-api

Its terms ask for a link back to arbeitnow.com (done in the README) and no abuse: a few pages
once a day is far below that.
"""

from __future__ import annotations

from typing import Any

import httpx

from agents.job_scout.models import Posting
from agents.job_scout.sources.base import from_unix, get_json, https_url, line, text

URL = "https://www.arbeitnow.com/api/job-board-api"


def parse_page(data: Any, description_chars: int) -> list[Posting]:
    postings = []
    for job in data.get("data", []):
        if not job.get("slug") or not job.get("title"):
            continue
        remote = job.get("remote")
        postings.append(
            Posting(
                source="arbeitnow",
                external_id=str(job["slug"]),
                company=line(job.get("company_name")),
                title=line(job["title"]),
                location=line(job.get("location")),
                remote=remote if isinstance(remote, bool) else None,
                url=https_url(job.get("url")),
                description=text(job.get("description"), description_chars),
                posted_at=from_unix(job.get("created_at")),
            )
        )
    return postings


class Arbeitnow:
    name = "arbeitnow"

    def __init__(self, http: httpx.Client, max_pages: int, description_chars: int) -> None:
        self._http = http
        self._max_pages = max_pages
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        postings: list[Posting] = []
        # Newest first, so the first few pages cover the last days. The `next` link in the
        # response is not followed: it is untrusted, so the page number is built here.
        for page in range(1, self._max_pages + 1):
            data = get_json(self._http, URL, {"page": page})
            postings += parse_page(data, self._chars)
            if not data.get("links", {}).get("next"):
                break
        return postings
