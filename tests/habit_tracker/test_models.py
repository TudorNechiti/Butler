from datetime import date, datetime

import pytest

from agents.habit_tracker.models import (
    InvalidCell,
    MissingColumnsError,
    logical_day,
    parse_float,
    parse_int,
    parse_rows,
    parse_yes_no,
    serial_to_datetime,
)
from tests.habit_tracker.fakes import HEADER, MONDAY, evening, row, serial


def test_serial_round_trip() -> None:
    moment = datetime(2030, 1, 7, 21, 15, 30)
    assert serial_to_datetime(serial(moment)) == moment


def test_parses_a_valid_row_and_derives_study_minutes() -> None:
    result = parse_rows([HEADER, row(evening(MONDAY), golang=45, german="15")], 4)

    [entry] = result.entries
    assert entry.day == MONDAY
    assert entry.subject_minutes == {"golang": 45, "leetcode": 0, "german": 15, "reading": 20}
    assert entry.study_minutes == 80
    assert entry.gym is False
    assert entry.project_minutes == 0  # blank optional -> 0
    assert entry.flags == {"tea": False}
    assert result.flag_names == ["tea"]
    assert result.skipped == 0


def test_after_midnight_counts_for_the_previous_day() -> None:
    late = datetime(2030, 1, 8, 0, 30)  # Tuesday 00:30
    result = parse_rows([HEADER, row(late)], day_starts_at_hour=4)
    assert result.entries[0].day == MONDAY


def test_explicit_date_overrides_timestamp() -> None:
    result = parse_rows([HEADER, row(evening(date(2030, 1, 10)), day=MONDAY)], 4)
    assert result.entries[0].day == MONDAY


def test_logical_day_boundary() -> None:
    assert logical_day(datetime(2030, 1, 8, 3, 59), 4) == MONDAY
    assert logical_day(datetime(2030, 1, 8, 4, 0), 4) == date(2030, 1, 8)


def test_latest_submission_per_day_wins() -> None:
    first = row(evening(MONDAY, 20), focus=2)
    correction = row(evening(MONDAY, 22), focus=5)
    result = parse_rows([HEADER, correction, first], 4)  # order in the sheet doesn't matter
    [entry] = result.entries
    assert entry.focus == 5


def test_invalid_rows_are_skipped_and_counted() -> None:
    rows = [
        HEADER,
        row(evening(MONDAY), focus=9),  # out of range
        row(evening(date(2030, 1, 8)), sleep=""),  # required
        row(evening(date(2030, 1, 9)), gym="maybe"),
        row(evening(date(2030, 1, 10))),
    ]
    result = parse_rows(rows, 4)
    assert result.skipped == 3
    assert [e.day for e in result.entries] == [date(2030, 1, 10)]


def test_short_and_blank_rows() -> None:
    # The API drops trailing empty cells; a deleted response leaves an empty row.
    short = row(evening(MONDAY))[:10]
    result = parse_rows([HEADER, short, ["", ""]], 4)
    assert result.skipped == 1  # flag_tea is required once the column exists
    short_no_flags = parse_rows([HEADER[:12], row(evening(MONDAY))[:10]], 4)
    assert short_no_flags.skipped == 0
    assert short_no_flags.entries[0].video_minutes == 0


def test_missing_column_fails_loudly_with_its_name() -> None:
    header = [title for title in HEADER if title != "focus"]
    with pytest.raises(MissingColumnsError) as excinfo:
        parse_rows([header], 4)
    assert excinfo.value.missing == ["focus"]


def test_empty_sheet_is_missing_every_column() -> None:
    with pytest.raises(MissingColumnsError):
        parse_rows([], 4)


def test_unknown_and_stale_columns_are_ignored() -> None:
    header = [*HEADER, "study_minutes", "studied"]
    result = parse_rows([header, [*row(evening(MONDAY)), 999, "Go"]], 4)
    assert result.skipped == 0


def test_parse_int_rules() -> None:
    assert parse_int("25", "c", 0, 300, 0) == 25
    assert parse_int(25.0, "c", 0, 300, 0) == 25
    assert parse_int("", "c", 0, 300, 0) == 0
    for bad in ("abc", 2.5, True, -1, 301):
        with pytest.raises(InvalidCell):
            parse_int(bad, "c", 0, 300, 0)
    with pytest.raises(InvalidCell):
        parse_int("", "c", 1, 5, None)


def test_parse_float_accepts_comma_decimals() -> None:
    assert parse_float("7,5", "sleep_hours", 0, 14) == 7.5
    with pytest.raises(InvalidCell):
        parse_float(15, "sleep_hours", 0, 14)


def test_parse_yes_no() -> None:
    assert parse_yes_no(" Yes ", "gym") is True
    assert parse_yes_no("no", "gym") is False
    with pytest.raises(InvalidCell):
        parse_yes_no(1, "gym")


def test_error_messages_name_the_column_not_the_value() -> None:
    with pytest.raises(InvalidCell) as excinfo:
        parse_int(4242, "focus", 1, 5, None)
    assert "focus" in str(excinfo.value)
    assert "4242" not in str(excinfo.value)
