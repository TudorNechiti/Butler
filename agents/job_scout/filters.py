"""Hard filters, applied in code before Claude sees anything.

They only drop what is clearly out (wrong role, wrong level, wrong place, stated pay too
low). Anything that needs judgement, like German level or tech fit, is left to the scorer.
Each rejection has a short reason so the run log can count them.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from agents.job_scout.config import Filters
from agents.job_scout.models import Posting


def word_pattern(words: Iterable[str]) -> re.Pattern[str]:
    """Match any of the words as a whole word: "lead" matches "Tech Lead", not "Leading"."""
    alternatives = "|".join(re.escape(w.lower()) for w in words)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


class PostingFilter:
    def __init__(self, filters: Filters) -> None:
        self._include = word_pattern(filters.title_include)
        self._exclude = word_pattern(filters.title_exclude) if filters.title_exclude else None
        self._onsite = word_pattern(filters.onsite_locations)
        self._remote = word_pattern(["remote"])
        self._remote_exclude = (
            word_pattern(filters.remote_exclude_locations)
            if filters.remote_exclude_locations
            else None
        )
        self._salary_floor = filters.salary_floor_eur

    def reject_reason(self, posting: Posting) -> str | None:
        if not self._include.search(posting.title):
            return "title"
        if self._exclude and self._exclude.search(posting.title):
            return "level_or_role"
        if not self._location_ok(posting):
            return "location"
        if posting.salary_max_eur is not None and posting.salary_max_eur < self._salary_floor:
            return "salary"
        return None

    def _location_ok(self, posting: Posting) -> bool:
        if self._onsite.search(posting.location):
            return True
        remote = posting.remote is True or bool(self._remote.search(posting.location))
        if not remote:
            return False
        return not (self._remote_exclude and self._remote_exclude.search(posting.location))

    def apply(self, postings: Iterable[Posting]) -> tuple[list[Posting], Counter[str]]:
        kept: list[Posting] = []
        rejected: Counter[str] = Counter()
        for posting in postings:
            reason = self.reject_reason(posting)
            if reason is None:
                kept.append(posting)
            else:
                rejected[reason] += 1
        return kept, rejected
