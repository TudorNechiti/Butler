# Habit tracker

Answers "is my routine working?" with numbers. I log one short Google Form a day (study minutes
per subject, start difficulty, focus, sleep, gym, project and video minutes). The agent reads the
responses and sends two Telegram messages: an evening nudge if I haven't logged, and a Sunday
report against the targets in `config.toml`. No LLM, no app, no cost.

## How it works

```
Google Form ──► Sheet (first tab)
                  │  read-only service account
GitHub Actions ───┤ daily 21:00 Berlin   store.py -> models.py -> no entry today? -> Telegram nudge
                  └ Sunday 20:00 Berlin  store.py -> models.py -> stats.py -> report.py -> Telegram
```

- `models.py` validates every cell (types, ranges, yes/no). Bad rows are skipped and counted in
  the report, never fixed silently. Submissions before 04:00 count for the previous day; the
  latest submission per day wins. Study minutes are the sum of the subject columns, never stored.
- `stats.py` is pure functions: weekly totals, means, ranges, and flag comparisons that are only
  shown when both groups have at least `min_n` days, always with `n`.
- `report.py` builds plain text: progress against targets, change versus last week, and a fixed
  "hints, not proof" line. It gives no advice.
- Cron is UTC, so each workflow runs at both UTC hours that can be 21:00 (or 20:00) in Berlin and
  the code exits unless the local hour matches. Daylight saving needs no edits.

## Privacy model

The repo is public; the data is not. Entries live only in my Google account. The service account
has no project roles: its only access is Viewer on that one sheet, with the read-only Sheets
scope. Custom yes/no questions are titled `flag_<name>` in the form and discovered at runtime, so
their names never appear in code or config. Logs carry counts only (enforced by
`core.logging.EventLogger`, tested). Reports go only to a private Telegram chat, and `--dry-run`
is blocked in CI because Actions logs of a public repo are public. Tests use made-up data.

## Setup

1. Google Form with the questions in `CLAUDE.md` (titles are the column contract), linked to a
   Sheet. Set the Sheet's time zone to Europe/Berlin.
2. Google Cloud: enable the Sheets API, create a service account with no roles, create a JSON
   key (store it outside the repo), and share the Sheet with the account's email as Viewer.
3. `.env`: `HABIT_SHEET_ID`, `HABIT_SA_KEY_FILE`, `HABIT_FORM_URL`, plus the Telegram values.
   Check access with `uv run python -m scripts.habit_sheet_smoke` (prints counts only).
4. Repository secrets: `HABIT_SHEET_ID`, `HABIT_FORM_URL`, `HABIT_SA_KEY_JSON` (the key file's
   content), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Running

```sh
uv run python -m agents.habit_tracker weekly --dry-run --force    # local: print this week's report
uv run python -m agents.habit_tracker reminder --dry-run --force  # local: print the nudge, if due
```

Manual runs from the Actions tab use `--force` and send to Telegram.

## Cost

Zero: GitHub Actions free minutes, two Sheets API reads a day (free quota), no LLM.
