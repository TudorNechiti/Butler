# Email labeler

Sorts incoming personal Gmail into coloured labels with Claude:
`Butler/Debts`, `Payments`, `Reminders`, `Jobs`, `Other`, plus `Review` when it isn't sure.
Mail stays in the inbox; the bot only adds labels.

## How it works

```
GitHub Actions (hourly)
  -> gmail.py       list inbox mail from the last 3 days that isn't Processed or already grouped
  -> sanitize       HTML to text, strip hidden characters, cut to 3,000 chars
  -> classifier.py  one Claude Haiku call -> {category, confidence, reason} (structured output)
  -> labeler.py     plain code maps category -> label, adds hidden Butler/Processed
  -> telegram       only on failure (expired Gmail login, every email failed)
```

Your own Gmail filters can apply `Butler/*` labels to known senders; the bot skips those.

## Security model

- **Prompt injection:** email is untrusted. Claude has no tools and can only return one of five
  categories, so a malicious email can at worst get the wrong label. Email content is wrapped in
  `<email>` tags, and any such tags inside the email are neutralised.
- **Least privilege:** `gmail.modify` is the narrowest scope that allows adding labels. It also
  allows trash and archive, so `GmailGateway` exposes only list, read, create-label and add-label.
  It never sends `removeLabelIds`.
- **Logs:** only message ids, labels, counts and error types (enforced by `core.logging`, tested).
- **Secrets:** `.env` locally (gitignored), repository secrets in CI.

## Cost

Claude Haiku 4.5, about $0.0015 per email (measured), so roughly $0.50 to $3 a month depending
on volume. Promotions, social mail and filter-labelled mail are skipped before any API call.
Limits: a workspace spend cap in the Anthropic Console, plus `max_items` per run.

## Running

```sh
uv run python -m agents.email_labeler --preview --max 5   # local: shows sender/subject/label, writes nothing
uv run python -m agents.email_labeler --dry-run           # classify only, logs ids and labels
uv run python -m agents.email_labeler                     # label for real
```

In GitHub: **Actions -> Email labeler -> Run workflow** for a manual run (dry run by default).

## Gmail login

One-time: `uv run python -m scripts.gmail_auth` and put the printed token in `.env` and in the
`GMAIL_REFRESH_TOKEN` repository secret.

⚠️ While the Google OAuth app is in **Testing** status, the token expires every 7 days. You get
a Telegram alert; re-run the script and update the secret. Publishing the app ("In production",
unverified, personal use) removes the expiry.

Configuration (model, limits, threshold) lives in `config.toml`.
