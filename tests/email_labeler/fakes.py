"""Test doubles for the email labeler. No network, no cost."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from agents.email_labeler.models import Category, Classification, EmailMessage


class FakeLLM:
    """Returns queued classifications (or raises queued errors) and records each prompt."""

    def __init__(self, responses: list[Classification | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def parse[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return schema.model_validate(response.model_dump())


def make_email(
    body: str = "Your invoice of 40 EUR is due on 1 May.",
    subject: str = "Invoice 2024-17",
    sender: str = "billing@example.com",
    id: str = "msg-1",
) -> EmailMessage:
    return EmailMessage(
        id=id,
        thread_id=f"thread-{id}",
        sender=sender,
        subject=subject,
        received_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        body_text=body,
    )


def classification(
    category: Category = Category.DEBTS, confidence: float = 0.95, reason: str = "Unpaid invoice"
) -> Classification:
    return Classification(category=category, confidence=confidence, reason=reason)
