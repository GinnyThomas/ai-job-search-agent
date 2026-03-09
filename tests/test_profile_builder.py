"""
Tests for agents/profile_builder.py

Originally written before the implementation as part of a TDD “red phase”,
these tests now serve as an executable specification for profile_builder.py.

New concept in this file: tmp_path
pytest provides a built-in fixture called tmp_path that creates a real
temporary directory for the duration of a test, then cleans it up.
It's perfect for testing file I/O without touching your actual project files.
Usage: just declare tmp_path as a parameter and pytest injects it automatically.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.profile_builder import (
    PROFICIENCY_LEVELS,
    PROFICIENCY_ORDER,
    normalise_skill,
    _extract_text_from_file,
    _extract_profile_from_text,
    _merge_profiles,
    build_profile,
    save_profile,
    load_profile,
    format_profile_for_display,
)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def sample_cv_text():
    """Realistic CV text as extracted from a PDF or DOCX."""
    return """
    Ginny Thomas — Software Engineer

    HMRC — Software Engineer (April 2022 – July 2025)
    Built production alerting systems in Python and Scala.
    Reduced production incidents by 95%.
    Worked with AWS, PostgreSQL, and Git daily.

    Makers Academy — Software Engineering Bootcamp (2021–2022)
    Learned Ruby, JavaScript, and test-driven development.

    Previous Career: Registered Nurse Practitioner (2010–2021)
    10 years in clinical settings. Team leadership and patient assessment.

    Education: BSc Nursing | Makers Academy Bootcamp
    Certifications: AWS Certified Cloud Practitioner
    """


@pytest.fixture
def valid_skill():
    """A single valid enriched skill object."""
    return {
        "name": "python",
        "proficiency": "Proficient",
        "last_used": "2025",
        "context": "Production engineering at HMRC",
        "is_current": True
    }


@pytest.fixture
def valid_profile():
    """A complete, valid profile as profile_builder should produce."""
    return {
        "full_name": "Ginny Thomas",
        "current_role": "Software Engineer",
        "technical_skills": [
            {
                "name": "python",
                "proficiency": "Proficient",
                "last_used": "2025",
                "context": "Production engineering at HMRC",
                "is_current": True
            },
            {
                "name": "ruby",
                "proficiency": "Basic",
                "last_used": "2022",
                "context": "Coding bootcamp — Makers Academy",
                "is_current": False
            }
        ],
        "domain_knowledge": [
            {
                "domain": "healthcare / clinical systems",
                "depth": "Expert",
                "years": 10,
                "context": "Registered Nurse Practitioner",
                "is_current": False
            }
        ],
        "soft_skills": ["team leadership", "public speaking"],
        "experience": [
            {
                "role": "Software Engineer",
                "company": "HMRC",
                "dates": "2022–2025",
                "achievements": ["95% reduction in production alerts"]
            }
        ],
        "education": ["BSc Nursing", "Makers Academy Bootcamp"],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "notable_achievements": ["95% reduction in production alerts"],
        "source_documents": ["cv_2025.pdf"]
    }


@pytest.fixture
def valid_claude_profile_response(valid_profile):
    """Claude's JSON response for a profile extraction request."""
    return json.dumps(valid_profile)


# ─────────────────────────────────────────────
# Constants tests
# ─────────────────────────────────────────────

class TestConstants:

    def test_proficiency_levels_contains_all_four_values(self):
        """All four proficiency levels must be defined."""
        assert "Expert" in PROFICIENCY_LEVELS
        assert "Proficient" in PROFICIENCY_LEVELS
        assert "Familiar" in PROFICIENCY_LEVELS
        assert "Basic" in PROFICIENCY_LEVELS

    def test_proficiency_order_ranks_expert_highest(self):
        """Expert must outrank all other levels."""
        assert PROFICIENCY_ORDER["Expert"] > PROFICIENCY_ORDER["Proficient"]
        assert PROFICIENCY_ORDER["Expert"] > PROFICIENCY_ORDER["Familiar"]
        assert PROFICIENCY_ORDER["Expert"] > PROFICIENCY_ORDER["Basic"]

    def test_proficiency_order_is_strictly_ordered(self):
        """Each level must be strictly higher than the one below it."""
        assert PROFICIENCY_ORDER["Expert"] > PROFICIENCY_ORDER["Proficient"]
        assert PROFICIENCY_ORDER["Proficient"] > PROFICIENCY_ORDER["Familiar"]
        assert PROFICIENCY_ORDER["Familiar"] > PROFICIENCY_ORDER["Basic"]


# ─────────────────────────────────────────────
# normalise_skill tests
# Profile builder has its own normalise_skill —
# we test it independently here.
# ─────────────────────────────────────────────

class TestNormaliseSkill:

    def test_lowercases_skill(self):
        assert normalise_skill("Python") == "python"

    def test_strips_whitespace(self):
        assert normalise_skill("  AWS  ") == "aws"

    def test_handles_empty_string(self):
        assert normalise_skill("") == ""

    def test_preserves_special_characters(self):
        assert normalise_skill("C++") == "c++"
        assert normalise_skill("Node.js") == "node.js"


# ─────────────────────────────────────────────
# _extract_text_from_file tests
# We mock pdfplumber and python-docx so we never
# need real files on disk during tests.
# ─────────────────────────────────────────────

class TestExtractTextFromFile:

    @patch("agents.profile_builder.pdfplumber")
    def test_extracts_text_from_pdf(self, mock_pdfplumber):
        """Happy path — PDF file returns extracted text."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Software Engineer at HMRC"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdf.pages = [mock_page]

        mock_pdfplumber.open.return_value = mock_pdf

        result = _extract_text_from_file("cv_2025.pdf")
        assert "Software Engineer at HMRC" in result

    @patch("agents.profile_builder.Document")
    def test_extracts_text_from_docx(self, mock_document_class):
        """Happy path — DOCX file returns extracted text."""
        mock_para = MagicMock()
        mock_para.text = "Software Engineer at HMRC"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_document_class.return_value = mock_doc

        result = _extract_text_from_file("cv_2025.docx")
        assert "Software Engineer at HMRC" in result

    def test_extracts_text_from_txt_file(self, tmp_path):
        """
        Plain text files don't need mocking — we write a real file
        to the tmp_path directory pytest provides.
        """
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Python developer with AWS experience")

        result = _extract_text_from_file(str(txt_file))
        assert "Python developer with AWS experience" in result

    def test_returns_empty_string_for_unsupported_file_type(self):
        """Unsupported formats return empty string, not an error."""
        result = _extract_text_from_file("presentation.pptx")
        assert result == ""

    @patch("agents.profile_builder.pdfplumber")
    def test_returns_empty_string_on_pdf_read_error(self, mock_pdfplumber):
        """If PDF extraction fails, return empty string — don't crash."""
        mock_pdfplumber.open.side_effect = Exception("Corrupted PDF")
        result = _extract_text_from_file("broken.pdf")
        assert result == ""

    @patch("agents.profile_builder.Document")
    def test_returns_empty_string_on_docx_read_error(self, mock_document_class):
        """If DOCX extraction fails, return empty string — don't crash."""
        mock_document_class.side_effect = Exception("Corrupted DOCX")
        result = _extract_text_from_file("broken.docx")
        assert result == ""

    @patch("agents.profile_builder.pdfplumber")
    def test_handles_pdf_page_with_no_text(self, mock_pdfplumber):
        """PDF pages can return None from extract_text — handle gracefully."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=None)
        mock_pdf.pages = [mock_page]

        mock_pdfplumber.open.return_value = mock_pdf

        result = _extract_text_from_file("scanned.pdf")
        assert isinstance(result, str)


# ─────────────────────────────────────────────
# _extract_profile_from_text tests
# This is where Claude does the extraction work.
# We mock the API and test our parsing logic.
# ─────────────────────────────────────────────

class TestExtractProfileFromText:

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_returns_dict_with_all_required_keys(
        self, mock_anthropic_class, sample_cv_text, valid_claude_profile_response
    ):
        """Happy path — all required keys present in output."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_profile_response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")

        required_keys = {
            "full_name", "current_role", "technical_skills",
            "domain_knowledge", "soft_skills", "experience",
            "education", "certifications", "notable_achievements",
            "source_documents"
        }
        assert required_keys.issubset(result.keys())

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_technical_skills_are_list_of_dicts(
        self, mock_anthropic_class, sample_cv_text, valid_claude_profile_response
    ):
        """Technical skills must be enriched objects, not plain strings."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_profile_response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")

        assert isinstance(result["technical_skills"], list)
        if result["technical_skills"]:
            skill = result["technical_skills"][0]
            assert "name" in skill
            assert "proficiency" in skill
            assert "last_used" in skill
            assert "context" in skill
            assert "is_current" in skill

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_skill_names_are_normalised(
        self, mock_anthropic_class, sample_cv_text
    ):
        """Skill names must be normalised — lowercase, stripped."""
        response = json.dumps({
            "full_name": "Ginny Thomas",
            "current_role": "Software Engineer",
            "technical_skills": [
                {
                    "name": "Python",        # Should be normalised to "python"
                    "proficiency": "Proficient",
                    "last_used": "2025",
                    "context": "HMRC production",
                    "is_current": True
                }
            ],
            "domain_knowledge": [],
            "soft_skills": [],
            "experience": [],
            "education": [],
            "certifications": [],
            "notable_achievements": [],
            "source_documents": []
        })

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")
        assert result["technical_skills"][0]["name"] == "python"

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_proficiency_values_are_valid(
        self, mock_anthropic_class, sample_cv_text, valid_claude_profile_response
    ):
        """All proficiency values must be from the defined set."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_profile_response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")

        for skill in result["technical_skills"]:
            assert skill["proficiency"] in PROFICIENCY_LEVELS, (
                f"Invalid proficiency '{skill['proficiency']}' for skill '{skill['name']}'"
            )

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_is_current_is_boolean(
        self, mock_anthropic_class, sample_cv_text, valid_claude_profile_response
    ):
        """is_current must be a boolean — Claude sometimes returns strings."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_profile_response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")

        for skill in result["technical_skills"]:
            assert isinstance(skill["is_current"], bool), (
                f"is_current should be bool, got {type(skill['is_current'])} for '{skill['name']}'"
            )

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_source_document_is_recorded(
        self, mock_anthropic_class, sample_cv_text, valid_claude_profile_response
    ):
        """The source filename must be recorded in the profile."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value.content[0].text = valid_claude_profile_response

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")
        assert "cv_2025.pdf" in result["source_documents"]

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_handles_empty_text(self, mock_anthropic_class):
        """Empty text returns a safe empty profile, not an error."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        result = _extract_profile_from_text("", "empty.pdf")

        assert isinstance(result, dict)
        assert "technical_skills" in result
        assert result["technical_skills"] == []

    @patch("agents.profile_builder.anthropic.Anthropic")
    def test_handles_claude_api_failure(
        self, mock_anthropic_class, sample_cv_text
    ):
        """API failure returns a safe empty profile — doesn't crash."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        result = _extract_profile_from_text(sample_cv_text, "cv_2025.pdf")

        assert isinstance(result, dict)
        assert result["technical_skills"] == []


# ─────────────────────────────────────────────
# _merge_profiles tests
# The most complex function — combining skills
# from multiple documents intelligently.
# ─────────────────────────────────────────────

class TestMergeProfiles:

    def test_returns_single_profile_unchanged(self, valid_profile):
        """Single profile needs no merging."""
        result = _merge_profiles([valid_profile])
        assert result["full_name"] == valid_profile["full_name"]
        assert len(result["technical_skills"]) == len(valid_profile["technical_skills"])

    def test_returns_empty_profile_for_empty_list(self):
        """Empty list returns a safe empty profile."""
        result = _merge_profiles([])
        assert isinstance(result, dict)
        assert result["technical_skills"] == []

    def test_combines_unique_skills_from_two_profiles(self):
        """Skills from both profiles appear in the merged result."""
        profile_a = {
            "full_name": "Ginny Thomas",
            "current_role": "Software Engineer",
            "technical_skills": [
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC", "is_current": True}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": ["cv_2025.pdf"]
        }
        profile_b = {
            "full_name": "Ginny Thomas",
            "current_role": "Software Engineer",
            "technical_skills": [
                {"name": "ruby", "proficiency": "Basic",
                 "last_used": "2022", "context": "Bootcamp", "is_current": False}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": ["cv_2022.pdf"]
        }

        result = _merge_profiles([profile_a, profile_b])
        skill_names = [s["name"] for s in result["technical_skills"]]
        assert "python" in skill_names
        assert "ruby" in skill_names

    def test_deduplicates_skills_by_normalised_name(self):
        """
        Same skill appearing in both profiles should appear once.
        Normalised name is the deduplication key — 'Python' and 'python' are the same.
        """
        profile_a = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Familiar",
                 "last_used": "2023", "context": "Bootcamp", "is_current": False}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        profile_b = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC", "is_current": True}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }

        result = _merge_profiles([profile_a, profile_b])
        python_skills = [s for s in result["technical_skills"] if s["name"] == "python"]
        assert len(python_skills) == 1

    def test_keeps_higher_proficiency_on_duplicate_skill(self):
        """
        When the same skill appears with different proficiency levels,
        keep the higher proficiency — Proficient beats Familiar beats Basic.
        """
        profile_a = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Familiar",
                 "last_used": "2023", "context": "Early work", "is_current": False}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        profile_b = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC production", "is_current": True}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }

        result = _merge_profiles([profile_a, profile_b])
        python_skill = next(s for s in result["technical_skills"] if s["name"] == "python")
        assert python_skill["proficiency"] == "Proficient"

    def test_keeps_most_recent_last_used_on_duplicate_skill(self):
        """When deduplicating, keep the most recent last_used date."""
        profile_a = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Familiar",
                 "last_used": "2023", "context": "Early", "is_current": False}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        profile_b = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC", "is_current": True}
            ],
            "domain_knowledge": [], "soft_skills": [], "experience": [],
            "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }

        result = _merge_profiles([profile_a, profile_b])
        python_skill = next(s for s in result["technical_skills"] if s["name"] == "python")
        assert python_skill["last_used"] == "2025"

    def test_combines_source_documents_from_all_profiles(self):
        """source_documents must list every file that contributed to the profile."""
        profile_a = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": [], "experience": [], "education": [],
            "certifications": [], "notable_achievements": [],
            "source_documents": ["cv_2025.pdf"]
        }
        profile_b = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": [], "experience": [], "education": [],
            "certifications": [], "notable_achievements": [],
            "source_documents": ["cv_2022.pdf"]
        }

        result = _merge_profiles([profile_a, profile_b])
        assert "cv_2025.pdf" in result["source_documents"]
        assert "cv_2022.pdf" in result["source_documents"]

    def test_last_profile_wins_for_current_role(self):
        """
        For scalar fields like current_role, the last profile's value wins.
        Documents should be passed in chronological order (oldest first).
        """
        profile_old = {
            "full_name": "Ginny", "current_role": "Junior Developer",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": [], "experience": [], "education": [],
            "certifications": [], "notable_achievements": [],
            "source_documents": []
        }
        profile_new = {
            "full_name": "Ginny", "current_role": "Software Engineer",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": [], "experience": [], "education": [],
            "certifications": [], "notable_achievements": [],
            "source_documents": []
        }

        result = _merge_profiles([profile_old, profile_new])
        assert result["current_role"] == "Software Engineer"

    def test_deduplicates_soft_skills(self):
        """Soft skills appearing in multiple documents should not be duplicated."""
        profile_a = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": ["team leadership", "public speaking"],
            "experience": [], "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        profile_b = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [], "domain_knowledge": [],
            "soft_skills": ["team leadership", "stakeholder communication"],
            "experience": [], "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }

        result = _merge_profiles([profile_a, profile_b])
        assert result["soft_skills"].count("team leadership") == 1
        assert "public speaking" in result["soft_skills"]
        assert "stakeholder communication" in result["soft_skills"]


# ─────────────────────────────────────────────
# save_profile / load_profile tests
# tmp_path is pytest's built-in temporary
# directory fixture — no cleanup needed.
# ─────────────────────────────────────────────

class TestSaveAndLoadProfile:

    def test_save_profile_writes_valid_json(self, tmp_path, valid_profile):
        """Profile is written as valid, readable JSON."""
        output_path = tmp_path / "profile.json"
        save_profile(valid_profile, str(output_path))

        assert output_path.exists()
        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded["full_name"] == valid_profile["full_name"]

    def test_load_profile_returns_dict(self, tmp_path, valid_profile):
        """load_profile returns a dict."""
        output_path = tmp_path / "profile.json"
        save_profile(valid_profile, str(output_path))

        result = load_profile(str(output_path))
        assert isinstance(result, dict)

    def test_round_trip_preserves_data(self, tmp_path, valid_profile):
        """Save then load returns identical data."""
        output_path = tmp_path / "profile.json"
        save_profile(valid_profile, str(output_path))
        result = load_profile(str(output_path))

        assert result["full_name"] == valid_profile["full_name"]
        assert len(result["technical_skills"]) == len(valid_profile["technical_skills"])
        assert result["technical_skills"][0]["name"] == valid_profile["technical_skills"][0]["name"]

    def test_load_profile_returns_empty_dict_for_missing_file(self, tmp_path):
        """Missing profile file returns empty dict — not a crash."""
        result = load_profile(str(tmp_path / "nonexistent.json"))
        assert result == {}


# ─────────────────────────────────────────────
# build_profile tests
# The main orchestrator — ties everything together.
# We mock the internal functions we've already
# tested above, testing only the orchestration.
# ─────────────────────────────────────────────

class TestBuildProfile:

    @patch("agents.profile_builder._extract_profile_from_text")
    @patch("agents.profile_builder._extract_text_from_file")
    def test_processes_all_supported_files(
        self, mock_extract_text, mock_extract_profile, tmp_path, valid_profile
    ):
        """All PDF, DOCX, and TXT files in the directory are processed."""
        (tmp_path / "cv_2025.pdf").write_bytes(b"fake pdf")
        (tmp_path / "cv_2022.docx").write_bytes(b"fake docx")
        (tmp_path / "notes.txt").write_text("some notes")

        mock_extract_text.return_value = "some extracted text"
        mock_extract_profile.return_value = valid_profile

        build_profile(str(tmp_path))

        assert mock_extract_text.call_count == 3

    @patch("agents.profile_builder._extract_profile_from_text")
    @patch("agents.profile_builder._extract_text_from_file")
    def test_skips_unsupported_file_types(
        self, mock_extract_text, mock_extract_profile, tmp_path, valid_profile
    ):
        """Unsupported formats (.pptx, .xlsx etc.) are ignored."""
        (tmp_path / "cv_2025.pdf").write_bytes(b"fake pdf")
        (tmp_path / "slides.pptx").write_bytes(b"fake pptx")

        mock_extract_text.return_value = "some text"
        mock_extract_profile.return_value = valid_profile

        build_profile(str(tmp_path))

        assert mock_extract_text.call_count == 1

    @patch("agents.profile_builder._extract_profile_from_text")
    @patch("agents.profile_builder._extract_text_from_file")
    def test_returns_empty_profile_for_empty_directory(
        self, mock_extract_text, mock_extract_profile, tmp_path
    ):
        """Empty directory returns a safe empty profile."""
        result = build_profile(str(tmp_path))
        assert isinstance(result, dict)
        assert result["technical_skills"] == []

    def test_returns_empty_profile_for_nonexistent_directory(self, tmp_path):
        """Non-existent directory returns a safe empty profile — doesn't crash."""
        result = build_profile(str(tmp_path / "does_not_exist"))
        assert isinstance(result, dict)
        assert result["technical_skills"] == []

    @patch("agents.profile_builder._extract_profile_from_text")
    @patch("agents.profile_builder._extract_text_from_file")
    def test_skips_files_that_produce_empty_text(
        self, mock_extract_text, mock_extract_profile, tmp_path
    ):
        """
        If text extraction returns empty string for a file,
        we skip calling Claude for that file — no wasted API calls.
        """
        (tmp_path / "cv_2025.pdf").write_bytes(b"fake pdf")

        mock_extract_text.return_value = ""  # Empty — nothing to process

        build_profile(str(tmp_path))

        mock_extract_profile.assert_not_called()

    @patch("agents.profile_builder._merge_profiles")
    @patch("agents.profile_builder._extract_profile_from_text")
    @patch("agents.profile_builder._extract_text_from_file")
    def test_merges_profiles_from_all_documents(
        self, mock_extract_text, mock_extract_profile,
        mock_merge, tmp_path, valid_profile
    ):
        """All extracted profiles are passed to _merge_profiles."""
        (tmp_path / "cv_2025.pdf").write_bytes(b"fake pdf")
        (tmp_path / "cv_2022.pdf").write_bytes(b"fake pdf")

        mock_extract_text.return_value = "some text"
        mock_extract_profile.return_value = valid_profile
        mock_merge.return_value = valid_profile

        build_profile(str(tmp_path))

        mock_merge.assert_called_once()
        profiles_passed = mock_merge.call_args[0][0]
        assert len(profiles_passed) == 2

# ─────────────────────────────────────────────
# format_profile_for_display tests
# This function transforms profile.json into a
# structure optimised for the Streamlit UI.
# ─────────────────────────────────────────────

class TestFormatProfileForDisplay:

    def test_returns_dict_with_all_required_display_keys(self, valid_profile):
        """All keys the UI depends on must always be present."""
        result = format_profile_for_display(valid_profile)
        required_keys = {
            "full_name", "current_role",
            "current_skills", "historical_skills",
            "domain_knowledge", "soft_skills",
            "notable_achievements", "source_documents"
        }
        assert required_keys.issubset(result.keys())

    def test_current_skills_only_contains_is_current_true(self, valid_profile):
        """
        current_skills must only contain skills where is_current is True.
        The UI displays these as active, relevant skills.
        """
        result = format_profile_for_display(valid_profile)
        for skill in result["current_skills"]:
            assert skill["is_current"] is True, (
                f"Skill '{skill['name']}' has is_current=False but appeared in current_skills"
            )

    def test_historical_skills_only_contains_is_current_false(self, valid_profile):
        """
        historical_skills must only contain skills where is_current is False.
        The UI displays these with a 'may be rusty' warning.
        """
        result = format_profile_for_display(valid_profile)
        for skill in result["historical_skills"]:
            assert skill["is_current"] is False, (
                f"Skill '{skill['name']}' has is_current=True but appeared in historical_skills"
            )

    def test_all_skills_are_accounted_for(self, valid_profile):
        """
        Every skill in the profile must appear in either current_skills
        or historical_skills — none should be lost in the split.
        """
        result = format_profile_for_display(valid_profile)
        total_display = len(result["current_skills"]) + len(result["historical_skills"])
        assert total_display == len(valid_profile["technical_skills"])

    def test_ruby_appears_in_historical_skills(self, valid_profile):
        """Ruby (is_current=False in our fixture) must be in historical_skills."""
        result = format_profile_for_display(valid_profile)
        historical_names = [s["name"] for s in result["historical_skills"]]
        assert "ruby" in historical_names

    def test_python_appears_in_current_skills(self, valid_profile):
        """Python (is_current=True in our fixture) must be in current_skills."""
        result = format_profile_for_display(valid_profile)
        current_names = [s["name"] for s in result["current_skills"]]
        assert "python" in current_names

    def test_current_skills_sorted_by_proficiency_highest_first(self):
        """
        Current skills should be sorted with highest proficiency first
        so the most impressive skills appear at the top of the UI table.
        """
        profile = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "docker", "proficiency": "Familiar",
                 "last_used": "2025", "context": "CI/CD", "is_current": True},
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC", "is_current": True},
                {"name": "aws", "proficiency": "Expert",
                 "last_used": "2025", "context": "Certified", "is_current": True},
            ],
            "domain_knowledge": [], "soft_skills": [],
            "experience": [], "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }

        result = format_profile_for_display(profile)
        proficiencies = [s["proficiency"] for s in result["current_skills"]]

        # Expert should come before Proficient, Proficient before Familiar
        assert proficiencies.index("Expert") < proficiencies.index("Proficient")
        assert proficiencies.index("Proficient") < proficiencies.index("Familiar")

    def test_soft_skills_are_included_in_output(self, valid_profile):
        """
        Soft skills must appear in the display output.
        They are shown in the UI as a tag list.
        """
        result = format_profile_for_display(valid_profile)
        assert "soft_skills" in result
        assert isinstance(result["soft_skills"], list)
        assert len(result["soft_skills"]) > 0

    def test_soft_skills_match_profile(self, valid_profile):
        """Soft skills in the display must match the profile."""
        result = format_profile_for_display(valid_profile)
        for skill in valid_profile["soft_skills"]:
            assert skill in result["soft_skills"]

    def test_domain_knowledge_is_included(self, valid_profile):
        """Domain knowledge must appear in the display output."""
        result = format_profile_for_display(valid_profile)
        assert isinstance(result["domain_knowledge"], list)
        assert len(result["domain_knowledge"]) > 0

    def test_notable_achievements_are_included(self, valid_profile):
        """Notable achievements must appear in the display output."""
        result = format_profile_for_display(valid_profile)
        assert isinstance(result["notable_achievements"], list)
        assert len(result["notable_achievements"]) > 0

    def test_source_documents_are_included(self, valid_profile):
        """Source documents must appear so the user can see what was processed."""
        result = format_profile_for_display(valid_profile)
        assert "cv_2025.pdf" in result["source_documents"]

    def test_handles_empty_profile_without_crashing(self):
        """Empty profile returns a safe display dict — no None values."""
        result = format_profile_for_display({})
        assert isinstance(result, dict)
        assert result["current_skills"] == []
        assert result["historical_skills"] == []
        assert result["soft_skills"] == []
        assert result["domain_knowledge"] == []
        assert result["notable_achievements"] == []

    def test_no_field_returns_none(self, valid_profile):
        """
        Every display field must return a list or string — never None.
        The UI should never need to guard against None values.
        """
        result = format_profile_for_display(valid_profile)
        for key, value in result.items():
            assert value is not None, f"Field '{key}' returned None"

    def test_profile_with_no_historical_skills_returns_empty_list(self):
        """
        If all skills are current, historical_skills must be an empty list.
        Not missing, not None — explicitly empty.
        """
        profile = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "python", "proficiency": "Proficient",
                 "last_used": "2025", "context": "HMRC", "is_current": True}
            ],
            "domain_knowledge": [], "soft_skills": [],
            "experience": [], "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        result = format_profile_for_display(profile)
        assert result["historical_skills"] == []

    def test_profile_with_no_current_skills_returns_empty_list(self):
        """
        If all skills are historical, current_skills must be an empty list.
        """
        profile = {
            "full_name": "Ginny", "current_role": "SWE",
            "technical_skills": [
                {"name": "ruby", "proficiency": "Basic",
                 "last_used": "2022", "context": "Bootcamp", "is_current": False}
            ],
            "domain_knowledge": [], "soft_skills": [],
            "experience": [], "education": [], "certifications": [],
            "notable_achievements": [], "source_documents": []
        }
        result = format_profile_for_display(profile)
        assert result["current_skills"] == []
