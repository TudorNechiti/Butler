# Job scout agent (`agents/job_scout/`)

Read the root `CLAUDE.md` first; everything there still applies. This file adds what is specific
to this agent.

## Status

v1 built: company boards (Greenhouse, Lever, Ashby, Personio) + Arbeitnow + optional Adzuna,
daily on GitHub Actions. Job alert emails (LinkedIn, StepStone, Xing, Indeed) are v1.1. How it
works and how to run it: `README.md`. Below: the research and decisions behind it.

## Purpose

One daily Telegram digest of relevant medior backend roles in Berlin or remote, scored against my
profile. Fewer, better matches beat a long list.

## Sources

All free and allowed. No scraping.

| Source | Access | Fit | Risk |
|---|---|---|---|
| Job alert emails (LinkedIn, StepStone, Xing) | Existing Gmail read access | High: I choose the searches | Email format changes now and then. Content is untrusted |
| [Arbeitnow API](https://arbeitnow.com/blog/job-board-api/) | Free, no key. `GET https://arbeitnow.com/api/job-board-api`, JSON, follow the `next` link to page | Good: Berlin-based, listings come from company hiring systems, `remote` and `visa_sponsorship` flags | Low |
| Greenhouse boards | Public, no auth. `boards-api.greenhouse.io/v1/boards/{company}/jobs` (`?content=true` adds descriptions) | Very high for chosen companies | Low: these endpoints are meant for this use |
| Lever boards | Public, no auth. `api.lever.co/v0/postings/{company}?mode=json`. Docs: github.com/lever/postings-api | Very high for chosen companies | Low |
| Ashby boards | Public posting API per company | Very high for chosen companies | Low. Confirm the endpoint when building |
| Personio feeds | XML at `{company}.jobs.personio.de/xml`, common at German startups | High for German startups | Low. Check each company has one |
| Bundesagentur für Arbeit | Fixed public key, but [no official API](https://github.com/bundesAPI/jobsuche-api), only community docs | Huge volume, mostly non-tech and agency posts | **Unofficial and could break.** Leave out at first. If added, flag it in code and README |
| Adzuna | Free key. Reported limits vary (about 1,000 calls a month, or 250 a day). Descriptions are cut short | Medium | Optional, only if coverage is thin |

Don't use:

- Paid Apify scrapers: they charge per record for data the endpoints above give for free.
- LinkedIn scraping: against their terms and against Butler's rules. Their alert emails are fine.

## v1 scope

Arbeitnow + Adzuna + a starter list of Berlin companies on Greenhouse, Lever, Ashby and Personio
(no preferred companies yet: trim the list as the digests show what I like). Indeed has no API
open to job seekers and forbids scraping, so it comes in through alert emails in v1.1.

## Pipeline

fetch -> filter in code -> dedupe + drop already seen -> score with Claude -> top N -> notify -> save seen

1. **Fetch** from each source into one `Posting` model. One failing source doesn't stop the run.
2. **Filter in code** (title keywords, level, location, stated salary below the floor). Only
   what is clearly out. "Senior" titles and unknown salaries pass to Claude. No age filter:
   company boards list only open jobs, and roles stay open for months.
3. **Dedupe before Claude**, so nothing is paid for twice: normalised company + title, not each
   source's own ID. Skip jobs already in the seen store.
4. **Score with Claude** (Haiku, no tools, schema-validated score 0-100 plus reason), newest
   first, capped by `max_calls`. Everything scored is marked seen, not only what is sent.
   Refusals are marked seen too (deterministic); network errors are retried the next day.
5. **Notify**: one Telegram digest, nothing when there are no matches. The seen store is saved
   only after the send succeeds.

## Design notes

- One interface for company boards, something like `fetch_postings(company) -> list[Posting]`,
  with one small class per hiring system (Greenhouse, Lever, Ashby, Personio). Config lists
  `{company, system}` pairs, so adding a company is one config line and adding a system is one class.
- Reuse `core/`: config, Claude client with cost tracking, Telegram, logging, `sanitize`.
- Keep `run()` free of scheduler details, as in the habit tracker (Azure Functions port later).
- Logs carry ids and counts only, never posting text.

## Cost

Fetching is free. Scoring is about $0.002 per job on Haiku 4.5. At 5-40 new jobs a day that is
about $1-2 a month (not cents, as first estimated). `max_calls` caps one run at about $0.08.
GitHub Actions free tier for the schedule and cache.

## Decisions

- **Seen store:** hashed company+title keys with a first-seen date in a JSON file, carried
  between runs by the GitHub Actions cache (new entry per run, restored by prefix). If it is
  evicted, I see a few repeats once. Nothing about my search ends up in git.
- **Company list:** public in `config.toml`. The starter list holds boards that answered in
  October 2026.
- **Profile:** free text in the `JOB_PROFILE` secret, inserted into the committed rubric at
  runtime. Never in git, logs, tests or the Actions run page.
- **Salary floor in code:** a little under my real floor, and only applied to stated yearly maximums.
  Claude handles figures in the ad text.
- **Daily brief:** `run()` returns a `JobDigest`; `__main__` formats and sends it.
- **Digest:** daily around 08:45 Berlin, up to 8 matches with score >= 60.

## Butler roadmap (context)

1. Job scout (this agent).
2. A shared daily brief: agents return results and one step builds a single morning message,
   instead of each agent sending its own. Design this before or with the job scout.
3. Two-way Telegram: commands like `/done gym`, `/jobs`, and 👍/👎 on jobs to improve scoring.
   Only accept my own chat ID. Commands map to code, never free text passed to Claude.
4. Azure Functions once there are 3-4 agents: Bicep, Key Vault, App Insights.
5. Stock digest last (summaries only).

Skip here: Roborock (own project, unofficial API) and a web dashboard (Telegram covers it).
