"""Application entry point: shared presentation, navigation, and screen selection."""

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from frontend.ui import render_shell
from frontend.views import (
    actions,
    comparisons,
    documents,
    extract,
    operations,
    policies,
    quotations,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

st.set_page_config(page_title="VendorOps AI", page_icon="📄", layout="wide")
render_shell()

screens = {
    "PDF Text": extract.render,
    "Documents": documents.render,
    "Quotes": quotations.render,
    "Compare": comparisons.render,
    "Policies": policies.render,
    "Actions": actions.render,
    "Operations": operations.render,
}
page = st.sidebar.radio("Workspace", list(screens))
st.sidebar.divider()
st.sidebar.markdown("**A clear path from document to decision.**")
st.sidebar.caption("Extract → Review → Compare → Apply policy → Approve")
st.sidebar.markdown("[Project & documentation](https://github.com/surajnair17/vendorops-ai)")
screens[page]()
