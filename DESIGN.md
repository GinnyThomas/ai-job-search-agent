# AI Job Search Agent — Design Document

**Author:** Ginny Thomas
**Status:** In Progress
**Last Updated:** March 2026 (current)

---

## 1. Problem Statement

Job hunting is inefficient in three specific ways this tool is designed to fix:

**The hallucination problem.** AI assistants like ChatGPT and custom GPTs cannot access live job boards. When asked about current openings, they fabricate results. Every listing they return is potentially fictional. This tool solves that by connecting directly to real job board APIs and scrapers, ensuring every result is a live posting.

**The incomplete profile problem.** A CV is a marketing document — curated for a specific context, deliberately selective, and quickly out of date. Matching jobs against a single CV means the tool only knows one version of the candidate at one point in time. This tool builds a rich candidate profile from multiple sources — CVs across time, year-end reviews, and self-reflections — so the matcher has access to the full picture.

**The ATS problem.** Most large companies filter applications through Applicant Tracking Systems before a human reads them. These systems do keyword matching — if your CV doesn't contain the right terms from the job description, you're filtered out regardless of your actual fit. This tool generates tailored, ATS-optimised resume versions assembled from the full candidate profile for each role you decide to apply for.

---

## 2. Goals

- Build a rich candidate profile from multiple source documents, including skill proficiency and recency
- Allow the candidate to view and verify their profile, with inline proficiency editing
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
┌────────────────────────────────────────────────────────────────────────┐
│                          app.py (Streamlit UI)                         │
│   Tab 1: My Profile  |  Tab 2: Search Jobs  |  Tab 3: Am I a Fit?     │
└───────────┬────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────┐
│  profile_builder.py │  Reads source documents, extracts enriched
│                     │  profile with proficiency + recency metadata.
│                     │  format_profile_for_display() prepares it for UI.
└─────────┬───────────┘
          │  data/profile.json (single source of truth)
          │
    ┌─────┴──────────────────────┐
    │                            │
    ▼                            ▼
┌─────────────────────┐   ┌─────────────────────┐
│   job_fetcher.py    │   │   job_matcher.py    │
└─────────┬───────────┘   └─────────┬───────────┘
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────┐
          │  gap_analyser.py    │  Two-call architecture: analysis first,
          └──────────┬──────────┘  then tailoring from a clear brief.
                     │
                     ▼
          ┌──────────────────────┐    ┌──────────────────────┐
          │  resume_tailor.py    │───▶│  cv_renderer.py      │
          └──────────────────────┘    │  (.docx generation)  │
                                      └──────────────────────┘

┌─────────────────────┐
│  saved_jobs.py      │  Atomic JSON persistence for bookmarked jobs.
└─────────────────────┘
```

### Two-Call Architecture

Gap analysis and resume tailoring are deliberately split into two API calls:

1. **`analyse_gaps(profile, job)`** — Runs first. Produces a structured brief: alignment points, genuine gaps, transferable strengths, quick wins, honest assessment, recommended framing.
2. **`tailor_resume(profile, job, gap_analysis)`** — Consumes the brief. Writes the CV from clear direction rather than doing analysis and writing simultaneously.

This improves tailoring quality and makes the gap brief independently useful in the UI — the candidate can read and act on the analysis before deciding whether to apply.

---

## 5. Components

### 5.1 `agents/profile_builder.py`

**Responsibility:** Read all candidate source documents, extract a structured master profile with enriched skill metadata, and provide a display-ready format for the UI.

**Status:** ✅ Implemented (tests written)

**Supported file formats:** PDF, DOCX, plain text (.txt)

**Required libraries:** `pdfplumber`, `python-docx`

---

#### Enriched Skill Schema

Skills are stored as objects, not flat strings. A bootcamp skill from 4 years ago scores differently from a production skill used last month:

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

---

#### Enriched Domain Knowledge Schema

```python
{
    "domain": "healthcare / clinical systems",
    "depth": "Expert",
    "years": 10,
    "context": "Registered Nurse Practitioner — clinical assessment, patient care",
    "is_current": False
}
```

---

#### Full Profile Schema

```python
{
    "full_name": str,
    "current_role": str,
    "technical_skills": [enriched skill objects],
    "domain_knowledge": [enriched domain objects],
    "soft_skills": list,           # Flat list — e.g. ["public speaking", "team leadership"]
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
    "source_documents": list
}
```

---

#### Internal Functions

```
_extract_text_from_pdf(path)          → str
_extract_text_from_docx(path)         → str
_extract_text_from_file(path)         → str   (dispatches by extension)
_extract_profile_from_text(text)      → dict  (calls Claude)
_merge_profiles(profiles)             → dict  (combines, deduplicates)
format_profile_for_display(profile)   → dict  (prepares for Streamlit UI)
build_profile(source_dir)             → dict  (main orchestrator)
save_profile(profile, output_path)    → None
load_profile(path)                    → dict
```

---

#### `format_profile_for_display(profile)` — Display Function

Transforms `profile.json` into a structure optimised for the Streamlit UI.
Splits technical skills into current and historical for clarity.
Every field returns an empty list rather than None — the UI never needs to guard against None.

**Returns:**
```python
{
    "full_name": str,
    "current_role": str,
    "current_skills": list,      # technical_skills where is_current == True, sorted by proficiency
    "historical_skills": list,   # technical_skills where is_current == False
    "domain_knowledge": list,
    "soft_skills": list,
    "notable_achievements": list,
    "source_documents": list
}
```

---

#### Merge Strategy

- **Skills:** deduplicated by normalised name. When the same skill appears in multiple documents, the highest proficiency wins. The most recent `last_used` date wins.
- **Domain knowledge:** deduplicated by domain name.
- **Soft skills:** deduplicated, case-insensitive.
- **Scalar fields** (name, current_role): last document wins — pass documents in chronological order (oldest first).
- **List fields** (experience, education, certifications, achievements): all documents contribute; entries are concatenated in a deterministic order, and no automatic deduplication is currently performed.

---

### 5.2 `agents/job_fetcher.py`

**Status:** ✅ Built and tested (38 tests passing)

**Markets supported:**
| Market | Sources | Adzuna Endpoint |
|---|---|---|
| Barcelona / Spain | LinkedIn, Indeed, Glassdoor, Adzuna | `es` |
| Remote UK | LinkedIn, Indeed, Glassdoor, Adzuna | `gb` |
| Remote US | LinkedIn, Indeed, Glassdoor, Adzuna | `us` |

Market configuration is data-driven — adding a new market requires only a new entry in `MARKET_CONFIG`. Nothing else in the code changes.

`fetch_job_from_url(url)` scrapes individual job postings by URL for use in the "Am I a good fit?" tab.

---

### 5.3 `agents/job_matcher.py`

**Status:** ✅ Built and tested (50 tests passing)

**Scoring thresholds:**
```python
STRONG_THRESHOLD = 70     # 70–100 → "Strong"
POTENTIAL_THRESHOLD = 40  # 40–69 → "Potential"
                          #  0–39 → "Weak"
```

**Enriched skill context passed to Claude:**
```
Technical Skills:
  - python: Proficient — production engineering at HMRC until 2025 (current)
  - ruby: Basic — coding bootcamp only, 2022 (not current)
  - aws: Proficient — certified, current
```

---

### 5.4 `agents/gap_analyser.py`

**Status:** ✅ Implemented (28 tests passing)

**Schema returned:**
```python
{
    "top_alignment_points":    list[str],  # Specific skill/experience matches
    "genuine_gaps":            list[str],  # Skills the job needs that are missing
    "transferable_strengths":  list[str],  # Non-obvious value from background
    "quick_wins":              list[str],  # Actionable steps (with time estimates)
    "honest_assessment":       str,        # 2-3 sentence realistic evaluation
    "recommended_framing":     str,        # Positioning angle for the CV writer
}
```

**Defensive design:**
- `_coerce_list_of_strings(value)` — converts non-list responses (plain string, None, dict) to `[]` instead of silently iterating characters
- `_coerce_string(value)` — converts None → `""`, non-string → `str()`
- `_parse_gap_response()` guards against: empty response, markdown-wrapped JSON, JSON arrays (not dicts), null fields, wrong field types, malformed JSON
- Pre-checks job description before API call — distinguishes "no description" from "API error"
- On exception, attaches `_error` field to return dict so UI can show the actual error string

---

### 5.5 `agents/resume_tailor.py`

**Status:** ✅ Implemented (11 tests passing)

Takes the candidate profile, job, and gap analysis brief (from `analyse_gaps`), and generates a tailored ATS-optimised resume as structured text. The gap brief provides the writing direction so Claude doesn't have to do analysis and writing simultaneously.

`_format_gap_analysis_for_prompt()` type-checks all fields before joining (guards against wrong types from Claude's output).

---

### 5.6 `agents/saved_jobs.py`

**Status:** ✅ Implemented (14 tests passing)

JSON persistence layer for bookmarked jobs. Key properties:
- Jobs are identified by `title + company` — saving the same job twice updates rather than duplicates
- Writes are atomic using `tempfile + os.replace` — a crash mid-write cannot corrupt the file
- `load_saved_jobs()`, `save_job()`, `remove_saved_job()` with explicit path parameter for easy testing with `tmp_path`

---

### 5.7 `agents/cv_renderer.py`

**Status:** ✅ Implemented

Takes tailored resume text from `resume_tailor.py` and renders a formatted `.docx` file for download. Used in the "Tailor My CV" flow in Tab 2 and Tab 3.

---

### 5.8 `app.py` (Streamlit Frontend)

**Status:** ✅ Implemented

**UI structure — three tabs:**

```
┌──────────────────────────────────────────────────────────┐
│  TABS: [👤 My Profile] [🔍 Search Jobs] [🎯 Am I a fit?] │
└──────────────────────────────────────────────────────────┘
```

---

#### Tab 1 — My Profile

Displays the full candidate profile for verification. The candidate can confirm that Claude correctly extracted skills, proficiency levels, and domain knowledge before running any job searches.

```
👤 My Profile
Built from: cv_2025.pdf, cv_2022.pdf, yearend_2024.pdf
─────────────────────────────────────────────────────

Current Technical Skills
┌──────────────┬────────────┬───────────┬──────────────────────────────┐
│ Skill        │ Proficiency│ Last Used │ Context                      │
├──────────────┼────────────┼───────────┼──────────────────────────────┤
│ python       │ Proficient │ 2025      │ Production engineering, HMRC │
│ aws          │ Proficient │ 2025      │ Certified, cloud infra       │
│ scala        │ Proficient │ 2025      │ Production, HMRC             │
└──────────────┴────────────┴───────────┴──────────────────────────────┘

Historical Skills (may be rusty)
┌──────────────┬────────────┬───────────┬──────────────────────────────┐
│ ruby         │ Basic      │ 2022      │ Coding bootcamp only         │
└──────────────┴────────────┴───────────┴──────────────────────────────┘

Domain Knowledge
• healthcare / clinical systems — Expert (10 years) — Nurse Practitioner
• fintech / tax systems — Proficient — HMRC engineering

Soft Skills
• public speaking  • team leadership  • stakeholder communication

Notable Achievements
• 95% reduction in production alerts at HMRC
• Conference speaker

─────────────────────────────────────────────────────
[+ Add Documents]    [🔄 Rebuild Profile]
```

**Inline proficiency editing (Option C):**
Each skill row has a selectbox for proficiency — `Expert | Proficient | Familiar | Basic`. Changes are saved directly to `profile.json`. This covers the most likely correction: Claude occasionally over- or under-estimates proficiency from limited document context.

**Deep edits (Option B fallback):**
For adding skills Claude missed or removing incorrect entries, a note directs the user to edit `data/profile.json` directly in their editor. IntelliJ handles JSON natively.

---

#### Tab 2 — Search Jobs

```
Sidebar: job title | market | results count | search button

Results table: ranked by match score
  columns: title | company | location | score | label | date | link

Job detail panel (on row click):
  - Match reasoning (score, label, skills matched / missing)
  - [💾 Save Job]
  - [Analyse Gaps] → shows full gap analysis panel
  - [Tailor My CV] → calls resume_tailor → .docx download
```

The "Analyse Gaps" button uses a **preserve-and-warn** pattern: if a new API call fails, the previously computed result is cleared and a warning shown (rather than silently showing stale results).

---

#### Tab 3 — Am I a Good Fit?

Designed for jobs found outside the search tab — via LinkedIn, a recruiter email, or any URL.

```
[Job URL input]  OR  [Paste job description directly]

[🔍 Analyse Fit] button:
  → match_job_to_profile (score + reasoning)
  → analyse_gaps (full brief, auto-runs on fit analysis)
  → displays: score, gaps, alignment points, quick wins

[Analyse Gaps] — re-run gap analysis manually
[Tailor My CV] — generate tailored .docx

Saved Jobs list:
  Each saved job shows its gap analysis (if available)
  with [Analyse Gaps] and [Tailor My CV] per job
```

**Tab 3 vs Tab 2 preserve-and-warn difference:** On Tab 3's main fit result panel, a failed gap re-run *preserves* the auto-run result (which was good) rather than clearing it. On Tab 2 and saved jobs, a failed re-run *clears* the stale result and shows a warning (since the button is the only source — no auto-run to fall back to).

---

## 6. Data Flow

```
User uploads source documents (PDF, DOCX, TXT)
        ↓
profile_builder.py → data/profile.json  (max_tokens=4096 to handle rich career histories)
        ↓
User reviews profile in Tab 1 → adjusts proficiency if needed
  (selectbox selection persisted to data/settings.json)
        ↓
Tab 2: User searches → job_fetcher → job_matcher → ranked results table
        ↓
User selects job → analyse_gaps → structured brief shown in UI
        ↓
User clicks "Tailor My CV" → tailor_resume (uses gap brief) → cv_renderer → .docx download

Tab 3 (parallel path — for jobs found externally):
  URL or paste → fetch_job_from_url / direct text
        ↓
  match_job_to_profile + analyse_gaps (auto-runs together)
        ↓
  "Tailor My CV" → .docx download
  "💾 Save Job" → data/saved_jobs.json
```

---

## 7. Data Folder Structure

```
data/
├── source_documents/     # gitignored — personal documents stay local
│   ├── cv_2025.pdf
│   ├── cv_2022.pdf
│   └── yearend_2024.pdf
├── profile.json          # Generated — do not edit manually (use Tab 1 for proficiency)
├── saved_jobs.json       # gitignored — bookmarked jobs with gap analysis results
├── settings.json         # gitignored — persisted preferences (e.g. selected base CV)
└── .gitkeep
```

**Note on Streamlit Cloud:** `data/` uses an ephemeral filesystem on Streamlit Community Cloud. `profile.json`, `saved_jobs.json`, and `settings.json` are lost on app restart. Users must rebuild their profile each session when using the hosted version.

---

## 8. External Integrations

| Service | Purpose | Auth | Free Tier |
|---|---|---|---|
| Anthropic Claude API | Profile building, matching, gap analysis, resume tailoring | API key | Pay per token |
| JobSpy | LinkedIn, Indeed, Glassdoor scraping | None | Yes |
| Adzuna API | Additional listings, EU/UK/US coverage | App ID + API key | Yes |

**Model strategy:** Haiku for bulk matching. Sonnet for profile building, detailed analysis, resume tailoring.

---

## 9. Configuration and Secrets

```
ANTHROPIC_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_API_KEY=...
```

Both `.env` and `data/source_documents/` are excluded from version control.

---

## 10. Testing Strategy

**Framework:** `pytest`
**Approach:** TDD — tests written before implementation throughout. Real API calls are never made in tests; `anthropic.Anthropic` is mocked.

```
tests/
├── test_profile_builder.py   ✅ 57 tests passing
├── test_job_fetcher.py       ✅ 38 tests passing
├── test_job_matcher.py       ✅ 50 tests passing
├── test_gap_analyser.py      ✅ 28 tests passing
├── test_resume_tailor.py     ✅ 11 tests passing
└── test_saved_jobs.py        ✅ 14 tests passing

Total: 198 tests
```

**Test patterns used:**
- Fixtures for sample profiles, jobs, and valid API responses
- `@patch("agents.X.anthropic.Anthropic")` to mock all Claude API calls
- Defensive parsing tests: empty response, markdown-wrapped JSON, null fields, wrong types, JSON arrays
- Atomic write tests using `pytest`'s `tmp_path` fixture
- NaN guard tests (pandas fills missing fields with float NaN, not empty string)

---

## 11. Deployment

Deployed on **Streamlit Community Cloud** (free tier). Pushes to `main` auto-redeploy.
Secrets configured via Streamlit Cloud dashboard — never stored in the repository.

**Live URL:** Deployed on Streamlit Community Cloud — accessible from any browser.

---

## 12. Future Enhancements

- **Custom location / remote toggle** — flexible location input beyond the three preset markets, with a separate "remote only" toggle
- **Application tracker** — log applications with status and notes
- **Cover letter generator** — tailored cover letters alongside CV
- **Scheduled search** — surface new matches automatically
- **Spanish language filter** — optionally filter non-English Barcelona listings
- **Salary benchmarking** — surface salary data alongside match score
- **Fuzzy skill matching** — `rapidfuzz` for normalisation beyond lowercase/strip
- **Profile versioning** — track how the candidate profile evolves over time
- **Full profile editor** — add/remove skills directly in the UI (beyond proficiency-only editing)
- **Persistent storage on Streamlit Cloud** — save profile and saved jobs across sessions
