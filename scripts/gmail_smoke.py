"""Read-only Gmail check: lists a few unprocessed ids and parses one. Changes nothing.

Run locally:  uv run python -m scripts.gmail_smoke

Prints only counts and lengths, never sender, subject or body.
"""

from __future__ import annotations

from agents.email_labeler.gmail import GmailGateway, GmailSettings


def main() -> None:
    gateway = GmailGateway.from_settings(GmailSettings())  # type: ignore[call-arg]
    ids = gateway.list_unprocessed(limit=5)
    print(f"unprocessed messages found (max 5): {len(ids)}")
    if ids:
        email = gateway.get(ids[0])
        print(
            f"parsed one: sender_chars={len(email.sender)} subject_chars={len(email.subject)} "
            f"body_chars={len(email.body_text)} received_at={email.received_at.isoformat()}"
        )


if __name__ == "__main__":
    main()
