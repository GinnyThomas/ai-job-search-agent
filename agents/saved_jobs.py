"""
Persistence layer for saved jobs.

Jobs are stored in a JSON file at the path provided by the caller (app.py
passes SOURCE_DOCS_DIR / "saved_jobs.json"). Using an explicit path rather
than a module-level constant makes this easy to test with tmp_path.

Job identity is determined by title + company. Saving the same job twice
updates the existing record rather than creating a duplicate.
"""

import json
import os
from typing import Dict, List


def _job_key(job: Dict) -> str:
    """Stable identity key for a job — title + company."""
    return f"{job.get('title', '')}_{job.get('company', '')}"


def load_saved_jobs(path: str) -> List[Dict]:
    """
    Load saved jobs from the JSON file at path.
    Returns an empty list if the file doesn't exist or is corrupt.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_job(job: Dict, path: str) -> None:
    """
    Save a job to the JSON file at path.

    If a job with the same title + company already exists, it is updated
    in place. Otherwise the new job is appended.
    """
    jobs = load_saved_jobs(path)
    key = _job_key(job)

    existing_keys = [_job_key(j) for j in jobs]
    if key in existing_keys:
        jobs = [job if _job_key(j) == key else j for j in jobs]
    else:
        jobs.append(job)

    with open(path, "w") as f:
        json.dump(jobs, f, indent=2, default=str)


def remove_saved_job(job_key: str, path: str) -> None:
    """
    Remove the job with the given key (title_company) from the saved list.
    No-op if the key doesn't exist.
    """
    jobs = load_saved_jobs(path)
    jobs = [j for j in jobs if _job_key(j) != job_key]

    with open(path, "w") as f:
        json.dump(jobs, f, indent=2, default=str)
