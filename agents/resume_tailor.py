import re
import json
import anthropic
from dotenv import load_dotenv
from agents.job_matcher import _format_profile_for_prompt

load_dotenv()

SONNET_MODEL = "claude-sonnet-4-5-20250929"


def _safe_default_tailored() -> dict:
    """
    Return a safe, valid result dict when something goes wrong.

    Used when Claude's API fails or returns something we cannot parse.
    Every value is a safe empty type — never None — because app.py
    will iterate over lists and render strings without checking first.
    """
    return {
        "contact_info": "",
        "summary": "",
        "highlighted_skills": [],
        "experience": [],
        "personal_projects": [],
        "education": [],
        "certifications": [],
        "cover_note": ""
    }

def _extract_json_from_text(text: str) -> str:
    """
    Extract a JSON object from text that may contain surrounding content.
    Claude sometimes wraps JSON in markdown code blocks or adds prose before it.

    Uses first-'{' to last-'}' extraction within code blocks to correctly
    handle nested JSON objects (non-greedy '?' would stop at first '}').
    """
    for pattern in (r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```'):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1)
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                return candidate[start:end + 1]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


def _parse_tailor_response(response_text: str) -> dict:
    """
    Parse and validate Claude's tailored CV response.

    Defensively handles every failure mode:
      - Empty or whitespace-only response
      - JSON wrapped in markdown code blocks
      - Missing keys (default to safe empty types)
      - Completely malformed response
    """
    if not response_text or not response_text.strip():
        return _safe_default_tailored()

    try:
        json_text = _extract_json_from_text(response_text)
        data = json.loads(json_text)

        return {
            "contact_info": data.get("contact_info") or "",
            "summary": data.get("summary") or "",
            "highlighted_skills": data.get("highlighted_skills") or [],
            "experience": data.get("experience") or [],
            "personal_projects": data.get("personal_projects") or [],
            "education": data.get("education") or [],
            "certifications": data.get("certifications") or [],
            "cover_note": data.get("cover_note") or ""
        }

    except (json.JSONDecodeError, ValueError, TypeError):
        return _safe_default_tailored()


def tailor_resume(profile: dict, job: dict, base_cv_text: str) -> dict:
    """
    The main public function. Tailor a CV to a specific job listing.

    Sends the candidate's existing CV text, structured profile, and job
    description to Claude Sonnet. Claude rewrites the summary, prioritises
    the most relevant skills, and adjusts bullet count per role based on
    relevance to this specific job.

    Args:
        profile:      The candidate's full profile from data/profile.json
        job:          A job listing dict as returned by job_fetcher
        base_cv_text: The raw text extracted from the candidate's current CV.
                      This is the structural foundation — Claude tailors it,
                      not replaces it.

    Returns:
        A tailored content dict conforming to the schema, or safe default
        if Claude fails or base_cv_text is empty.
    """
    if not base_cv_text or not base_cv_text.strip():
        return _safe_default_tailored()

    try:
        client = anthropic.Anthropic()

        job_title = job.get("title", "")
        job_company = job.get("company", "")
        job_description = job.get("description", "")

        full_name = profile.get("full_name", "")
        formatted_profile = _format_profile_for_prompt(profile)

        prompt = f"""You are a professional CV writer tailoring a candidate's CV for a specific job.

            CANDIDATE NAME: {full_name}

            STRUCTURED PROFILE (skills with proficiency levels, domain knowledge, achievements):
            {formatted_profile}

            CANDIDATE'S CURRENT CV (use this as the base for wording and structure):
            {base_cv_text}

            JOB TO TAILOR FOR:
            Title: {job_title}
            Company: {job_company}
            Description: {job_description}

            Rewrite the CV content to best fit this specific role. Rules:
            - Keep all real experience — do not invent roles or skills that aren't in the CV
            - Adjust bullet count per role based on relevance: more bullets for relevant roles, fewer for less relevant ones
            - Lead the summary with what makes this candidate compelling for THIS role specifically
            - If the candidate has an unusual background (e.g. previous career), surface it as a strength where genuinely relevant
            - highlighted_skills should be ordered most-relevant-first for this job

            Return ONLY a JSON object with this exact structure, no other text:
            {{
                "contact_info": "<email | phone | LinkedIn | location — copied exactly from the CV>",
                "summary": "<tailored professional summary paragraph>",
                "highlighted_skills": ["<most relevant skill>", "<second most relevant>"],
                "experience": [
                    {{
                        "role": "<job title>",
                        "company": "<company name>",
                        "dates": "<date range>",
                        "bullets": ["<tailored bullet>", "<tailored bullet>"]
                    }}
                ],
                "personal_projects": [
                    {{
                        "name": "<project name>",
                        "bullets": ["<tailored bullet>"]
                    }}
                ],
                "education": ["<degree or qualification, copied exactly from the CV>"],
                "certifications": ["<certification or course, copied exactly from the CV>"],
                "cover_note": "<2-3 talking points for a cover letter or intro email>"
            }}"""

        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        return _parse_tailor_response(response.content[0].text)

    except Exception as e:
        print(f"Resume tailoring failed for '{job.get('title', 'unknown')}': {e}")
        return _safe_default_tailored()
