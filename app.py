import copy
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from agents.job_fetcher import fetch_all_jobs, get_market_options, fetch_job_from_url
from agents.saved_jobs import load_saved_jobs, save_job, remove_saved_job
from agents.job_matcher import match_job_to_profile
from agents.profile_builder import (
    build_profile,
    save_profile,
    load_profile,
    format_profile_for_display,
    extract_text_from_file,
    PROFICIENCY_LEVELS,
)
from agents.resume_tailor import tailor_resume
from agents.cv_renderer import generate_docx
from agents.gap_analyser import analyse_gaps

load_dotenv()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
PROFILE_PATH = "data/profile.json"
SOURCE_DOCS_DIR = "data/source_documents"
SAVED_JOBS_PATH = "data/saved_jobs.json"

MATCH_LABEL_EMOJI = {
    "Strong": "🟢",
    "Potential": "🟡",
    "Weak": "🔴",
}

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI Job Search Agent",
    page_icon="🔍",
    layout="wide"
)

# ─────────────────────────────────────────────
# Session state
# Try to load an existing profile from disk on
# first run so the user doesn't have to rebuild
# every session.
# ─────────────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = load_profile(PROFILE_PATH)

if "match_results" not in st.session_state:
    st.session_state.match_results = []

if "base_cv_filename" not in st.session_state:
    st.session_state.base_cv_filename = None

if "tailored_results" not in st.session_state:
    st.session_state.tailored_results = {}

if "fit_check_result" not in st.session_state:
    st.session_state.fit_check_result = None

if "gap_analysis_results" not in st.session_state:
    st.session_state.gap_analysis_results = {}

# ─────────────────────────────────────────────
# Sidebar — profile status at a glance
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("Status")
    if st.session_state.profile:
        name = st.session_state.profile.get("full_name") or "Profile"
        skill_count = len(st.session_state.profile.get("technical_skills", []))
        st.success(f"✅ {name}")
        st.caption(f"{skill_count} skills detected")
    else:
        st.warning("⚠️ No profile built yet")
        st.caption("Go to My Profile to get started.")

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.title("🔍 AI Job Search Agent")
st.caption("Find the right roles. Apply with confidence.")
st.divider()

# ─────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["👤 My Profile", "🔍 Search Jobs", "🎯 Am I a good fit?"])


# ─────────────────────────────────────────────
# Helper — Tailor Resume UI block
# Used in both Tab 2 (search results) and Tab 3
# (saved jobs). widget_prefix keeps Streamlit
# widget keys unique across tabs.
# ─────────────────────────────────────────────
def _has_gap_content(gap: dict) -> bool:
    """
    Return True if the gap analysis dict contains any renderable content.

    Checks all six fields so a result that only has (e.g.) quick_wins or
    recommended_framing still renders rather than being treated as empty.
    """
    return any([
        gap.get("top_alignment_points"),
        gap.get("genuine_gaps"),
        gap.get("transferable_strengths"),
        gap.get("quick_wins"),
        gap.get("honest_assessment"),
        gap.get("recommended_framing"),
    ])


def _render_gap_analysis(gap: dict) -> None:
    """Render the gap analysis output — shared by Tab 2 cards and Tab 3."""
    if gap.get("top_alignment_points"):
        st.markdown("**✅ Key alignment points**")
        for point in gap["top_alignment_points"]:
            st.write(f"• {point}")

    if gap.get("genuine_gaps"):
        st.markdown("**⚠️ Genuine gaps**")
        for g in gap["genuine_gaps"]:
            st.write(f"• {g}")

    if gap.get("transferable_strengths"):
        st.markdown("**💡 Transferable strengths**")
        for s in gap["transferable_strengths"]:
            st.write(f"• {s}")

    if gap.get("quick_wins"):
        st.markdown("**🎯 Quick wins**")
        for win in gap["quick_wins"]:
            st.write(f"• {win}")

    if gap.get("honest_assessment"):
        st.info(gap["honest_assessment"])

    if gap.get("recommended_framing"):
        st.success(f"**Framing:** {gap['recommended_framing']}")


def _render_tailor_section(job: dict, job_key: str, widget_prefix: str = "") -> None:
    wk = f"{widget_prefix}{job_key}"

    if st.button("✍️ Tailor Resume", key=f"tailor_{wk}"):
        base_cv_filename = st.session_state.get("base_cv_filename")
        if not base_cv_filename:
            st.warning("Select your base CV in the My Profile tab first.")
        else:
            base_cv_path = Path(SOURCE_DOCS_DIR) / base_cv_filename
            base_cv_text = extract_text_from_file(str(base_cv_path))
            if not base_cv_text:
                st.error("Could not read the base CV. Check the file is a valid PDF, DOCX, or TXT.")
            else:
                gap = st.session_state.gap_analysis_results.get(job_key)
                with st.spinner("Tailoring your CV for this role…"):
                    tailored = tailor_resume(
                        st.session_state.profile, job, base_cv_text, gap_analysis=gap
                    )
                candidate_name = st.session_state.profile.get("full_name", "CV")
                st.session_state.tailored_results[job_key] = {
                    "content": tailored,
                    "docx_bytes": generate_docx(tailored, candidate_name),
                }

    cached = st.session_state.tailored_results.get(job_key)
    if cached:
        tailored = cached["content"]
        if tailored.get("summary"):
            st.divider()
            st.markdown("**✍️ Tailored CV Content**")

            if tailored.get("summary"):
                st.markdown("**Summary**")
                st.write(tailored["summary"])

            if tailored.get("highlighted_skills"):
                st.markdown("**Key Skills**")
                st.write(", ".join(tailored["highlighted_skills"]))

            if tailored.get("cover_note"):
                st.markdown("**Cover Note / Talking Points**")
                st.info(tailored["cover_note"])

            safe_company = "".join(
                c for c in job.get("company", "company") if c.isalnum() or c in " _-"
            ).strip()
            st.download_button(
                label="⬇️ Download Tailored CV (.docx)",
                data=cached["docx_bytes"],
                file_name=f"CV_{safe_company}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"download_{wk}",
            )


# ═════════════════════════════════════════════
# TAB 1 — MY PROFILE
# ═════════════════════════════════════════════
with tab1:

    st.subheader("Build Your Profile")
    st.write(
        "Upload your CV and any supporting documents — performance reviews, "
        "cover letters, reflections. The more context you provide, the more "
        "accurately the tool can assess your skills."
    )

    uploaded_files = st.file_uploader(
        "Upload documents",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if st.button("⚙️ Build Profile", disabled=not uploaded_files):
        Path(SOURCE_DOCS_DIR).mkdir(parents=True, exist_ok=True)

        for f in uploaded_files:
            # Sanitise the filename — Path(f.name).name strips any directory
            # components (e.g. "../../config.py" becomes "config.py"),
            # preventing path traversal outside data/source_documents/.
            safe_name = Path(f.name).name
            if safe_name != f.name:
                st.warning(f"Skipping file with unsafe name: {f.name}")
                continue
            dest = Path(SOURCE_DOCS_DIR) / safe_name
            dest.write_bytes(f.read())

        with st.spinner("Reading your documents and building your profile…"):
            profile = build_profile(SOURCE_DOCS_DIR)
            save_profile(profile, PROFILE_PATH)
            st.session_state.profile = profile
            st.session_state.match_results = []  # old results are now stale

        skill_count = len(profile.get("technical_skills", []))
        if skill_count == 0:
            st.warning(
                "⚠️ Profile built but no skills were detected. "
                "This can happen if the documents are scanned images (not selectable text), "
                "or if the AI response was cut short. Try uploading your main CV only and "
                "rebuilding, or check that your PDF contains selectable text."
            )
        else:
            st.success(f"Profile built and saved — {skill_count} skills detected.")
        st.rerun()

    # ── Profile display ──────────────────────────────────────────────
    if not st.session_state.profile:
        st.info("No profile yet. Upload your documents above and click Build Profile.")
    else:
        display = format_profile_for_display(st.session_state.profile)

        st.header(display["full_name"] or "Your Profile")

        # Editable current role — Claude sometimes picks up an older role
        # from historical CVs. The user can correct it here without touching
        # the JSON directly.
        current_role_input = st.text_input(
            "Current Role",
            value=display["current_role"],
            key="current_role_input",
            placeholder="e.g. Java Developer",
        )
        if current_role_input != display["current_role"]:
            if st.button("💾 Save role"):
                updated = copy.deepcopy(st.session_state.profile)
                updated["current_role"] = current_role_input
                save_profile(updated, PROFILE_PATH)
                st.session_state.profile = updated
                st.success("Saved.")
                st.rerun()

        st.divider()

        # ── Current skills table with inline proficiency editing ─────
        if display["current_skills"]:
            st.subheader("Current Skills")
            st.caption(
                "Adjust proficiency levels if Claude's assessment doesn't "
                "match your experience, then click Save."
            )

            # Column headers
            h_name, h_prof, h_context = st.columns([2, 1, 4])
            h_name.markdown("**Skill**")
            h_prof.markdown("**Proficiency**")
            h_context.markdown("**Context**")

            # We work on a deep copy so edits don't silently mutate
            # session_state until the user explicitly saves.
            updated_profile = copy.deepcopy(st.session_state.profile)
            proficiency_changed = False

            for skill in display["current_skills"]:
                col_name, col_prof, col_context = st.columns([2, 1, 4])
                col_name.write(skill["name"])

                current_prof = skill.get("proficiency", "Basic")
                # Guard against unexpected values (e.g. hand-edited profile.json)
                # — list.index() raises ValueError if the value isn't found.
                safe_index = (
                    PROFICIENCY_LEVELS.index(current_prof)
                    if current_prof in PROFICIENCY_LEVELS
                    else PROFICIENCY_LEVELS.index("Basic")
                )
                new_prof = col_prof.selectbox(
                    label=skill["name"],
                    options=PROFICIENCY_LEVELS,
                    index=safe_index,
                    key=f"prof_current_{skill['name']}",
                    label_visibility="collapsed",
                )
                col_context.caption(skill.get("context", ""))

                if new_prof != current_prof:
                    proficiency_changed = True
                    for s in updated_profile.get("technical_skills", []):
                        if s["name"] == skill["name"]:
                            s["proficiency"] = new_prof
                            break

            if proficiency_changed:
                if st.button("💾 Save proficiency changes"):
                    save_profile(updated_profile, PROFILE_PATH)
                    st.session_state.profile = updated_profile
                    st.success("Saved.")
                    st.rerun()

        # ── Historical skills ────────────────────────────────────────
        if display["historical_skills"]:
            with st.expander(
                f"Historical Skills ({len(display['historical_skills'])})"
            ):
                for skill in display["historical_skills"]:
                    last = skill.get("last_used", "")
                    last_str = f" — last used {last}" if last else ""
                    st.write(
                        f"**{skill['name']}** "
                        f"({skill.get('proficiency', 'Basic')})"
                        f"{last_str}"
                    )
                    if skill.get("context"):
                        st.caption(skill["context"])

        col_left, col_right = st.columns(2)

        # ── Domain knowledge ─────────────────────────────────────────
        with col_left:
            if display["domain_knowledge"]:
                st.subheader("Domain Knowledge")
                for domain in display["domain_knowledge"]:
                    years = domain.get("years", 0)
                    years_str = (
                        f" — {years} yr{'s' if years != 1 else ''}" if years else ""
                    )
                    st.write(
                        f"**{domain.get('domain', '')}** "
                        f"({domain.get('depth', '')})"
                        f"{years_str}"
                    )
                    if domain.get("context"):
                        st.caption(domain["context"])

            # ── Soft skills ──────────────────────────────────────────
            if display["soft_skills"]:
                st.subheader("Soft Skills")
                st.write(", ".join(display["soft_skills"]))

        # ── Notable achievements ─────────────────────────────────────
        with col_right:
            if display["notable_achievements"]:
                st.subheader("Notable Achievements")
                for ach in display["notable_achievements"]:
                    st.write(f"• {ach}")

        # ── Source documents + base CV selection ─────────────────────
        if display["source_documents"]:
            st.divider()
            st.caption(f"Built from: {', '.join(display['source_documents'])}")

            st.session_state.base_cv_filename = st.selectbox(
                "📄 Which document is your main CV?",
                options=display["source_documents"],
                index=(
                    display["source_documents"].index(st.session_state.base_cv_filename)
                    if st.session_state.base_cv_filename in display["source_documents"]
                    else 0
                ),
                help="This document will be used as the base for tailoring.",
            )


# ═════════════════════════════════════════════
# TAB 2 — SEARCH JOBS
# ═════════════════════════════════════════════
with tab2:

    if not st.session_state.profile:
        st.warning(
            "👤 Build your profile first in the **My Profile** tab "
            "so results can be matched against your skills."
        )
        st.stop()

    # ── Search controls ──────────────────────────────────────────────
    st.subheader("Search Settings")
    col_title, col_market, col_num = st.columns([3, 2, 1])

    with col_title:
        job_title = st.text_input(
            "Job Title", placeholder="e.g. Python Developer"
        )
    with col_market:
        market = st.radio(
            "Market",
            options=get_market_options(),
            horizontal=True,
        )
    with col_num:
        num_results = st.slider("Results per source", 5, 30, 10)

    search_button = st.button(
        "🔍 Search & Match", type="primary"
    )
    st.divider()

    # ── Search + match loop ──────────────────────────────────────────
    if search_button:
        if not job_title:
            st.warning("Please enter a job title before searching.")
        else:
            with st.spinner(f"Fetching {job_title} roles in {market}…"):
                jobs = fetch_all_jobs(job_title, market, num_results)

            if jobs.empty:
                st.error("No jobs found. Try a different title or market.")
            else:
                st.success(
                    f"Found {len(jobs)} roles. Matching against your profile…"
                )

                progress_bar = st.progress(0)
                status = st.empty()
                match_results = []
                jobs_list = jobs.to_dict("records")
                total = len(jobs_list)

                for i, job in enumerate(jobs_list):
                    company = job.get("company") or "Unknown"
                    title = job.get("title") or "Role"
                    status.caption(
                        f"Matching {i + 1}/{total} — {title} at {company}"
                    )

                    result = match_job_to_profile(
                        st.session_state.profile, job
                    )
                    result["_job"] = job
                    match_results.append(result)
                    progress_bar.progress((i + 1) / total)

                progress_bar.empty()
                status.empty()

                # Sort: Strong → Potential → Weak
                label_order = {"Strong": 0, "Potential": 1, "Weak": 2}
                match_results.sort(
                    key=lambda r: label_order.get(r["match_label"], 3)
                )
                st.session_state.match_results = match_results

    # ── Results display ──────────────────────────────────────────────
    if st.session_state.match_results:
        results = st.session_state.match_results

        # Summary metrics
        counts = {
            label: sum(1 for r in results if r["match_label"] == label)
            for label in ["Strong", "Potential", "Weak"]
        }
        col_s, col_p, col_w, _ = st.columns([1, 1, 1, 3])
        col_s.metric("🟢 Strong", counts["Strong"])
        col_p.metric("🟡 Potential", counts["Potential"])
        col_w.metric("🔴 Weak", counts["Weak"])

        hide_weak = st.checkbox("Hide Weak matches", value=True)
        st.divider()

        filtered = [
            r for r in results
            if not (hide_weak and r["match_label"] == "Weak")
        ]

        if not filtered:
            st.info("No results to show. Uncheck 'Hide Weak matches' to see all.")

        for result in filtered:
            job = result["_job"]
            emoji = MATCH_LABEL_EMOJI.get(result["match_label"], "")
            location = job.get("location", "")
            location_str = f"  ·  {location}" if location else ""
            header = (
                f"{emoji} {result['match_score']}%  —  "
                f"{job.get('title', '')} at {job.get('company', '')}"
                f"{location_str}"
            )

            with st.expander(header):
                col_match, col_missing = st.columns(2)

                with col_match:
                    st.markdown("**✅ Matching skills**")
                    if result["matching_skills"]:
                        st.write(", ".join(result["matching_skills"]))
                    else:
                        st.caption("None identified")

                with col_missing:
                    st.markdown("**⚠️ Missing skills**")
                    if result["missing_skills"]:
                        st.write(", ".join(result["missing_skills"]))
                    else:
                        st.caption("None identified")

                if result.get("summary"):
                    st.write(result["summary"])

                if result.get("highlight_background"):
                    st.info(f"💡 {result['highlight_background']}")

                if result.get("reasoning"):
                    with st.expander("Full reasoning"):
                        st.write(result["reasoning"])

                job_key = f"{job.get('title', '')}_{job.get('company', '')}"

                col_link, col_save = st.columns([4, 1])
                with col_link:
                    job_url = job.get("job_url", "")
                    if job_url:
                        st.link_button("View Job Posting →", job_url)
                with col_save:
                    if st.button("🔖 Save", key=f"save_{job_key}"):
                        save_job({
                            "title": job.get("title", ""),
                            "company": job.get("company", ""),
                            "description": job.get("description", ""),
                            "job_url": job.get("job_url", ""),
                            "match_label": result["match_label"],
                            "match_score": result["match_score"],
                            "matching_skills": result.get("matching_skills", []),
                            "missing_skills": result.get("missing_skills", []),
                            "summary": result.get("summary", ""),
                            "highlight_background": result.get("highlight_background", ""),
                            "reasoning": result.get("reasoning", ""),
                            "source": "search",
                        }, SAVED_JOBS_PATH)
                        st.success("Saved to 🎯 Am I a good fit?")

                if st.button("🔍 Analyse Gaps", key=f"gap_{job_key}"):
                    _desc = job.get("description", "")
                    if not isinstance(_desc, str) or not _desc.strip():
                        # No description — store empty result so caption renders
                        st.session_state.gap_analysis_results[job_key] = {}
                    else:
                        with st.spinner("Analysing gaps for this role…"):
                            new_gap = analyse_gaps(st.session_state.profile, job)
                        if _has_gap_content(new_gap):
                            st.session_state.gap_analysis_results[job_key] = new_gap
                        else:
                            st.warning(
                                "Gap analysis returned no results — the API may be busy. "
                                "Try again in a moment."
                            )

                gap = st.session_state.gap_analysis_results.get(job_key)
                if gap is not None:
                    if _has_gap_content(gap):
                        st.divider()
                        st.markdown("**🔍 Gap Analysis**")
                        _render_gap_analysis(gap)
                    else:
                        st.caption(
                            "No job description available to analyse — visit the job posting "
                            "and paste the description into **🎯 Am I a good fit?** for a full gap analysis."
                        )

                _render_tailor_section(job, job_key, widget_prefix="t2_")
        
# ═════════════════════════════════════════════
# TAB 3 — AM I A GOOD FIT?
# ═════════════════════════════════════════════
with tab3:

    if not st.session_state.profile:
        st.warning(
            "👤 Build your profile first in the **My Profile** tab "
            "so roles can be matched against your skills."
        )
        st.stop()

    # ── Input form ───────────────────────────────────────────────────
    st.subheader("Analyse a Job")
    st.write(
        "Paste a URL or drop in the job description directly. "
        "Optionally add a title and company so your tailored CV is labelled correctly."
    )

    col_url, col_paste = st.columns(2)
    with col_url:
        url_input = st.text_input(
            "Job posting URL",
            placeholder="https://example.com/jobs/123",
        )
    with col_paste:
        paste_input = st.text_area(
            "Or paste the job description",
            height=120,
            placeholder="Paste the full job description here…",
        )

    col_title_in, col_company_in = st.columns(2)
    with col_title_in:
        title_input = st.text_input(
            "Job title (optional)",
            placeholder="e.g. Senior Python Developer",
        )
    with col_company_in:
        company_input = st.text_input(
            "Company (optional)",
            placeholder="e.g. Acme Corp",
        )

    if st.button("🎯 Analyse Fit", type="primary"):
        description = ""

        if url_input.strip():
            with st.spinner("Fetching job posting…"):
                description = fetch_job_from_url(url_input.strip())
            if not description:
                st.warning(
                    "Couldn't fetch that URL — the site may block automated requests "
                    "(LinkedIn, for example). Paste the job description in the box above instead."
                )

        if not description and paste_input.strip():
            description = paste_input.strip()

        if not description:
            st.error("Please provide a URL or paste a job description to continue.")
        else:
            job = {
                "title": title_input.strip() or "Unknown Role",
                "company": company_input.strip() or "Unknown Company",
                "description": description,
                "job_url": url_input.strip() if url_input.strip() else "",
                "source": "manual",
            }
            with st.spinner("Matching against your profile…"):
                result = match_job_to_profile(st.session_state.profile, job)
            result["_job"] = job
            st.session_state.fit_check_result = result

            fit_key = f"{job.get('title', '')}_{job.get('company', '')}"
            with st.spinner("Running deep gap analysis…"):
                gap = analyse_gaps(st.session_state.profile, job)
            st.session_state.gap_analysis_results[fit_key] = gap

    # ── Analysis result ───────────────────────────────────────────────
    if st.session_state.fit_check_result:
        result = st.session_state.fit_check_result
        job = result["_job"]
        fit_job_key = f"{job.get('title', '')}_{job.get('company', '')}"
        emoji = MATCH_LABEL_EMOJI.get(result["match_label"], "")

        st.divider()
        st.markdown(
            f"### {emoji} {result['match_label']} Match — {result['match_score']}%"
        )
        st.markdown(
            f"**{job.get('title', 'Unknown Role')}** at **{job.get('company', 'Unknown Company')}**"
        )

        col_match, col_missing = st.columns(2)
        with col_match:
            st.markdown("**✅ Matching skills**")
            skills = result.get("matching_skills", [])
            st.write(", ".join(skills) if skills else "None identified")
        with col_missing:
            st.markdown("**⚠️ Missing skills**")
            missing = result.get("missing_skills", [])
            st.write(", ".join(missing) if missing else "None identified")

        if result.get("summary"):
            st.write(result["summary"])

        if result.get("highlight_background"):
            st.info(f"💡 {result['highlight_background']}")

        if result.get("reasoning"):
            with st.expander("Full reasoning"):
                st.write(result["reasoning"])

        col_link_fit, col_save_fit = st.columns([4, 1])
        with col_link_fit:
            if job.get("job_url"):
                st.link_button("View Job Posting →", job["job_url"])
        with col_save_fit:
            if st.button("🔖 Save this job", key="save_fit_check"):
                save_job({
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "description": job.get("description", ""),
                    "job_url": job.get("job_url", ""),
                    "match_label": result["match_label"],
                    "match_score": result["match_score"],
                    "matching_skills": result.get("matching_skills", []),
                    "missing_skills": result.get("missing_skills", []),
                    "summary": result.get("summary", ""),
                    "highlight_background": result.get("highlight_background", ""),
                    "reasoning": result.get("reasoning", ""),
                    "source": "manual",
                }, SAVED_JOBS_PATH)
                st.success("Saved!")

        if st.button("🔍 Analyse Gaps", key=f"gap_fit_{fit_job_key}"):
            with st.spinner("Analysing gaps for this role…"):
                new_gap = analyse_gaps(st.session_state.profile, job)
            if _has_gap_content(new_gap):
                st.session_state.gap_analysis_results[fit_job_key] = new_gap
            else:
                st.warning(
                    "Gap analysis returned no results — the API may be busy. "
                    "Try again in a moment."
                )

        fit_gap = st.session_state.gap_analysis_results.get(fit_job_key)
        if fit_gap is not None:
            if _has_gap_content(fit_gap):
                st.divider()
                st.markdown("**🔍 Gap Analysis**")
                _render_gap_analysis(fit_gap)
            else:
                st.caption(
                    "No description content to analyse — paste the full job description "
                    "above and click **🎯 Analyse Fit** again for a gap analysis."
                )

        _render_tailor_section(job, fit_job_key, widget_prefix="t3_fit_")

    # ── Saved jobs list ───────────────────────────────────────────────
    st.divider()
    saved = load_saved_jobs(SAVED_JOBS_PATH)

    if not saved:
        st.info(
            "No saved jobs yet. Click **🔖 Save** on any job card — "
            "from search results or after analysing a URL above — to build your list here."
        )
    else:
        st.subheader(f"Saved Jobs ({len(saved)})")

        for saved_job in saved:
            sj_key = f"{saved_job.get('title', '')}_{saved_job.get('company', '')}"
            sj_emoji = MATCH_LABEL_EMOJI.get(saved_job.get("match_label", ""), "")
            sj_score = saved_job.get("match_score", "")
            source_badge = "🔍" if saved_job.get("source") == "search" else "🔗"
            sj_header = (
                f"{sj_emoji} {sj_score}%  —  "
                f"{saved_job.get('title', 'Unknown')} at {saved_job.get('company', 'Unknown')} "
                f"{source_badge}"
            )

            with st.expander(sj_header):
                col_match, col_missing = st.columns(2)
                with col_match:
                    st.markdown("**✅ Matching skills**")
                    skills = saved_job.get("matching_skills", [])
                    st.write(", ".join(skills) if skills else "None identified")
                with col_missing:
                    st.markdown("**⚠️ Missing skills**")
                    missing = saved_job.get("missing_skills", [])
                    st.write(", ".join(missing) if missing else "None identified")

                if saved_job.get("summary"):
                    st.write(saved_job["summary"])

                if saved_job.get("highlight_background"):
                    st.info(f"💡 {saved_job['highlight_background']}")

                if saved_job.get("reasoning"):
                    with st.expander("Full reasoning"):
                        st.write(saved_job["reasoning"])

                col_link_sj, col_remove = st.columns([4, 1])
                with col_link_sj:
                    if saved_job.get("job_url"):
                        st.link_button("View Job Posting →", saved_job["job_url"])
                with col_remove:
                    if st.button("🗑 Remove", key=f"remove_{sj_key}"):
                        remove_saved_job(sj_key, SAVED_JOBS_PATH)
                        st.rerun()

                if st.button("🔍 Analyse Gaps", key=f"gap_saved_{sj_key}"):
                    _sj_desc = saved_job.get("description", "")
                    if not isinstance(_sj_desc, str) or not _sj_desc.strip():
                        # No description — store empty result so caption renders
                        st.session_state.gap_analysis_results[sj_key] = {}
                    else:
                        with st.spinner("Analysing gaps for this role…"):
                            new_sj_gap = analyse_gaps(st.session_state.profile, saved_job)
                        if _has_gap_content(new_sj_gap):
                            st.session_state.gap_analysis_results[sj_key] = new_sj_gap
                        else:
                            st.warning(
                                "Gap analysis returned no results — the API may be busy. "
                                "Try again in a moment."
                            )

                sj_gap = st.session_state.gap_analysis_results.get(sj_key)
                if sj_gap is not None:
                    if _has_gap_content(sj_gap):
                        st.divider()
                        st.markdown("**🔍 Gap Analysis**")
                        _render_gap_analysis(sj_gap)
                    else:
                        st.caption(
                            "No job description available to analyse — paste the description "
                            "into **🎯 Am I a good fit?** above for a full gap analysis."
                        )

                _render_tailor_section(saved_job, sj_key, widget_prefix="t3_saved_")
