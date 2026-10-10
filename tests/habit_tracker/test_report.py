from datetime import timedelta

from agents.habit_tracker.report import CAVEAT, ReportInput, build_report
from agents.habit_tracker.stats import Comparison, week_stats
from tests.habit_tracker.fakes import MONDAY, TARGETS, days, entry

SUNDAY = MONDAY + timedelta(days=6)


def _input(**overrides: object) -> ReportInput:
    this_week = [entry(d, gym=True) for d in days(MONDAY, 3)]
    last_week = [entry(d - timedelta(days=7), focus=3) for d in days(MONDAY, 2)]
    fields: dict[str, object] = {
        "week": week_stats(this_week, MONDAY, TARGETS),
        "previous": week_stats(last_week, MONDAY - timedelta(days=7), TARGETS),
        "targets": TARGETS,
        "phase": "phase1",
        "trial_week": 2,
        "through": SUNDAY,
        "comparisons": [],
        "min_n": 3,
        "skipped_rows": 0,
    }
    fields.update(overrides)
    return ReportInput(**fields)  # type: ignore[arg-type]


def test_report_shows_counts_targets_and_deltas() -> None:
    text = build_report(_input())

    assert "trial week 2, phase1" in text
    assert "Logged 3/7 days" in text
    assert "Study     150/400 min (38%) (+50)" in text
    assert "3/5 study days" in text
    assert "Go         90/100 min, 3 days" in text
    assert "Gym       3/3 (+3)" in text
    assert "Focus     avg 4.0/5 (+1.0)" in text
    assert text.rstrip().endswith(CAVEAT)


def test_partial_week_is_labelled() -> None:
    text = build_report(_input(through=MONDAY + timedelta(days=3)))
    assert "through Thu" in text
    assert "Logged 3/4 days" in text


def test_no_previous_week_means_no_deltas() -> None:
    empty = week_stats([], MONDAY - timedelta(days=7), TARGETS)
    text = build_report(_input(previous=empty))
    assert "(+" not in text
    assert "No entries last week" in text


def test_empty_week() -> None:
    text = build_report(_input(week=week_stats([], MONDAY, TARGETS)))
    assert "No entries this week." in text
    assert "Study" not in text


def test_comparisons_always_show_n() -> None:
    comparisons = [
        Comparison("tea", 2, 9, None, None, None, None),
        Comparison("pushups", 4, 5, 4.25, 3.0, 80.0, 45.5),
    ]
    text = build_report(_input(comparisons=comparisons))
    assert "tea: not enough days to compare (n=2 vs 9, need 3 each)" in text
    assert "pushups: focus 4.2 vs 3.0, study 80 vs 46 min (n=4 vs 5)" in text


def test_skipped_rows_are_reported() -> None:
    assert "2 sheet rows skipped" in build_report(_input(skipped_rows=2))
