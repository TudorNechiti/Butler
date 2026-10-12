from datetime import UTC, datetime

import pytest

from agents.habit_tracker.schedule import scheduled_local_time

BERLIN = "Europe/Berlin"


def test_summer_slot_maps_to_21_berlin_even_when_started_late() -> None:
    started = datetime(2030, 7, 1, 22, 40, tzinfo=UTC)  # 3.5 h late
    assert scheduled_local_time("7 19 * * *", started, BERLIN) == datetime(2030, 7, 1, 21, 7)


def test_winter_slot_maps_to_21_berlin() -> None:
    started = datetime(2030, 1, 7, 20, 9, tzinfo=UTC)
    assert scheduled_local_time("7 20 * * *", started, BERLIN) == datetime(2030, 1, 7, 21, 7)


def test_only_one_slot_matches_the_due_hour() -> None:
    started = datetime(2030, 1, 7, 23, 0, tzinfo=UTC)
    hours = {scheduled_local_time(c, started, BERLIN).hour for c in ("7 19 * * *", "7 20 * * *")}
    assert hours == {20, 21}


def test_start_after_utc_midnight_belongs_to_the_day_before() -> None:
    started = datetime(2030, 1, 8, 0, 30, tzinfo=UTC)  # Tuesday UTC, run was Monday's
    assert scheduled_local_time("7 20 * * *", started, BERLIN) == datetime(2030, 1, 7, 21, 7)


def test_weekly_sunday_slot_stays_on_sunday() -> None:
    started = datetime(2030, 1, 13, 23, 50, tzinfo=UTC)  # 00:50 Monday in Berlin
    fired = scheduled_local_time("13 19 * * 0", started, BERLIN)
    assert fired == datetime(2030, 1, 13, 20, 13)
    assert fired.weekday() == 6


@pytest.mark.parametrize("cron", ["", "*/5 * * * *", "7 19 * *", "0 9-17 * * *"])
def test_rejects_unsupported_lines(cron: str) -> None:
    with pytest.raises(ValueError):
        scheduled_local_time(cron, datetime(2030, 1, 7, tzinfo=UTC), BERLIN)
