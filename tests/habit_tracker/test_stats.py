from datetime import date

from agents.habit_tracker.stats import compare_flag, trial_week, week_start, week_stats
from tests.habit_tracker.fakes import MONDAY, TARGETS, days, entry


def test_week_start_and_trial_week() -> None:
    assert week_start(date(2030, 1, 13)) == MONDAY  # Sunday -> its Monday
    assert trial_week(MONDAY, MONDAY) == 1
    assert trial_week(date(2030, 1, 14), MONDAY) == 2
    assert trial_week(date(2029, 12, 31), MONDAY) == 0


def test_week_stats_for_a_fake_week() -> None:
    mon, tue, wed, *_ = days(MONDAY, 7)
    entries = [
        entry(
            mon,
            subject_minutes={"golang": 60, "leetcode": 40, "german": 0, "reading": 0},
            gym=True,
            sleep_hours=6.5,
            focus=4,
            start_difficulty=2,
            project_minutes=60,
        ),
        entry(
            tue,
            subject_minutes={"golang": 0, "leetcode": 0, "german": 10, "reading": 10},
            sleep_hours=8.0,
            focus=2,
            start_difficulty=4,
        ),
        entry(
            wed,
            subject_minutes={"golang": 30, "leetcode": 0, "german": 0, "reading": 0},
            gym=True,
            sleep_hours=7.5,
            focus=3,
            start_difficulty=3,
            video_minutes=30,
        ),
        entry(date(2030, 1, 14)),  # next week: excluded
    ]

    w = week_stats(entries, MONDAY, TARGETS)

    assert w.days_logged == 3
    assert w.study_minutes == 150
    assert w.study_days == 1 + 0 + 1  # 100 and 30 count (>= 25), 20 doesn't
    assert w.full_days == 1  # only 100 >= 90
    assert w.subject_minutes == {"golang": 90, "leetcode": 40, "german": 10, "reading": 10}
    assert w.subject_days == {"golang": 2, "leetcode": 1, "german": 1, "reading": 1}
    assert w.gym_sessions == 2
    assert w.sleep is not None
    assert (w.sleep.mean, w.sleep.low, w.sleep.high) == (7.333333333333333, 6.5, 8.0)
    assert w.nights_below_min == 1
    assert w.focus_mean == 3.0
    assert w.start_difficulty_mean == 3.0
    assert (w.project_minutes, w.project_sessions, w.video_minutes) == (60, 1, 30)


def test_empty_week_reports_missing_not_zero() -> None:
    w = week_stats([], MONDAY, TARGETS)
    assert w.days_logged == 0
    assert w.sleep is None
    assert w.focus_mean is None


def test_comparison_hidden_below_min_n() -> None:
    entries = [entry(d, flags={"tea": i < 2}) for i, d in enumerate(days(MONDAY, 10))]
    c = compare_flag(entries, "tea", min_n=3)
    assert (c.n_with, c.n_without) == (2, 8)
    assert not c.shown
    assert c.focus_with is None


def test_comparison_shown_with_enough_days() -> None:
    entries = [
        entry(d, flags={"tea": i % 2 == 0}, focus=5 if i % 2 == 0 else 3)
        for i, d in enumerate(days(MONDAY, 8))
    ]
    c = compare_flag(entries, "tea", min_n=3)
    assert c.shown
    assert (c.n_with, c.n_without) == (4, 4)
    assert (c.focus_with, c.focus_without) == (5.0, 3.0)
    assert c.study_with == c.study_without == 50.0
