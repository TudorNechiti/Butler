from typing import Any

import httplib2
import pytest
from googleapiclient.errors import HttpError

from agents.habit_tracker.store import SCOPES, SheetReadError, SheetsStore


class _Request:
    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result

    def execute(self) -> dict[str, Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeSheets:
    """Mimics service.spreadsheets().values().get(...).execute()."""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def spreadsheets(self) -> "_FakeSheets":
        return self

    def values(self) -> "_FakeSheets":
        return self

    def get(self, **kwargs: Any) -> _Request:
        self.calls.append(kwargs)
        return _Request(self.result)


def test_scope_is_read_only() -> None:
    assert SCOPES == ("https://www.googleapis.com/auth/spreadsheets.readonly",)


def test_reads_raw_values_not_locale_formatted_text() -> None:
    service = _FakeSheets({"values": [["Timestamp"], [46000.5]]})
    rows = SheetsStore(service, "sheet-id").read_rows()

    assert rows == [["Timestamp"], [46000.5]]
    [call] = service.calls
    assert call["valueRenderOption"] == "UNFORMATTED_VALUE"
    assert call["dateTimeRenderOption"] == "SERIAL_NUMBER"


def test_empty_sheet_returns_no_rows() -> None:
    assert SheetsStore(_FakeSheets({}), "sheet-id").read_rows() == []


@pytest.mark.parametrize(("status", "hint"), [(403, "not shared"), (404, "HABIT_SHEET_ID")])
def test_http_errors_become_safe_messages(status: int, hint: str) -> None:
    error = HttpError(httplib2.Response({"status": status}), b'{"error": "SHEET-CONTENT"}')
    with pytest.raises(SheetReadError) as excinfo:
        SheetsStore(_FakeSheets(error), "sheet-id").read_rows()
    assert hint in str(excinfo.value)
    assert "SHEET-CONTENT" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
