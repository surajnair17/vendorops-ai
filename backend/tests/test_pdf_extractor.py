import pymupdf
import pytest
from conftest import make_pdf

from backend.config import settings
from backend.services.pdf_extractor import extract_pdf


def test_valid_multipage_pdf():
    result = extract_pdf(make_pdf("Invoice INV-001", "Total: 100.00"), "invoice.pdf")
    assert result.page_count == 2
    assert "INV-001" in result.extracted_text
    assert "\f" in result.extracted_text
    assert result.character_count == len(result.extracted_text)


def test_blank_and_image_only(client):
    with pymupdf.open() as document:
        page = document.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 10, 10), False)
        pixmap.clear_with(120)
        page.insert_image(pymupdf.Rect(10, 10, 100, 100), pixmap=pixmap)
        scanned = document.tobytes()
    for content in (make_pdf(""), scanned):
        response = client.post("/api/v1/documents/extract", files={"file": ("scan.pdf", content)})
        assert response.status_code == 200
        assert response.json()["extraction_status"] == "no_text"
        assert response.json()["character_count"] == 0


@pytest.mark.parametrize(
    "filename,content,status,code",
    [
        ("empty.pdf", b"", 400, "empty_upload"),
        ("broken.pdf", b"%PDF-1.7\nnot a pdf", 400, "corrupt_pdf"),
        ("fake.pdf", b"not a PDF", 415, "unsupported_content"),
        ("text.txt", b"Hello", 415, "unsupported_file_type"),
    ],
)
def test_controlled_errors(client, filename, content, status, code):
    response = client.post("/api/v1/documents/extract", files={"file": (filename, content)})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_encrypted_pdf(client):
    with pymupdf.open(stream=make_pdf("Private"), filetype="pdf") as document:
        encrypted = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader"
        )
    response = client.post("/api/v1/documents/extract", files={"file": ("locked.pdf", encrypted)})
    assert response.status_code == 422


def test_limit_boundary(client, monkeypatch):
    content = make_pdf("Boundary")
    monkeypatch.setattr(settings, "max_upload_bytes", len(content))
    assert (
        client.post("/api/v1/documents/extract", files={"file": ("a.pdf", content)}).status_code
        == 200
    )
    monkeypatch.setattr(settings, "max_upload_bytes", len(content) - 1)
    assert (
        client.post("/api/v1/documents/extract", files={"file": ("a.pdf", content)}).status_code
        == 413
    )


def test_missing_upload_and_health(client):
    assert client.post("/api/v1/documents/extract").status_code == 422
    assert client.get("/health").json() == {"status": "ok"}


def test_unexpected_error_hides_details(client, monkeypatch, caplog):
    def broken(*args):
        raise Exception("secret document content")

    monkeypatch.setattr("backend.routes.documents.extract_pdf", broken)
    response = client.post(
        "/api/v1/documents/extract", files={"file": ("a.pdf", make_pdf("Hello"))}
    )
    assert response.status_code == 500
    assert "secret" not in response.text
    assert "secret document content" not in caplog.text
