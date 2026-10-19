"""CLI: python -m agents.job_scout [--dry-run] [--preview] [--max N] [--seen-file PATH]

Exit codes: 0 ok (with or without matches), 1 every source failed or the digest could not be
sent. On GitHub Actions the outcome is also shown on the run's page (counts only).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import anthropic

from agents.job_scout.app import run
from agents.job_scout.config import JobScoutSettings, load_config
from agents.job_scout.dedupe import SeenStore
from agents.job_scout.digest import format_digest
from agents.job_scout.models import Posting, Score
from agents.job_scout.scorer import load_system_prompt
from agents.job_scout.sources import build_sources, new_http_client
from core import ci
from core.llm import LLM
from core.logging import EventLogger, configure_logging
from core.telegram import TelegramClient, TelegramError

# Gitignored. In CI the workflow restores and saves this file with the Actions cache.
DEFAULT_SEEN_FILE = Path(".cache/job_scout/seen.json")

log = EventLogger(
    __name__,
    allowed_fields={"model", "llm_calls", "input_tokens", "output_tokens", "usd_estimate"},
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m agents.job_scout")
    parser.add_argument(
        "--dry-run", action="store_true", help="score but send nothing and save nothing"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="local only: dry run that prints every scored job and the digest to this terminal",
    )
    parser.add_argument("--max", type=int, default=None, help="max Claude calls this run")
    parser.add_argument("--seen-file", type=Path, default=DEFAULT_SEEN_FILE)
    return parser.parse_args(argv)


def _print_scored(posting: Posting, result: Score) -> None:
    # Deliberately print(), not logging: a local, interactive view for tuning filters and rubric.
    print(
        f"\n[{result.score:>3}] {posting.title[:80]}\n      {posting.company} · {posting.location}"
    )
    print(f"      -> {result.reason}")


def _alert(telegram: TelegramClient, text: str) -> None:
    """An alert failure must never hide the original problem."""
    try:
        telegram.send_message(text)
    except TelegramError:
        ci.note("Could not send the failure alert to Telegram either.", "error")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.preview and os.environ.get("CI"):
        # Scores and reasons reflect my private profile; Actions logs of a public repo are public.
        sys.exit("--preview prints profile-based scores and is disabled in CI.")
    dry_run = args.dry_run or args.preview

    configure_logging()
    config = load_config()
    settings = JobScoutSettings()  # type: ignore[call-arg]
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    llm = LLM(
        client, config.model, max_calls=args.max or config.max_calls, max_tokens=config.max_tokens
    )
    llm.check_model()  # free metadata call: fails fast if the model id was retired

    seen = SeenStore.load(args.seen_file)
    if seen.was_reset:
        ci.note(
            "The seen-jobs file was unreadable and started empty: expect a few repeats.", "warning"
        )

    try:
        with new_http_client() as http:
            sources = build_sources(config, settings, http)
            digest = run(
                config=config,
                sources=sources,
                llm=llm,
                system_prompt=load_system_prompt(settings.job_profile.get_secret_value()),
                seen=seen,
                now=datetime.now(UTC),
                on_scored=_print_scored if args.preview else None,
            )
    finally:
        log.event(
            "llm_usage",
            model=llm.model,
            llm_calls=llm.usage.calls,
            input_tokens=llm.usage.input_tokens,
            output_tokens=llm.usage.output_tokens,
            usd_estimate=round(llm.usd_spent, 5),
        )

    if sources and len(digest.failed_sources) == len(sources):
        if not dry_run:
            _alert(telegram, "Butler job scout: every job source failed this run. Check the logs.")
        ci.note("Every job source failed.", "error")
        return 1

    summary = f"{digest.scored} new jobs scored out of {digest.fetched} fetched"
    if dry_run:
        if args.preview and digest.matches:
            print("\n----- digest -----\n" + format_digest(digest))
        print(f"\nDry run: {len(digest.matches)} matches, {summary}. Nothing sent or saved.")
        return 0

    if digest.matches:
        try:
            telegram.send_message(format_digest(digest))
        except TelegramError:
            # Seen store not saved, so tomorrow's run scores and offers these jobs again.
            ci.note("The digest could not be sent to Telegram.", "error")
            return 1
    seen.save()
    ci.note(
        f"Sent {len(digest.matches)} matches ({summary})."
        if digest.matches
        else f"No new matches today ({summary})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
