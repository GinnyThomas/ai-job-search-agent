import copy
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from agents.job_fetcher import fetch_all_jobs, get_market_options
from agents.job_matcher import match_job_to_profile
from agents.profile_builder import (
    build_profile,
    save_profile,
    load_profile,
    format_profile_for_display,
    PROFICIENCY_LEVELS,
)

load_dotenv()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
PROFILE_PATH = "data/profile.json"
SOURCE_DOCS_DIR = "data/source_documents"

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
tab1, tab2 = st.tabs(["👤 My Profile", "🔍 Search Jobs"])


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

        st.success("Profile built and saved.")
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
                new_prof = col_prof.selectbox(
                    label=skill["name"],
                    options=PROFICIENCY_LEVELS,
                    index=PROFICIENCY_LEVELS.index(current_prof),
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

        # ── Source documents ─────────────────────────────────────────
        if display["source_documents"]:
            st.divider()
            st.caption(f"Built from: {', '.join(display['source_documents'])}")


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

                job_url = job.get("job_url", "")
                if job_url:
                    st.link_button("View Job Posting →", job_url)
