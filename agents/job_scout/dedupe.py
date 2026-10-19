"""Recognise the same job across sources and across days.

The same ad often shows up on the company board, on Arbeitnow and on Adzuna, each with its own
id. So a job is identified by its normalised company + title instead. The seen store keeps
hashes of those keys (no readable text) for `seen_retention_days`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from agents.job_scout.models import Posting

_PARENS_RE = re.compile(r"\([^)]*\)")  # (m/w/d), (f/m/x), (all genders), (Senior), ...
_NON_WORD_RE = re.compile(r"[^\w]+")
_LEGAL_FORMS = frozenset({"gmbh", "ag", "se", "kg", "co", "ug", "inc", "ltd", "llc", "bv", "plc"})


def _normalise(value: str, drop: frozenset[str] = frozenset()) -> str:
    words = _NON_WORD_RE.sub(" ", _PARENS_RE.sub(" ", value.lower())).split()
    return " ".join(w for w in words if w not in drop)


def dedupe_key(posting: Posting) -> str:
    company = _normalise(posting.company, _LEGAL_FORMS)
    title = _normalise(posting.title)
    return hashlib.sha256(f"{company}|{title}".encode()).hexdigest()[:32]


def dedupe(postings: Iterable[Posting]) -> list[Posting]:
    """Keep the first posting per key. Sources are ordered so the most complete ad comes first."""
    kept: dict[str, Posting] = {}
    for posting in postings:
        kept.setdefault(dedupe_key(posting), posting)
    return list(kept.values())


class SeenStore:
    """Keys of jobs already scored, with the day they were first seen. A small JSON file."""

    VERSION = 1

    def __init__(self, path: Path, seen: dict[str, str] | None = None) -> None:
        self.path = path
        self._seen = seen or {}
        self.was_reset = False  # True when an unreadable file was replaced by an empty store

    @classmethod
    def load(cls, path: Path) -> SeenStore:
        if not path.exists():
            return cls(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            seen = data["seen"] if data.get("version") == cls.VERSION else None
            if not isinstance(seen, dict):
                raise ValueError("unexpected format")
        except (OSError, ValueError, KeyError, AttributeError):
            # Worst case of starting empty: a few repeats in one digest.
            store = cls(path)
            store.was_reset = True
            return store
        return cls(path, {str(k): str(v) for k, v in seen.items()})

    def __contains__(self, key: str) -> bool:
        return key in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def add(self, keys: Iterable[str], today: date) -> None:
        for key in keys:
            self._seen.setdefault(key, today.isoformat())

    def prune(self, today: date, retention_days: int) -> int:
        cutoff = (today - timedelta(days=retention_days)).isoformat()
        old = [key for key, first_seen in self._seen.items() if first_seen < cutoff]
        for key in old:
            del self._seen[key]
        return len(old)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {"version": self.VERSION, "seen": dict(sorted(self._seen.items()))}
        tmp.write_text(json.dumps(payload, indent=0), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves half a file
