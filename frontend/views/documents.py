"""Upload documents and review revisioned structured data."""

import json

import streamlit as st

from frontend.client import api


def review_editor(record: dict):
    current = next(
        (r for r in record["revisions"] if r["id"] == record["data"]["revision_id"]), None
    )
    structured = current["data"]["structured"] if current else None
    if current:
        st.write(f"Provider: {current['data']['provider']}")
        for issue in current["data"]["issues"]:
            st.warning(issue)
    if structured is None:
        st.info(
            "No usable extraction yet. Enter fields reviewed against the original PDF. "
            "This creates a human record and makes no AI call. Leave unknown values null."
        )
        structured = {
            "document_type": "quotation",
            "supplier": None,
            "document_number": None,
            "document_date": None,
            "valid_until": None,
            "payment_terms": None,
            "currency": None,
            "items": [],
            "subtotal": None,
            "discount": None,
            "taxable_amount": None,
            "tax_rate_percent": None,
            "tax": None,
            "freight": None,
            "total": None,
            "evidence": {},
        }
    st.caption(
        "Money and quantities use decimal strings. Evidence format: "
        '"total": {"page": 1, "quote": "Total: 315.63"}. '
        "Citations must match source text; check OCR numbers against the original PDF."
    )
    edited = st.text_area(
        "Editable structured JSON",
        json.dumps(structured, indent=2),
        height=420,
        key=f"edit-{record['id']}-{record['version']}",
    )
    if st.button("Save corrected revision" if current else "Save initial reviewed record"):
        try:
            payload = {
                "expected_revision_id": record["data"]["revision_id"],
                "expected_document_version": record["version"],
                "structured": json.loads(edited),
            }
            if api("PATCH", f"/documents/{record['id']}/structured-data", json=payload):
                st.rerun()
        except ValueError:
            st.error("Enter valid JSON before saving.")


def render():
    st.header("Document workspace")
    mode = api("GET", "/metrics")
    if mode:
        st.caption(
            f"Extraction provider: {mode['provider']}. "
            "Fixture mode handles exact samples only; reviewed fields can be entered manually."
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
        review_editor(record)
        with st.expander("Revision history"):
            st.json(record["revisions"])
        with st.expander("Extraction attempt history"):
            st.json(record.get("extraction_attempts", []))
