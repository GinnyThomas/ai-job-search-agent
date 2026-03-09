"""
Tests for agents/job_fetcher.py

We never make real API calls in tests. Instead we use unittest.mock to replace
external calls (scrape_jobs, requests.get) with controlled fake versions.

This is called mocking. The pattern you'll see repeatedly:
    @patch("agents.job_fetcher.scrape_jobs")
    def test_something(mock_scrape):
        mock_scrape.return_value = <fake data>
        # now call our function — it uses the fake, not the real API
        result = fetch_jobs_jobspy(...)
        # assert our logic handled the fake data correctly
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from agents.job_fetcher import (
    MARKET_CONFIG,
    DEFAULT_MARKET,
    fetch_jobs_jobspy,
    fetch_jobs_adzuna,
    fetch_all_jobs,
    get_market_options,
)


# ─────────────────────────────────────────────
# Fixtures
# Fixtures are reusable pieces of test data.
# pytest injects them automatically when a test
# function declares them as parameters.
# ─────────────────────────────────────────────

@pytest.fixture
def sample_jobspy_row():
    """A single job row in the shape JobSpy returns."""
    return {
        "title": "Python Developer",
        "company": "Acme Corp",
        "location": "Barcelona, Catalonia, Spain",
        "description": "We are looking for a Python developer with Django experience.",
        "job_url": "https://www.linkedin.com/jobs/view/123456",
        "date_posted": "2026-03-02",
    }


@pytest.fixture
def sample_adzuna_response():
    """A single job result in the shape Adzuna's API returns."""
    return {
        "title": "Backend Engineer",
        "company": {"display_name": "TechCorp"},
        "location": {"display_name": "Barcelona"},
        "description": "Backend role requiring Python and FastAPI.",
        "redirect_url": "https://www.adzuna.com/jobs/details/123",
        "created": "2026-03-01T10:00:00Z",
    }


# ─────────────────────────────────────────────
# MARKET_CONFIG tests
# These verify the configuration is complete and
# consistent — the foundation everything else
# depends on.
# ─────────────────────────────────────────────

class TestMarketConfig:

    def test_all_three_markets_are_present(self):
        """All supported markets must exist in the config."""
        assert "Barcelona / Spain" in MARKET_CONFIG
        assert "Remote UK" in MARKET_CONFIG
        assert "Remote US" in MARKET_CONFIG

    def test_each_market_has_required_keys(self):
        """Every market config must have all four required keys."""
        required_keys = {"location", "adzuna_country", "indeed_country", "is_remote"}
        for market_name, config in MARKET_CONFIG.items():
            missing = required_keys - config.keys()
            assert not missing, f"Market '{market_name}' is missing keys: {missing}"

    def test_remote_markets_have_is_remote_true(self):
        """Remote markets must set is_remote to True."""
        assert MARKET_CONFIG["Remote UK"]["is_remote"] is True
        assert MARKET_CONFIG["Remote US"]["is_remote"] is True

    def test_barcelona_is_not_remote(self):
        """Barcelona is a local market, not remote."""
        assert MARKET_CONFIG["Barcelona / Spain"]["is_remote"] is False

    def test_adzuna_country_codes_are_correct(self):
        """Adzuna uses two-letter country codes for its API endpoint."""
        assert MARKET_CONFIG["Barcelona / Spain"]["adzuna_country"] == "es"
        assert MARKET_CONFIG["Remote UK"]["adzuna_country"] == "gb"
        assert MARKET_CONFIG["Remote US"]["adzuna_country"] == "us"

    def test_get_market_options_matches_config_keys(self):
        """
        get_market_options() must stay in sync with MARKET_CONFIG.
        If someone adds a market to the config but forgets to update the
        options function, this test will catch it.
        """
        options = get_market_options()
        assert set(options) == set(MARKET_CONFIG.keys())

    def test_get_market_options_returns_list(self):
        """The return type must be a list — Streamlit expects this."""
        assert isinstance(get_market_options(), list)


# ─────────────────────────────────────────────
# fetch_jobs_jobspy tests
# ─────────────────────────────────────────────

class TestFetchJobsJobspy:

    @patch("agents.job_fetcher.scrape_jobs")
    def test_returns_dataframe_on_success(self, mock_scrape, sample_jobspy_row):
        """Happy path: JobSpy returns data, we return a DataFrame."""
        mock_scrape.return_value = pd.DataFrame([sample_jobspy_row])
        result = fetch_jobs_jobspy("Python Developer", "Barcelona / Spain")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    @patch("agents.job_fetcher.scrape_jobs")
    def test_tags_results_with_market(self, mock_scrape, sample_jobspy_row):
        """
        Every result must be tagged with its market.
        We need this later when displaying results to the user.
        """
        mock_scrape.return_value = pd.DataFrame([sample_jobspy_row])
        result = fetch_jobs_jobspy("Python Developer", "Barcelona / Spain")
        assert "market" in result.columns
        assert result.iloc[0]["market"] == "Barcelona / Spain"

    @patch("agents.job_fetcher.scrape_jobs")
    def test_appends_remote_to_search_term_for_remote_markets(self, mock_scrape):
        """
        For remote markets, 'remote' must be appended to the search term
        so job boards surface remote-filtered results.
        """
        mock_scrape.return_value = pd.DataFrame()
        fetch_jobs_jobspy("Python Developer", "Remote UK")

        # Inspect what scrape_jobs was actually called with
        call_kwargs = mock_scrape.call_args[1]
        search_term = call_kwargs.get("search_term", "")
        assert "remote" in search_term.lower()

    @patch("agents.job_fetcher.scrape_jobs")
    def test_does_not_append_remote_for_local_markets(self, mock_scrape):
        """Barcelona search should not have 'remote' added to the search term."""
        mock_scrape.return_value = pd.DataFrame()
        fetch_jobs_jobspy("Python Developer", "Barcelona / Spain")

        call_kwargs = mock_scrape.call_args[1]
        search_term = call_kwargs.get("search_term", "")
        assert "remote" not in search_term.lower()

    @patch("agents.job_fetcher.scrape_jobs")
    def test_returns_empty_dataframe_on_exception(self, mock_scrape):
        """
        If JobSpy throws an exception (connection error, rate limit, etc.)
        we must return an empty DataFrame — not crash the app.
        """
        mock_scrape.side_effect = Exception("Connection refused")
        result = fetch_jobs_jobspy("Python Developer", "Barcelona / Spain")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("agents.job_fetcher.scrape_jobs")
    def test_returns_empty_dataframe_when_no_results(self, mock_scrape):
        """JobSpy returning zero results is valid — handle it cleanly."""
        mock_scrape.return_value = pd.DataFrame()
        result = fetch_jobs_jobspy("Python Developer", "Barcelona / Spain")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ─────────────────────────────────────────────
# fetch_jobs_adzuna tests
# ─────────────────────────────────────────────

class TestFetchJobsAdzuna:

    @patch("agents.job_fetcher.ADZUNA_APP_ID", None)
    @patch("agents.job_fetcher.ADZUNA_API_KEY", None)
    def test_returns_empty_dataframe_when_no_credentials(self):
        """
        If Adzuna credentials aren't configured, return empty DataFrame.
        This handles the case where someone clones the repo without
        setting up their .env file.
        """
        result = fetch_jobs_adzuna("Python Developer")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_normalises_adzuna_results_correctly(self, mock_get, sample_adzuna_response):
        """
        Adzuna returns nested JSON. We must flatten it into a consistent
        structure that matches our DataFrame shape.
        """
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [sample_adzuna_response]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_jobs_adzuna("Python Developer", "Barcelona / Spain")

        assert not result.empty
        assert result.iloc[0]["title"] == "Backend Engineer"
        assert result.iloc[0]["company"] == "TechCorp"
        assert result.iloc[0]["location"] == "Barcelona"
        assert result.iloc[0]["source"] == "adzuna"

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_uses_correct_country_endpoint_for_each_market(self, mock_get):
        """
        Adzuna's API is country-specific — the URL must match the market.
        Spain = /es/, UK = /gb/, US = /us/
        """
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetch_jobs_adzuna("Python Developer", "Remote UK")
        called_url = mock_get.call_args[0][0]
        assert "/gb/" in called_url

        fetch_jobs_adzuna("Python Developer", "Remote US")
        called_url = mock_get.call_args[0][0]
        assert "/us/" in called_url

        fetch_jobs_adzuna("Python Developer", "Barcelona / Spain")
        called_url = mock_get.call_args[0][0]
        assert "/es/" in called_url

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_returns_empty_dataframe_on_api_failure(self, mock_get):
        """If the Adzuna API call fails, return empty DataFrame — don't crash."""
        mock_get.side_effect = Exception("API timeout")
        result = fetch_jobs_adzuna("Python Developer", "Barcelona / Spain")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_tags_results_with_market(self, mock_get, sample_adzuna_response):
        """Adzuna results must also be tagged with their market."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [sample_adzuna_response]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_jobs_adzuna("Python Developer", "Remote UK")
        assert result.iloc[0]["market"] == "Remote UK"


# ─────────────────────────────────────────────
# fetch_all_jobs tests
# We mock the two inner functions here — we've
# already tested those individually above.
# This layer only tests the orchestration logic.
# ─────────────────────────────────────────────

class TestFetchAllJobs:

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_combines_results_from_both_sources(self, mock_jobspy, mock_adzuna):
        """Results from JobSpy and Adzuna must be combined into one DataFrame."""
        mock_jobspy.return_value = pd.DataFrame([
            {"title": "Python Dev", "company": "Acme", "location": "Barcelona"}
        ])
        mock_adzuna.return_value = pd.DataFrame([
            {"title": "Backend Engineer", "company": "TechCorp", "location": "Barcelona"}
        ])
        result = fetch_all_jobs("Python Developer", "Barcelona / Spain")
        assert len(result) == 2

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_deduplicates_by_title_and_company(self, mock_jobspy, mock_adzuna):
        """
        The same job can appear from multiple sources.
        Deduplication is on title + company combination.
        """
        same_job = {"title": "Python Dev", "company": "Acme", "location": "Barcelona"}
        mock_jobspy.return_value = pd.DataFrame([same_job])
        mock_adzuna.return_value = pd.DataFrame([same_job])
        result = fetch_all_jobs("Python Developer", "Barcelona / Spain")
        assert len(result) == 1

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_returns_empty_dataframe_when_all_sources_fail(self, mock_jobspy, mock_adzuna):
        """If every source returns empty, we return empty — not an error."""
        mock_jobspy.return_value = pd.DataFrame()
        mock_adzuna.return_value = pd.DataFrame()
        result = fetch_all_jobs("Python Developer", "Barcelona / Spain")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_passes_market_to_both_sources(self, mock_jobspy, mock_adzuna):
        """
        The market choice must flow through to both underlying fetchers.
        If it doesn't, both will silently use the default market instead.
        """
        mock_jobspy.return_value = pd.DataFrame()
        mock_adzuna.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", "Remote UK")

        mock_jobspy.assert_called_once_with("Python Developer", "Remote UK", 20)
        mock_adzuna.assert_called_once_with("Python Developer", "Remote UK", 20)

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_handles_mixed_date_types_without_error(self, mock_jobspy, mock_adzuna):
        """
        JobSpy returns date_posted as datetime.date objects.
        Adzuna returns date_posted as ISO strings (timezone-aware).
        Sorting a column with mixed types raises TypeError — we must
        normalise to UTC datetime before sorting.

        This test pins down four properties of the fix:
        1. No exception is raised
        2. The column is a proper datetime dtype (not a mixed object column)
        3. The dtype is timezone-aware UTC — pd.to_datetime(..., utc=True)
        4. Rows are sorted newest-first (TechCorp Mar 9 > Acme Mar 1)
        """
        import datetime
        mock_jobspy.return_value = pd.DataFrame([
            {
                "title": "Python Dev",
                "company": "Acme",
                "date_posted": datetime.date(2025, 3, 1)   # older
            }
        ])
        mock_adzuna.return_value = pd.DataFrame([
            {
                "title": "Backend Engineer",
                "company": "TechCorp",
                "date_posted": "2025-03-09T10:00:00Z"      # newer, tz-aware string
            }
        ])
        result = fetch_all_jobs("Python Developer", "Barcelona / Spain")

        assert len(result) == 2
        assert "date_posted" in result.columns

        # The column must be datetime, not a mixed object column
        assert pd.api.types.is_datetime64_any_dtype(result["date_posted"])

        # pd.to_datetime(..., utc=True) produces this specific dtype
        assert str(result["date_posted"].dtype) == "datetime64[ns, UTC]"

        # Rows must be sorted newest-first
        assert result["date_posted"].is_monotonic_decreasing

        # Concrete proof: the newer job (TechCorp, Mar 9) is first
        assert result.iloc[0]["company"] == "TechCorp"
