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
    pass