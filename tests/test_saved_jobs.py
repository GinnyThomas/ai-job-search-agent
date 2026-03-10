"""
Tests for agents/saved_jobs.py

Saved jobs are persisted to a JSON file. We never touch the real filesystem
in tests — instead we use tmp_path (a pytest built-in fixture that gives
each test its own temporary directory) and pass that path to our functions.

This keeps tests fast, isolated, and side-effect-free.
"""

import json
import pytest

from agents.saved_jobs import load_saved_jobs, save_job, remove_saved_job


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def saved_jobs_path(tmp_path):
    """A temporary path for saved_jobs.json — clean for every test."""
    return str(tmp_path / "saved_jobs.json")


@pytest.fixture
def sample_job():
    """
    A job dict in the shape our app produces.
    match_label must be one of "Strong" / "Potential" / "Weak" —
    the values returned by match_job_to_profile (the UI appends "Match").
    """
    return {
        "title": "Senior Python Developer",
        "company": "Acme Corp",
        "description": "We need a Python expert with FastAPI experience.",
        "job_url": "https://example.com/jobs/123",
        "match_label": "Strong",
        "match_score": 85,
        "source": "search",
    }


@pytest.fixture
def second_job():
    return {
        "title": "Backend Engineer",
        "company": "TechCorp",
        "description": "Backend role with Python and Django.",
        "job_url": "https://example.com/jobs/456",
        "match_label": "Potential",
        "match_score": 72,
        "source": "manual",
    }


# ─────────────────────────────────────────────
# load_saved_jobs tests
# ─────────────────────────────────────────────

class TestLoadSavedJobs:

    def test_returns_empty_list_when_file_does_not_exist(self, saved_jobs_path):
        """No saved_jobs.json yet — return [] rather than raising FileNotFoundError."""
        result = load_saved_jobs(saved_jobs_path)
        assert result == []

    def test_returns_saved_jobs_from_existing_file(self, saved_jobs_path, sample_job):
        """Reads and returns jobs from an existing JSON file."""
        with open(saved_jobs_path, "w") as f:
            json.dump([sample_job], f)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1
        assert result[0]["title"] == "Senior Python Developer"

    def test_returns_empty_list_on_corrupt_file(self, saved_jobs_path):
        """Corrupt JSON must not crash the app — return [] gracefully."""
        with open(saved_jobs_path, "w") as f:
            f.write("not valid json {{{{")

        result = load_saved_jobs(saved_jobs_path)
        assert result == []

    def test_returns_list_type(self, saved_jobs_path):
        """Return type must always be a list, even for an empty file."""
        with open(saved_jobs_path, "w") as f:
            json.dump([], f)

        result = load_saved_jobs(saved_jobs_path)
        assert isinstance(result, list)

    def test_returns_empty_list_when_file_contains_dict_not_list(self, saved_jobs_path):
        """
        Valid JSON that is not a list of dicts (e.g. a bare {}) must
        return [] rather than causing 'for saved_job in saved:' to
        iterate over dict keys and break the UI.
        """
        with open(saved_jobs_path, "w") as f:
            json.dump({"title": "oops"}, f)

        result = load_saved_jobs(saved_jobs_path)
        assert result == []


# ─────────────────────────────────────────────
# save_job tests
# ─────────────────────────────────────────────

class TestSaveJob:

    def test_saves_job_to_new_file(self, saved_jobs_path, sample_job):
        """Saving a job to a non-existent file creates the file with that job."""
        save_job(sample_job, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1
        assert result[0]["title"] == "Senior Python Developer"

    def test_appends_to_existing_jobs(self, saved_jobs_path, sample_job, second_job):
        """Saving a second job appends it — doesn't overwrite the first."""
        save_job(sample_job, saved_jobs_path)
        save_job(second_job, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 2

    def test_does_not_duplicate_same_job(self, saved_jobs_path, sample_job):
        """
        Saving the same job twice (same title + company) must not create a duplicate.
        This handles the case where the user clicks Save more than once.
        """
        save_job(sample_job, saved_jobs_path)
        save_job(sample_job, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1

    def test_updates_existing_job_on_resave(self, saved_jobs_path, sample_job):
        """
        If a job with the same title + company is saved again with updated data
        (e.g. after tailoring), the stored record should be updated, not duplicated.
        """
        save_job(sample_job, saved_jobs_path)

        updated_job = {**sample_job, "match_score": 95, "match_label": "Excellent Match"}
        save_job(updated_job, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1
        assert result[0]["match_score"] == 95
        assert result[0]["match_label"] == "Excellent Match"

    def test_persists_all_fields(self, saved_jobs_path, sample_job):
        """All fields on the job dict must survive the save/load round-trip."""
        save_job(sample_job, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        saved = result[0]
        assert saved["title"] == sample_job["title"]
        assert saved["company"] == sample_job["company"]
        assert saved["description"] == sample_job["description"]
        assert saved["job_url"] == sample_job["job_url"]
        assert saved["match_label"] == sample_job["match_label"]
        assert saved["match_score"] == sample_job["match_score"]
        assert saved["source"] == sample_job["source"]


# ─────────────────────────────────────────────
# remove_saved_job tests
# ─────────────────────────────────────────────

class TestRemoveSavedJob:

    def test_removes_job_by_key(self, saved_jobs_path, sample_job, second_job):
        """Removes the correct job and leaves the rest untouched."""
        save_job(sample_job, saved_jobs_path)
        save_job(second_job, saved_jobs_path)

        job_key = f"{sample_job['title']}_{sample_job['company']}"
        remove_saved_job(job_key, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1
        assert result[0]["title"] == "Backend Engineer"

    def test_no_error_when_removing_nonexistent_key(self, saved_jobs_path, sample_job):
        """Removing a key that doesn't exist is a no-op — no exception raised."""
        save_job(sample_job, saved_jobs_path)

        remove_saved_job("NonExistent_Company", saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert len(result) == 1

    def test_no_error_when_removing_from_empty_file(self, saved_jobs_path):
        """Removing from an empty list is safe."""
        remove_saved_job("SomeJob_SomeCompany", saved_jobs_path)
        result = load_saved_jobs(saved_jobs_path)
        assert result == []

    def test_empty_list_after_removing_only_job(self, saved_jobs_path, sample_job):
        """After removing the last job, the saved list should be empty."""
        save_job(sample_job, saved_jobs_path)

        job_key = f"{sample_job['title']}_{sample_job['company']}"
        remove_saved_job(job_key, saved_jobs_path)

        result = load_saved_jobs(saved_jobs_path)
        assert result == []
