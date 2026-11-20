import json

import streamlit as st

from frontend.client import api


def policies():
    st.header("Policies and confirmed rules")
    st.caption("Fixture retrieval is lexical test plumbing. It does not measure semantic accuracy.")
    with st.form("policy_upload"):
        name = st.text_input("Policy name", "Purchasing")
        version = st.text_input("Policy version", "1")
        effective = st.date_input("Effective date")
        text = st.text_area("Policy text", "Invoice price variance up to 10 percent is permitted.")
        if st.form_submit_button("Save and index inactive policy"):
            api(
                "POST",
                "/policies",
                json={
                    "name": name,
                    "policy_version": version,
                    "effective_date": effective.isoformat(),
                    "text": text,
                },
            )
    records = api("GET", "/policies") or []
    for policy in records:
        with st.expander(
            f"{policy['data']['name']} v{policy['data']['policy_version']}"
            f" · active={policy['data']['active']}"
        ):
            st.json(policy)
            if st.button("Toggle activation", key=f"activate-{policy['id']}"):
                if api(
                    "POST",
                    f"/policies/{policy['id']}/activate",
                    json={
                        "active": not policy["data"]["active"],
                        "expected_version": policy["version"],
                    },
                ):
                    st.rerun()
    if records:
        with st.form("rule"):
            selected = st.selectbox("Source policy", [r["id"] for r in records])
            chunk = st.text_input("Source chunk ID", "p1-c1")
            kind = st.selectbox(
                "Rule type",
                [
                    "price_variance_percent",
                    "quantity_overage_percent",
                    "required_field",
                    "invoice_value_threshold",
                ],
            )
            value = st.text_input("Rule value", "10")
            if st.form_submit_button("Save unconfirmed rule"):
                api(
                    "POST",
                    "/rules",
                    json={
                        "policy_id": selected,
                        "chunk_id": chunk,
                        "rule_type": kind,
                        "value": value,
                    },
                )
    for rule in api("GET", "/rules") or []:
        st.json(rule)
        if st.button("Confirm / revoke this rule", key=f"confirm-{rule['id']}"):
            if api(
                "POST",
                f"/rules/{rule['id']}/confirm",
                json={"active": not rule["data"]["confirmed"], "expected_version": rule["version"]},
            ):
                st.rerun()


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
    po = st.selectbox(
        "Purchase order", ["Automatic", *labels], format_func=lambda x: labels.get(x, x)
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
