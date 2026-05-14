# Job Scanner

Automated job scanner for the Israeli market. Runs twice daily, scrapes major job boards, scores listings against your CV using Gemini, and emails you the matches.

## How it works

1. Scrapes LinkedIn, drushim.co.il, jobmaster.co.il, and alljobs.co.il
2. Filters by center district location
3. Scores each listing against your CV and preferences via Gemini Flash
4. Sends a digest email with listings scoring ≥ 70%
5. Tracks seen listings so you never get the same job twice

Runs at **06:00 and 18:00 Israel time** via GitHub Actions.

## Configuration

Edit `config.yaml` to adjust target roles, experience levels, location, and match threshold.

Replace `Dor_Alagem_CV.pdf` with your own CV to use with a different profile.

## Setup

### 1. Secrets

Add the following to your repo's **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | From [Google AI Studio](https://aistudio.google.com) |
| `GMAIL_FROM` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | From [Google Account → App Passwords](https://myaccount.google.com/apppasswords) |

### 2. Permissions

In **Settings → Actions → General**, set workflow permissions to **Read and write**.

### 3. Manual run

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
export GEMINI_API_KEY=...
export GMAIL_FROM=...
export GMAIL_APP_PASSWORD=...
python -m src.orchestrator
```
