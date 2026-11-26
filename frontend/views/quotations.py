"""Review limited, deterministic quotation assessments."""

from datetime import date

import streamlit as st

from frontend.client import api


def check_label(field: str) -> str:
    if field.startswith("items."):
        return f"Line {int(field.split('.')[1]) + 1} total"
    return field.replace("_", " ").capitalize()


def render():
    st.header("Quotation review")
    st.caption(
        "Check stated dates and amounts. Results do not approve a purchase, determine tax law, "
        "or rank suppliers. Unknown inputs remain review requirements."
    )
    records = api("GET", "/documents") or []
    quotes = [r for r in records if r["summary"]["document_type"] == "quotation"]
    if not quotes:
        st.info(
            "Store a quotation in Documents, then extract a generated sample or save manually "
            "reviewed fields. Try backend/artifacts/samples/quotations/Q-TERMS-001.pdf."
        )
        return
    labels = {r["id"]: f"{r['data']['filename']} / {r['id'][:8]}" for r in quotes}
    selected = st.selectbox("Quotation", list(labels), format_func=labels.get)
    record = api("GET", f"/documents/{selected}")
    if not record:
        return
    revision = next(r for r in record["revisions"] if r["id"] == record["data"]["revision_id"])
    values = revision["data"]["structured"]
    st.caption(f"Record provider: {revision['data']['provider']} / revision {revision['id'][:8]}")
    left, right = st.columns(2)
    left.metric("Valid until", values.get("valid_until") or "Unknown")
    right.metric("Stated total", f"{values.get('currency') or '?'} {values.get('total') or '?'}")
    st.write("Payment terms:", values.get("payment_terms") or "Unknown")
    with st.expander("Source text and reviewed fields"):
        st.text("\n\n".join(record["data"]["pages"]))
        st.json(values)
    as_of = st.date_input("Assess as of", value=date.today())
    if st.button("Assess quotation"):
        if api(
            "POST",
            f"/documents/{selected}/quote-assessments",
            json={"expected_revision_id": revision["id"], "as_of": as_of.isoformat()},
        ):
            st.success("Assessment saved for this exact revision.")
    reports = api("GET", f"/documents/{selected}/quote-assessments") or []
    for report in reversed(reports):
        result = report["data"]
        with st.expander(
            f"{result['as_of']} / {result['status']}" + (" / STALE" if report["stale"] else ""),
            expanded=report == reports[-1],
        ):
            if report["stale"]:
                st.warning("Fields changed after this assessment. Run a new assessment.")
            if result["status"] == "checks_passed":
                st.success("Supported checks passed. This is not purchase approval.")
            for finding in result["findings"]:
                st.warning(f"{check_label(finding['field'])}: {finding['message']}")
                if finding["expected"] is not None:
                    st.write(
                        {
                            "expected": finding["expected"],
                            "actual": finding["actual"],
                            "difference": finding["difference"],
                        }
                    )
                for evidence in finding["evidence"]:
                    st.caption(f"Page {evidence['page']}: {evidence['quote']}")
            st.markdown("**Checks performed**")
            rows = ["| Check | Result | Expected | Stated |", "| --- | --- | --- | --- |"]
            for check in result["checks"]:
                rows.append(
                    f"| {check_label(check['field'])} | {check['status'].capitalize()} | "
                    f"{check.get('expected', '-')} | {check.get('actual', '-')} |"
                )
                if check.get("reason"):
                    st.caption(f"{check_label(check['field'])}: {check['reason']}")
            st.markdown("\n".join(rows))
            with st.expander("Full assessment record"):
                st.json(report)
