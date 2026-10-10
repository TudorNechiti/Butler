"""Weekly report text. Plain code, no LLM: it describes what happened and gives no advice.

The text goes to a private Telegram chat only. It contains personal numbers, so it is never
logged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from agents.habit_tracker.config import Targets
from agents.habit_tracker.models import SUBJECTS
from agents.habit_tracker.stats import Comparison, WeekStats

CAVEAT = "Hints, not proof: sleep, workload and other things change at the same time."
SUBJECT_NAMES = {"golang": "Go", "leetcode": "LeetCode", "german": "German", "reading": "Reading"}


@dataclass(frozen=True)
class ReportInput:
    week: WeekStats
    previous: WeekStats
    targets: Targets
    phase: str
    trial_week: int
    through: date  # last day included; earlier than week.end for a partial week
    comparisons: Sequence[Comparison]
    min_n: int
    skipped_rows: int


def _delta(current: float | None, previous: float | None, decimals: int = 0) -> str:
    if current is None or previous is None:
        return ""
    diff = current - previous
    return f" ({diff:+.{decimals}f})"


def _percent(value: int, target: int) -> str:
    return f"{round(100 * value / target)}%" if target else "-"


def _title(r: ReportInput) -> str:
    week = f"trial week {r.trial_week}" if r.trial_week >= 1 else "before the trial"
    partial = f", through {r.through:%a}" if r.through < r.week.end else ""
    return f"Habit report, week of {r.week.start:%d %b} ({week}, {r.phase}{partial})"


def _study_lines(r: ReportInput) -> list[str]:
    w, p, t = r.week, r.previous, r.targets
    prev_minutes = p.study_minutes if p.days_logged else None
    lines = [
        f"Study     {w.study_minutes}/{t.weekly_study_minutes} min "
        f"({_percent(w.study_minutes, t.weekly_study_minutes)})"
        f"{_delta(w.study_minutes, prev_minutes)}",
        f"          {w.study_days}/{t.study_days_per_week} study days (>= "
        f"{t.min_minutes_day_counts} min), {w.full_days} full days (>= "
        f"{t.min_minutes_full_day} min)",
    ]
    for subject in SUBJECTS:
        target = t.subject_minutes_per_week[subject]
        lines.append(
            f"  {SUBJECT_NAMES[subject]:<9}{w.subject_minutes[subject]:>4}/{target} min, "
            f"{w.subject_days[subject]} days"
        )
    return lines


def _body_lines(r: ReportInput) -> list[str]:
    w, p, t = r.week, r.previous, r.targets
    lines = [
        f"Gym       {w.gym_sessions}/{t.gym_sessions_per_week}"
        f"{_delta(w.gym_sessions, p.gym_sessions if p.days_logged else None)}"
    ]
    if w.sleep is None:
        lines.append("Sleep     no data")
    else:
        prev_sleep = p.sleep.mean if p.sleep else None
        lines.append(
            f"Sleep     avg {w.sleep.mean:.1f}h (min {t.sleep_hours_min:g}, aim "
            f"{t.sleep_hours_aim:g}){_delta(w.sleep.mean, prev_sleep, 1)}, range "
            f"{w.sleep.low:g}-{w.sleep.high:g}, {w.nights_below_min} nights under "
            f"{t.sleep_hours_min:g}h"
        )
    if w.focus_mean is not None and w.start_difficulty_mean is not None:
        lines.append(
            f"Focus     avg {w.focus_mean:.1f}/5{_delta(w.focus_mean, p.focus_mean, 1)}, "
            f"start difficulty avg {w.start_difficulty_mean:.1f}/5"
            f"{_delta(w.start_difficulty_mean, p.start_difficulty_mean, 1)}"
        )
    return lines


def _side_lines(r: ReportInput) -> list[str]:
    w, t = r.week, r.targets
    return [
        f"Project   {w.project_minutes}/{t.project_minutes_per_week} min, "
        f"{w.project_sessions}/{t.project_min_sessions} sessions",
        f"Videos    {w.video_minutes}/{t.video_minutes_per_week} min",
    ]


def _comparison_lines(r: ReportInput) -> list[str]:
    if not r.comparisons:
        return []
    lines = ["", "Flags, since trial start (with vs without):"]
    for c in r.comparisons:
        n = f"n={c.n_with} vs {c.n_without}"
        if not c.shown:
            lines.append(f"  {c.flag}: not enough days to compare ({n}, need {r.min_n} each)")
            continue
        lines.append(
            f"  {c.flag}: focus {c.focus_with:.1f} vs {c.focus_without:.1f}, "
            f"study {c.study_with:.0f} vs {c.study_without:.0f} min ({n})"
        )
    return lines


def build_report(r: ReportInput) -> str:
    days_in_view = (r.through - r.week.start).days + 1
    lines = [_title(r), f"Logged {r.week.days_logged}/{days_in_view} days", ""]
    if r.week.days_logged == 0:
        lines.append("No entries this week.")
    else:
        lines += _study_lines(r) + _body_lines(r) + _side_lines(r)
        lines += _comparison_lines(r)
    if r.previous.days_logged == 0:
        lines += ["", "No entries last week, so no changes shown."]
    lines += ["", CAVEAT]
    if r.skipped_rows:
        lines.append(f"{r.skipped_rows} sheet rows skipped as invalid (check the sheet).")
    return "\n".join(lines)
