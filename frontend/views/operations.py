"""Inspect application mode, usage, and durable job outcomes."""

import streamlit as st

from frontend.client import api


def render():
    st.header("Operational metrics")
    if metrics := api("GET", "/metrics"):
        st.caption(f"Provider: {metrics['provider']} · Operator: {metrics['operator']}")
        columns = st.columns(4)
        columns[0].metric("Documents", metrics["documents"])
        columns[1].metric("Actions", sum(metrics["action_states"].values()))
        columns[2].metric(
            "Active jobs",
            sum(
                metrics["job_statuses"].get(state, 0)
                for state in ("queued", "starting", "waiting", "running")
            ),
        )
        columns[3].metric("Completed jobs", metrics["job_statuses"].get("succeeded", 0))
        left, right = st.columns(2)
        with left:
            st.subheader("Action states")
            if metrics["action_states"]:
                st.markdown(
                    "| State | Count |\n| :--- | ---: |\n"
                    + "\n".join(
                        f"| {state} | {count} |"
                        for state, count in metrics["action_states"].items()
                    )
                )
            else:
                st.info("No follow-up actions yet.")
        with right:
            st.subheader("Job outcomes")
            if metrics["job_statuses"]:
                st.markdown(
                    "| Status | Count |\n| :--- | ---: |\n"
                    + "\n".join(
                        f"| {status} | {count} |"
                        for status, count in metrics["job_statuses"].items()
                    )
                )
            else:
                st.info("No background jobs yet.")
        with st.expander("Processing configuration and usage"):
            st.json(metrics)
    st.info(
        "Run python -m backend.worker in a third terminal to process queued actions. "
        "Usage counts do not establish live accuracy or represent a cloud bill."
    )
    if st.button("Refresh metrics"):
        st.rerun()
