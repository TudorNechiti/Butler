"""Turn a JobDigest into one plain-text Telegram message."""

from __future__ import annotations

from agents.job_scout.models import JobDigest, Match


def _where(match: Match) -> str:
    posting = match.posting
    parts = [posting.company or "unknown company", posting.location or "location not stated"]
    if posting.remote:
        parts.append("remote")
    return " · ".join(parts)


def format_digest(digest: JobDigest) -> str:
    count = len(digest.matches)
    lines = [f"Butler job scout: {count} new match{'es' if count != 1 else ''}", ""]
    for i, match in enumerate(digest.matches, start=1):
        lines.append(f"{i}. [{match.score.score}] {match.posting.title}")
        lines.append(f"   {_where(match)}")
        lines.append(f"   {match.score.reason}")
        if match.posting.url:
            lines.append(f"   {match.posting.url}")
        lines.append("")
    lines.append(f"{digest.scored} new jobs scored out of {digest.fetched} fetched.")
    if digest.failed_sources:
        lines.append(f"Sources that failed: {', '.join(digest.failed_sources)}.")
    if any(m.posting.source == "adzuna" for m in digest.matches):
        lines.append("Jobs by Adzuna.")  # attribution required by Adzuna's API terms
    return "\n".join(lines)
