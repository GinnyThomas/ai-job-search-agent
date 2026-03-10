import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from jobspy import scrape_jobs
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")

# ------------------------------------------------------------
# Market configurations
# Each entry defines everything that changes between markets:
# where we search, which Adzuna country endpoint to hit,
# which Indeed country to use, and whether to filter for remote.
#
# To add a new market later, just add a new entry here.
# Nothing else in the code needs to change.
# ------------------------------------------------------------
MARKET_CONFIG = {
    "Barcelona / Spain": {
        "location": "Barcelona, Spain",
        "adzuna_country": "es",
        "indeed_country": "Spain",
        "is_remote": False,
    },
    "Remote UK": {
        "location": "United Kingdom",
        "adzuna_country": "gb",
        "indeed_country": "UK",
        "is_remote": True,
    },
    "Remote US": {
        "location": "United States",
        "adzuna_country": "us",
        "indeed_country": "USA",
        "is_remote": True,
    }
}

# The default market if none is specified
DEFAULT_MARKET = "Barcelona / Spain"


def fetch_jobs_jobspy(
    job_title: str,
    market: str = DEFAULT_MARKET,
    num_results: int = 20
) -> pd.DataFrame:
    """
    Fetch live jobs from LinkedIn, Indeed, and Glassdoor using JobSpy.

    When searching a remote market, we append 'remote' to the search term
    so the job boards surface remote-filtered results.
    """
    config = MARKET_CONFIG.get(market, MARKET_CONFIG[DEFAULT_MARKET])

    # For remote markets, add 'remote' to the search term to improve results
    search_term = f"{job_title} remote" if config["is_remote"] else job_title

    try:
        jobs = scrape_jobs(
            site_name=["linkedin", "indeed", "glassdoor"],
            search_term=search_term,
            location=config["location"],
            results_wanted=num_results,
            hours_old=72,
            country_indeed=config["indeed_country"],
            is_remote=config["is_remote"]
        )
        # Tag each result with its source market so we know where it came from
        if not jobs.empty:
            jobs["market"] = market
        return jobs

    except Exception as e:
        print(f"JobSpy fetch failed for market '{market}': {e}")
        return pd.DataFrame()


def fetch_jobs_adzuna(
    job_title: str,
    market: str = DEFAULT_MARKET,
    num_results: int = 20
) -> pd.DataFrame:
    """
    Fetch live jobs from Adzuna API.

    Adzuna uses country-specific endpoints (es, gb, us),
    which we look up from MARKET_CONFIG.
    """
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        print("Adzuna API credentials not found in .env — skipping Adzuna fetch.")
        return pd.DataFrame()

    config = MARKET_CONFIG.get(market, MARKET_CONFIG[DEFAULT_MARKET])
    country = config["adzuna_country"]

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    # For remote markets, add 'remote' to the search term
    search_term = f"{job_title} remote" if config["is_remote"] else job_title

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_API_KEY,
        "results_per_page": num_results,
        "what": search_term,
        "sort_by": "date"
    }

    # For Spain, specify Barcelona as the location
    if market == "Barcelona / Spain":
        params["where"] = "Barcelona"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("results", [])

        # Normalise Adzuna results into a consistent structure
        # so they can be combined cleanly with JobSpy results
        normalised = []
        for job in results:
            normalised.append({
                "title": job.get("title", ""),
                "company": job.get("company", {}).get("display_name", ""),
                "location": job.get("location", {}).get("display_name", ""),
                "description": job.get("description", ""),
                "job_url": job.get("redirect_url", ""),
                "source": "adzuna",
                "market": market,
                "date_posted": job.get("created", "")
            })

        return pd.DataFrame(normalised)

    except Exception as e:
        print(f"Adzuna fetch failed for market '{market}': {e}")
        return pd.DataFrame()


def fetch_all_jobs(
    job_title: str,
    market: str = DEFAULT_MARKET,
    num_results: int = 20
) -> pd.DataFrame:
    """
    The main public function called by the app.

    Fetches from all sources for the given market,
    combines results, and removes duplicates.
    """
    print(f"Fetching '{job_title}' jobs — market: {market}")

    jobspy_results = fetch_jobs_jobspy(job_title, market, num_results)
    adzuna_results = fetch_jobs_adzuna(job_title, market, num_results)

    all_jobs = pd.concat([jobspy_results, adzuna_results], ignore_index=True)

    if not all_jobs.empty:
        all_jobs = all_jobs.drop_duplicates(subset=["title", "company"], keep="first")
        # Normalise date_posted before sorting — JobSpy returns datetime.date
        # objects while Adzuna returns ISO strings. Mixing the two types causes
        # a TypeError when pandas tries to compare them for sorting.
        # pd.to_datetime handles both formats; errors='coerce' turns anything
        # unparseable into NaT which sorts last.
        if "date_posted" in all_jobs.columns:
            all_jobs["date_posted"] = pd.to_datetime(
                all_jobs["date_posted"], errors="coerce", utc=True
            )
            all_jobs = all_jobs.sort_values(
                "date_posted", ascending=False, na_position="last"
            )

    print(f"Total unique jobs found: {len(all_jobs)}")
    return all_jobs


def get_market_options() -> list:
    """
    Returns the list of available markets for use in the Streamlit UI.
    Keeps the UI and the config in sync automatically.
    """
    return list(MARKET_CONFIG.keys())


def fetch_job_from_url(url: str) -> str:
    """
    Fetch a job posting from a URL and return the main body text.

    Strips navigation, headers, footers, and scripts so only the job
    content is passed to the matcher/tailor. Uses Python's built-in
    html.parser to avoid external C-library dependencies.

    Returns an empty string if the request fails (blocked, timed out,
    404, etc.) so the caller can show a graceful UI message.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Strip boilerplate tags — we only want the job content
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text if text.strip() else ""

    except Exception:
        return ""
