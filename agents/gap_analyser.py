"""
Gap analysis agent.

Performs a deep analysis of the fit between a candidate profile and a
specific job description, returning a structured brief that:

  1. Can be displayed in the UI to help the candidate understand where
     they stand before applying.
  2. Is passed to resume_tailor as a pre-computed writing brief so
     Claude tailors from clear direction rather than doing analysis
     and writing simultaneously (two-call architecture).

Schema:
    top_alignment_points  — specific ways the candidate matches this role
    genuine_gaps          — skills/experience the job wants that are missing
    transferable_strengths — non-obvious strengths from background
    quick_wins            — actionable steps to address the most important gaps
    honest_assessment     — 2-3 sentence realistic evaluation of overall fit
    recommended_framing   — how to position the candidacy for this specific role
"""

import json
import re
import anthropic
from dotenv import load_dotenv
from agents.job_matcher import _format_profile_for_prompt

load_dotenv()

SONNET_MODEL = "claude-sonnet-4-5-20250929"


def _safe_default_gap_analysis() -> dict:
    """
    Return a safe, valid result dict when something goes wrong.
    Every value is a safe empty type — never None — because app.py
    will iterate over lists and render strings without None checks.
    """
    return {
        "top_alignment_points": [],
        "genuine_gaps": [],
        "transferable_strengths": [],
        "quick_wins": [],
        "honest_assessment": "",
        "recommended_framing": "",
    }


def _extract_json_from_text(text: str) -> str:
    """
    Extract a JSON object from text that may contain surrounding content.
    Uses first-'{' to last-'}' extraction to handle nested objects correctly.
    """
    for pattern in (r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```'):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1)
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                return candidate[start:end + 1]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


def _parse_gap_response(response_text: str) -> dict:
    """
    Parse and validate Claude's gap analysis response.

    Defensively handles every failure mode:
      - Empty or whitespace-only response
      - JSON wrapped in markdown code blocks
      - Missing keys (default to safe empty types)
      - JSON null values (coerced via `or` fallback)
      - Completely malformed response
    """
    if not response_text or not response_text.strip():
        return _safe_default_gap_analysis()

    try:
        json_text = _extract_json_from_text(response_text)
        data = json.loads(json_text)

        return {
            "top_alignment_points": data.get("top_alignment_points") or [],
            "genuine_gaps": data.get("genuine_gaps") or [],
            "transferable_strengths": data.get("transferable_strengths") or [],
            "quick_wins": data.get("quick_wins") or [],
            "honest_assessment": data.get("honest_assessment") or "",
            "recommended_framing": data.get("recommended_framing") or "",
        }

    except (json.JSONDecodeError, ValueError, TypeError):
        return _safe_default_gap_analysis()


def analyse_gaps(profile: dict, job: dict) -> dict:
    """
    Analyse the gaps between a candidate's profile and a job description.

    Returns a structured brief that can be shown in the UI and passed to
    tailor_resume as pre-computed direction (see two-call architecture).

    Returns safe default if the job has no description (nothing to analyse)
    or if the Claude API call fails.
    """
    job_description = job.get("description", "")
    # pandas fills missing fields with float NaN — coerce to string defensively
    if not isinstance(job_description, str):
        job_description = ""
    if not job_description.strip():
        return _safe_default_gap_analysis()

    try:
        client = anthropic.Anthropic()

        job_title = job.get("title", "")
        job_company = job.get("company", "")
        full_name = profile.get("full_name", "")
        formatted_profile = _format_profile_for_prompt(profile)

        prompt = f"""You are a senior career coach and technical recruiter with deep expertise \
in software engineering hiring. Analyse the fit between this candidate and job, then return \
a structured brief a CV writer will use to tailor the application.

            CANDIDATE: {full_name}

            CANDIDATE PROFILE:
            {formatted_profile}

            JOB TO ANALYSE:
            Title: {job_title}
            Company: {job_company}
            Description: {job_description}

            Provide an honest, specific analysis. Rules:
            - Be concrete — reference actual skills, technologies, and experiences by name
            - Be honest about gaps — a realistic assessment is more useful than flattery
            - transferable_strengths should surface non-obvious value (e.g. domain expertise,
              unusual background, soft skills with measurable impact)
            - quick_wins should be genuinely actionable in days or weeks, not months
            - recommended_framing should give the CV writer a clear positioning angle

            Return ONLY a JSON object with this exact structure, no other text:
            {{
                "top_alignment_points": [
                    "<specific way candidate matches a requirement — name the skill/tech/experience>"
                ],
                "genuine_gaps": [
                    "<skill or experience the job requires that is missing or weak in the profile>"
                ],
                "transferable_strengths": [
                    "<non-obvious strength from background that is genuinely relevant to this role>"
                ],
                "quick_wins": [
                    "<specific actionable step to address a gap — include time estimate where possible>"
                ],
                "honest_assessment": "<2-3 sentences: realistic evaluation of overall fit, naming the strongest asset and the biggest risk>",
                "recommended_framing": "<1-2 sentences: the positioning angle the CV writer should lead with for this specific role>"
            }}"""

        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        return _parse_gap_response(response.content[0].text)

    except Exception as e:
        print(f"Gap analysis failed for '{job.get('title', 'unknown')}': {e}")
        return _safe_default_gap_analysis()
