"""Read-only check that the service account can read the habit sheet. Changes nothing.

Run locally:  uv run python -m scripts.habit_sheet_smoke

Needs in .env: HABIT_SHEET_ID and HABIT_SA_KEY_FILE (path to the key, kept outside the repo).
Prints only column checks and counts, never values or flag names.
"""

from __future__ import annotations

from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic_settings import BaseSettings, SettingsConfigDict

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
EXPECTED = [
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
]


class SheetSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    habit_sheet_id: str
    habit_sa_key_file: str


def main() -> None:
    settings = SheetSettings()  # type: ignore[call-arg]
    creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
        settings.habit_sa_key_file, scopes=SCOPES
    )
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    # No sheet name in the range: reads the first tab, which is the form's responses tab.
    result = sheets.spreadsheets().values().get(spreadsheetId=settings.habit_sheet_id, range="A1:Z")
    rows: list[list[str]] = result.execute().get("values", [])

    if not rows:
        print("sheet is readable but empty (no header row yet: submit the form once)")
        return

    header = rows[0]
    missing = [name for name in EXPECTED if name not in header]
    flags = sum(1 for name in header if name.startswith("flag_"))
    print(f"readable: yes | data rows: {len(rows) - 1} | flag columns: {flags}")
    print(f"missing expected columns: {missing or 'none'}")


if __name__ == "__main__":
    main()
