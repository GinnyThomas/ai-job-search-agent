import re
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Model constants
# Haiku for bulk matching — fast and cheap.
# Sonnet for detailed single-role analysis
# where quality matters more than speed.
# ─────────────────────────────────────────────
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20250929"

# ─────────────────────────────────────────────
# Scoring thresholds
# Named constants so thresholds are defined
# once and tests reference the same values.
# Change here and everything updates.
# ─────────────────────────────────────────────
STRONG_THRESHOLD = 70     # 70–100 → "Strong"
POTENTIAL_THRESHOLD = 40  # 40–69 → "Potential"
                          #  0–39 → "Weak"


def _get_match_label(score: int) -> str:
    """
    Convert a numeric score to a human-readable label.

    This is the single place where thresholds are applied.
    match_label is ALWAYS derived here — never returned by Claude directly.
    That way score and label can never be inconsistent.
    """
    if score >= STRONG_THRESHOLD:
        return "Strong"
    elif score >= POTENTIAL_THRESHOLD:
        return "Potential"
    else:
        return "Weak"


def normalise_skill(skill: str) -> str:
    """
    Normalise a skill string for consistent comparison and display.

    Lowercase + strip handles:
      - "Python" vs "python"
      - "  AWS  " vs "AWS"
      - "JavaScript" vs "javascript"

    We deliberately do NOT remove internal spaces or special characters.
    "machine learning" and "C++" and "Node.js" should stay intact.
    Fuzzy matching for cases like "Java Script" vs "JavaScript"
    is noted as a future enhancement in DESIGN.md.
    """
    return skill.lower().strip()


def _safe_default_result() -> dict:
    """
    Return a safe, valid result dict when something goes wrong.

    Used when Claude's API fails or returns something we cannot parse.
    Returns a Weak match so the job appears at the bottom of results
    rather than disappearing entirely — the user can still see the listing.
    """
    return {
        "match_score": 0,
        "match_label": "Weak",
        "summary": "Unable to determine match — please try again.",
        "matching_skills": [],
        "missing_skills": [],
        "reasoning": "",
        "highlight_background": ""
    }


def _extract_json_from_text(text: str) -> str:
    """
    Extract a JSON object from text that may contain surrounding content.

    Claude sometimes wraps its JSON in markdown code blocks or adds
    an introductory sentence. This function handles both cases:

      Case 1: ```json { ... } ```
      Case 2: Here is my analysis: { ... }
      Case 3: Plain JSON with no wrapping (the happy path)
    """
    # Try markdown code block with json tag first
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)

    # Try any markdown code block
    match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)

    # Fall back to finding the outermost { ... } in the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)

    # Return the original text and let json.loads handle the failure
    return text


def _parse_match_response(response_text: str) -> dict:
    """
    Parse and validate Claude's response into our match schema.

    This is the most defensively written function in the codebase.
    Every assumption about Claude's output is validated here:
      - Score may be a float, a string, or out of range
      - Keys may be missing
      - JSON may be wrapped in text
      - Response may be empty or completely malformed

    The goal: no matter what Claude returns, we return a valid dict.
    """
    # Handle empty or whitespace-only response
    if not response_text or not response_text.strip():
        return _safe_default_result()

    try:
        # Extract JSON from potentially wrapped text
        json_text = _extract_json_from_text(response_text)
        data = json.loads(json_text)

        # --- Score validation ---
        raw_score = data.get("match_score", 0)

        # Claude occasionally returns "75" as a string or 75.5 as a float
        if isinstance(raw_score, str):
            raw_score = float(raw_score)
        score = int(raw_score)

        # Clamp to valid range — Claude should never go outside 0–100
        # but we enforce it defensively
        score = max(0, min(100, score))

        # --- Label derivation ---
        # We NEVER use a label Claude may have returned.
        # We always compute it from the score ourselves.
        label = _get_match_label(score)

        # --- Skills — normalise for consistent comparison ---
        # Guard the container type first: if Claude returns a string instead
        # of a list (e.g. "Python, AWS"), iterating it character-by-character
        # would produce garbage. We default to [] for any non-list value.
        raw_matching = data.get("matching_skills", [])
        matching_skills = [
            normalise_skill(s)
            for s in (raw_matching if isinstance(raw_matching, list) else [])
            if isinstance(s, str)
        ]
        raw_missing = data.get("missing_skills", [])
        missing_skills = [
            normalise_skill(s)
            for s in (raw_missing if isinstance(raw_missing, list) else [])
            if isinstance(s, str)
        ]

        return {
            "match_score": score,
            "match_label": label,
            "summary": data.get("summary", ""),
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "reasoning": data.get("reasoning", ""),
            "highlight_background": data.get("highlight_background", "")
        }

    except (json.JSONDecodeError, ValueError, TypeError):
        # Claude returned something we cannot parse — return safe default
        return _safe_default_result()


def _format_profile_for_prompt(profile: dict) -> str:
    """
    Format the candidate profile as readable text for the Claude prompt.

    This is what Claude actually reads when evaluating fit.
    We include everything — skills from all eras, domain knowledge,
    achievements — so the matcher has the full picture.
    """
    if not profile:
        return "No profile available."

    parts = []

    if profile.get("full_name"):
        parts.append(f"Name: {profile['full_name']}")

    if profile.get("current_role"):
        parts.append(f"Current Role: {profile['current_role']}")

    # Flatten all technical skills into one readable list
    tech_skills = profile.get("technical_skills", {})
    if tech_skills:
        all_skills = []
        for skills in tech_skills.values():
            if isinstance(skills, list):
                all_skills.extend(skills)
        if all_skills:
            parts.append(f"Technical Skills: {', '.join(all_skills)}")

    domain = profile.get("domain_knowledge", [])
    if domain:
        parts.append(f"Domain Knowledge: {', '.join(domain)}")

    soft = profile.get("soft_skills", [])
    if soft:
        parts.append(f"Soft Skills: {', '.join(soft)}")

    experience = profile.get("experience", [])
    if experience:
        exp_lines = []
        for exp in experience:
            role = exp.get("role", "")
            company = exp.get("company", "")
            dates = exp.get("dates", "")
            achievements = exp.get("achievements", [])
            exp_lines.append(f"  - {role} at {company} ({dates})")
            for achievement in achievements:
                exp_lines.append(f"    • {achievement}")
        parts.append("Experience:\n" + "\n".join(exp_lines))

    education = profile.get("education", [])
    if education:
        parts.append(f"Education: {', '.join(education)}")

    certifications = profile.get("certifications", [])
    if certifications:
        parts.append(f"Certifications: {', '.join(certifications)}")

    achievements = profile.get("notable_achievements", [])
    if achievements:
        parts.append(f"Notable Achievements: {', '.join(achievements)}")

    return "\n".join(parts)


def match_job_to_profile(profile: dict, job: dict) -> dict:
    """
    The main public function. Score a job listing against the candidate profile.

    Calls Claude with a structured prompt defining the scoring criteria,
    then parses and validates the response.

    The prompt is the scoring logic — it defines what matters and how much.
    Claude reasons through each criterion and returns a score.
    We validate the score, derive the label, and normalise the skills.

    Args:
        profile: The candidate's full profile from data/profile.json
        job:     A job listing dict as returned by job_fetcher

    Returns:
        A match result dict conforming to the schema in DESIGN.md
    """
    try:
        client = anthropic.Anthropic()

        formatted_profile = _format_profile_for_prompt(profile)
        job_title = job.get("title", "")
        job_company = job.get("company", "")
        job_description = job.get("description", "")

        prompt = f"""You are evaluating a candidate's fit for a job role.

CANDIDATE PROFILE:
{formatted_profile}

JOB TO EVALUATE:
Title: {job_title}
Company: {job_company}
Description: {job_description}

Score the candidate's fit from 0 to 100 based on these weighted criteria:

1. Technical skills overlap (40%) — how many required skills does the candidate have?
   Consider ALL skills in their profile history, not just their most recent role.

2. Domain knowledge relevance (25%) — does their background fit this industry or problem space?
   Consider previous careers and non-obvious transferable knowledge.

3. Seniority and experience fit (20%) — does their level of experience match what the role requires?

4. Non-obvious strengths (15%) — any transferable skills, previous career experience,
   or achievements that add unexpected value for this specific role?

Return ONLY a JSON object with this exact structure, no other text:
{{
    "match_score": <integer 0-100>,
    "summary": "<one sentence summary of overall fit>",
    "matching_skills": ["<skill1>", "<skill2>"],
    "missing_skills": ["<skill1>", "<skill2>"],
    "reasoning": "<detailed reasoning explaining the score>",
    "highlight_background": "<any non-obvious relevant background, or empty string if none>"
}}"""

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        return _parse_match_response(response.content[0].text)

    except Exception as e:
        print(f"Job matching failed for '{job.get('title', 'unknown')}': {e}")
        return _safe_default_result()
