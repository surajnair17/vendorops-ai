import json

import streamlit as st

from frontend.client import api


def actions():
    st.header("Review and approve follow-up actions")
    reports = api("GET", "/comparisons") or []
    contacts = api("GET", "/contacts") or []
    current_reports = [r for r in reports if not r["stale"]]
    if current_reports and contacts:
        with st.form("draft_action"):
            report = st.selectbox("Comparison report", [r["id"] for r in current_reports])
            assessment = st.text_input(
                "Policy assessment ID (optional)",
                help="Saved assessment IDs are shown on the Compare screen.",
            )
            recipient = st.selectbox("Test recipient", contacts)
            kind = st.selectbox(
                "Action", ["clarification", "corrected_invoice", "internal_escalation"]
            )
            mode = st.selectbox("Delivery mode", ["simulated", "ses"])
            if st.form_submit_button("Create draft"):
                api(
                    "POST",
                    "/actions",
                    json={
                        "comparison_id": report,
                        "assessment_id": assessment or None,
                        "recipient": recipient,
                        "action_type": kind,
                        "delivery_mode": mode,
                    },
                )
    for action in api("GET", "/actions") or []:
        data = action["data"]
        with st.expander(f"{data['subject']} · {data['state']} · {action['id'][:8]}"):
            st.write(f"To: {data['recipient']} | Delivery: {data['delivery_mode']}")
            st.text(data["body"])
            st.caption(
                f"Content revision {data['content_revision']} · Report {data['comparison_id']}"
            )
            supporting_report = next((r for r in reports if r["id"] == data["comparison_id"]), None)
            if supporting_report:
                if supporting_report["stale"]:
                    st.warning("The source documents changed. Create a fresh comparison and draft.")
                st.write("Supporting findings")
                st.json(supporting_report["data"]["findings"])
                if data.get("assessment_id"):
                    assessments = (
                        api("GET", f"/comparisons/{data['comparison_id']}/policy-assessments") or []
                    )
                    assessment_record = next(
                        (a for a in assessments if a["id"] == data["assessment_id"]), None
                    )
                    if assessment_record:
                        st.write("Policy evidence reviewed with this draft")
                        st.json(assessment_record["data"])
            if st.button("Load revision and approval history", key=f"history-{action['id']}"):
                detail = api("GET", f"/actions/{action['id']}")
                if detail:
                    st.json(detail["history"])
            expected = {"expected_version": action["version"]}
            if data["state"] in {"draft", "pending_review", "approved", "rejected", "failed"}:
                with st.form(f"edit-{action['id']}"):
                    subject = st.text_input("Subject", data["subject"])
                    body = st.text_area("Body", data["body"])
                    if st.form_submit_button("Save edit and invalidate approval"):
                        if api(
                            "PATCH",
                            f"/actions/{action['id']}",
                            json={
                                **expected,
                                "recipient": data["recipient"],
                                "subject": subject,
                                "body": body,
                            },
                        ):
                            st.rerun()
            if data["state"] == "draft" and st.button(
                "Submit for review", key=f"review-{action['id']}"
            ):
                if api("POST", f"/actions/{action['id']}/request-review", json=expected):
                    st.rerun()
            if data["state"] == "pending_review":
                for decision in ("approve", "reject"):
                    if st.button(
                        decision.title() + " exact revision", key=f"{decision}-{action['id']}"
                    ):
                        if api(
                            "POST",
                            f"/actions/{action['id']}/review",
                            json={**expected, "decision": decision},
                        ):
                            st.rerun()
            if data["state"] == "approved" and st.button(
                "Execute approved action", key=f"execute-{action['id']}"
            ):
                if api("POST", f"/actions/{action['id']}/execute", json=expected):
                    st.rerun()
            if data["job_id"]:
                st.json(api("GET", f"/jobs/{data['job_id']}"))
            if data["state"] == "unknown":
                with st.form(f"reconcile-{action['id']}"):
                    outcome = st.selectbox("Verified delivery outcome", ["sent", "not_sent"])
                    evidence = st.text_input("Evidence used to verify delivery")
                    if st.form_submit_button("Record reconciliation"):
                        if api(
                            "POST",
                            f"/actions/{action['id']}/reconcile",
                            json={**expected, "outcome": outcome, "evidence": evidence},
                        ):
                            st.rerun()
    if st.button("Refresh action status"):
        st.rerun()
    with st.expander("Audit history"):
        if st.button("Load audit events"):
            st.json(api("GET", "/audit"))


def policies():
    st.header("Policies and confirmed rules")
    st.caption("Fixture retrieval is lexical test plumbing. It does not measure semantic accuracy.")
    with st.form("policy_upload"):
        name = st.text_input("Policy name", "Purchasing")
        version = st.text_input("Policy version", "1")
        effective = st.date_input("Effective date")
        text = st.text_area("Policy text", "Invoice price variance up to 10 percent is permitted.")
        pdf = st.file_uploader("Or upload a policy PDF", type=["pdf"])
        if st.form_submit_button("Save and index inactive policy"):
            if pdf is not None:
                api(
                    "POST",
                    "/policies/pdf",
                    params={
                        "name": name,
                        "policy_version": version,
                        "effective_date": effective.isoformat(),
                    },
                    files={"file": (pdf.name, pdf.getvalue())},
                )
            else:
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
            if st.button("Rebuild index", key=f"reindex-{policy['id']}"):
                if api("POST", f"/policies/{policy['id']}/reindex"):
                    st.rerun()
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
            currency = st.text_input("Currency for invoice-value thresholds", "USD")
            if st.form_submit_button("Save unconfirmed rule"):
                api(
                    "POST",
                    "/rules",
                    json={
                        "policy_id": selected,
                        "chunk_id": chunk,
                        "rule_type": kind,
                        "value": value,
                        "currency": currency if kind == "invoice_value_threshold" else None,
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


def operations():
    st.header("Operational metrics")
    if metrics := api("GET", "/metrics"):
        st.write(f"Provider: {metrics['provider']} · Operator: {metrics['operator']}")
        st.metric("Documents", metrics["documents"])
        st.json(metrics)
    st.info(
        "Run python -m backend.worker in a third terminal to process queued actions. "
        "Usage counts do not establish live accuracy or represent a cloud bill."
    )
    if st.button("Refresh metrics"):
        st.rerun()
