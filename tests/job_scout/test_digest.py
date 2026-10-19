from agents.job_scout.digest import format_digest
from agents.job_scout.models import JobDigest, Match, Score
from tests.job_scout.fakes import make_posting


def _match(score: int, **posting: object) -> Match:
    return Match(make_posting(**posting), Score(score=score, reason="Spring Boot, English team"))  # type: ignore[arg-type]


def test_digest_lists_matches_with_score_place_reason_and_link() -> None:
    digest = JobDigest(
        matches=[_match(85, remote=True), _match(70, title="Java Developer", external_id="2")],
        fetched=500,
        scored=12,
    )

    text = format_digest(digest)

    assert text.startswith("Butler job scout: 2 new matches\n")
    assert "1. [85] Backend Engineer (Java)\n   Acme GmbH · Berlin · remote\n" in text
    assert "   https://jobs.example.com/1\n" in text
    assert "2. [70] Java Developer" in text
    assert "12 new jobs scored out of 500 fetched." in text
    assert "Adzuna" not in text


def test_digest_credits_adzuna_and_names_failed_sources() -> None:
    digest = JobDigest(
        matches=[_match(90, source="adzuna")], failed_sources=["greenhouse:acme"], scored=1
    )

    text = format_digest(digest)

    assert text.startswith("Butler job scout: 1 new match\n")
    assert "Sources that failed: greenhouse:acme." in text
    assert text.endswith("Jobs by Adzuna.")
