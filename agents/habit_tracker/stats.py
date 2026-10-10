"""Weekly numbers and flag comparisons. Pure functions: entries in, numbers out.

Missing days stay missing: means are over logged days only, and the report always shows how
many days that was.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import fmean

from agents.habit_tracker.config import Targets
from agents.habit_tracker.models import SUBJECTS, Entry


@dataclass(frozen=True)
class Range:
    mean: float
    low: float
    high: float


@dataclass(frozen=True)
class WeekStats:
    start: date
    days_logged: int
    study_minutes: int
    study_days: int  # days with at least min_minutes_day_counts
    full_days: int  # days with at least min_minutes_full_day
    subject_minutes: dict[str, int]
    subject_days: dict[str, int]
    gym_sessions: int
    sleep: Range | None  # None when nothing was logged
    nights_below_min: int
    start_difficulty_mean: float | None
    focus_mean: float | None
    project_minutes: int
    project_sessions: int
    video_minutes: int

    @property
    def end(self) -> date:
        return self.start + timedelta(days=6)


@dataclass(frozen=True)
class Comparison:
    """A metric on days with a flag versus days without it."""

    flag: str
    n_with: int
    n_without: int
    focus_with: float | None  # None when either group is below min_n
    focus_without: float | None
    study_with: float | None
    study_without: float | None

    @property
    def shown(self) -> bool:
        return self.focus_with is not None


def week_start(day: date) -> date:
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())


def trial_week(start: date, trial_start: date) -> int:
    """1-based week number in the trial; 0 or less means before the trial."""
    return (start - trial_start).days // 7 + 1


def _range(values: Sequence[float]) -> Range | None:
    if not values:
        return None
    return Range(mean=fmean(values), low=min(values), high=max(values))


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def week_stats(entries: Sequence[Entry], start: date, targets: Targets) -> WeekStats:
    week = [e for e in entries if start <= e.day <= start + timedelta(days=6)]
    return WeekStats(
        start=start,
        days_logged=len(week),
        study_minutes=sum(e.study_minutes for e in week),
        study_days=sum(e.study_minutes >= targets.min_minutes_day_counts for e in week),
        full_days=sum(e.study_minutes >= targets.min_minutes_full_day for e in week),
        subject_minutes={s: sum(e.subject_minutes[s] for e in week) for s in SUBJECTS},
        subject_days={s: sum(e.subject_minutes[s] > 0 for e in week) for s in SUBJECTS},
        gym_sessions=sum(e.gym for e in week),
        sleep=_range([e.sleep_hours for e in week]),
        nights_below_min=sum(e.sleep_hours < targets.sleep_hours_min for e in week),
        start_difficulty_mean=_mean([e.start_difficulty for e in week]),
        focus_mean=_mean([e.focus for e in week]),
        project_minutes=sum(e.project_minutes for e in week),
        project_sessions=sum(e.project_minutes > 0 for e in week),
        video_minutes=sum(e.video_minutes for e in week),
    )


def _group_mean(group: Sequence[Entry], metric: Callable[[Entry], float]) -> float:
    return fmean(metric(e) for e in group)


def compare_flag(entries: Sequence[Entry], flag: str, min_n: int) -> Comparison:
    """Compare focus and study minutes on days with vs without a flag.

    Means are only computed when both groups have at least `min_n` days. Below that the
    difference is mostly noise, so the report says so instead of showing a number.
    """
    with_flag = [e for e in entries if e.flags.get(flag) is True]
    without = [e for e in entries if e.flags.get(flag) is False]
    if len(with_flag) < min_n or len(without) < min_n:
        return Comparison(flag, len(with_flag), len(without), None, None, None, None)
    return Comparison(
        flag=flag,
        n_with=len(with_flag),
        n_without=len(without),
        focus_with=_group_mean(with_flag, lambda e: e.focus),
        focus_without=_group_mean(without, lambda e: e.focus),
        study_with=_group_mean(with_flag, lambda e: e.study_minutes),
        study_without=_group_mean(without, lambda e: e.study_minutes),
    )
