from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest


def test_frontend_renders_without_backend():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "VendorOps AI"
    assert app.button[0].disabled


def test_scanned_upload_requires_opt_in_then_displays_ocr_and_clears_stale_text(monkeypatch):
    status = {"value": "queued"}
    calls = []
    no_text = {
        "filename": "scan.pdf",
        "page_count": 1,
        "extracted_text": "",
        "character_count": 0,
        "extraction_status": "no_text",
        "message": "No text found.",
    }
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: httpx.Response(200, json=no_text))

    def request(method, url, **kwargs):
        path = url.split("/api/v1", 1)[1]
        calls.append((method, path))
        responses = {
            ("GET", "/metrics"): {"ocr_provider": "local"},
            ("POST", "/documents"): {"id": "doc-1"},
            ("POST", "/documents/doc-1/ocr"): {"job_id": "job-1", "status": "queued"},
            ("GET", "/jobs/job-1"): {"data": {"status": status["value"]}},
            ("GET", "/documents/doc-1"): {
                "data": {"filename": "scan.pdf", "pages": ["Synthetic quote 250"], "page_count": 1}
            },
        }
        return httpx.Response(200, json=responses[method, path])

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    app.file_uploader[0].upload("scan.pdf", b"synthetic scanned PDF", "application/pdf").run()
    app.button[0].click().run()
    assert not app.exception
    assert not any(method == "POST" for method, _ in calls)
    next(b for b in app.button if b.label == "Read scanned PDF with local OCR").click().run()
    assert calls.count(("POST", "/documents")) == 1
    assert calls.count(("POST", "/documents/doc-1/ocr")) == 1
    assert not app.text_area
    status["value"] = "succeeded"
    next(b for b in app.button if b.label == "Refresh OCR status").click().run()
    assert not app.exception
    assert app.text_area[0].value == "Synthetic quote 250"
    app.run()
    assert calls.count(("POST", "/documents")) == 1
    assert calls.count(("POST", "/documents/doc-1/ocr")) == 1
    app.file_uploader[0].clear().run()
    assert not app.text_area
    assert app.button[0].disabled


@pytest.mark.parametrize("provider", ["disabled", "textract"])
def test_scan_screen_never_starts_an_unconfigured_or_cloud_ocr_provider(monkeypatch, provider):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json={"extraction_status": "no_text", "message": "No text found."}
        ),
    )

    def request(method, url, **kwargs):
        assert method == "GET" and url.endswith("/metrics")
        return httpx.Response(200, json={"ocr_provider": provider})

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
    app.file_uploader[0].upload("scan.pdf", b"synthetic scanned PDF", "application/pdf").run()
    app.button[0].click().run()
    assert not app.exception
    assert not any(b.label == "Read scanned PDF with local OCR" for b in app.button)
