# Job Scanner — Context

## Glossary

**Job Listing**
A single job posting scraped from one of the configured sources. Identified uniquely by its URL.

**Source**
A job board the scanner scrapes. Current sources: LinkedIn (public, no login), drushim.co.il, jobmaster.co.il, alljobs.co.il.

**Run**
One execution of the scanner. Happens twice daily (06:00 and 18:00 Israel time), triggered by cron-job.org via `workflow_dispatch` on GitHub Actions.

**Digest Email**
A single email sent after each Run containing all Matching Listings, formatted in English with match score, short description, and fit reasoning.

**Match Score**
A percentage (0–100) produced by Groq (Llama 3.1 8B Instant) representing how well a Job Listing fits the user's CV and preferences config. Only listings scoring ≥ the configured `match_threshold` (default 60%) are included in the Digest Email.

**Pre-Filter**
A rule-based pass that runs before any LLM call. Drops listings that fail region, title-keyword (seniority/unwanted roles), or experience-year checks. Pre-filtered listings are not marked Seen, so they re-appear if filter rules change in a future Run.

**Search Terms**
Keywords used by scrapers to query job boards. Defined in `config.yaml` under `search_terms`. Drushim scrapes by category and ignores these terms.

**Seen Jobs**
The set of Job Listing URLs already evaluated by the LLM. Stored in `seen_jobs.json` and committed back to the repo after each Run to prevent duplicates. Pre-filtered listings are intentionally excluded from this set.

**Preferences Config**
`config.yaml` at the repo root. Defines target regions, experience level tolerance, match threshold, email recipient, search terms, and filter rules. Read at the start of every Run.

**CV**
`Dor_Alagem_CV.pdf` at the repo root. Parsed at the start of every Run to extract skills and experience for matching.
