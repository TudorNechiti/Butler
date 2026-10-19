"""Personio XML job feed: public, no auth, common at German startups.

The XML is untrusted. The standard library parser is fine here: it never fetches external
entities, and the expat bundled with Python 3.12+ refuses entity-expansion bombs.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from agents.job_scout.models import Posting
from agents.job_scout.sources.base import SourceError, from_iso, get, line, text

URL = "https://{slug}.jobs.personio.de/xml"


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path) or "").strip()


def parse_feed(xml: bytes, company: str, slug: str, description_chars: int) -> list[Posting]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise SourceError("feed is not valid XML") from None
    postings = []
    for position in root.iter("position"):
        job_id, title = _text(position, "id"), _text(position, "name")
        if not job_id.isdigit() or not title:
            continue
        offices = [_text(position, "office")]
        offices += [(o.text or "").strip() for o in position.iterfind("additionalOffices/office")]
        description = "".join(
            f"<h3>{_text(d, 'name')}</h3>{_text(d, 'value')}"
            for d in position.iterfind("jobDescriptions/jobDescription")
        )
        postings.append(
            Posting(
                source=f"personio:{slug}",
                external_id=job_id,
                company=company,
                title=line(title),
                location=line(", ".join(o for o in offices if o)),
                remote=None,  # only in the office names, e.g. "Berlin (Remote)"
                # Built from the config slug and a numeric id, so nothing untrusted in it.
                url=f"https://{slug}.jobs.personio.de/job/{job_id}",
                description=text(description, description_chars),
                posted_at=from_iso(_text(position, "createdAt")),
            )
        )
    return postings


class Personio:
    def __init__(self, http: httpx.Client, company: str, slug: str, description_chars: int) -> None:
        self.name = f"personio:{slug}"
        self._http = http
        self._company = company
        self._slug = slug
        self._chars = description_chars

    def fetch(self) -> list[Posting]:
        response = get(self._http, URL.format(slug=self._slug), {"language": "en"})
        return parse_feed(response.content, self._company, self._slug, self._chars)
