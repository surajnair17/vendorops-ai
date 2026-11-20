import json

import streamlit as st

from frontend.client import api


def documents():
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
        st.info("Generate sample PDFs with python -m scripts.generate_samples, then upload one.")
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
    with right:
        st.subheader("Structured data and corrections")
        if record["revisions"]:
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
