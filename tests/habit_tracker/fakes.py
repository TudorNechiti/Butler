"""Fake sheet data. Obviously made-up values and flags only (tea, pushups), never real entries."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from agents.habit_tracker.config import HabitConfig, Targets
from agents.habit_tracker.models import Cell, Entry

HEADER: list[Cell] = [
    "Timestamp",
    "date",
    "golang_minutes",
    "leetcode_minutes",
    "german_minutes",
    "reading_minutes",
    "start_difficulty",
    "focus",
    "sleep_hours",
    "gym",
    "project_minutes",
    "video_minutes",
    "flag_tea",
    "notes",
]

MONDAY = date(2030, 1, 7)  # a Monday, far from any real data

TARGETS = Targets(
    study_days_per_week=5,
    min_minutes_day_counts=25,
    min_minutes_full_day=90,
    weekly_study_minutes=400,
    gym_sessions_per_week=3,
    sleep_hours_min=7.0,
    sleep_hours_aim=7.5,
    project_minutes_per_week=120,
    project_min_sessions=2,
    video_minutes_per_week=60,
    subject_minutes_per_week={"golang": 100, "leetcode": 100, "german": 100, "reading": 100},
)

CONFIG = HabitConfig(
    timezone="Europe/Berlin",
    day_starts_at_hour=4,
    trial_start=MONDAY,
    active_phase="phase1",
    reminder_hour=21,
    weekly_report_hour=20,
    min_n=3,
    targets={"phase1": TARGETS},
)


def serial(moment: datetime | date) -> float:
    """Inverse of models.serial_to_datetime: what the Sheets API returns for a date-time."""
    if not isinstance(moment, datetime):
        moment = datetime(moment.year, moment.month, moment.day)
    return (moment - datetime(1899, 12, 30)).total_seconds() / 86400


def row(
    submitted: datetime,
    *,
    golang: Cell = 30,
    leetcode: Cell = "",
    german: Cell = "",
    reading: Cell = 20,
    difficulty: Cell = 3,
    focus: Cell = 4,
    sleep: Cell = 7.5,
    gym: Cell = "no",
    project: Cell = "",
    video: Cell = "",
    tea: Cell = "no",
    day: date | None = None,
) -> list[Cell]:
    return [
        serial(submitted),
        "" if day is None else round(serial(day)),
        golang,
        leetcode,
        german,
        reading,
        difficulty,
        focus,
        sleep,
        gym,
        project,
        video,
        tea,
        "a private note",
    ]


def evening(day: date, hour: int = 21) -> datetime:
    return datetime(day.year, day.month, day.day, hour)


def entry(day: date, **overrides: Any) -> Entry:
    fields: dict[str, Any] = {
        "day": day,
        "submitted_at": evening(day),
        "subject_minutes": {"golang": 30, "leetcode": 0, "german": 0, "reading": 20},
        "start_difficulty": 3,
        "focus": 4,
        "sleep_hours": 7.5,
        "gym": False,
        "project_minutes": 0,
        "video_minutes": 0,
        "flags": {"tea": False},
    }
    fields.update(overrides)
    return Entry(**fields)


def days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


class FakeRows:
    def __init__(self, rows: Sequence[Sequence[Cell]] | Exception) -> None:
        self._rows = rows

    def read_rows(self) -> Sequence[Sequence[Cell]]:
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows


class FakeSend:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, text: str) -> None:
        self.messages.append(text)
