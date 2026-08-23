"""
RM Student Data Pipeline & UI
==============================
Streamlit application for the DTU CDIE Recruitment Manager technical
assessment.

Run locally:
    streamlit run app.py
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from src.cleaning import clean_dataframe

st.set_page_config(
    page_title="RM Student Data Pipeline",
    page_icon="🎓",
    layout="wide",
)

# ----------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------
if "clean_df" not in st.session_state:
    st.session_state.clean_df = None
if "report" not in st.session_state:
    st.session_state.report = None
if "load_seconds" not in st.session_state:
    st.session_state.load_seconds = None


def load_and_clean(raw_df: pd.DataFrame) -> None:
    start = time.perf_counter()
    clean_df, report = clean_dataframe(raw_df)
    st.session_state.load_seconds = round(time.perf_counter() - start, 3)
    st.session_state.clean_df = clean_df
    st.session_state.report = report


# ----------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------
st.title("🎓 RM Student Data Pipeline & UI")
st.caption(
    "Upload a raw student CSV → auto-clean → filter, toggle Active/Debarred "
    "status, and export a live shortlist."
)

# ----------------------------------------------------------------------
# 1. Upload
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("1. Upload dataset")
    uploaded = st.file_uploader("Raw student CSV", type=["csv"])
    use_sample = st.button("Use bundled sample dataset", use_container_width=True)

    if uploaded is not None:
        try:
            raw_df = pd.read_csv(uploaded)
            load_and_clean(raw_df)
            st.success(f"Loaded {len(raw_df)} rows from **{uploaded.name}**.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not process file: {exc}")

    if use_sample:
        try:
            raw_df = pd.read_csv("data/sample_students_raw.csv")
            load_and_clean(raw_df)
            st.success(f"Loaded {len(raw_df)} rows from bundled sample dataset.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load sample dataset: {exc}")

if st.session_state.clean_df is None:
    st.info("⬅️ Upload a CSV or click **Use bundled sample dataset** in the sidebar to begin.")
    st.stop()

clean_df: pd.DataFrame = st.session_state.clean_df
report = st.session_state.report

# ----------------------------------------------------------------------
# 2. Cleaning report
# ----------------------------------------------------------------------
with st.expander("🧹 Data cleaning report", expanded=False):
    st.caption(f"Pipeline ran in **{st.session_state.load_seconds}s**.")
    cols = st.columns(4)
    stats = report.as_dict()
    for i, (label, value) in enumerate(stats.items()):
        cols[i % 4].metric(label, value)
    if report.duplicate_groups:
        st.markdown(
            "**Name/Gender/Grade collisions reviewed** "
            "(merged only when scores were near-identical; otherwise kept as distinct students):"
        )
        st.dataframe(pd.DataFrame(report.duplicate_groups), use_container_width=True, hide_index=True)
    st.markdown("**Notes:**")
    for note in report.notes:
        st.markdown(f"- {note}")

# ----------------------------------------------------------------------
# 3. Active / Debarred status editor (real-time)
# ----------------------------------------------------------------------
st.subheader("2. Student roster — toggle Active / Debarred status")
st.caption("Debarred students are immediately excluded from the shortlist below.")

edited_df = st.data_editor(
    clean_df,
    key="roster_editor",
    use_container_width=True,
    hide_index=True,
    disabled=["StudentID", "Name", "Gender", "Grade", "Math", "Science", "English", "Total"],
    column_config={
        "Status": st.column_config.SelectboxColumn(
            "Status",
            options=["Active", "Debarred"],
            required=True,
        )
    },
)
# Persist edits back so toggles survive reruns/filter changes.
st.session_state.clean_df = edited_df

# ----------------------------------------------------------------------
# 4. Live shortlist filter
# ----------------------------------------------------------------------
st.subheader("3. Shortlist")

min_total = int(edited_df["Total"].min()) if len(edited_df) else 0
max_total = int(edited_df["Total"].max()) if len(edited_df) else 0

threshold = st.slider(
    "Minimum Total Score",
    min_value=min_total,
    max_value=max_total,
    value=min_total,
    step=1,
)

active_df = edited_df[edited_df["Status"] == "Active"]
shortlist = active_df[active_df["Total"] >= threshold].sort_values("Total", ascending=False)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Shortlisted", len(shortlist))
m2.metric("Debarred (excluded)", int((edited_df["Status"] == "Debarred").sum()))
m3.metric("Avg Total", round(shortlist["Total"].mean(), 1) if len(shortlist) else 0)
m4.metric("Max Total", int(shortlist["Total"].max()) if len(shortlist) else 0)
m5.metric("Min Total", int(shortlist["Total"].min()) if len(shortlist) else 0)

st.dataframe(shortlist, use_container_width=True, hide_index=True)

st.download_button(
    "⬇️ Export shortlist as CSV",
    data=shortlist.to_csv(index=False).encode("utf-8"),
    file_name="shortlist.csv",
    mime="text/csv",
    use_container_width=True,
)

st.divider()
st.caption(
    "Built for the DTU CDIE Recruitment Manager (RM) Portal technical assessment. "
    "See README.md for setup instructions and cleaning logic."
)
