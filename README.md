# Job Scanner

Automated job scanner for the Israeli market. Runs twice daily, scrapes major job boards, scores listings against your CV using Groq (Llama 3.1), and emails you the matches.

## How it works

1. Scrapes LinkedIn, drushim.co.il, jobmaster.co.il, and alljobs.co.il
2. Filters by center district location
3. Scores each listing against your CV and preferences via Groq (Llama 3.1)
4. Sends a digest email with listings scoring ≥ 70%
5. Tracks seen listings so you never get the same job twice

Runs at **06:00 and 18:00 Israel time** via cron-job.org, which triggers the GitHub Actions workflow at exact times.

## Configuration

Edit `config.yaml` to adjust regions, match threshold, seniority/unwanted keyword filters, max years of experience, and per-role experience overrides.

Replace `Dor_Alagem_CV.pdf` with your own CV to use with a different profile.

## Setup

### 1. Secrets

Add the following to your repo's **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `GROQ_API_KEY` | From [Groq Console](https://console.groq.com) |
| `GMAIL_FROM` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | From [Google Account → App Passwords](https://myaccount.google.com/apppasswords) |

### 2. Permissions

In **Settings → Actions → General**, set workflow permissions to **Read and write**.

### 3. Scheduling

Create two cron jobs on [cron-job.org](https://cron-job.org) (free), each sending a `POST` to:

```
https://api.github.com/repos/<your-username>/<your-repo>/actions/workflows/scan.yml/dispatches
```

With headers `Authorization: Bearer <github_pat>` and `Accept: application/vnd.github+json`, and body `{"ref": "master"}`.

Schedule one at **06:00** and one at **18:00** in your timezone. This triggers the workflow at exact times, bypassing GitHub's unreliable scheduler.

### 4. Manual run

Trigger a test run from the **Actions** tab → **Job Scanner** → **Run workflow**.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

To run the scanner locally:

```bash
export GROQ_API_KEY=...
export GMAIL_FROM=...
export GMAIL_APP_PASSWORD=...
python -m src.orchestrator
```
