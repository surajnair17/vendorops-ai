import json

import streamlit as st

from frontend.client import api


def comparisons():
    st.header("Compare an invoice with a purchase order")
    records = api("GET", "/documents") or []
    ready = [r for r in records if r["data"]["revision_id"]]
    if not ready:
        st.info("Upload and structure documents first.")
        return
    labels = {r["id"]: f"{r['data']['filename']} · {r['id'][:8]}" for r in ready}
    invoice = st.selectbox("Invoice", list(labels), format_func=labels.get)
    if st.button("Find purchase orders"):
        result = api("GET", f"/documents/{invoice}/match-candidates")
        if result:
            st.json(result)
    po = st.selectbox("Purchase order", ["Automatic", *labels], format_func=lambda x: labels.get(x, x))
    mapping = st.text_input("Optional line mapping JSON (zero-based invoice index to PO index)", "")
    if st.button("Compare documents"):
        try:
            payload = {"invoice_id": invoice, "po_id": None if po == "Automatic" else po,
                       "line_mapping": json.loads(mapping) if mapping else None}
            if result := api("POST", "/comparisons", json=payload):
                st.json(result)
        except ValueError:
            st.error("The line mapping must be valid JSON.")
    with st.expander("Confirmed supplier aliases"):
        alias = st.text_input("Supplier alias")
        canonical = st.text_input("Canonical supplier")
        if st.button("Confirm alias"):
            api("POST", "/supplier-aliases", json={"alias": alias, "canonical": canonical})
    st.subheader("Reports")
    for report in api("GET", "/comparisons") or []:
        with st.expander(f"{report['id'][:8]} · {report['data']['status']}" + (" · STALE" if report["stale"] else "")):
            st.json(report)


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
