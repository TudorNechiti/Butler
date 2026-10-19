# Job scout

One Telegram message a morning with the few backend jobs worth my time: medior roles in Berlin,
or remote within Germany/EU, scored against my profile by Claude. Fewer, better matches beat a
long list.

## How it works

```
company boards (Greenhouse, Lever, Ashby, Personio) ┐
Arbeitnow (free API)                                ├► Posting ► filter ► dedupe + seen? ► Claude score ► top N ► Telegram
Adzuna (free key, optional)                         ┘   (code)    (code)     (hashes)       (Haiku, no tools)
```

- **Sources** (`sources/`): one small module per API, all returning the same `Posting`. Adding a
  company is one `[[companies]]` entry in `config.toml`. Adding a hiring system is one module.
  Company boards come first, so their full ads win when the same job also appears on an aggregator.
- **Filters** (`filters.py`, plain code, free): drop clearly wrong titles (non-backend,
  junior-only, lead/staff/manager), places outside Berlin / remote Germany-EU, and ads whose
  *stated* yearly maximum is below the floor. "Senior" titles and ads without a salary pass:
  Claude judges those.
- **Dedupe** (`dedupe.py`): a job is its normalised company + title, so the same ad on three
  sites counts once. Jobs already scored are skipped for 60 days: the run keeps a small JSON file
  of hashes, carried between GitHub Actions runs by the Actions cache.
- **Scoring** (`scorer.py`): Haiku scores each new job from 0 to 100 against a committed rubric
  (`prompts/system.md`: seniority fit, English vs German, stack, location, salary) plus my
  profile. The profile comes from the `JOB_PROFILE` secret, never from git.
- **Digest** (`digest.py`): the best `max_matches` with score ≥ `min_score`: title, company,
  place, score, a one-line reason and the link. With no matches, nothing is sent.

`app.run()` returns a typed `JobDigest` and knows nothing about schedulers, so a later shared
morning brief (or an Azure Functions timer) can reuse it as is.

## Sources and their terms

| Source | Access | Notes |
|---|---|---|
| Greenhouse / Lever / Ashby boards | Public posting APIs, no auth | Meant for this use. Lever's EU instance would need `api.eu.lever.co`. |
| Personio | Public XML feed per company | Many feeds have no description, only the title. |
| [Arbeitnow](https://www.arbeitnow.com) | Free public API, no key | Asks for a link back (this one) and no abuse. 3 pages a day. |
| Adzuna | Free developer key, monthly call limit | Results must credit Adzuna: the digest says "Jobs by Adzuna" when one is shown. Snippets only. |

Not used: LinkedIn/Indeed scraping (against their terms), Indeed's API (closed to job seekers),
Bundesagentur für Arbeit (no official API). Job alert emails, Indeed's included, are planned for
v1.1 through read-only Gmail.

## Security model

Job ads are untrusted third-party text. Every field is sanitised (`core.sanitize`), single-line
fields stay single-line, and only `https://` links are kept. Claude gets no tools: it returns a
schema-checked score and reason, and plain code decides what is sent. The ad is wrapped in
`<posting>` tags that it can't close early, and the rubric tells Claude to score an ad that tries
to give instructions low. Logs carry counts and source names only (enforced by
`core.logging.EventLogger`, tested). `--preview` is blocked in CI because scores and reasons
reflect my private profile and Actions logs of a public repo are public. API errors are reduced to
a status code, so Adzuna's key (a URL parameter) can't reach the logs.

## Setup

1. `.env`: `JOB_PROFILE` (a few lines: experience, languages, work permit, location, salary
   floor, tech wanted), plus the Anthropic and Telegram values. Optionally `ADZUNA_APP_ID` and
   `ADZUNA_APP_KEY`.
2. Repository secrets: the same names. Unset Adzuna secrets just skip that source.

## Running

```sh
uv run python -m agents.job_scout --preview --max 5   # local: print scored jobs and the digest
uv run python -m agents.job_scout --dry-run            # score, but send nothing and save nothing
uv run python -m agents.job_scout                      # the real thing (what the cron runs)
uv run pytest -m live tests/job_scout                  # hit each real source once (free)
```

Manual runs from the Actions tab default to a dry run with 5 Claude calls.

## Tuning

All in `config.toml`: title keywords, location words, the salary floor, `min_score`,
`max_matches` and the company list. `--preview` shows every score and reason, which is the quickest
way to see whether a filter or the rubric needs changing.

## Cost

Fetching is free. Scoring uses Claude Haiku 4.5 at about $0.002 per job. After the filters and
the seen check that is 5-40 jobs a day, so about **$1-2 a month**. `max_calls` (40) caps a single
run at about $0.08. The first run is the most expensive, because every open job is new. GitHub
Actions free tier for the schedule and cache.
