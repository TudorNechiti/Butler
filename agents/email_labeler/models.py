from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    DEBTS = "debts"
    PAYMENTS = "payments"
    REMINDERS = "reminders"
    JOBS = "jobs"
    OTHER = "other"


@dataclass(frozen=True)
class EmailMessage:
    """One email, already sanitised: plain text, no hidden characters, bounded length."""

    id: str
    thread_id: str
    sender: str
    subject: str
    received_at: datetime
    body_text: str


class Classification(BaseModel):
    """What Claude returns (structured output).

    Limits are stated in the descriptions rather than as schema constraints. The API doesn't
    enforce min/max, and a client-side validation error would fail the whole email. The
    classifier clamps and truncates instead.
    """

    category: Category
    confidence: float = Field(description="How sure you are, from 0.0 to 1.0.")
    reason: str = Field(description="At most 15 words. Do not quote the email or include links.")
