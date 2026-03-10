import re
import json
import anthropic
import pdfplumber
from pathlib import Path
from docx import Document
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Model constants
# Sonnet for profile building — quality matters
# more than speed here. This runs once, not in bulk.
# ─────────────────────────────────────────────
SONNET_MODEL = "claude-sonnet-4-5-20250929"

# ─────────────────────────────────────────────
# Proficiency constants
# Named here so tests, prompts, and merging logic
# all reference the same definitions.
# ─────────────────────────────────────────────
PROFICIENCY_LEVELS = ["Expert", "Proficient", "Familiar", "Basic"]

PROFICIENCY_ORDER = {
    "Expert": 4,
    "Proficient": 3,
    "Familiar": 2,
    "Basic": 1
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


# ─────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────

def normalise_skill(skill: str) -> str:
    """
    Normalise a skill name for consistent comparison and storage.
    Lowercase + strip handles case variations and accidental whitespace.
    We do not remove internal spaces or special characters —
    'machine learning', 'C++', and 'Node.js' should stay intact.
    """
    return skill.lower().strip()


def _safe_empty_profile() -> dict:
    """
    A valid, empty profile with all required keys.
    Returned whenever extraction or merging fails.
    Every field is an empty list/string — never None.
    """
    return {
        "full_name": "",
        "current_role": "",
        "technical_skills": [],
        "domain_knowledge": [],
        "soft_skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "notable_achievements": [],
        "source_documents": []
    }


def _extract_json_from_text(text: str) -> str:
    """
    Extract a JSON object from text that may contain surrounding content.
    Claude sometimes wraps JSON in markdown code blocks or preambles.
    """
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)

    match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)

    return text


# ─────────────────────────────────────────────
# Text extraction functions
# ─────────────────────────────────────────────

def _extract_text_from_pdf(path: str) -> str:
    """
    Extract all text from a PDF file using pdfplumber.
    Handles pages that return None (scanned images without OCR).
    """
    try:
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF extraction failed for {path}: {e}")
        return ""


def _extract_text_from_docx(path: str) -> str:
    """
    Extract all paragraph text from a DOCX file using python-docx.
    Skips empty paragraphs (common in Word docs used for spacing).
    """
    try:
        doc = Document(path)
        text = "\n".join(
            para.text for para in doc.paragraphs
            if para.text.strip()
        )
        return text.strip()
    except Exception as e:
        print(f"DOCX extraction failed for {path}: {e}")
        return ""


def _extract_text_from_txt(path: str) -> str:
    """Extract text from a plain text file."""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"Text file extraction failed for {path}: {e}")
        return ""


def _extract_text_from_file(path: str) -> str:
    """
    Dispatch text extraction to the appropriate function
    based on file extension.

    Returns empty string for unsupported file types
    rather than raising an error — build_profile skips
    files that return empty text.
    """
    ext = Path(path).suffix.lower()

    if ext == ".pdf":
        return _extract_text_from_pdf(path)
    elif ext == ".docx":
        return _extract_text_from_docx(path)
    elif ext == ".txt":
        return _extract_text_from_txt(path)
    else:
        return ""


def extract_text_from_file(path: str) -> str:
    """
    Public wrapper around _extract_text_from_file.

    Used by app.py to extract base CV text for resume tailoring
    without coupling app.py to the private internals of this module.
    """
    return _extract_text_from_file(path)

# ─────────────────────────────────────────────
# Profile extraction
# ─────────────────────────────────────────────

def _parse_profile_response(response_text: str, filename: str) -> dict:
    """
    Parse and validate Claude's profile extraction response.

    Handles all the ways Claude's response can be imperfect:
      - JSON wrapped in markdown
      - Missing fields (default to empty)
      - is_current returned as string "true"/"false"
      - Invalid proficiency values (default to Basic)
      - Skill names not yet normalised
    """
    if not response_text or not response_text.strip():
        result = _safe_empty_profile()
        result["source_documents"] = [filename]
        return result

    try:
        json_text = _extract_json_from_text(response_text)
        data = json.loads(json_text)

        # --- Validate and normalise technical skills ---
        normalised_skills = []
        for skill in data.get("technical_skills", []):
            if not isinstance(skill, dict):
                continue

            name = normalise_skill(skill.get("name", ""))
            if not name:
                continue

            # Clamp proficiency to valid values
            proficiency = skill.get("proficiency", "Basic")
            if proficiency not in PROFICIENCY_LEVELS:
                proficiency = "Basic"

            # Claude sometimes returns "true"/"false" strings
            is_current = skill.get("is_current", False)
            if isinstance(is_current, str):
                is_current = is_current.lower() == "true"
            is_current = bool(is_current)

            normalised_skills.append({
                "name": name,
                "proficiency": proficiency,
                "last_used": str(skill.get("last_used", "")),
                "context": skill.get("context", ""),
                "is_current": is_current
            })

        # --- Ensure filename is recorded as a source document ---
        source_docs = list(data.get("source_documents", []))
        if filename not in source_docs:
            source_docs.insert(0, filename)

        return {
            "full_name": data.get("full_name", ""),
            "current_role": data.get("current_role", ""),
            "technical_skills": normalised_skills,
            "domain_knowledge": data.get("domain_knowledge", []),
            "soft_skills": data.get("soft_skills", []),
            "experience": data.get("experience", []),
            "education": data.get("education", []),
            "certifications": data.get("certifications", []),
            "notable_achievements": data.get("notable_achievements", []),
            "source_documents": source_docs
        }

    except (json.JSONDecodeError, ValueError, TypeError):
        result = _safe_empty_profile()
        result["source_documents"] = [filename]
        return result


def _extract_profile_from_text(text: str, filename: str) -> dict:
    """
    Use Claude to extract a structured candidate profile from document text.

    We use Sonnet here (not Haiku) — profile building happens once
    and quality matters more than speed.

    The prompt is the extraction logic: it defines exactly what to look for,
    how to assess proficiency, and what makes a skill current vs historical.
    """
    # Don't call Claude for empty text — return safe empty profile
    if not text or not text.strip():
        result = _safe_empty_profile()
        result["source_documents"] = [filename]
        return result

    try:
        client = anthropic.Anthropic()

        prompt = f"""Extract a comprehensive candidate profile from the following document.

DOCUMENT ({filename}):
{text}

Return ONLY a JSON object with this exact structure, no other text:
{{
    "full_name": "<candidate's full name, or empty string if not found>",
    "current_role": "<most recent job title, or empty string>",
    "technical_skills": [
        {{
            "name": "<skill name, lowercase>",
            "proficiency": "<Expert|Proficient|Familiar|Basic>",
            "last_used": "<year as string e.g. '2025', or empty string>",
            "context": "<brief description of where/how this skill was used>",
            "is_current": <true if used in most recent role or within last year, false otherwise>
        }}
    ],
    "domain_knowledge": [
        {{
            "domain": "<domain or industry name>",
            "depth": "<Expert|Proficient|Familiar>",
            "years": <integer number of years, or 0 if unknown>,
            "context": "<brief description of this domain experience>",
            "is_current": <true if currently working in this domain>
        }}
    ],
    "soft_skills": ["<skill1>", "<skill2>"],
    "experience": [
        {{
            "role": "<job title>",
            "company": "<company name>",
            "dates": "<date range e.g. '2022–2025'>",
            "achievements": ["<specific achievement, quantified where possible>"]
        }}
    ],
    "education": ["<degree or qualification name>"],
    "certifications": ["<certification name>"],
    "notable_achievements": ["<quantified achievement e.g. '95% reduction in production alerts'>"],
    "source_documents": []
}}

Proficiency guidelines:
  Expert     — Deep mastery, long-term use, could teach this skill
  Proficient — Solid production experience, used regularly in real work
  Familiar   — Used meaningfully but not as a primary skill
  Basic      — Introductory level only, e.g. bootcamp or short course

is_current guidelines:
  true  — Used in the most recent role, or within the last 12 months
  false — Last used in a previous role, bootcamp, or over a year ago

Important:
  - Skill names must be lowercase
  - notable_achievements should be quantified where possible
  - source_documents should always be an empty list (the system populates this)
  - Capture ALL skills mentioned, including historical ones from earlier roles
  - For someone who was a nurse before becoming a software engineer,
    capture their healthcare domain knowledge under domain_knowledge"""

        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        return _parse_profile_response(response.content[0].text, filename)

    except Exception as e:
        print(f"Profile extraction failed for '{filename}': {e}")
        result = _safe_empty_profile()
        result["source_documents"] = [filename]
        return result


# ─────────────────────────────────────────────
# Profile merging
# ─────────────────────────────────────────────

def _merge_profiles(profiles: list) -> dict:
    """
    Merge profiles from multiple source documents into one.

    Strategy:
      - Skills:         deduplicate by name, keep highest proficiency
                        and most recent last_used date
      - Domain:         deduplicate by domain name
      - Soft skills:    deduplicate case-insensitively
      - Scalar fields:  last non-empty value wins (pass oldest doc first)
      - List fields:    all documents contribute, duplicates removed
      - Source docs:    all filenames combined
    """
    if not profiles:
        return _safe_empty_profile()

    if len(profiles) == 1:
        return profiles[0]

    merged = _safe_empty_profile()

    for profile in profiles:

        # Scalar fields — last non-empty wins
        if profile.get("full_name"):
            merged["full_name"] = profile["full_name"]
        if profile.get("current_role"):
            merged["current_role"] = profile["current_role"]

        # Technical skills — deduplicate by normalised name
        for skill in profile.get("technical_skills", []):
            name = normalise_skill(skill.get("name", ""))
            if not name:
                continue

            existing = next(
                (s for s in merged["technical_skills"] if s["name"] == name),
                None
            )

            if existing is None:
                merged["technical_skills"].append({**skill, "name": name})
            else:
                # Keep higher proficiency
                new_prof = skill.get("proficiency", "Basic")
                existing_prof = existing.get("proficiency", "Basic")
                if PROFICIENCY_ORDER.get(new_prof, 0) > PROFICIENCY_ORDER.get(existing_prof, 0):
                    existing["proficiency"] = new_prof
                    existing["context"] = skill.get("context", existing.get("context", ""))

                # Keep most recent last_used
                new_last_used = str(skill.get("last_used", ""))
                existing_last_used = str(existing.get("last_used", ""))
                if new_last_used > existing_last_used:
                    existing["last_used"] = new_last_used
                    existing["is_current"] = skill.get("is_current", existing.get("is_current", False))

        # Domain knowledge — deduplicate by domain name
        for domain in profile.get("domain_knowledge", []):
            domain_name = domain.get("domain", "").lower().strip()
            if not domain_name:
                continue
            existing = next(
                (d for d in merged["domain_knowledge"]
                 if d.get("domain", "").lower().strip() == domain_name),
                None
            )
            if existing is None:
                merged["domain_knowledge"].append(domain)

        # Soft skills — deduplicate case-insensitively
        existing_soft = {s.lower().strip() for s in merged["soft_skills"]}
        for skill in profile.get("soft_skills", []):
            if skill.lower().strip() not in existing_soft:
                merged["soft_skills"].append(skill)
                existing_soft.add(skill.lower().strip())

        # Experience — all entries kept (no deduplication, all context is valuable)
        merged["experience"].extend(profile.get("experience", []))

        # Education — deduplicate
        existing_edu = {e.lower().strip() for e in merged["education"]}
        for edu in profile.get("education", []):
            if edu.lower().strip() not in existing_edu:
                merged["education"].append(edu)
                existing_edu.add(edu.lower().strip())

        # Certifications — deduplicate
        existing_certs = {c.lower().strip() for c in merged["certifications"]}
        for cert in profile.get("certifications", []):
            if cert.lower().strip() not in existing_certs:
                merged["certifications"].append(cert)
                existing_certs.add(cert.lower().strip())

        # Notable achievements — deduplicate
        existing_ach = {a.lower().strip() for a in merged["notable_achievements"]}
        for ach in profile.get("notable_achievements", []):
            if ach.lower().strip() not in existing_ach:
                merged["notable_achievements"].append(ach)
                existing_ach.add(ach.lower().strip())

        # Source documents — combine all
        for doc in profile.get("source_documents", []):
            if doc not in merged["source_documents"]:
                merged["source_documents"].append(doc)

    return merged


# ─────────────────────────────────────────────
# Display formatting
# ─────────────────────────────────────────────

def format_profile_for_display(profile: dict) -> dict:
    """
    Transform profile.json into a structure optimised for the Streamlit UI.

    Splits technical skills into current and historical so the UI can
    display them in separate, clearly labelled sections.

    Current skills are sorted by proficiency (highest first) so the
    strongest skills appear at the top of the table.

    Every field returns a list or string — never None — so the UI
    never needs to guard against missing values.
    """
    if not profile:
        return {
            "full_name": "",
            "current_role": "",
            "current_skills": [],
            "historical_skills": [],
            "domain_knowledge": [],
            "soft_skills": [],
            "notable_achievements": [],
            "source_documents": []
        }

    technical_skills = profile.get("technical_skills", [])

    current_skills = [s for s in technical_skills if s.get("is_current", False)]
    historical_skills = [s for s in technical_skills if not s.get("is_current", False)]

    # Sort current skills — highest proficiency first
    current_skills.sort(
        key=lambda s: PROFICIENCY_ORDER.get(s.get("proficiency", "Basic"), 0),
        reverse=True
    )

    return {
        "full_name": profile.get("full_name", ""),
        "current_role": profile.get("current_role", ""),
        "current_skills": current_skills,
        "historical_skills": historical_skills,
        "domain_knowledge": profile.get("domain_knowledge", []),
        "soft_skills": profile.get("soft_skills", []),
        "notable_achievements": profile.get("notable_achievements", []),
        "source_documents": profile.get("source_documents", [])
    }


# ─────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────

def build_profile(source_dir: str) -> dict:
    """
    The main public function. Builds a complete candidate profile
    from all supported documents in the source directory.

    Processing order:
      1. List all .pdf, .docx, and .txt files
      2. Extract text from each
      3. Skip files that produce no text (scanned images, empty files)
      4. Extract structured profile from each file's text using Claude
      5. Merge all profiles into one

    Files should be named or ordered so older CVs come before newer ones
    — the merge strategy gives scalar fields (like current_role) to the
    last document, which should be the most recent.
    """
    source_path = Path(source_dir)

    if not source_path.exists() or not source_path.is_dir():
        return _safe_empty_profile()

    profiles = []

    # Sort for deterministic processing order
    for file_path in sorted(source_path.iterdir()):
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        text = _extract_text_from_file(str(file_path))

        # Skip files that produced no text — no point calling Claude
        if not text.strip():
            continue

        profile = _extract_profile_from_text(text, file_path.name)
        profiles.append(profile)

    return _merge_profiles(profiles)


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────

def save_profile(profile: dict, output_path: str) -> None:
    """
    Save the candidate profile to a JSON file.

    Uses indent=2 for human readability — profile.json should be
    legible when opened in an editor for manual inspection or editing.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def load_profile(path: str) -> dict:
    """
    Load a candidate profile from a JSON file.

    Returns an empty dict if the file doesn't exist —
    the caller can treat this as "no profile built yet".
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
