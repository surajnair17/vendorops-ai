import os
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

st.set_page_config(page_title="VendorOps AI", page_icon="📄", layout="wide")
st.title("VendorOps AI")
page = st.sidebar.radio("Workspace", ["PDF Text", "Documents", "Compare", "Policies"])
if page == "Policies":
    from frontend.workspace import policies

    policies()
    st.stop()
if page == "Compare":
    from frontend.workspace import comparisons

    comparisons()
    st.stop()
if page == "Documents":
    from frontend.workspace import documents

    documents()
    st.stop()
st.write("Upload a digital PDF to extract and inspect its text. Scanned PDFs need OCR.")
backend_url = os.getenv("VENDOROPS_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def clear_result() -> None:
    st.session_state.pop("extraction", None)


uploaded = st.file_uploader("PDF document", type=["pdf"], on_change=clear_result)
if st.button("Extract Text", disabled=uploaded is None, type="primary"):
    clear_result()
    with st.spinner("Extracting text…"):
        try:
            response = httpx.post(
                f"{backend_url}/api/v1/documents/extract",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                timeout=float(os.getenv("VENDOROPS_REQUEST_TIMEOUT_SECONDS", "60")),
            )
            if response.is_success:
                st.session_state.extraction = response.json()
            else:
                try:
                    st.error(response.json()["error"]["message"])
                except (ValueError, KeyError, TypeError):
                    st.error(f"The backend returned an error (HTTP {response.status_code}).")
        except httpx.TimeoutException:
            st.error("Processing timed out. Try a smaller PDF or check the backend.")
        except httpx.RequestError:
            st.error("Cannot reach the backend. Start FastAPI and check its address.")
        except ValueError:
            st.error("The backend returned an unreadable response.")

if result := st.session_state.get("extraction"):
    if result["extraction_status"] == "success":
        st.success(result["message"])
    else:
        st.warning(result["message"])
    left, right = st.columns(2)
    left.metric("Pages", result["page_count"])
    right.metric("Characters", result["character_count"])
    st.text_area("Extracted text", result["extracted_text"], height=400)
