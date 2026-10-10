"""Daily entries and the code that turns raw sheet rows into them.

Sheet content is untrusted input: every cell is type- and range-checked. A bad row is skipped
and counted, never silently fixed. Error messages name the column, never the value, so they are
safe to log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

type Cell = str | int | float

SUBJECTS = ("golang", "leetcode", "german", "reading")
FLAG_PREFIX = "flag_"

TIMESTAMP = "Timestamp"
DATE = "date"
REQUIRED_COLUMNS = (
    TIMESTAMP,
    DATE,
    *(f"{subject}_minutes" for subject in SUBJECTS),
    "start_difficulty",
    "focus",
    "sleep_hours",
    "gym",
    "project_minutes",
    "video_minutes",
)

# Google Sheets serial dates count days from this epoch (same as Excel/Lotus).
_SHEETS_EPOCH = datetime(1899, 12, 30)


class MissingColumnsError(Exception):
    """A form question was renamed or deleted. Names are column titles, safe to show."""

    def __init__(self, missing: Sequence[str]) -> None:
        super().__init__(f"sheet is missing columns: {', '.join(missing)}")
        self.missing = list(missing)


class InvalidCell(ValueError):
    def __init__(self, column: str, reason: str) -> None:
        super().__init__(f"{column}: {reason}")
        self.column = column


@dataclass(frozen=True)
class Entry:
    day: date
    submitted_at: datetime  # sheet-local wall time
    subject_minutes: Mapping[str, int]
    start_difficulty: int
    focus: int
    sleep_hours: float
    gym: bool
    project_minutes: int
    video_minutes: int
    flags: Mapping[str, bool] = field(default_factory=dict)

    @property
    def study_minutes(self) -> int:
        # Derived, never stored: the subjects are the single source of truth.
        return sum(self.subject_minutes.values())


@dataclass
class ParseResult:
    entries: list[Entry]
    skipped: int
    flag_names: list[str]


def serial_to_datetime(serial: float) -> datetime:
    return (_SHEETS_EPOCH + timedelta(days=serial)).replace(microsecond=0)


def logical_day(moment: datetime, day_starts_at_hour: int) -> date:
    """The day a moment belongs to: logging at 00:30 still counts for the evening before."""
    return (moment - timedelta(hours=day_starts_at_hour)).date()


def _is_blank(cell: Cell | None) -> bool:
    return cell is None or (isinstance(cell, str) and not cell.strip())


def _is_number(cell: Cell | None) -> bool:
    # bool is a subclass of int; never a valid number here.
    return isinstance(cell, int | float) and not isinstance(cell, bool)


def _number(cell: Cell, column: str) -> float:
    if isinstance(cell, bool):
        raise InvalidCell(column, "not a number")
    if isinstance(cell, int | float):
        return float(cell)
    try:
        return float(cell.strip().replace(",", "."))
    except ValueError:
        raise InvalidCell(column, "not a number") from None


def parse_int(cell: Cell | None, column: str, low: int, high: int, default: int | None) -> int:
    """Whole number in [low, high]. Blank gives `default`, or an error when it is required."""
    if cell is None or _is_blank(cell):
        if default is None:
            raise InvalidCell(column, "required")
        return default
    value = _number(cell, column)
    if not value.is_integer():
        raise InvalidCell(column, "not a whole number")
    if not low <= value <= high:
        raise InvalidCell(column, f"outside {low}-{high}")
    return int(value)


def parse_float(cell: Cell | None, column: str, low: float, high: float) -> float:
    if cell is None or _is_blank(cell):
        raise InvalidCell(column, "required")
    value = _number(cell, column)
    if not low <= value <= high:
        raise InvalidCell(column, f"outside {low:g}-{high:g}")
    return value


def parse_yes_no(cell: Cell | None, column: str) -> bool:
    text = cell.strip().lower() if isinstance(cell, str) else ""
    if text not in ("yes", "no"):
        raise InvalidCell(column, "expected yes or no")
    return text == "yes"


def parse_entry(
    row: Mapping[str, Cell], flag_columns: Sequence[str], day_starts_at_hour: int
) -> Entry:
    """Build one Entry from a row keyed by column title. Raises InvalidCell."""
    timestamp = row.get(TIMESTAMP)
    if not isinstance(timestamp, int | float) or not _is_number(timestamp):
        raise InvalidCell(TIMESTAMP, "not a date-time")
    submitted_at = serial_to_datetime(timestamp)

    date_cell = row.get(DATE)
    if _is_blank(date_cell):
        day = logical_day(submitted_at, day_starts_at_hour)
    elif isinstance(date_cell, int | float) and _is_number(date_cell):
        day = serial_to_datetime(date_cell).date()
    else:
        raise InvalidCell(DATE, "not a date")

    return Entry(
        day=day,
        submitted_at=submitted_at,
        subject_minutes={
            subject: parse_int(row.get(f"{subject}_minutes"), f"{subject}_minutes", 0, 300, 0)
            for subject in SUBJECTS
        },
        start_difficulty=parse_int(row.get("start_difficulty"), "start_difficulty", 1, 5, None),
        focus=parse_int(row.get("focus"), "focus", 1, 5, None),
        sleep_hours=parse_float(row.get("sleep_hours"), "sleep_hours", 0, 14),
        gym=parse_yes_no(row.get("gym"), "gym"),
        project_minutes=parse_int(row.get("project_minutes"), "project_minutes", 0, 480, 0),
        video_minutes=parse_int(row.get("video_minutes"), "video_minutes", 0, 240, 0),
        flags={
            column.removeprefix(FLAG_PREFIX): parse_yes_no(row.get(column), column)
            for column in flag_columns
        },
    )


def parse_rows(rows: Sequence[Sequence[Cell]], day_starts_at_hour: int) -> ParseResult:
    """Parse a whole sheet (header row first). One entry per day: the latest submission wins.

    Unknown columns (notes, stale columns of deleted questions) are ignored.
    """
    if not rows:
        raise MissingColumnsError(REQUIRED_COLUMNS)
    header = [str(title).strip() for title in rows[0]]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise MissingColumnsError(missing)
    flag_columns = [title for title in header if title.startswith(FLAG_PREFIX)]

    latest: dict[date, Entry] = {}
    skipped = 0
    for raw in rows[1:]:
        if all(_is_blank(cell) for cell in raw):
            continue  # a deleted response leaves an empty row behind
        # The API drops trailing empty cells, so short rows are normal.
        row = dict(zip(header, raw, strict=False))
        try:
            entry = parse_entry(row, flag_columns, day_starts_at_hour)
        except InvalidCell:
            skipped += 1
            continue
        current = latest.get(entry.day)
        if current is None or entry.submitted_at >= current.submitted_at:
            latest[entry.day] = entry

    return ParseResult(
        entries=sorted(latest.values(), key=lambda e: e.day),
        skipped=skipped,
        flag_names=[column.removeprefix(FLAG_PREFIX) for column in flag_columns],
    )
