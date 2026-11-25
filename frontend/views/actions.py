"""Review, edit, approve, and execute follow-up actions."""

import streamlit as st

from frontend.client import api


def render():
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
