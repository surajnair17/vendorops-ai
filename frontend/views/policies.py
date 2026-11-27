"""Maintain policy evidence and human-confirmed business rules."""

import streamlit as st

from frontend.client import api


def render():
    st.header("Policies and confirmed rules")
    metrics = api("GET", "/metrics")
    if metrics and metrics["provider"] == "bedrock":
        st.caption("Titan embeddings retrieve source passages. Python applies confirmed rules.")
    else:
        st.caption(
            "Fixture retrieval is lexical test plumbing. It does not measure semantic accuracy."
        )
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
