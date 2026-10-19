import json
from datetime import date
from pathlib import Path

from agents.job_scout.dedupe import SeenStore, dedupe, dedupe_key
from tests.job_scout.fakes import make_posting


def test_same_job_on_different_sources_gets_one_key() -> None:
    board = make_posting(title="Backend Engineer (m/w/d)", company="Acme GmbH", source="greenhouse")
    aggregator = make_posting(
        title="Backend  Engineer (f/m/x)", company="ACME", source="arbeitnow", external_id="x9"
    )
    other = make_posting(title="Backend Engineer, Payments", company="Acme GmbH")

    assert dedupe_key(board) == dedupe_key(aggregator)
    assert dedupe_key(board) != dedupe_key(other)
    assert dedupe([board, aggregator, other]) == [board, other]  # first one wins


def test_key_is_a_hash_not_readable_text() -> None:
    key = dedupe_key(make_posting(company="Acme", title="Backend Engineer"))
    assert len(key) == 32 and "acme" not in key


def test_seen_store_round_trip_and_prune(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "seen.json"
    store = SeenStore.load(path)
    store.add(["old"], date(2026, 7, 1))
    store.add(["new"], date(2026, 10, 18))
    store.add(["new"], date(2026, 10, 19))  # keeps the first-seen day
    store.save()

    loaded = SeenStore.load(path)
    assert "old" in loaded and "new" in loaded
    assert loaded.prune(date(2026, 10, 19), retention_days=60) == 1
    assert "old" not in loaded and len(loaded) == 1
    assert json.loads(path.read_text())["seen"] == {"old": "2026-07-01", "new": "2026-10-18"}


def test_unreadable_seen_file_starts_empty_and_says_so(tmp_path: Path) -> None:
    path = tmp_path / "seen.json"
    path.write_text("{not json", encoding="utf-8")

    store = SeenStore.load(path)

    assert len(store) == 0
    assert store.was_reset


def test_missing_seen_file_is_a_normal_first_run(tmp_path: Path) -> None:
    store = SeenStore.load(tmp_path / "seen.json")
    assert len(store) == 0
    assert not store.was_reset
