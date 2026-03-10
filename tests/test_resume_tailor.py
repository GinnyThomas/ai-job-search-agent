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
        assert "contact_info" in result
        assert "education" in result
        assert "certifications" in result

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
        assert isinstance(result["contact_info"], str)
        assert isinstance(result["education"], list)
        assert isinstance(result["certifications"], list)


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
            "cover_note": "Highlight nursing background for healthtech roles.",
            "contact_info": "ginnynjon@gmail.com | linkedin.com/in/ginny",
            "education": ["BSc Nursing, University of X"],
            "certifications": ["AWS Certified Developer"]
        })
        result = _parse_tailor_response(response)
        assert result["summary"] == "Strong fit for this backend role."
        assert result["highlighted_skills"] == ["Python", "FastAPI"]
        assert len(result["experience"]) == 1
        assert result["experience"][0]["role"] == "Java Developer"
        assert len(result["experience"][0]["bullets"]) == 2
        assert len(result["personal_projects"]) == 1
        assert result["cover_note"] == "Highlight nursing background for healthtech roles."
        assert result["contact_info"] == "ginnynjon@gmail.com | linkedin.com/in/ginny"
        assert result["education"] == ["BSc Nursing, University of X"]
        assert result["certifications"] == ["AWS Certified Developer"]

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
        assert result["contact_info"] == ""
        assert result["education"] == []
        assert result["certifications"] == []


class TestTailorResume:

    @pytest.fixture
    def sample_profile(self):
        return {
            "full_name": "Virginia Thomas",
            "current_role": "Java Developer",
            "technical_skills": [
                {"name": "Python", "proficiency": "Proficient", "is_current": True},
                {"name": "Java", "proficiency": "Familiar", "is_current": True},
            ],
            "domain_knowledge": [
                {"domain": "Healthcare", "depth": "Expert"}
            ],
            "soft_skills": ["communication", "problem solving"],
            "experience": [
                {
                    "role": "Java Developer",
                    "company": "Capgemini",
                    "dates": "2022 - present",
                    "achievements": ["Built REST APIs", "Led migration project"]
                }
            ],
            "notable_achievements": ["Career changer from Nurse Practitioner"],
        }

    @pytest.fixture
    def sample_job(self):
        return {
            "title": "Backend Engineer",
            "company": "HealthTech Ltd",
            "description": "Python backend role in digital health. FastAPI, REST APIs required."
        }

    @patch("agents.resume_tailor.anthropic.Anthropic")
    def test_calls_claude_with_profile_job_and_base_cv(
        self, mock_anthropic_class, sample_profile, sample_job
    ):
        """
        The prompt sent to Claude must contain the job title, job description,
        and content from the candidate profile. If any of these are missing,
        the tailoring will be generic rather than targeted.
        """
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"summary": "Good fit.", "highlighted_skills": [], "experience": [], "personal_projects": [], "cover_note": ""}')]
        )

        tailor_resume(sample_profile, sample_job, base_cv_text="My CV content here.")

        assert mock_client.messages.create.called
        call_kwargs = mock_client.messages.create.call_args[1]
        prompt = call_kwargs["messages"][0]["content"]

        assert "Backend Engineer" in prompt
        assert "Python backend role in digital health" in prompt
        assert "My CV content here." in prompt

    @patch("agents.resume_tailor.anthropic.Anthropic")
    def test_returns_parsed_response_on_success(
        self, mock_anthropic_class, sample_profile, sample_job
    ):
        """
        When Claude returns valid JSON, the result must be a fully
        populated dict matching our schema — not the safe default.
        """
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps({
                "summary": "Strong fit for this healthtech role.",
                "highlighted_skills": ["Python", "FastAPI"],
                "experience": [
                    {
                        "role": "Java Developer",
                        "company": "Capgemini",
                        "dates": "2022 - present",
                        "bullets": ["Built REST APIs serving 10k users"]
                    }
                ],
                "personal_projects": [],
                "cover_note": "Nursing background is directly relevant.",
                "contact_info": "ginnynjon@gmail.com | linkedin.com/in/ginny",
                "education": ["BSc Nursing, University of X"],
                "certifications": ["AWS Certified Developer"]
            }))]
        )

        result = tailor_resume(sample_profile, sample_job, base_cv_text="My CV.")

        assert result["summary"] == "Strong fit for this healthtech role."
        assert "python" in [s.lower() for s in result["highlighted_skills"]]
        assert len(result["experience"]) == 1
        assert result["cover_note"] == "Nursing background is directly relevant."

    @patch("agents.resume_tailor.anthropic.Anthropic")
    def test_returns_safe_default_on_api_failure(
        self, mock_anthropic_class, sample_profile, sample_job
    ):
        """
        If the Claude API throws (network error, quota exceeded, etc.)
        we must return the safe default — not crash the app.
        """
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        result = tailor_resume(sample_profile, sample_job, base_cv_text="My CV.")

        assert result == _safe_default_tailored()

    @patch("agents.resume_tailor.anthropic.Anthropic")
    def test_returns_safe_default_when_no_base_cv_text(
        self, mock_anthropic_class, sample_profile, sample_job
    ):
        """
        base_cv_text is required for meaningful tailoring.
        An empty string should return the safe default rather than
        sending a useless prompt to Claude and wasting API credits.
        """
        result = tailor_resume(sample_profile, sample_job, base_cv_text="")

        assert result == _safe_default_tailored()
        assert not mock_anthropic_class.called
