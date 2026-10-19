# Job scout agent (`agents/job_scout/`)

Read the root `CLAUDE.md` first; everything there still applies. This file adds what is specific
to this agent.

## Status

Planned. No code yet. This file holds the research and design notes so far.

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

## Recommended v1

Job alert emails + Arbeitnow + a list of 20-40 target Berlin companies on Greenhouse, Lever, Ashby
and Personio. The company list is the most useful part: it covers places I actually want to work.

## Pipeline

fetch -> filter in code -> ask Claude -> remove duplicates -> notify

1. **Fetch** from each source into one `Posting` model.
2. **Filter in code** first (keywords, location, seniority), so Claude only sees a few dozen
   candidates a day.
3. **Ask Claude** (cheapest model that works, likely Haiku) to score each candidate against my
   profile. Output is validated against a schema (score plus a short reason), same pattern as the
   email labeler. Posting text is untrusted: Claude gets no tools.
4. **Remove duplicates.** The same job often appears in an alert email, on Arbeitnow and on the
   company board. Match on normalised company + title, not each source's own ID. Store IDs already
   seen so nothing is sent twice.
5. **Notify**: one Telegram digest per day.

## Design notes

- One interface for company boards, something like `fetch_postings(company) -> list[Posting]`,
  with one small class per hiring system (Greenhouse, Lever, Ashby, Personio). Config lists
  `{company, system}` pairs, so adding a company is one config line and adding a system is one class.
- Reuse `core/`: config, Claude client with cost tracking, Telegram, logging, `sanitize`.
- Keep `run()` free of scheduler details, as in the habit tracker (Azure Functions port later).
- Logs carry ids and counts only, never posting text.

## Cost

Fetching is free. Claude scoring after the code filter costs cents per month. GitHub Actions free
tier for the schedule.

## Open decisions

- Where to store IDs already seen (file committed by the workflow, Actions cache, or a small
  store). Must survive between runs.
- The target company list and which hiring system each uses.
- How to store my profile for scoring. Butler is a public repo: keep personal details in a secret
  or env var, not in git.
- Digest time and how many matches to send.

## Butler roadmap (context)

1. Job scout (this agent).
2. A shared daily brief: agents return results and one step builds a single morning message,
   instead of each agent sending its own. Design this before or with the job scout.
3. Two-way Telegram: commands like `/done gym`, `/jobs`, and 👍/👎 on jobs to improve scoring.
   Only accept my own chat ID. Commands map to code, never free text passed to Claude.
4. Azure Functions once there are 3-4 agents: Bicep, Key Vault, App Insights.
5. Stock digest last (summaries only).

Skip here: Roborock (own project, unofficial API) and a web dashboard (Telegram covers it).
