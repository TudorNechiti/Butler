import io
import logging
from collections.abc import Iterator

import pytest

from agents.email_labeler.gmail import PROCESSED_LABEL, REVIEW_LABEL, GmailAuthError
from agents.email_labeler.labeler import LabelerConfig, RunStats, load_config, run
from agents.email_labeler.models import Category, Classification
from core.llm import CallLimitExceeded, Refused, Truncated
from core.logging import JsonFormatter
from tests.email_labeler.fakes import FakeAlert, FakeLLM, FakeMailbox, classification, make_email

CONFIG = LabelerConfig(
    model="claude-haiku-4-5",
    max_tokens=256,
    max_items=50,
    newer_than_days=3,
    body_chars=3000,
    review_threshold=0.6,
)


def _run(
    mailbox: FakeMailbox,
    responses: list[Classification | Exception],
    alert: FakeAlert | None = None,
    dry_run: bool = False,
) -> RunStats:
    return run(
        config=CONFIG,
        mailbox=mailbox,
        llm=FakeLLM(responses),
        system_prompt="SYSTEM",
        alert=alert or FakeAlert(),
        dry_run=dry_run,
    )


def test_shipped_config_is_valid() -> None:
    config = load_config()
    assert config.model == "claude-haiku-4-5"
    assert 0 < config.review_threshold < 1


def test_labels_each_email_with_its_group_and_processed() -> None:
    mailbox = FakeMailbox([make_email(id="a"), make_email(id="b")])

    stats = _run(mailbox, [classification(Category.DEBTS), classification(Category.JOBS)])

    assert mailbox.added == {
        "a": ["id:Butler/Debts", f"id:{PROCESSED_LABEL}"],
        "b": ["id:Butler/Jobs", f"id:{PROCESSED_LABEL}"],
    }
    assert stats.processed == 2
    assert stats.failed == 0


def test_low_confidence_goes_to_review() -> None:
    mailbox = FakeMailbox([make_email(id="a")])

    _run(mailbox, [classification(Category.PAYMENTS, confidence=0.4)])

    assert mailbox.added["a"] == [f"id:{REVIEW_LABEL}", f"id:{PROCESSED_LABEL}"]


@pytest.mark.parametrize("error", [Refused("no"), Truncated("cut")])
def test_model_errors_go_to_review_so_they_are_not_paid_for_again(error: Exception) -> None:
    mailbox = FakeMailbox([make_email(id="a")])

    stats = _run(mailbox, [error])

    assert mailbox.added["a"] == [f"id:{REVIEW_LABEL}", f"id:{PROCESSED_LABEL}"]
    assert stats.labeled[REVIEW_LABEL] == 1


def test_dry_run_writes_nothing_to_gmail() -> None:
    mailbox = FakeMailbox([make_email(id="a")])

    stats = _run(mailbox, [classification()], dry_run=True)

    assert mailbox.ensure_labels_calls == 0
    assert mailbox.added == {}
    assert stats.processed == 1


def test_one_failing_email_does_not_stop_the_run_and_stays_unprocessed() -> None:
    mailbox = FakeMailbox([make_email(id="a"), make_email(id="b")], fail_get={"a"})

    stats = _run(mailbox, [classification()])

    assert "a" not in mailbox.added  # retried next run
    assert "b" in mailbox.added
    assert stats.failed == 1


def test_call_limit_stops_the_run() -> None:
    mailbox = FakeMailbox([make_email(id="a"), make_email(id="b")])

    stats = _run(mailbox, [classification(), CallLimitExceeded("cap")])

    assert list(mailbox.added) == ["a"]
    assert stats.failed == 0


def test_auth_error_sends_alert_and_propagates() -> None:
    class ExpiredMailbox(FakeMailbox):
        def list_unprocessed(self, limit: int, newer_than_days: int = 3) -> list[str]:
            raise GmailAuthError("Gmail authorization expired")

    alert = FakeAlert()
    with pytest.raises(GmailAuthError):
        _run(ExpiredMailbox([]), [], alert=alert)
    assert alert.messages == ["Butler email labeler: Gmail authorization expired"]


def test_alert_when_every_email_fails_but_not_on_normal_runs() -> None:
    alert = FakeAlert()
    _run(FakeMailbox([make_email(id="a")], fail_get={"a"}), [], alert=alert)
    assert len(alert.messages) == 1

    quiet = FakeAlert()
    _run(FakeMailbox([make_email(id="a")]), [classification()], alert=quiet)
    assert quiet.messages == []


def test_failing_alert_does_not_hide_the_auth_error() -> None:
    class ExpiredMailbox(FakeMailbox):
        def list_unprocessed(self, limit: int, newer_than_days: int = 3) -> list[str]:
            raise GmailAuthError("expired")

    def broken_alert(text: str) -> None:
        raise RuntimeError("telegram down")

    with pytest.raises(GmailAuthError):
        run(
            config=CONFIG,
            mailbox=ExpiredMailbox([]),
            llm=FakeLLM([]),
            system_prompt="SYSTEM",
            alert=broken_alert,
            dry_run=False,
        )


# --- the logging rule: no email content, ever ----------------------------------------------


@pytest.fixture
def json_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("agents.email_labeler")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield stream
    logger.removeHandler(handler)


def test_logs_never_contain_sender_subject_body_or_reason(json_logs: io.StringIO) -> None:
    markers = {
        "sender": "SENDER-MARKER@example.com",
        "subject": "SUBJECT-MARKER",
        "body": "BODY-MARKER",
        "reason": "REASON-MARKER",
    }
    emails = [
        make_email(
            id="ok", sender=markers["sender"], subject=markers["subject"], body=markers["body"]
        ),
        # The failing read raises an exception whose message contains the subject.
        make_email(
            id="bad", sender=markers["sender"], subject=markers["subject"], body=markers["body"]
        ),
    ]
    mailbox = FakeMailbox(emails, fail_get={"bad"})

    _run(mailbox, [classification(reason=markers["reason"])])

    output = json_logs.getvalue()
    assert '"event": "email_labeled"' in output
    assert '"event": "email_failed"' in output
    for name, marker in markers.items():
        assert marker not in output, f"{name} leaked into logs"
