"""
Tests for agents/job_matcher.py

Written BEFORE the implementation — this is TDD.
All tests here will fail until job_matcher.py is built.
That is intentional. A failing test is a precise description
of behaviour that doesn't exist yet.

The cycle:
  1. Run tests → all fail (Red)
  2. Write minimum implementation to pass them (Green)
  3. Clean up the code without breaking tests (Refactor)
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from agents.job_matcher import (
    STRONG_THRESHOLD,
    POTENTIAL_THRESHOLD,
    _get_match_label,
    normalise_skill,
    _parse_match_response,
    match_job_to_profile,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def sample_profile():
    """
    A realistic candidate profile — the kind profile_builder.py will produce.
    Note it includes skills not on any single CV: Ruby, nursing domain knowledge.
    This is the point of the profile — it knows more than any one CV.
    """
    return {
        "full_name": "Ginny Thomas",
        "current_role": "Software Engineer",
        "technical_skills": {
            "languages": ["Python", "JavaScript", "Ruby", "Scala", "Java"],
            "frameworks": ["Flask", "React"],
            "cloud": ["AWS"],
            "tools": ["Git", "Docker"],
            "databases": ["PostgreSQL"]
        },
        "domain_knowledge": ["healthcare", "fintech", "tax systems", "clinical assessment"],
        "soft_skills": ["public speaking", "team leadership", "stakeholder communication"],
        "experience": [
            {
                "role": "Software Engineer",
                "company": "HMRC",
                "dates": "2022–2025",
                "achievements": ["95% reduction in production alerts"]
            }
        ],
        "education": ["BSc Nursing", "Software Engineering Bootcamp"],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "notable_achievements": ["95% reduction in production alerts", "Conference speaker"],
        "source_documents": ["cv_2025.pdf", "cv_2022.pdf"]
    }


@pytest.fixture
def sample_job():
    """A realistic job listing dict as returned by job_fetcher."""
    return {
        "title": "Backend Python Engineer",
        "company": "HealthTech Barcelona",
        "location": "Barcelona, Spain",
        "description": (
            "We are looking for a Python engineer with experience in Flask or FastAPI, "
            "AWS, and PostgreSQL. Experience in healthcare or clinical systems is a strong "
            "advantage. You will work with a small team building data pipelines for "
            "patient analytics. Docker and Git required. Kubernetes a plus."
        ),
        "job_url": "https://linkedin.com/jobs/view/123456",
        "source": "linkedin",
        "market": "Barcelona / Spain"
    }


@pytest.fixture
def valid_claude_response():
    """
    The JSON structure we expect Claude to return.
    Note: match_label is NOT here — we derive it from match_score ourselves.
    This ensures label and score can never be inconsistent.
    """
    return json.dumps({
        "match_score": 78,
        "summary": "Strong Python and AWS match with valuable healthcare domain knowledge.",
        "matching_skills": ["Python", "Flask", "AWS", "PostgreSQL", "Docker", "Git"],
        "missing_skills": ["FastAPI", "Kubernetes"],
        "reasoning": (
            "The candidate has strong Python skills demonstrated through production work at HMRC. "
            "AWS certification directly addresses the cloud requirement. Healthcare domain knowledge "
            "from nursing background is a significant differentiator for this role."
        ),
        "highlight_background": (
            "Nursing background and clinical domain knowledge is directly relevant — "
            "this role builds patient analytics tools and clinical experience is listed "
            "as a strong advantage."
        )
    })


@pytest.fixture
def valid_claude_response_weak():
    """A valid Claude response for a weak match."""
    return json.dumps({
        "match_score": 25,
        "summary": "Significant skill gaps — this role requires deep Kubernetes and Go expertise.",
        "matching_skills": ["Git"],
        "missing_skills": ["Go", "Kubernetes", "Terraform", "gRPC"],
        "reasoning": "The candidate's Python background does not align with this Go-focused role.",
        "highlight_background": ""
    })


# ─────────────────────────────────────────────
# _get_match_label tests
# Testing every boundary condition — this is where
# bugs hide if you're not explicit about them.
# ─────────────────────────────────────────────

class TestGetMatchLabel:

    def test_score_at_strong_threshold_returns_strong(self):
        """Score of exactly 70 must be Strong, not Potential."""
        assert _get_match_label(70) == "Strong"

    def test_score_just_below_strong_threshold_returns_potential(self):
        """Score of 69 must be Potential, not Strong. This is the boundary."""
        assert _get_match_label(69) == "Potential"

    def test_score_at_potential_threshold_returns_potential(self):
        """Score of exactly 40 must be Potential, not Weak."""
        assert _get_match_label(40) == "Potential"

    def test_score_just_below_potential_threshold_returns_weak(self):
        """Score of 39 must be Weak, not Potential. This is the boundary."""
        assert _get_match_label(39) == "Weak"

    def test_high_score_returns_strong(self):
        assert _get_match_label(95) == "Strong"

    def test_mid_score_returns_potential(self):
        assert _get_match_label(55) == "Potential"

    def test_low_score_returns_weak(self):
        assert _get_match_label(15) == "Weak"

    def test_score_of_zero_returns_weak(self):
        assert _get_match_label(0) == "Weak"

    def test_score_of_100_returns_strong(self):
        assert _get_match_label(100) == "Strong"

    def test_thresholds_are_named_constants(self):
        """
        Thresholds must be named constants, not magic numbers buried in the function.
        This ensures they're defined once and all tests reference the same values.
        """
        assert isinstance(STRONG_THRESHOLD, int)
        assert isinstance(POTENTIAL_THRESHOLD, int)
        assert STRONG_THRESHOLD > POTENTIAL_THRESHOLD


# ─────────────────────────────────────────────
# normalise_skill tests
# ─────────────────────────────────────────────

class TestNormaliseSkill:

    def test_lowercases_skill(self):
        assert normalise_skill("Python") == "python"

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalise_skill("  Python  ") == "python"

    def test_handles_mixed_case(self):
        assert normalise_skill("JavaScript") == "javascript"

    def test_handles_already_lowercase(self):
        assert normalise_skill("python") == "python"

    def test_preserves_special_characters(self):
        """C++ and Node.js should not be mangled."""
        assert normalise_skill("C++") == "c++"
        assert normalise_skill("Node.js") == "node.js"

    def test_handles_empty_string(self):
        assert normalise_skill("") == ""

    def test_handles_all_caps(self):
        assert normalise_skill("AWS") == "aws"

    def test_handles_skill_with_numbers(self):
        assert normalise_skill("Python 3") == "python 3"

    def test_handles_hyphenated_skill(self):
        assert normalise_skill("CI/CD") == "ci/cd"


# ─────────────────────────────────────────────
# _parse_match_response tests
# This is the most important set of tests — it covers
# all the ways Claude's response could be wrong or
# unexpected. Defensive parsing is critical here.
# ─────────────────────────────────────────────

class TestParseMatchResponse:

    def test_parses_valid_response_correctly(self, valid_claude_response):
        """Happy path — Claude returns exactly what we asked for."""
        result = _parse_match_response(valid_claude_response)
        assert result["match_score"] == 78
        assert result["match_label"] == "Strong"
        assert result["summary"] == "Strong Python and AWS match with valuable healthcare domain knowledge."
        assert "Python" in result["matching_skills"]
        assert "Kubernetes" in result["missing_skills"]
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    def test_all_required_keys_present_in_output(self, valid_claude_response):
        """Every key in our schema must always be present."""
        result = _parse_match_response(valid_claude_response)
        required_keys = {
            "match_score", "match_label", "summary",
            "matching_skills", "missing_skills",
            "reasoning", "highlight_background"
        }
        assert required_keys.issubset(result.keys())

    def test_match_label_derived_from_score_not_claude(self, valid_claude_response):
        """
        The match_label must always be derived from match_score using our thresholds.
        Claude does not return a label — we compute it.
        This ensures they can never be inconsistent.
        """
        result = _parse_match_response(valid_claude_response)
        assert result["match_label"] == _get_match_label(result["match_score"])

    def test_consistency_invariant_holds_for_weak_match(self, valid_claude_response_weak):
        """The label/score consistency invariant must hold for all match strengths."""
        result = _parse_match_response(valid_claude_response_weak)
        assert result["match_label"] == _get_match_label(result["match_score"])

    def test_clamps_score_above_100(self):
        """Claude should never return >100, but if it does we clamp it."""
        response = json.dumps({
            "match_score": 105,
            "summary": "Great match.",
            "matching_skills": ["Python"],
            "missing_skills": [],
            "reasoning": "Very strong.",
            "highlight_background": ""
        })
        result = _parse_match_response(response)
        assert result["match_score"] <= 100

    def test_clamps_score_below_zero(self):
        """Claude should never return <0, but if it does we clamp it."""
        response = json.dumps({
            "match_score": -10,
            "summary": "Poor match.",
            "matching_skills": [],
            "missing_skills": ["Python"],
            "reasoning": "No overlap.",
            "highlight_background": ""
        })
        result = _parse_match_response(response)
        assert result["match_score"] >= 0

    def test_converts_float_score_to_int(self):
        """Claude occasionally returns 75.5 instead of 75."""
        response = json.dumps({
            "match_score": 75.5,
            "summary": "Good match.",
            "matching_skills": ["Python"],
            "missing_skills": [],
            "reasoning": "Strong overlap.",
            "highlight_background": ""
        })
        result = _parse_match_response(response)
        assert isinstance(result["match_score"], int)

    def test_converts_string_score_to_int(self):
        """Claude occasionally returns '75' as a string instead of 75."""
        response = json.dumps({
            "match_score": "75",
            "summary": "Good match.",
            "matching_skills": ["Python"],
            "missing_skills": [],
            "reasoning": "Strong overlap.",
            "highlight_background": ""
        })
        result = _parse_match_response(response)
        assert isinstance(result["match_score"], int)
        assert result["match_score"] == 75

    def test_handles_json_embedded_in_text(self):
        """
        Claude sometimes wraps JSON in explanatory text like:
        'Here is my analysis: { ... }'
        We must extract the JSON and ignore the surrounding text.
        """
        response = 'Here is my analysis:\n```json\n' + json.dumps({
            "match_score": 60,
            "summary": "Decent match.",
            "matching_skills": ["Python"],
            "missing_skills": ["Docker"],
            "reasoning": "Some overlap.",
            "highlight_background": ""
        }) + '\n```'
        result = _parse_match_response(response)
        assert result["match_score"] == 60

    def test_handles_missing_matching_skills_key(self):
        """If Claude omits matching_skills, return an empty list — not a crash."""
        response = json.dumps({
            "match_score": 50,
            "summary": "Partial match.",
            "missing_skills": ["Docker"],
            "reasoning": "Some overlap.",
            "highlight_background": ""
        })
        result = _parse_match_response(response)
        assert result["matching_skills"] == []

    def test_handles_missing_highlight_background_key(self):
        """highlight_background is optional — default to empty string if missing."""
        response = json.dumps({
            "match_score": 50,
            "summary": "Partial match.",
            "matching_skills": ["Python"],
            "missing_skills": ["Docker"],
            "reasoning": "Some overlap."
        })
        result = _parse_match_response(response)
        assert result["highlight_background"] == ""

    def test_handles_completely_malformed_response(self):
        """
        If Claude returns something that is not JSON at all,
        return a safe default dict rather than crashing.
        """
        result = _parse_match_response("Sorry, I cannot process this request.")
        assert isinstance(result, dict)
        assert "match_score" in result
        assert "match_label" in result

    def test_handles_empty_response(self):
        """Empty string from Claude — return a safe default."""
        result = _parse_match_response("")
        assert isinstance(result, dict)
        assert result["match_score"] == 0
        assert result["match_label"] == "Weak"

    def test_normalises_skills_in_output(self, valid_claude_response):
        """
        Skills in matching_skills and missing_skills must be normalised.
        We compare skills consistently downstream — this is the point of normalisation.
        """
        result = _parse_match_response(valid_claude_response)
        for skill in result["matching_skills"]:
            assert skill == skill.lower().strip()
        for skill in result["missing_skills"]:
            assert skill == skill.lower().strip()


# ─────────────────────────────────────────────
# match_job_to_profile tests
# The main public function — orchestrates the
# Claude call and passes the response to the parser.
# We mock the Claude client here.
# ─────────────────────────────────────────────

class TestMatchJobToProfile:

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_returns_correctly_structured_result(
        self, mock_anthropic_class, sample_profile, sample_job, valid_claude_response
    ):
        """Happy path — profile and job provided, Claude responds correctly."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        result = match_job_to_profile(sample_profile, sample_job)

        assert isinstance(result, dict)
        assert "match_score" in result
        assert "match_label" in result
        assert "matching_skills" in result
        assert "missing_skills" in result
        assert "reasoning" in result
        assert "highlight_background" in result

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_score_is_within_valid_range(
        self, mock_anthropic_class, sample_profile, sample_job, valid_claude_response
    ):
        """match_score must always be between 0 and 100."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        result = match_job_to_profile(sample_profile, sample_job)
        assert 0 <= result["match_score"] <= 100

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_label_consistent_with_score(
        self, mock_anthropic_class, sample_profile, sample_job, valid_claude_response
    ):
        """Label and score must always be consistent — label derived from score."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        result = match_job_to_profile(sample_profile, sample_job)
        assert result["match_label"] == _get_match_label(result["match_score"])

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_handles_empty_job_description(
        self, mock_anthropic_class, sample_profile, valid_claude_response
    ):
        """A job with no description should return a result, not crash."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        empty_job = {
            "title": "Software Engineer",
            "company": "Unknown",
            "description": "",
            "job_url": "https://example.com"
        }
        result = match_job_to_profile(sample_profile, empty_job)
        assert isinstance(result, dict)
        assert "match_score" in result

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_handles_empty_profile(
        self, mock_anthropic_class, sample_job, valid_claude_response
    ):
        """An empty profile should return a result, not crash."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        result = match_job_to_profile({}, sample_job)
        assert isinstance(result, dict)

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_handles_claude_api_failure(
        self, mock_anthropic_class, sample_profile, sample_job
    ):
        """
        If the Claude API call fails entirely, return a safe default result.
        The app must keep running — one failed match should not crash everything.
        """
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        result = match_job_to_profile(sample_profile, sample_job)
        assert isinstance(result, dict)
        assert result["match_score"] == 0
        assert result["match_label"] == "Weak"

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_profile_skills_are_passed_to_claude(
        self, mock_anthropic_class, sample_profile, sample_job, valid_claude_response
    ):
        """
        The Claude prompt must include the candidate's skills from the profile.
        If it doesn't, the matching will be based on nothing.
        We verify this by checking the call arguments.
        """
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        match_job_to_profile(sample_profile, sample_job)

        call_args = mock_client.messages.create.call_args
        prompt_content = str(call_args)

        # The profile's skills must appear in the prompt
        assert "Python" in prompt_content

    @patch("agents.job_matcher.anthropic.Anthropic")
    def test_job_description_is_passed_to_claude(
        self, mock_anthropic_class, sample_profile, sample_job, valid_claude_response
    ):
        """The job description must appear in the Claude prompt."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_response

        match_job_to_profile(sample_profile, sample_job)

        call_args = mock_client.messages.create.call_args
        prompt_content = str(call_args)
        assert "patient analytics" in prompt_content
