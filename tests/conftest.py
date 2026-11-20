import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


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
