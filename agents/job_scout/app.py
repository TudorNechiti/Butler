"""One run of the job scout: fetch -> filter -> dedupe -> score -> pick the best.

Plain function, no scheduler or CI specifics, so it can move to Azure Functions unchanged.
Sending and saving the seen store are left to the caller: a job only counts as seen once the
digest that could have contained it was delivered.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import datetime

from agents.job_scout.config import JobScoutConfig
from agents.job_scout.dedupe import SeenStore, dedupe, dedupe_key
from agents.job_scout.filters import PostingFilter
from agents.job_scout.models import JobDigest, Match, Posting, Score
from agents.job_scout.scorer import score
from agents.job_scout.sources import Source
from core.llm import CallLimitExceeded, LLMError, StructuredLLM
from core.logging import EventLogger

log = EventLogger(
    __name__,
    allowed_fields={
        "source",
        "fetched",
        "rejected_title",
        "rejected_level_or_role",
        "rejected_location",
        "rejected_salary",
        "candidates",
        "new",
        "scored",
        "matches",
        "failed_sources",
        "pruned",
        "duration_s",
    },
)

# Called for every scored posting. Only used by the local --preview mode.
OnScored = Callable[[Posting, Score], None]


def _fetch_all(sources: Sequence[Source], digest: JobDigest) -> list[Posting]:
    postings: list[Posting] = []
    for source in sources:
        try:
            batch = source.fetch()
        except Exception as exc:
            # One broken board must not cost the whole digest.
            digest.failed_sources.append(source.name)
            log.error("source_failed", exc, source=source.name)
            continue
        log.event("source_fetched", source=source.name, fetched=len(batch))
        postings += batch
    return postings


def run(
    *,
    config: JobScoutConfig,
    sources: Sequence[Source],
    llm: StructuredLLM,
    system_prompt: str,
    seen: SeenStore,
    now: datetime,
    on_scored: OnScored | None = None,
) -> JobDigest:
    started = time.monotonic()
    digest = JobDigest()

    postings = _fetch_all(sources, digest)
    digest.fetched = len(postings)

    candidates, rejected = PostingFilter(config.filters).apply(postings)
    digest.candidates = len(candidates)

    pruned = seen.prune(now.date(), config.seen_retention_days)
    new = [p for p in dedupe(candidates) if dedupe_key(p) not in seen]
    digest.new = len(new)
    # Newest first, so when the call cap is hit it is the oldest ads that wait for tomorrow.
    new.sort(key=lambda p: p.posted_at.timestamp() if p.posted_at else 0.0, reverse=True)

    matches: list[Match] = []
    done: list[str] = []
    for posting in new:
        key = dedupe_key(posting)
        try:
            result = score(llm, system_prompt, posting)
        except CallLimitExceeded:
            log.event("call_limit_reached", scored=digest.scored)
            break
        except LLMError as exc:
            # Refusal or unusable output: deterministic, so mark it seen instead of paying again.
            log.error("score_rejected", exc)
            done.append(key)
            continue
        except Exception as exc:
            # Transient (network, API 5xx after SDK retries): not marked seen, retried tomorrow.
            log.error("score_failed", exc)
            continue
        digest.scored += 1
        done.append(key)
        matches.append(Match(posting, result))
        if on_scored is not None:
            on_scored(posting, result)

    seen.add(done, now.date())
    good = [m for m in matches if m.score.score >= config.min_score]
    digest.matches = sorted(good, key=lambda m: m.score.score, reverse=True)[: config.max_matches]

    log.event(
        "run_finished",
        fetched=digest.fetched,
        rejected_title=rejected["title"],
        rejected_level_or_role=rejected["level_or_role"],
        rejected_location=rejected["location"],
        rejected_salary=rejected["salary"],
        candidates=digest.candidates,
        new=digest.new,
        scored=digest.scored,
        matches=len(digest.matches),
        failed_sources=len(digest.failed_sources),
        pruned=pruned,
        duration_s=round(time.monotonic() - started, 1),
    )
    return digest
