"""CLI: python -m agents.email_labeler [--dry-run] [--preview] [--max N]

Exit codes: 0 ok, 1 every email failed, 2 Gmail authorization problem.
"""

from __future__ import annotations

import argparse
import os
import sys

import anthropic

from agents.email_labeler.classifier import load_system_prompt
from agents.email_labeler.gmail import GmailAuthError, GmailGateway, GmailSettings
from agents.email_labeler.labeler import load_config, run
from agents.email_labeler.models import Classification, EmailMessage
from core.llm import LLM
from core.logging import EventLogger, configure_logging
from core.telegram import TelegramClient

log = EventLogger(
    __name__, allowed_fields={"model", "llm_calls", "input_tokens", "output_tokens", "usd_estimate"}
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agents.email_labeler")
    parser.add_argument("--dry-run", action="store_true", help="classify but change nothing")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="local only: dry run that prints sender/subject/label/reason to this terminal",
    )
    parser.add_argument("--max", type=int, default=None, help="max emails this run")
    return parser.parse_args(argv)


def _print_preview(email: EmailMessage, label: str, result: Classification | None) -> None:
    # Deliberately print(), not logging: this is a local, interactive view of your own mail.
    confidence = f"{result.confidence:.2f}" if result else "-"
    reason = result.reason if result else "(model declined / invalid output)"
    print(f"\n{label:<18} {confidence}  {email.sender[:60]}\n{'':<24}{email.subject[:80]}")
    print(f"{'':<24}-> {reason}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.preview and os.environ.get("CI"):
        sys.exit("--preview prints email content and is disabled in CI.")
    dry_run = args.dry_run or args.preview

    configure_logging()
    config = load_config()
    settings = GmailSettings()  # type: ignore[call-arg]
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    llm = LLM(
        client, config.model, max_calls=args.max or config.max_items, max_tokens=config.max_tokens
    )
    llm.check_model()  # free metadata call: fails fast if the model id was retired

    try:
        stats = run(
            config=config,
            mailbox=GmailGateway.from_settings(settings, config.body_chars),
            llm=llm,
            system_prompt=load_system_prompt(),
            alert=telegram.send_message,
            dry_run=dry_run,
            max_items=args.max,
            on_result=_print_preview if args.preview else None,
        )
    except GmailAuthError:
        return 2
    finally:
        log.event(
            "llm_usage",
            model=llm.model,
            llm_calls=llm.usage.calls,
            input_tokens=llm.usage.input_tokens,
            output_tokens=llm.usage.output_tokens,
            usd_estimate=round(llm.usd_spent, 5),
        )
    return 1 if stats.fetched and stats.failed == stats.fetched else 0


if __name__ == "__main__":
    sys.exit(main())
