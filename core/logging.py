"""JSON logging with a per-agent field allowlist.

Agents handle personal, untrusted data (email). A log line may only carry fields the agent
explicitly allows, such as ids, counts and categories. Any other field raises at the call site, so a
careless `log.event("x", subject=...)` fails in tests instead of leaking into CI logs.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable
from datetime import UTC, datetime

type Scalar = str | int | float | bool | None

# Libraries that log request URLs or payloads at INFO/DEBUG. httpx, for example, logs the
# full Telegram URL, which contains the bot token.
_NOISY_LOGGERS = ("httpx", "httpx2", "httpcore", "httpcore2", "anthropic", "googleapiclient")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        else:
            # Third-party records only; those loggers are capped at WARNING.
            payload["message"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


class EventLogger:
    """Structured logger that only accepts allowlisted, scalar fields."""

    def __init__(self, name: str, allowed_fields: Iterable[str]) -> None:
        self._logger = logging.getLogger(name)
        self._allowed = frozenset(allowed_fields) | {"error_type"}

    def event(self, event: str, level: int = logging.INFO, **fields: Scalar) -> None:
        unknown = fields.keys() - self._allowed
        if unknown:
            raise ValueError(f"fields not allowed in logs: {sorted(unknown)}")
        for key, value in fields.items():
            if not isinstance(value, str | int | float | bool | None):
                raise TypeError(f"log field {key!r} must be a scalar, got {type(value).__name__}")
        self._logger.log(level, event, extra={"event_fields": {"event": event, **fields}})

    def error(self, event: str, exc: BaseException, **fields: Scalar) -> None:
        """Log an error by type only. Exception messages can embed untrusted content."""
        self.event(event, level=logging.ERROR, error_type=type(exc).__name__, **fields)
