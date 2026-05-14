# Job Scanner — Context

## Glossary

**Job Listing**
A single job posting scraped from one of the configured sources. Identified uniquely by its URL.

**Source**
A job board the scanner scrapes. Current sources: LinkedIn (public, no login), drushim.co.il, jobmaster.co.il, alljobs.co.il.

**Run**
One execution of the scanner. Happens twice daily (06:00 and 18:00 Israel time) via GitHub Actions cron.

**Digest Email**
A single email sent after each Run containing all Matching Listings, formatted in English with match score, short description, and fit reasoning.

**Match Score**
A percentage (0–100) produced by Gemini Flash representing how well a Job Listing fits the user's CV and preferences config. Only listings scoring ≥ 70% are included in the Digest Email.

**Seen Jobs**
The set of Job Listing URLs already sent to the user in a previous Digest Email. Stored in `seen_jobs.json` and committed back to the repo after each Run to prevent duplicates.

**Preferences Config**
`config.yaml` at the repo root. Defines target roles, experience level tolerance, location, match threshold, and email language. Read at the start of every Run.

**CV**
`Dor_Alagem_CV.pdf` at the repo root. Parsed by Gemini Flash at the start of every Run to extract skills and experience for matching.
