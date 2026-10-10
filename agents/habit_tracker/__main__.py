"""CLI: python -m agents.habit_tracker {reminder,weekly} [--dry-run] [--force]

Cron runs in UTC, so each workflow is scheduled at both UTC hours that can map to the local
target hour. Without --force, a run exits quietly unless the local hour matches.

Exit codes: 0 ok (or not due), 2 the sheet could not be read.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.habit_tracker.app import reminder, weekly
from agents.habit_tracker.config import HabitSettings, load_config
from agents.habit_tracker.models import MissingColumnsError
from agents.habit_tracker.store import SheetReadError, SheetsStore
from core.logging import EventLogger, configure_logging
from core.telegram import TelegramClient

log = EventLogger(__name__, allowed_fields={"job", "local_hour"})


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agents.habit_tracker")
    parser.add_argument("job", choices=["reminder", "weekly"])
    parser.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    parser.add_argument("--force", action="store_true", help="run now, ignore the scheduled hour")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.dry_run and os.environ.get("CI"):
        # Actions logs of a public repo are public; a printed report would leak personal data.
        sys.exit("--dry-run prints personal data and is disabled in CI.")
    configure_logging()
    config = load_config()
    now = datetime.now(ZoneInfo(config.timezone)).replace(tzinfo=None)

    due_hour = config.reminder_hour if args.job == "reminder" else config.weekly_report_hour
    due_day = args.job == "reminder" or now.weekday() == 6  # weekly: Sunday only
    if not args.force and not (due_day and now.hour == due_hour):
        log.event("not_due", job=args.job, local_hour=now.hour)
        return 0

    settings = HabitSettings()  # type: ignore[call-arg]
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    send = print if args.dry_run else telegram.send_message

    try:
        rows = SheetsStore.from_settings(settings)
        if args.job == "reminder":
            reminder(
                config=config,
                rows=rows,
                send=send,
                form_url=settings.habit_form_url.get_secret_value(),
                now=now,
            )
        else:
            weekly(config=config, rows=rows, send=send, now=now)
    except (SheetReadError, MissingColumnsError) as exc:
        log.error("sheet_unreadable", exc, job=args.job)
        # Both messages hold only column names or HTTP status, never sheet content.
        send(f"Butler habit tracker: can't read the sheet ({exc}).")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
