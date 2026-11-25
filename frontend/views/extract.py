"""Stateless PDF upload and extraction; persistent review lives in documents.py."""

import os

import httpx
import streamlit as st


def clear_result() -> None:
    st.session_state.pop("extraction", None)


def render() -> None:
    st.header("PDF text extraction")
    st.write("Start with the source. Upload a digital PDF and inspect every page's text.")
    st.markdown(
        '<div class="vo-steps">'
        '<div class="vo-step"><span>01 / UPLOAD</span><strong>Bring your document</strong>'
        "<p>Start with an invoice, purchase order, or quotation.</p></div>"
        '<div class="vo-step"><span>02 / EXTRACT</span><strong>Read the source text</strong>'
        "<p>Extract existing PDF text, with page and character counts.</p></div>"
        '<div class="vo-step"><span>03 / REVIEW</span><strong>Keep decisions traceable</strong>'
        "<p>Use Documents to store, structure, and correct a record.</p></div></div>",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("PDF document", type=["pdf"], on_change=clear_result)
    st.caption("Up to 10 MiB by default. This screen does not store uploads or run OCR.")
    backend_url = os.getenv("VENDOROPS_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
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
        st.text_area("Extracted text", result["extracted_text"], height=300)
