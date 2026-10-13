"""Show a run's outcome on its GitHub Actions page.

Exit codes only say whether a job worked. A job can work and still send nothing (already done,
not due yet), so the outcome is shown as a short note: an annotation on the run plus a line in
the run summary. Outside GitHub Actions these functions do nothing.

The repo is public, so its Actions pages are too: pass fixed texts, counts and times only, never
personal data.
"""

from __future__ import annotations

import os
from typing import Literal

type Level = Literal["notice", "warning", "error"]

_ICONS: dict[Level, str] = {"notice": "ℹ️", "warning": "⚠️", "error": "❌"}  # noqa: RUF001


def _escape(text: str) -> str:
    # Workflow commands are one line; GitHub decodes these escapes back.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def note(text: str, level: Level = "notice") -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    print(f"::{level}::{_escape(text)}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"{_ICONS[level]} {text}\n\n")
