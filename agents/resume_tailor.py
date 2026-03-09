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


def _parse_tailor_response(response_text: str) -> dict:
    pass


def tailor_resume(profile: dict, job: dict, base_cv_text: str) -> dict:
    pass