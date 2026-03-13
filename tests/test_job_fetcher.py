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
    CUSTOM_LOCATION_LABEL,
    fetch_jobs_jobspy,
    fetch_jobs_adzuna,
    fetch_all_jobs,
    get_market_options,
    fetch_job_from_url,
    _is_safe_url,
    _fetch_jobs_jobspy_custom,
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

    def test_get_market_options_contains_all_config_keys(self):
        """
        get_market_options() must include all MARKET_CONFIG keys.
        If someone adds a market to the config but forgets to update the
        options function, this test will catch it.
        """
        options = get_market_options()
        for market in MARKET_CONFIG.keys():
            assert market in options

    def test_get_market_options_includes_custom_location_label(self):
        """
        get_market_options() must include the CUSTOM_LOCATION_LABEL sentinel
        so the UI can offer a free-text location entry option.
        """
        options = get_market_options()
        assert CUSTOM_LOCATION_LABEL in options

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
        The is_remote_override defaults to None and must also be forwarded.
        """
        mock_jobspy.return_value = pd.DataFrame()
        mock_adzuna.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", "Remote UK")

        mock_jobspy.assert_called_once_with("Python Developer", "Remote UK", 20, None)
        mock_adzuna.assert_called_once_with("Python Developer", "Remote UK", 20, None)

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


# ─────────────────────────────────────────────
# fetch_job_from_url tests
# This function fetches a job posting from any
# URL and returns the main body text.
# ─────────────────────────────────────────────

class TestFetchJobFromUrl:

    @patch("agents.job_fetcher.requests.get")
    def test_returns_text_from_valid_url(self, mock_get):
        """Happy path: a reachable page returns its main text content."""
        mock_response = MagicMock()
        mock_response.text = """
            <html>
              <body>
                <nav>Site navigation</nav>
                <main>
                  <h1>Senior Python Developer</h1>
                  <p>We are looking for an experienced Python developer.</p>
                  <p>You will work with FastAPI and PostgreSQL.</p>
                </main>
                <footer>Footer content</footer>
              </body>
            </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_job_from_url("https://example.com/jobs/123")

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Senior Python Developer" in result
        assert "FastAPI" in result

    @patch("agents.job_fetcher.requests.get")
    def test_strips_navigation_and_footer(self, mock_get):
        """
        Nav, footer, header, and script tags must be stripped.
        Only the job content should remain.
        """
        mock_response = MagicMock()
        mock_response.text = """
            <html>
              <body>
                <nav>Log in | Sign up | About us</nav>
                <header>Company Header</header>
                <script>alert('tracking')</script>
                <div class="job-description">
                  <h2>Software Engineer</h2>
                  <p>Join our team to build great things.</p>
                </div>
                <footer>Privacy Policy | Terms</footer>
              </body>
            </html>
        """
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_job_from_url("https://example.com/jobs/456")

        assert "Software Engineer" in result
        assert "Log in" not in result
        assert "Privacy Policy" not in result
        assert "alert" not in result

    @patch("agents.job_fetcher.requests.get")
    def test_returns_empty_string_on_network_error(self, mock_get):
        """
        Connection errors (timeout, DNS failure, etc.) must return empty string.
        The app should handle this gracefully and show a UI message.
        """
        mock_get.side_effect = Exception("Connection timed out")

        result = fetch_job_from_url("https://example.com/jobs/789")

        assert result == ""

    @patch("agents.job_fetcher.requests.get")
    def test_returns_empty_string_on_http_error(self, mock_get):
        """
        A 403 (blocked) or 404 (not found) must return empty string, not raise.
        Many job boards block scrapers — we should fail gracefully.
        """
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_get.return_value = mock_response

        result = fetch_job_from_url("https://linkedin.com/jobs/view/99999")

        assert result == ""

    @patch("agents.job_fetcher.requests.get")
    def test_sends_browser_like_user_agent(self, mock_get):
        """
        We must send a realistic User-Agent header to avoid trivial bot blocks.
        Requests without a User-Agent are often rejected immediately.
        """
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Job content</p></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetch_job_from_url("https://example.com/jobs/123")

        call_kwargs = mock_get.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "User-Agent" in headers
        # Should look like a real browser, not 'python-requests/x.y.z'
        assert "Mozilla" in headers["User-Agent"]

    @patch("agents.job_fetcher.requests.get")
    def test_returns_empty_string_for_empty_page(self, mock_get):
        """An empty or near-empty response body should return empty string."""
        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = fetch_job_from_url("https://example.com/jobs/empty")

        assert result == ""


# ─────────────────────────────────────────────
# _is_safe_url tests
# ─────────────────────────────────────────────

class TestIsSafeUrl:

    def test_allows_https_public_domain(self):
        assert _is_safe_url("https://example.com/jobs/123") is True

    def test_allows_http_public_domain(self):
        assert _is_safe_url("http://example.com/jobs/123") is True

    def test_blocks_non_http_scheme(self):
        assert _is_safe_url("ftp://example.com/file") is False
        assert _is_safe_url("file:///etc/passwd") is False

    def test_blocks_localhost_hostname(self):
        assert _is_safe_url("http://localhost/admin") is False

    def test_blocks_loopback_ipv4(self):
        assert _is_safe_url("http://127.0.0.1/secret") is False

    def test_blocks_private_ipv4(self):
        assert _is_safe_url("http://192.168.1.1/router") is False
        assert _is_safe_url("http://10.0.0.1/internal") is False

    def test_blocks_link_local_aws_metadata(self):
        """169.254.169.254 is the AWS instance metadata endpoint — must be blocked."""
        assert _is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    @patch("agents.job_fetcher.requests.get")
    def test_fetch_job_from_url_rejects_unsafe_url(self, mock_get):
        """fetch_job_from_url must return '' for unsafe URLs without making a request."""
        result = fetch_job_from_url("http://localhost/admin")
        assert result == ""
        mock_get.assert_not_called()


# ─────────────────────────────────────────────
# CUSTOM_LOCATION_LABEL tests
# ─────────────────────────────────────────────

class TestCustomLocationLabel:

    def test_custom_location_label_is_a_string(self):
        """The sentinel must be a plain string — Streamlit selectbox requires this."""
        assert isinstance(CUSTOM_LOCATION_LABEL, str)
        assert len(CUSTOM_LOCATION_LABEL) > 0

    def test_custom_location_label_is_not_a_market_key(self):
        """
        The sentinel must not collide with any real market name — otherwise
        the app would try to look it up in MARKET_CONFIG and get wrong config.
        """
        assert CUSTOM_LOCATION_LABEL not in MARKET_CONFIG


# ─────────────────────────────────────────────
# _fetch_jobs_jobspy_custom tests
# ─────────────────────────────────────────────

class TestFetchJobsJobspyCustom:

    @patch("agents.job_fetcher.scrape_jobs")
    def test_returns_dataframe_on_success(self, mock_scrape, sample_jobspy_row):
        """Happy path: returns a DataFrame with the scraped results."""
        mock_scrape.return_value = pd.DataFrame([sample_jobspy_row])
        result = _fetch_jobs_jobspy_custom("Python Developer", "Berlin, Germany")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1

    @patch("agents.job_fetcher.scrape_jobs")
    def test_tags_results_with_custom_location_as_market(self, mock_scrape, sample_jobspy_row):
        """
        Custom location searches tag results with the location string as market.
        This is what the UI uses to display where the search was run.
        """
        mock_scrape.return_value = pd.DataFrame([sample_jobspy_row])
        result = _fetch_jobs_jobspy_custom("Python Developer", "Berlin, Germany")
        assert result.iloc[0]["market"] == "Berlin, Germany"

    @patch("agents.job_fetcher.scrape_jobs")
    def test_appends_remote_to_search_term_when_is_remote_true(self, mock_scrape):
        """When is_remote=True, 'remote' must be added to the search term."""
        mock_scrape.return_value = pd.DataFrame()
        _fetch_jobs_jobspy_custom("Python Developer", "Berlin, Germany", is_remote=True)
        call_kwargs = mock_scrape.call_args[1]
        assert "remote" in call_kwargs["search_term"].lower()

    @patch("agents.job_fetcher.scrape_jobs")
    def test_does_not_append_remote_when_is_remote_false(self, mock_scrape):
        """When is_remote=False, 'remote' must NOT be added to the search term."""
        mock_scrape.return_value = pd.DataFrame()
        _fetch_jobs_jobspy_custom("Python Developer", "Berlin, Germany", is_remote=False)
        call_kwargs = mock_scrape.call_args[1]
        assert "remote" not in call_kwargs["search_term"].lower()

    @patch("agents.job_fetcher.scrape_jobs")
    def test_passes_location_to_scrape_jobs(self, mock_scrape):
        """The custom location string must be forwarded to scrape_jobs as 'location'."""
        mock_scrape.return_value = pd.DataFrame()
        _fetch_jobs_jobspy_custom("Python Developer", "Sydney, Australia")
        call_kwargs = mock_scrape.call_args[1]
        assert call_kwargs["location"] == "Sydney, Australia"

    @patch("agents.job_fetcher.scrape_jobs")
    def test_returns_empty_dataframe_on_exception(self, mock_scrape):
        """Exceptions from scrape_jobs must be caught and return empty DataFrame."""
        mock_scrape.side_effect = Exception("Network error")
        result = _fetch_jobs_jobspy_custom("Python Developer", "Berlin, Germany")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ─────────────────────────────────────────────
# is_remote_override tests
# Verify the override flows through correctly in
# fetch_jobs_jobspy and fetch_jobs_adzuna.
# ─────────────────────────────────────────────

class TestIsRemoteOverride:

    @patch("agents.job_fetcher.scrape_jobs")
    def test_jobspy_override_true_forces_remote_search_on_local_market(self, mock_scrape):
        """
        is_remote_override=True must add 'remote' to the search term even for
        Barcelona, which defaults to is_remote=False.
        """
        mock_scrape.return_value = pd.DataFrame()
        fetch_jobs_jobspy("Python Developer", "Barcelona / Spain", is_remote_override=True)
        call_kwargs = mock_scrape.call_args[1]
        assert "remote" in call_kwargs["search_term"].lower()
        assert call_kwargs["is_remote"] is True

    @patch("agents.job_fetcher.scrape_jobs")
    def test_jobspy_override_false_suppresses_remote_on_remote_market(self, mock_scrape):
        """
        is_remote_override=False must remove 'remote' from the search term even for
        Remote UK, which defaults to is_remote=True.
        """
        mock_scrape.return_value = pd.DataFrame()
        fetch_jobs_jobspy("Python Developer", "Remote UK", is_remote_override=False)
        call_kwargs = mock_scrape.call_args[1]
        assert "remote" not in call_kwargs["search_term"].lower()
        assert call_kwargs["is_remote"] is False

    @patch("agents.job_fetcher.scrape_jobs")
    def test_jobspy_none_override_uses_market_default(self, mock_scrape):
        """
        is_remote_override=None must fall back to the market config's default.
        Remote UK defaults to is_remote=True so the search term must include 'remote'.
        """
        mock_scrape.return_value = pd.DataFrame()
        fetch_jobs_jobspy("Python Developer", "Remote UK", is_remote_override=None)
        call_kwargs = mock_scrape.call_args[1]
        assert "remote" in call_kwargs["search_term"].lower()

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_adzuna_override_true_adds_remote_to_search_term(self, mock_get):
        """is_remote_override=True must add 'remote' to the Adzuna search term."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetch_jobs_adzuna("Python Developer", "Barcelona / Spain", is_remote_override=True)
        call_params = mock_get.call_args[1]["params"]
        assert "remote" in call_params["what"].lower()

    @patch("agents.job_fetcher.ADZUNA_APP_ID", "test_app_id")
    @patch("agents.job_fetcher.ADZUNA_API_KEY", "test_api_key")
    @patch("agents.job_fetcher.requests.get")
    def test_adzuna_override_false_suppresses_remote_on_remote_market(self, mock_get):
        """is_remote_override=False must remove 'remote' from the Adzuna search term."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetch_jobs_adzuna("Python Developer", "Remote UK", is_remote_override=False)
        call_params = mock_get.call_args[1]["params"]
        assert "remote" not in call_params["what"].lower()


# ─────────────────────────────────────────────
# fetch_all_jobs custom_location tests
# ─────────────────────────────────────────────

class TestFetchAllJobsCustomLocation:

    @patch("agents.job_fetcher._fetch_jobs_jobspy_custom")
    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_custom_location_uses_jobspy_custom_not_standard(
        self, mock_jobspy, mock_adzuna, mock_custom
    ):
        """
        When custom_location is provided, _fetch_jobs_jobspy_custom must be called
        and fetch_jobs_jobspy / fetch_jobs_adzuna must NOT be called.
        Custom locations have no Adzuna country code, so Adzuna is skipped.
        """
        mock_custom.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", custom_location="Berlin, Germany")
        mock_custom.assert_called_once()
        mock_jobspy.assert_not_called()
        mock_adzuna.assert_not_called()

    @patch("agents.job_fetcher._fetch_jobs_jobspy_custom")
    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_custom_location_passes_location_to_custom_fetcher(
        self, mock_jobspy, mock_adzuna, mock_custom
    ):
        """The location string must flow through to _fetch_jobs_jobspy_custom."""
        mock_custom.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", custom_location="Sydney, Australia")
        call_args = mock_custom.call_args
        assert call_args[0][1] == "Sydney, Australia"

    @patch("agents.job_fetcher._fetch_jobs_jobspy_custom")
    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_custom_location_with_remote_override_true(
        self, mock_jobspy, mock_adzuna, mock_custom
    ):
        """is_remote_override=True must be forwarded to the custom fetcher."""
        mock_custom.return_value = pd.DataFrame()
        fetch_all_jobs(
            "Python Developer",
            custom_location="Berlin, Germany",
            is_remote_override=True,
        )
        call_args = mock_custom.call_args
        assert call_args[0][2] is True  # is_remote positional arg

    @patch("agents.job_fetcher._fetch_jobs_jobspy_custom")
    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_custom_location_defaults_is_remote_false_when_override_is_none(
        self, mock_jobspy, mock_adzuna, mock_custom
    ):
        """
        When is_remote_override is None (not provided) with a custom location,
        is_remote must default to False — no 'remote' search when unspecified.
        """
        mock_custom.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", custom_location="Berlin, Germany")
        call_args = mock_custom.call_args
        assert call_args[0][2] is False  # is_remote defaults to False

    @patch("agents.job_fetcher.fetch_jobs_adzuna")
    @patch("agents.job_fetcher.fetch_jobs_jobspy")
    def test_is_remote_override_forwarded_to_both_sources_for_preset_market(
        self, mock_jobspy, mock_adzuna
    ):
        """
        For preset markets, is_remote_override must be forwarded to both
        fetch_jobs_jobspy and fetch_jobs_adzuna.
        """
        mock_jobspy.return_value = pd.DataFrame()
        mock_adzuna.return_value = pd.DataFrame()
        fetch_all_jobs("Python Developer", "Barcelona / Spain", is_remote_override=True)
        mock_jobspy.assert_called_once_with("Python Developer", "Barcelona / Spain", 20, True)
        mock_adzuna.assert_called_once_with("Python Developer", "Barcelona / Spain", 20, True)
