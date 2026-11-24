import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest
from conftest import make_pdf

from backend import db
from backend.config import settings
from backend.errors import AppError
from backend.services.local_ocr import process_local_ocr_once, recognize_pages


def test_offline_ocr_job_preserves_digital_and_invalidates_old_structure(client, monkeypatch):
    monkeypatch.setattr("backend.services.local_ocr.require_tesseract", lambda: "tesseract")
    record = client.post(
        "/api/v1/documents", files={"file": ("mixed.pdf", make_pdf("Keep", ""))}
    ).json()
    first = client.post(f"/api/v1/documents/{record['id']}/ocr")
    assert first.status_code == 202
    assert (
        client.post(f"/api/v1/documents/{record['id']}/ocr").json()["job_id"]
        == first.json()["job_id"]
    )
    monkeypatch.setattr(
        "backend.services.local_ocr.recognize_pages", lambda *args: [[], ["Scan 200"]]
    )
    assert process_local_ocr_once()
    assert not process_local_ocr_once()
    result = client.get(f"/api/v1/documents/{record['id']}").json()
    assert result["data"]["pages"] == ["Keep", "Scan 200"]
    assert result["data"]["revision_id"] is None
    with db.transaction() as connection:
        assert db.get(connection, first.json()["job_id"])["data"]["status"] == "succeeded"
        assert db.all_records(connection, "text_revision")[0]["data"]["provider"] == "tesseract"
        assert db.all_records(connection, "usage") == []


def test_local_ocr_timeout_cleanup_and_digital_page_skip(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.local_ocr.require_tesseract", lambda: "tesseract")
    source = tmp_path / "mixed.pdf"
    source.write_bytes(make_pdf("Digital", ""))
    paths = []

    def timeout(arguments, **kwargs):
        assert arguments[-2:] == ["--psm", "3"]
        assert kwargs["timeout"] == settings.ocr_page_timeout_seconds
        assert Path(arguments[1]).is_file()
        paths.append(Path(arguments[1]))
        raise subprocess.TimeoutExpired(arguments, 60)

    monkeypatch.setattr("backend.services.local_ocr.subprocess.run", timeout)
    with pytest.raises(AppError) as failure:
        recognize_pages(source, ["Digital", ""])
    assert failure.value.code == "ocr_timeout"
    assert len(paths) == 1
    assert not paths[0].parent.exists()


def test_missing_tesseract_and_disabled_provider_are_actionable(client, monkeypatch):
    record = client.post("/api/v1/documents", files={"file": ("scan.pdf", make_pdf(""))}).json()
    monkeypatch.setattr("backend.services.local_ocr.shutil.which", lambda value: None)
    assert (
        client.post(f"/api/v1/documents/{record['id']}/ocr").json()["error"]["code"]
        == "local_ocr_unavailable"
    )
    monkeypatch.setattr(settings, "ocr_provider", "disabled")
    assert client.post(f"/api/v1/documents/{record['id']}/ocr").status_code == 403


def test_stale_document_and_failed_ocr_never_replace_text(client, monkeypatch):
    monkeypatch.setattr("backend.services.local_ocr.require_tesseract", lambda: "tesseract")
    record = client.post("/api/v1/documents", files={"file": ("scan.pdf", make_pdf(""))}).json()
    job = client.post(f"/api/v1/documents/{record['id']}/ocr").json()
    with db.transaction() as connection:
        stored = db.get(connection, record["id"])
        db.update(connection, stored, {**stored["data"], "pages": ["Human revision"]})
    monkeypatch.setattr("backend.services.local_ocr.recognize_pages", lambda *args: [["Old scan"]])
    assert process_local_ocr_once()
    assert client.get(f"/api/v1/jobs/{job['job_id']}").json()["data"]["status"] == "failed"
    assert client.get(f"/api/v1/documents/{record['id']}").json()["data"]["pages"] == [
        "Human revision"
    ]


def test_local_ocr_recovers_expired_worker_lease(client, monkeypatch):
    monkeypatch.setattr("backend.services.local_ocr.require_tesseract", lambda: "tesseract")
    record = client.post("/api/v1/documents", files={"file": ("scan.pdf", make_pdf(""))}).json()
    job = client.post(f"/api/v1/documents/{record['id']}/ocr").json()
    with db.transaction() as connection:
        stored = db.get(connection, job["job_id"])
        db.update(
            connection,
            stored,
            {
                **stored["data"],
                "status": "starting",
                "start_attempts": 1,
                "lease_until": "2000-01-01",
            },
        )
    monkeypatch.setattr("backend.services.local_ocr.recognize_pages", lambda *args: [["Recovered"]])
    assert process_local_ocr_once()
    assert client.get(f"/api/v1/jobs/{job['job_id']}").json()["data"]["start_attempts"] == 2


def test_oversized_page_is_rejected_before_raster_allocation(tmp_path, monkeypatch):
    source = tmp_path / "large.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page(width=3000, height=3000)
        pdf.save(source)
    monkeypatch.setattr("backend.services.local_ocr.require_tesseract", lambda: "tesseract")
    with pytest.raises(AppError) as error:
        recognize_pages(source, [""])
    assert error.value.code == "ocr_page_too_large"


@pytest.mark.skipif(
    not shutil.which(settings.tesseract_command), reason="Install Tesseract for real offline OCR"
)
def test_real_scanned_pdf_through_durable_worker(client):
    with pymupdf.open() as original, pymupdf.open() as scanned:
        page = original.new_page()
        page.insert_text((72, 100), "INVOICE 12345\nTotal 100.00 USD", fontsize=24)
        raster = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        scanned.new_page().insert_image(page.rect, pixmap=raster)
        content = scanned.tobytes()
    record = client.post("/api/v1/documents", files={"file": ("scan.pdf", content)}).json()
    assert not record["data"]["pages"][0].strip()
    response = client.post(f"/api/v1/documents/{record['id']}/ocr")
    assert response.status_code == 202
    assert process_local_ocr_once()
    updated = client.get(f"/api/v1/documents/{record['id']}").json()
    assert "12345" in updated["data"]["pages"][0]
    assert "100.00" in updated["data"]["pages"][0]
