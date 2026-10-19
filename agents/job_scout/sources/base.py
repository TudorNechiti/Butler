"""Plumbing every source shares: one HTTP helper and the cleaning of untrusted fields.

Job ads are third-party content. Every text field goes through core.sanitize before it is
stored in a Posting, and only https links are kept.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from agents.job_scout.models import Posting
from core.sanitize import clean_untrusted, html_to_text

USER_AGENT = "butler-job-scout/0.1 (personal, non-commercial)"
MAX_LINE_CHARS = 200


class SourceError(Exception):
    """A source could not be read. The message never holds the URL: Adzuna's carries the key."""


class Source(Protocol):
    name: str

    def fetch(self) -> list[Posting]: ...


def new_http_client() -> httpx.Client:
    return httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})


def get(http: httpx.Client, url: str, params: dict[str, str | int] | None = None) -> httpx.Response:
    try:
        response = http.get(url, params=params)
    except httpx.HTTPError as exc:
        # httpx errors include the request URL; drop the chain so keys can't reach the logs.
        raise SourceError(f"request failed: {type(exc).__name__}") from None
    if response.is_error:
        raise SourceError(f"HTTP {response.status_code}")
    return response


def get_json(http: httpx.Client, url: str, params: dict[str, str | int] | None = None) -> Any:
    try:
        return get(http, url, params).json()
    except ValueError:
        raise SourceError("response is not JSON") from None


def line(value: object, max_chars: int = MAX_LINE_CHARS) -> str:
    """A single line of untrusted text: a newline in a title could fake extra fields."""
    return " ".join(clean_untrusted(str(value or ""), max_chars).split())


def text(markup: object, max_chars: int, escaped: bool = False) -> str:
    """Untrusted HTML (entity-escaped once more when `escaped`) to bounded plain text."""
    raw = str(markup or "")
    return clean_untrusted(html_to_text(html.unescape(raw) if escaped else raw), max_chars)


def https_url(value: object) -> str:
    return value if isinstance(value, str) and value.startswith("https://") else ""


def from_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def from_unix(value: object, millis: bool = False) -> datetime | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return datetime.fromtimestamp(value / 1000 if millis else value, UTC)
