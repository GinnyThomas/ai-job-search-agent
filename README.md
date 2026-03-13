# AI Job Search Agent

An AI-powered job search assistant that builds a rich candidate profile from your documents, matches live job listings against it, analyses gaps honestly, and generates tailored, ATS-optimised CVs for each role you want to apply for.

Built with Python, Streamlit, and the Anthropic Claude API.

---

## Why this exists

Most AI job search tools have one of three problems:

- **Hallucinated listings** — ChatGPT and similar tools fabricate job postings because they have no access to live job boards.
- **Thin profile** — Matching against a single CV means the tool only knows one curated snapshot of you, missing years of context.
- **Generic CVs** — ATS systems filter on keywords. A CV that isn't tailored to the specific job description gets filtered before a human sees it.

This tool fixes all three.

---

## Features

**Profile builder (Tab 1)**
- Extracts a rich, structured profile from multiple source documents (PDF, DOCX, TXT)
- Captures skill proficiency (`Expert / Proficient / Familiar / Basic`), recency, and context
- Separates current skills from historical/rusty skills
- Captures domain knowledge with depth and years — especially valuable for career-changers
- Inline proficiency editing so you can correct Claude's assessments
- Persists across sessions locally; rebuilt on Streamlit Cloud

**Job search (Tab 2)**
- Fetches live listings from LinkedIn, Indeed, Glassdoor (via JobSpy) and Adzuna
- Markets: Barcelona/Spain, Remote UK, Remote US
- Scores each listing against your full profile using Claude Haiku — cost-effective bulk matching
- Weighted scoring: recent production skills score higher than bootcamp skills
- Gap analysis per job: alignment points, genuine gaps, quick wins, honest assessment
- Tailored CV generation: `.docx` download per role

**Fit checker (Tab 3 — "Am I a good fit?")**
- For jobs found outside the search tab (LinkedIn email, recruiter message, any URL)
- Accepts a job URL or paste of the job description directly
- Runs fit scoring and gap analysis together automatically
- Save jobs to a persistent list with gap analysis attached
- Tailored CV download per saved job

---

## Tech stack

| Component | Technology |
|---|---|
| UI | Streamlit |
| AI | Anthropic Claude (Haiku for bulk matching, Sonnet for analysis and tailoring) |
| Job sources | JobSpy (LinkedIn/Indeed/Glassdoor), Adzuna API |
| CV output | python-docx |
| PDF parsing | pdfplumber |
| Testing | pytest (198 tests, no real API calls) |

---

## Project structure

```
agents/
├── profile_builder.py    # Extract enriched profile from source documents
├── job_fetcher.py        # Fetch live listings from job boards
├── job_matcher.py        # Score listings against profile (Claude Haiku)
├── gap_analyser.py       # Deep gap analysis (Claude Sonnet)
├── resume_tailor.py      # ATS-optimised CV text (uses gap brief)
├── cv_renderer.py        # Render tailored CV as .docx
└── saved_jobs.py         # Atomic JSON persistence for bookmarked jobs

tests/
├── test_profile_builder.py   # 57 tests
├── test_job_fetcher.py       # 38 tests
├── test_job_matcher.py       # 50 tests
├── test_gap_analyser.py      # 28 tests
├── test_resume_tailor.py     # 11 tests
└── test_saved_jobs.py        # 14 tests

data/
├── source_documents/     # Your CVs, year-end reviews, etc. (gitignored)
├── profile.json          # Generated profile (gitignored)
├── saved_jobs.json       # Saved jobs with gap analysis (gitignored)
└── settings.json         # Persisted preferences (gitignored)

app.py                    # Streamlit entry point
DESIGN.md                 # Full architecture and design decisions
```

---

## Setup

**Requirements:** Python 3.11+, an Anthropic API key, and an Adzuna API key (free tier).

```bash
# Clone and install dependencies
git clone https://github.com/yourusername/ai-job-search-agent.git
cd ai-job-search-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure secrets
cp .env.example .env
# Edit .env and add:
#   ANTHROPIC_API_KEY=your_key_here
#   ADZUNA_APP_ID=your_app_id
#   ADZUNA_API_KEY=your_api_key

# Run
streamlit run app.py
```

---

## Usage

1. **Build your profile** — Upload your CVs, year-end reviews, and any self-reflection documents in Tab 1. Claude extracts skills, domain knowledge, and experience with proficiency ratings. Correct any ratings that are off.

2. **Search for jobs** — Enter a job title and market in Tab 2. Results are ranked by match score with reasoning. Click any result to see the full analysis and generate a tailored CV.

3. **Check external jobs** — In Tab 3, paste a job URL or description for any role you found elsewhere. Get a fit score, gap analysis, and tailored CV without needing it to appear in search results.

---

## Running tests

```bash
python -m pytest tests/ -v
```

All 198 tests run without network access or real API calls — `anthropic.Anthropic` is mocked throughout.

---

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API access |
| `ADZUNA_APP_ID` | Yes | Adzuna job listings |
| `ADZUNA_API_KEY` | Yes | Adzuna job listings |

---

## Deployment

Deployed on Streamlit Community Cloud. Pushes to `main` auto-redeploy. Secrets configured via the Streamlit Cloud dashboard — never stored in the repository.

**Note:** Streamlit Community Cloud uses an ephemeral filesystem. `data/profile.json` and saved jobs are lost on app restart. Users rebuild their profile each session on the hosted version. For persistent storage, run locally.

---

## Design decisions

See [DESIGN.md](DESIGN.md) for the full architecture document, including:
- Enriched skill schema (proficiency + recency + context)
- Two-call architecture (gap analysis → resume tailoring)
- Preserve-and-warn pattern for gap analysis state management
- Defensive parsing strategy for Claude API responses
- Atomic write strategy for saved jobs
