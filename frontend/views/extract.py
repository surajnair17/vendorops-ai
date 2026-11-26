"""Stateless PDF upload and extraction; persistent review lives in documents.py."""

import os

import httpx
import streamlit as st

from frontend.client import api


def clear_result() -> None:
    for key in ("extraction", "extract_ocr_document_id", "extract_ocr_job"):
        st.session_state.pop(key, None)


def render_local_ocr(uploaded) -> None:
    st.caption(
        "Local OCR reads scanned pages and saves a copy of this PDF in Documents for review."
    )
    job = st.session_state.get("extract_ocr_job")
    if job is None:
        metrics = api("GET", "/metrics")
        if not metrics:
            return
        if metrics["ocr_provider"] != "local":
            st.info(
                "Local OCR is not enabled. Open Documents to review the configured OCR options."
            )
            return
        if not st.button(
            "Read scanned PDF with local OCR", type="primary", disabled=uploaded is None
        ):
            return
        document_id = st.session_state.get("extract_ocr_document_id")
        if document_id is None:
            document = api(
                "POST",
                "/documents",
                files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
            )
            if not document:
                return
            document_id = document["id"]
            st.session_state["extract_ocr_document_id"] = document_id
        job = api("POST", f"/documents/{document_id}/ocr")
        if not job:
            return
        st.session_state["extract_ocr_job"] = job

    record = api("GET", f"/jobs/{job['job_id']}")
    if not record:
        return
    state = record["data"]["status"]
    if state == "succeeded":
        document = api("GET", f"/documents/{st.session_state['extract_ocr_document_id']}")
        if not document:
            return
        text = "\n\n\f\n\n".join(document["data"]["pages"])
        if not text.strip():
            st.warning("OCR finished but found no readable text. The page may be blank or unclear.")
            return
        st.success("Scanned text recognized with local OCR. Review it against the original PDF.")
        left, right = st.columns(2)
        left.metric("Pages", document["data"]["page_count"])
        right.metric("Characters", len(text))
        st.text_area("Extracted text", text, height=300)
        st.download_button("Download OCR text", text, file_name="ocr-text.txt", mime="text/plain")
        st.caption(f"Saved in Documents as {document['data']['filename']}.")
    elif state in {"queued", "starting", "waiting", "running"}:
        st.info(f"Local OCR is {state}. The worker must be running to process scanned pages.")
        if st.button("Refresh OCR status"):
            st.rerun()
    else:
        code = record["data"].get("error_code", state)
        st.error(f"OCR did not complete ({code}). Inspect this document's job in Documents.")


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
    st.caption(
        "Up to 10 MiB by default. Extract Text reads existing text without storing the PDF. "
        "Scanned PDFs can use the separate local OCR action."
    )
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
            st.warning(
                "This PDF has no embedded text. If its pages contain visible writing, "
                "use local OCR below."
            )
            render_local_ocr(uploaded)
            return
        left, right = st.columns(2)
        left.metric("Pages", result["page_count"])
        right.metric("Characters", result["character_count"])
        st.text_area("Extracted text", result["extracted_text"], height=300)
