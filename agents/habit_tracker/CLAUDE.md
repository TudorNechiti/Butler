# Habit tracker agent (`agents/habit_tracker/`)

Read the root `CLAUDE.md` first; everything there still applies. This file adds what is specific
to this agent.

## Purpose

Answer one question with data instead of feelings: **is my daily routine working?** The routine is
a daily focused-study block (Go, LeetCode, German, reading), gym, enough sleep, plus a personal
project and educational videos tracked separately. It runs as a 4-week trial in two phases.

It is a cron job, not an app: Google Form -> Sheet -> GitHub Actions -> Telegram.

## Non-goals

- No web UI, mobile app or dashboard.
- No streaks, points or gamification.
- No medical, psychological or diagnostic claims.
- No advice. Reports describe what happened; the owner decides what to change, including when to
  move from phase 1 to phase 2.
- No LLM. Parsing, stats and report text are plain code. (The optional Claude phrasing step from
  the first draft was dropped: it adds a key and a cost for less precise text.)
- No extra integrations (Calendar, Tasks, Obsidian) in v1. Read-only Calendar for "planned vs
  done" may be considered after week 3, only if logging stuck.

## Privacy rules (most important)

Butler is a public repo and this agent handles personal data.

- **No personal data in git:** no real entries, exports, screenshots or real values in tests,
  docs, fixtures or commit messages. Tests use obviously fake data.
- **Flag names stay private.** Custom yes/no questions are titled `flag_<name>` in the form. Code
  discovers them by prefix and treats the names as opaque strings. They never appear in code,
  config, logs or tests (tests use `flag_tea`, `flag_pushups`).
- **Logs contain counts and ids only**, never values, flag names or notes.
- **Telegram private chat only.** Reminders carry no personal values (the form link is fine).
- **The `notes` column is ignored:** never parsed, logged or sent anywhere.
- **Secrets** (`HABIT_SHEET_ID`, service account key, `HABIT_FORM_URL`, Telegram) only in `.env`
  and GitHub secrets. The form URL is a secret because anyone with it can submit rows.

## Data flow and storage

- The owner logs once a day in a **Google Form**; responses land in a linked **Sheet** (first tab).
- The agent reads the Sheet as a **service account** (`butler-habit-reader`, no project roles)
  that has Viewer access to that one Sheet, scope `spreadsheets.readonly`. No OAuth consent screen,
  no 7-day token expiry. The agent never writes.
- `store.py` returns raw rows behind a small `RowSource` protocol; `models.py` parses them. Tests
  use a fake row source. Rows are read as unformatted values (dates as serial numbers), so the
  sheet's locale can't change their meaning.

## Data model

One entry per day. Validate at the boundary: out-of-range or unparseable rows are skipped and
counted in the report ("1 row skipped: invalid"), never silently fixed.

The form question titles are the column contract. Renaming a question breaks the agent, so a
missing column must fail loudly with its name.

| Column | Type | Rule |
|---|---|---|
| `Timestamp` | datetime | added by Forms, Europe/Berlin |
| `date` | date, optional | blank = day of `Timestamp`; submissions before 04:00 count as the previous day |
| `golang_minutes` | int, optional | 0-300, blank = 0 |
| `leetcode_minutes` | int, optional | 0-300, blank = 0 |
| `german_minutes` | int, optional | 0-300, blank = 0 |
| `reading_minutes` | int, optional | 0-300, blank = 0 |
| `start_difficulty` | int | 1-5 (1 = easy to start) |
| `focus` | int | 1-5 |
| `sleep_hours` | float | 0-14, last night |
| `gym` | yes/no | |
| `project_minutes` | int, optional | 0-480, blank = 0. Never counts toward study |
| `video_minutes` | int, optional | 0-240, blank = 0. Never counts toward study |
| `flag_*` | yes/no | private, discovered by prefix |
| `notes` | text, optional | ignored |

Several rows for the same day: the latest `Timestamp` wins. Unknown columns (including stale ones
from deleted form questions) are ignored.

**Study minutes are derived, never stored:** `study_minutes = golang + leetcode + german + reading`.
Storing a total next to its parts would create two sources of truth that can disagree.

## Reports (plain Python, `statistics` module, no pandas)

Weekly, Monday-Sunday, against the active phase targets in `config.toml`:

- Days logged out of 7. Missing days are shown as missing, never filled in.
- Study days (>= `min_minutes_day_counts`), full days (>= `min_minutes_full_day`), weekly study
  minutes vs pass mark. Per subject: minutes vs weekly target, days practised.
- Gym sessions vs target. Sleep mean and range vs min/aim, nights under the minimum.
- Start difficulty and focus mean.
- Project minutes and sessions vs floor; video minutes vs target. Reported separately.
- Delta versus the previous week for each metric.
- Flag comparisons (focus and study minutes, days with vs without): only when both groups have at
  least `min_n` days; always print `n` for both. Below that: "not enough days to compare".
- Fixed caveat line: other things change at the same time, so comparisons are hints, not proof.

## Jobs

- **Reminder**, daily at 21:00 Europe/Berlin: if there is no entry for today, send a Telegram
  nudge with the form link. Otherwise send nothing.
- **Weekly report**, Sunday at 20:00 Europe/Berlin.
- GitHub Actions cron is UTC. To survive daylight saving, each workflow is scheduled at both
  UTC hours, and the code exits unless the Berlin local hour matches the configured one.
- `--dry-run` prints the message instead of sending it. Blocked in CI: Actions logs of a public
  repo are public. `--force` skips the hour check (manual runs).
- Keep `run()` free of scheduler specifics (Azure Functions port later).

## Architecture

```
agents/habit_tracker/
  CLAUDE.md, README.md, config.toml
  config.py      # HabitSettings (secrets) and HabitConfig/Targets (validated config.toml)
  models.py      # Entry, row parsing and validation
  store.py       # RowSource protocol and the read-only Sheets implementation
  stats.py       # pure functions, fully unit-tested
  report.py      # weekly report text from stats
  app.py         # reminder() and weekly(): fetch -> compute -> notify
  __main__.py    # python -m agents.habit_tracker [reminder|weekly] [--dry-run]
tests/habit_tracker/   # fake data only
```

Reuse `core/` (config, telegram, logging). No new dependencies: `google-auth` and
`google-api-python-client` are already in use.

## Cost

Zero: GitHub Actions free tier, Sheets API free quota (two reads a day), no LLM.

## Definition of done for v1

- `ruff`, `mypy` and `pytest` pass with no network calls.
- A fake week produces correct counts, means, deltas and `n` values.
- Flag comparisons are suppressed below `min_n`.
- No personal data or real flag names in the repo (grep before committing).
- README explains the privacy model in a few sentences.
