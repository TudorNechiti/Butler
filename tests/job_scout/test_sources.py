from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from agents.job_scout.config import JobScoutConfig, JobScoutSettings
from agents.job_scout.sources import SourceError, build_sources
from agents.job_scout.sources.adzuna import Adzuna
from agents.job_scout.sources.adzuna import parse_page as parse_adzuna
from agents.job_scout.sources.arbeitnow import Arbeitnow
from agents.job_scout.sources.arbeitnow import parse_page as parse_arbeitnow
from agents.job_scout.sources.ashby import parse_board as parse_ashby
from agents.job_scout.sources.base import https_url, line
from agents.job_scout.sources.greenhouse import parse_board as parse_greenhouse
from agents.job_scout.sources.lever import parse_postings as parse_lever
from agents.job_scout.sources.personio import parse_feed as parse_personio
from tests.job_scout.fakes import CONFIG


def _http(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_arbeitnow_maps_fields() -> None:
    data = {
        "data": [
            {
                "slug": "backend-engineer-acme-1",
                "company_name": "Acme GmbH",
                "title": "Backend Engineer\n(Java)",
                "description": "<p>Build <b>APIs</b></p><script>x()</script>",
                "remote": True,
                "url": "https://www.arbeitnow.com/jobs/acme/backend-engineer-acme-1",
                "location": "Berlin",
                "created_at": 1792411284,
            },
            {"slug": "", "title": "no id, skipped"},
        ]
    }

    [posting] = parse_arbeitnow(data, 1000)

    assert posting.source == "arbeitnow"
    assert posting.external_id == "backend-engineer-acme-1"
    assert posting.title == "Backend Engineer (Java)"  # one line, no fake extra fields
    assert posting.description == "Build APIs"
    assert posting.remote is True
    assert posting.posted_at == datetime.fromtimestamp(1792411284, UTC)


def test_arbeitnow_builds_page_numbers_itself_and_stops_without_next() -> None:
    requested: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        page = request.url.params["page"]
        nxt = "https://evil.example/steal" if page == "1" else None
        job = {"slug": f"job-{page}", "title": "Backend Engineer", "url": "https://x.example"}
        return httpx.Response(200, json={"data": [job], "links": {"next": nxt}})

    postings = Arbeitnow(_http(httpx.MockTransport(handle)), 5, 500).fetch()

    assert [p.external_id for p in postings] == ["job-1", "job-2"]
    assert all(url.startswith("https://www.arbeitnow.com/") for url in requested)


def test_adzuna_keeps_only_stated_salaries() -> None:
    data = {
        "results": [
            {
                "id": "11",
                "title": "Java Developer",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "Berlin, Deutschland"},
                "redirect_url": "https://www.adzuna.de/land/ad/11",
                "description": "Spring Boot …",
                "created": "2026-10-18T09:00:00Z",
                "salary_max": 60000,
                "salary_is_predicted": "0",
            },
            {
                "id": "12",
                "title": "Java Developer",
                "salary_max": 90000,
                "salary_is_predicted": "1",
            },
        ]
    }

    stated, predicted = parse_adzuna(data, 1000)

    assert stated.salary_max_eur == 60000
    assert predicted.salary_max_eur is None
    assert stated.posted_at == datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def test_adzuna_errors_never_contain_the_api_key() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed", request=request)

    source = Adzuna(
        _http(httpx.MockTransport(handle)),
        CONFIG.adzuna,
        "app-id",
        SecretStr("SECRET-KEY"),
        500,
    )

    with pytest.raises(SourceError) as excinfo:
        source.fetch()
    assert "SECRET-KEY" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_greenhouse_unescapes_double_escaped_content() -> None:
    data = {
        "jobs": [
            {
                "id": 42,
                "title": "Senior Backend Engineer",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/42",
                "location": {"name": "Berlin, Germany"},
                "content": "&lt;p&gt;Kafka &amp;amp; Go&lt;/p&gt;",
                "first_published": "2026-10-01T10:00:00-04:00",
            }
        ]
    }

    [posting] = parse_greenhouse(data, "Acme", "acme", 1000)

    assert posting.source == "greenhouse:acme"
    assert posting.company == "Acme"
    assert posting.description == "Kafka & Go"
    assert posting.location == "Berlin, Germany"


def test_lever_reads_workplace_type_lists_and_yearly_eur_salary() -> None:
    data = [
        {
            "id": "abc",
            "text": "Backend Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "categories": {"location": "Berlin"},
            "workplaceType": "hybrid",
            "createdAt": 1760000000000,
            "descriptionPlain": "Intro.",
            "lists": [{"text": "Requirements", "content": "<li>Java</li><li>Kafka</li>"}],
            "additionalPlain": "Apply now.",
            "salaryRange": {
                "min": 60000,
                "max": 75000,
                "currency": "EUR",
                "interval": "per-year-salary",
            },
        },
        {
            "id": "def",
            "text": "Backend Engineer",
            "workplaceType": "unspecified",
            "salaryRange": {"max": 9000, "currency": "EUR", "interval": "per-month-salary"},
        },
    ]

    first, second = parse_lever(data, "Acme", "acme", 1000)

    assert first.remote is False
    assert first.salary_max_eur == 75000
    assert "Requirements" in first.description and "Kafka" in first.description
    assert second.remote is None
    assert second.salary_max_eur is None  # monthly: not comparable, so not used


def test_ashby_skips_unlisted_and_joins_locations() -> None:
    data = {
        "jobs": [
            {
                "id": "u1",
                "title": "Backend Engineer",
                "location": "Berlin",
                "secondaryLocations": [{"location": "Remote - Germany"}],
                "isRemote": True,
                "isListed": True,
                "jobUrl": "https://jobs.ashbyhq.com/acme/u1",
                "descriptionHtml": "<p>Go and Postgres</p>",
                "publishedAt": "2026-10-19T11:22:46.527+00:00",
            },
            {"id": "u2", "title": "Hidden", "isListed": False},
        ]
    }

    [posting] = parse_ashby(data, "Acme", "acme", 1000)

    assert posting.location == "Berlin, Remote - Germany"
    assert posting.remote is True
    assert posting.description == "Go and Postgres"


def test_personio_parses_positions_and_builds_its_own_url() -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <workzag-jobs>
      <position>
        <id>123</id>
        <office>Berlin</office>
        <additionalOffices><office>Berlin (Remote)</office></additionalOffices>
        <name>Backend Engineer (m/w/d)</name>
        <jobDescriptions>
          <jobDescription>
            <name>Your tasks</name><value><![CDATA[<p>Java</p>]]></value>
          </jobDescription>
        </jobDescriptions>
        <createdAt>2026-09-17T07:57:12+00:00</createdAt>
      </position>
      <position><id>../../x</id><name>Bad id</name></position>
    </workzag-jobs>"""

    [posting] = parse_personio(xml, "Acme", "acme", 1000)

    assert posting.url == "https://acme.jobs.personio.de/job/123"
    assert posting.location == "Berlin, Berlin (Remote)"
    assert "Your tasks" in posting.description and "Java" in posting.description


def test_personio_rejects_invalid_xml() -> None:
    with pytest.raises(SourceError):
        parse_personio(b"<not-xml", "Acme", "acme", 1000)


def test_only_https_urls_are_kept() -> None:
    assert https_url("https://ok.example/job") == "https://ok.example/job"
    assert https_url("javascript:alert(1)") == ""
    assert https_url("http://plain.example") == ""
    assert https_url(None) == ""


def test_line_flattens_and_bounds_untrusted_text() -> None:
    assert line("a\n\nTitle: fake​", 50) == "a Title: fake"
    assert len(line("x" * 500)) <= 200


def test_build_sources_puts_boards_first_and_skips_adzuna_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = JobScoutSettings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token=SecretStr("t"),
        telegram_chat_id="1",
        anthropic_api_key=SecretStr("k"),
        job_profile=SecretStr("Backend developer."),
    )
    config = JobScoutConfig.model_validate(
        {
            **CONFIG.model_dump(),
            "companies": [
                {"name": "Acme", "system": "greenhouse", "slug": "acme"},
                {"name": "Beta", "system": "personio", "slug": "beta"},
            ],
        }
    )

    names = [s.name for s in build_sources(config, settings, httpx.Client())]

    assert names == ["greenhouse:acme", "personio:beta", "arbeitnow"]
