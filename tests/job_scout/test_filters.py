import pytest

from agents.job_scout.filters import PostingFilter, word_pattern
from tests.job_scout.fakes import FILTERS, make_posting

FILTER = PostingFilter(FILTERS)


@pytest.mark.parametrize(
    ("title", "location", "remote", "expected"),
    [
        ("Backend Engineer (Java)", "Berlin", None, None),
        ("Senior Backend Engineer", "Berlin, Germany", None, None),  # "Senior" is for Claude
        ("Senior SRE", "Remote - Germany", None, None),
        ("Backend Engineer", "Munich", True, None),  # remote flag, region not excluded
        ("Sales Manager", "Berlin", None, "title"),
        ("Junior Backend Engineer", "Berlin", None, "level_or_role"),
        ("Backend Tech Lead", "Berlin", None, "level_or_role"),
        ("Staff Software Engineer", "Berlin", None, "level_or_role"),
        ("Frontend / Backend Engineer", "Berlin", None, "level_or_role"),
        ("Backend Engineer", "Munich", None, "location"),
        ("Backend Engineer", "Munich", False, "location"),
        ("Backend Engineer", "Remote, US", None, "location"),
        ("Backend Engineer", "Remote (UK)", True, "location"),
    ],
)
def test_reject_reason(title: str, location: str, remote: bool | None, expected: str) -> None:
    posting = make_posting(title=title, location=location, remote=remote)
    assert FILTER.reject_reason(posting) == expected


def test_salary_drops_only_an_explicit_maximum_below_the_floor() -> None:
    assert FILTER.reject_reason(make_posting(salary_max_eur=55000)) == "salary"
    assert FILTER.reject_reason(make_posting(salary_max_eur=80000)) is None
    assert FILTER.reject_reason(make_posting(salary_max_eur=None)) is None


def test_whole_words_only() -> None:
    pattern = word_pattern(["lead", "us"])
    assert pattern.search("Tech Lead")
    assert pattern.search("Lead-Entwickler")
    assert not pattern.search("Leading backend platform")
    assert not pattern.search("Austria")


def test_apply_counts_rejections() -> None:
    postings = [make_posting(), make_posting(title="Recruiter"), make_posting(location="Paris")]

    kept, rejected = FILTER.apply(postings)

    assert kept == [postings[0]]
    assert rejected == {"title": 1, "location": 1}
