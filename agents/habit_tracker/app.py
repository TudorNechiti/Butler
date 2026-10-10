"""The two jobs: evening reminder and weekly report. Fetch -> compute -> notify.

No scheduler specifics here: `now` and `send` are passed in, so GitHub Actions, Azure Functions
and tests all call the same functions.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from agents.habit_tracker.config import HabitConfig
from agents.habit_tracker.models import ParseResult, logical_day, parse_rows
from agents.habit_tracker.report import ReportInput, build_report
from agents.habit_tracker.stats import compare_flag, trial_week, week_start, week_stats
from agents.habit_tracker.store import RowSource
from core.logging import EventLogger

Send = Callable[[str], None]

REMINDER_TEXT = "Evening check-in: today isn't logged yet. After dinner, log it here (20 s):\n{url}"

# Counts only: no values, dates or flag names.
log = EventLogger(__name__, allowed_fields={"job", "entries", "skipped", "flags", "sent"})


def _load(rows: RowSource, config: HabitConfig, job: str) -> ParseResult:
    result = parse_rows(rows.read_rows(), config.day_starts_at_hour)
    log.event(
        "sheet_read",
        job=job,
        entries=len(result.entries),
        skipped=result.skipped,
        flags=len(result.flag_names),
    )
    return result


def reminder(
    *, config: HabitConfig, rows: RowSource, send: Send, form_url: str, now: datetime
) -> bool:
    """Nudge only if today has no entry. `now` is naive local time. Returns whether it sent."""
    result = _load(rows, config, "reminder")
    today = logical_day(now, config.day_starts_at_hour)
    sent = not any(entry.day == today for entry in result.entries)
    if sent:
        send(REMINDER_TEXT.format(url=form_url))
    log.event("reminder_done", job="reminder", sent=sent)
    return sent


def weekly(*, config: HabitConfig, rows: RowSource, send: Send, now: datetime) -> str:
    """Report on the week containing `now` (Monday to today). Returns the text it sent."""
    result = _load(rows, config, "weekly")
    today = logical_day(now, config.day_starts_at_hour)
    # A mistyped future date must not count yet.
    entries = [e for e in result.entries if e.day <= today]
    targets = config.active_targets

    start = week_start(today)
    week = week_stats(entries, start, targets)
    previous = week_stats(entries, start - timedelta(days=7), targets)
    # Flag comparisons pool the whole trial: one week can never reach min_n in both groups.
    trial_entries = [e for e in entries if e.day >= config.trial_start]
    comparisons = [compare_flag(trial_entries, flag, config.min_n) for flag in result.flag_names]

    text = build_report(
        ReportInput(
            week=week,
            previous=previous,
            targets=targets,
            phase=config.active_phase,
            trial_week=trial_week(start, config.trial_start),
            through=today,
            comparisons=comparisons,
            min_n=config.min_n,
            skipped_rows=result.skipped,
        )
    )
    send(text)
    log.event("weekly_done", job="weekly", sent=True)
    return text
