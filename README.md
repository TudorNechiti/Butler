# Butler

Personal AI agents I use day to day, sharing one small core.

| Agent | Status |
|---|---|
| Email labeler | running hourly on GitHub Actions |
| Habit tracker | evening reminder and Sunday report on GitHub Actions (no LLM) |
| Job scout | planned |
| Stock news digest | planned |

## Layout

- `core/`: shared building blocks: config, JSON logging with a field allowlist, a thin Claude client with cost tracking, a Telegram sender, and text sanitising for untrusted input.
- `agents/<name>/`: one module per agent, each following fetch -> ask Claude -> act -> notify
  (Claude only where it adds something; the habit tracker is plain code).

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Tests never call external APIs. Tests marked `live` cost money and only run with `-m live`.

## Security model

- Secrets come only from env vars (`.env` locally, repository secrets in CI). See `.env.example`.
- Email and web content are untrusted. Claude gets no tools; its output is a schema-validated enum that plain code maps to an action.
- Logs carry only ids, counts and categories, never message content. This is enforced by `core.logging.EventLogger`.
