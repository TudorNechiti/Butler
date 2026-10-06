import io
import json
import logging
from collections.abc import Iterator

import pytest

from core.logging import EventLogger, JsonFormatter, configure_logging


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.events")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield stream
    logger.removeHandler(handler)


def test_event_is_written_as_json_with_allowed_fields(log_output: io.StringIO) -> None:
    log = EventLogger("test.events", allowed_fields={"message_id", "category"})
    log.event("labeled", message_id="abc", category="debts")

    line = json.loads(log_output.getvalue())
    assert line["event"] == "labeled"
    assert line["message_id"] == "abc"
    assert line["category"] == "debts"
    assert line["level"] == "INFO"


def test_disallowed_field_is_rejected() -> None:
    log = EventLogger("test.events", allowed_fields={"message_id"})
    with pytest.raises(ValueError, match="subject"):
        log.event("labeled", message_id="abc", subject="Your invoice")


def test_non_scalar_field_is_rejected() -> None:
    log = EventLogger("test.events", allowed_fields={"ids"})
    with pytest.raises(TypeError):
        log.event("batch", ids=["a", "b"])  # type: ignore[arg-type]


def test_error_logs_exception_type_but_never_its_message(log_output: io.StringIO) -> None:
    log = EventLogger("test.events", allowed_fields={"message_id"})
    log.error("classify_failed", ValueError("SECRET-SUBJECT-MARKER"), message_id="abc")

    output = log_output.getvalue()
    assert "SECRET-SUBJECT-MARKER" not in output
    line = json.loads(output)
    assert line["error_type"] == "ValueError"
    assert line["level"] == "ERROR"


def test_configure_logging_quiets_http_libraries() -> None:
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("anthropic").level == logging.WARNING
