"""CLI: python -m agents.habit_tracker {reminder,weekly} [--scheduled CRON] [--dry-run] [--force]

Cron runs in UTC, so each workflow is scheduled at both UTC hours that can map to the local
target hour. Without --force, a run exits quietly unless the local hour matches. With
--scheduled (the cron line that fired), that hour is the scheduled one, not the start time:
GitHub often starts scheduled runs hours late.

Exit codes: 0 ok (or not due), 2 the sheet could not be read. On GitHub Actions the outcome
(sent, nothing to send, not due, started late) is also shown on the run's page.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.habit_tracker.app import reminder, weekly
from agents.habit_tracker.config import HabitSettings, load_config
from agents.habit_tracker.models import MissingColumnsError
from agents.habit_tracker.schedule import scheduled_local_time
from agents.habit_tracker.store import SheetReadError, SheetsStore
from core import ci
from core.logging import EventLogger, configure_logging
from core.telegram import TelegramClient

log = EventLogger(__name__, allowed_fields={"job", "local_hour", "delay_minutes"})

# GitHub's delays are usually minutes; past this the run page gets a warning, so a pattern of
# late starts is visible without reading logs.
LATE_AFTER = timedelta(hours=1)


def _due_text(job: str, hour: int) -> str:
    if job == "reminder":
        return f"the reminder goes out at {hour:02d}:00"
    return f"the weekly report goes out on Sundays at {hour:02d}:00"


def _hours_minutes(delay: timedelta) -> str:
    minutes = int(delay.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agents.habit_tracker")
    parser.add_argument("job", choices=["reminder", "weekly"])
    parser.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    parser.add_argument("--force", action="store_true", help="run now, ignore the scheduled hour")
    parser.add_argument(
        "--scheduled", metavar="CRON", help="cron line that fired (UTC); decides the due hour"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.dry_run and os.environ.get("CI"):
        # Actions logs of a public repo are public; a printed report would leak personal data.
        sys.exit("--dry-run prints personal data and is disabled in CI.")
    configure_logging()
    config = load_config()
    now_utc = datetime.now(UTC)
    now = now_utc.astimezone(ZoneInfo(config.timezone)).replace(tzinfo=None)
    delay: timedelta | None = None
    if args.scheduled and not args.force:
        # Act as of the scheduled moment, so a late start still checks the intended day.
        scheduled = scheduled_local_time(args.scheduled, now_utc, config.timezone)
        delay = now - scheduled
        log.event("schedule", job=args.job, delay_minutes=int(delay.total_seconds() // 60))
        now = scheduled

    due_hour = config.reminder_hour if args.job == "reminder" else config.weekly_report_hour
    due_day = args.job == "reminder" or now.weekday() == 6  # weekly: Sunday only
    if not args.force and not (due_day and now.hour == due_hour):
        log.event("not_due", job=args.job, local_hour=now.hour)
        ci.note(
            f"Skipped: this run is for {now:%a %H:%M}, but {_due_text(args.job, due_hour)} "
            f"({config.timezone}). The job is scheduled at two times so one run lands on that "
            "time in both summer and winter; the other run always skips. Nothing is wrong."
        )
        return 0

    if delay is not None and delay > LATE_AFTER:
        ci.note(
            f"GitHub started this run {_hours_minutes(delay)} late (scheduled for "
            f"{now:%H:%M} {config.timezone}). Messages arrive that much later.",
            level="warning",
        )

    settings = HabitSettings()  # type: ignore[call-arg]
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    send = print if args.dry_run else telegram.send_message

    try:
        rows = SheetsStore.from_settings(settings)
        if args.job == "reminder":
            sent = reminder(
                config=config,
                rows=rows,
                send=send,
                form_url=settings.habit_form_url.get_secret_value(),
                now=now,
            )
            ci.note("Reminder sent." if sent else "No reminder needed: today is already logged.")
        else:
            weekly(config=config, rows=rows, send=send, now=now)
            ci.note("Weekly report sent.")
    except (SheetReadError, MissingColumnsError) as exc:
        log.error("sheet_unreadable", exc, job=args.job)
        # Both messages hold only column names or HTTP status, never sheet content.
        send(f"Butler habit tracker: can't read the sheet ({exc}).")
        ci.note(f"Can't read the sheet ({exc}).", level="error")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
