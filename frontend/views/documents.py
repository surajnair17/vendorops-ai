"""Upload documents and review revisioned structured data."""

import json

import streamlit as st

from frontend.client import api


def render():
    st.header("Document workspace")
    st.caption(
        "Fixture mode handles exact generated samples only. Corrections create new revisions."
    )
    uploaded = st.file_uploader("Store a PDF for review", type=["pdf"], key="stored_upload")
    if st.button("Store document", disabled=uploaded is None):
        if api("POST", "/documents", files={"file": (uploaded.name, uploaded.getvalue())}):
            st.success("Document stored")
    records = api("GET", "/documents") or []
    if not records:
        st.info(
            "Generate sample PDFs with python -m backend.scripts.generate_samples, then upload one."
        )
        return
    labels = {r["id"]: f"{r['data']['filename']} · {r['id'][:8]}" for r in records}
    selected = st.selectbox("Document", list(labels), format_func=labels.get)
    record = api("GET", f"/documents/{selected}")
    if not record:
        return
    if record["data"]["duplicate_of"]:
        st.warning("This file duplicates an existing upload. Review before comparing.")
    left, right = st.columns(2)
    with left:
        st.subheader("Source text")
        st.text_area(
            "Pages",
            "\n\n".join(record["data"]["pages"]),
            height=350,
            key=f"source-{selected}-{record['version']}",
        )
        if st.button("Extract structured data"):
            with st.spinner("Extracting…"):
                if api("POST", f"/documents/{selected}/structure"):
                    st.rerun()
        if st.button("Request OCR for scanned pages"):
            if job := api("POST", f"/documents/{selected}/ocr"):
                st.session_state["ocr_job"] = job["job_id"]
        if jobs := api("GET", "/jobs", params={"document_id": selected}):
            st.json(jobs)
            if st.button("Refresh OCR status"):
                st.rerun()
    with right:
        st.subheader("Structured data and corrections")
        if record["data"]["revision_id"]:
            current = next(
                r for r in record["revisions"] if r["id"] == record["data"]["revision_id"]
            )
            st.write(f"Provider: {current['data']['provider']}")
            for issue in current["data"]["issues"]:
                st.warning(issue)
            edited = st.text_area(
                "Editable structured JSON",
                json.dumps(current["data"]["structured"], indent=2),
                height=350,
                key=f"edit-{current['id']}",
            )
            if st.button("Save corrected revision"):
                try:
                    payload = {
                        "expected_revision_id": current["id"],
                        "structured": json.loads(edited),
                    }
                    if api("PATCH", f"/documents/{selected}/structured-data", json=payload):
                        st.rerun()
                except ValueError:
                    st.error("Enter valid JSON before saving.")
            with st.expander("Revision history"):
                st.json(record["revisions"])
        with st.expander("Extraction attempt history"):
            st.json(record.get("extraction_attempts", []))
