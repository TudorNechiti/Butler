import io
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest

from agents.habit_tracker.app import reminder, weekly
from agents.habit_tracker.store import SheetReadError
from core.logging import JsonFormatter
from tests.habit_tracker.fakes import CONFIG, HEADER, MONDAY, FakeRows, FakeSend, evening, row

FORM = "https://forms.example/fake"


def test_reminder_sends_when_today_is_missing() -> None:
    send = FakeSend()
    rows = FakeRows([HEADER, row(evening(MONDAY))])
    sent = reminder(
        config=CONFIG, rows=rows, send=send, form_url=FORM, now=evening(MONDAY + timedelta(1))
    )
    assert sent
    assert FORM in send.messages[0]


def test_reminder_quiet_when_logged() -> None:
    send = FakeSend()
    rows = FakeRows([HEADER, row(datetime(2030, 1, 7, 19))])
    assert not reminder(config=CONFIG, rows=rows, send=send, form_url=FORM, now=evening(MONDAY))
    assert send.messages == []


def test_weekly_sends_report_and_ignores_future_dates() -> None:
    send = FakeSend()
    sunday = MONDAY + timedelta(days=6)
    rows = FakeRows(
        [
            HEADER,
            row(evening(MONDAY), gym="yes"),
            row(evening(MONDAY + timedelta(1))),
            row(evening(MONDAY), day=sunday + timedelta(days=3)),  # mistyped future date
        ]
    )
    text = weekly(config=CONFIG, rows=rows, send=send, now=evening(sunday, 20))
    assert send.messages == [text]
    assert "Logged 2/7 days" in text
    assert "tea: not enough days to compare (n=0 vs 2, need 3 each)" in text


def test_sheet_errors_propagate_without_sending() -> None:
    send = FakeSend()
    with pytest.raises(SheetReadError):
        weekly(
            config=CONFIG, rows=FakeRows(SheetReadError("HTTP 403")), send=send, now=evening(MONDAY)
        )
    assert send.messages == []


@pytest.fixture
def json_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("agents.habit_tracker")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield stream
    logger.removeHandler(handler)


def test_logs_hold_counts_only(json_logs: io.StringIO) -> None:
    rows = FakeRows([HEADER, row(evening(MONDAY), golang=77, sleep=6.25, tea="yes")])
    weekly(config=CONFIG, rows=rows, send=FakeSend(), now=evening(MONDAY + timedelta(6)))
    reminder(config=CONFIG, rows=rows, send=FakeSend(), form_url=FORM, now=evening(MONDAY))

    logs = json_logs.getvalue()
    assert "sheet_read" in logs
    for secret in ("tea", "77", "6.25", "private note", FORM, "2030"):
        assert secret not in logs.replace('"ts"', "")
