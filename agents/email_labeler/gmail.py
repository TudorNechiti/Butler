"""The only code that talks to Gmail.

Deliberately small surface: list, read, create our own labels, add labels. Nothing here can
send, trash, delete or remove labels, even though the gmail.modify scope would allow some of it
(no narrower Google scope permits adding labels to messages).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import SecretStr

from agents.email_labeler.models import Category, EmailMessage
from core.config import Settings
from core.sanitize import clean_untrusted, html_to_text

SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)
TOKEN_URI = "https://oauth2.googleapis.com/token"

PARENT_LABEL = "Butler"
PROCESSED_LABEL = "Butler/Processed"
REVIEW_LABEL = "Butler/Review"

# Gmail only accepts colours from its fixed label palette.
_WHITE = "#ffffff"
_COLORS: dict[str, str] = {
    "Butler/Debts": "#fb4c2f",  # red
    "Butler/Payments": "#16a766",  # green
    "Butler/Reminders": "#ffad47",  # orange
    "Butler/Jobs": "#4a86e8",  # blue
    "Butler/Other": "#999999",  # grey
    REVIEW_LABEL: "#a479e2",  # purple
}


def category_label(category: Category) -> str:
    return f"{PARENT_LABEL}/{category.value.capitalize()}"


GROUP_LABELS = (*(category_label(c) for c in Category), REVIEW_LABEL)


class GmailSettings(Settings):
    gmail_client_id: str
    gmail_client_secret: SecretStr
    gmail_refresh_token: SecretStr


class GmailAuthError(Exception):
    """The refresh token expired or was revoked: re-run scripts/gmail_auth.py."""


def build_credentials(settings: GmailSettings) -> Credentials:
    return Credentials(  # type: ignore[no-untyped-call]  # google-auth is untyped
        token=None,
        refresh_token=settings.gmail_refresh_token.get_secret_value(),
        token_uri=TOKEN_URI,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret.get_secret_value(),
        scopes=list(SCOPES),
    )


def _search_name(label: str) -> str:
    # Gmail search refers to "Butler/Debts" as "butler-debts".
    return label.lower().replace("/", "-").replace(" ", "-")


def build_query(newer_than_days: int) -> str:
    """Inbox mail we haven't handled, skipping anything a Gmail filter already grouped."""
    excluded = " ".join(f"-label:{_search_name(name)}" for name in (PROCESSED_LABEL, *GROUP_LABELS))
    return (
        f"in:inbox newer_than:{newer_than_days}d -category:promotions -category:social {excluded}"
    )


def _header(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _decode_data(part: dict[str, Any]) -> str:
    """Decode one MIME part's base64url body. Empty string if the part has no inline data."""
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _find_part(part: dict[str, Any], mime_type: str) -> dict[str, Any] | None:
    """Depth-first search for the first inline (non-attachment) part of a MIME type."""
    if part.get("filename"):
        return None  # attachments are never the body, even text/plain ones
    if part.get("mimeType") == mime_type and part.get("body", {}).get("data"):
        return part
    for child in part.get("parts", []):
        found = _find_part(child, mime_type)
        if found is not None:
            return found
    return None


def _extract_body(payload: dict[str, Any]) -> str:
    """Return the readable text of an email from Gmail's MIME tree.

    Prefers text/plain (cleaner input, no hidden-HTML tricks) and falls back to text/html
    converted to text. `payload` is a tree of parts shaped like
    {"mimeType": ..., "filename": ..., "body": {"data": ...}, "parts": [...]}.
    """
    plain = _find_part(payload, "text/plain")
    if plain is not None:
        return _decode_data(plain)
    html = _find_part(payload, "text/html")
    return html_to_text(_decode_data(html)) if html is not None else ""


def parse_message(raw: dict[str, Any], body_chars: int) -> EmailMessage:
    """Turn a Gmail API message (format="full") into a sanitised EmailMessage."""
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])
    return EmailMessage(
        id=raw["id"],
        thread_id=raw.get("threadId", ""),
        sender=_header(headers, "From"),
        subject=_header(headers, "Subject"),
        # internalDate (ms since epoch, set by Gmail) is more reliable than the Date header.
        received_at=datetime.fromtimestamp(int(raw.get("internalDate", 0)) / 1000, UTC),
        body_text=clean_untrusted(_extract_body(payload), body_chars),
    )


class GmailGateway:
    def __init__(self, service: Any, body_chars: int = 3000) -> None:
        self._messages = service.users().messages()
        self._labels = service.users().labels()
        self._body_chars = body_chars

    @classmethod
    def from_settings(cls, settings: GmailSettings, body_chars: int = 3000) -> GmailGateway:
        service = build(
            "gmail", "v1", credentials=build_credentials(settings), cache_discovery=False
        )
        return cls(service, body_chars)

    def list_unprocessed(self, limit: int, newer_than_days: int = 3) -> list[str]:
        response = _execute(
            self._messages.list(userId="me", q=build_query(newer_than_days), maxResults=limit)
        )
        return [m["id"] for m in response.get("messages", [])]

    def get(self, message_id: str) -> EmailMessage:
        raw = _execute(self._messages.get(userId="me", id=message_id, format="full"))
        return parse_message(raw, self._body_chars)

    def ensure_labels(self) -> dict[str, str]:
        """Create any missing Butler labels; return {label name: label id}."""
        existing = {
            label["name"]: label["id"]
            for label in _execute(self._labels.list(userId="me")).get("labels", [])
        }
        for name in (PARENT_LABEL, *GROUP_LABELS, PROCESSED_LABEL):
            if name not in existing:
                existing[name] = _execute(self._labels.create(userId="me", body=_label_body(name)))[
                    "id"
                ]
        return existing

    def add_labels(self, message_id: str, label_ids: list[str]) -> None:
        # addLabelIds only. This gateway never sends removeLabelIds.
        _execute(self._messages.modify(userId="me", id=message_id, body={"addLabelIds": label_ids}))


def _label_body(name: str) -> dict[str, Any]:
    hidden = name == PROCESSED_LABEL
    body: dict[str, Any] = {
        "name": name,
        "labelListVisibility": "labelHide" if hidden else "labelShow",
        "messageListVisibility": "hide" if hidden else "show",
    }
    if name in _COLORS:
        body["color"] = {"backgroundColor": _COLORS[name], "textColor": _WHITE}
    return body


def _execute(request: Any) -> dict[str, Any]:
    try:
        result: dict[str, Any] = request.execute()
    except RefreshError:
        raise GmailAuthError(
            "Gmail authorization expired or was revoked; run: uv run python -m scripts.gmail_auth"
        ) from None
    return result
