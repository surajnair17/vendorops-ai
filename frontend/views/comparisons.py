"""Compare invoices against purchase orders and inspect findings."""

import json

import streamlit as st

from frontend.client import api


def render():
    st.header("Compare an invoice with a purchase order")
    records = api("GET", "/documents") or []
    invoices = [r for r in records if r.get("summary", {}).get("document_type") == "invoice"]
    orders = [r for r in records if r.get("summary", {}).get("document_type") == "purchase_order"]
    if not invoices or not orders:
        st.info("Upload and structure an invoice and a purchase order first.")
        return
    labels = {r["id"]: f"{r['data']['filename']} · {r['id'][:8]}" for r in invoices + orders}
    invoice = st.selectbox("Invoice", [r["id"] for r in invoices], format_func=labels.get)
    if st.button("Find purchase orders"):
        result = api("GET", f"/documents/{invoice}/match-candidates")
        if result:
            st.json(result)
    po = st.selectbox(
        "Purchase order",
        ["Automatic", *[r["id"] for r in orders]],
        format_func=lambda x: labels.get(x, x),
    )
    mapping = st.text_input("Optional line mapping JSON (zero-based invoice index to PO index)", "")
    if st.button("Compare documents"):
        try:
            payload = {
                "invoice_id": invoice,
                "po_id": None if po == "Automatic" else po,
                "line_mapping": json.loads(mapping) if mapping else None,
            }
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
        with st.expander(
            f"{report['id'][:8]} · {report['data']['status']}"
            + (" · STALE" if report["stale"] else "")
        ):
            st.json(report)
            if st.button("Assess policy", key=f"assess-{report['id']}"):
                if result := api("POST", f"/comparisons/{report['id']}/policy-assessments"):
                    st.json(result)
            for assessment in api("GET", f"/comparisons/{report['id']}/policy-assessments") or []:
                st.caption(f"Saved policy assessment: {assessment['id']}")
                st.json(assessment["data"])
