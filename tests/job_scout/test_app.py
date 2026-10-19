import io
import logging
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from agents.job_scout.app import run
from agents.job_scout.config import load_config
from agents.job_scout.dedupe import SeenStore, dedupe_key
from agents.job_scout.models import JobDigest, Score
from agents.job_scout.sources import Source
from core.llm import CallLimitExceeded, Refused
from core.logging import JsonFormatter
from tests.job_scout.fakes import CONFIG, NOW, FakeLLM, FakeSource, make_posting


def _run(
    sources: list[Source], responses: list[Score | Exception], seen: SeenStore
) -> tuple[JobDigest, FakeLLM]:
    llm = FakeLLM(responses)
    digest = run(
        config=CONFIG, sources=sources, llm=llm, system_prompt="SYSTEM", seen=seen, now=NOW
    )
    return digest, llm


def _seen(tmp_path: Path) -> SeenStore:
    return SeenStore.load(tmp_path / "seen.json")


def test_shipped_config_is_valid() -> None:
    config = load_config()
    assert config.model == "claude-haiku-4-5"
    assert config.companies, "starter company list is empty"
    assert len({c.slug for c in config.companies}) == len(config.companies)


def test_scores_only_new_candidates_and_returns_best_first(tmp_path: Path) -> None:
    seen = _seen(tmp_path)
    old = make_posting(title="Java Developer", external_id="old")
    seen.add([dedupe_key(old)], date(2026, 10, 1))
    board = FakeSource(
        "greenhouse:acme",
        [
            make_posting(external_id="a"),
            make_posting(title="Backend Engineer, Payments", external_id="b"),
            make_posting(title="Recruiter", external_id="c"),  # filtered in code
            old,  # seen yesterday
        ],
    )
    duplicate = FakeSource("arbeitnow", [make_posting(source="arbeitnow", external_id="z")])

    digest, llm = _run(
        [board, duplicate], [Score(score=65, reason="ok"), Score(score=90, reason="great")], seen
    )

    assert len(llm.calls) == 2
    assert [m.score.score for m in digest.matches] == [90, 65]
    assert (digest.fetched, digest.candidates, digest.new, digest.scored) == (5, 4, 2, 2)


def test_below_min_score_is_not_a_match_but_is_marked_seen(tmp_path: Path) -> None:
    seen = _seen(tmp_path)
    posting = make_posting()

    digest, _ = _run([FakeSource("s", [posting])], [Score(score=30, reason="weak")], seen)

    assert digest.matches == []
    assert dedupe_key(posting) in seen


def test_keeps_at_most_max_matches(tmp_path: Path) -> None:
    postings = [make_posting(title=f"Backend Engineer {i}", external_id=str(i)) for i in range(5)]
    scores: list[Score | Exception] = [Score(score=60 + i, reason="ok") for i in range(5)]

    digest, _ = _run([FakeSource("s", postings)], scores, _seen(tmp_path))

    assert [m.score.score for m in digest.matches] == [64, 63, 62]  # CONFIG.max_matches == 3


def test_one_failing_source_does_not_stop_the_run(tmp_path: Path) -> None:
    broken = FakeSource("greenhouse:broken", ConnectionError("boom"))
    working = FakeSource("arbeitnow", [make_posting()])

    digest, _ = _run([broken, working], [Score(score=80, reason="ok")], _seen(tmp_path))

    assert digest.failed_sources == ["greenhouse:broken"]
    assert len(digest.matches) == 1


def test_call_cap_leaves_the_rest_unseen_for_tomorrow(tmp_path: Path) -> None:
    seen = _seen(tmp_path)
    first = make_posting(external_id="1")
    second = make_posting(title="Backend Engineer II", external_id="2", posted_at=None)

    digest, _ = _run(
        [FakeSource("s", [second, first])],
        [Score(score=80, reason="ok"), CallLimitExceeded("cap")],
        seen,
    )

    assert digest.scored == 1
    assert dedupe_key(first) in seen  # newest first, so the dated one was scored
    assert dedupe_key(second) not in seen


def test_refusal_is_marked_seen_but_network_error_is_retried(tmp_path: Path) -> None:
    seen = _seen(tmp_path)
    refused = make_posting(external_id="1")
    flaky = make_posting(title="Backend Engineer II", external_id="2")

    digest, _ = _run(
        [FakeSource("s", [refused, flaky])], [Refused("no"), ConnectionError("down")], seen
    )

    assert digest.scored == 0
    assert dedupe_key(refused) in seen
    assert dedupe_key(flaky) not in seen


@pytest.fixture
def captured_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    yield stream
    root.removeHandler(handler)
    root.setLevel(old_level)


def test_logs_never_contain_posting_text(tmp_path: Path, captured_logs: io.StringIO) -> None:
    posting = make_posting(title="Backend Engineer SECRET-TITLE", description="SECRET-BODY")

    _run([FakeSource("s", [posting])], [Score(score=80, reason="SECRET-REASON")], _seen(tmp_path))

    logs = captured_logs.getvalue()
    assert '"event": "run_finished"' in logs
    for secret in ("SECRET-TITLE", "SECRET-BODY", "SECRET-REASON", "Acme"):
        assert secret not in logs
