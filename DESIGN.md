# AI Job Search Agent — Design Document

**Author:** Ginny Thomas
**Status:** In Progress
**Last Updated:** March 2026

---

## 1. Problem Statement

Job hunting is inefficient in three specific ways this tool is designed to fix:

**The hallucination problem.** AI assistants like ChatGPT and custom GPTs cannot access live job boards. When asked about current openings, they fabricate results. Every listing they return is potentially fictional. This tool solves that by connecting directly to real job board APIs and scrapers, ensuring every result is a live posting.

**The incomplete profile problem.** A CV is a marketing document — curated for a specific context, deliberately selective, and quickly out of date. Matching jobs against a single CV means the tool only knows one version of the candidate at one point in time. Skills from earlier roles, domain expertise from a previous career, and achievements buried in performance reviews are all invisible. This tool solves that by building a rich candidate profile from multiple sources — CVs across time, year-end reviews, and self-reflections — so the matcher has access to the full picture.

**The ATS problem.** Most large companies filter applications through Applicant Tracking Systems before a human reads them. These systems do keyword matching — if your CV doesn't contain the right terms from the job description, you're filtered out regardless of your actual fit. This tool solves that by generating tailored, ATS-optimised resume versions assembled from the full candidate profile, for each role you decide to apply for.

---

## 2. Goals

- Build a rich candidate profile from multiple source documents
- Fetch live, real job listings from multiple sources with no hallucinations
- Score each listing honestly against the full candidate profile with clear reasoning
- Identify skill gaps and suggest concrete actions to close them
- Generate tailored, ATS-optimised resumes assembled from the full profile
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
┌──────────────────────────────────────────────────────────┐
│                     app.py (Streamlit UI)                │
│          User inputs → displays results + actions        │
└───────────┬──────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────┐
│  profile_builder.py │  Reads all source documents (CVs, reviews,
│                     │  reflections) and extracts a structured
│                     │  master candidate profile → data/profile.json
└─────────┬───────────┘
          │  data/profile.json (single source of truth)
          │
    ┌─────┴──────────────────────┐
    │                            │
    ▼                            ▼
┌─────────────────────┐   ┌─────────────────────┐
│   job_fetcher.py    │   │   job_matcher.py    │
│                     │   │                     │
│  Fetches live jobs  │   │  Scores each job    │
│  from JobSpy +      │   │  against the full   │
│  Adzuna API         │   │  candidate profile  │
└─────────┬───────────┘   └─────────┬───────────┘
          │                         │
          └────────────┬────────────┘
                       │  Ranked, scored listings
                       ▼
          ┌─────────────────────┐     ┌──────────────────────┐
          │  gap_analyser.py    │     │  resume_tailor.py    │
          │                     │     │                      │
          │  For a selected job │     │  Assembles a CV from │
          │  identifies missing │     │  the full profile,   │
          │  skills + suggests  │     │  tailored to ATS     │
          │  actions to close   │     │  keywords in the     │
          │  the gap            │     │  job description     │
          └─────────────────────┘     └──────────────────────┘
```

---

## 5. Components

### 5.1 `agents/profile_builder.py`

**Responsibility:** Read all candidate source documents and extract a structured master profile. This profile is the single source of truth used by all other agents.

**Status:** 🔲 Planned

**Inputs:**
- Any combination of: CV files (PDF or DOCX), year-end reviews, self-reflections, personal statements — stored in `data/source_documents/`

**Output:** `data/profile.json` — a structured candidate profile

**Profile schema:**
```python
{
    "full_name": str,
    "current_role": str,
    "technical_skills": {
        "languages": list,       # e.g. ["Python", "JavaScript", "Ruby", "Scala"]
        "frameworks": list,      # e.g. ["Flask", "React"]
        "cloud": list,           # e.g. ["AWS"]
        "tools": list,           # e.g. ["Git", "Docker"]
        "databases": list
    },
    "domain_knowledge": list,    # e.g. ["healthcare", "fintech", "tax systems"]
    "soft_skills": list,         # e.g. ["public speaking", "team leadership"]
    "experience": [
        {
            "role": str,
            "company": str,
            "dates": str,
            "achievements": list
        }
    ],
    "education": list,
    "certifications": list,
    "notable_achievements": list,  # Quantified wins e.g. "95% alert reduction"
    "source_documents": list       # Track which files were used
}
```

**Key design decisions:**
- The profile is regenerated whenever new source documents are added
- Skill names are normalised at extraction time (consistent casing, spacing) so all downstream agents work from clean data
- Claude is used to extract and reconcile information across multiple documents — it handles the case where the same skill appears differently across sources
- The profile stores more than any single CV would — earlier skills, domain knowledge from previous careers, achievements from performance reviews

---

### 5.2 `agents/job_fetcher.py`

**Responsibility:** Fetch live job listings from external sources and return a unified, deduplicated DataFrame.

**Status:** ✅ Built and tested

**Sources:**
- LinkedIn, Indeed, Glassdoor via `python-jobspy`
- Adzuna via REST API

**Key design decisions:**
- `MARKET_CONFIG` dictionary centralises all market-specific configuration. Adding a new market requires only a new dictionary entry — no other code changes
- `get_market_options()` exposes the market list to the UI, ensuring the dropdown and the config are always in sync (single source of truth)
- Remote markets append "remote" to the search term and pass `is_remote=True` to JobSpy for better filtering
- All external calls are wrapped in try/except — a failed source returns an empty DataFrame rather than crashing the app
- Each result is tagged with its `market` for display and filtering

**Markets supported:**
| Market | Sources | Adzuna Endpoint |
|---|---|---|
| Barcelona / Spain | LinkedIn, Indeed, Glassdoor, Adzuna | `es` |
| Remote UK | LinkedIn, Indeed, Glassdoor, Adzuna | `gb` |
| Remote US | LinkedIn, Indeed, Glassdoor, Adzuna | `us` |

---

### 5.3 `agents/job_matcher.py`

**Responsibility:** Score each job listing against the candidate's full profile and return structured match data.

**Status:** 🔲 Planned (tests next)

**Inputs:**
- `data/profile.json` — the full candidate profile
- A single job listing (title, company, description)

**Outputs per job:**
```python
{
    "match_score": int,          # 0–100
    "match_label": str,          # "Strong" (≥70), "Potential" (40–69), "Weak" (<40)
    "summary": str,              # One-sentence fit summary
    "matching_skills": list,     # Skills present in both profile and job
    "missing_skills": list,      # Skills in job description not in profile
    "reasoning": str,            # Claude's full reasoning
    "highlight_background": str  # Non-obvious profile strengths relevant to this role
                                 # e.g. nursing background for a health tech role
}
```

**Scoring thresholds:**
```python
STRONG_THRESHOLD = 70     # 70–100 → "Strong"
POTENTIAL_THRESHOLD = 40  # 40–69 → "Potential"
                          #  0–39 → "Weak"
```

**Key design decisions:**
- Matching is done against the full candidate profile, not a single CV — surfacing skills and experience that may not appear on the current CV
- `match_label` is always derived from `match_score` using the thresholds above — never returned independently by Claude — ensuring they can never be inconsistent
- A separate `_parse_match_response()` function handles all parsing and validation of Claude's JSON response, keeping error handling isolated and testable
- `normalise_skill()` is applied to all skill lists for consistent display and comparison
- Claude Haiku is used for bulk matching (speed and cost); Claude Sonnet is used for detailed single-role analysis
- `highlight_background` surfaces non-obvious strengths — e.g. clinical domain knowledge for a health data role — that the candidate might not think to emphasise

---

### 5.4 `agents/gap_analyser.py`

**Responsibility:** For a specific job, identify what's missing from the candidate profile and suggest concrete actions to close the gap.

**Status:** 🔲 Planned

**Inputs:**
- `data/profile.json`
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

### 5.5 `agents/resume_tailor.py`

**Responsibility:** Assemble an ATS-optimised CV tailored to a specific job description, drawing from the full candidate profile.

**Status:** 🔲 Planned

**Inputs:**
- `data/profile.json` — the full candidate profile
- Target job description
- Match output from `job_matcher.py`

**Outputs:**
- A tailored CV as a `.docx` file, downloadable from the UI
- A summary of what was selected, emphasised, and why

**Key design decisions:**
- The tailored CV is *assembled* from the full profile, not just a rewrite of the current CV — earlier skills, domain knowledge from previous careers, and relevant achievements can all be surfaced
- Claude selects and emphasises the most relevant subset of the profile for the specific role
- Keywords from the job description are woven in where the underlying experience genuinely supports it — nothing is fabricated
- For health tech roles, nursing background is surfaced. For data roles, analytical experience from any domain is included. The profile makes this possible.

---

### 5.6 `app.py` (Streamlit Frontend)

**Responsibility:** Provide the user interface. Orchestrates calls to all agents.

**Status:** 🔧 In Progress

**UI flow:**
1. Profile setup: upload source documents, trigger profile build
2. Sidebar: job title input, market selector, results count slider, search button
3. Results table: ranked by match score, with company, location, date, link, score, label
4. Job detail panel: click a job to see full match reasoning, highlighted strengths, and gap analysis
5. Resume tailor button: generates a downloadable tailored CV for the selected job

---

## 6. Data Flow

```
User uploads source documents (CVs, reviews, reflections)
        │
        ▼
profile_builder.py → extracts full candidate profile → data/profile.json
        │
        │   (profile is built once, reused for all searches)
        │
User inputs job title + market
        │
        ▼
job_fetcher.py → fetches N live jobs → DataFrame
        │
        ▼
job_matcher.py → scores each job against profile → adds score columns
        │
        ▼
app.py → displays ranked results table with scores and links
        │
        ├── User selects a job
        │         │
        │         ├── gap_analyser.py → displays gaps + suggestions
        │         │
        │         └── User clicks "Tailor Resume"
        │                   │
        │                   └── resume_tailor.py → .docx download
        │
        └── User clicks job URL → opens live posting in browser
```

---

## 7. Data Folder Structure

```
data/
├── source_documents/     # User uploads CVs, reviews, reflections here
│   ├── cv_2025.pdf
│   ├── cv_2022.pdf
│   └── yearend_2024.pdf
├── profile.json          # Generated by profile_builder — do not edit manually
└── .gitkeep
```

`profile.json` is generated and can be regenerated at any time. Source documents are local only and should never be committed to the repository — add `data/source_documents/` to `.gitignore`.

---

## 8. External Integrations

| Service | Purpose | Auth | Free Tier |
|---|---|---|---|
| Anthropic Claude API | Profile building, matching, gap analysis, resume tailoring | API key | Pay per token |
| JobSpy (python-jobspy) | LinkedIn, Indeed, Glassdoor scraping | None required | Yes |
| Adzuna API | Additional job listings, EU/UK/US coverage | App ID + API key | Yes (free tier) |

**Model strategy:**
- Claude Haiku — bulk job matching (fast, low cost)
- Claude Sonnet — profile building, detailed role analysis, resume tailoring (higher quality)

---

## 9. Configuration and Secrets

All secrets are stored in a `.env` file excluded from version control via `.gitignore`.

```
ANTHROPIC_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_API_KEY=...
```

An `.env.example` file is committed to the repository to show the required structure without exposing values.

The `data/source_documents/` folder is also excluded from version control — personal documents should never be committed to a public repository.

---

## 10. Testing Strategy

This project adopts **Test Driven Development (TDD)** from `job_matcher.py` onwards. Tests for `job_fetcher.py` were written retroactively.

**Framework:** `pytest`

**Structure:**
```
tests/
├── test_job_fetcher.py     ✅ 22 tests passing
├── test_profile_builder.py 🔲 Planned
├── test_job_matcher.py     🔲 Next
├── test_gap_analyser.py    🔲 Planned
└── test_resume_tailor.py   🔲 Planned
```

**Approach:**
- Agent logic is tested in isolation using mocked API responses — tests never make real API calls
- Each test file covers: expected happy path, empty inputs, malformed inputs, and API failure scenarios
- The TDD cycle for new agents: write failing tests → write minimum implementation → refactor
- Boundary conditions are explicitly tested for all scored/labelled outputs

---

## 11. Deployment

The app is deployed on **Streamlit Community Cloud** (free tier), connected directly to the GitHub repository. Pushes to `main` trigger automatic redeployment.

Secrets are configured via the Streamlit Cloud dashboard and are never stored in the repository.

**Live URL:** *(to be added on deployment)*

---

## 12. Future Enhancements

- **Application tracker:** Log which jobs have been applied for, with status and notes
- **Cover letter generator:** Generate tailored cover letters alongside the CV
- **Scheduled search:** Run searches automatically and surface new matches daily
- **Spanish language filter:** Optionally filter out non-English listings for the Barcelona market
- **Salary benchmarking:** Where salary data is available, surface it alongside match score
- **Fuzzy skill matching:** Use `rapidfuzz` library for more sophisticated skill normalisation beyond lowercase/strip
- **Profile versioning:** Track how the candidate profile evolves over time
