from pathlib import Path

import pytest

from core import ci


@pytest.fixture
def summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


def test_note_prints_annotation_and_appends_summary(
    summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ci.note("Reminder sent.")
    ci.note("Started late.", level="warning")

    assert capsys.readouterr().out == "::notice::Reminder sent.\n::warning::Started late.\n"
    text = summary.read_text(encoding="utf-8")
    assert "Reminder sent." in text
    assert "Started late." in text


def test_note_escapes_newlines_so_the_annotation_stays_one_command(
    summary: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ci.note("100% done\nsecond line")

    assert capsys.readouterr().out == "::notice::100%25 done%0Asecond line\n"


def test_note_does_nothing_outside_github_actions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    ci.note("Reminder sent.")

    assert capsys.readouterr().out == ""
