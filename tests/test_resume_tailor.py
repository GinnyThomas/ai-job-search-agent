"""
Tests for agents/resume_tailor.py

Same patterns as test_job_matcher.py:
  - Private functions are tested directly (they're pure functions — input in, output out)
  - Claude API calls are mocked — we test our logic, not Anthropic's servers
  - Every test has a docstring explaining WHY we care about this behaviour
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from agents.resume_tailor import (
    _safe_default_tailored,
    _parse_tailor_response,
    tailor_resume,
)


class TestSafeDefaultTailored:

    def test_returns_all_required_keys(self):
        """
        The safe default must have every key the rest of the app expects.
        If a key is missing, app.py will KeyError when trying to render
        the tailored output — even in the failure case.
        """
        result = _safe_default_tailored()
        assert "summary" in result
        assert "highlighted_skills" in result
        assert "experience" in result
        assert "personal_projects" in result
        assert "cover_note" in result

    def test_all_values_are_safe_empty_types(self):
        """
        Lists must be lists, strings must be strings — never None.
        app.py will iterate over highlighted_skills and experience,
        so None would raise a TypeError.
        """
        result = _safe_default_tailored()
        assert isinstance(result["summary"], str)
        assert isinstance(result["highlighted_skills"], list)
        assert isinstance(result["experience"], list)
        assert isinstance(result["personal_projects"], list)
        assert isinstance(result["cover_note"], str)

class TestParseTailorResponse:

    def test_parses_valid_json_response(self):
        """
        Happy path: Claude returns clean JSON with all expected fields.
        We verify the values flow through correctly.
        """
        response = json.dumps({
            "summary": "Strong fit for this backend role.",
            "highlighted_skills": ["Python", "FastAPI"],
            "experience": [
                {
                    "role": "Java Developer",
                    "company": "Capgemini",
                    "dates": "2022 - present",
                    "bullets": ["Built REST APIs", "Led migration"]
                }
            ],
            "personal_projects": [
                {
                    "name": "AI Job Search Agent",
                    "bullets": ["Demonstrates Python and API skills"]
                }
            ],
            "cover_note": "Highlight nursing background for healthtech roles."
        })
        result = _parse_tailor_response(response)
        assert result["summary"] == "Strong fit for this backend role."
        assert result["highlighted_skills"] == ["Python", "FastAPI"]
        assert len(result["experience"]) == 1
        assert result["experience"][0]["role"] == "Java Developer"
        assert len(result["experience"][0]["bullets"]) == 2
        assert len(result["personal_projects"]) == 1
        assert result["cover_note"] == "Highlight nursing background for healthtech roles."

    def test_returns_safe_default_on_empty_response(self):
        """
        Claude occasionally returns an empty string (timeout, refusal).
        We must not raise an exception — return the safe default instead.
        """
        result = _parse_tailor_response("")
        assert result == _safe_default_tailored()

    def test_returns_safe_default_on_malformed_json(self):
        """
        If Claude returns something that isn't valid JSON, we catch it
        and return the safe default rather than crashing the app.
        """
        result = _parse_tailor_response("here is your tailored CV: {broken json{{")
        assert result == _safe_default_tailored()

    def test_handles_json_wrapped_in_markdown_code_block(self):
            """
            Claude often wraps JSON in ```json ... ``` markdown blocks.
            We must strip the wrapping and parse the inner JSON.
            """
            response = '```json\n{"summary": "Great fit.", "highlighted_skills": [], "experience": [], "personal_projects": [], "cover_note": ""}\n```'
            result = _parse_tailor_response(response)
            assert result["summary"] == "Great fit."

    def test_missing_keys_fall_back_to_safe_empty_values(self):
        """
        Claude may omit optional keys if it has nothing to say.
        Missing keys should default to safe empty types, not raise KeyError.
        """
        response = json.dumps({"summary": "Good fit."})
        result = _parse_tailor_response(response)
        assert result["summary"] == "Good fit."
        assert result["highlighted_skills"] == []
        assert result["experience"] == []
        assert result["personal_projects"] == []
        assert result["cover_note"] == ""
        