import re
import json
import anthropic
from dotenv import load_dotenv

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
        "summary": "",
        "highlighted_skills": [],
        "experience": [],
        "personal_projects": [],
        "cover_note": ""
    }

def _extract_json_from_text(text: str) -> str:
    """
    Extract a JSON object from text that may contain surrounding content.
    Claude sometimes wraps JSON in markdown code blocks or adds prose before it.
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
            "summary": data.get("summary", ""),
            "highlighted_skills": data.get("highlighted_skills", []),
            "experience": data.get("experience", []),
            "personal_projects": data.get("personal_projects", []),
            "cover_note": data.get("cover_note", "")
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

        current_role = profile.get("current_role", "")
        full_name = profile.get("full_name", "")

        prompt = f"""You are a professional CV writer tailoring a candidate's CV for a specific job.

            CANDIDATE NAME: {full_name}
            CURRENT ROLE: {current_role}

            CANDIDATE'S CURRENT CV:
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
