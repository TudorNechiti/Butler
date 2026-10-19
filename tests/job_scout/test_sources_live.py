"""Hit each real job source once (no Claude, free). Run manually: pytest -m live tests/job_scout

These catch an API changing its shape. The companies are from the starter list; if one stops
using that hiring system, swap in another company that does.
"""

from collections.abc import Callable

import httpx
import pytest

from agents.job_scout.models import Posting
from agents.job_scout.sources import new_http_client
from agents.job_scout.sources.arbeitnow import Arbeitnow
from agents.job_scout.sources.ashby import Ashby
from agents.job_scout.sources.greenhouse import Greenhouse
from agents.job_scout.sources.lever import Lever
from agents.job_scout.sources.personio import Personio

pytestmark = pytest.mark.live

type Factory = Callable[[httpx.Client], list[Posting]]

SOURCES: dict[str, Factory] = {
    "arbeitnow": lambda http: Arbeitnow(http, 1, 500).fetch(),
    "greenhouse": lambda http: Greenhouse(http, "N26", "n26", 500).fetch(),
    "lever": lambda http: Lever(http, "FINN", "finn", 500).fetch(),
    "ashby": lambda http: Ashby(http, "Forto", "forto", 500).fetch(),
    "personio": lambda http: Personio(http, "1KOMMA5", "1komma5grad", 500).fetch(),
}


@pytest.mark.parametrize("name", SOURCES)
def test_source_returns_usable_postings(name: str) -> None:
    with new_http_client() as http:
        postings = SOURCES[name](http)

    assert postings, f"{name} returned no postings"
    assert all(p.title and p.external_id for p in postings)
    assert sum(1 for p in postings if p.url) / len(postings) > 0.9
