# AI Job Search Agent — Design Document

**Author:** Ginny Thomas
**Status:** In Progress
**Last Updated:** March 2026

---

## 1. Problem Statement

Job hunting is inefficient in three specific ways this tool is designed to fix:

**The hallucination problem.** AI assistants like ChatGPT and custom GPTs cannot access live job boards. When asked about current openings, they fabricate results. Every listing they return is potentially fictional. This tool solves that by connecting directly to real job board APIs and scrapers, ensuring every result is a live posting.

**The incomplete profile problem.** A CV is a marketing document — curated for a specific context, deliberately selective, and quickly out of date. Matching jobs against a single CV means the tool only knows one version of the candidate at one point in time. Skills from earlier roles, domain expertise from a previous career, and achievements buried in performance reviews are all invisible. This tool solves that by building a rich candidate profile from multiple sources — CVs across time, year-end reviews, and self-reflections.

**The ATS problem.** Most large companies filter applications through Applicant Tracking Systems before a human reads them. These systems do keyword matching — if your CV doesn't contain the right terms from the job description, you're filtered out regardless of your actual fit. This tool solves that by generating tailored, ATS-optimised resume versions assembled from the full candidate profile, for each role you decide to apply for.

---

## 2. Goals

- Build a rich candidate profile from multiple source documents, including skill proficiency and recency
- Fetch live, real job listings from multiple sources with no hallucinations
- Score each listing honestly against the full candidate profile with clear reasoning
- Weight skill matches appropriately — recent production skills score differently from historical bootcamp skills
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
│                     │  Skills include proficiency + recency metadata
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
│  Adzuna API         │   │  candidate profile, │
└─────────┬───────────┘   │  weighting by skill │
          │               │  recency/proficiency│
          │               └─────────┬───────────┘
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

**Responsibility:** Read all candidate source documents and extract a structured master profile with enriched skill metadata. This profile is the single source of truth used by all other agents.

**Status:** 🔲 Planned (tests next)

**Supported file formats:** PDF, DOCX, plain text (.txt)

**Required libraries:** `pdfplumber`, `python-docx`

**Inputs:**
- Any combination of: CV files (PDF or DOCX), year-end reviews, self-reflections, personal statements — stored in `data/source_documents/`

**Output:** `data/profile.json`

---

#### Enriched Skill Schema

Skills are **not** stored as flat strings. Each skill is an object capturing proficiency and recency so downstream agents can score appropriately.

A bootcamp skill from 4 years ago should not score the same as a production skill used until last month:

```python
# Historical / low-confidence skill
{
    "name": "ruby",              # Always normalised: lowercase, stripped
    "proficiency": "Basic",      # Expert | Proficient | Familiar | Basic
    "last_used": "2022",
    "context": "Coding bootcamp — Makers Academy",
    "is_current": False
}

# Current / high-confidence skill
{
    "name": "python",
    "proficiency": "Proficient",
    "last_used": "2025",
    "context": "Production engineering at HMRC — alerting systems, data pipelines",
    "is_current": True
}
```

**Proficiency levels:**

| Level | Meaning |
|---|---|
| `Expert` | Deep, long-term mastery — could teach it |
| `Proficient` | Solid production experience |
| `Familiar` | Used meaningfully but not deeply |
| `Basic` | Introductory or bootcamp level only |

**Claude infers proficiency and recency from document context.** "Built production alerting systems in Python" → Proficient, current. "Completed Ruby exercises at Makers Academy" → Basic, 2022.

---

#### Enriched Domain Knowledge Schema

Domain knowledge is stored separately from technical skills — it represents industry or problem-space expertise, often accumulated over an entire career:

```python
{
    "domain": "healthcare / clinical systems",
    "depth": "Expert",          # Expert | Proficient | Familiar
    "years": 10,
    "context": "Registered Nurse Practitioner — clinical assessment, patient care",
    "is_current": False         # Not current employment but knowledge remains
}
```

This is what allows `job_matcher` to recognise that a nursing background is a genuine differentiator for a health data engineering role — not just a tag, but deep domain expertise with context.

---

#### Full Profile Schema

```python
{
    "full_name": str,
    "current_role": str,
    "technical_skills": [
        {
            "name": str,           # Normalised: lowercase, stripped
            "proficiency": str,    # Expert | Proficient | Familiar | Basic
            "last_used": str,      # Year as string e.g. "2025"
            "context": str,        # Where/how this skill was used
            "is_current": bool
        }
    ],
    "domain_knowledge": [
        {
            "domain": str,
            "depth": str,          # Expert | Proficient | Familiar
            "years": int,
            "context": str,
            "is_current": bool
        }
    ],
    "soft_skills": list,           # Flat list — proficiency less relevant here
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
    "notable_achievements": list,
    "source_documents": list       # Which files were used to build this profile
}
```

**Key design decisions:**
- Profile is fully regenerated when new documents are added — no partial updates
- Skill names normalised at extraction time (lowercase, stripped) — all downstream agents work from clean data
- When merging skills across documents, deduplication uses the normalised name — "JavaScript" and "javascript" from different CVs become one entry, keeping the higher proficiency
- For scalar fields (name, current role), the most recently dated document wins
- For list fields (skills, experience), all documents contribute and are deduplicated

---

#### Internal Functions

```
_extract_text_from_pdf(path)        → str
_extract_text_from_docx(path)       → str
_extract_text_from_file(path)       → str   (dispatches by extension)
_extract_profile_from_text(text)    → dict  (calls Claude)
_merge_profiles(profiles)           → dict  (combines, deduplicates)
build_profile(source_dir)           → dict  (main orchestrator)
save_profile(profile, output_path)  → None
load_profile(path)                  → dict
```

---

### 5.2 `agents/job_fetcher.py`

**Responsibility:** Fetch live job listings from external sources and return a unified, deduplicated DataFrame.

**Status:** ✅ Built and tested (22 tests passing)

**Markets supported:**
| Market | Sources | Adzuna Endpoint |
|---|---|---|
| Barcelona / Spain | LinkedIn, Indeed, Glassdoor, Adzuna | `es` |
| Remote UK | LinkedIn, Indeed, Glassdoor, Adzuna | `gb` |
| Remote US | LinkedIn, Indeed, Glassdoor, Adzuna | `us` |

---

### 5.3 `agents/job_matcher.py`

**Responsibility:** Score each job listing against the candidate's full profile and return structured match data.

**Status:** ✅ Built and tested (41 tests passing)

**Scoring thresholds:**
```python
STRONG_THRESHOLD = 70     # 70–100 → "Strong"
POTENTIAL_THRESHOLD = 40  # 40–69 → "Potential"
                          #  0–39 → "Weak"
```

**Outputs per job:**
```python
{
    "match_score": int,          # 0–100
    "match_label": str,          # "Strong" | "Potential" | "Weak"
    "summary": str,
    "matching_skills": list,     # Normalised skill names
    "missing_skills": list,      # Normalised skill names
    "reasoning": str,
    "highlight_background": str  # Non-obvious profile strengths for this role
}
```

**Prompt structure for scoring (weighted criteria):**

The enriched skill profile is passed to Claude with full context, not a flat list:

```
Technical Skills:
  - python: Proficient — production engineering at HMRC until 2025 (current)
  - ruby: Basic — coding bootcamp only, 2022 (not current)
  - scala: Proficient — production use 2022–2025 (may be rusty)
  - aws: Proficient — certified, current

Domain Knowledge:
  - healthcare / clinical systems: Expert — 10 years as Nurse Practitioner
```

This means Claude scores Ruby appropriately — the knowledge exists but the matcher will reflect its age. A Ruby role might score 55 (Potential) rather than 90 (Strong), with reasoning explaining the gap.

**Key design decisions:**
- `match_label` always derived from `match_score` in our code — never from Claude
- `_parse_match_response()` handles all validation and edge cases in isolation
- Claude Haiku for bulk matching; Claude Sonnet for detailed single-role analysis

---

### 5.4 `agents/gap_analyser.py`

**Responsibility:** For a specific job, identify what's missing from the candidate profile and suggest concrete actions to close the gap.

**Status:** 🔲 Planned

**Outputs:**
```python
{
    "gaps": list,
    "suggestions": list,        # e.g. "Build a small FastAPI project"
    "effort_estimate": str,     # "1 weekend", "2–3 weeks"
    "apply_now": bool
}
```

The enriched skill schema makes gap analysis more nuanced — a "Basic / not current" skill is a softer gap than a skill that's completely absent.

---

### 5.5 `agents/resume_tailor.py`

**Responsibility:** Assemble an ATS-optimised CV tailored to a specific job description, drawing from the full candidate profile.

**Status:** 🔲 Planned

**Key design decision:** The tailored CV is *assembled* from the full profile — earlier skills, domain knowledge from previous careers, and relevant achievements can all be surfaced. For a health tech role, nursing background is included. For a data role, analytical experience from any domain is considered.

---

### 5.6 `app.py`

**Status:** 🔧 In Progress

**UI flow:**
1. Profile setup — upload source documents, trigger profile build
2. Sidebar — job title, market selector, results count, search
3. Results table — ranked by match score with links, scores, labels
4. Job detail panel — match reasoning, highlighted strengths, gap analysis
5. Resume tailor button — downloadable tailored CV

---

## 6. Data Flow

```
User uploads source documents (CVs, reviews, reflections)
        │
        ▼
profile_builder.py → extracts enriched profile → data/profile.json
        │
        │   (profile built once, reused for all searches)
        │
User inputs job title + market
        │
        ▼
job_fetcher.py → fetches live jobs → DataFrame
        │
        ▼
job_matcher.py → scores each job against enriched profile
               → skill recency/proficiency informs scoring
        │
        ▼
app.py → ranked results table with scores and direct links
        │
        ├── User selects a job
        │         ├── gap_analyser.py → gaps + suggestions
        │         └── "Tailor Resume" → resume_tailor.py → .docx download
        │
        └── User clicks job URL → live posting in browser
```

---

## 7. Data Folder Structure

```
data/
├── source_documents/     # User uploads CVs, reviews, reflections here
│   ├── cv_2025.pdf       # gitignored — personal documents stay local
│   ├── cv_2022.pdf
│   └── yearend_2024.pdf
├── profile.json          # Generated by profile_builder — do not edit manually
└── .gitkeep
```

`data/source_documents/` is excluded from version control — personal documents should never be committed to a public repository.

---

## 8. External Integrations

| Service | Purpose | Auth | Free Tier |
|---|---|---|---|
| Anthropic Claude API | Profile building, matching, gap analysis, resume tailoring | API key | Pay per token |
| JobSpy (python-jobspy) | LinkedIn, Indeed, Glassdoor scraping | None | Yes |
| Adzuna API | Additional listings, EU/UK/US coverage | App ID + API key | Yes |

**Model strategy:**
- Claude Haiku — bulk job matching (fast, low cost)
- Claude Sonnet — profile building, detailed analysis, resume tailoring

---

## 9. Configuration and Secrets

```
ANTHROPIC_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_API_KEY=...
```

`data/source_documents/` and `.env` are both excluded from version control.

---

## 10. Testing Strategy

**Framework:** `pytest`
**Approach:** TDD from `job_matcher.py` onwards. Tests for `job_fetcher.py` written retroactively.

```
tests/
├── test_job_fetcher.py       ✅ 22 tests passing
├── test_job_matcher.py       ✅ 41 tests passing
├── test_profile_builder.py   🔲 Next
├── test_gap_analyser.py      🔲 Planned
└── test_resume_tailor.py     🔲 Planned
```

Tests never make real API calls — all external dependencies are mocked.
Boundary conditions are explicitly tested for all scored/labelled outputs.

---

## 11. Deployment

Deployed on **Streamlit Community Cloud** (free tier). Pushes to `main` trigger automatic redeployment. Secrets configured via Streamlit Cloud dashboard.

**Live URL:** *(to be added on deployment)*

---

## 12. Future Enhancements

- **Application tracker** — log applications with status and notes
- **Cover letter generator** — tailored cover letters alongside CV
- **Scheduled search** — surface new matches automatically
- **Spanish language filter** — optionally filter non-English Barcelona listings
- **Salary benchmarking** — surface salary data alongside match score
- **Fuzzy skill matching** — `rapidfuzz` for sophisticated normalisation beyond lowercase/strip
- **Profile versioning** — track how the candidate profile evolves over time
