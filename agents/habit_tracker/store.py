"""The only code that talks to Google Sheets. Read-only.

Auth is a service account with no project roles. Its only access is Viewer on the one sheet
that was shared with it, and the scope below is read-only, so this code cannot change anything.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from agents.habit_tracker.config import HabitSettings
from agents.habit_tracker.models import Cell

SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)
# No tab name: the first tab, which is where Forms writes responses.
RANGE = "A1:AZ"


class SheetReadError(Exception):
    """The sheet could not be read: key, sharing or API problem. Message holds no content."""


def _credentials(settings: HabitSettings) -> service_account.Credentials:
    """Locally the key is a file path; in CI it is the key's JSON content in a secret."""
    creds_cls = service_account.Credentials
    try:
        if settings.habit_sa_key_json is not None:
            info = json.loads(settings.habit_sa_key_json.get_secret_value())
            return creds_cls.from_service_account_info(info, scopes=list(SCOPES))  # type: ignore[no-untyped-call,no-any-return]
        return creds_cls.from_service_account_file(  # type: ignore[no-untyped-call,no-any-return]
            settings.habit_sa_key_file, scopes=list(SCOPES)
        )
    except (ValueError, OSError) as exc:
        # Messages could echo parts of the key; keep only the type.
        raise SheetReadError(f"service account key unreadable ({type(exc).__name__})") from None


class RowSource(Protocol):
    def read_rows(self) -> Sequence[Sequence[Cell]]: ...


class SheetsStore:
    def __init__(self, service: Any, sheet_id: str) -> None:
        self._values = service.spreadsheets().values()
        self._sheet_id = sheet_id

    @classmethod
    def from_settings(cls, settings: HabitSettings) -> SheetsStore:
        service = build("sheets", "v4", credentials=_credentials(settings), cache_discovery=False)
        return cls(service, settings.habit_sheet_id)

    def read_rows(self) -> Sequence[Sequence[Cell]]:
        request = self._values.get(
            spreadsheetId=self._sheet_id,
            range=RANGE,
            # Raw values, not display text: numbers stay numbers and dates come as serial
            # numbers, so the sheet's locale (10/12 vs 12.10) can't change the meaning.
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="SERIAL_NUMBER",
        )
        try:
            response: dict[str, Any] = request.execute()
        except HttpError as exc:
            hint = {
                403: "not shared with the service account, or Sheets API disabled",
                404: "wrong HABIT_SHEET_ID",
            }.get(exc.status_code, "API error")
            raise SheetReadError(f"HTTP {exc.status_code}: {hint}") from None
        except GoogleAuthError as exc:
            raise SheetReadError(f"service account key rejected ({type(exc).__name__})") from None
        rows: list[list[Cell]] = response.get("values", [])
        return rows
