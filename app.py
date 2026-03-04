import streamlit as st
from dotenv import load_dotenv
from agents.job_fetcher import fetch_all_jobs, get_market_options

# Load environment variables from .env file
load_dotenv()

# --- Page Configuration ---
st.set_page_config(
    page_title="AI Job Search Agent",
    page_icon="🔍",
    layout="wide"
)

# --- Header ---
st.title("🔍 AI Job Search Agent")
st.subheader("Find the right roles. Apply with confidence.")
st.divider()

# --- Sidebar ---
with st.sidebar:
    st.header("Search Settings")
    job_title = st.text_input("Job Title", placeholder="e.g. Python Developer")

    market = st.radio(
        "Market",
        options=get_market_options(),
        help="Choose where to search for jobs"
    )

    num_results = st.slider("Results per source", 5, 50, 20)
    search_button = st.button("🔍 Search Jobs", use_container_width=True)

# --- Main Area ---
if not search_button:
    st.info("👈 Enter a job title, choose your market, then click Search Jobs.")
else:
    if not job_title:
        st.warning("Please enter a job title before searching.")
    else:
        with st.spinner(f"Searching for {job_title} roles in {market}..."):
            jobs = fetch_all_jobs(job_title, market, num_results)

        if jobs.empty:
            st.error("No jobs found. Try a different title or market.")
        else:
            st.success(f"Found {len(jobs)} roles in **{market}**")

            # Display results as a table for now
            # We'll add matching scores and gap analysis in the next session
            display_cols = ["title", "company", "location", "date_posted", "job_url", "source"]
            available_cols = [c for c in display_cols if c in jobs.columns]
            st.dataframe(jobs[available_cols], use_container_width=True)
