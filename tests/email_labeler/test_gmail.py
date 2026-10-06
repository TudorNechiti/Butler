import base64
from typing import Any

from agents.email_labeler.gmail import (
    GROUP_LABELS,
    PROCESSED_LABEL,
    SCOPES,
    _extract_body,
    _label_body,
    build_query,
    category_label,
    parse_message,
)
from agents.email_labeler.models import Category


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _part(mime: str, text: str = "", filename: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "mimeType": mime,
        "filename": filename,
        "body": {"data": _b64(text)} if text else {},
        **extra,
    }


# --- permissions and labels ---------------------------------------------------------------


def test_requests_only_the_gmail_modify_scope() -> None:
    assert SCOPES == ("https://www.googleapis.com/auth/gmail.modify",)


def test_category_labels_are_nested_under_butler() -> None:
    assert category_label(Category.DEBTS) == "Butler/Debts"
    assert GROUP_LABELS == (
        "Butler/Debts",
        "Butler/Payments",
        "Butler/Reminders",
        "Butler/Jobs",
        "Butler/Other",
        "Butler/Review",
    )


def test_query_skips_processed_and_already_grouped_mail() -> None:
    query = build_query(newer_than_days=3)
    assert query.startswith("in:inbox newer_than:3d -category:promotions -category:social")
    for label in ("butler-processed", "butler-debts", "butler-review"):
        assert f"-label:{label}" in query


def test_processed_label_is_hidden_and_group_labels_are_coloured() -> None:
    processed = _label_body(PROCESSED_LABEL)
    assert processed["labelListVisibility"] == "labelHide"
    assert "color" not in processed
    assert _label_body("Butler/Debts")["color"]["backgroundColor"] == "#fb4c2f"


# --- message parsing -------------------------------------------------------------------------


def test_parse_message_reads_headers_date_and_sanitises_body() -> None:
    raw = {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1790000000000",
        "payload": {
            **_part("text/plain", "Pay​ now   please"),
            "headers": [{"name": "from", "value": "a@b.com"}, {"name": "Subject", "value": "Hi"}],
        },
    }
    email = parse_message(raw, body_chars=100)
    assert (email.id, email.thread_id, email.sender, email.subject) == ("m1", "t1", "a@b.com", "Hi")
    assert email.body_text == "Pay now please"
    assert email.received_at.year == 2026


# --- _extract_body (TODO(human)) -------------------------------------------------------------


def test_extract_body_single_plain_part() -> None:
    assert _extract_body(_part("text/plain", "Invoice due")) == "Invoice due"


def test_extract_body_html_only_is_converted_to_text() -> None:
    assert _extract_body(_part("text/html", "<p>Invoice <b>due</b></p>")) == "Invoice due"


def test_extract_body_prefers_plain_over_html_in_alternative() -> None:
    payload = _part(
        "multipart/alternative",
        parts=[_part("text/plain", "plain version"), _part("text/html", "<p>html version</p>")],
    )
    assert _extract_body(payload) == "plain version"


def test_extract_body_finds_text_in_nested_multipart_and_skips_attachments() -> None:
    payload = _part(
        "multipart/mixed",
        parts=[
            _part(
                "multipart/alternative",
                parts=[_part("text/plain", "the real body"), _part("text/html", "<p>x</p>")],
            ),
            _part("text/plain", "attachment text", filename="notes.txt"),
        ],
    )
    assert _extract_body(payload) == "the real body"


def test_extract_body_returns_empty_string_when_no_text() -> None:
    payload = _part("multipart/mixed", parts=[_part("image/png", filename="logo.png")])
    assert _extract_body(payload) == ""
