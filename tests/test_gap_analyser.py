"""
Tests for agents/gap_analyser.py

Follows the same TDD pattern as test_resume_tailor.py:
  - Never make real API calls — mock anthropic.Anthropic
  - Test each layer in isolation: safe default, parser, main function
  - Verify defensive handling of every failure mode Claude can produce
"""

import pytest
from unittest.mock import patch, MagicMock

from agents.gap_analyser import (
    _safe_default_gap_analysis,
    _coerce_list_of_strings,
    _coerce_string,
    _parse_gap_response,
    analyse_gaps,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def sample_profile():
    return {
        "full_name": "Ginny Thomas",
        "current_role": "Java Developer",
        "technical_skills": [
            {"name": "Python", "proficiency": "Proficient"},
            {"name": "Java", "proficiency": "Advanced"},
        ],
        "domain_knowledge": [
            {"domain": "Healthcare", "depth": "Expert", "years": 8}
        ],
    }


@pytest.fixture
def sample_job():
    return {
        "title": "Senior Python Developer",
        "company": "Acme Corp",
        "description": (
            "We need a Python expert with FastAPI and AWS experience. "
            "Healthcare domain knowledge is a strong plus."
        ),
    }


@pytest.fixture
def valid_gap_response():
    """A well-formed JSON response as Claude would return it."""
    return """{
        "top_alignment_points": [
            "8 years of healthcare domain expertise directly matches the industry focus",
            "Proficient Python skills align with primary tech stack requirement"
        ],
        "genuine_gaps": [
            "No demonstrated FastAPI experience",
            "AWS cloud experience not evident in profile"
        ],
        "transferable_strengths": [
            "Nursing background provides rare clinical workflow understanding valuable for health-tech products"
        ],
        "quick_wins": [
            "Build a small FastAPI project to demonstrate REST API skills — 1-2 days of work",
            "AWS Cloud Practitioner certification addresses the cloud gap — roughly 20 hours study"
        ],
        "honest_assessment": "Strong domain fit but a clear technical gap on FastAPI and AWS. The healthcare expertise is genuinely rare and likely outweighs the framework gap for a health-tech employer.",
        "recommended_framing": "Lead with the clinical domain expertise as a differentiator, then position Python proficiency as the foundation for a quick FastAPI ramp-up."
    }"""


# ─────────────────────────────────────────────
# _safe_default_gap_analysis tests
# ─────────────────────────────────────────────

class TestSafeDefaultGapAnalysis:

    def test_returns_all_required_keys(self):
        """Safe default must contain every key the app will access."""
        result = _safe_default_gap_analysis()
        assert "top_alignment_points" in result
        assert "genuine_gaps" in result
        assert "transferable_strengths" in result
        assert "quick_wins" in result
        assert "honest_assessment" in result
        assert "recommended_framing" in result

    def test_list_fields_are_empty_lists_not_none(self):
        """
        App code iterates over list fields without None checks.
        They must be [] not None so iteration is always safe.
        """
        result = _safe_default_gap_analysis()
        for key in ("top_alignment_points", "genuine_gaps",
                    "transferable_strengths", "quick_wins"):
            assert result[key] == []
            assert isinstance(result[key], list)

    def test_string_fields_are_empty_strings_not_none(self):
        """String fields must be "" not None so .strip() and display are safe."""
        result = _safe_default_gap_analysis()
        for key in ("honest_assessment", "recommended_framing"):
            assert result[key] == ""
            assert isinstance(result[key], str)


# ─────────────────────────────────────────────
# _coerce_list_of_strings tests
# ─────────────────────────────────────────────

class TestCoerceListOfStrings:

    def test_returns_list_of_strings_unchanged(self):
        assert _coerce_list_of_strings(["a", "b"]) == ["a", "b"]

    def test_coerces_non_string_items_to_strings(self):
        """Items that aren't strings should be converted, not dropped."""
        assert _coerce_list_of_strings([1, 2.5, True]) == ["1", "2.5", "True"]

    def test_returns_empty_list_for_none(self):
        assert _coerce_list_of_strings(None) == []

    def test_returns_empty_list_when_value_is_a_string(self):
        """
        Claude occasionally returns a plain string instead of a list.
        Joining over the characters would produce garbage; return [] instead.
        """
        assert _coerce_list_of_strings("some string") == []

    def test_returns_empty_list_for_dict(self):
        assert _coerce_list_of_strings({"key": "value"}) == []

    def test_returns_empty_list_for_integer(self):
        assert _coerce_list_of_strings(42) == []


# ─────────────────────────────────────────────
# _coerce_string tests
# ─────────────────────────────────────────────

class TestCoerceString:

    def test_returns_string_unchanged(self):
        assert _coerce_string("hello") == "hello"

    def test_returns_empty_string_for_none(self):
        assert _coerce_string(None) == ""

    def test_coerces_integer_to_string(self):
        assert _coerce_string(42) == "42"

    def test_coerces_list_to_string(self):
        """Non-string non-None values should be str()-converted, not dropped."""
        assert _coerce_string(["a", "b"]) == "['a', 'b']"


# ─────────────────────────────────────────────
# _parse_gap_response tests
# ─────────────────────────────────────────────

class TestParseGapResponse:

    def test_parses_valid_json_response(self, valid_gap_response):
        """Happy path: valid JSON returns all fields correctly populated."""
        result = _parse_gap_response(valid_gap_response)
        assert len(result["top_alignment_points"]) == 2
        assert len(result["genuine_gaps"]) == 2
        assert len(result["transferable_strengths"]) == 1
        assert len(result["quick_wins"]) == 2
        assert "healthcare" in result["honest_assessment"].lower()
        assert "domain expertise" in result["recommended_framing"].lower()

    def test_returns_safe_default_for_empty_response(self):
        """An empty response from Claude returns safe default, not a crash."""
        result = _parse_gap_response("")
        assert result == _safe_default_gap_analysis()

    def test_returns_safe_default_for_whitespace_response(self):
        result = _parse_gap_response("   \n  ")
        assert result == _safe_default_gap_analysis()

    def test_returns_safe_default_for_malformed_json(self):
        """Garbled output returns safe default rather than raising."""
        result = _parse_gap_response("Here is my analysis: it looks good {broken json")
        assert result == _safe_default_gap_analysis()

    def test_parses_json_wrapped_in_markdown_code_block(self, valid_gap_response):
        """Claude often wraps JSON in ```json ... ``` — must extract correctly."""
        wrapped = f"```json\n{valid_gap_response}\n```"
        result = _parse_gap_response(wrapped)
        assert len(result["top_alignment_points"]) == 2

    def test_uses_safe_empty_types_for_missing_keys(self):
        """If Claude omits a key, the safe empty type is used — not KeyError."""
        partial = '{"honest_assessment": "Good fit overall."}'
        result = _parse_gap_response(partial)
        assert result["top_alignment_points"] == []
        assert result["genuine_gaps"] == []
        assert result["honest_assessment"] == "Good fit overall."

    def test_or_fallback_handles_null_values(self):
        """
        Claude can return JSON null for optional fields.
        json.loads gives Python None — .get(key, default) won't catch it.
        The `or` fallback must coerce None to the safe empty type.
        """
        with_nulls = """{
            "top_alignment_points": null,
            "genuine_gaps": null,
            "transferable_strengths": null,
            "quick_wins": null,
            "honest_assessment": null,
            "recommended_framing": null
        }"""
        result = _parse_gap_response(with_nulls)
        assert result["top_alignment_points"] == []
        assert result["honest_assessment"] == ""

    def test_returns_safe_default_when_json_is_not_a_dict(self):
        """
        If Claude returns a JSON array instead of an object, parsing must not
        crash on .get() — return safe default instead.
        """
        result = _parse_gap_response('["point one", "point two"]')
        assert result == _safe_default_gap_analysis()

    def test_coerces_string_value_for_list_field_to_empty_list(self):
        """
        Claude occasionally returns a plain string for a list field.
        Iterating over a string produces characters — coerce to [] instead.
        """
        bad_types = """{
            "top_alignment_points": "Strong Python skills",
            "genuine_gaps": [],
            "transferable_strengths": [],
            "quick_wins": [],
            "honest_assessment": "Good fit.",
            "recommended_framing": "Lead with Python."
        }"""
        result = _parse_gap_response(bad_types)
        assert result["top_alignment_points"] == []

    def test_coerces_non_string_value_for_assessment_field(self):
        """
        If Claude returns a number or list for a string field, coerce to str.
        """
        bad_assessment = """{
            "top_alignment_points": [],
            "genuine_gaps": [],
            "transferable_strengths": [],
            "quick_wins": [],
            "honest_assessment": 42,
            "recommended_framing": ""
        }"""
        result = _parse_gap_response(bad_assessment)
        assert result["honest_assessment"] == "42"


# ─────────────────────────────────────────────
# analyse_gaps tests
# ─────────────────────────────────────────────

class TestAnalyseGaps:

    @patch("agents.gap_analyser.anthropic.Anthropic")
    def test_calls_claude_with_profile_and_job(
        self, mock_anthropic, sample_profile, sample_job, valid_gap_response
    ):
        """
        Claude must receive both the formatted profile and the job description.
        If either is missing from the prompt, the analysis will be blind to it.
        """
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=valid_gap_response)]
        )

        analyse_gaps(sample_profile, sample_job)

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        prompt = call_kwargs["messages"][0]["content"]

        assert "Ginny Thomas" in prompt
        assert "FastAPI" in prompt
        assert "Acme Corp" in prompt

    @patch("agents.gap_analyser.anthropic.Anthropic")
    def test_returns_parsed_result_on_success(
        self, mock_anthropic, sample_profile, sample_job, valid_gap_response
    ):
        """Successful API call returns the parsed gap analysis dict."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=valid_gap_response)]
        )

        result = analyse_gaps(sample_profile, sample_job)

        assert len(result["top_alignment_points"]) == 2
        assert len(result["genuine_gaps"]) == 2
        assert result["honest_assessment"] != ""

    @patch("agents.gap_analyser.anthropic.Anthropic")
    def test_returns_safe_default_on_api_failure(
        self, mock_anthropic, sample_profile, sample_job
    ):
        """If the Claude API throws, return safe default — don't crash the app."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        result = analyse_gaps(sample_profile, sample_job)

        assert result == _safe_default_gap_analysis()

    @patch("agents.gap_analyser.anthropic.Anthropic")
    def test_returns_safe_default_when_job_has_no_description(
        self, mock_anthropic, sample_profile
    ):
        """
        A job with no description gives Claude nothing to analyse.
        Return safe default rather than making a pointless API call.
        """
        empty_job = {"title": "Some Role", "company": "Some Co", "description": ""}

        result = analyse_gaps(sample_profile, empty_job)

        mock_anthropic.return_value.messages.create.assert_not_called()
        assert result == _safe_default_gap_analysis()

    @patch("agents.gap_analyser.anthropic.Anthropic")
    def test_returns_safe_default_when_description_is_nan(
        self, mock_anthropic, sample_profile
    ):
        """
        Jobs fetched from pandas DataFrames (JobSpy/Adzuna) have missing
        fields filled with float NaN, not empty string. NaN is truthy so
        `not job_description` passes, then .strip() raises AttributeError.
        The isinstance guard must catch this before any string operation.
        """
        import math
        nan_job = {"title": "Some Role", "company": "Some Co", "description": float("nan")}

        result = analyse_gaps(sample_profile, nan_job)

        mock_anthropic.return_value.messages.create.assert_not_called()
        assert result == _safe_default_gap_analysis()
