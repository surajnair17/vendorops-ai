import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.config import settings
from backend.main import app


@pytest.fixture(autouse=True)
def offline_configuration(monkeypatch):
    monkeypatch.setattr(settings, "provider", "fixture")
    monkeypatch.setattr(settings, "live_calls_enabled", False)
    monkeypatch.setattr(settings, "live_send_enabled", False)
    monkeypatch.setattr(settings, "recipient_allowlist", "reviewer@example.test")
    monkeypatch.setattr(settings, "storage_mode", "local")
    monkeypatch.setattr(settings, "chroma_host", "")
    monkeypatch.setattr(settings, "ocr_provider", "local")


def make_pdf(*pages: str) -> bytes:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        return document.tobytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    db.engine_for(str(tmp_path.resolve())).dispose()
