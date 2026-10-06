"""One run of the email labeler: fetch -> classify -> label, plus failure alerts.

Plain function, no framework. Claude only picks a category; this code decides what happens.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from agents.email_labeler.classifier import StructuredLLM, classify
from agents.email_labeler.gmail import (
    PROCESSED_LABEL,
    REVIEW_LABEL,
    GmailAuthError,
    category_label,
)
from agents.email_labeler.models import Classification, EmailMessage
from core.config import load_toml
from core.llm import CallLimitExceeded, LLMError
from core.logging import EventLogger

CONFIG_PATH = Path(__file__).parent / "config.toml"

log = EventLogger(
    __name__,
    allowed_fields={
        "message_id",
        "label",
        "confidence_bucket",
        "dry_run",
        "fetched",
        "labeled",
        "review",
        "failed",
        "duration_s",
    },
)


class LabelerConfig(BaseModel):
    model: str
    max_tokens: int
    max_items: int
    newer_than_days: int
    body_chars: int
    review_threshold: float


def load_config(path: Path = CONFIG_PATH) -> LabelerConfig:
    return LabelerConfig.model_validate(load_toml(path))


class Mailbox(Protocol):
    """What the run needs from GmailGateway."""

    def list_unprocessed(self, limit: int, newer_than_days: int = 3) -> list[str]: ...
    def get(self, message_id: str) -> EmailMessage: ...
    def ensure_labels(self) -> dict[str, str]: ...
    def add_labels(self, message_id: str, label_ids: list[str]) -> None: ...


Alert = Callable[[str], None]
# Called for every classified email. Only used by the local --preview mode.
OnResult = Callable[[EmailMessage, str, Classification | None], None]


@dataclass
class RunStats:
    fetched: int = 0
    labeled: Counter[str] = field(default_factory=Counter)
    failed: int = 0

    @property
    def processed(self) -> int:
        return sum(self.labeled.values())


def choose_label(result: Classification, review_threshold: float) -> str:
    if result.confidence < review_threshold:
        return REVIEW_LABEL
    return category_label(result.category)


def _confidence_bucket(confidence: float, review_threshold: float) -> str:
    if confidence >= 0.9:
        return "high"
    return "medium" if confidence >= review_threshold else "low"


def run(
    *,
    config: LabelerConfig,
    mailbox: Mailbox,
    llm: StructuredLLM,
    system_prompt: str,
    alert: Alert,
    dry_run: bool,
    max_items: int | None = None,
    on_result: OnResult | None = None,
) -> RunStats:
    started = time.monotonic()
    stats = RunStats()
    try:
        ids = mailbox.list_unprocessed(max_items or config.max_items, config.newer_than_days)
        # Creating labels is a write, so a dry run skips it.
        label_ids = {} if dry_run else mailbox.ensure_labels()
    except GmailAuthError as exc:
        _safe_alert(alert, f"Butler email labeler: {exc}")
        raise
    stats.fetched = len(ids)

    for message_id in ids:
        try:
            email = mailbox.get(message_id)
            try:
                result: Classification | None = classify(llm, system_prompt, email)
            except CallLimitExceeded:
                raise
            except LLMError as exc:
                # Refusal, truncation or unparseable output: deterministic, so retrying would
                # just pay again. Park it in Review instead.
                log.error("classify_rejected", exc, message_id=message_id)
                result = None
            label = (
                REVIEW_LABEL if result is None else choose_label(result, config.review_threshold)
            )
            if not dry_run:
                mailbox.add_labels(message_id, [label_ids[label], label_ids[PROCESSED_LABEL]])
        except CallLimitExceeded:
            log.event("call_limit_reached", message_id=message_id)
            break
        except GmailAuthError as exc:
            _safe_alert(alert, f"Butler email labeler: {exc}")
            raise
        except Exception as exc:
            # Transient (network, API 5xx after SDK retries): leave it unprocessed so the next
            # run retries. newer_than_days bounds how long that can go on.
            stats.failed += 1
            log.error("email_failed", exc, message_id=message_id)
            continue

        stats.labeled[label] += 1
        bucket = _confidence_bucket(result.confidence, config.review_threshold) if result else "low"
        log.event(
            "email_labeled",
            message_id=message_id,
            label=label,
            confidence_bucket=bucket,
            dry_run=dry_run,
        )
        if on_result is not None:
            on_result(email, label, result)

    log.event(
        "run_finished",
        dry_run=dry_run,
        fetched=stats.fetched,
        labeled=stats.processed,
        review=stats.labeled[REVIEW_LABEL],
        failed=stats.failed,
        duration_s=round(time.monotonic() - started, 1),
    )
    if stats.fetched and stats.failed == stats.fetched:
        _safe_alert(
            alert,
            f"Butler email labeler: all {stats.failed} emails failed this run. Check the logs.",
        )
    return stats


def _safe_alert(alert: Alert, text: str) -> None:
    """An alert failure must never hide the original problem."""
    try:
        alert(text)
    except Exception as exc:
        log.error("alert_failed", exc)
