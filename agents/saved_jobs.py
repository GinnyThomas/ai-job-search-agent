"""
Persistence layer for saved jobs.

Jobs are stored in a JSON file at the path provided by the caller.
Using an explicit path parameter rather than a module-level constant
makes this easy to test with pytest's tmp_path fixture.

Job identity is determined by title + company. Saving the same job twice
updates the existing record rather than creating a duplicate.

Writes are atomic (tempfile + os.replace) so a crash mid-write cannot
produce a partially-written or corrupt file.
"""

import json
import os
import tempfile
from typing import Dict, List


def _job_key(job: Dict) -> str:
    """Stable identity key for a job — title + company."""
    return f"{job.get('title', '')}_{job.get('company', '')}"


def _write_jobs_atomic(jobs: List[Dict], path: str) -> None:
    """
    Write jobs to path atomically using a temporary file + os.replace.

    os.replace is atomic on POSIX systems: the file is either fully
    written or untouched — a crash mid-write cannot corrupt the target.
    """
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_name, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(jobs, tmp, indent=2, default=str)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def load_saved_jobs(path: str) -> List[Dict]:
    """
    Load saved jobs from the JSON file at path.

    Returns an empty list if the file doesn't exist, is corrupt, or
    contains valid JSON that is not a list of dicts (e.g. a bare {}).
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
        return []
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

    _write_jobs_atomic(jobs, path)


def remove_saved_job(job_key: str, path: str) -> None:
    """
    Remove the job with the given key (title_company) from the saved list.
    No-op if the key doesn't exist.
    """
    jobs = load_saved_jobs(path)
    jobs = [j for j in jobs if _job_key(j) != job_key]
    _write_jobs_atomic(jobs, path)
