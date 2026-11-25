"""Shared visual shell; presentation never changes application permissions or provider mode."""

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"


def render_shell() -> None:
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.sidebar.markdown(
        '<div class="vo-brand"><span class="vo-brand-mark">V</span>'
        "<div>VENDOROPS<span>DOCUMENT REVIEW WORKSPACE</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="vo-eyebrow">VENDOR OPERATIONS / HUMAN OVERSIGHT</p>', unsafe_allow_html=True
    )
    st.title("VendorOps AI")
    st.caption("Review documents. Trace decisions. Approve every follow-up.")
    st.divider()
