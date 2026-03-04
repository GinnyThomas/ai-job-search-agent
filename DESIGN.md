# AI Job Search Agent — Design Document

**Author:** Ginny Thomas
**Status:** In Progress
**Last Updated:** March 2026

---

## 1. Problem Statement

Job hunting is inefficient in two specific ways this tool is designed to fix:

**The hallucination problem.** AI assistants like ChatGPT and custom GPTs cannot access live job boards. When asked about current openings, they fabricate results. Every listing they return is potentially fictional. This tool solves that by connecting directly to real job board APIs and scrapers, ensuring every result is a live posting.

**The ATS problem.** Most large companies filter applications through Applicant Tracking Systems before a human ever reads them. These systems do keyword matching — if your CV doesn't contain the right terms from the job description, you're filtered out regardless of your actual fit. This tool solves that by generating tailored, ATS-optimised resume versions for each role you decide to apply for.

**The wasted effort problem.** Applying for roles where your skills don't align wastes time and is demoralising. This tool scores each job against your CV and provides honest reasoning, so you only spend time on applications where you have a genuine shot — or where a small, targeted side project would close the gap.

---

## 2. Goals

- Fetch live, real job listings from multiple sources with no hallucinations
- Score each listing honestly against the user's CV with clear reasoning
- Identify skill gaps and suggest concrete actions to close them
- Generate tailored, ATS-optimised resumes for strong-match roles
- Provide direct links to every job posting for one-click access
- Support multiple job markets from a single interface
- Be deployable as a live web app accessible from any browser

---

## 3. Non-Goals

- Automatically submitting applications on the user's behalf
- Storing or managing recruiter communications
- Accessing job boards by logging in as the user (Terms of Service risk)
- Real-time notifications or background job polling (possible future enhancement)

---

## 4. Architecture Overview

The system is organised as a set of independent agents, each with a single responsibility, orchestrated by a Streamlit frontend.

```
┌─────────────────────────────────────────────────────┐
│                    app.py (Streamlit UI)             │
│         User inputs → displays results + actions    │
└───────────┬─────────────────────────────────────────┘
            │
            ▼
┌─────────────────────┐
│   job_fetcher.py    │  Fetches live jobs from external sources
│                     │  JobSpy (LinkedIn, Indeed, Glassdoor)
│                     │  Adzuna API
└─────────┬───────────┘
          │  DataFrame of live job listings
          ▼
┌─────────────────────┐
│   job_matcher.py    │  Scores each job against the user's CV
│                     │  Uses Claude API for reasoning
│                     │  Returns: score, reasoning, fit summary
└─────────┬───────────┘
          │  Ranked, scored listings
          ▼
┌─────────────────────┐     ┌──────────────────────┐
│  gap_analyser.py    │     │  resume_tailor.py    │
│                     │     │                      │
│  For a selected job │     │  For a selected job  │
│  identifies missing │     │  generates a CV      │
│  skills + suggests  │     │  tailored to ATS     │
│  actions to close   │     │  keywords in the     │
│  the gap            │     │  job description     │
└─────────────────────┘     └──────────────────────┘
```

---

## 5. Components

### 5.1 `agents/job_fetcher.py`

**Responsibility:** Fetch live job listings from external sources and return a unified, deduplicated DataFrame.

**Status:** ✅ Built

**Sources:**
- LinkedIn, Indeed, Glassdoor via `python-jobspy`
- Adzuna via REST API

**Key design decisions:**
- `MARKET_CONFIG` dictionary centralises all market-specific configuration. Adding a new market requires only a new dictionary entry — no other code changes.
- `get_market_options()` exposes the market list to the UI, ensuring the dropdown and the config are always in sync (single source of truth).
- Remote markets append "remote" to the search term and pass `is_remote=True` to JobSpy for better filtering.
- All external calls are wrapped in try/except — a failed source returns an empty DataFrame rather than crashing the app.
- Each result is tagged with its `market` for display and filtering.

**Markets supported:**
| Market | Sources | Adzuna Endpoint |
|---|---|---|
| Barcelona / Spain | LinkedIn, Indeed, Glassdoor, Adzuna | `es` |
| Remote UK | LinkedIn, Indeed, Glassdoor, Adzuna | `gb` |
| Remote US | LinkedIn, Indeed, Glassdoor, Adzuna | `us` |

---

### 5.2 `agents/job_matcher.py`

**Responsibility:** Score each job listing against the user's CV and return structured match data.

**Status:** 🔲 Planned

**Inputs:**
- User's CV (text extracted from PDF or DOCX)
- A single job listing (title, company, description)

**Outputs per job:**
```python
{
    "match_score": int,          # 0–100
    "match_label": str,          # "Strong", "Potential", "Weak"
    "summary": str,              # One-sentence fit summary
    "matching_skills": list,     # Skills present in both CV and job
    "missing_skills": list,      # Skills in job description not in CV
    "reasoning": str             # Claude's full reasoning
}
```

**Approach:** Each job description and the CV are passed to Claude with a structured prompt. Claude returns a JSON response we parse into the schema above. We use Claude Haiku for bulk matching (speed + cost) and Claude Sonnet for detailed analysis on selected roles.

---

### 5.3 `agents/gap_analyser.py`

**Responsibility:** For a specific job, identify what's missing from the user's profile and suggest concrete actions to close the gap.

**Status:** 🔲 Planned

**Inputs:**
- User's CV
- A single job listing
- The match output from `job_matcher.py`

**Outputs:**
```python
{
    "gaps": list,               # Specific missing skills or experience
    "suggestions": list,        # Concrete actions (e.g. "Build a FastAPI project")
    "effort_estimate": str,     # "1 weekend", "2–3 weeks", etc.
    "apply_now": bool           # True if strong enough match to apply immediately
}
```

---

### 5.4 `agents/resume_tailor.py`

**Responsibility:** Generate an ATS-optimised version of the user's CV tailored to a specific job description.

**Status:** 🔲 Planned

**Inputs:**
- User's base CV (text)
- Target job description
- Match output from `job_matcher.py`

**Outputs:**
- A tailored CV as a `.docx` file, downloadable from the UI
- A summary of what was changed and why

**Approach:** Claude rewrites the CV summary and reorders/reframes bullet points to reflect the language of the job description, without fabricating experience. Keywords from the job description are woven in where the underlying experience genuinely supports it.

---

### 5.5 `app.py` (Streamlit Frontend)

**Responsibility:** Provide the user interface. Orchestrates calls to all agents.

**Status:** 🔧 In Progress

**UI flow:**
1. Sidebar: job title input, market selector, results count slider, search button
2. Results table: ranked by match score, with company, location, date, link, score
3. Job detail panel: click a job to see full match reasoning and gap analysis
4. Resume tailor button: generates a downloadable tailored CV for the selected job

---

## 6. Data Flow

```
User inputs job title + market
        │
        ▼
job_fetcher.py → fetches N live jobs → DataFrame
        │
        ▼
job_matcher.py → scores each job against CV → adds score columns to DataFrame
        │
        ▼
app.py → displays ranked results table
        │
        ├── User selects a job
        │         │
        │         ├── gap_analyser.py → displays gap + suggestions
        │         │
        │         └── User clicks "Tailor Resume"
        │                   │
        │                   └── resume_tailor.py → returns .docx download
        │
        └── User clicks job URL → opens live posting in browser
```

---

## 7. External Integrations

| Service | Purpose | Auth | Free Tier |
|---|---|---|---|
| Anthropic Claude API | Matching, gap analysis, resume tailoring | API key | Pay per token |
| JobSpy (python-jobspy) | LinkedIn, Indeed, Glassdoor scraping | None required | Yes |
| Adzuna API | Additional job listings, EU/UK/US coverage | App ID + API key | Yes (free tier) |

---

## 8. Configuration and Secrets

All secrets are stored in a `.env` file which is excluded from version control via `.gitignore`.

```
ANTHROPIC_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_API_KEY=...
```

An `.env.example` file is committed to the repository to show the required structure without exposing values.

---

## 9. Testing Strategy

This project adopts **Test Driven Development (TDD)** from the `job_matcher.py` agent onwards. Tests for `job_fetcher.py` will be written retroactively.

**Framework:** `pytest`

**Structure:**
```
tests/
├── test_job_fetcher.py
├── test_job_matcher.py
├── test_gap_analyser.py
└── test_resume_tailor.py
```

**Approach:**
- Agent logic is tested in isolation using mocked API responses — tests should never make real API calls
- Each test file covers: expected happy path, empty inputs, malformed inputs, and API failure scenarios
- The TDD cycle for new agents: write failing test → write minimum implementation → refactor

---

## 10. Deployment

The app is deployed on **Streamlit Community Cloud** (free tier), connected directly to the GitHub repository. Pushes to `main` trigger automatic redeployment.

Secrets are configured via the Streamlit Cloud dashboard and are never stored in the repository.

**Live URL:** *(to be added on deployment)*

---

## 11. Future Enhancements

- **Application tracker:** Log which jobs have been applied for, with status and notes
- **Cover letter generator:** Generate tailored cover letters alongside the CV
- **Scheduled search:** Run searches automatically and surface new matches daily
- **Spanish language filter:** Optionally filter out non-English listings for the Barcelona market
- **Salary benchmarking:** Where salary data is available, surface it alongside match score
- **Multi-CV support:** Support different base CVs for different role types (e.g. backend vs data engineering)
